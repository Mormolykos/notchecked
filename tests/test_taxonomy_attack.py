"""The taxonomy attack, written down so it can be re-run.

WHY THIS FILE EXISTS, STATED HONESTLY
-------------------------------------
An attack of 24 cases was run before the first public commit. Its OUTCOME was
recorded — twelve fit exactly one state, five fit none, four fit two, three
exposed limitations — and it produced two states, WAIVED and PREREQUISITE_FAILED.
**The case list itself was never written down.** So when the schema changed on
2026-08-24 it could not be re-run: reconstructing the cases from memory and
calling the result evidence would be the precise failure this library is about,
committed by its own author.

This file is the fix, and it is a NEW attack rather than a recovery of the old
one. No claim is made that these are the original 24. What matters is that from
here a schema change is attacked reproducibly instead of from recollection.

HOW TO USE IT
-------------
Adding a state, removing one, or changing what a state requires: run this first.
A case that stops landing anywhere is the signal. Do not delete a case to make
the suite green — move it to FITS_NO_STATE with a note, because a documented hole
is a finding and a deleted case is a hole nobody can see.
"""

from __future__ import annotations

import pytest

from notchecked import Coverage, Owner, Permanence, Record, Report

# Every case: (id, domain, situation, state, required kwargs)
# The kwargs exist because three states refuse to be constructed without a
# pointer — blocked_by, waived_by, permanent_wrt. That refusal is under attack
# here too: if a state stops demanding its pointer, these cases still pass and
# the guard has silently gone.
CASES = [
    # -- ML training runs -----------------------------------------------------
    ("ml-01", "ml", ("grad-norm spike check on a log whose every grad norm is 0.0 "
     "because clipping is off — the signal is present and carries no scale"),
     Coverage.NOT_CHECKED_DATA_DEGENERATE, {}),
    ("ml-02", "ml", "loss-shape check on a run that trained normally",
     Coverage.CHECKED, {"verdict": "PASS"}),
    ("ml-03", "ml", "the log parser raised a UnicodeDecodeError partway through",
     Coverage.NOT_CHECKED_CHECKER_FAILED, {}),
    ("ml-04", "ml", ("a tfevents-only check run against a CSV log — this format "
     "never carries the field and never will"),
     Coverage.OUT_OF_SCOPE_DATA_PERMANENT, {"permanent_wrt": "csv-log"}),
    ("ml-05", "ml", "an eval-set check the caller did not select",
     Coverage.OUT_OF_SCOPE_CALLER, {}),
    ("ml-06", "ml", ("checkpoint-vs-best-step comparison skipped because the "
     "checkpoint index itself failed to parse first"),
     Coverage.NOT_CHECKED_PREREQUISITE_FAILED, {"blocked_by": "checkpoint-index"}),

    # -- Infrastructure compliance -------------------------------------------
    ("cmp-01", "compliance", "a control evidenced by the terraform plan, evaluated, compliant",
     Coverage.CHECKED, {"verdict": "COMPLIANT"}),
    ("cmp-02", "compliance", ("a Kubernetes control against a plan with no Kubernetes — "
     "becomes checkable the moment the deployment adds it"),
     Coverage.OUT_OF_SCOPE_DATA_TRANSIENT, {}),
    ("cmp-03", "compliance", ("a control about staff background checks — no generated "
     "artifact of any kind can evidence a human process"),
     Coverage.OUT_OF_SCOPE_DATA_PERMANENT, {"permanent_wrt": "terraform-plan"}),
    ("cmp-04", "compliance", ("an applicable control a named risk owner accepted "
     "rather than evaluating, with an expiry"),
     Coverage.NOT_CHECKED_WAIVED,
     {"waived_by": "risk-owner@example.com", "waiver_expires": "2026-12-31"}),
    ("cmp-05", "compliance", "the policy engine timed out against a very large plan",
     Coverage.NOT_CHECKED_CHECKER_FAILED, {}),
    ("cmp-06", "compliance", ("a control whose evidence field is present but empty "
     "in every resource — present and unusable"),
     Coverage.NOT_CHECKED_DATA_DEGENERATE, {}),

    # -- Retrieval / RAG evaluation ------------------------------------------
    ("rag-01", "rag", "a question the model answered and the grader scored",
     Coverage.CHECKED, {"verdict": "PASS"}),
    ("rag-02", "rag", ("the model refused; there is no assertion to grade, and "
     "scoring the refusal against the gold phrase is how ten refusals were "
     "counted correct"),
     Coverage.NOT_CHECKED_DATA_DEGENERATE, {}),
    ("rag-03", "rag", ("a citation check on a corpus with no URLs at all — this "
     "corpus kind cannot carry them"),
     Coverage.OUT_OF_SCOPE_DATA_PERMANENT, {"permanent_wrt": "plaintext-corpus"}),
    ("rag-04", "rag", ("an answer-quality check skipped because retrieval returned "
     "nothing to answer from"),
     Coverage.NOT_CHECKED_PREREQUISITE_FAILED, {"blocked_by": "retrieval"}),
    ("rag-05", "rag", ("an adversarial injection case the caller filtered out of "
     "this run with a category flag"),
     Coverage.OUT_OF_SCOPE_CALLER, {}),

    # -- CI/CD ----------------------------------------------------------------
    ("ci-01", "cicd", "unit tests ran and passed",
     Coverage.CHECKED, {"verdict": "PASS"}),
    ("ci-02", "cicd", ("integration tests skipped because the build job they "
     "depend on failed"),
     Coverage.NOT_CHECKED_PREREQUISITE_FAILED, {"blocked_by": "build"}),
    ("ci-03", "cicd", ("a Windows matrix leg on a repository that ships a Linux-only "
     "binary — no Windows artifact will ever exist to test"),
     Coverage.OUT_OF_SCOPE_DATA_PERMANENT, {"permanent_wrt": "linux-only-wheel"}),
    ("ci-04", "cicd", "a flaky external service made the smoke test error, not fail",
     Coverage.NOT_CHECKED_CHECKER_FAILED, {}),
    ("ci-05", "cicd", "a security scan a release manager waived to ship a hotfix",
     Coverage.NOT_CHECKED_WAIVED, {"waived_by": "release-manager"}),

    # -- Production monitoring ------------------------------------------------
    ("mon-01", "monitoring", "p99 latency SLO evaluated over a full window",
     Coverage.CHECKED, {"verdict": "PASS"}),
    ("mon-02", "monitoring", ("an error-rate SLO over a window with zero requests — "
     "a ratio with an empty denominator is not a rate of zero"),
     Coverage.NOT_CHECKED_DATA_DEGENERATE, {}),
    ("mon-03", "monitoring", ("a GPU-saturation alert on a CPU-only deployment, "
     "which changes if the deployment gets a GPU"),
     Coverage.OUT_OF_SCOPE_DATA_TRANSIENT, {}),
    ("mon-04", "monitoring", "the metrics scrape failed for the whole interval",
     Coverage.NOT_CHECKED_CHECKER_FAILED, {}),
]


# Cases that fit NO state. Kept deliberately: a documented hole is a finding, a
# deleted case is a hole nobody can see. If a future state absorbs one of these,
# move it up to CASES rather than dropping it.
FITS_NO_STATE = [
    ("hole-01", ("the check ran, the evidence conflicts, and the tool has no way "
     "to prefer one source. Resolved as a VERDICT, not a coverage gap — a "
     "determination that the evidence disagrees IS a determination.")),
    ("hole-02", ("a check that partially completed: 900 of 1000 resources scanned "
     "before a timeout. Neither CHECKED nor NOT_CHECKED is honest for the target "
     "as a whole. Currently the caller must split it into two targets.")),
    ("hole-03", ("a target that is in scope, evaluable, and simply never got "
     "scheduled — no waiver, no prerequisite, nobody decided. Caught by "
     "`expected` + `missing()` rather than by a state, on purpose: a row nobody "
     "wrote cannot carry a state.")),
]


@pytest.mark.parametrize("case_id,domain,situation,state,kwargs", CASES,
                         ids=[c[0] for c in CASES])
def test_every_case_lands_in_exactly_one_state(case_id, domain, situation, state, kwargs):
    """Each realistic situation constructs, and lands where the taxonomy says."""
    reason = None if state.is_checked else f"{case_id}_reason"
    record = Record(target=case_id, coverage=state, reason=reason,
                    detail=situation, **kwargs)
    assert record.coverage is state
    assert record.coverage.meta.owner in set(Owner)
    assert record.coverage.meta.permanence in set(Permanence)
    # A gap never carries a verdict; a determination always does or may.
    if not state.is_checked:
        assert record.verdict is None


def test_the_attack_covers_every_state():
    """A state no case exercises is a state nobody has attacked."""
    exercised = {state for _, _, _, state, _ in CASES}
    missing = set(Coverage) - exercised
    assert not missing, f"no attack case reaches {sorted(s.value for s in missing)}"


def test_the_attack_covers_every_domain_it_claims_to():
    domains = {d for _, d, _, _, _ in CASES}
    assert domains == {"ml", "compliance", "rag", "cicd", "monitoring"}


def test_every_state_that_demands_a_pointer_still_demands_it():
    """The guard under attack, not just the states.

    If a required pointer quietly became optional, the cases above would still
    pass — they supply it. These assert the refusal itself."""
    with pytest.raises(ValueError, match="blocked_by"):
        Record("x", Coverage.NOT_CHECKED_PREREQUISITE_FAILED, reason="r")
    with pytest.raises(ValueError, match="waived_by"):
        Record("x", Coverage.NOT_CHECKED_WAIVED, reason="r")
    with pytest.raises(ValueError, match="permanent_wrt"):
        Record("x", Coverage.OUT_OF_SCOPE_DATA_PERMANENT, reason="r")


def test_the_whole_attack_survives_one_report():
    """All cases in a single report: the counts must stay coherent."""
    r = Report(tool="attack", failing_verdicts=frozenset({"FAIL", "NON_COMPLIANT"}))
    for case_id, _, situation, state, kwargs in CASES:
        reason = None if state.is_checked else f"{case_id}_reason"
        r.add(Record(target=case_id, coverage=state, reason=reason,
                     detail=situation, **kwargs))

    checked = sum(1 for c in CASES if c[3].is_checked)
    out_of_scope = sum(1 for c in CASES
                       if not c[3].counts_toward_denominator)
    assert r.total == len(CASES)
    assert r.checked == checked
    assert r.excluded == out_of_scope
    assert r.evaluable == len(CASES) - out_of_scope
    assert r.checked < r.evaluable, "gaps exist; this must not read as complete"
    assert r.exit_code != 0, "incomplete coverage never exits zero"
    # Every gap names an owner somebody can act on, or nobody.
    assert set(r.by_owner()) <= {o.value for o in Owner}


def test_documented_holes_are_still_documented():
    """Guards the notes, so a hole cannot quietly vanish from the record."""
    assert len(FITS_NO_STATE) == 3
    assert all(len(note) > 80 for _, note in FITS_NO_STATE)
