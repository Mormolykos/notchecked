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
    ReportError,
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
    r = Report(tool="trainproof doctor", vocabulary=vocab(),
               failing_verdicts=frozenset({"FAIL"}))
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
    r = Report(tool="landing-zone-audit", vocabulary=vocab(),
               failing_verdicts=frozenset({"NON_COMPLIANT"}))
    for i in range(2):
        r.add(Record(f"AC-{i}", Coverage.CHECKED, verdict="COMPLIANT"))
    for i in range(8):
        r.add(Record(f"PR-{i}", Coverage.OUT_OF_SCOPE_DATA_PERMANENT,
                     reason="no_signal", permanent_wrt="terraform-plan"))

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
    r.add(Record("AT-2", Coverage.OUT_OF_SCOPE_DATA_PERMANENT, reason="no_signal",
                 permanent_wrt="terraform-plan"))

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
    r = Report(tool="anything", vocabulary=vocab(),
               failing_verdicts=frozenset({"FAIL"}))
    assert r.total == 0 and r.coverage_ratio is None
    r.add(Record("a", Coverage.CHECKED, verdict="PASS"))
    assert r.total == 1 and r.coverage_ratio == 1.0
    r.add(Record("b", Coverage.NOT_CHECKED_CHECKER_FAILED, reason="checker_raised"))
    assert r.total == 2 and r.coverage_ratio == 0.5


def test_a_report_that_judged_nothing_never_exits_zero():
    """FOUND BY AUDIT. The first draft returned EXIT_OK here, and a test
    asserted that as correct: declare every target out of scope and the report
    reads as green. That is this library's own thesis error, one level up.
    Excluding a target is a claim; a tool that excludes everything has made no
    measurement."""
    r = Report(tool="cheat", vocabulary=vocab(),
               failing_verdicts=frozenset({"FAIL"}))
    for i in range(100):
        r.add(Record(f"control-{i}", Coverage.OUT_OF_SCOPE_CALLER,
                     reason="not_requested"))
    assert r.coverage_ratio is None
    assert r.excluded_ratio == 1.0
    assert r.exit_code == EXIT_COVERAGE_INCOMPLETE


def test_incomplete_coverage_never_exits_zero():
    r = Report(tool="anything", vocabulary=vocab(),
               failing_verdicts=frozenset({"FAIL"}))
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
    r = Report(tool="anything", vocabulary=vocab(), context={"corpus": "v1"},
               failing_verdicts=frozenset({"FAIL"}))
    r.add(Record("a", Coverage.CHECKED, verdict="PASS", evidence=("p1", "p2")))
    r.add(Record("b", Coverage.OUT_OF_SCOPE_CALLER, reason="not_requested"))
    payload = json.loads(r.to_json())

    assert payload["schema"] == "notchecked/1"
    assert payload["counts"]["evaluable"] == 1
    assert payload["counts"]["checked"] == 1
    assert payload["counts"]["excluded"] == 1
    assert payload["records"][1]["owner"] == Owner.CALLER.value
    assert payload["records"][1]["permanence"] == "mutable"


# -- Found by auditing this library, before it was published -------------------
#
# Five attacks landed on the first draft. Two of them were this library
# committing its own thesis error one level up. Each is now a regression test.

def test_a_target_that_never_arrived_is_detected():
    """FOUND BY AUDIT. The discovery-loop failure in domain 2 is the reason this
    library exists, and the first draft did not prevent it: a target that never
    became a record was invisible, and the report claimed perfect coverage.
    A report cannot notice a row nobody wrote, so the caller declares the target
    set and the report says what never arrived."""
    r = Report(tool="doctor", vocabulary=vocab(),
               failing_verdicts=frozenset({"FAIL"}),
               expected={"logs/a.jsonl", "logs/b.jsonl"})
    r.add(Record("logs/a.jsonl", Coverage.CHECKED, verdict="PASS"))
    # logs/b.jsonl raised during discovery and was swallowed.

    assert r.missing() == ["logs/b.jsonl"]
    assert r.evaluable == 2, "an absent row cannot be out of scope"
    assert r.coverage_ratio == 0.5
    assert r.exit_code == EXIT_COVERAGE_INCOMPLETE


def test_without_an_expected_set_the_report_says_so():
    """Silence about missing targets is not evidence there are none."""
    r = Report(tool="doctor", vocabulary=vocab(),
               failing_verdicts=frozenset({"FAIL"}))
    r.add(Record("logs/a.jsonl", Coverage.CHECKED, verdict="PASS"))
    assert r.expected_declared is False
    assert "never arrived cannot be detected" in r.render()


def test_one_target_cannot_hold_two_states():
    """FOUND BY AUDIT. Two records for one target were counted twice in
    silence, so `checked` and `total` described different target sets."""
    r = Report(tool="dupe", vocabulary=vocab(),
               failing_verdicts=frozenset({"FAIL"}))
    r.add(Record("x", Coverage.CHECKED, verdict="PASS"))
    with pytest.raises(ReportError, match="already has a record"):
        r.add(Record("x", Coverage.OUT_OF_SCOPE_CALLER, reason="not_requested"))


def test_a_verdict_vocabulary_must_be_declared():
    """FOUND BY AUDIT. `failing_verdicts` defaulted to {"FAIL"}, so a compliance
    tool emitting NON_COMPLIANT exited 0 on real failures. There is no safe
    default for another domain's vocabulary, so there is no default."""
    r = Report(tool="compliance", vocabulary=vocab())
    r.add(Record("AC-1", Coverage.CHECKED, verdict="NON_COMPLIANT"))
    with pytest.raises(ReportError, match="failing_verdicts was never declared"):
        r.exit_code


def test_a_record_cannot_be_mutated_after_the_check_returned():
    """FOUND BY AUDIT. `frozen=True` protects the binding, not the dict behind
    it, so a record could change after the check that wrote it had returned."""
    rec = Record("x", Coverage.CHECKED, verdict="PASS", extra={"a": 1})
    with pytest.raises(TypeError):
        rec.extra["a"] = 999          # type: ignore[index]
    assert rec.extra["a"] == 1


# -- Found by the taxonomy attack: 24 cases, 5 fit no state at all -------------

def test_a_waiver_is_not_out_of_scope():
    """FOUND BY AUDIT. A waived control IS in scope, IS applicable, and was
    deliberately not evaluated by a named person. Filing it under
    OUT_OF_SCOPE/CALLER says 'not requested', which is false and removes it from
    the denominator -- exactly where an accepted risk goes to disappear."""
    r = Report(tool="audit", vocabulary=Vocabulary([
        Reason("accepted_risk", Coverage.NOT_CHECKED_WAIVED, "signed waiver on file")]),
        failing_verdicts=frozenset({"NON_COMPLIANT"}))
    r.add(Record("AC-7", Coverage.NOT_CHECKED_WAIVED, reason="accepted_risk",
                 waived_by="ciso@example.com", waiver_expires="2026-12-31"))

    assert r.evaluable == 1, "a waiver does not shrink the denominator"
    assert r.excluded == 0
    assert r.waived == 1
    assert r.by_owner() == {Owner.WAIVER_HOLDER.value: 1}


def test_an_unowned_waiver_is_refused():
    """A waiver with no name on it is a silence with paperwork."""
    with pytest.raises(ValueError, match="requires waived_by"):
        Record("AC-7", Coverage.NOT_CHECKED_WAIVED, reason="accepted_risk")


def test_waiving_everything_does_not_produce_green():
    """The attack that closed OUT_OF_SCOPE returns in a new costume if a waiver
    is treated as a resolved gap. It is not: a named person accepting a risk is
    auditable, but it is still nothing measured."""
    r = Report(tool="audit", vocabulary=Vocabulary([
        Reason("accepted_risk", Coverage.NOT_CHECKED_WAIVED, "signed waiver")]),
        failing_verdicts=frozenset({"NON_COMPLIANT"}))
    for i in range(50):
        r.add(Record(f"AC-{i}", Coverage.NOT_CHECKED_WAIVED,
                     reason="accepted_risk", waived_by="ciso@example.com"))
    assert r.checked == 0
    assert r.coverage_ratio == 0.0
    assert r.exit_code == EXIT_COVERAGE_INCOMPLETE


def test_a_cascade_does_not_blame_the_tooling():
    """FOUND BY AUDIT. grad-spike skipped because the parse check feeding it
    failed. The checker did not fail, the data is not degenerate, the caller did
    ask. Filing it as CHECKER_FAILED sends someone to debug a working parser."""
    r = Report(tool="trainproof", vocabulary=Vocabulary([
        Reason("upstream_failed", Coverage.NOT_CHECKED_PREREQUISITE_FAILED,
               "a target this check depends on failed first")]),
        failing_verdicts=frozenset({"FAIL"}))
    r.add(Record("grad-spike", Coverage.NOT_CHECKED_PREREQUISITE_FAILED,
                 reason="upstream_failed", blocked_by="log-parse"))

    rec = r.records[0]
    assert rec.coverage.meta.owner is Owner.UPSTREAM
    assert rec.to_dict()["blocked_by"] == "log-parse"
    assert r.evaluable == 1, "the target was in scope; it just never got its turn"


def test_a_cascade_must_name_what_blocked_it():
    with pytest.raises(ValueError, match="requires blocked_by"):
        Record("grad-spike", Coverage.NOT_CHECKED_PREREQUISITE_FAILED,
               reason="upstream_failed")


def test_unreachable_is_not_unhealthy():
    """TIE-BREAK RULE, from the attack. A health check that could not reach the
    service has made no observation. Reporting that as a failing verdict is this
    library's own error in a different costume: absence of evidence rendered as
    a result."""
    r = Report(tool="prod-health", vocabulary=Vocabulary([
        Reason("unreachable", Coverage.NOT_CHECKED_CHECKER_FAILED,
               "the checker could not observe the target")]),
        failing_verdicts=frozenset({"UNHEALTHY"}))
    r.add(Record("api.example.com", Coverage.NOT_CHECKED_CHECKER_FAILED,
                 reason="unreachable"))

    assert r.failures() == [], "no observation was made, so nothing failed"
    assert r.exit_code == EXIT_COVERAGE_INCOMPLETE
    assert r.by_owner() == {Owner.TOOLING.value: 1}


def test_every_state_still_has_a_distinct_owner_story():
    """Two states may share an owner only if they share a remediation. The
    moment they do not, one of them is misfiled."""
    seen: dict[tuple, Coverage] = {}
    for state in Coverage:
        key = (state.meta.owner, state.meta.remediation)
        assert key not in seen, f"{state} duplicates {seen[key]}"
        seen[key] = state
