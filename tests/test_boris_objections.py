"""The three objections Boris Teplitsky raised from the compliance side, as tests.

They are kept in their own file because they are not a feature. They are the
places where the taxonomy was wrong about its own scope, and each one was found
by someone applying it to a domain its author has never worked in.

1. THE UNIT IS NOT GIVEN. In a linter a row is a check somebody wrote, so the
   unit exists before the schema. In compliance a framework is prose and turning
   it into checkable requirements is a judgment call. The taxonomy starts after
   that mapping and must say so, or it reads as if rows arrive by themselves.
   Scope statements are not testable, so that one lives in the docstrings; what
   IS testable is the mechanism it implies, which is objection 3.

2. PERMANENCE IS RELATIVE TO A TARGET. "Nobody, never" is not a property of a
   control. It is a property of pairing that control with a kind of artifact.

3. ROWS FOR THE CHECKABLE SUBSET, A COUNT FOR THE REST. A framework document is
   hundreds of pages of which a few paragraphs concern anything an artifact can
   evidence. One row each makes the report mostly noise.
"""

import pytest

from notchecked import Coverage, Exclusion, Record, Report, ReportError

# -- Objection 2: permanence is relative --------------------------------------

def test_permanent_exclusion_must_name_what_it_is_permanent_against():
    """Unqualified 'never' is the bug: two reports on the same framework can
    disagree and both be correct."""
    with pytest.raises(ValueError, match="permanent_wrt"):
        Record("AT-2", Coverage.OUT_OF_SCOPE_DATA_PERMANENT, reason="no_signal")


def test_the_same_control_is_permanent_against_one_target_and_a_row_in_another():
    """The concrete case Boris gave: a Kubernetes control is permanently out of
    scope only while the target has no Kubernetes."""
    plan = Report(tool="audit", failing_verdicts=frozenset({"NON_COMPLIANT"}))
    plan.add(Record("CM-6-k8s", Coverage.OUT_OF_SCOPE_DATA_PERMANENT,
                    reason="no_signal", permanent_wrt="terraform-plan"))

    cluster = Report(tool="audit", failing_verdicts=frozenset({"NON_COMPLIANT"}))
    cluster.add(Record("CM-6-k8s", Coverage.CHECKED, verdict="COMPLIANT"))

    assert plan.excluded == 1 and plan.evaluable == 0
    assert cluster.evaluable == 1 and cluster.checked == 1
    # Both reports are correct. The reference target is what reconciles them,
    # and it is on the record rather than in someone's head.
    assert plan.records[0].to_dict()["permanent_wrt"] == "terraform-plan"


def test_permanence_reference_is_refused_where_it_would_be_a_lie():
    """A mutable state cannot be permanent with respect to anything."""
    with pytest.raises(ValueError, match="only means something"):
        Record("AC-1", Coverage.OUT_OF_SCOPE_DATA_TRANSIENT,
               reason="service_unused", permanent_wrt="terraform-plan")


# -- Objection 3: rows for the checkable subset, a count for the rest ----------

def test_bulk_exclusion_keeps_the_report_readable_without_hiding_the_count():
    """412 paragraphs no artifact can evidence become one counted rule, not 412
    rows -- and the count still lands in `total`."""
    r = Report(tool="landing-zone-audit", failing_verdicts=frozenset({"NON_COMPLIANT"}))
    for i in range(3):
        r.add(Record(f"AC-{i}", Coverage.CHECKED, verdict="COMPLIANT"))
    r.exclude(rule="no-artifact-evidence", count=412,
              permanent_wrt="terraform-plan",
              describes="framework prose no generated artifact can evidence")

    assert len(r.records) == 3, "the excluded 412 never became rows"
    assert r.total == 415, "but they are still counted as considered"
    assert r.evaluable == 3
    assert r.checked == 3
    assert r.coverage_ratio == 1.0, "3 of 3 checkable controls were checked"
    assert r.excluded == 412
    assert round(r.excluded_ratio, 4) == round(412 / 415, 4)


def test_a_bulk_exclusion_cannot_flatter_the_exclusion_ratio_by_vanishing():
    """The failure this guards: if bulk exclusions were left out of `total`,
    excluding 412 of 415 would report an exclusion ratio of 0%."""
    r = Report(tool="audit", failing_verdicts=frozenset({"NON_COMPLIANT"}))
    r.add(Record("AC-0", Coverage.CHECKED, verdict="COMPLIANT"))
    r.exclude(rule="no-artifact-evidence", count=99,
              permanent_wrt="terraform-plan")
    assert r.excluded_ratio > 0.98, (
        "an exclusion that does not reach the denominator is a coverage number "
        "hiding in its own scope decision")


def test_an_exclusion_without_a_named_rule_is_refused():
    """An unattributed count is the same silence, moved from the row to the
    corpus."""
    with pytest.raises(ReportError, match="named rule"):
        Exclusion(rule="", count=10, permanent_wrt="terraform-plan")


def test_an_exclusion_must_state_its_reference_target():
    with pytest.raises(ReportError, match="permanent_wrt"):
        Exclusion(rule="no-artifact-evidence", count=10, permanent_wrt="")


def test_a_negative_exclusion_count_is_refused():
    with pytest.raises(ReportError, match="negative"):
        Exclusion(rule="r", count=-1, permanent_wrt="terraform-plan")


def test_two_counts_under_one_rule_name_are_refused():
    """Merged silently, nobody can tell afterwards which rule excluded what."""
    r = Report(tool="audit")
    r.exclude(rule="no-artifact-evidence", count=10, permanent_wrt="terraform-plan")
    with pytest.raises(ReportError, match="already recorded"):
        r.exclude(rule="no-artifact-evidence", count=5, permanent_wrt="terraform-plan")


def test_bulk_exclusions_survive_into_both_outputs():
    """A count a reader cannot see is not a disclosure."""
    r = Report(tool="audit", failing_verdicts=frozenset({"NON_COMPLIANT"}))
    r.add(Record("AC-0", Coverage.CHECKED, verdict="COMPLIANT"))
    r.exclude(rule="no-artifact-evidence", count=412,
              permanent_wrt="terraform-plan", describes="prose, not configuration")

    d = r.to_dict()
    assert d["counts"]["bulk_excluded"] == 412
    assert d["exclusions"] == [{
        "rule": "no-artifact-evidence",
        "count": 412,
        "permanent_wrt": "terraform-plan",
        "describes": "prose, not configuration",
    }]

    text = r.render()
    assert "412" in text and "no-artifact-evidence" in text
    assert "terraform-plan" in text


def test_a_near_total_exclusion_never_renders_as_total():
    """Found by running the README example against the new bulk path.

    413 of 415 excluded printed as '100% of all targets' while one target had
    been checked — the reader concludes nothing was measured. That is this
    library's own failure mode, committed by its own reporter."""
    r = Report(tool="trainproof", failing_verdicts=frozenset({"FAIL"}))
    r.add(Record("loss-shape", Coverage.CHECKED, verdict="PASS"))
    r.exclude(rule="no-artifact-evidence", count=412,
              permanent_wrt="terraform-plan")

    text = r.render()
    assert "100%" not in text, "something was checked; 100% excluded is a lie"
    assert "99%" in text


def test_a_total_exclusion_does_render_as_total():
    """The other direction: when nothing was checked, say so at full strength."""
    r = Report(tool="trainproof", failing_verdicts=frozenset({"FAIL"}))
    r.exclude(rule="no-artifact-evidence", count=412,
              permanent_wrt="terraform-plan")
    assert "100%" in r.render()


def test_a_single_exclusion_in_a_large_run_never_renders_as_zero():
    """The mirror failure: 1 excluded of 400 floors to 0%, which reads as none."""
    r = Report(tool="trainproof", failing_verdicts=frozenset({"FAIL"}))
    for i in range(399):
        r.add(Record(f"t{i}", Coverage.CHECKED, verdict="PASS"))
    r.add(Record("t-out", Coverage.OUT_OF_SCOPE_DATA_PERMANENT,
                 reason="no_signal", permanent_wrt="jsonl-log"))
    text = r.render()
    assert "0%" not in text, "one target was excluded; 0% reads as none"
    assert "1 out of scope (1% of all targets)" in text


def test_excluding_everything_in_bulk_still_never_exits_zero():
    """The original audit finding, re-checked through the new path: a report
    that judged nothing must not read as green."""
    r = Report(tool="audit", failing_verdicts=frozenset({"NON_COMPLIANT"}))
    r.exclude(rule="no-artifact-evidence", count=500,
              permanent_wrt="terraform-plan")
    assert r.checked == 0
    assert r.exit_code != 0, "no measurement was made; that is not a pass"
