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
from types import MappingProxyType
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
    # Required by NOT_CHECKED/PREREQUISITE_FAILED: the target that failed first.
    # A cascade without a pointer to its cause is a dead end for whoever reads it.
    blocked_by: str | None = None
    # Required by NOT_CHECKED/WAIVED: who accepted the gap. A waiver with no
    # name on it is not a waiver, it is a silence with paperwork.
    waived_by: str | None = None
    waiver_expires: str | None = None
    # Required by OUT_OF_SCOPE/DATA_PERMANENT: the target type the exclusion is
    # permanent WITH RESPECT TO. "Nobody, never" is not a property of the control
    # -- it is a property of the pairing of that control with a kind of artifact.
    # A Kubernetes control is permanently out of scope only while the target has
    # no Kubernetes; change the target and it becomes a row. Unqualified, two
    # reports on the same framework disagree and both are correct.
    permanent_wrt: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # `frozen=True` protects the binding, not the object bound. A mutable
        # mapping behind a frozen record is a record that can change after the
        # check that wrote it has returned, which defeats the point of writing
        # it at the moment of decision.
        object.__setattr__(self, "extra", MappingProxyType(dict(self.extra)))
        object.__setattr__(self, "evidence", tuple(self.evidence))

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
            if (self.coverage is Coverage.NOT_CHECKED_PREREQUISITE_FAILED
                    and not self.blocked_by):
                raise ValueError(
                    f"{self.target}: PREREQUISITE_FAILED requires blocked_by - "
                    f"a cascade with no pointer to its cause is a dead end"
                )
            if (self.coverage is Coverage.NOT_CHECKED_WAIVED
                    and not self.waived_by):
                raise ValueError(
                    f"{self.target}: WAIVED requires waived_by - an unowned "
                    f"waiver is a silence with paperwork"
                )
            if (self.coverage is Coverage.OUT_OF_SCOPE_DATA_PERMANENT
                    and not self.permanent_wrt):
                raise ValueError(
                    f"{self.target}: DATA_PERMANENT requires permanent_wrt - "
                    f"permanence is relative to a target type, and unqualified "
                    f"'never' cannot be reconciled across two reports"
                )
        if (self.permanent_wrt
                and self.coverage is not Coverage.OUT_OF_SCOPE_DATA_PERMANENT):
            raise ValueError(
                f"{self.target}: permanent_wrt only means something under "
                f"OUT_OF_SCOPE/DATA_PERMANENT; {self.coverage.value} can change"
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
        if self.blocked_by:
            out["blocked_by"] = self.blocked_by
        if self.waived_by:
            out["waived_by"] = self.waived_by
        if self.waiver_expires:
            out["waiver_expires"] = self.waiver_expires
        if self.permanent_wrt:
            out["permanent_wrt"] = self.permanent_wrt
        if self.verdict is not None:
            out["verdict"] = self.verdict
        if self.evidence:
            out["evidence"] = list(self.evidence)
        if self.detail:
            out["detail"] = self.detail
        if self.extra:
            out["extra"] = dict(self.extra)
        return out
