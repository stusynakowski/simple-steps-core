# Session states: where the object model stands

> **Superseded 2026-11-03** by [model.md §8](../model.md#8-states-in-a-session); its decisions S1–S7 are SS1–SS7 in [decisions.md](../decisions.md). Kept as background: where it differs, the newer page holds.

> Review, 2026-11-03, at `d69b5f1`. Every "today" below was run, not read:
> two scripts drove one workflow through each kind of edit and printed every
> step's state, stale reason and values. The rules this is measured against
> are [core-asks/model.md §M7](../core-asks/model.md#m7-an-interactive-session-editing-steps-and-what-changes-downstream).
> Nothing here is built yet: it lists what holds, what doesn't, and the
> decisions to make before code changes.

## 1. The objects, as they are

```
Kernel ── catalog (tools, resource types) ── resources
  └─ Workflow: steps in order
       └─ Step: a name, an expression, problems
            └─ Output: data · lineage (#v…) · row numbers (#<step>) · a state per cell
```

- A **step's expression** is what it does. Its **spec** is the saved form.
  Core already gives every step a **spec id** (K20, `workflow.identity()`):
  a hash of its expression, its tool's code, its resources' settings and the
  spec ids of the steps it reads. It never involves data.
- A **step's output** holds the values of its last run, and a **data
  version**: a hash of those values.
- A step's **state** rolls up its problems and its cells' states.

## 2. The states

**Step states** (core's, `Step.state`), decided in this order:

| State | When |
|---|---|
| `invalid` | the step has problems (its own, or an input that is `invalid` or empty), or a cell is `invalid` |
| `staged` | it has no output from a run: never run, or its output was dropped. An **empty step** (`k["x"] = None`) is `staged` too, holding `"empty"` |
| `stale` | it ran, and something changed since: its own expression ("updated args"), an input's data ("input p changed"), an input that is itself stale ("h is stale"), a tool's code, a resource |
| `failed` | it ran, and a cell `failed` or is `blocked` |
| `completed` | it ran, and nothing above holds (zero rows included) |

**Cell states:** `absent`, `known`, `maybe`, `pending`, `blocked`, `failed`,
`invalid`. Core has no `running` state; the app shows it while a run is going.

## 3. What core does today, edit by edit

Workflow: `p` (a DataFrame), `f = to_f[map](p)`, `h = hot[filter](p)`,
`r = risky[map](h)`, then all run.

| # | Edit | The edited step | Its readers | Holds M7? |
|---|---|---|---|---|
| 1 | declare everything | sources `completed`, the rest `staged` | — | ✓ |
| 2 | change `f`'s expression (valid) | `stale` (updated args), old values kept | — | ✓ |
| 3 | change `f`'s expression **back to exactly what it ran** | still `stale` (updated args) | — | ✗ see F1 |
| 4 | change `p`'s data | `completed` | `f`, `h` `stale` (input p changed); `r` `stale` (h is stale) | ✓ |
| 5 | assign `p` the identical data again | `completed` | stay `completed` (same data version) | ✓ |
| 6 | run `h` only | `completed` | `r` `stale` (input h changed) | ✓ |
| 7 | run `r` only, **while `h` is stale** | `r` `completed`, computed from `h`'s outdated values | — | ✗ see F3 |
| 8 | a tool raises on one row | `failed`; the run stops, naming the row | not run | ✓ |
| 9 | change `f` to read a step that doesn't exist | `invalid`, old values kept, stale reason still "updated args" | — | ✓ values; F4 |
| 10 | change `p` so a column a reader needs is gone | `completed` | `f`, `h`, `r` `invalid` at once, naming the column; **old values dropped** | ✓ at once; ✗ values, F2 |
| 11 | put the column back, data as the readers last ran on | `completed` | `staged`: their results are gone | ✗ see F2 |
| 12 | `k["x"] = None`, an empty step | `staged`, holding `"empty"` | a reader is `invalid` ("x is empty") | ✓; F5 |
| 13 | rename `h` to `hot_rows` | renamed, output kept | `r`'s expression rewritten to read `hot_rows` | ✓ |
| 14 | delete `h` while `r` reads it | refused, naming `r` | — | ✓; no delete-anyway (L43d) |

## 4. What doesn't hold

**F1. Stale is a flag, not a fact.** An edit sets "updated args", and only a
run clears it. A step whose expression returns to exactly what it ran is
still `stale`, though its values are right. Its spec id says so, but the spec
id isn't used for staleness.

**F2. An invalid reader loses its values, and can't get them back.** When an
upstream change makes a reader `invalid`, core re-stages it and drops what it
computed. M7 rule 1 says old values stay, marked, until a run replaces them.
When the upstream returns to what the reader ran on, the reader is `staged`,
so it re-runs for nothing. A step made `invalid` by its own edit (row 9)
keeps its values, so the two paths disagree.

**F3. A run can read a stale input and call itself completed.** Running one
step alone uses its input's outdated values, as designed ("a stale input
passes through", 009), and the result is `completed`. That it read a stale
input is kept only in hidden metadata (`read_stale`). M7 rule 4 says a step
never runs on a stale input. A user sees `completed` on values that may
already be wrong.

**F4. One state, two stories.** Row 9 is `invalid` and carries a stale reason
at the same time. The state says *can't run*; the reason says *needs a
re-run*. A step should say one thing.

**F5. An empty step needs running.** `needs_run()` lists an empty step as
`staged`, though running it does nothing until it has an expression.

**F6. A failed step isn't listed as needing a run.** After row 8, `needs_run()`
is empty. Re-running gives the same failure unless something changes, so
this may be right, but it isn't written down.

## 5. A simpler model to decide on

Every state is computed from facts core already has, never kept as a flag.

| State | Computed as |
|---|---|
| `invalid` | the step has problems now (checked at once on every edit, M7 rule 3) |
| `staged` | it has never produced an output |
| `completed` | its output was made with **its spec id now** and **each input's data version now** |
| `stale` | it has an output, but its spec id or an input's data version differs from what the output was made with. The reason says which: **"the step changed"** (spec id) or **"input p's data changed"** (data version) |
| `failed` | as `completed`, but some cells failed |

What follows from it:

- **F1 goes away:** an expression put back is `completed` again, because its
  spec id matches.
- **F2 goes away if values are never dropped:** an `invalid` step keeps its
  last output, shown as out of date. When the problem is fixed and nothing
  else changed, it is `completed` again without a re-run.
- **F3 is decided by one rule:** a step that read a stale input is itself
  `stale`, "read h while it was stale". It doesn't say `completed` until it
  has run on fresh inputs.
- **F4:** `invalid` wins and is the only state shown; the old values are
  still there, marked.
- The edit-equals-fresh law (L40c) becomes a direct consequence: the state
  depends only on what the workflow is now, not on the order of edits.

One case needs a ruling. A DataFrame assigned as a step has its data *as* its
spec: replacing it changes its spec id, so its readers are stale because "p
changed". A `source` tool's spec is its code and settings, and what it
returns is data. Both end in the same state, `stale`; only the reason differs.

## 6. Decisions to make

| | Decision | Recommended |
|---|---|---|
| S1 | Derive step states from spec ids and data versions instead of flags (§5) | yes |
| S2 | An `invalid` step keeps its last output, marked, and is `completed` again when fixed if nothing else changed (F2) | yes |
| S3 | A step run on a stale input is `stale` itself, saying which input (F3); or such a run is refused until the input runs | `stale`, with the reason |
| S4 | An `invalid` step shows no stale reason (F4) | yes |
| S5 | `needs_run()` leaves out empty steps (F5) and failed steps whose spec and inputs haven't changed (F6) | yes, both |
| S6 | Whether core has a `running` state, or it stays the app's | the app's |
| S7 | Delete-anyway, `k.remove(name, force=True)`, leaving each reader `invalid` and naming the deleted step (L43d) | as already decided (CA-6) |

Open from earlier, and tied to this page: saved picks into a source when its
rows move (row hashing, rewriting the pick's row number), and the three
contradictions about how rows pair (a child reading its parent's column;
rows with no partner blocked or refused; lineage showing row numbers as of
the run, or current ones).
