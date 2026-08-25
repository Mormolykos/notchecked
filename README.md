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

## The eight states

| state | owner of the fix | does it ever move? |
|---|---|---|
| `CHECKED` | — | a determination was made; see the verdict |
| `NOT_CHECKED / DATA_DEGENERATE` | the data | the signal is there and unusable — accept the gap or supply better data |
| `NOT_CHECKED / CHECKER_FAILED` | your tooling | the checker raised, timed out, or could not observe — fix it |
| `NOT_CHECKED / WAIVED` | a named person | in scope, deliberately not evaluated, accepted — revisit at expiry |
| `NOT_CHECKED / PREREQUISITE_FAILED` | another target | something upstream failed first; fix that, then this becomes judgeable |
| `OUT_OF_SCOPE / CALLER` | the caller | not requested — pass the flag |
| `OUT_OF_SCOPE / DATA_TRANSIENT` | the deployment | changes when the deployment changes |
| `OUT_OF_SCOPE / DATA_PERMANENT` | nobody | no artifact of this kind can ever evidence it |

Two states that share a bucket give the reader a to-do they cannot action. Every split here
exists because two things that read identically in a report have opposite remediations — and
a test asserts that no two states share both an owner and a remediation.

The last two `NOT_CHECKED` states were added after the first draft was attacked with 24
realistic cases across ML training, compliance, RAG evaluation, CI/CD and production
monitoring. Twelve fit exactly one state, **five fit none**, four fit two. A **waiver** and a
**cascade** were the only two that needed new states; the rest needed rules or a verdict.

`WAIVED` requires `waived_by` and `PREREQUISITE_FAILED` requires `blocked_by`. An unowned
waiver is a silence with paperwork, and a cascade with no pointer to its cause is a dead end.

### Three tie-break rules

Four of the 24 cases fit **two** states. These decide them, and none of them needed a new
state:

**Could the caller have fixed it by changing the invocation?** Missing credentials, missing
permissions, an unset flag — yes means `OUT_OF_SCOPE / CALLER`, no means
`NOT_CHECKED / CHECKER_FAILED`.

**Did the check produce a determination?** A crash halfway through, a timeout after partial
work — no determination is `CHECKER_FAILED`, however far it got. Partial is not a result.

**Could the checker observe the target at all?** A health check that cannot reach the service
is `CHECKER_FAILED`, **never a failing verdict**. Unreachable is not unhealthy, and reporting
it as failure is this library's own error wearing a different costume.

### Coverage and verdict are orthogonal

`CHECKED` is **not** a result. It says a determination was made, not what it was. The verdict
vocabulary belongs to the domain — `PASS`/`WARN`/`FAIL`, `COMPLIANT`/`NON_COMPLIANT` — and
hangs off `CHECKED` rather than sitting beside the not-checked states.

Collapsing the two axes is failure 1 above. The constructor enforces the separation: a gap
cannot carry a verdict, and a checked record cannot carry a skip reason.

### Scope: this starts after the unit exists

**Nothing here governs how something becomes a checkable unit.** In a linter a row is a check
somebody wrote, so the unit precedes the schema. In compliance the unit is the hard part — a
framework is prose, and turning it into requirements is a judgment call: one paragraph can
yield three, three can collapse into one. Ingest owns that mapping. This library governs what
happens to a row once it *is* a row, and it must not be read as if the rows arrive by
themselves.

### Two denominators, and only one is yours to quote

```
total       every target considered, in scope or not
evaluable   the targets that were mechanically checkable at all
```

A percentage over `total` is a claim about the framework you named. A percentage over
`evaluable` is a claim about your own evidence. `coverage_ratio` computes only the second.

When nothing was evaluable it returns `None`, not `0.0` — an absence of coverage is not a
coverage of zero, and the two must not render alike.

### Rows for the checkable subset, a count for the rest

A framework document is hundreds of pages of which a few paragraphs concern anything an
artifact can evidence. One `DATA_PERMANENT` row each makes the report mostly noise, and the
signal drowns in its own denominator. So the excluded corpus can be a single counted rule:

```python
report.exclude(rule="no-artifact-evidence", count=412,
               permanent_wrt="terraform-plan",
               describes="framework prose no generated artifact can evidence")
```

What keeps this a measurement rather than a shrug: the count **cannot be stated without the
rule that produced it**, and it lands in `total` — so excluding 412 of 415 shows an exclusion
ratio of 99%, not a flattering silence. Use a row when a reader would want the target named;
use a rule when the excluded set is large and uniform.

### Permanence is relative to a target, never absolute

`OUT_OF_SCOPE / DATA_PERMANENT` requires `permanent_wrt`, and the constructor refuses without
it. "Nobody, never" is not a property of a control — it is a property of pairing that control
with a kind of artifact. A Kubernetes control is permanently out of scope only while the
target has no Kubernetes; change the target and it becomes a row.

Unqualified, two reports on the same framework disagree and both are correct, which makes the
state useless to the audience it was added for.

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

report = Report(
    tool="trainproof",
    vocabulary=vocab,
    failing_verdicts=frozenset({"FAIL"}),          # no default - see below
    expected={"loss-shape", "grad-spike", "lr", "import"},
)
report.add(Record("loss-shape", Coverage.CHECKED, verdict="PASS"))
report.add(Record("grad-spike", Coverage.NOT_CHECKED_DATA_DEGENERATE, reason="no_scale"))
report.add(Record("lr", Coverage.OUT_OF_SCOPE_DATA_PERMANENT, reason="no_signal"))
report.add(Record("import", Coverage.OUT_OF_SCOPE_CALLER, reason="not_requested"))

print(report.render())
raise SystemExit(report.exit_code)
```

```
trainproof: 1/2 evaluable targets checked, 2 out of scope (50% of all targets)
  PASS: 1
  not checked: 3
    [NOT_CHECKED/DATA_DEGENERATE] grad-spike: no_scale  -> the signal is present and unusable; accept the gap or supply data that carries scale
    [OUT_OF_SCOPE/DATA_PERMANENT] lr: no_signal  -> no artifact of this kind can ever evidence it; excluded by design, not pending
    [OUT_OF_SCOPE/CALLER] import: not_requested  -> not requested; pass the flag or select the check
```

### Two arguments with no defaults, on purpose

**`failing_verdicts`.** Verdicts are your domain's vocabulary. An earlier draft
defaulted to `{"FAIL"}`, which meant a compliance tool emitting `NON_COMPLIANT`
exited **0 on real failures**. There is no safe guess, so there is no default —
reading `exit_code` with undeclared verdicts raises.

**`expected`.** A report cannot notice a row nobody wrote. Declaring the target
set up front is what lets `missing()` report targets that never arrived — the
discovery-loop failure above. Omit it and the report says so out loud rather than
implying the set was complete.

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

Named because the attack found them, not because they sound modest.

**A misconfigured check reports `CHECKED`.** If your threshold is wrong, the check runs,
produces a meaningless number, and this library records a clean determination. It accounts
for what your checks *report*; it cannot know whether a check is meaningful. This is the
largest limitation and nothing here mitigates it.

**No sub-target granularity.** A checker that sampled 10% of a target reports `CHECKED` for
the whole target. If partial evaluation matters to you, split the target.

**No history.** A single run. A target `CHECKED` yesterday and `CHECKER_FAILED` today produces
two independent reports and this library will not notice the flake.

**Evidence freshness is invisible.** A check that ran successfully against a six-month-old
artifact is `CHECKED`. Put the timestamp in `evidence` or `context`; the coverage state will
not carry it for you.

**`expected` is only as good as you are.** It closes the vanished-target hole, but nothing
validates that the declared target set is itself complete or free of duplicates.

**Conflicting evidence is a verdict, not a state.** Two artifacts disagreeing about one
target *is* a determination — give it a verdict like `CONFLICT`. It is not a coverage gap.

## Status

`0.1.0`. The six states are settled between two independent domains; the API is not, and may
change before `1.0`.

## Credit

The four-state split and the **caller-versus-data ownership axis** are Panagiotis Gkilis's,
from ML training-run validation.

The **fixed reason vocabulary**, **counts derived from rows rather than computed on top of
them**, and the **permanence split** on `OUT_OF_SCOPE / DATA` are **Boris Teplitsky**'s
(`New_Technician_7041`), from infrastructure compliance — along with the observation that
separates `NOT_CHECKED / DATA_DEGENERATE` from `NOT_CHECKED / CHECKER_FAILED`.

Three further corrections are his, and each one changed the schema rather than the prose:

- **the taxonomy starts after the unit exists**, and saying so is scope, not an omission;
- **permanence must name its reference target** — `permanent_wrt` is required because
  unqualified "never" cannot be reconciled between two reports;
- **rows for the checkable subset, one count for the rest**, so the excluded corpus is
  disclosed as a counted rule instead of drowning the report.

He also confirmed, from the side that would have to defend it in an audit, that `WAIVED` is a
coverage state and not a verdict, and that it has to stay in the denominator — which is the
reason it exists.

Neither of us would have found the whole shape alone; two unrelated domains is what makes it
a primitive rather than one person's preference.

## Reference implementations

**None yet.** The four failures above are real and are regression tests here, but no shipped
tool has adopted this schema, so nothing has yet proved the API survives contact with one.

[trainproof](https://github.com/Mormolykos/trainproof) — the deterministic linter for ML
training runs that failures 1 and 2 came from — is the intended first adopter, additively:
the typed field will ship alongside its existing `skipped` map rather than replacing it. That
work is not done, and it is the next thing that will find holes in this design.

---

## Who built this, and what he sells

Built and maintained by **Panagiotis (Panos) Gkilis** — solo founder, BedVibe Studios.
This library is MIT and always will be. These are not:

- **Available for hire.** Remote ML/AI engineering — training pipelines, evaluation
  methodology, retrieval systems, inference infrastructure. What I have shipped and
  measured: **[ai.bedvibe.studio/work](https://ai.bedvibe.studio/work/)**
- **Licensed emotional speech datasets** — multilingual, studio-recorded with cleared
  and paid voice actors, six emotional states, commercial licence:
  **[tts.bedvibe.studio/datasets](https://tts.bedvibe.studio/datasets/)**
- **BedVibe TTS** — a 730M-parameter expressive text-to-speech model and platform,
  live and in production: **[tts.bedvibe.studio](https://tts.bedvibe.studio/)**

If this library saved you time, the most useful thing you can do costs nothing:
**link to it from wherever you write about it.** A followed link is worth more than
a star, and it is the one thing an author of free software cannot give himself.
