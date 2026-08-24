# Changelog

All notable changes to `notchecked` are recorded here.

## 0.1.0 — unreleased

Nothing is tagged and nothing is on PyPI. The API is not frozen: the eight states are
settled between two independent domains, the Python surface around them is not.

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
