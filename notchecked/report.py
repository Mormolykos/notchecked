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

WHAT THIS MODULE LEARNED BY BEING ATTACKED
------------------------------------------
An audit of the first draft landed five hits, and two of them were the library
committing its own thesis error one level up:

1. Declaring every target OUT_OF_SCOPE gave `evaluable == 0` and **exit 0**.
   A report that judged nothing read as green. Excluding a target is a claim,
   and a tool that excludes everything has made no measurement -- so `exit_code`
   now refuses to return 0 when nothing at all was checked.
2. A target that never became a record was invisible. That is precisely the
   discovery-loop failure this library was written for: `except Exception: pass`
   meant a file present on disk never entered the report and so could not be
   distinguished from one that passed. A report cannot notice a row nobody
   wrote, so `expected` lets the caller declare the target set up front and
   `missing()` reports what never arrived.
3. Two records for one target were counted twice in silence. Now refused.
4. `failing_verdicts` defaulted to `{"FAIL"}`, so a compliance tool emitting
   `NON_COMPLIANT` exited 0 on real failures. There is no safe default for
   another domain's vocabulary, so there is now no default.
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


class ReportError(ValueError):
    """Raised for a report that cannot be honestly summarised."""


@dataclass
class Report:
    """A run's records plus the counts that fall out of them.

    `expected` is the target set the caller believes exists. Supplying it is what
    turns "nothing reported a problem" into "everything I set out to judge was
    accounted for". Without it, a target that silently never arrived cannot be
    detected by anything downstream.

    `failing_verdicts` has no default. Verdicts are the domain's vocabulary and
    guessing at them is how a failed control exits zero.
    """

    tool: str
    records: list[Record] = field(default_factory=list)
    vocabulary: Vocabulary | None = None
    failing_verdicts: frozenset[str] | None = None
    expected: frozenset[str] | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.failing_verdicts is not None:
            self.failing_verdicts = frozenset(self.failing_verdicts)
        if self.expected is not None:
            self.expected = frozenset(self.expected)

    # -- writing -----------------------------------------------------------

    def add(self, record: Record) -> Record:
        """Append a record, validating its reason and its uniqueness.

        A target with two states is a bug in the caller, not a fact about the
        target, so it raises rather than being counted twice."""
        if any(r.target == record.target for r in self.records):
            raise ReportError(
                f"{record.target!r} already has a record; a target lands in "
                f"exactly one state or the counts are meaningless"
            )
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

    def missing(self) -> Sequence[str]:
        """Declared targets that never produced a record.

        Empty when `expected` was not supplied -- which is not the same as
        nothing being missing, and `expected_declared` says which case you are
        looking at."""
        if self.expected is None:
            return []
        seen = {r.target for r in self.records}
        return sorted(self.expected - seen)

    @property
    def expected_declared(self) -> bool:
        return self.expected is not None

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def evaluable(self) -> int:
        """Targets that were mechanically checkable, plus any declared target
        that never arrived -- an absent row cannot be out of scope, because
        nothing ever judged whether it was."""
        return sum(1 for r in self.records
                   if r.coverage.counts_toward_denominator) + len(self.missing())

    @property
    def checked(self) -> int:
        return sum(1 for r in self.records if r.coverage.is_checked)

    @property
    def waived(self) -> int:
        """Targets in scope that a named person accepted rather than judging.

        Counted and surfaced separately because a waiver is an auditable
        decision, not a shrug -- and because a report where every target is
        waived must not read differently from one where every target was
        excluded. Both are 'nothing was measured'."""
        return sum(1 for r in self.records if r.coverage.is_waived)

    @property
    def excluded(self) -> int:
        return sum(1 for r in self.records
                   if not r.coverage.counts_toward_denominator)

    @property
    def excluded_ratio(self) -> float | None:
        """What fraction of the declared work was ruled out rather than judged.

        Reported beside `coverage_ratio` on purpose. Excluding a target is a
        claim, and a high exclusion rate is the place a coverage number goes to
        hide."""
        return self.excluded / self.total if self.total else None

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
        if self.failing_verdicts is None:
            verdicts = self.by_verdict()
            if verdicts:
                raise ReportError(
                    f"{self.tool}: records carry verdicts {sorted(verdicts)} but "
                    f"failing_verdicts was never declared. There is no safe "
                    f"default for another domain's vocabulary"
                )
            return []
        return [r for r in self.records
                if r.coverage.is_checked and r.verdict in self.failing_verdicts]

    # -- output ------------------------------------------------------------

    @property
    def exit_code(self) -> int:
        """1 if something was checked and failed. 2 if coverage is incomplete or
        nothing was checked at all. 0 only when work was done and none failed.

        Nothing-was-checked never returns 0. A tool that excluded every target
        has made no measurement, and a report of no measurement must not be
        indistinguishable from a clean one."""
        if self.failures():
            return EXIT_VERDICT_FAILED
        if self.missing():
            return EXIT_COVERAGE_INCOMPLETE
        if self.total and self.checked == 0:
            return EXIT_COVERAGE_INCOMPLETE
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
                "waived": self.waived,
                "missing": len(self.missing()),
                "coverage_ratio": self.coverage_ratio,
                "excluded_ratio": self.excluded_ratio,
                "expected_declared": self.expected_declared,
                "by_state": {s.value: n for s, n in self.by_state().items()},
                "by_verdict": self.by_verdict(),
                "by_owner": self.by_owner(),
            },
            "missing": list(self.missing()),
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
            pct = f"{self.excluded_ratio:.0%}" if self.excluded_ratio else "0%"
            lines[0] += f", {self.excluded} out of scope ({pct} of all targets)"
        if self.waived:
            lines[0] += f", {self.waived} waived"
        if not self.expected_declared:
            lines.append("  no expected target set declared - a target that "
                         "never arrived cannot be detected")
        for verdict, n in sorted(self.by_verdict().items()):
            lines.append(f"  {verdict}: {n}")
        for target in self.missing():
            lines.append(f"  MISSING: {target} - expected, never reported")
        gaps = self.gaps()
        if gaps:
            lines.append(f"  not checked: {len(gaps)}")
            for r in gaps:
                lines.append(
                    f"    [{r.coverage.value}] {r.target}: {r.reason}"
                    f"  -> {r.coverage.meta.remediation}"
                )
        return "\n".join(lines)
