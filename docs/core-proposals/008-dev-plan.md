# 008 — Dev plan

How core builds [008-core-changes.md](008-core-changes.md), the app's single list
of asks. Progress is tracked by `python scripts/core_asks.py`, which runs one
probe per ask. It is the app's script, plus core probes for N1, N2, C13, O and
C6. Each ask also gets a test in `tests/unit/test_008_asks.py`, so a fix can't
regress after the app adopts it.

Baseline at `a799d0e`: **3 of 23 probes done** (K6, K7, K10).

## Phases

The phases follow 008's "Suggested order for core". Within a phase, small and
independent items go first, so each lands with its own tests and probe.

| Phase | Asks | Why together | Saved format |
|---|---|---|---|
| **1. Wrong results, small** | K3, K4, K11, N2, C13, N1, O, K2, K1 | Each is a refusal or a local rule change in `check` / wiring. K1 and K2 share the "unknown, not empty" idea. | unchanged |
| **1b. Small consistency** | K5, K8, K13, C6 | Short, independent, and they remove app shims | unchanged |
| **2. Failure as state** | C10, C14, R8 | One model for "this cell has no value": failed cells and missing values keep the column's type, and flow downstream without calling tools | outputs only |
| **3. Saved-format v2** | C11, C1, C2, C7 (K9), K17 | Each changes how a value, setting or selection is written. One `version: 2` bump; v1 keeps loading | **v2** |
| **4. Planning** | C5, then C8, C9 | Typed columns first; the planned grid and partial plans build on them | plan API only |
| **5. Boundary** | C3, K12, M, P, N, C12 | Let the app import only `grid` and drop its shims | unchanged |
| **6. Features** | K14, K15, K16, C4, C15, C16, R3/R4, R5 | Independent, each behind its own API | R4/R5 add sections |
| **7. Later** | K18, R7, R9 | Need the async engine (K18) or are post-MVP | — |

## Phase 1 — design decisions

- **K3, K4, K11 are refusals at wiring time,** raised from `Operation._wire` /
  `_add` with the 008 wording. K3 stays a refusal until calls can nest (P0).
- **N2: an explicit argument beats a column.** That is 008's preferred answer.
  `_d_apply` used to let the column win ("the unit wins"). Now a literal,
  `$ref` or `$res` bound on the step always reaches the tool. This changes
  behaviour, but no existing test depended on the old rule.
- **C13:** a verb that writes a payload column (`map`, `group`, `expand`) with
  an **explicit** `name=` the input already has is a declaration problem,
  unless the step says `replace=True`. `replace` becomes a setting of those
  verbs. **Narrowed:** the *default* payload (`value`) overwriting the previous
  step's default `value` is how `map` over `map` chains (and how a list cell
  expands in place), so it is a **warning** on the step, not a problem. `widen`
  is excluded: spreading a record's fields over same-named columns is its
  documented job.
- **N1:** `_value_fits` treated `X | Y` (a `types.UnionType`) as a plain type.
  Unions now fit when any member fits.
- **O:** a required modifier setting with no default (`retry(times=)`,
  `timeout(seconds=)`) is a declaration problem, found from the modifier's own
  signature. `check(operation)` already works without a workflow, so the
  formula bar can call it directly.
- **K2:** `infer_verb` decides from the signature first. A two-parameter tool
  whose first parameter is named `acc`, `accumulator`, `memo` or `carry` is a
  reducer whether or not the columns are known. Columns only break a tie the
  signature can't settle. **Narrowed:** a reducer with another first-parameter
  name is still recognised only once its input's columns are known. Before
  that it infers `map`, as before, so name the accumulator or write the verb.
- **K1:** a step's predicted columns can be **open**: a tool-backed source
  that hasn't run, and anything that carries its columns through. A column
  check against an open set is deferred, not failed. When a step runs, the
  steps downstream are re-checked as well as re-staged, so `picked` turns
  valid once `readings` has run and fails only if the column is really missing.
  C5 (typed sources) will close the set at declaration later. `run_all` skips
  a step that turns invalid during the run (its deferred check failed) and
  carries on, rather than raising.
- **K5:** `mod.<verb>(over="name")` raises; the unbound `grid.wf["name"]` (C6)
  is the spelling for "a step named this in whichever workflow". JSON keeps
  string ids.
- **K8:** a modifier is callable on a reference when its verb has a default
  tool (`select`, `drop`, `widen`, `slice`, `rename`, `sort`, `distinct`,
  `source`, `expand`, `collapse`). `map`, `filter` and `group` refuse.
- **K13:** `modifier_catalog()` entries gain `takes_tool` (`true`, `false`,
  `"optional"`, or `null` for execution modifiers) and `default_tool`.

## Status

| Ask | Phase | Status |
|---|---|---|
| K1, K2, K3, K4, K11, N1, N2, C13, O | 1 | **done** (2026-10-15); tests in `test_008_asks.py` |
| K5, K8, K13, C6 | 1b | **done** (2026-10-15) |
| C10, C14, R8 | 2 | next |
| everything else | 3–7 | not started |

`scripts/core_asks.py`: **16 of 23 done** (from 3). Still open among the
probed asks: K9 (phase 3), K12 (5), K14–K16 (6), K17 (3), K18 (7).

### Behaviour changes the app should know about

- An explicit argument now beats a same-named column (N2). Before, the column won.
- `mod.map(over="x")` raises (K5). Use `wf["x"]` (yours or `grid.wf`).
- An explicit `name=` that already exists is refused without `replace=True`
  (C13). `map`/`group`/`expand` accept `replace`.
- `timeout()` without `seconds=` and `retry()` without `times=` are
  declaration problems (O).
- A step downstream of an unrun tool-backed source is no longer invalid at
  declaration (K1). It is re-checked when the source runs.

Update this table, and the summary in [007-status.md](007-status.md)'s
successor, as each phase lands.
