# notchecked

**Coverage accounting for validators.** Three states, not two: what was checked, what could
not be checked, and what was never in scope — six once you account for who owns the gap and
whether it can ever change.

A validator that reports a verdict without reporting its coverage is asserting something it
did not measure. Silence reads as green.

MIT. No dependencies. `pip install notchecked`

---

## The problem, four times

The same bug, in four unrelated systems. None of these was found by a test. Each was found
by a real input, after the tool had been shipped.

**1. ML training logs.** A run whose loss was exactly `0.0` on every step returned **PASS**.
Every loss-shape check is guarded against dividing by zero, so all of them skipped silently —
and the report then listed those same skipped checks as having *run*. A run that learned
nothing passed, along with the list of checks that had cleared it.

**2. The same tool, one loop earlier.** A directory walk discovered candidate logs inside
`except Exception: pass`. A file that raised while being *found* never became a candidate and
never appeared in the report at all: plainly visible on disk, absent from the output,
indistinguishable from a file that passed.

**3. Infrastructure compliance.** A framework document is mostly prose that no generated
artifact can satisfy or violate. Reporting against the framework name makes everything
unevaluated look identical to everything that passed, and the 90% that was never in scope
disappears from the output entirely.

**4. Retrieval-grounded answering.** An evaluation harness recorded model refusals under a
failure type asserting an answer the model never gave; scored ten refusals as **correct**,
because the expected phrase appeared inside the sentence explaining what could not be
determined; and missed eight correct answers because its negative pattern required a comma.
One absent value, wrong in both directions, inside the tool being used to judge the
hypothesis.

Four domains, one primitive: **absence of evidence rendered as a positive result.**

## The six states

| state | owner of the fix | does it ever move? |
|---|---|---|
| `CHECKED` | — | a determination was made; see the verdict |
| `NOT_CHECKED / DATA_DEGENERATE` | the data | the signal is there and unusable — accept the gap or supply better data |
| `NOT_CHECKED / CHECKER_FAILED` | your tooling | the checker raised, timed out, or lacked a dependency — fix it |
| `OUT_OF_SCOPE / CALLER` | the caller | not requested — pass the flag |
| `OUT_OF_SCOPE / DATA_TRANSIENT` | the deployment | changes when the deployment changes |
| `OUT_OF_SCOPE / DATA_PERMANENT` | nobody | no artifact of this kind can ever evidence it |

Two states that share a bucket give the reader a to-do they cannot action. Every split here
exists because two things that read identically in a report have opposite remediations.

### Coverage and verdict are orthogonal

`CHECKED` is **not** a result. It says a determination was made, not what it was. The verdict
vocabulary belongs to the domain — `PASS`/`WARN`/`FAIL`, `COMPLIANT`/`NON_COMPLIANT` — and
hangs off `CHECKED` rather than sitting beside the not-checked states.

Collapsing the two axes is failure 1 above. The constructor enforces the separation: a gap
cannot carry a verdict, and a checked record cannot carry a skip reason.

### Two denominators, and only one is yours to quote

```
total       every target considered, in scope or not
evaluable   the targets that were mechanically checkable at all
```

A percentage over `total` is a claim about the framework you named. A percentage over
`evaluable` is a claim about your own evidence. `coverage_ratio` computes only the second.

When nothing was evaluable it returns `None`, not `0.0` — an absence of coverage is not a
coverage of zero, and the two must not render alike.

## Usage

```python
from notchecked import Coverage, Reason, Record, Report, Vocabulary

vocab = Vocabulary([
    Reason("no_scale", Coverage.NOT_CHECKED_DATA_DEGENERATE,
           "median gradient norm is zero - no scale to measure a spike against"),
    Reason("no_signal", Coverage.OUT_OF_SCOPE_DATA_PERMANENT,
           "this log format never carries the column"),
    Reason("not_requested", Coverage.OUT_OF_SCOPE_CALLER,
           "the caller did not ask for this check"),
])

report = Report(tool="trainproof", vocabulary=vocab)
report.add(Record("loss-shape", Coverage.CHECKED, verdict="PASS"))
report.add(Record("grad-spike", Coverage.NOT_CHECKED_DATA_DEGENERATE, reason="no_scale"))
report.add(Record("lr", Coverage.OUT_OF_SCOPE_DATA_PERMANENT, reason="no_signal"))
report.add(Record("import", Coverage.OUT_OF_SCOPE_CALLER, reason="not_requested"))

print(report.render())
raise SystemExit(report.exit_code)
```

```
trainproof: 1/2 evaluable targets checked, 2 out of scope
  PASS: 1
  not checked: 3
    [NOT_CHECKED/DATA_DEGENERATE] grad-spike: no_scale  -> the signal is present and unusable; accept the gap or supply data that carries scale
    [OUT_OF_SCOPE/DATA_PERMANENT] lr: no_signal  -> no artifact of this kind can ever evidence it; excluded by design, not pending
    [OUT_OF_SCOPE/CALLER] import: not_requested  -> not requested; pass the flag or select the check
```

`report.to_json()` emits the same thing for CI, under schema `notchecked/1`.

### Exit codes, separate from severity on purpose

```
0   everything evaluable was evaluated, and nothing failed
1   something was checked and failed
2   nothing failed, but coverage is incomplete
```

**Incomplete coverage never returns 0.** A tool that cannot tell "your thing is broken" from
"I could not judge your thing" is lying to CI quietly.

## Design rules

- **The record is written by the check, at the moment it decides**, carrying its own reason —
  never reconstructed afterwards from what is missing. Provenance as a byproduct rather than
  a later reconstruction.
- **Reasons come from a declared vocabulary, not free text.** A reason string is readable by
  a human and useless to CI. An unregistered code raises; a code that means two things
  raises; a reason emitted under the wrong state raises.
- **Counts are derived from the records at read time and never stored.** A count held beside
  the rows it summarises can drift from them, and nothing catches it.
- **No dependencies, no model calls, no confidence scores.** Every decision traces to the
  check that made it.

## Limits

This is a schema and an accounting layer. It cannot tell you whether your *checks* are any
good — a tool with one trivial check and full coverage will report full coverage. It does not
know what your targets are, and it will happily account for a target list that is itself
incomplete. It makes coverage claims auditable; it does not make them true.

## Status

`0.1.0`. The six states are settled between two independent domains; the API is not, and may
change before `1.0`.

## Credit

The four-state split and the **caller-versus-data ownership axis** are Panagiotis Gkilis's,
from ML training-run validation.

The **fixed reason vocabulary**, **counts derived from rows rather than computed on top of
them**, and the **permanence split** on `OUT_OF_SCOPE / DATA` are Boris Teplitsky's, from
infrastructure compliance — along with the observation that separates
`NOT_CHECKED / DATA_DEGENERATE` from `NOT_CHECKED / CHECKER_FAILED`.

Neither of us would have found the whole shape alone; two unrelated domains is what makes it
a primitive rather than one person's preference.

## Reference implementations

- [trainproof](https://github.com/Mormolykos/trainproof) — deterministic linter for ML
  training runs. First adopter, additively: the typed field ships alongside the existing
  `skipped` map rather than replacing it.
