"""The six terminal coverage states, and what each one obliges someone to do.

WHY THIS EXISTS
---------------
Most validation tooling has two states: it passed, or it failed. Everything that
was not actually evaluated has to be forced into one of them, and it is wrong in
both directions.

Four real instances, from four unrelated domains:

1. ML training logs. A run whose loss was exactly 0.0 on every step returned
   PASS. Every loss-shape check is guarded against dividing by zero, so all of
   them skipped silently -- and the report then listed those same skipped checks
   as having run. A run that learned nothing passed, along with the list of
   checks that had cleared it.

2. The same tool, one loop earlier. A directory walk discovered candidate logs
   with `except Exception: pass`. A file that raised while being *found* never
   became a candidate and never appeared in the report at all: plainly visible
   on disk, absent from the output, indistinguishable from a file that passed.

3. Infrastructure compliance. A framework document is mostly prose that no
   generated artifact can satisfy or violate. Reporting against the framework
   name makes everything unevaluated look identical to everything that passed,
   and the 90% that was never in scope disappears from the output entirely.

4. Retrieval-grounded answering. An evaluation harness recorded model refusals
   under a failure type asserting an answer the model never gave; scored ten
   refusals as *correct* because the expected phrase appeared inside the sentence
   explaining what could not be determined; and missed eight correct answers
   because its negative pattern required a comma. One absent value, wrong in both
   directions, inside the tool being used to judge the hypothesis.

COVERAGE IS NOT VERDICT
-----------------------
`CHECKED` is not a result. It says a determination was made, not what it was.
The verdict vocabulary belongs to the domain -- pass/warn/fail, compliant/
non-compliant -- and hangs off `CHECKED` rather than sitting beside the
not-checked states. Collapsing the two axes is instance 1 above.

WHERE THIS TAXONOMY STARTS
--------------------------
It starts **after** the unit exists. In a linter a row is a check somebody wrote,
so the unit precedes the schema. In compliance the unit is the hard part: a
framework is prose, and turning it into checkable requirements is a judgment
call -- one paragraph can yield three, three can collapse into one. Nothing here
governs that mapping, and it must not be read as if the rows arrive by
themselves. Ingest decides what becomes a row; this library governs what happens
to a row once it is one. (Boris Teplitsky's first objection.)

Credit: the CALLER-versus-DATA ownership axis and the four-state split are
Panagiotis Gkilis's. The fixed reason vocabulary, counts derived from rows, the
permanence axis that splits OUT_OF_SCOPE / DATA, the requirement that permanence
name its reference target, and the rows-for-the-checkable-subset-with-a-count-
for-the-rest reporting rule are Boris Teplitsky's (New_Technician_7041), from the
infrastructure-compliance side.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Owner(str, Enum):
    """Who can act on this state. Two states with the same owner have the same
    kind of to-do; two with different owners must never share a bucket, because
    the remediation is different and only one of them is actionable by the
    person reading the report."""

    NOBODY = "nobody"
    CALLER = "caller"
    TOOLING = "tooling"
    DATA = "data"
    DEPLOYMENT = "deployment"
    WAIVER_HOLDER = "waiver_holder"   # a named person who accepted the gap
    UPSTREAM = "upstream"             # another target, which failed first


class Permanence(str, Enum):
    """Whether this state can ever change.

    The distinction Boris raised from compliance: a control excluded because the
    deployment does not use that service changes the moment the deployment
    changes. A control excluded because no generated artifact can ever evidence
    it does not. They read identically in a report and one of them is a backlog
    item forever.

    PERMANENCE IS RELATIVE, NEVER ABSOLUTE. Boris's second objection, and it is
    the one that changes the schema: `SETTLED` is meaningless on its own. The
    same control is checkable against one target and unevidenceable against
    another -- a Kubernetes control is permanently out of scope only while the
    target has no Kubernetes. Change the target and it becomes a row.

    So `SETTLED` must always name what it is settled *with respect to*, and
    `Record` refuses to construct an OUT_OF_SCOPE/DATA_PERMANENT row without it.
    Without that reference, two reports on the same framework disagree and both
    are correct, which makes the state useless for exactly the audience it was
    added for."""

    SETTLED = "settled"      # unchanging WITH RESPECT TO a named target type
    MUTABLE = "mutable"      # changes when the owner acts, or when inputs change


@dataclass(frozen=True)
class StateMeta:
    owner: Owner
    permanence: Permanence
    remediation: str


class Coverage(str, Enum):
    """The six terminal states. Every check target lands in exactly one.

    A report that cannot express all six will collapse two of them, and the
    collapse is silent."""

    CHECKED = "CHECKED"
    NOT_CHECKED_DATA_DEGENERATE = "NOT_CHECKED/DATA_DEGENERATE"
    NOT_CHECKED_CHECKER_FAILED = "NOT_CHECKED/CHECKER_FAILED"
    NOT_CHECKED_WAIVED = "NOT_CHECKED/WAIVED"
    NOT_CHECKED_PREREQUISITE_FAILED = "NOT_CHECKED/PREREQUISITE_FAILED"
    OUT_OF_SCOPE_CALLER = "OUT_OF_SCOPE/CALLER"
    OUT_OF_SCOPE_DATA_TRANSIENT = "OUT_OF_SCOPE/DATA_TRANSIENT"
    OUT_OF_SCOPE_DATA_PERMANENT = "OUT_OF_SCOPE/DATA_PERMANENT"

    @property
    def meta(self) -> StateMeta:
        return _META[self]

    @property
    def is_checked(self) -> bool:
        """True only for CHECKED. Everything else is a gap in coverage, and a
        gap is never evidence of a clean result."""
        return self is Coverage.CHECKED

    @property
    def counts_toward_denominator(self) -> bool:
        """Whether this target belongs in the denominator of a coverage claim.

        Out-of-scope targets do not: a percentage computed against everything
        that exists is a claim about the framework, while a percentage computed
        against what was mechanically checkable is a claim about your evidence.
        Only the second one is yours to make."""
        return self in (
            Coverage.CHECKED,
            Coverage.NOT_CHECKED_DATA_DEGENERATE,
            Coverage.NOT_CHECKED_CHECKER_FAILED,
            Coverage.NOT_CHECKED_WAIVED,
            Coverage.NOT_CHECKED_PREREQUISITE_FAILED,
        )

    @property
    def is_waived(self) -> bool:
        return self is Coverage.NOT_CHECKED_WAIVED


_META: dict[Coverage, StateMeta] = {
    Coverage.CHECKED: StateMeta(
        owner=Owner.NOBODY,
        permanence=Permanence.SETTLED,
        remediation="none - a determination was made; see the verdict",
    ),
    Coverage.NOT_CHECKED_DATA_DEGENERATE: StateMeta(
        owner=Owner.DATA,
        permanence=Permanence.MUTABLE,
        remediation="the signal is present and unusable; accept the gap or "
                    "supply data that carries scale",
    ),
    Coverage.NOT_CHECKED_CHECKER_FAILED: StateMeta(
        owner=Owner.TOOLING,
        permanence=Permanence.MUTABLE,
        remediation="the checker raised, timed out or lacked a dependency; "
                    "fix the tooling and re-run",
    ),
    Coverage.NOT_CHECKED_WAIVED: StateMeta(
        owner=Owner.WAIVER_HOLDER,
        permanence=Permanence.MUTABLE,
        remediation="in scope and deliberately not evaluated; a named person "
                    "accepted the gap - revisit when the waiver expires",
    ),
    Coverage.NOT_CHECKED_PREREQUISITE_FAILED: StateMeta(
        owner=Owner.UPSTREAM,
        permanence=Permanence.MUTABLE,
        remediation="a target this check depends on failed first; fix that one, "
                    "then this becomes judgeable",
    ),
    Coverage.OUT_OF_SCOPE_CALLER: StateMeta(
        owner=Owner.CALLER,
        permanence=Permanence.MUTABLE,
        remediation="not requested; pass the flag or select the check",
    ),
    Coverage.OUT_OF_SCOPE_DATA_TRANSIENT: StateMeta(
        owner=Owner.DEPLOYMENT,
        permanence=Permanence.MUTABLE,
        remediation="does not apply to this deployment; revisit when the "
                    "deployment changes",
    ),
    Coverage.OUT_OF_SCOPE_DATA_PERMANENT: StateMeta(
        owner=Owner.NOBODY,
        permanence=Permanence.SETTLED,
        remediation="no artifact of this kind can ever evidence it; excluded "
                    "by design, not pending",
    ),
}

assert set(_META) == set(Coverage), "every state needs an owner and a remediation"
