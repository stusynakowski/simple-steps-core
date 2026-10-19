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
- **N2: an explicit argument beats a column, with a warning.** `_d_apply` used
  to let the column win ("the unit wins"). Now a literal, `$ref` or `$res`
  bound on the step always reaches the tool. It is **not** refused, because
  pinning a value over a column can be deliberate. Instead the step carries a
  warning: *"city='NYC' overrides the 'city' column of 'readings' for every
  row; drop the argument to use the column"*. This is 008's first option,
  made visible. Only one existing test depended on the old rule.
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

## Phase 2 — design decisions

- **One record of failure: the ledger.** A cell whose tool raised is `failed`
  with its error, as before. A row whose input failed is `failed` too, with
  `attempts: 0` (the tool was never called), `error: "upstream cell a[1]
  failed"`, and a new ledger column **`cause`** holding the root
  (`a[1]: ValueError: boom`). The root travels through every verb: `map`,
  `group`, `expand` and `widen` block the row; `filter`, `select`, `drop`,
  `slice`, `rename`, `sort` and `distinct` carry it through still failed;
  `collapse` turns a group with a failed row into one failed cell.
- **Arguments:** a `$ref` argument that reads a step with any failed cell
  blocks every row of the step that receives it.
- **Typed gaps (R8):** a payload column with a missing or failed cell is
  nullable: `Int64`, `Float64` or `boolean`, else `object` holding `None`. A
  column with no gap is unchanged. `Output.values` reads gaps as `None`.
- **Missing is `None` (C14):** a tool receives `None`, never `NaN`/`pd.NA`.
  Rows are now iterated with `to_dict("records")`, not `iterrows`, which used
  to turn an `Int64` row into floats. A literal source's float column whose
  present values are all whole becomes `Int64` (pandas' `convert_dtypes`
  rule), so `pd.DataFrame({"n": [1, None, 3]})` is ints with a gap. A
  completed row's `None` given to a parameter that doesn't admit it is a
  declaration problem worded about `None`. A failed cell doesn't count as a
  missing value: its row is blocked instead.
- **Bad references (C10.1):** `wf["nope"]` returns a reference that doesn't
  resolve instead of raising. The step declares with the existing *"not an
  earlier step"* problem. Declaring the missing step later re-checks its
  readers, and a reader positioned before it gets *"'w' comes after 'a'; a
  step can only read earlier steps"*. Re-declaring a step can no longer
  quietly read a step after it.
- **Root cause (C10.4):** a step reading an invalid step says *"input 'a',
  which is invalid (root cause: a: input 'nope', which is not an earlier
  step)"*, and `wf.root_cause(step_id)` returns `(step, problem)`.
- **Fixing the root (C10.5):** running a step marks every step that already
  read it `stale`, and `stale` now outranks `failed` in `Step.status`.
- **Kept, not renamed:** a step with a declaration problem still has status
  **`invalid`**, not `failed` as C10's text suggests. `invalid` (can't run)
  and `failed` (ran, some cells failed) are different things, and the app
  already shows both. To be confirmed with the app.
- **Not yet:** `join`/`stack`/`zip_` don't carry failed cells (they combine
  frames, not ledgers). C10.6 (plans show `blocked`) waits for C8, and
  re-running only the failed rows is K15.

## Phase 3 — design decisions (saved format v2)

`to_dict` now writes **`"version": 2`**. Version 1 files still load; a file
from a newer core is refused with *"this core reads versions 1 to 2"* (K17).

- **C11, literals.** A bound argument or setting is a reference or a Python
  literal, checked at declaration (*"weight: a date isn't a literal; pass a
  str ('2024-01-01'), or make it a step"*). Literals save exactly, tagged where
  plain JSON would lose the type: `{"$tuple": […]}`, `{"$set": […]}` (sorted
  when sortable), `{"$dict": [[k, v], …]}` for non-string keys. A literal dict
  whose keys start with `$` also saves as `$dict`, so it can never be read
  back as a reference. Numpy numbers save as plain numbers.
- **C1, references everywhere.**
  - A `wf[…]` may appear in any setting (`select(columns=wf["cols"])`,
    `slice(start=wf["k"])`, `retry(times=wf["n"])`). It is a dependency (order
    and staleness), resolved at run, and type-checked once its step holds a
    value. It saves as `{"$ref": …}` inside `modifiers[].params`.
  - **Positional arguments after the input** bind to the tool's next free
    parameter: not given by keyword, and not supplied by the input (a known
    input column, or, when the input's columns aren't known, the first
    parameter). A `res[…]` binds to the first free parameter its declared
    type fits. Too many positionals is a `TypeError` naming the parameters.
  - **Shape follows the annotation:** a cell gives its value, a column a list
    (or `Series`), a row a dict (or list/`Series`), anything else the
    DataFrame. Untyped, the natural form. Before, anything but a cell was a
    DataFrame. A shape that can't convert (a column into `float`) is a
    declaration problem once the shape is known.
- **C2, tools in settings.** `sort(by=)`, `group(by=)`, `collapse(by=)` and
  `distinct(columns=)` take a tool computing a key per row. `select(columns=)`
  takes a predicate on column names, `rename(columns=)` a name mapping. Saved
  as `{"$tool": id}`, resolved from the run's tool table. A lambda runs, but
  `to_json` refuses it. `collapse(by=tool)` names the key column after the
  tool. `modifier_catalog()` shows these settings as `… | tool`.
- **C7, selection.** `rows`, `cols`, `Rows`, `Cols` and `SelectionError` are
  exported. `grid.rows(value)` still works as before: the indexer is callable.
  - `wf["p"][…]` takes the forms in 008's tables, in any order, one bracket
    or two. Each spelling normalizes at once to the saved form, so they
    compare and save identically.
  - On its own, a selection is a `select` step (K9: `select(rows=…,
    columns=…)`). A list of names stays a plain list; ranges and positions
    are dicts. Assigning a plain `wf["p"]` copies it (all columns).
  - As an argument it is applied, then converted by the parameter's type.
  - As a tool's input it is refused (*"make it its own step"*). The row-only
    amendment we discussed is **not** built; it's still a question for the app.
  - Bracket errors raise `SelectionError` as written. A missing column, a
    backwards range or a position past the end is a declaration problem
    when the step's data is known. Otherwise the step **fails at run** with
    the message (one failed cell), instead of raising.
  - Column names become `str` on every source and every run output; a
    collision fails.
  - `RESERVED_NAMES` (`wf res mod rows cols op join stack zip_`) are refused
    as tool, bound tool and resource type names. Declaring a step from a
    scope where `rows`/`cols` are anything else raises *"Rename your
    variable"*.
  - A row position over a `filter`/`expand`/`group`/`distinct`/`collapse`
    output warns that the rows may differ next run.

## Phase 4 — first slice: what an unrun step will produce

Built for a source that hasn't run, where some or all of the columns are
known but the rows are not.

- **Saying what a source produces.** Annotate the return,
  `-> Annotated[pd.DataFrame, Readings]` with a TypedDict or dataclass, for
  every column and its type (C5). Or state it on the step: `mod.expect(
  columns=["city"] | {"city": str}, more_columns=True, rows=…, min_rows=…,
  max_rows=…)` (C9.4). `expect` is an execution modifier: it changes nothing
  about how the tool runs, and saves column types as their names.
- **`Step.plan`** gives three axes, each with a `certainty`. `rows`: `exact`
  (count), `stated`, `bounded` (min/max), or `unknown`. `columns`: `exact`,
  `stated`, `bounded` (these names plus more), or `unknown`. `types`: a name
  per column, `any` when not known. Anything short of exact carries `because`
  and `resolve`. An unknown is never an empty list (K1's bug). A step that has
  run is exact on every axis. The staged grid has the planned columns, typed
  `object`, so nothing reads false dtypes from it.
- **`describe()` for an unrun source** reads from the plan: `source load ·
  columns city (str), n (int) + maybe more (stated) · rows unknown until it
  runs`. Other verbs' wording is unchanged.
- **Types flow downstream:** carried columns keep their types, a payload gets
  the tool's return type (an expand gets the element type of `list[T]`), and
  `rename` moves types with names. A tool parameter is checked against a
  staged input's declared type, so `shout(city: int)` over a source declaring
  `city: str` is refused at declaration, not after a run.
- **Promises are checked at run.** A source whose output doesn't match its
  declared schema fails (*"load declares columns city, n; it returned
  town"*). So does a step that breaks its `expect` (*"expected 12 rows, got
  2"*).
- **Contradictions at declaration:** `expect(rows=…)` against a verb that
  fixes the count (`collapse` → 1, `map` over n → n, `filter` over n → at most
  n). `expect()` with nothing in it is refused too.
- **Limit:** under `from __future__ import annotations`, a schema class must
  be importable from the tool's module. A class defined inside a function
  can't be resolved, and the source plans as `unknown`.

Still open in phase 4: C5 for record returns spread by `widen`; C8's planned
grid with known values and `pending`/`maybe` cell states; C9's tighter bounds
(`tuple[T, T]` → exactly 2n, join bounds) and the trailing marker row/column.

## Decision (owner, 2026-10-19): a failure stops the run

This **overrides part of C10**. C10 asked that `run_all` "runs everything
else" past a failure. The owner's rule is that a failed row stops the
workflow unless the step says it may fail.

- **`run_all` stops** at the first step with a failed cell the step didn't
  catch, raising `grid.StepFailed` (`step_id`, `cell`, `error`, `not_run`).
  Steps that already ran keep their results, and nothing after the failure
  runs, independent branches included. `wf.run(step)` on one step still
  records the failure without raising, so it can be inspected.
- **`mod.try_except(default=…, on=[…])`** is an execution modifier.
  - With `default=`, a caught failure completes the row with that value; the
    ledger keeps the error (`"caught ValueError: boom; used the default"`) and
    marks it `caught`. `default=None` is a value, not "no default".
  - Without `default=`, the row stays failed (`caught`) and the run continues.
    Rows that read it are blocked with its `cause`, as C10 describes, so
    C10's model holds for steps that opt in.
  - `on=` limits which exceptions are caught; it takes classes and saves
    their names. Others still stop the run.
  - Order is semantics: `[mod.try_except(…), mod.retry(times=2)]` retries
    first, then falls back.
- **A blocked row never stops the run by itself.** Its root either stopped it
  or was caught.
- **A failing source** is now a failed step (one failed cell) instead of an
  exception escaping `run`, so it follows the same rule.
- The ledger gains a **`caught`** column (seven in all).
- **To tell the app:** C10's "run_all runs everything else" now needs
  `mod.try_except()` on the steps that may fail.

## Status

| Ask | Phase | Status |
|---|---|---|
| K1, K2, K3, K4, K11, N1, N2, C13, O | 1 | **done** (2026-10-15); tests in `test_008_asks.py` |
| K5, K8, K13, C6 | 1b | **done** (2026-10-15) |
| C10, C14, R8 | 2 | **done** (2026-10-15), except combine verbs and C10.6 |
| C11, C1, C2, C7 (K9), K17 | 3 | **done** (2026-10-15) |
| C5 (sources), C9 (plans, `mod.expect`) | 4 | **first slice done** (2026-10-19) |
| C5 (widen), C8, C9 (bounds) | 4 | next |
| everything else | 5–7 | not started |

`scripts/core_asks.py`: **28 of 33 done** (from 3; C11, C1, C2 and C7 probes
added, K17's made real). Still open among the probed asks: K12 (5),
K14–K16 (6), K18 (7).

### Behaviour changes the app should know about

- An explicit argument now beats a same-named column, and the step gets a
  warning saying so (N2). Before, the column won silently.
- `mod.map(over="x")` raises (K5). Use `wf["x"]` (yours or `grid.wf`).
- An explicit `name=` that already exists is refused without `replace=True`
  (C13). `map`/`group`/`expand` accept `replace`.
- `timeout()` without `seconds=` and `retry()` without `times=` are
  declaration problems (O).
- A step downstream of an unrun tool-backed source is no longer invalid at
  declaration (K1). It is re-checked when the source runs.
- `wf["nope"]` no longer raises `KeyError`; the step that reads it is invalid (C10).
- The ledger has a seventh column, `cause` (C10).
- A failed row no longer turns an int column into `float64`: it's `Int64`, and
  `Output.values` reads the gap as `None` (R8, C14).
- A source column like `[1, None, 3]` is `Int64`, and tools get `None` for the
  gap. A tool typed `n: int` over it is refused at declaration (C14).
- Running a step marks the steps that already read it `stale` (C10.5).
- **Saved format v2** (phase 3): tagged literals, `$ref` in settings, `$tool`
  settings, selections on `$ref`. Version 1 still loads; the app's own parser
  of saved JSON needs the new tags.
- A non-literal argument (a `date`, an object) is a declaration problem (C11).
- A one-column `$ref` argument to an untyped parameter is now a list, not a
  DataFrame (C1).
- `wf["p"]["price"]` raises (C7); a variable named `rows` or `cols` in the
  declaring scope makes `wf[…] = …` raise.
- Integer column names become strings (C7).
- New `Step.plan`, `mod.expect`, and typed source schemas. A tool parameter is
  now checked against a staged input's declared types (C5). One test that
  asserted "no type check until the upstream runs" was updated.

Update this table, and [008-status.md](008-status.md) (the app's summary),
as each phase lands.
