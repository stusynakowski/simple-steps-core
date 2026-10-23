# UI context: what the front end needs from simple-steps-core

> **For the people (and agents) planning the interactive UI.** 2026-10-21.
> One page on what core gives a UI to render and act on. Every example below
> was produced by running core on 2026-10-21. Design detail lives in
> [core-proposals/009-step-output-model.md](core-proposals/009-step-output-model.md);
> the full list of changes for the app's backend is
> [core-proposals/008-status.md](core-proposals/008-status.md).
>
> **Version note:** everything here through 009 is in **`b9f66d5`**. The 010
> additions (complete cell `inputs`, per-cell staleness, `Output.uncaught`)
> are described in [core-proposals/010-status.md](core-proposals/010-status.md).

## 1. The model in five rules

1. **A workflow is an ordered list of steps.** Each step is a formula, and
   its output is a grid: a DataFrame.
2. **A step stores only its own results.** A `map` over `readings` stores one
   column (`value`), not `readings` plus `value`. To show inputs beside
   results, the UI joins them **by row id** at display time; nothing is saved
   twice.
3. **Row ids are the links.** `map`, `filter`, `sort`, `select` and the like
   keep the input row's id; `expand` derives `1.0`, `1.1` from parent row `1`.
   A result cell always points back to its input row through its id.
4. **Every cell has a state.** An output is **`data`, `states`, `meta`**:
   `states` is the same shape as `data`, one state per cell (`known`,
   `maybe`, `pending`, `blocked`, `failed`, `invalid`), and `meta["notes"]`
   holds the error or cause **only for the rows that have one**.
   `print(output)` shows it all as one grid.
5. **Every step exists before it runs.** A declared step is *staged*: core
   already knows its columns, types and (when it can) its row count, and
   says what it doesn't know and why. A UI can show, select and wire steps
   that have never run.

## 2. The formula language

The same text in the formula bar and in Python:

| Written | Means |
|---|---|
| `wf["readings"]` | a step in this workflow |
| `res["llm"]` | a resource (an LLM client, a database), supplied when the workflow runs |
| anything else | a Python literal (`3`, `"x"`, `[1, 2]`, `(1, 2)`, `{"k": 1}`) |
| `score(wf["r"])` | run `score` on `r`, orchestration chosen automatically (**auto**) |
| `score[mod.map()](wf["r"], weight=2)` | run `score` once per row (orchestration written) |
| `wf["p"][1:3][cols["name":"price"]]` | rows 1–2, columns `name` through `price` (a selection; see §5) |
| `zip_(wf["r"], wf["s"])`, `join(…)`, `stack(…)` | combine grids |

- `Operation.to_source()` prints any step back as its canonical formula
  (`score[mod.auto()](wf["r"])`), so the formula bar can always show text for
  a step built some other way.
- **The formula bar must parse with its own grammar** (`ast`, whitelisted
  names), never `eval` user text.

## 3. What a step gives the UI

For `s = score(wf["r"])`, where `r` is a source that loads a CSV:

| What | Where | Example |
|---|---|---|
| Formula | `step.operation.to_source()` | `score[mod.auto()](wf["r"])` |
| Status | `step.status` | `staged` → `completed` / `failed` / `stale` / `invalid` |
| One-line summary | `step.describe()` | `map score · one cell per upstream row (auto, for now: 'n' comes from the input's columns, so apply it per row; adds breaker(after=5))` |
| Problems (can't run) | `step.problems` | `("input 'nope', which is not an earlier step",)` |
| Warnings (can run) | `step.warnings` | `("city='NYC' overrides the 'city' column of 'readings' for every row; …",)` |
| Results | `step.output.data` | `{'value': [1.5, 3.0, None]}`, index `[0, 1, 2]` |
| Per-cell state | `step.output.states` (same shape as data); `output.row_states` (worst per row) | `known`, `failed`, … |
| Notes, only where needed | `step.output.notes` (row id → note) | see below |
| Plan (before and after running) | `step.plan` | see below |
| What auto chose | `step.output.meta["auto"]` | `{"verb": "map", "reason": "…; adds breaker(after=5)", "provisional": false}` |
| Version / what it read | `meta["version"]`, `meta["read"]` | `"b018e0d52f15"`, `{"r": "47b66401b2ea"}` |
| Saved form | `wf.to_dict()` / `to_session_json()` | `{"tool_id": "score", "input": {"$ref": "r"}, "modifiers": [{"kind": "auto", "params": {}}]}` |

**Printed** (`print(output)`), which is also the shape to draw:

```
<Output zip · 3 row(s) × 3 col(s), 1 failed>
  city  n  value    state                                   note
0   SF  1    1.5    known
1  NYC  2    3.0    known
2   LA -1   <NA>  blocked  blocked by s[2]: ValueError: negative
```

**The note for a row** (`output.notes[2]`), stored only for rows that have
something to say:

```json
{"error": "ValueError: negative", "caught": true}                                  // its tool raised
{"error": "upstream cell s[2] failed", "cause": "s[2]: ValueError: negative"}      // blocked: jump to the cause
{"error": "not run: stopped after 5 failures in a row (ValueError: bad key)"}      // the breaker stopped it
```

- `caught: true` means the step chose to let the failure through
  (`mod.try_except`); a caught failure **with a default** is a `known` cell
  whose note keeps the original error.
- Each cell has its own state: in a `zip_`, a row can have `city` and `n`
  known and `value` blocked.
- A `filter` lists the rows it rejected in `meta["excluded"]`; a row whose
  predicate raised stays, `failed`.

**The plan of a staged step** (`step.plan`, here `s` before `r` has run):

```json
{"rows":    {"certainty": "unknown",
             "because": "its input's row count isn't known yet",
             "resolve": ["run the steps before it", "state it on the step: mod.expect(rows=…)"]},
 "columns": {"certainty": "exact", "names": ["value"]},
 "types":   {"value": "float"}}
```

Each axis is `exact`, `stated` (the author said so with `mod.expect`),
`bounded` (a range, or "these columns plus more") or `unknown`. Anything
short of exact carries `because` and `resolve`. That's the text for tooltips
and "how do I fix this" affordances. A step that has run is `exact` on every
axis.

## 3a. Known unknowns: `wf.preview(step)` and `wf.cell(step, row, column)`

**A known unknown is information, and the UI shows it.** Known columns with an
unknown row count, some columns known "plus maybe more", a filter that keeps
"at most 4 rows": each comes back as something to draw.

`wf.preview("r")` for an unrun source that declares its columns:

```json
{"step": "r", "status": "staged",
 "summary": "source load · columns city (str), n (int) · rows unknown until it runs",
 "formula": "load[mod.source()](path=\"r.csv\")",
 "columns": [{"name": "city", "type": "str"}, {"name": "n", "type": "int"}],
 "rows": [],
 "row_count": {"certainty": "unknown",
               "because": "load is a source that hasn't run; its rows come from its data",
               "resolve": ["run load", "state it on the step: mod.expect(rows=…)"]},
 "markers": [{"kind": "rows", "certainty": "unknown",
              "text": "‹rows unknown — load is a source that hasn't run; its rows come from its data›",
              "because": "…", "resolve": ["run load", "state it on the step: mod.expect(rows=…)"]}],
 "window": {"start": 0, "stop": 0, "of": 0}}
```

- **Draw the header from `columns`** (names and types), **the body from
  `rows`**, and **each marker in place:** a `rows` marker as a trailing
  placeholder row, a `columns` marker (`"‹+ maybe more columns›"`) as a
  trailing placeholder column. Show `because` on hover, and offer `resolve`
  as actions.
- A step **after** an unrun source names what it's waiting on: *"‹rows unknown
  — its input 'r' doesn't know its row count yet›"*, resolve *"run 'r'"*.
- **Planned rows:** a `map` over known rows shows them as `pending`, each
  cell with its `type`. A `filter` shows its input rows as `maybe`, plus the
  marker *"‹0–4 rows — filter keeps at most the 4 rows it reads›"*.
- **Run rows:** each row and cell has a `state`: `known` (with `value`),
  `stale` (the **old value**, still shown), `failed` (`error`) or `blocked`
  (`cause`, the cell where the failure started).
- An **invalid** step has one marker: *"‹can't run — input 'nope', which is
  not an earlier step›"*, with the root cause.
- `rows=(start, stop)` gives a window, for paging.

`wf.cell("s", 1, "value")`, for a click, works on any step:

| When | Returns |
|---|---|
| `s` hasn't run, rows unknown | `{"state": "unknown", "type": "float", "because": "its input 'r' doesn't know its row count yet", "resolve": ["run 'r'", …]}`, i.e. row 1, *if it exists* |
| after the run | `{"state": "known", "value": 3.0, "type": "float", "id": 1, "inputs": [{"step": "r", "id": 1, "columns": ["n"], "argument": "n", "state": "known", "values": {"n": 2}}]}` |
| a failed cell | `{"state": "failed", "error": "ValueError: negative", …}` |
| a blocked cell | `{"state": "blocked", "cause": "s[1]: ValueError: negative", …}` |
| no such row / column | `{"state": "missing", "because": "row 9 of 's', which has 2 rows (0–1)"}` |

`inputs` names **every input cell** the result came from, one entry per
binding: the `step`, the row `id` (or `rows` for several), the `columns`
read, the `argument` they were bound to (`None` when a step copies the cell
without a tool), the cells' `state` (a cell state, e.g. `known`, `failed`),
and their `values`. An argument reference appears too
(`{"step": "w", "id": 0, "columns": ["w"], "argument": "weight"}`), as do
setting references (`"argument": "select.columns"`) and resources. A `zip_`
cell lists only the input that supplied its column. Nothing is stored for
this; it's worked out from row ids and the formula.

## 4. Step statuses: what to show

| `status` | Meaning | Data | Suggested UI |
|---|---|---|---|
| `staged` | declared, not run | none yet; `plan` | planned columns and types; unknowns marked, with `because`/`resolve` |
| `invalid` | can't run (a declaration problem) | none | `problems[0]`; it names the root cause when the problem is upstream |
| `completed` | ran; every row completed | yes | the grid |
| `failed` | ran; some rows failed | yes, failed cells empty | failed cells marked; `error`/`cause` on hover |
| `stale` | ran, but something it read has changed since | **yes, the old data** | the old grid, dimmed or marked stale, with "re-run" |

- **Stale data is never deleted.** It stays readable until the step re-runs.
  Staleness comes from data versions: re-running an earlier step that gives
  the same result leaves later steps fresh.
- **Running stops on an uncaught failure.** `run_all()` raises `StepFailed`
  (`step_id`, `cell`, `error`, `not_run`); steps already run keep their
  results. `wf.run(step)` on a single step records the failure without
  raising.

## 5. Selecting rows, columns and cells

- Any selection of a step is a step, run or not:
  `wf["cell"] = wf["s"][0][cols["value"]]`. Rows are integer positions
  (negative from the end); columns are `cols[…]` by name, name range
  (inclusive), position, position range (half-open) or a list.
- As an argument, a selection arrives in the shape the parameter's type asks
  for: one cell is its value, one column a `list`, a row a `dict`, a block a
  DataFrame. A shape that can't convert is refused at declaration.
- `rows` and `cols` are reserved names.
- Every spelling of a selection saves identically, e.g.
  `{"$ref": "p", "rows": {"start": 1, "stop": 3}, "columns": {"from": "name", "to": "price"}}`.

### Row ids (`#`) and column names as values

- **`#` is the row number: always 0…n-1 down every step's grid,** in order,
  even after a `filter`, `sort` or `expand`. Draw it as the first column
  (`output.view()` and `wf.preview()` rows include it). It's what a user
  clicks and references: `rows[…]`, `cols["#"]` and `wf.cell(step, row, …)`
  all count by `#`.
- Each row's link to the input row it came from is kept internally (the
  `id` in preview rows and cell inputs). The UI never needs to show it. A
  cell's inputs name their row by the input step's `#` (`"row": 2`).
- **Columns are numbered the same way:** each column in `wf.preview()` has a
  `#` (0…m-1, left to right), and `wf.cell()` returns `column_number`. That's
  what `cols[1]` and `cols[0:3]` select. Show it so position references are
  readable. Names stay the safer reference: positions follow the current
  column order.
- `cols["#"]` selects the row numbers like a column: `wf["p"][cols["#"]]`,
  `wf["p"][1:3][cols[["#", "n"]]]` (gives `#` 1, 2), `select(columns=["#", "city"])`.
- **`wf["p"].header`** is the step's column names, as a value (a list
  argument), or as a step: one column, `name`.
- **Loading a table:** a table with its own `#` column is refused (*"'#' is
  reserved for row ids; rename or remove that column"*). A predefined index
  becomes an ordinary column (its name, or `index`).

## 6. Auto, and what to show about it

- A formula with no orchestration (`score(wf["r"])`) is **auto**. Core picks
  the orchestration from the tool and the data (map, filter, collapse,
  expand, table), adds defaults (a breaker that stops a row-wise step after 5
  failures in a row), and saves it as `mod.auto()`. Re-decided at each run.
- **Show what auto chose.** Use `meta["auto"]`'s `verb` and `reason`, with
  `provisional: true` before the run ("for now") and `false` after ("from the
  data"). Offer "choose the orchestration myself", which writes e.g.
  `mod.map()` (core then adds nothing).
- Overriding one default: `score[mod.auto(), mod.breaker(after=None)](…)`.
- A setting, `grid.settings.implicit_auto`, can turn implicit auto off; then
  the formula must state `mod.auto()` or a verb.

## 7. Catalogs that drive palettes and forms

| Call | Gives |
|---|---|
| `grid.catalog()` | every tool: `params` (name, type, required, default, choices, nullable, description), `returns`, `typed`, `open`, `tags`, `description` |
| `grid.modifier_catalog()` | every modifier: `class` (shape / execution), `row_rule`, `settings` (with types; `… \| tool` where a tool can go), `takes_tool`, `default_tool` |
| `grid.resource_catalog()` | resource types: settings, bound tools, bases |
| `grid.check_modifier(kind, params)`, `operation.check()` | problems while typing, with no workflow |

Modifiers today: shape `source map filter select drop widen slice rename sort
distinct group expand collapse sweep table auto`; execution `retry timeout
expect try_except breaker`.

## 8. Built vs planned

| Need | Status | Until then |
|---|---|---|
| Step status, results, per-cell states and notes, plan, `describe`, auto's choice, versions | **built** | — |
| Selections as steps; selections as arguments | **built** | — |
| `wf.preview(step)`: the grid to draw, with known unknowns as markers | **built** | — |
| `wf.cell(step, row, column)`: a cell's value or what's expected, with state, type, error, cause and every input cell | **built** | — |
| Cell states `known` `stale` `failed` `blocked` `pending` `maybe` `unknown` `missing` | **built** | — |
| Whether an output stops a run: `output.uncaught`, `output.stops_run` | **built** (010) | — |
| A cell of a row that may not exist yet ("row 2, if it exists") | **built** for `wf.cell` (`state: unknown`) | — |
| Selection *steps* over rows that may not exist yet | planned (009 §3) | the step is checked when it runs |
| `step.references()`: status of each reference in a formula (`ok`, `stale`, `has failures`, `staged`, `missing`, `not loaded`) | **planned** (009 §5) | `meta["read"]` vs `wf.version(...)` |
| Per-cell staleness (edit one input row → only its cells stale): `wf.stale_rows(step)` | **built** (010) for row-aligned steps; others stale as a whole | — |
| Re-run only failed rows; progress callback during a run | open (K15, K14) | re-run the step |

## 9. Gaps the UI will hit today

1. **`join` and `stack` don't carry failures yet; `zip_` does.** A `zip_`
   cell that failed in its own step is `blocked` in the zip, with the cause.
   A `join` or `stack` still marks every cell `known`, so for those read a
   cell's state from the step that produced its column (`wf.cell` on that
   step).
2. **No rows before an unrun source runs** — by design: the row count isn't
   known. `wf.preview` gives the columns and types plus a `rows` marker to
   draw as a placeholder row ("‹rows unknown — …›"); `wf.cell` answers a click
   on any row as `unknown`, with the type and how to resolve it.
3. **`describe()` for staged selections and combines is terse**
   (`select identity · one cell per upstream row`). Build the UI from `plan`,
   not from `describe()` text.
4. Expanded rows have string ids (`"1.0"`); other steps mostly have integers.

## 10. Decisions that constrain the UI

- Steps store results only; inputs are shown beside them by row id.
- `zip_` never drops rows silently: an unmatched row fails the step.
- Staleness comes from data versions; stale data stays visible.
- Cells run independently. A failure stops the run unless the step uses
  `mod.try_except`. Auto adds a 5-in-a-row breaker to row-wise steps.
- A clicked cell is saved as a **position** (spreadsheet-like), with a
  planned "pin this record" by id. (Recommended, not final.)

## 11. Questions for UI planning

1. How does the grid show a step's results beside its inputs? A joined
   view by row id, inputs greyed?
2. How are the seven cell states shown, especially `stale` (old value) versus
   `pending` (planned type) versus `unknown`?
3. Where do `because`/`resolve` appear: tooltip, side panel, inline?
4. What happens on `StepFailed`: a banner naming the cell, with "jump to cause"
   and "let failures through" (adds `mod.try_except`)?
5. When auto picks an orchestration, how prominent is the choice, and how
   does the user switch to a written one?
6. Should clicking a cell of an unrun step create a selection step, an
   argument reference, or just inspect?
