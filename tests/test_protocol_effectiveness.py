"""Does the protocol catch the failures it was built for?

The other suites establish IMPLEMENTATION CORRECTNESS — the software behaves as
the protocol says. This one asks a different and harder question: given the
exact real-world investigations that went wrong, would the protocol have
refused the claim that came out of them?

Every case below is a thing that actually happened on 2026-08-25, or a RAG
failure mode with a named mechanism. A case that the protocol does NOT catch is
kept here and marked, because a hole nobody wrote down is a hole nobody fixes.

NOTE ON WHAT THIS FILE CAN AND CANNOT SHOW. It can show the protocol refuses a
claim when the tools are used. It cannot show an agent will use them, and it
cannot show the problem generalises beyond this estate. Both of those need
evidence this file does not contain.
"""
from __future__ import annotations

import json

import pytest

from notchecked import mcp_server as srv


def call(name: str, **args):
    resp = srv.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": args},
    })
    return json.loads(resp["result"]["content"][0]["text"]), resp["result"]["isError"]


@pytest.fixture(autouse=True)
def _clean():
    srv._state.update({"report": None, "question": None,
                       "declared": [], "failing_verdicts": []})
    yield


# ==========================================================================
# The six real failures of 2026-08-25
# ==========================================================================

def test_real_1_portfolio_judged_from_a_fragment():
    """CLAIM MADE: "your portfolio undersells you."
    ACTUAL BASIS: 3,000 characters of a 10,828-word page.
    """
    call("coverage_open", question="Does the portfolio undersell him?",
         targets=["portfolio/index.html"])
    body, _ = call("coverage_checked", target="portfolio/index.html",
                   evidence="read the rendered text from the top of the page",
                   scope="3,000 of 10,828 words")
    assert body["exhaustive"] is False
    assert "does NOT support a claim that something is absent" in body["note"]

    fin, _ = call("coverage_finish")
    # "undersells" is an absence claim: it asserts things are NOT on the page.
    assert "ABSENCE_WARNING" in fin
    assert "3,000 of 10,828 words" in fin["ABSENCE_WARNING"]


def test_real_2_html_extraction_that_silently_dropped_links():
    """CLAIM MADE: "five project entries are missing."
    ACTUAL BASIS: a search over text with the HTML stripped, so anything named
    only inside an href was invisible. The measurement had a blind spot the
    measurer did not know about.

    THE PROTOCOL CATCHES THIS ONLY IF THE AGENT DESCRIBES ITS METHOD HONESTLY.
    `scope` is free text. An agent that writes "searched the whole page" when it
    searched stripped text records a true-sounding row. What the protocol does
    give is a written, disputable method — the row says "text with tags
    removed", and a reviewer can see the hole even when the author could not.
    """
    call("coverage_open", question="Which projects are missing from the page?",
         targets=["portfolio/index.html"])
    body, _ = call("coverage_checked", target="portfolio/index.html",
                   evidence="regex over text with HTML tags stripped",
                   scope="all visible prose; href attributes NOT searched")
    assert body["exhaustive"] is False
    fin, _ = call("coverage_finish")
    assert "ABSENCE_WARNING" in fin


def test_real_3_a_broken_walk_that_produced_three_different_counts():
    """CLAIM MADE: "36 Rust crates", then 677, then 34.
    ACTUAL BASIS: a filesystem walk that counted vendored dependency manifests.

    The honest record is CHECKER_FAILED — the tooling ran and could not observe
    the thing correctly. It is not DATA_DEGENERATE: the disk was fine.
    """
    call("coverage_open", question="How many Rust crates are there?",
         targets=["Rust crates on disk"])
    _body, is_error = call("coverage_gap", target="Rust crates on disk",
                          state="NOT_CHECKED_CHECKER_FAILED",
                          reason="the walk counted vendored dependency manifests as authored crates")
    assert not is_error
    fin, _ = call("coverage_finish")
    assert fin["checked"] == 0
    assert fin["gaps"][0]["state"] == "NOT_CHECKED_CHECKER_FAILED"
    assert "MUST state these gaps" in fin["INSTRUCTION"]


def test_real_4_searching_for_a_word_instead_of_the_semantic_state():
    """CLAIM MADE: "/portfolio/ is noindexed."
    ACTUAL BASIS: the string "noindex" appearing in the page's own prose, where
    it described a noindex page the owner had built. The robots meta tag said
    index,follow.

    A wrong method with a stated scope is disputable. The row below is visibly
    the wrong instrument for the question.
    """
    call("coverage_open", question="Is /portfolio/ noindexed?", targets=["/portfolio/"])
    body, _ = call("coverage_checked", target="/portfolio/",
                   evidence="substring search for 'noindex' anywhere in the response body",
                   scope="whole document body, prose included", exhaustive=True)
    assert not body.get("error")
    # exhaustive over the WRONG THING still yields a row a reviewer can reject
    assert body.get("evidence", True)
    fin, _ = call("coverage_finish")
    assert fin["checked"] == 1
    # PROTOCOL LIMIT, recorded deliberately: exhaustive coverage of the wrong
    # instrument is still exhaustive. Nothing here can know that a substring
    # search is not a robots-tag check. See test_hole_wrong_instrument below.


def test_real_5_one_platform_measured_four_claimed():
    """CLAIM MADE: "the host has zero followed inbound links."
    ACTUAL BASIS: dev.to only. Tumblr was passing followed links the whole time.

    This is the case the declared denominator was built for.
    """
    call("coverage_open", question="Does tts.bedvibe.studio have followed inbound links?",
         targets=["dev.to", "Tumblr", "Mastodon", "Bluesky"])
    call("coverage_checked", target="dev.to",
         evidence="fetched each post and read the rel attribute on outbound anchors",
         scope="all 8 posts", exhaustive=True)
    fin, _ = call("coverage_finish")

    assert fin["checked"] == 1
    assert fin["total"] == 4
    assert sorted(fin["declared_but_never_recorded"]) == ["Bluesky", "Mastodon", "Tumblr"]
    assert "MUST state these gaps" in fin["INSTRUCTION"]


def test_real_6_a_recorded_decision_reported_as_a_gap():
    """CLAIM MADE: "spkproof is unreleased" — framed as an omission.
    ACTUAL BASIS: a commit that says "make the pipeline match the decision not
    to publish". It is WAIVED, and WAIVED requires a named owner, which is what
    stops "nobody did this" being written where "someone decided this" is true.
    """
    call("coverage_open", question="Is spkproof published?", targets=["spkproof"])
    body, is_error = call("coverage_gap", target="spkproof",
                          state="NOT_CHECKED_WAIVED",
                          reason="owner decided not to publish; commit 252039c")
    if is_error:
        # the schema requires the named person — that is the point of the state
        assert "waived_by" in body["error"]
        body, is_error = call("coverage_gap", target="spkproof",
                              state="NOT_CHECKED_WAIVED",
                              reason="owner decided not to publish; commit 252039c",
                              waived_by="the repository owner")
    assert not is_error
    fin, _ = call("coverage_finish")
    assert fin["gaps"][0]["state"] == "NOT_CHECKED_WAIVED"


# ==========================================================================
# RAG failure modes, each with a named mechanism
# ==========================================================================

def test_rag_relevant_evidence_exists_but_retrieval_missed_it():
    """The document was there. The retriever did not return it. Today this is
    indistinguishable from "the corpus does not contain it"."""
    call("coverage_open", question="Is there a reimbursement policy?", targets=["policies"])
    body, _ = call("coverage_retrieval", target="policies",
                   query="reimbursement", corpus_size=2431, retrieved=8, in_context=8)
    assert body["coverage"] == "CHECKED"
    assert "CANNOT support 'there is no X in the corpus'" in body["ABSENCE_WARNING"]
    assert "2423 units were never looked at" in body["ABSENCE_WARNING"]


def test_rag_a_tiny_fraction_is_reported_as_a_tiny_fraction():
    call("coverage_open", question="q", targets=["corpus"])
    body, _ = call("coverage_retrieval", target="corpus", query="q",
                   corpus_size=2_000_000, retrieved=8, in_context=8)
    assert "0.0004" in body["scope"] or "of 2000000" in body["scope"]
    assert body["exhaustive"] is False


def test_rag_context_truncation_is_named_as_context_not_retrieval():
    call("coverage_open", question="q", targets=["corpus"])
    body, _ = call("coverage_retrieval", target="corpus", query="q",
                   corpus_size=1000, retrieved=10, in_context=0)
    assert body["stage"] == "context assembly"
    assert "CONTEXT FAILURE" in body["DIAGNOSIS"]


def test_rag_large_but_non_exhaustive_still_blocks_an_absence_claim():
    """999,999 of 1,000,000 is 99.9999% and still cannot establish absence.
    A threshold here would be a lie with a decimal point on it."""
    call("coverage_open", question="q", targets=["corpus"])
    body, _ = call("coverage_retrieval", target="corpus", query="q",
                   corpus_size=1_000_000, retrieved=999_999, in_context=999_999)
    assert body["exhaustive"] is False
    assert "ABSENCE_WARNING" in body
    assert "1 units were never looked at" in body["ABSENCE_WARNING"]


def test_rag_correct_evidence_retrieved_and_the_agent_still_reasons_wrong():
    """PROTOCOL LIMIT, recorded on purpose.

    Retrieval was exhaustive, nothing was dropped, the agent had everything and
    produced a wrong answer. The report is CHECKED with full coverage and no
    warning — correctly, because coverage is not correctness.

    This is the residual case, and it is where the value lies: once coverage is
    complete and truthful, a wrong answer is a REASONING failure and cannot be
    blamed on retrieval. That is a diagnosis the protocol enables and does not
    itself make.
    """
    call("coverage_open", question="q", targets=["corpus"])
    body, _ = call("coverage_retrieval", target="corpus", query="q",
                   corpus_size=12, retrieved=12, in_context=12)
    assert body["exhaustive"] is True
    assert "ABSENCE_WARNING" not in body
    fin, _ = call("coverage_finish")
    assert fin["gaps"] == []
    assert "MUST" not in fin["INSTRUCTION"]


# ==========================================================================
# Holes: places an agent can still turn a partial measurement into a claim
# ==========================================================================

def test_hole_exhaustive_is_self_asserted_against_a_contradicting_scope():
    """DEFECT FOUND BY THIS SUITE.

    An agent may pass exhaustive=True while its own scope string says it looked
    at part of the target. The protocol accepts the assertion and drops the
    absence warning, which is the failure this exists to prevent, performed by
    the tool that prevents it.

    Where the numbers are present in the scope, the contradiction is machine
    visible and must be refused.
    """
    call("coverage_open", question="q", targets=["a"])
    body, is_error = call("coverage_checked", target="a", evidence="skimmed it",
                          scope="3,000 of 10,828 words", exhaustive=True)
    assert is_error, "exhaustive=True must be refused when scope shows a fragment"
    assert "contradicts" in body["error"]


def test_hole_wrong_instrument_is_not_detectable():
    """PROTOCOL LIMIT — no test can fix this, and pretending otherwise would be
    the library's own error.

    An exhaustive search of the wrong thing is still exhaustive. The protocol
    records the method so a reader can dispute it; it cannot know that a
    substring search is not a robots-tag check. What it removes is the silence,
    not the possibility of being wrong.
    """
    call("coverage_open", question="Is it noindexed?", targets=["page"])
    _body, is_error = call("coverage_checked", target="page",
                          evidence="substring search for the word 'noindex'",
                          scope="whole document", exhaustive=True)
    assert not is_error  # accepted, and correctly so
    fin, _ = call("coverage_finish")
    assert "MUST" not in fin["INSTRUCTION"]  # the protocol has no objection


def test_hole_the_denominator_is_self_declared():
    """PROTOCOL LIMIT. An agent that declares one target and checks it reports
    100% coverage honestly and uselessly. Nothing in a protocol can know what
    the caller failed to think of.

    Mitigation, not a fix: targets are declared BEFORE looking, so the list
    reflects the plan rather than the outcome, and a reviewer sees the plan.
    """
    call("coverage_open", question="Does the host have followed links?",
         targets=["dev.to"])  # the 2026-08-25 mistake, honestly recorded
    call("coverage_checked", target="dev.to", evidence="read every rel attribute",
         scope="all 8 posts", exhaustive=True)
    fin, _ = call("coverage_finish")
    assert fin["checked"] == fin["total"] == 1
    assert "MUST" not in fin["INSTRUCTION"]


def test_hole_retrieval_numbers_are_self_reported():
    """PROTOCOL LIMIT. corpus_size, retrieved and in_context come from the
    caller. A caller that reports corpus_size=8 when the corpus holds 2,431
    gets a clean exhaustive row.

    What IS enforced is internal consistency: in_context may not exceed
    retrieved, and corpus_size must be positive. Those catch a broken
    measurement, not a dishonest one.
    """
    call("coverage_open", question="q", targets=["corpus"])
    body, is_error = call("coverage_retrieval", target="corpus", query="q",
                          corpus_size=8, retrieved=8, in_context=8)
    assert not is_error
    assert body["exhaustive"] is True  # true of the declared corpus, and unverifiable
