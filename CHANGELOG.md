# Changelog

All notable changes to `notchecked` are recorded here.

## [Unreleased]

On `main`, not in any published version. `pip install notchecked` gives 0.2.0,
which collects **112 tests**; `main` collects **119**. Both are correct about
different code, and this section exists because until now nothing outside the
commit log said so.

### Added

- **`claim_type`: the control is the shape of the sentence, not a percentage**
  (`a2cefb9`). `CLAIM_RULES` in `notchecked/mcp_server.py` names five claim types,
  `_NEEDS_EXHAUSTIVE` marks the four that assert something about the unread remainder,
  and `_claim_is_supported()` enforces it.

  The question that produced it was what a retrieval system should report and what
  counts as acceptable coverage. The second half has no numeric answer. 0.598% is a
  live agent's real coverage: entirely adequate for *"he mentions Rust"*, where you
  need only the unit you are quoting, and incapable of supporting *"he never mentions
  Rust"*, which asserts something about 997 units nobody read. One threshold cannot
  serve both — set it low and it licenses the second, set it high and it forbids the
  first. So no percentage appears anywhere in the protocol as a gate. `existence`
  needs only what it cites; `absence`, `universal`, `superlative` and `count` each
  require exhaustive coverage at any corpus size, because 999,999 units of 1,000,000
  still cannot establish absence.

  **+7 tests** (`tests/test_protocol_effectiveness.py`: three cases plus
  `test_every_claim_about_the_unread_remainder_needs_exhaustive` parametrized over the
  four exhaustive types) — including that the same coverage is accepted for one claim
  and refused for another, that faithfulness is named as insufficient, and that an
  unknown claim type is refused with its reason rather than waved through.

## 0.2.0 — 2026-08-25

An MCP server, and retrieval treated as an instrument with its own coverage.

**No state was added or removed. The eight are frozen after Boris Teplitsky's public
review**, and two external proposals were rejected on that ground: making `CHECKED` mean
"the evidence was sufficient" re-collapses coverage into verdict, which is the bug this
library exists for; and a context truncation is `CHECKER_FAILED` — the tooling surfaced
the evidence and then could not observe it — not a ninth kind of gap.

### The fifth instance of the failure was not a program

The four cases in the README are all software. On 2026-08-25 an AI assistant working on
this estate made six confident claims in one session, each from a partial measurement: a
portfolio judged from 3,000 of 10,828 words; "five entries are missing" from a search
that had stripped the HTML, so anything named only in an `href` was invisible; three
different Rust crate counts from three broken filesystem walks; "the page is noindexed"
from grepping for the *word* instead of the tag; "zero followed inbound links" measured
on one platform of four; and an explicit recorded decision reported as an omission.

Every one is a VERDICT issued where the honest output was NOT_CHECKED. The library could
not help, because it types the skips a *program* makes and has nothing to say between an
agent and a sentence.

### Added

- **`notchecked.mcp_server`** — an MCP server over stdio, written from the JSON-RPC wire
  format. No SDK: this library declares no runtime dependencies, and a vocabulary that
  needs a framework to be spoken is not a vocabulary.
- **`coverage_retrieval`** — the part that matters. **Retrieval is not the evidence; it is
  a measurement instrument, and an instrument has its own coverage.** An agent that
  queried 2,431 documents and received 8 chunks inspected 0.3% of the corpus, and today
  reports that identically to an exhaustive read. It also separates three failures that
  currently share the label "the model hallucinated": nothing was retrieved (fix the
  retriever), it was retrieved and dropped at context assembly (fix assembly), or the
  agent had it and reasoned past it (fix the agent).
- **`scope` and `exhaustive` on every checked row.** Evidence says *how*; scope says *how
  much*. Without scope, "read the page" and "read 3,000 of 10,828 words" are the same row.
- **An absence rule.** A partial inspection supports statements about what you FOUND. It
  cannot support a claim that something is ABSENT — including at 999,999 of 1,000,000,
  because a threshold there would be a lie with a decimal point on it.

### Fixed

- **`exhaustive` was a bare assertion.** An agent could pass `exhaustive=true` alongside
  `scope="3,000 of 10,828 words"` and the absence warning was dropped — this tool
  committing the exact failure it exists to prevent, one layer above the schema it
  protects. Where the scope carries "N of M" the contradiction is machine visible and is
  now refused. Found by the effectiveness suite on its first run.
- Evidence-free `CHECKED` rows were accepted. They are now refused.
- The server's own first version was refused by its own library for attaching verdicts
  without declaring a failing set. That refusal is correct and is now surfaced at the
  point of the mistake rather than on close.

### Limits, recorded as passing tests rather than hidden

An exhaustive search of the **wrong instrument** is still exhaustive. The target list is
**self-declared**, so nothing here can know what the caller failed to think of. Retrieval
counts are **self-reported**, with only internal consistency enforced. A hole nobody
writes down is a hole nobody fixes.

**Not claimed:** that the mechanism is proven. The tests show the protocol refuses a claim
*when the tools are used*. They do not show an agent will use them, and they do not show
the failure generalises beyond one estate.

112 tests, ruff clean, zero runtime dependencies.

## 0.1.0 — 2026-08-25

First release to PyPI. The eight states are settled between two independent domains; the
Python surface around them is not yet frozen.

### Boris Teplitsky's second review — three corrections, all schema-level (2026-08-24)

Sent before tagging, so objecting stayed cheap. All three were accepted. **No state was added
or removed** — the eight terminal states are unchanged.

- **`permanent_wrt` is now REQUIRED on `OUT_OF_SCOPE / DATA_PERMANENT`.** Permanence is
  relative to a target type, never absolute. A Kubernetes control is permanently out of scope
  only while the target has no Kubernetes; change the target and it becomes a row. Unqualified
  "nobody, never" lets two reports on the same framework disagree while both are correct, which
  makes the state useless to the audience it was added for. Constructing one without the
  reference now raises, and supplying it on any *mutable* state raises too — permanence that
  can move is not permanence. **This is a breaking change**, taken now because nothing is
  tagged; it broke two of this repository's own tests on the first run, which is the evidence
  that it was doing something.
- **`Report.exclude(rule=, count=, permanent_wrt=)` — rows for the checkable subset, one count
  for the rest.** A framework document is hundreds of pages of which a few paragraphs concern
  anything an artifact can evidence; a `DATA_PERMANENT` row each makes the report mostly noise.
  Ingest decides what becomes a row. The count **cannot be stated without the rule that
  produced it**, and it enters `total` — so excluding 412 of 415 reports a 99% exclusion ratio
  rather than a flattering silence. An unattributed count would be the same silence this
  library removes, moved up a level from the row to the corpus.
- **Scope stated: the taxonomy starts after the unit exists.** In a linter a row is a check
  somebody wrote. In compliance a framework is prose and the mapping to requirements is a
  judgment call — one paragraph can yield three, three can collapse into one. Nothing here
  governs that, and the README no longer reads as though rows arrive by themselves.

He also confirmed, from the side that would defend it in an audit, that `WAIVED` is a coverage
state rather than a verdict and must stay in the denominator. No change; the design was right.

On the tie-break rules he declined to give an opinion, saying he has never sat through an
audit and would only be describing how he reasons. That question is still open.

Credit in the README is now under his name, **Boris Teplitsky (`New_Technician_7041`)**, at
his request rather than the handle alone.

**And one defect the new code found in the old renderer, immediately.** Running the README
example through the bulk path printed `413 out of scope (100% of all targets)` while one
target had been checked — `:.0%` rounded 99.5 up. A reader takes "100% out of scope" as
"nothing was measured", which is the indistinguishable-from-nothing failure this library
exists to remove, committed by its own reporter one layer above the schema it protects. `100%`
is now printed only when `excluded == total` and `0%` only when nothing was excluded;
everything between is floored into `(0, 100)`. The mirror case is covered too: 1 excluded of
400 floored to `0%`, which reads as none.

14 new tests (43 total, from 29).

### The taxonomy attack is now a file, not a memory (2026-08-24)

The first attack was recorded only by its outcome — twelve fit one state, five fit none, four
fit two — and **never as a case list**, so when the schema changed it could not be re-run.
Reconstructing the cases from recollection and calling that evidence would be this library's
own failure mode, committed by its author.

`tests/test_taxonomy_attack.py` is the fix, and it states plainly that it is a **new** attack
rather than a recovery of the old one. 26 cases across ML training, infrastructure compliance,
RAG evaluation, CI/CD and production monitoring, each asserting the state it lands in. Three
structural tests on top: every state must be reached by some case, every claimed domain must
appear, and every state that demands a pointer must still demand it — because the cases supply
those pointers and would keep passing if the guard silently went.

Three cases that fit **no** state are kept in `FITS_NO_STATE` with their reasoning: conflicting
evidence (a verdict, not a gap), a partially-completed check (the caller must split the
target), and a target nobody scheduled (caught by `expected` + `missing()`, since a row nobody
wrote cannot carry a state). A documented hole is a finding; a deleted case is a hole nobody
can see.

**Verified to fire.** Removing the `permanent_wrt` guard makes both the objection test and the
attack's pointer test fail; restoring it returns 74 passing. A suite that has never failed is
not evidence.

74 tests total.

**Outstanding before a tag:** Boris has had the three corrections but has not yet responded to
them. Tagging before he has had the chance to object would break the arrangement he was given
— that objecting stays cheap until there is a release.

### The states

Eight terminal coverage states, each carrying an **owner** and a **permanence**. A test
enforces that no two share *both* — the moment two states have the same owner and the same
remediation, one of them is misfiled and its reader gets a to-do they cannot action.

```
CHECKED
NOT_CHECKED / DATA_DEGENERATE       the data          moves with better data
NOT_CHECKED / CHECKER_FAILED        your tooling      moves when you fix it
NOT_CHECKED / WAIVED                a named person    moves at expiry
NOT_CHECKED / PREREQUISITE_FAILED   another target    moves when that one is fixed
OUT_OF_SCOPE / CALLER               the caller        moves next invocation
OUT_OF_SCOPE / DATA_TRANSIENT       the deployment    moves when it changes
OUT_OF_SCOPE / DATA_PERMANENT       nobody            never
```

### Guarantees

- **Coverage and verdict are orthogonal**, enforced in the constructor. A gap cannot carry a
  verdict; a checked record cannot carry a skip reason.
- **Reasons come from a declared vocabulary.** Unregistered codes raise, a code meaning two
  things raises, a reason emitted under the wrong state raises.
- **Counts are derived from the records at read time and never stored**, so a count cannot
  drift from the rows it summarises.
- **`coverage_ratio` is computed over the mechanically checkable subset**, never over every
  target that exists, and returns `None` rather than `0.0` on an empty denominator.
- **Incomplete coverage never exits 0.**

### Two hardening passes, both before publication

**API attack — five findings, all now regression tests.**

- Declaring every target out of scope gave `evaluable == 0` and **exit 0**. A report that
  judged nothing read as green — this library's own thesis error, one level up. A test had
  asserted that behaviour as correct.
- A target that never became a record was invisible, and the report claimed perfect coverage.
  That is the `except Exception: pass` discovery failure the library exists for. Added
  `Report(expected=...)` and `missing()`; an absent row counts toward `evaluable`, because
  nothing ever judged whether it was in scope.
- Two records for one target were counted twice in silence. Now refused.
- `failing_verdicts` defaulted to `{"FAIL"}`, so a compliance tool emitting `NON_COMPLIANT`
  exited 0 on real failures. There is no safe default for another domain's vocabulary, so
  there is no default.
- `frozen=True` protected the binding, not the mapping behind it. `extra` and `evidence` are
  deep-frozen at construction.

**Taxonomy attack — 24 realistic cases across ML training, compliance, RAG evaluation, CI/CD
and production monitoring.** Twelve fit exactly one state, **five fit none**, four fit two,
three exposed limitations.

Two needed new states, and only two:

- `NOT_CHECKED / WAIVED` — a waived control *is* in scope and *is* applicable. Filing it under
  `OUT_OF_SCOPE / CALLER` says "not requested", which is false, and removes it from the
  denominator, which is where an accepted risk goes to hide. Requires `waived_by`.
- `NOT_CHECKED / PREREQUISITE_FAILED` — the checker did not fail, the data is not degenerate,
  the caller did ask. `CHECKER_FAILED` would send someone to debug a working parser. Requires
  `blocked_by`.

Three needed rules rather than states:

- **Could the caller have fixed it by changing the invocation?** Missing credentials or
  permissions — yes means `OUT_OF_SCOPE / CALLER`, no means `NOT_CHECKED / CHECKER_FAILED`.
- **Did the check produce a determination?** A crash or timeout after partial work is
  `CHECKER_FAILED`. Partial is not a result.
- **Could the checker observe the target at all?** A health check that cannot reach the
  service is `CHECKER_FAILED`, **never a failing verdict**. Unreachable is not unhealthy, and
  reporting it as failure is this library's own error in a different costume.

One was a verdict, not a state: conflicting evidence *is* a determination. Give it `CONFLICT`.

### Known limitations

Named in the README because the attack found them, not because they sound modest. The largest:
**a misconfigured check reports `CHECKED`.** This library accounts for what your checks report;
it cannot know whether a check is meaningful.

### Credit

The caller-versus-data ownership axis and the four-state split are Panagiotis Gkilis's, from
ML training-run validation. The fixed reason vocabulary, counts derived from rows, the
permanence split on `OUT_OF_SCOPE / DATA`, and the distinction between degenerate data and a
failed checker are Boris Teplitsky's, from infrastructure compliance.
