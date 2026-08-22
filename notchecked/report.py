"""The report. Every count is derived from the records, at the moment it is read.

Nothing here stores a total. A count held beside the rows it summarises can
drift from them, and nothing catches it -- that is a bug you have not hit yet
rather than one you have designed out.

Two denominators, and the distinction is the whole reason this is a library and
not a dictionary:

    total       every target considered, in scope or not
    evaluable   the targets that were mechanically checkable at all

A percentage over `total` is a claim about the framework you named. A percentage
over `evaluable` is a claim about your own evidence. Only the second one is
yours to make, and `coverage_ratio` computes only that one.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .record import Record, Vocabulary
from .states import Coverage

SCHEMA = "notchecked/1"

# Exit codes. Separate from severity on purpose: a tool that cannot tell "your
# thing is broken" from "I could not judge your thing" is lying to CI quietly.
EXIT_OK = 0
EXIT_VERDICT_FAILED = 1
EXIT_COVERAGE_INCOMPLETE = 2


@dataclass
class Report:
    """A run's records plus the counts that fall out of them."""

    tool: str
    records: list[Record] = field(default_factory=list)
    vocabulary: Vocabulary | None = None
    failing_verdicts: frozenset[str] = frozenset({"FAIL"})
    context: Mapping[str, Any] = field(default_factory=dict)

    # -- writing -----------------------------------------------------------

    def add(self, record: Record) -> Record:
        """Append a record, validating its reason against the vocabulary.

        Validation happens here rather than in `Record` so that a caller can
        build records without a vocabulary in hand, but cannot *report* one that
        the vocabulary does not define."""
        if record.reason and self.vocabulary is not None:
            self.vocabulary.resolve(record.reason, record.coverage)
        self.records.append(record)
        return record

    def extend(self, records: Iterable[Record]) -> None:
        for r in records:
            self.add(r)

    # -- derived counts ----------------------------------------------------

    def __iter__(self) -> Iterator[Record]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def by_state(self) -> Mapping[Coverage, int]:
        counts = Counter(r.coverage for r in self.records)
        return {state: counts.get(state, 0) for state in Coverage}

    def by_verdict(self) -> Mapping[str, int]:
        """Verdicts, over CHECKED records only. A gap has no verdict."""
        return dict(Counter(
            r.verdict for r in self.records
            if r.coverage.is_checked and r.verdict is not None
        ))

    def by_owner(self) -> Mapping[str, int]:
        """Who owns the outstanding work, over the gaps only.

        The number a reader acts on. Two gaps with the same owner are one
        to-do; two with different owners are two, and one of them may be
        nobody's."""
        return dict(Counter(
            r.coverage.meta.owner.value
            for r in self.records if not r.coverage.is_checked
        ))

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def evaluable(self) -> int:
        return sum(1 for r in self.records
                   if r.coverage.counts_toward_denominator)

    @property
    def checked(self) -> int:
        return sum(1 for r in self.records if r.coverage.is_checked)

    @property
    def excluded(self) -> int:
        return self.total - self.evaluable

    @property
    def coverage_ratio(self) -> float | None:
        """checked / evaluable. None when nothing was evaluable at all.

        None rather than 0.0 or 1.0 deliberately: a ratio over an empty
        denominator is not a coverage of zero, it is an absence of coverage, and
        the two must not render alike."""
        return self.checked / self.evaluable if self.evaluable else None

    def gaps(self) -> Sequence[Record]:
        return [r for r in self.records if not r.coverage.is_checked]

    def failures(self) -> Sequence[Record]:
        return [r for r in self.records
                if r.coverage.is_checked and r.verdict in self.failing_verdicts]

    # -- output ------------------------------------------------------------

    @property
    def exit_code(self) -> int:
        """1 if something was checked and failed. 2 if nothing failed but
        coverage is incomplete. 0 only when everything evaluable was evaluated
        and no verdict failed.

        Incomplete coverage never returns 0. Silence reads as green, and that is
        the failure this library exists to prevent."""
        if self.failures():
            return EXIT_VERDICT_FAILED
        if self.checked < self.evaluable:
            return EXIT_COVERAGE_INCOMPLETE
        return EXIT_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "tool": self.tool,
            "context": dict(self.context),
            "counts": {
                "total": self.total,
                "evaluable": self.evaluable,
                "checked": self.checked,
                "excluded": self.excluded,
                "coverage_ratio": self.coverage_ratio,
                "by_state": {s.value: n for s, n in self.by_state().items()},
                "by_verdict": self.by_verdict(),
                "by_owner": self.by_owner(),
            },
            "records": [r.to_dict() for r in self.records],
            "exit_code": self.exit_code,
        }

    def to_json(self, **kwargs: Any) -> str:
        kwargs.setdefault("indent", 2)
        return json.dumps(self.to_dict(), **kwargs)

    def render(self) -> str:
        """A human-readable summary that states its own coverage.

        A validator that reports a verdict without reporting its coverage is
        asserting something it did not measure."""
        lines = [f"{self.tool}: {self.checked}/{self.evaluable} evaluable "
                 f"targets checked"]
        if self.excluded:
            lines[0] += f", {self.excluded} out of scope"
        for verdict, n in sorted(self.by_verdict().items()):
            lines.append(f"  {verdict}: {n}")
        gaps = self.gaps()
        if gaps:
            lines.append(f"  not checked: {len(gaps)}")
            for r in gaps:
                lines.append(
                    f"    [{r.coverage.value}] {r.target}: {r.reason}"
                    f"  -> {r.coverage.meta.remediation}"
                )
        return "\n".join(lines)
