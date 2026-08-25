"""The MCP server, driven the way a client drives it.

These tests exist because the fifth instance of this library's failure was not
a program. It was an AI assistant making six confident claims in one session,
each from a partial measurement, with no vocabulary for "I did not look at
that". The server is the vocabulary; these are the cases that prove it refuses
what it should refuse.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from notchecked import mcp_server as srv


def call(name: str, **args):
    """One tools/call through the real dispatcher, decoded."""
    resp = srv.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": args},
    })
    body = json.loads(resp["result"]["content"][0]["text"])
    return body, resp["result"]["isError"]


@pytest.fixture(autouse=True)
def _clean():
    srv._state.update({"report": None, "question": None,
                       "declared": [], "failing_verdicts": []})
    yield


def test_a_checked_row_without_evidence_is_refused():
    """"I checked it" is the assertion that went wrong six times in one day."""
    call("coverage_open", question="q", targets=["a"])
    body, is_error = call("coverage_checked", target="a", evidence="   ", scope="all")
    assert is_error
    assert "evidence is required" in body["error"]


def test_permanence_still_needs_its_reference_through_the_transport():
    """Boris Teplitsky's correction has to survive being spoken over MCP.

    A schema rule that only holds when called in-process is not a schema rule.
    """
    call("coverage_open", question="q", targets=["a"])
    body, is_error = call("coverage_gap", target="a",
                          state="OUT_OF_SCOPE_DATA_PERMANENT",
                          reason="nothing can ever evidence it")
    assert is_error
    assert "permanent_wrt" in body["error"]

    body, is_error = call("coverage_gap", target="a",
                          state="OUT_OF_SCOPE_DATA_PERMANENT",
                          reason="nothing can ever evidence it",
                          permanent_wrt="a static HTML page")
    assert not is_error


def test_a_verdict_without_a_declared_failing_set_is_refused():
    """The library refused the first version of this server for exactly this.

    It will not guess which words in another domain mean failure, and the
    server must surface that at the point of the mistake rather than crash on
    close, which is what it did before this test existed.
    """
    call("coverage_open", question="q", targets=["a"])
    body, is_error = call("coverage_checked", target="a", evidence="read the file",
                          scope="whole file", exhaustive=True, verdict="broken")
    assert is_error
    assert "failing_verdicts" in body["error"]

    # and it is accepted once the domain's failing words are declared
    call("coverage_open", question="q", targets=["a"], failing_verdicts=["broken"])
    body, is_error = call("coverage_checked", target="a", evidence="read the file",
                          scope="whole file", exhaustive=True, verdict="broken")
    assert not is_error


def test_a_partial_inspection_cannot_underwrite_a_claim_of_absence():
    """The correction a second model found in the first version of this server.

    Every wrong claim on 2026-08-25 was true of the fragment inspected and false
    of the whole. "I did not find five entries" became "five entries are
    missing" with nothing in between to stop it. `scope` makes the fragment
    visible; `exhaustive` is what a negative claim requires.
    """
    call("coverage_open", question="Is anything missing from the portfolio?",
         targets=["portfolio"])
    body, is_error = call("coverage_checked", target="portfolio",
                          evidence="regex over text extracted from the page",
                          scope="3,000 of 10,828 words")
    assert not is_error
    assert body["exhaustive"] is False
    assert "does NOT support a claim that something is absent" in body["note"]

    body, _ = call("coverage_finish")
    assert body["partial_inspections"] == [
        {"target": "portfolio", "scope": "3,000 of 10,828 words"}]
    assert "ABSENCE_WARNING" in body
    assert "absence of evidence found in a fragment" in body["ABSENCE_WARNING"]


def test_an_exhaustive_inspection_carries_no_absence_warning():
    call("coverage_open", question="Is anything missing?", targets=["portfolio"])
    call("coverage_checked", target="portfolio",
         evidence="read every one of the 38 <h3> from the raw HTML",
         scope="10,828 of 10,828 words", exhaustive=True)
    body, _ = call("coverage_finish")
    assert body["partial_inspections"] == []
    assert "ABSENCE_WARNING" not in body


def test_scope_is_required_and_says_why():
    call("coverage_open", question="q", targets=["a"])
    body, is_error = call("coverage_checked", target="a", evidence="read the page")
    assert is_error
    assert "scope is required" in body["error"]
    assert "10,828" in body["error"]  # the refusal carries the real example


def test_targets_never_looked_at_are_named_not_silently_dropped():
    """The whole point. Six declared, one checked, four never touched.

    This is the 2026-08-25 session replayed: the assistant read the headings and
    pronounced on the page. A denominator of 1 would have called that complete.
    """
    call("coverage_open", question="Is the portfolio complete?",
         targets=["headings", "MCP coverage", "crate count",
                  "noindex tag", "followed links", "spkproof status"])
    call("coverage_checked", target="headings", evidence="38 <h3> from raw HTML",
         scope="38 of 38 headings", exhaustive=True)
    call("coverage_gap", target="crate count",
         state="NOT_CHECKED_CHECKER_FAILED", reason="walk counted vendored manifests")

    body, _ = call("coverage_finish")
    assert body["checked"] == 1
    assert body["total"] == 6
    assert sorted(body["declared_but_never_recorded"]) == [
        "MCP coverage", "followed links", "noindex tag", "spkproof status"]
    assert "MUST state these gaps" in body["INSTRUCTION"]


def test_full_coverage_says_so_and_does_not_nag():
    """A rule that fires on a clean run teaches people to ignore it."""
    call("coverage_open", question="q", targets=["a", "b"])
    call("coverage_checked", target="a", evidence="read it", scope="all", exhaustive=True)
    call("coverage_checked", target="b", evidence="read it too", scope="all", exhaustive=True)
    body, _ = call("coverage_finish")
    assert body["checked"] == body["total"] == 2
    assert body["gaps"] == []
    assert "MUST" not in body["INSTRUCTION"]


def test_recording_before_opening_is_refused():
    body, is_error = call("coverage_checked", target="a", evidence="x", scope="all")
    assert is_error and "no open report" in body["error"]


def test_coverage_gap_cannot_smuggle_in_a_pass():
    call("coverage_open", question="q", targets=["a"])
    body, is_error = call("coverage_gap", target="a", state="CHECKED", reason="fine")
    assert is_error
    assert "coverage_checked" in body["error"]


def test_an_unknown_state_lists_the_valid_ones():
    call("coverage_open", question="q", targets=["a"])
    body, is_error = call("coverage_gap", target="a", state="PROBABLY_FINE", reason="hmm")
    assert is_error
    assert "NOT_CHECKED_DATA_DEGENERATE" in body["error"]


def test_isError_marks_a_refusal():
    """A refusal that looks like a result is this library's thesis in its own
    transport. `isError` is how a caller tells them apart."""
    call("coverage_open", question="q", targets=["a"])
    _, is_error = call("coverage_checked", target="a", evidence="", scope="all")
    assert is_error is True
    _, is_error = call("coverage_checked", target="a", evidence="read it", scope="all")
    assert is_error is False


def test_initialize_and_tools_list():
    r = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert r["result"]["serverInfo"]["name"] == "notchecked"
    r = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in r["result"]["tools"]}
    assert names == {"coverage_open", "coverage_checked", "coverage_gap",
                     "coverage_retrieval", "coverage_finish", "coverage_states"}


# --------------------------------------------------------------------------
# Retrieval: the instrument has its own coverage
# --------------------------------------------------------------------------

def test_a_tiny_slice_of_a_corpus_cannot_support_a_claim_of_absence():
    """8 chunks of 2,431 documents is 0.3%, and today that reports identically
    to an exhaustive read. 'The company has no policy about X' is not a thing
    eight retrieved chunks can establish."""
    call("coverage_open", question="Is there a remote-work policy?",
         targets=["policy corpus"])
    body, is_error = call("coverage_retrieval", target="policy corpus",
                          query="remote work reimbursement",
                          corpus_size=2431, retrieved=8, in_context=8,
                          corpus_id="policies-v17", method="hybrid")
    assert not is_error
    assert body["coverage"] == "CHECKED"
    assert body["exhaustive"] is False
    assert "0.329" in body["scope"] or "of 2431" in body["scope"]
    assert "CANNOT support" in body["ABSENCE_WARNING"]
    assert "2423 units were never looked at" in body["ABSENCE_WARNING"]


def test_retrieval_returning_nothing_is_a_retrieval_failure_not_a_gap_in_reasoning():
    """The distinction that turns 'the LLM hallucinated' into an actionable bug."""
    call("coverage_open", question="q", targets=["corpus"])
    body, _ = call("coverage_retrieval", target="corpus", query="whatever",
                   corpus_size=1000, retrieved=0)
    assert body["coverage"] == "NOT_CHECKED_CHECKER_FAILED"
    assert body["stage"] == "retrieval"
    assert "RETRIEVAL FAILURE" in body["DIAGNOSIS"]


def test_everything_dropped_at_assembly_is_a_context_failure():
    """Retrieval worked. The agent still never saw it. Two different bugs."""
    call("coverage_open", question="q", targets=["corpus"])
    body, _ = call("coverage_retrieval", target="corpus", query="q",
                   corpus_size=1000, retrieved=6, in_context=0)
    assert body["coverage"] == "NOT_CHECKED_CHECKER_FAILED"
    assert body["stage"] == "context assembly"
    assert "CONTEXT FAILURE" in body["DIAGNOSIS"]


def test_partial_truncation_is_reported_without_being_called_a_failure():
    """4 of 6 survived. The agent did answer from evidence — but if the answer
    is wrong, context assembly is where to look first."""
    call("coverage_open", question="q", targets=["corpus"])
    body, _ = call("coverage_retrieval", target="corpus", query="q",
                   corpus_size=1000, retrieved=6, in_context=4)
    assert body["coverage"] == "CHECKED"
    assert body["dropped_at_context_assembly"] == 2
    assert "check context assembly before the agent" in body["PARTIAL_CONTEXT"]


def test_full_corpus_coverage_carries_no_absence_warning():
    call("coverage_open", question="q", targets=["corpus"])
    body, _ = call("coverage_retrieval", target="corpus", query="q",
                   corpus_size=12, retrieved=12, in_context=12)
    assert body["exhaustive"] is True
    assert "ABSENCE_WARNING" not in body


def test_a_missing_denominator_is_refused():
    call("coverage_open", question="q", targets=["corpus"])
    body, is_error = call("coverage_retrieval", target="corpus", query="q",
                          corpus_size=0, retrieved=8)
    assert is_error
    assert "denominator" in body["error"]


def test_context_cannot_hold_more_than_retrieval_returned():
    """An impossible number is a broken measurement, and a broken measurement
    that reports a clean figure is this library's entire subject."""
    call("coverage_open", question="q", targets=["corpus"])
    body, is_error = call("coverage_retrieval", target="corpus", query="q",
                          corpus_size=100, retrieved=3, in_context=9)
    assert is_error
    assert "cannot have held more evidence" in body["error"]


def test_a_notification_gets_no_reply():
    """A JSON-RPC notification has no id. Replying to one is a protocol error
    that some clients treat as a fatal desync."""
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_it_runs_as_a_real_subprocess_over_stdio():
    """In-process dispatch is not proof the transport works."""
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    p = subprocess.run(
        [sys.executable, "-m", "notchecked.mcp_server"],
        input="\n".join(json.dumps(m) for m in msgs),
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert p.returncode == 0, p.stderr
    lines = [json.loads(x) for x in p.stdout.splitlines()]
    assert [x["id"] for x in lines] == [1, 2]  # the notification produced nothing


def test_malformed_json_does_not_kill_the_server():
    """A client that sends one bad line must not take the session down."""
    p = subprocess.run(
        [sys.executable, "-m", "notchecked.mcp_server"],
        input='not json at all\n{"jsonrpc":"2.0","id":9,"method":"tools/list"}\n',
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert p.returncode == 0
    assert json.loads(p.stdout.splitlines()[-1])["id"] == 9
