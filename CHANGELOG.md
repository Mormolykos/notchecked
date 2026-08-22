# Changelog

All notable changes to `notchecked` are recorded here.

## 0.1.0 — unreleased

Nothing is tagged and nothing is on PyPI. The API is not frozen: the eight states are
settled between two independent domains, the Python surface around them is not.

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
