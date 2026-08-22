"""Regression tests written from four real failures, in four unrelated domains.

These are not illustrative examples. Each one happened, in a shipped tool, and
each was found by a real input rather than by a test. They are the reason the
six states exist, so they are the tests that guard them.
"""

from __future__ import annotations

import pytest

from notchecked import (
    EXIT_COVERAGE_INCOMPLETE,
    EXIT_OK,
    EXIT_VERDICT_FAILED,
    Coverage,
    Owner,
    Reason,
    Record,
    Report,
    Vocabulary,
    VocabularyError,
)


def vocab() -> Vocabulary:
    return Vocabulary([
        Reason("no_scale", Coverage.NOT_CHECKED_DATA_DEGENERATE,
               "median gradient norm is zero - no scale to measure a spike against"),
        Reason("no_signal", Coverage.OUT_OF_SCOPE_DATA_PERMANENT,
               "this log format never carries the column"),
        Reason("not_requested", Coverage.OUT_OF_SCOPE_CALLER,
               "the caller did not ask for this check"),
        Reason("checker_raised", Coverage.NOT_CHECKED_CHECKER_FAILED,
               "the checker raised while reading the target"),
        Reason("service_unused", Coverage.OUT_OF_SCOPE_DATA_TRANSIENT,
               "this deployment does not use the service the control governs"),
    ])


# -- Domain 1: ML training logs ------------------------------------------------

def test_skipped_checks_cannot_be_reported_as_having_run():
    """A run whose loss was exactly 0.0 on every step returned PASS, because
    every loss-shape check was guarded against dividing by zero and skipped
    silently -- and the report then listed those checks as having run."""
    r = Report(tool="trainproof", vocabulary=vocab())
    r.add(Record("zero-loss", Coverage.NOT_CHECKED_DATA_DEGENERATE, reason="no_scale"))
    r.add(Record("flat-loss", Coverage.NOT_CHECKED_DATA_DEGENERATE, reason="no_scale"))
    r.add(Record("divergence", Coverage.NOT_CHECKED_DATA_DEGENERATE, reason="no_scale"))

    assert r.checked == 0
    assert r.evaluable == 3
    assert r.coverage_ratio == 0.0
    # The whole point: nothing here may return success.
    assert r.exit_code == EXIT_COVERAGE_INCOMPLETE


def test_a_checked_record_cannot_also_claim_it_was_skipped():
    with pytest.raises(ValueError, match="carry no reason"):
        Record("loss-shape", Coverage.CHECKED, reason="no_scale", verdict="PASS")


def test_a_gap_cannot_carry_a_verdict():
    """No determination was made, so there is no determination to report."""
    with pytest.raises(ValueError, match="cannot carry a verdict"):
        Record("grad-spike", Coverage.NOT_CHECKED_DATA_DEGENERATE,
               reason="no_scale", verdict="PASS")


def test_an_unexplained_gap_is_refused():
    with pytest.raises(ValueError, match="requires a reason"):
        Record("grad-spike", Coverage.NOT_CHECKED_DATA_DEGENERATE)


# -- Domain 2: the discovery loop that swallowed files -------------------------

def test_a_target_that_raised_while_being_found_is_still_a_row():
    """`except Exception: pass` in a discovery walk meant a file that raised
    while being *found* never became a candidate and never appeared in the
    report -- visible on disk, absent from the output, indistinguishable from a
    file that passed. It must appear, owned by the tooling."""
    r = Report(tool="trainproof doctor", vocabulary=vocab())
    r.add(Record("logs/run_a.jsonl", Coverage.CHECKED, verdict="PASS"))
    r.add(Record("logs/run_b.jsonl", Coverage.NOT_CHECKED_CHECKER_FAILED,
                 reason="checker_raised", detail="UnicodeDecodeError at byte 4096"))

    assert r.total == 2, "a swallowed target is still a target"
    assert r.by_owner() == {Owner.TOOLING.value: 1}
    assert r.exit_code == EXIT_COVERAGE_INCOMPLETE


def test_degenerate_data_and_a_broken_checker_are_different_to_dos():
    """Both are 'I could not judge this'. One says accept the gap, the other
    says fix your parser, and only one of them will ever change on its own."""
    a = Coverage.NOT_CHECKED_DATA_DEGENERATE
    b = Coverage.NOT_CHECKED_CHECKER_FAILED
    assert a is not b
    assert a.meta.owner is not b.meta.owner
    assert a.meta.remediation != b.meta.remediation


# -- Domain 3: infrastructure compliance --------------------------------------

def test_the_denominator_is_the_checkable_subset_not_the_framework():
    """A framework document is mostly prose no artifact can satisfy. Reporting
    against the framework name makes the never-in-scope majority vanish and the
    remainder look like full coverage."""
    r = Report(tool="landing-zone-audit", vocabulary=vocab())
    for i in range(2):
        r.add(Record(f"AC-{i}", Coverage.CHECKED, verdict="COMPLIANT"))
    for i in range(8):
        r.add(Record(f"PR-{i}", Coverage.OUT_OF_SCOPE_DATA_PERMANENT,
                     reason="no_signal"))

    assert r.total == 10
    assert r.evaluable == 2
    assert r.excluded == 8
    assert r.coverage_ratio == 1.0, "2 of 2 checkable controls were checked"
    # 2/10 would be a claim about the framework; 2/2 is a claim about the evidence.
    assert r.exit_code == EXIT_OK


def test_permanent_and_transient_exclusions_do_not_share_a_bucket():
    """A control excluded because the deployment does not use that service
    changes the moment the deployment changes. One excluded because nothing
    generated can ever evidence it does not."""
    r = Report(tool="landing-zone-audit", vocabulary=vocab())
    r.add(Record("AC-9", Coverage.OUT_OF_SCOPE_DATA_TRANSIENT, reason="service_unused"))
    r.add(Record("AT-2", Coverage.OUT_OF_SCOPE_DATA_PERMANENT, reason="no_signal"))

    states = r.by_state()
    assert states[Coverage.OUT_OF_SCOPE_DATA_TRANSIENT] == 1
    assert states[Coverage.OUT_OF_SCOPE_DATA_PERMANENT] == 1
    assert r.by_owner() == {Owner.DEPLOYMENT.value: 1, Owner.NOBODY.value: 1}


# -- Domain 4: retrieval-grounded answering ------------------------------------

def test_a_refusal_is_neither_correct_nor_incorrect():
    """An evaluation harness scored ten model refusals as *correct*, because the
    expected phrase appeared inside the sentence explaining what could not be
    determined -- and separately logged refusals under a failure type asserting
    an answer the model never gave. A refusal is a coverage state, not a
    verdict."""
    r = Report(tool="rag-eval", vocabulary=vocab(), failing_verdicts=frozenset({"WRONG"}))
    r.add(Record("q1", Coverage.CHECKED, verdict="RIGHT"))
    r.add(Record("q2", Coverage.CHECKED, verdict="WRONG"))
    r.add(Record("q3", Coverage.NOT_CHECKED_DATA_DEGENERATE, reason="no_scale",
                 detail="model answered NOT ESTABLISHED; the passages do not "
                        "carry the relation"))

    assert r.by_verdict() == {"RIGHT": 1, "WRONG": 1}
    assert "REFUSED" not in r.by_verdict(), "a refusal never enters the verdict tally"
    assert r.checked == 2 and r.evaluable == 3
    assert r.exit_code == EXIT_VERDICT_FAILED


# -- The library's own guarantees ----------------------------------------------

def test_free_text_reasons_are_refused():
    r = Report(tool="anything", vocabulary=vocab())
    with pytest.raises(VocabularyError, match="unregistered reason code"):
        r.add(Record("x", Coverage.NOT_CHECKED_CHECKER_FAILED,
                     reason="it broke somehow"))


def test_a_code_cannot_mean_two_things():
    with pytest.raises(VocabularyError, match="already registered"):
        Vocabulary([
            Reason("gap", Coverage.NOT_CHECKED_CHECKER_FAILED, "checker died"),
            Reason("gap", Coverage.OUT_OF_SCOPE_CALLER, "not requested"),
        ])


def test_a_reason_cannot_be_emitted_under_the_wrong_state():
    r = Report(tool="anything", vocabulary=vocab())
    with pytest.raises(VocabularyError, match="registered for"):
        r.add(Record("x", Coverage.OUT_OF_SCOPE_CALLER, reason="no_scale"))


def test_counts_are_derived_not_stored():
    """The count and the rows cannot disagree, because there is no count to
    disagree with until someone reads one."""
    r = Report(tool="anything", vocabulary=vocab())
    assert r.total == 0 and r.coverage_ratio is None
    r.add(Record("a", Coverage.CHECKED, verdict="PASS"))
    assert r.total == 1 and r.coverage_ratio == 1.0
    r.add(Record("b", Coverage.NOT_CHECKED_CHECKER_FAILED, reason="checker_raised"))
    assert r.total == 2 and r.coverage_ratio == 0.5


def test_empty_denominator_is_not_zero_coverage():
    """Nothing evaluable is an absence of coverage, not a coverage of zero."""
    r = Report(tool="anything", vocabulary=vocab())
    r.add(Record("only", Coverage.OUT_OF_SCOPE_CALLER, reason="not_requested"))
    assert r.coverage_ratio is None
    assert r.exit_code == EXIT_OK, "nothing was in scope, so nothing is outstanding"


def test_incomplete_coverage_never_exits_zero():
    r = Report(tool="anything", vocabulary=vocab())
    r.add(Record("a", Coverage.CHECKED, verdict="PASS"))
    r.add(Record("b", Coverage.NOT_CHECKED_DATA_DEGENERATE, reason="no_scale"))
    assert not r.failures()
    assert r.exit_code == EXIT_COVERAGE_INCOMPLETE


def test_every_state_has_an_owner_and_a_remediation():
    for state in Coverage:
        assert state.meta.owner
        assert state.meta.remediation


def test_json_round_trips_and_states_its_coverage():
    import json
    r = Report(tool="anything", vocabulary=vocab(), context={"corpus": "v1"})
    r.add(Record("a", Coverage.CHECKED, verdict="PASS", evidence=("p1", "p2")))
    r.add(Record("b", Coverage.OUT_OF_SCOPE_CALLER, reason="not_requested"))
    payload = json.loads(r.to_json())

    assert payload["schema"] == "notchecked/1"
    assert payload["counts"]["evaluable"] == 1
    assert payload["counts"]["checked"] == 1
    assert payload["counts"]["excluded"] == 1
    assert payload["records"][1]["owner"] == Owner.CALLER.value
    assert payload["records"][1]["permanence"] == "mutable"
