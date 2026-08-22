"""One record per check target, and the vocabulary that constrains it.

A reason string is readable by a human and useless to CI. That sentence is why
this module exists: the state is typed, and the reason is drawn from a
vocabulary the caller declares up front, so a job counting gaps can tell two
gaps apart without parsing prose.

The record is written **by the check, at the moment it decides**, carrying its
own reason -- never reconstructed afterwards from what is missing. Provenance as
a byproduct rather than a later reconstruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .states import Coverage


class VocabularyError(ValueError):
    """Raised when a record carries a reason the vocabulary does not define.

    Deliberately loud. A tool that silently accepts an unregistered reason has
    free text again, one release later."""


@dataclass(frozen=True)
class Reason:
    """A registered, machine-readable cause. `code` is what CI branches on;
    `describes` is for the person reading the report."""

    code: str
    state: Coverage
    describes: str


class Vocabulary:
    """The fixed set of reasons this tool can emit, declared before any run.

    Registration is per-state on purpose. The same code cannot mean
    "the log never carried this signal" under one state and "the checker threw"
    under another -- those have different owners, and sharing a code would put
    two different to-dos in one bucket.
    """

    def __init__(self, reasons: Iterable[Reason] = ()) -> None:
        self._by_code: dict[str, Reason] = {}
        for r in reasons:
            self.register(r)

    def register(self, reason: Reason) -> Reason:
        existing = self._by_code.get(reason.code)
        if existing is not None and existing != reason:
            raise VocabularyError(
                f"reason code {reason.code!r} is already registered for "
                f"{existing.state.value}; a code means one thing or it means nothing"
            )
        self._by_code[reason.code] = reason
        return reason

    def resolve(self, code: str, state: Coverage) -> Reason:
        reason = self._by_code.get(code)
        if reason is None:
            raise VocabularyError(
                f"unregistered reason code {code!r}. Declare it in the "
                f"vocabulary; free-text reasons are the thing this replaces"
            )
        if reason.state is not state:
            raise VocabularyError(
                f"reason {code!r} is registered for {reason.state.value} but was "
                f"emitted under {state.value}"
            )
        return reason

    def codes(self) -> Mapping[str, Reason]:
        return dict(self._by_code)


@dataclass(frozen=True)
class Record:
    """What happened to one check target.

    `coverage` and `verdict` are orthogonal axes and the constructor enforces it:

    - a non-CHECKED record must carry a reason and must not carry a verdict,
      because no determination was made;
    - a CHECKED record must not carry a reason, because nothing was skipped.

    That invariant is the whole point. A run whose loss was exactly zero once
    returned PASS with a list of the checks that had "cleared" it, because
    skipping and passing shared a representation.
    """

    target: str
    coverage: Coverage
    reason: str | None = None
    verdict: str | None = None
    evidence: tuple[str, ...] = ()
    detail: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.coverage.is_checked:
            if self.reason is not None:
                raise ValueError(
                    f"{self.target}: CHECKED records carry no reason - nothing "
                    f"was skipped"
                )
        else:
            if not self.reason:
                raise ValueError(
                    f"{self.target}: {self.coverage.value} requires a reason "
                    f"code; an unexplained gap is indistinguishable from a pass"
                )
            if self.verdict is not None:
                raise ValueError(
                    f"{self.target}: {self.coverage.value} cannot carry a "
                    f"verdict - no determination was made"
                )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "target": self.target,
            "coverage": self.coverage.value,
            "owner": self.coverage.meta.owner.value,
            "permanence": self.coverage.meta.permanence.value,
        }
        if self.reason:
            out["reason"] = self.reason
        if self.verdict is not None:
            out["verdict"] = self.verdict
        if self.evidence:
            out["evidence"] = list(self.evidence)
        if self.detail:
            out["detail"] = self.detail
        if self.extra:
            out["extra"] = dict(self.extra)
        return out
