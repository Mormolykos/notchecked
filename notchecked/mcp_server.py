"""An MCP server that makes an agent declare its coverage before it answers.

WHY THIS EXISTS, AND THE EVIDENCE FOR IT

    This library was written because validators conflate "I did not check this"
    with "this passed". The four cases in the README are all programs. The fifth
    case is the one that produced this file, and it is not a program.

    On 2026-08-25 an AI assistant working on this estate made six confident
    claims in one session, each later shown false:

        "your portfolio undersells you"   - had read 3,000 chars of 10,828 words
        "five project entries are missing" - the search stripped HTML, so it
                                             never saw anything named in a link
        "36 Rust crates" -> "677" -> "34"  - three different broken walks
        "/portfolio/ is noindexed"         - grepped for the word, not the tag
        "the host has zero followed links" - measured one platform of four
        "spkproof is unreleased"           - it was a recorded decision

    Every one has the same shape: a VERDICT issued where the honest output was
    NOT_CHECKED. The library existed the whole time and could not help, because
    it types the skips a *program* makes and has no way to sit between an agent
    and a sentence.

    That is the gap this server closes. Agents assert constantly and have no
    vocabulary for doubt. Their frameworks give them tools to act and nothing to
    say "I could not determine this" in a form a caller can count.

HOW IT CHANGES THE FAILURE

    The agent opens a report, records one row per thing it was asked about, and
    calls `coverage_finish`. `coverage_finish` returns the summary AND, when
    gaps exist, an explicit instruction to state them in the answer. An agent
    that has recorded three CHECKED rows out of eleven cannot receive a clean
    summary to paste; it receives "3 of 11 checked" and the list of what it did
    not look at.

    It cannot force honesty -- nothing can, and claiming otherwise would be this
    library's own error one level up. What it removes is the *silence*: the gap
    stops being invisible to the caller, which is the whole thesis.

PROTOCOL

    MCP over stdio, JSON-RPC 2.0, written from the wire format. No SDK, because
    notchecked declares no runtime dependencies and a vocabulary that needs a
    framework to be spoken is not a vocabulary. Same reasoning as trainproof's
    tfevents reader.

USAGE

    python -m notchecked.mcp_server

    In an MCP client config:
        {"command": "python", "args": ["-m", "notchecked.mcp_server"]}
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

from .record import Record
from .report import Report
from .states import Coverage

PROTOCOL_VERSION = "2024-11-05"

# One report at a time. A server that let an agent interleave several reports
# would let it record a gap against the wrong question, which is a quieter
# version of the failure this exists to remove.
_state: dict[str, Any] = {"report": None, "question": None}


_SCOPE_FRACTION = re.compile(
    r"([\d][\d,._]*)\s*(?:of|/|out of)\s*([\d][\d,._]*)", re.IGNORECASE)


def _scope_contradicts_exhaustive(scope: str) -> tuple[int, int] | None:
    """Numbers in a scope string that prove it is NOT exhaustive.

    FOUND BY tests/test_protocol_effectiveness.py. `exhaustive` was a bare
    assertion: an agent could write scope="3,000 of 10,828 words" and pass
    exhaustive=True, and the absence warning would be dropped -- the tool
    performing the exact failure it exists to prevent.

    Where the scope carries "N of M", the contradiction is machine visible and
    must be refused. Where it does not, the assertion stands unverified, which
    is recorded as a known limit rather than hidden.
    """
    m = _SCOPE_FRACTION.search(scope or "")
    if not m:
        return None
    try:
        part = int(m.group(1).replace(",", "").replace("_", "").replace(".", ""))
        whole = int(m.group(2).replace(",", "").replace("_", "").replace(".", ""))
    except ValueError:
        return None
    if whole > 0 and part < whole:
        return part, whole
    return None


# --------------------------------------------------------------------------
# What coverage a claim actually needs
# --------------------------------------------------------------------------
#
# THE CONTROL IS THE CLAIM TYPE, NOT A COVERAGE THRESHOLD. This is the part
# that took longest to see, and it is why no percentage appears in this file as
# a gate. 0.6% coverage is entirely adequate for "the policy says X" -- you need
# the one document you are quoting and nothing else. The same 0.6% is
# catastrophic for "there is no policy about X", which asserts something about
# every document that was not read. A single threshold cannot serve both, and
# picking one would license the second sentence or forbid the first.
#
# WHY FAITHFULNESS DOES NOT COVER THIS. Faithfulness asks whether the answer is
# supported by the retrieved context. It never asks whether the context was
# sufficient for the claim. An answer of "there is no such policy" derived from
# 8 retrieved chunks scores a perfect faithfulness -- it invented nothing -- and
# may be false about the other 2,423 documents. Faithfulness scores
# answer-against-context; coverage scores context-against-corpus. They are
# different axes and a system can be perfect on one while silent on the other.
CLAIM_RULES = {
    "existence": (
        "An EXISTENCE claim ('the policy says X', 'he mentions Rust') needs only "
        "the units it cites. Any coverage is sufficient."
    ),
    "absence": (
        "An ABSENCE claim ('there is no policy about X') requires EXHAUSTIVE "
        "coverage. It is a statement about every unit you did not read."
    ),
    "universal": (
        "A UNIVERSAL claim ('all policies require X', 'the only mention is') "
        "requires EXHAUSTIVE coverage, for the same reason as absence."
    ),
    "superlative": (
        "A SUPERLATIVE claim ('the most recent', 'the largest') requires "
        "EXHAUSTIVE coverage: the unread remainder may hold the true maximum."
    ),
    "count": (
        "A COUNT claim ('there are three mentions') requires EXHAUSTIVE "
        "coverage. A count over a sample is an estimate, and reporting it as a "
        "count is the same silent upgrade this whole schema exists to stop."
    ),
}

# Claims that assert something about what was NOT retrieved.
_NEEDS_EXHAUSTIVE = frozenset({"absence", "universal", "superlative", "count"})


def _claim_is_supported(claim_type: str, exhaustive: bool) -> bool:
    if claim_type not in _NEEDS_EXHAUSTIVE:
        return True
    return exhaustive


# --------------------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------------------

def _coverage_open(question: str, targets: list[str] | None = None,
                   failing_verdicts: list[str] | None = None) -> dict:
    """Begin a report. `targets` is the honest denominator, declared up front.

    Declaring the targets BEFORE looking is what makes the denominator
    trustworthy. An agent that names its targets afterwards names the ones it
    happened to check, and 3-of-3 always looks like full coverage.

    `failing_verdicts` is only needed if you intend to attach verdicts. The
    library refuses to close a report that carries verdicts without it -- "there
    is no safe default for another domain's vocabulary" -- and it is right to.
    The first version of this server omitted it and was refused by its own
    library, which is the schema catching its own transport.
    """
    _state["report"] = Report(
        tool="agent-answer",
        failing_verdicts=frozenset(failing_verdicts) if failing_verdicts else None,
    )
    _state["question"] = question
    _state["declared"] = list(targets or [])
    _state["failing_verdicts"] = list(failing_verdicts or [])
    return {
        "opened": True,
        "question": question,
        "declared_targets": _state["declared"],
        "failing_verdicts": _state["failing_verdicts"],
        "note": (
            "Record one row per target with coverage_checked or coverage_gap, "
            "then call coverage_finish before answering. Declaring targets up "
            "front is what keeps the denominator honest. If you plan to attach "
            "verdicts, declare failing_verdicts here — the schema will not guess "
            "which of your words mean failure."
        ),
    }


def _coverage_checked(target: str, evidence: str, scope: str = "",
                      exhaustive: bool = False, verdict: str | None = None) -> dict:
    """Record that a target WAS determined, how, and over how much of it.

    `evidence` is required and is the point of the tool. "I checked the
    portfolio" is the claim that went wrong six times; "I read the 38 <h3>
    headings from the raw HTML" is a thing a reader can dispute.

    `scope` and `exhaustive` were added after a second model audited the first
    version and found the hole the failure actually went through. Evidence alone
    does not say how MUCH of the target was inspected, and every wrong claim on
    2026-08-25 was true of the part inspected and false of the whole:

        "your portfolio undersells you"   evidence: "read the page"
                                          scope:    3,000 of 10,828 words

    Both rows look identical without `scope`. With it, the second is visibly
    unable to support a statement about the page.

    `exhaustive` carries the distinction that matters for NEGATIVE claims. "I
    did not find X" and "X is not there" are different assertions, and only a
    complete inspection supports the second. `coverage_finish` refuses to let a
    partial row underwrite a claim of absence.
    """
    rep = _state.get("report")
    if rep is None:
        return {"error": "no open report — call coverage_open first"}
    if not evidence or not evidence.strip():
        return {"error": (
            "evidence is required. A CHECKED row without a stated method is the "
            "same unverifiable assertion this server exists to prevent."
        )}
    if not scope or not scope.strip():
        return {"error": (
            "scope is required: what PORTION of the target did you inspect? "
            "'read the page' and 'read 3,000 of 10,828 words' are the same "
            "evidence string and different claims. Without scope the report "
            "cannot tell them apart, and that is the hole every wrong claim on "
            "2026-08-25 went through."
        )}
    if verdict and not _state.get("failing_verdicts"):
        return {"error": (
            f"you attached the verdict {verdict!r} but did not declare failing_verdicts in "
            "coverage_open. The schema will not guess which words in your domain "
            "mean failure — declare them, or record coverage without a verdict. "
            "Coverage and verdict are separate axes and that separation is the "
            "point."
        )}
    if exhaustive:
        contradiction = _scope_contradicts_exhaustive(scope)
        if contradiction:
            part, whole = contradiction
            return {"error": (
                f"you set exhaustive=true but your own scope says {part} of {whole}. "
                "That contradicts itself, and accepting it would drop the absence "
                "warning on a fragment — this tool performing the exact failure it "
                "exists to prevent. Either inspect the whole target, or leave "
                "exhaustive false and keep the warning."
            )}
    rep.add(Record(
        target=target,
        coverage=Coverage.CHECKED,
        verdict=verdict,
        evidence=(evidence,),
        extra={"scope": scope, "exhaustive": bool(exhaustive)},
    ))
    return {
        "recorded": target, "coverage": "CHECKED", "verdict": verdict,
        "scope": scope, "exhaustive": bool(exhaustive),
        "note": None if exhaustive else (
            "Recorded as a PARTIAL inspection. This row supports statements "
            "about what you found. It does NOT support a claim that something "
            "is absent — for that, inspect the whole target and set "
            "exhaustive=true."
        ),
    }


def _coverage_gap(target: str, state: str, reason: str,
                  permanent_wrt: str | None = None,
                  waived_by: str | None = None,
                  blocked_by: str | None = None) -> dict:
    """Record that a target was NOT determined, and whose problem that is."""
    rep = _state.get("report")
    if rep is None:
        return {"error": "no open report — call coverage_open first"}
    try:
        cov = Coverage[state]
    except KeyError:
        return {"error": "unknown state {!r}. Valid: {}".format(state, ", ".join(c.name for c in Coverage))}
    if cov is Coverage.CHECKED:
        return {"error": "coverage_gap cannot record CHECKED — use coverage_checked"}
    try:
        rep.add(Record(
            target=target, coverage=cov, reason=reason,
            permanent_wrt=permanent_wrt, waived_by=waived_by, blocked_by=blocked_by,
        ))
    except Exception as exc:  # noqa: BLE001 - the schema's rules, surfaced as a refusal
        return {"error": str(exc)}
    return {"recorded": target, "coverage": cov.name, "reason": reason}


def _coverage_retrieval(target: str, query: str, corpus_size: int,
                        retrieved: int, in_context: int | None = None,
                        corpus_id: str | None = None,
                        method: str | None = None,
                        claim_type: str = "existence") -> dict:
    """Record that a target was inspected THROUGH a retrieval system.

    THE POINT, AND IT IS THE WHOLE PRODUCT: retrieval is not the evidence. It
    is a measurement instrument, and an instrument has its own coverage.

    An agent that queried 2,431 documents and received 8 chunks has inspected
    0.3% of the corpus. Today it reports that identically to an exhaustive
    read, and every downstream reader treats the two the same. "The company has
    no policy about X" and "no policy about X appeared in the 8 chunks my
    retriever returned" are different claims, and only the second one is true.

    IT ALSO SEPARATES THREE FAILURES THAT CURRENTLY LOOK IDENTICAL. When an
    answer is wrong, "the LLM hallucinated" is usually three different
    engineering problems wearing one label:

        retrieved == 0            the right document was never surfaced
                                  -> fix retrieval
        in_context < retrieved    it was surfaced and dropped at assembly
                                  -> fix context construction
        in_context == retrieved   the agent had it and reasoned past it
        and the answer is wrong   -> fix the agent

    This records which one happened. Nothing here can tell you the answer was
    wrong; it tells you what the agent actually had when it answered, which is
    the thing nobody logs and everybody guesses at.

    NO NEW STATES. `in_context < retrieved` is CHECKER_FAILED: your tooling
    surfaced the evidence and then could not observe it. The eight states are
    frozen after a public review and a truncation is not a ninth kind of gap.
    """
    rep = _state.get("report")
    if rep is None:
        return {"error": "no open report — call coverage_open first"}
    if claim_type not in CLAIM_RULES:
        return {"error": (
            f"unknown claim_type {claim_type!r}. Valid: "
            + ", ".join(sorted(CLAIM_RULES))
            + ". The claim type is what decides how much coverage you need — a "
              "percentage threshold cannot, because 0.6% is fine for 'the policy "
              "says X' and catastrophic for 'there is no policy about X'."
        )}
    if corpus_size <= 0:
        return {"error": (
            "corpus_size must be positive: it is the denominator, and a "
            "coverage figure without one is the assertion this exists to stop."
        )}
    if retrieved < 0 or (in_context is not None and in_context < 0):
        return {"error": "retrieved and in_context cannot be negative"}
    if in_context is not None and in_context > retrieved:
        return {"error": (
            f"in_context ({in_context}) exceeds retrieved ({retrieved}) — the agent "
            "cannot have held more evidence than the retriever returned"
        )}

    used = retrieved if in_context is None else in_context
    fraction = used / corpus_size
    exhaustive = used >= corpus_size

    extra = {
        "source": "retrieval",
        "query": query,
        "corpus_id": corpus_id,
        "corpus_size": corpus_size,
        "retrieved": retrieved,
        "in_context": in_context,
        "method": method,
        "scope": f"{used} of {corpus_size} corpus units ({fraction * 100:.3g}%)",
        "exhaustive": exhaustive,
    }

    # Nothing came back. The agent did not inspect a small part of the corpus;
    # it inspected none of it, and a CHECKED row here would be a lie about the
    # only thing that matters.
    if retrieved == 0:
        rep.add(Record(
            target=target, coverage=Coverage.NOT_CHECKED_CHECKER_FAILED,
            reason=f"retrieval returned nothing for {query!r} over {corpus_size} units",
            extra=extra,
        ))
        return {
            "recorded": target, "coverage": "NOT_CHECKED_CHECKER_FAILED",
            "stage": "retrieval", "scope": extra["scope"],
            "DIAGNOSIS": (
                "RETRIEVAL FAILURE, not a reasoning failure. Nothing was "
                "surfaced, so the agent had no evidence to reason over. Fix the "
                "retriever or the query before blaming the answer."
            ),
        }

    dropped = 0 if in_context is None else retrieved - in_context
    if dropped > 0 and in_context == 0:
        rep.add(Record(
            target=target, coverage=Coverage.NOT_CHECKED_CHECKER_FAILED,
            reason=f"all {retrieved} retrieved units were dropped before the agent saw them",
            extra=extra,
        ))
        return {
            "recorded": target, "coverage": "NOT_CHECKED_CHECKER_FAILED",
            "stage": "context assembly", "scope": extra["scope"],
            "DIAGNOSIS": (
                "CONTEXT FAILURE, not a retrieval failure and not a reasoning failure. "
                f"The retriever found {retrieved} units and every one was dropped "
                "before the agent could read it."
            ),
        }

    rep.add(Record(
        target=target, coverage=Coverage.CHECKED,
        evidence=("retrieval over {}: query {!r}, {}".format(corpus_id or "corpus", query, extra["scope"]),),
        extra=extra,
    ))
    out = {
        "recorded": target, "coverage": "CHECKED", "stage": "answered",
        "scope": extra["scope"], "exhaustive": exhaustive,
        "dropped_at_context_assembly": dropped,
        "claim_type": claim_type,
        "claim_supported": _claim_is_supported(claim_type, exhaustive),
    }
    if not out["claim_supported"]:
        out["REFUSE_THIS_CLAIM"] = (
            f"A {claim_type.upper()} claim asserts something about every unit you "
            f"did NOT read, and {corpus_size - used} were never read. "
            f"{CLAIM_RULES[claim_type]} "
            "Downgrade the answer to what you found, or inspect the whole corpus. "
            "Note that FAITHFULNESS does not help here: an answer perfectly "
            "grounded in 8 retrieved chunks can still be a false statement about "
            "2,431 documents. Faithfulness scores answer-against-context; this "
            "scores context-against-corpus."
        )
    if dropped > 0:
        out["PARTIAL_CONTEXT"] = (
            f"{dropped} of {retrieved} retrieved units were dropped before the agent "
            "saw them. If the answer is wrong, check context assembly before the agent."
        )
    if not exhaustive:
        out["ABSENCE_WARNING"] = (
            f"You inspected {extra['scope']}. This supports statements about what you "
            "FOUND. It CANNOT support 'there is no X in the corpus' — that requires "
            f"exhaustive coverage, and {corpus_size - used} units were never looked at."
        )
    return out


def _coverage_finish() -> dict:
    """Close the report and return coverage — with the gaps spelled out.

    This is where the server earns its place. It never returns a bare "done".
    When rows are missing or gaps exist it returns an instruction to state them,
    because a caller who cannot see the gap will read the answer as complete.
    """
    rep = _state.get("report")
    if rep is None:
        return {"error": "no open report — call coverage_open first"}

    data = rep.to_dict()
    recorded = {r.target for r in rep.records}
    declared = set(_state.get("declared") or [])
    never_recorded = sorted(declared - recorded)

    checked = [r.target for r in rep.records if r.coverage is Coverage.CHECKED]
    partial = [
        {"target": r.target, "scope": (r.extra or {}).get("scope")}
        for r in rep.records
        if r.coverage is Coverage.CHECKED and not (r.extra or {}).get("exhaustive")
    ]
    gaps = [
        {"target": r.target, "state": r.coverage.name, "reason": r.reason}
        for r in rep.records if r.coverage is not Coverage.CHECKED
    ]

    total = len(recorded | declared)
    out: dict[str, Any] = {
        "question": _state.get("question"),
        "checked": len(checked),
        "total": total,
        "gaps": gaps,
        "declared_but_never_recorded": never_recorded,
        "partial_inspections": partial,
        "report": data,
    }

    # A negative claim needs a complete look. "I did not find five entries" and
    # "five entries are missing" are different assertions, and only the second
    # requires exhaustiveness -- which is exactly how "five entries are missing"
    # got published on 2026-08-25 off a search that had stripped the HTML.
    if partial:
        out["ABSENCE_WARNING"] = (
            f"{len(partial)} target(s) were inspected only in part: "
            + ", ".join(f"{p['target']} ({p['scope']})" for p in partial)
            + ". These rows support what you FOUND. They do not support a claim "
            "that anything is ABSENT — absence of evidence found in a fragment "
            "is not evidence of absence in the whole."
        )

    if gaps or never_recorded:
        out["INSTRUCTION"] = (
            f"Your answer MUST state these gaps. You determined {len(checked)} of {total}. "
            "Do not present this as a complete answer, and do not let a target "
            "you never looked at read as one that passed — that is the exact "
            "failure this schema exists to remove."
        )
    else:
        out["INSTRUCTION"] = (
            "Every declared target was determined with stated evidence. "
            "You may answer without a coverage caveat."
        )

    _state["report"] = None
    _state["question"] = None
    _state["declared"] = []
    return out


def _coverage_states() -> dict:
    """The vocabulary, with who owns each gap. For an agent choosing a state."""
    return {
        "states": {
            "CHECKED": "a determination was made; the verdict is separate",
            "NOT_CHECKED_DATA_DEGENERATE": "the data is present and unusable — owner: the data",
            "NOT_CHECKED_CHECKER_FAILED": "your tooling raised, timed out, or could not observe — owner: you",
            "NOT_CHECKED_WAIVED": "in scope, deliberately not evaluated by a named person — requires waived_by",
            "NOT_CHECKED_PREREQUISITE_FAILED": "something upstream failed first — requires blocked_by",
            "OUT_OF_SCOPE_CALLER": "not requested",
            "OUT_OF_SCOPE_DATA_TRANSIENT": "does not apply yet to this target",
            "OUT_OF_SCOPE_DATA_PERMANENT": "no artifact of this kind can ever evidence it — requires permanent_wrt",
        },
        "rule": (
            "Coverage is not verdict. CHECKED says a determination was made, not "
            "what it was. Permanence is relative to a target, never absolute."
        ),
    }


TOOLS = [
    {
        "name": "coverage_open",
        "description": (
            "Begin a coverage report before answering a question about a system. "
            "Declare every target you were asked about UP FRONT — that is what "
            "keeps the denominator honest."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "what you were asked"},
                "targets": {
                    "type": "array", "items": {"type": "string"},
                    "description": "every thing the answer depends on, named before you look",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "coverage_checked",
        "description": (
            "Record that you determined one target: HOW you checked, and how MUCH "
            "of it you looked at. 'I checked it' is the assertion this server "
            "exists to stop, and scope is what separates a fragment from the whole."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "evidence": {"type": "string", "description": "the actual method or measurement"},
                "scope": {"type": "string", "description": "what PORTION you inspected, e.g. '38 of 38 headings' or '3,000 of 10,828 words'"},
                "exhaustive": {"type": "boolean", "description": "true only if you inspected the WHOLE target. Required for any claim that something is absent."},
                "verdict": {"type": "string", "description": "your domain's result; declare failing_verdicts in coverage_open first"},
            },
            "required": ["target", "evidence", "scope"],
        },
    },
    {
        "name": "coverage_gap",
        "description": (
            "Record that you could NOT determine a target, in a typed state that "
            "says whose problem it is. Call coverage_states to choose."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "state": {"type": "string", "description": "one of the eight states"},
                "reason": {"type": "string"},
                "permanent_wrt": {"type": "string", "description": "required for OUT_OF_SCOPE_DATA_PERMANENT"},
                "waived_by": {"type": "string", "description": "required for NOT_CHECKED_WAIVED"},
                "blocked_by": {"type": "string", "description": "required for NOT_CHECKED_PREREQUISITE_FAILED"},
            },
            "required": ["target", "state", "reason"],
        },
    },
    {
        "name": "coverage_retrieval",
        "description": (
            "Record that you inspected a target THROUGH a retrieval system (RAG, "
            "search, a database query). Retrieval is a measurement instrument, not "
            "the evidence: 8 chunks out of 2,431 documents is 0.3% coverage and "
            "cannot support 'there is no X'. Also separates a retrieval failure "
            "from a context-truncation failure from a reasoning failure, which "
            "all look like 'the model hallucinated' today."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "what you were trying to establish"},
                "query": {"type": "string", "description": "the query you actually issued"},
                "corpus_size": {"type": "integer", "description": "how many units exist IN TOTAL — the denominator"},
                "retrieved": {"type": "integer", "description": "how many units the retriever returned"},
                "in_context": {"type": "integer", "description": "how many survived context assembly and reached you"},
                "corpus_id": {"type": "string", "description": "which corpus and version"},
                "method": {"type": "string", "description": "hybrid, dense, bm25, sql, ..."},
                "claim_type": {
                    "type": "string",
                    "enum": ["existence", "absence", "universal", "superlative", "count"],
                    "description": (
                        "What SHAPE of claim you intend to make. This decides how much "
                        "coverage you need — not a percentage. 'existence' ('the policy "
                        "says X') needs only the cited units and is fine at 0.6%. "
                        "'absence', 'universal', 'superlative' and 'count' each assert "
                        "something about the units you did NOT read, and require "
                        "exhaustive coverage at any corpus size."
                    ),
                },
            },
            "required": ["target", "query", "corpus_size", "retrieved"],
        },
    },
    {
        "name": "coverage_finish",
        "description": (
            "Close the report and get the coverage summary. Returns the gaps and "
            "an instruction to state them. Call this BEFORE you answer."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "coverage_states",
        "description": "The eight states and who owns each gap.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "coverage_open": _coverage_open,
    "coverage_checked": _coverage_checked,
    "coverage_gap": _coverage_gap,
    "coverage_retrieval": _coverage_retrieval,
    "coverage_finish": _coverage_finish,
    "coverage_states": _coverage_states,
}


# --------------------------------------------------------------------------
# JSON-RPC over stdio
# --------------------------------------------------------------------------

def handle(msg: dict) -> dict | None:
    """One request in, one response out. None for notifications."""
    method = msg.get("method")
    mid = msg.get("id")

    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "notchecked", "version": "0.1.0"},
        })

    if method in ("notifications/initialized", "initialized"):
        return None  # notification: no id, no reply

    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            return _err(mid, -32601, f"unknown tool {name!r}")
        try:
            result = fn(**(params.get("arguments") or {}))
        except TypeError as exc:
            return _err(mid, -32602, f"bad arguments for {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - a crash here must not look like a clean run
            return _err(mid, -32603, f"{name} failed: {exc}")
        return _ok(mid, {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            # `isError` is how the caller tells a refusal from a result. Omitting
            # it on a refusal would make "I would not record that" look like "I
            # recorded that" -- this library's thesis, in its own transport.
            "isError": bool(isinstance(result, dict) and result.get("error")),
        })

    if mid is None:
        return None
    return _err(mid, -32601, f"unknown method {method!r}")


def _ok(mid: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
