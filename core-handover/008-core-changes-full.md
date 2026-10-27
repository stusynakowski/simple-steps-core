# 008 — Every change the app needs from simple-steps-core

> **For `simple-steps-core`.** Status: proposal. Every "Today" line was
> produced by **running** core at `a799d0e` on 2026-10-15. The pin is now
> `9a86a0d`; see [Status at 9a86a0d](#status-at-9a86a0d) for what that closed,
> and C17–C19 for what it opened.
>
> **This is the only list.** It merges every open item from the app's
> proposals 001–006 (now in [`archive/`](archive/)) and the core asks in
> `docs/dev_plan/117` and `200`, and adds sixteen new asks, C1–C16. Old IDs
> are kept, so core's replies still match. The last section maps the old IDs
> and each `SHIM(core §X)` tag in the app to an entry here.

## How to check progress

```bash
python scripts/core_asks.py      # one probe per ask: OPEN / DONE
```

The K items, plus core's probes for the C/N/O items (marked "(core)"). C8,
C15, C16, C17–C19, R3–R9 have no probe yet. Each "Done when" line is written
so it can become one.

## Status at 9a86a0d

Core replied in its own `docs/core-proposals/008-status.md`. Its claims were
checked by **running** core at `9a86a0d` on 2026-10-19, not by reading that
reply:

- `python external/simple-steps-core/scripts/core_asks.py` → **34/38 done**.
  Open: K14, K15, K16, K18.
- The app's own probes (one per shim, through `/api/run`, `/api/operations`,
  `/api/infer_verb`, `/api/format_formula`), and
  `examples/all_orchestrations/check.py` → 63/63 steps match core's run.
  (Since replaced by the examples' `runme.py` scripts, which check the same
  workflows against Python twins: `python src/SIMPLE_STEPS/examples/runme.py`.)

**Shims deleted from `core_bridge.py`**, each replaced by core's function:

| Tag | Replaced by |
|---|---|
| `SHIM(core §A)`, `§B`, `§E`, `§J` (docstring parser, annotation readers, `x-form`) | `grid.tool_entry()`: `description`, `type`, `choices`, `returns`, even for a tool taking a `DataFrame` |
| `SHIM(core §K)` (whole-table tools on the legacy orchestrator) | `mod.table()`; the UI's `dataframe` mode and `f(df: pd.DataFrame)` tools run under it |
| `SHIM(core §L)` (a value from another step on the legacy path) | a `$ref` argument; a column for a `list` parameter is `{"$ref": s, "columns": {"names": [c]}}` |
| `SHIM(core §M)` (`inferable_method`) | `grid.infer_verb(DB.lookup, …)` |
| `SHIM(core §N)` (`AUTO`, its catalog entry, `resolve_auto`) | `mod.auto()`; saved as `auto`, the run's verb read from `output.meta["auto"]` |
| `SHIM(core §O)` (`modifier_settings_problem`) | `grid.check_modifier(kind, params)` |
| reads of `grid.BUILTIN_TOOLS`, `SHAPE_VERBS`, `MODIFIERS`, `PAYLOAD` | `builtin_tools()`, `shape_verbs()`, `modifier_catalog()`, `payload_column()` |
| `REGISTRY.freeze()` only | plus `grid.freeze()` |

**What the app's users see change:** modifier errors are in core's words
(*"retry needs times= — it has no default, so a step without it cannot
run"*); `mod.auto()` is saved as `auto`; table tools follow core's C14 and
C11 rules (a gapped whole-number column is `Int64`, so `10.0` reads `10`;
column names are strings); a table tool must return a DataFrame. `merge_steps`
now annotates `right_data: pd.DataFrame | str`, because core rightly refuses
a table for a `str` parameter.

**Still on the app's side, by choice:**

- `operation_formula.format_parts`, not `Operation.to_source()` (P). The step
  editor's parts keep what was *written*: a bracket-less inferred form and
  positional resources. `to_source()` canonicalises both away.
- Steps holding one value (a dict, a list, a number) are passed to a tool as
  that value, as a literal, not as a `$ref` — see C19.

**Core's eight decisions for the app to confirm** are in
[009-decisions-to-confirm.md](009-decisions-to-confirm.md), each with what core
does (run, not quoted), what it changes in the app, and a recommendation.
Running them found C20 below, and that K2 is only half fixed.

## Status at b9f66d5

The app was moved to `b9f66d5` (core 009: results-only steps, `Output(data,
states, meta)`, row ids, strict `zip_`, data-hash versions, implicit
`mod.auto()`, `wf.preview` / `wf.cell`) on 2026-10-21. Plan:
[`dev_plan/124`](../dev_plan/124-core-009-integration.md).

- **`SHIM(core §C21)` rewritten**, not deleted: `core_bridge.uncaught_failed`
  now reads `row_states` and `notes` (the ledger is gone). Checked by running
  core: a breaker-stopped row is `failed` with no `cause` and counts as
  uncaught; `try_except` (written after the verb) sets `caught: True`; a
  blocked row has a `cause` and doesn't count.

New asks, each found by running core at `b9f66d5`:

| # | Ask | Evidence |
|---|---|---|
| **C22** | `zip_` refuses two grids that share a column name, instead of keeping the first | `zip_(readings, double_n[mod.map(name="n")](readings))` completed with columns `['city', 'n']` and `n = [1, 0, 2]`: the doubled `[2, 0, 4]` were dropped without a message — the silent drop 009 decision 2 rules out |
| **C23** | `collapse(by=…)` naming a column the input lacks is refused at declaration | `sum_totals[mod.collapse(by="city")](wf["totals"])` over a map's result (no `city`) declared fine, then raised a bare pandas `KeyError: 'city'` from `collapse_` at run |
| **C24** | `wf.cell(...)["inputs"][].state` uses cell states | it returns step statuses (`"completed"`), not `"known"` as 009 §4 shows |
| **C25** | Per-cell staleness (009 step 7) | app spec 014's out-of-date marks are per step until then |
| **C26** | `009-status.md` and `ui-context.md` say `wf.preview` / `wf.cell` are uncommitted | both are in `b9f66d5` |
| **C27** | `wf.cell(...)["inputs"]` lists every input cell: argument references too, and the column(s) read, not only the main input's row | for `scale[mod.map()](wf["r"], weight=wf["w"][0][cols["w"]])`, `wf.cell("s", 1, "value")["inputs"]` is `[{"step": "r", "id": 1}]` — no `w` row 0, no column `n`. The app reconstructs both from the saved formula meanwhile (spec 014 REQ-VIS-058) |

## Status at 523ad1d

Core answered [`010-asks-at-b9f66d5.md`](010-asks-at-b9f66d5.md) in its own
`docs/core-proposals/010-status.md`. Checked by **running** core at `523ad1d`
on 2026-10-21 (not by reading the reply), and the app moved to it the same
day, with the owner's confirmation:

| Ask | Checked |
|---|---|
| C21 | `output.uncaught` → `[1]`, `output.stops_run` → `True` for one failing row. **`SHIM(core §C21)` deleted**; metrics read `len(output.uncaught)` |
| C22 | `zip_(r, d)` sharing `n` is `invalid`: *"zip_: 'n' is in both 'r' and 'd'; rename one (mod.map(name=…) or mod.rename)"*. New bad example `zip_shares_a_column` |
| C23 | *"collapse groups by 'city', which 's' does not have (it has value)"* at declaration |
| C24, C27 | `inputs` lists both bindings, each with `columns`, `argument`, a cell `state` (`known`) and `values` |
| C25 | editing row 1's `n` → `wf.stale_rows("s")` = `[1]`; editing a column the step doesn't read leaves it fresh |
| C26 | done — though core's `010-status.md` itself still says "uncommitted"; it's in `523ad1d` |

Also new in core: editing a step that has run keeps its output, stale, with a
reason (`meta["stale_reason"]`: `updated args`, …), and `wf.arg_changes(step)`
says what it was computed with. The app uses these from dev_plan/124 phase 2.

## At 86170a3 (2026-10-23)

The app moved to `86170a3` (`#` row numbers, column numbers, `cols["#"]`,
`wf["p"].header`) with the owner. Phase 2 runs every core step in one core
`Workflow` per session and saves it whole between uses with
`to_session_dict()` / `Workflow.from_dict()` (`kernels.py`, then named `session_workflow.py`) —
checked by running: restored, nothing recomputes, row links and staleness
hold. New asks, each found by running core at `86170a3`:

| # | Ask | Evidence |
|---|---|---|
| **C28** | `wf["p"].header[k]` either picks one column name or is refused | `wf["p"].header[1]` on columns `city, n` returns **both** names (`{'name': ['city', 'n']}`): the `[1]` is ignored, silently. `header[cols["n"]]` is refused, which is fine |
| **C29** | `to_session_dict()` on an image-array payload gives a clear refusal, or saves it | the `swatches` step (one numpy array per row) raises `ValueError: can only convert an array of size 1 to a Python scalar` from `_encode_output` — a crash, not a message |
| **C30** | A session export that saves what it can: per step, so one unsaveable payload doesn't lose every output | a `Figure` payload is refused by design (*"Object payloads persist only as handles or as something with a to_json"*), and that refusal fails the whole `to_session_dict()`. The app then saves the steps only (`to_dict()`), so every step of that workflow re-runs after a restore. Ask: e.g. `to_session_dict(skip_unsaveable=True)` returning which steps it skipped |
| **C31** | A `mod.table()` tool that returns a list is refused or wrapped, not stored as `None` | `colnames[mod.table()](wf["r"])` returning `['city', 'n', 'm']` stored `{'value': [None]}`; returning a one-column DataFrame works |
| **C32** | A pluggable payload store for the session export (core's own P1: `Output.ref` + a store backend, with codecs) | replaces C29/C30. The app wants outputs as files beside the workflow — parquet for tables, PNG / Plotly JSON for objects, named by version — and a loader on `Workflow.from_dict(…, outputs=loader)` (`docs/system_design/11-data-flow-and-storage.md`) |
| **C33** | A grid `Session` with per-workflow **kernels** (core's P5), in the app's words: a **session** is a user's area (as core's `Session` already is); a **kernel** is one workflow, live — its `Workflow`, outputs, versions; a **kernel manager** keeps some live and puts others away. A kernel offers: `Operation.from_source(text)` (the inverse of `to_source`), run a step with its never-run inputs first, step-ran / stale callbacks, save / restore through C32 | the app built this in `src/SIMPLE_STEPS/kernels.py` (`Kernel`) on public core API; core refuses "reads 'r', which has not run. Run 'r' first", has no parser (no `ast` in the package), and no change notifications — so every front end (the app, a CLI REPL, a notebook) rebuilds them |

## The goal: the app imports core's grid and nothing else

The app should use only `simple_steps_core.grid`'s public functions. Each
`SHIM(core §X)` in `src/SIMPLE_STEPS/core_bridge.py` marks a place where that
boundary leaks. An ask's **Removes** line names the shim it deletes. The rule
for adding one is unchanged: shim it in `core_bridge.py`, tag it, and add the
gap here with what you ran and what it returned.

---

## Summary

| ID | Ask | Priority | Removes from the app |
|---|---|---|---|
| **K1** | An unrun source's columns are unknown, not empty | **1: wrong result** | blocks workflow-level sessions |
| **K2** | Verb inference doesn't depend on run state | **1: wrong result** | — |
| **K3** | Refuse an operation used as an input | **1: wrong result** | the formula's inline-op check |
| **N2** | A literal sharing a column's name is silently ignored | **1: wrong result** | — |
| **K4** | Refuse `over` given twice | **1: wrong result** | — |
| **C10** | A bad reference or a failure is a state that flows downstream without calling tools; failed cells keep their type | **1: wrong result** | R8; one failed row blocking a whole step |
| **C11** | Literals are Python literals and round-trip exactly; anything else refused at declaration | **1: wrong result** | silent tuple → list, int keys → str |
| **C13** | An output column never silently replaces an input column | **1: wrong result** | — |
| **C14** | Missing values are `None`, never `NaN`; nullability is part of the type | **1: wrong result** | — |
| **C1** | Every value slot takes a literal or a reference, in the right shape | **2: UI** | `SHIM(core §L)` remainder |
| **C7** | Excel-style selection: bare ints are rows, `cols[…]` is columns, any order (`wf["p"][1:5][cols["a":"c"]]`); column names are `str`, rows are `int` (includes K9) | **2: UI** | two-step cell/block picks; the `step1["col"]` legacy path |
| **C5** | A tool's return type predicts the step's columns | **2: UI** | deferred checks; untyped staging |
| **C8** | Reactive, typed staging: known cells show values, tool cells show their type, re-planned on every change | **2: UI** | `useStagedPreview.ts` (the client-side guess) |
| **C9** | Partial plans: rows, columns and types each `exact` / `bounded` / `unknown`, with why and how to resolve; `mod.expect(…)` | **2: UI** | — |
| **C2** | Shape settings can be functions (tools) | **2: UI** | per-verb helper tools |
| **C6** | Export an unbound `wf`: "a step in this workflow" | **2: UI** | — |
| **C3** | A public surface made of functions | **2: encapsulation** | reads of `grid.<GLOBAL>` |
| **O** | A missing required modifier setting passes declaration | **2: UI** | `SHIM(core §O)` |
| **K12** | A whole-table verb | **2: UI** | `SHIM(core §K)` |
| **N1** | A `dict \| None` resource setting refuses every value | **2: UI** | — |
| **C12** | Discourage `**kwargs` (warn; refuse in strict mode); keep refusing `*args` | 3: cleanup | — |
| **C15** | Tool versions and a `deterministic` flag decide when results are reused | 3: feature | — |
| **C16** | Stable row ids, guaranteed per verb (`expand` derives from the parent) | 3: feature | — |
| **C17** | `mod.table()` binds the parameter typed `DataFrame`, not the first | 2: UI (new at 9a86a0d) | `SHIM(core §C17)`, the last legacy `dataframe` fallback |
| **C18** | `catalog()` description is the docstring's first paragraph, not first line | 3: cleanup (new) | `SHIM(core §C18)` |
| **C19** | A one-cell step passed to a `dict`-typed parameter is its value | 3: consistency (new) | inlining one-value steps as literals |
| **C20** | A selection as a tool's input is silently ignored in JSON | **1: wrong result** (new) | — |
| **C21** | Whether a step's failures stop a run is public | 3: boundary (new) | `SHIM(core §C21)`, `core_bridge.uncaught_failed` |
| **N** | A written `mod.auto()`, resolved at run | 3: editor | `SHIM(core §N)` |
| **P** | `Operation.to_source()` | 3: editor | replaces `format_parts` |
| **M** | `infer_verb` reads a bound method's `self` as a column | 3: cleanup | `SHIM(core §M)` |
| **K13** | `modifier_catalog()` says which verbs take a tool | 3: cleanup | hard-coded verb lists in 2 files |
| **K5** | In Python, `over` takes only a `StepRef` | 3: consistency | — |
| **K8** | Tool-less modifiers callable on a reference | 3: consistency | `identity[…]` spelling |
| **R3/R4** | `Secret` settings; loaded resources with overrides | 3: resources | — |
| **R5** | Unknown top-level sections survive a round trip | 3: resources | — |
| **K14** | Progress callback on `run` | 3: feature | — |
| **K15** | Re-run only the failed rows | 3: feature | — |
| **K16** | A pluggable results store | 3: feature | the app's result store |
| **C4** | Registry can be cleared and re-filled in-process | 3: feature | blocks kernel restart (200 B2) |
| **K11** | Refuse `over=[a, b]` with a clear message (it crashes) | 4: later | — |
| **K17** | Keep JSON v1 loadable across P0 | 4: later | — |
| **K18** | Enforce `timeout` | 4: later | the "not enforced" UI note |
| **R7** | A standard handle for media | 4: later | the app's media store |
| **R8** | Failed rows turn `int64` columns into `float64` (fixed by C10) | 4: later | — |
| **R9** | Stages: a group of steps that runs as one | 4: later | — |

### Done (no action)

| Was | What core built |
|---|---|
| K6, K7 | `tool[mod.source()](**args)` and `tool[mod.sweep(…)]()` declare an `Operation` |
| K10 (003 §L, 001 §F) | `$ref` in keyword arguments; serialised, tracked for stale/rename/remove |
| K11's request (001 §G) | `join`, `stack`, `zip_` combine steps |
| R1, R2, defined R3/R4, Q1 | `res["x"]` → `{"$res": "x"}`; `@bound_tool`; type-checked; caller owns live objects |
| 001 §A/B (select/project) | `select(columns=…)`, `slice(...)`; rows half is in C7 |
| 003 §A, §E, §J | `grid.catalog()` already gives per-param `description`, `choices`, `type`, and `returns: "DataFrame"`. **App-side:** read it instead of the engine registry (see C3) |

### Not asked (the engine is retiring)

003 §C (`AppConfig` fields), §D (`register_tool(type=…)` annotation), §G
(`'step'` type), §H (duplicate ids) concern the engine. They still reproduce
at `a799d0e`, but the app is moving off the engine (C3), so they go away rather
than get fixed. 002's open decision (new verbs vs. restriction on `over`) was
settled by core's `select`/`slice` verbs.

---

## Priority 1 — wrong results that look right

These come first, whatever else is planned. The app's agent proposes exactly
these shapes, and the user can't tell the result is wrong.

### K1. An unrun source's columns are unknown, not empty

**Today:** declared invalid; after `run_all` gives `{'value': [None]}`.

```python
wf["readings"] = to_rows.bind(data=DATA)[mod.source()]      # tool-backed, not run yet
wf["scored"]   = scale[mod.map(name="score")](wf["readings"])
wf["picked"]   = mod.select(over=wf["scored"], columns=["city", "score"])
# picked: invalid — "select names 'city', which the input does not have (it has score)"
wf.run_all()   # readings and scored run; picked stays invalid -> {'value': [None]}
```

The probe needs a **tool-backed** source; an assigned DataFrame doesn't
reproduce it.

**Ask:** treat an unrun source's columns as unknown, so column checks against
it are deferred, not failed. When a step runs, re-check the staged steps that
read it. A source that declares its schema (core's D2) removes the case.

**Done when:** `picked` gives `{'city': ['SF','NYC','SF','LA'], 'score': [10, 20, 30, 20]}`.

### K2. Verb inference doesn't depend on run state

**Today:** `add_n(wf["readings"])` infers `collapse` when `readings` holds
data, and `map` when it is an unrun tool-backed source.

**Ask:** infer from the signature (`(acc, x)` collapses, `-> bool` filters,
`-> list` expands). If the columns are needed, mark the step as waiting for
them. Never fall back to a different verb.

**Done when:** both declare `collapse`.

### K3. Refuse an operation used as an input

**Today:** accepted; runs as a one-cell source, reports `completed`, gives
`{'value': [None]}`.

```python
inner = op("identity")[mod.select(columns=["n"])](wf["readings"])
wf["x"] = scale[mod.map()](inner)
```

**Ask:** raise *"an operation can't be an input yet; make it its own step and
pass wf[…]"* until calls can nest (P0). When P0 lands, this becomes nesting.

**Done when:** the call raises.

### N2. An explicit literal is ignored when a column has the same name

**Today:** `tag[mod.map()](wf["r"], city="NYC")` over a grid with a `city`
column gives `['SF','NYC','SF','LA']`. Over a grid without `city` it gives
`['NYC', …]`.

**Ask:** an explicit argument always beats a column bind. Or, at least, refuse
it at declaration.

**Done when:** the call gives `['NYC','NYC','NYC','NYC']`, or declares a problem.

### K4. Refuse `over` given twice

**Today:** `scale[mod.map(over=wf["a"])](wf["b"])` is accepted; the call wins
silently.

**Done when:** the call raises.

---

### C10. Failure is a state that flows downstream, cheaply

**Rule:** a step may reference only steps **before** it. Anything else, or any
failure upstream, puts the step in a failed state that passes down to
everything that reads it, without calling any tool.

**Today:**

```python
wf["a"] = scale[mod.map()](wf["nope"])              # KeyError: "no step 'nope'; defined so far: ['r']"
wf["a"] = scale[mod.map()](wf["r"], weight=wf["w"])  # KeyError too, even if w is defined on the next line
```

The order rule holds, but as an exception at the reference, so the step
can't be declared at all. Neither can anything after it, and a saved
workflow whose step was deleted can't be loaded and shown. At the cell level,
a failed row turns into `NaN`, the column becomes `float`, and the next step
is **refused entirely**: *"plus1() declares value: int, but 'a' has value as
float64"*. One bad row stops every row downstream.

**Ask:**

1. **Bad references are a failed step, not an exception.** `wf["nope"]`
   gives a reference that doesn't resolve, and the step declares with status
   `failed` and the problem *"no earlier step 'nope'"*. A reference to a step
   defined later fails with *"'w' comes after 'a'; a step can only read earlier
   steps"*, and stays failed until the steps are reordered.
2. **Failed steps pass through.** Any step whose input or argument
   references a failed step is itself `failed`, with *"upstream 'a' failed: no
   earlier step 'nope'"*. This is worked out at declaration, in one pass over
   the steps, and calls no tool.
3. **Failed cells pass through, row by row.**
   - A cell whose tool raised is a **failed cell**: its own state, keeping
     the column's type (no `NaN`, no `int` → `float`; this replaces R8).
   - A `map` row that reads a failed cell fails **without calling the tool**:
     *"upstream cell a[1] failed"*. The other rows run normally.
   - An **argument** is passed whole (C1), so if it holds any failed cell,
     every row that receives it fails without calling the tool. A selection
     (C7) that leaves the failed cell out is unaffected.
   - `collapse` over a column with a failed cell gives a failed cell.
     `filter`, `sort` and `select` carry failed rows through unchanged.
4. **The root cause is kept.** Every failed step and cell records where the
   failure started (`a[1]: ValueError: boom`), so the UI can jump to it and
   show how far it spread.
5. **Fixing the root clears the rest.** When the root is fixed or re-run,
   everything it blocked becomes `stale` and can re-run; with K15, only the
   failed rows re-run.
6. **C8/C9 plans show it:** a cell downstream of a failure is planned as
   `blocked`, not `pending`.

**Done when:**
- `wf["a"] = scale[mod.map()](wf["nope"])` declares with status `failed`,
  and `wf["c"] = scale[mod.map()](wf["a"])` declares as `failed` too, naming
  `nope`;
- a forward reference declares `failed`, with the "comes after" message;
- `risky` failing on 1 of 3 rows keeps the column `int`, and `plus1` over it
  runs 2 rows, fails 1 without calling `plus1` (a call counter reads 2), and
  names `a[1]` as the cause;
- `run_all` on a workflow with a failed step runs everything else and calls
  no tool for a blocked cell.

### C11. Literals are Python literals, saved exactly

**Rule:** a tool argument that isn't `wf[…]` or `res[…]` is a literal, and a
literal is anything **Python's literal syntax** can write: `int`, `float`,
`str`, `bool`, `None`, and `list`, `tuple`, `dict` and `set` built from those.
That's what `ast.literal_eval` accepts (excluding `bytes` and `complex`). A
literal saves and reloads as **exactly** the same value and type.

**Today** (saved with `to_json`, reloaded with `from_json`):

| Literal | Result |
|---|---|
| `3`, `2.5`, `"x"`, `True`, `None`, `[1, 2]`, `{"k": [1, {"z": None}]}` | same ✓ |
| `(1, 2)` | **comes back as `[1, 2]`**, silently |
| `{1: "one"}` | **comes back as `{"1": "one"}`**, silently |
| `{1, 2}` | accepted at declaration, then **`to_json` raises** `TypeError` |
| `date(2024, 1, 1)`, `Decimal("1.5")`, `b"raw"` | accepted at declaration, then **`to_json` raises** |

**Ask:**

1. **Exact round trip** for the literal types, using tagged JSON where plain
   JSON loses the type: `{"$tuple": [1, 2]}`, `{"$set": [1, 2]}`, and
   `{"$dict": [[1, "one"]]}` for a dict with non-string keys. Plain JSON stays
   plain (a `list` is a list, a `dict` with `str` keys is an object).
2. **Anything else is refused at declaration, not at save:** *"weight: a
   date isn't a literal; pass a str ('2024-01-01') or make it a step"*. This
   covers `date`, `Decimal`, `bytes`, objects, and functions (a function
   belongs in C2's tool slot).
3. **The formula bar matches:** a formula's literals are exactly what this
   rule allows. A call like `date(2024, 1, 1)` inside a formula isn't a
   literal, and is refused by the grammar.

**Done when:** every literal type above survives `to_json` → `from_json` with
the same value and type, and the non-literals are refused when the step is
declared.

### C13. An output column never silently replaces an input column

**Today:** `dbl[mod.map(name="n")](wf["r"])` over a grid that already has `n`
declares with no problem and replaces `n`: `{'n': [2, 4, 6]}`. The input
values are gone, and nothing said so. This is the same class of bug as N2.

**Ask:** naming an output after an existing column is a declaration problem,
*"map writes 'n', which r already has; choose another name, or say
replace=True"*, unless the step says `replace=True`. With `replace=True`, the
C8 plan shows the column as replaced.

**Done when:** the call above is refused, and `mod.map(name="n", replace=True)`
declares and replaces it.

### C14. Missing values are part of the type: `T | None`

**Today:**
- A column holding `None` becomes `float64` with `NaN`
  (`[1, None, 3]` → `[1.0, nan, 3.0]`).
- A tool taking `n: int` over it is refused with *"declares n: int, but 'r'
  has n as float64"*. The message talks about `float64`, not about the `None`.
- A tool taking `n: int | None` over it **receives `NaN`, not `None`**. It
  returns `NaN` for that row, so a tool written correctly for `None` gets a
  wrong result.

**Ask:**
1. **Missing is `None`, never `NaN`.** A missing value reaches a tool as
   `None`, and an `int` column with a missing value stays an `int` column
   (nullable), as C10 asks for failed cells.
2. **Nullability is part of a column's type.** The C8 plan shows `int?` (or
   `int | None`) for a column that can hold `None`.
3. **Checks are about `None`.** A nullable column given to an `int` parameter
   is a declaration problem: *"r.n can be None, but inc() takes n: int; accept
   int | None, or filter the Nones first"*. Given to `int | None`, it's fine.

**Done when:** `inc_opt(n: int | None)` over `[1, None, 3]` receives `None` on
row 1 and returns `[2, 1, 4]` as `int`; `inc(n: int)` over it gets the
`None`-worded problem.

---

## Priority 2 — needed for the UI and the boundary

### C1. Every value slot takes a literal or a reference, in the right shape

The formula rule: **`wf["…"]` is a table, `res["…"]` is a resource, anything
else is a literal.** Core implements it in tool keyword arguments only.

**Today:**

| Slot | Literal | `wf[…]` | `res[…]` |
|---|---|---|---|
| tool keyword argument | works | **works** | works |
| tool positional argument after the input | — | `TypeError: Operation.__call__() takes from 1 to 2 positional arguments but 3 were given` | same |
| shape setting: `select(columns=wf["cols"])` | works | **crashes:** `TypeError: 'StepRef' object is not iterable` | — |
| shape setting: `slice(start=wf["k"])` | works | refused: `slice's start= must be int, got StepRef` | — |
| execution setting: `retry(times=wf["w"])` | works | refused: `retry's times= must be int, got StepRef` | — |

Several keyword references in one call work: `f(wf["r"], a=wf["a"], b=wf["b"])`
gives `[10, 20, 30]`, and changing `a` marks the step stale. The gap is the
**shape** a reference arrives in. `g(n, vals: list)` with `vals=wf["col"]`
(one column, two rows) declares with no problem. Every row then fails at run
time with `TypeError: unsupported operand type(s) for +`, because `vals`
receives a DataFrame, not a list.

**Ask:**

1. **One value type for every slot:** `Literal | StepRef | ResRef` (plus
   `ToolRef`, C2), serialised as a literal, `{"$ref": …}`, `{"$res": …}` or
   `{"$tool": …}`. Arguments and modifier settings both accept it.
2. **Positional arguments after the input** bind by position, as keyword
   arguments do. A `res[…]` binds to the parameter of its type. The app does
   this today for `summarize(wf["notes"], res["llm"])`.
3. **References in settings** resolve at run, record a dependency, and are
   type-checked against the setting's declared type.
4. **Shape conversion follows the annotation.** A one-cell step gives its
   cell. A one-column step gives a list when the parameter is annotated `list`.
   Any other shape mismatch is a declaration problem, not a failure on every row.
5. **Never crash on a reference.** Until (3) lands, a `StepRef` in any setting
   is a declaration problem, as `slice` and `retry` already give.

**Done when:** `select(columns=wf["cols"])` with `wf["cols"] = ["city"]` gives
the `city` column, and changing `cols` marks it stale; `scale(wf["r"], wf["w"])`
equals `scale(wf["r"], weight=wf["w"])`; `g(vals=wf["col"])` gives
`[31, 32, 33]`.

**Removes:** what's left of `SHIM(core §L)` in `core_bridge.needs_whole_frame_shim`.

### C7. Excel-style selection: `wf["step"][rows][cols[columns]]` (includes K9)

One way to select cells, rows, columns and blocks, written the same in the
formula bar and in Python, with every failure stated.

#### Two type rules

- **Column names are strings.** Always, in every step's output.
- **Row selectors are integers.** They are positions in the step's output,
  0-based, and negative counts from the end (`-1` is the last row). They are
  not the stored row ids.

And one syntax rule built on them: **a plain bracket always selects rows, and
`cols[…]` always selects columns.** No string ever goes in a row bracket, and
no bare integer ever means a column.

**Today:** core breaks both. `wf["p"] = pd.DataFrame({2023: [1, 2], 2024: [3, 4]})`
keeps integer column names; `select(columns=[2023])` works, and
`select(columns=["2023"])` **crashes** building its own error message:
`TypeError: sequence item 0: expected str instance, int found`.

**Ask:** when a step produces its output, core converts every column name to
`str` (`2023` → `"2023"`). If two names collide after converting (`1` and
`"1"`), the step fails: *"columns 1 and '1' both become '1'; rename one"*.
Error messages must never assume a name is a string before that conversion
(the crash above).

#### Syntax

`cols` is a module-level indexer exported beside `wf`, `res` and `mod`. It is
written with brackets because `:` ranges only work inside `[]`
(`cols("a":"c")` is a syntax error).

**Rows: plain brackets, integers only.**

| Excel | Formula | Selects |
|---|---|---|
| `3:3` | `wf["p"][2]` | one row |
| `2:5` | `wf["p"][1:5]` | rows 1–4 (half-open, as in Python) |
| — | `wf["p"][[0, 2]]` | rows 0 and 2, in that order |
| last row | `wf["p"][-1]` | one row |
| — | `wf["p"][-3:]` | the last 3 rows |

**Columns: `cols[…]`, by name or by position.**

| Excel | Formula | Selects |
|---|---|---|
| `B:B` | `wf["p"][cols["price"]]` | one column, by name |
| — | `wf["p"][cols[["name", "price"]]]` | those columns, in that order |
| `A:C` | `wf["p"][cols["name":"price"]]` | `name` to `price`, **inclusive**, in the step's column order |
| — | `wf["p"][cols["name":]]` / `wf["p"][cols[:"price"]]` | open-ended name ranges |
| `B:B` | `wf["p"][cols[1]]` | one column, by position |
| `A:C` | `wf["p"][cols[0:3]]` | columns 0–2, **half-open** |
| — | `wf["p"][cols[[0, 2, 5]]]` | those positions, in that order |
| — | `wf["p"][cols[-2:]]` | the last 2 columns |

Names are inclusive and positions are half-open, which is pandas' `.loc` /
`.iloc` rule. The formula bar shows the resolved names next to any range, e.g.
`cols 0–2 (name, qty, price)`.

**Both: rows, then columns.**

| Excel | Formula | Selects |
|---|---|---|
| `B3` | `wf["p"][2][cols["price"]]` | one cell |
| `A2:C5` | `wf["p"][1:5][cols["name":"price"]]` | a block |
| — | `wf["p"][-1][cols[0:3]]` | first 3 columns of the last row |

**Order is free.** Columns are always `cols[…]` and a bare integer is always
rows, so each part says what it is, and parts can come in any order, in one
bracket or two. `rows[…]` is an optional label, never required. All of these
are the same block:

```python
wf["p"][1:5][cols["a":"c"]]
wf["p"][cols["a":"c"]][1:5]
wf["p"][1:5, cols["a":"c"]]
wf["p"][cols["a":"c"], 1:5]
wf["p"][rows[1:5], cols["a":"c"]]
```

`rows` is a module-level indexer like `cols`, taking the row forms (`int`,
`int` range, list of `int`). Python passes a one-bracket pair as a tuple,
e.g. `(slice(1, 5), cols[…])`, checked with a plain `__getitem__`.

**Bracket rules:**

1. **Rows:** a bare `int`, `int` range or list of `int`, or the same inside
   `rows[…]`. Bare integers default to rows.
2. **Columns:** only `cols[…]`, holding a `str`, a `str` range, a list of
   `str`, an `int`, an `int` range or a list of `int`. Names and positions are
   not mixed in one `cols[…]`.
3. **At most one row part and one column part,** in any order, written as one
   bracket (`[a, b]`) or two (`[a][b]`). Nothing may follow once both are given.

Python hands each form over as a distinct value: an `int`, a `slice`, a `list`,
or a `rows`/`cols` object wrapping one of those. So the step reference can tell
every case apart by type, with no guessing.

#### Where a selection can go

| Position | Allowed | Means |
|---|---|---|
| On its own: `wf["block"] = wf["p"][1:5][cols["name":"price"]]` | yes | a `select` step, visible and re-runnable (this is K9) |
| As an argument: `score(wf["o"], prices=wf["p"][cols["price"]])` | yes | the selected value, passed whole to every row |
| As a tool's input: `score(wf["p"][1:5])` | **no** | two reshapes in one step; make the selection its own step |

#### What arrives in an argument

The parameter's type decides the conversion. A mismatch is refused, never guessed.

| Selection | `list` | `pd.Series` / `pd.DataFrame` | `dict` | scalar (`float`, `str`, …) |
|---|---|---|---|---|
| cell | `[v]` | — | — | **the value** |
| one column | **list of values** | Series | — | ✗ *"a column; to pair rows, join first"* |
| one row | list of values | Series | **{column: value}** | ✗ |
| several rows or columns | ✗ | **DataFrame** | ✗ | ✗ |
| untyped parameter | the natural form (value / list / dict / DataFrame), with a warning to add a type | | | |

The scalar ✗ for a column is the per-row trap: an argument is never paired
with the input's rows. Pairing rows needs `join`.

#### When it fails

**At declaration** (as the formula is typed):

1. A row bracket that isn't an `int` form: a `float`, a `bool`, `None`, or a
   range with a step (`0:10:2`).
2. **A string in a row bracket:** `wf["p"]["price"]` → *"columns are selected
   with cols: `wf['p'][cols['price']]`"*. This is the pandas habit, so the
   message names the fix.
3. A `cols[…]` that mixes names and positions (`cols[["name", 2]]`,
   `cols["name":3]`), or holds anything else (`float`, `bool`, `None`, a
   stepped range).
4. Two row parts (`wf["p"][1:5][2]`), two column parts, or a third bracket.
5. An empty selection: `wf["p"][[]]`, `wf["p"][cols[[]]]`, `wf["p"][rows[[]]]`.
6. A one-bracket pair with more than two parts, or two parts of the same
   kind (`[1:5, 2]`, `[cols["a"], cols["b"]]`).
7. A column name that doesn't exist: *"p has no column 'prise' (it has name,
   price)"*, when the columns are known (C5). Otherwise checked at run.
8. A name range in the wrong order (`cols["price":"name"]`).
9. A shape that doesn't fit the parameter's type (✗ above).
10. A selection used as a tool's input.
11. A row or column position out of range, when the upstream shape is
    already known (data present, typed columns, or a fixed row rule).

**At run** (the step fails with this message, never `None`, `NaN` or empty):

12. A position out of range: *"row 7 of 'p', which has 5 rows (0–4)"*, or
    *"column 7 of 'p', which has 5 columns (0–4)"*, like Excel's `#REF!`.
13. **A range that goes past the end fails; it is not trimmed**, for rows and
    column positions alike. For "up to the first n rows", use a `slice` step,
    which promises *at most* n.
14. A named column that's gone after the upstream step re-ran or was renamed.
    A rename also marks the reading step with a problem straight away.
15. A value that doesn't fit the parameter's type, for untyped upstream steps.

**Flagged, not failed:**

- A **warning** when a row position reads a step whose row order isn't fixed
  (the output of `filter`, `expand`, `group`, or an unsorted source): row 3
  may be a different row next run.
- **Column positions and name ranges follow the current columns.** If the
  upstream step adds or reorders columns, `cols[0:3]` or `cols["name":"price"]`
  covers different columns. The step goes stale and the formula bar's resolved
  names show the change. For a fixed set, use a list of names.
- When the upstream step changes, every step that selects from it is
  **stale** and re-runs, like Excel recalculating.

#### `rows` and `cols` are reserved names

`rows` and `cols` mean only core's row and column indexers. Nothing else may
use those names: not a tool, not a variable in a script that declares steps.

**Why:** a script's own `rows` replaces the import, and Python evaluates
`rows[1:5]` on it before core sees anything:

```python
rows = [10, 20, 30, 40, 50, 60]                 # the script's own variable
wf["p"][rows[1:5], cols["a"]]    # core receives ([20, 30, 40, 50], cols['a'])
wf["p"][rows[1:5]]               # core receives [20, 30, 40, 50]
```

Both arrive as valid row selections (bare integers are rows), selecting rows
20–50 silently. Without the reservation they can't be told apart from a
deliberate selection.

**Where it's enforced:**

| Where | How | Message |
|---|---|---|
| Registering a tool, bound tool or resource type | its formula name is checked against the reserved list | *"'rows' is reserved for row selection; choose another tool name"* |
| Declaring a step in Python (`wf["x"] = …`) | core looks up `rows` and `cols` in the **calling scope** (locals, then globals). If either is bound to anything but core's indexer, the declaration is refused, **whether or not the formula uses it** | *"'rows' is reserved for row selection, but here it's a list. Rename your variable"* |
| The formula bar | formulas run with a fixed set of names, so `rows` and `cols` are always core's | — |

Checked with a prototype: a script-level `rows = [10, 20, 30]` and a
function-local `rows = [1, 2]` are both detected at declaration; the imported
indexer passes.

**Reserved for tool names** (the formula bar's vocabulary, so no tool can hide
one): `wf`, `res`, `mod`, `rows`, `cols`, `op`, `join`, `stack`, `zip_`. None of
the app's 42 current tools uses one. The caller-scope check applies only to
`rows` and `cols`: a workflow named `wf` is allowed (C6), and `res`/`mod` are
rarely used as variable names.

**What it costs:** a script that uses `rows` or `cols` for its own data (a
common habit, e.g. `cols = df.columns`) must rename them before it declares
steps. The error names the variable and its type, so the fix is immediate.

#### Saved form

```json
{"$ref": "p", "rows": 2, "columns": {"names": ["price"]}}
{"$ref": "p", "rows": {"start": 1, "stop": 5}, "columns": {"from": "name", "to": "price"}}
{"$ref": "p", "columns": {"positions": {"start": 0, "stop": 3}}}
{"$ref": "p", "columns": {"positions": [0, 2, 5]}}
{"$ref": "p", "rows": [0, 2]}
```

`columns` always says which kind it is (`names`, `from`/`to`, or
`positions`), so a saved selection never relies on value types to be read.

Every spelling of the same selection saves identically, so the file doesn't
record which one was written. The formula printer (P) writes one canonical
form, **rows first, then `cols`, in two brackets** (`wf["p"][1:5][cols["a":"c"]]`);
the formula bar shows the user's own text while they're editing.

A selection on its own saves as a `select` step with the same `rows` and
`columns` settings, so there's one selection model in all three positions.

#### Ask

- The two type rules above, enforced where a step produces its output.
- `select(rows=…, columns=…)` taking every form in the syntax table (K9).
  Kept rows keep their row ids, so cells stay addressable.
- `rows` and `cols` indexers exported from `grid`, with the reserved-name
  checks above (registration, and the calling scope at declaration), and `StepRef.__getitem__` producing
  these forms, with `$ref` carrying `rows` and `columns` as an argument (with C1).
- The conversion table and the failure list, with the messages above.

**Done when:** `wf["p"][1:3][cols["name":"price"]]` and `wf["p"][1:3][cols[0:2]]`
as steps give the expected blocks; `score(wf["o"], prices=wf["p"][cols["price"]])`
with `prices: list` gets a list, and with `prices: float` is refused at
declaration; `wf["p"]["price"]` is refused with the `cols` hint; `wf["p"][9]`
on 5 rows fails with the row-7-style message; and a DataFrame with columns
`2023`, `2024` comes out with columns `"2023"`, `"2024"`; and
`wf["p"][1:3][cols["name":"price"]]`, `wf["p"][cols["name":"price"], 1:3]` and
`wf["p"][rows[1:3], cols["name":"price"]]` all save identically; and declaring a step from a
script that has its own `rows = [...]` is refused with the rename message.

### C5. A tool's return type predicts the step's columns

Staging already predicts a step's **size** as a rule from the verb: `map` →
"3 cells" (same as input), `filter` → "at most 3 cells", `expand` → "unknown
count from 3 rows". It doesn't use the tool's **return type** to predict the
step's **columns**.

**Today:**

```python
class Out(TypedDict):
    region: str
    score: float

@tool
def typed(n: int) -> Out: ...

wf["a"] = typed[mod.map()](wf["r"])
wf["w"] = op("identity")[mod.widen(columns=["value"])](wf["a"])
# staged columns of w: ['n', 'value'] — the same as for an untyped tool
op("identity")[mod.select(columns=["region"])](wf["w"])
# problem: "select names 'region', which the input does not have (it has n, value)"
```

A typed and an untyped tool stage identically, so typing a tool buys nothing
downstream before it runs.

**Ask:**

- A `TypedDict`, dataclass or pydantic return names the columns and their
  types. When the step spreads the result (`widen`, or `map` with a
  spreading option), those are the staged columns.
- A whole-table tool (K12) or a tool-backed source can declare its columns
  the same way, e.g. `-> Annotated[pd.DataFrame, Out]`. This removes K1's
  unknown case for typed sources.
- An untyped return gives **unknown** columns (K1), never an empty or wrong
  set, so checks are deferred and not failed.
- The catalog reports the return's fields, so the UI and the agent see a
  tool's output columns before it runs.

**Done when:** the `select(columns=["region"])` above declares with no
problems and the staged columns are `['n', 'region', 'score']`.

The model this completes: **types fix a step's shape at declaration; the verb
fixes its size as a rule** (`same`, `at most n`, `1`, `unknown`). The actual
row count is the only thing left to running.

### C8. Reactive, typed staging: a planned grid where every cell has a type

**Goal:** as soon as a step is declared, and again whenever its formula or its
input changes, the step shows the grid it *will* produce, without running
anything. Known cells show their values. Cells the tool will fill show the
type they'll hold.

```
step "scored" = score[mod.map()](wf["orders"])        score(n: int) -> float

 row │ city (str) │ n (int) │ value (float)
─────┼────────────┼─────────┼───────────────
  0  │ SF         │ 1       │ ‹float›
  1  │ NYC        │ 2       │ ‹float›
  2  │ LA         │ 3       │ ‹float›
```

**Today** (`map score` with `-> float`, over 3 known rows):

```
expected 3 · rows_rule same · columns ['city', 'n', 'value']
data: {'city': [None, None, None], 'n': [None, None, None], 'value': [None, None, None]}
dtypes: object, object, object
```

- **Known values are blanked.** `city` and `n` are already in the input, but
  the planned grid shows `None`.
- **No types.** A tool annotated `-> float` and an untyped one plan
  identically; nothing records `float`.
- **`filter` and `expand` plan an empty grid.** `filter` says "at most 3" and
  `expand` says "unknown count from 3 rows", but there are no rows to show.
- **Not reactive.** Replacing the input's 3 rows with 1 leaves the step at
  `map score · 3 cells`. Its plan isn't refreshed.

**Ask:**

1. **Every planned cell has a state and a type:**

   | State | Means | Shown as |
   |---|---|---|
   | `known` | the value is already determined (a passed-through input column, a literal, a selection from a step that has run) | the value |
   | `pending` | the tool will produce it | `‹float›` |
   | `maybe` | the row may not appear (`filter`) | the row, marked "may be dropped" |
   | `unknown` | the count isn't known yet (`expand`, `group`, a source that hasn't run) | one marked placeholder per input row, e.g. `‹0..n × list[str]›` |

2. **Where types come from:**
   - an input column: the type of its known values (`str`, `int`, …);
   - a tool's output: its return annotation (`-> float`); with C5, a
     `TypedDict`/dataclass gives one typed column per field;
   - a selection (C7) or argument (C1): the type it converts to;
   - `collapse`: one cell of the return type;
   - **untyped:** type `any`, plus the warning to add a type.

3. **Each verb's plan:**

   | Verb | Rows planned | Cells |
   |---|---|---|
   | `map` | one per input row (`same`) | input columns `known`; output column `pending` |
   | `filter` | every input row, `maybe` | all `known`; the count reads "at most n" |
   | `expand` | one `unknown` group per input row | output `pending` |
   | `collapse` | 1 | `pending` |
   | `select`, `slice`, `sort`, `rename`, `drop`, `distinct` | computed from the known input: these apply no tool | `known` |
   | `source` (tool-backed, not run) | `unknown` | typed from the return annotation (C5), else `any` |
   | `join`, `stack`, `zip_` | from the known inputs where the rule allows (`stack`: sum of rows) | `known` where computable |

   Tool-less verbs can be computed exactly when the input is known, because
   they don't run user code. Only tool calls stay `pending`.

4. **Reactive:** a step's plan is recomputed, **without running any tool**, when:
   - its formula changes;
   - an input or argument step gets new data (it's assigned, or it runs);
   - an upstream step's plan changes. Plans cascade down the workflow, as
     staleness already does.

   A planning pass never calls a tool, so it's safe to repeat on every edit.

5. **Cheap for large inputs:** the column types and the row rule are always
   computed; per-row cells are computed for a requested window (e.g. rows
   0–99), so the UI can render a planned grid of a million rows by page.

6. **In the API:** each planned column carries `type` and `source`
   (`input` / `output` / `argument`), and each row carries a `state`. A cell
   needs its own type only when a known column holds mixed types. That keeps
   the payload small: types are mostly per column, states are mostly per row.

**Done when**, for the `orders` example above:
- `scored`'s plan shows `city` and `n` with their values, and `value` as
  3 `pending` cells of type `float`;
- the same step with an untyped tool shows `value` as `any`, with a warning;
- `is_big[mod.filter()]` plans 3 `maybe` rows with known values;
- `fan[mod.expand()]` (`-> list[str]`) plans 3 `unknown` groups typed `str`;
- assigning 1 row to `orders` re-plans `scored` to 1 row, with nothing run;
- planning a step never calls its tool (a tool that counts its calls stays at 0).

**Why it matters:** this is the spreadsheet promise. You see the shape and
types of every step while you build, and running only fills in values. It
also turns C1's and C7's type checks into something visible: a mismatch is a
red column before anything runs.

### C9. Partial plans: stage what's known, mark what isn't, say how to resolve it

C8 plans a grid when everything is known. Often only part is: the output
type is known but the row count isn't, or the rows are known but the columns
aren't. The plan should show everything that *is* known, mark each unknown
explicitly, and say what would resolve it.

**Today:**

| Step | Core's plan | What's actually knowable |
|---|---|---|
| `expand` of `-> tuple[str, str]` over 3 rows | "unknown count from 3 rows" | exactly 6 rows (the type fixes the length) |
| `join(r, s, on="k")`, 3 rows × 2 rows | "unknown count from 2 grids" | 0–6 rows; columns `k, n, m` |
| tool-backed source `-> pd.DataFrame`, not run | "one cell per upstream row", columns `[]` | columns and rows unknown; `[]` wrongly reads as "no columns" |
| `stack(r, r)` | 6 ✓ | — |

The plan is a single sentence (`describe()`). Nothing records which part is
unknown, why, or what would settle it.

**Ask:**

1. **Three independent axes, each with its own certainty.** A plan never
   lets one unknown blank out the others:

   | Axis | `exact` | `bounded` | `unknown` |
   |---|---|---|---|
   | **rows** | `3` | `0–3`, `≥ 3`, `≤ 6` | `?` |
   | **columns** | `city, n, value` | `city, n` **plus more** | `?` |
   | **types** | `float` | one of `int \| float` | `any` |

   An unknown is **never** written as an empty value (`[]`, `0`, `None`). That
   is K1's bug, and the source row above repeats it.

2. **Bounds from the verb and the types.** The tighter the types, the tighter
   the plan:

   | Step | Rows |
   |---|---|
   | `filter` over n | `0–n` |
   | `expand` of `-> tuple[T, T, T]` | exactly `3n` |
   | `expand` of `-> Annotated[list[T], MaxLen(5)]` | `0–5n` |
   | `expand` of `-> list[T]` | `≥ 0`, unknown |
   | `group` / `distinct` over n | `1–n` (`0` if n is 0) |
   | `join` inner, n × m | `0–n·m`; `left`: `n–n·m` |
   | `stack` | exact sum |
   | `slice` / `select` rows | exact, from the selection |
   | tool-backed source | from its declared schema (C5), else unknown |

3. **Every unknown says why and how to resolve it.** Each axis that isn't
   `exact` carries a reason and the ways to settle it:

   ```json
   "rows": {"certainty": "unknown",
            "because": "expand: fan returns list[str], whose length is only known by running",
            "resolve": ["run fan", "annotate a fixed length: -> tuple[str, str]",
                        "state it on the step: mod.expect(rows=…)"]}
   ```

   Typical resolutions, in order of preference:
   - **run an upstream step** (its data makes later plans exact);
   - **tighten a type** on the tool (a return type, `tuple` length, `MaxLen`,
     a DataFrame schema, C5);
   - **state it on the step** (point 4).

4. **Let the author state what they know: `mod.expect(…)`.** When the author
   knows the shape and the types can't express it, they say so on the step:

   ```python
   wf["parts"] = split[mod.expand(), mod.expect(rows=12, columns=["part", "qty"])](wf["orders"])
   ```

   - **Staging** uses the stated shape as the plan, marked `stated`
     (distinct from `exact`, which core derived itself).
   - **At declaration**, a statement that contradicts what core already knows
     is a problem: `filter` over 3 rows with `expect(rows=10)` → *"filter
     gives at most 3 rows; expect(rows=10) can't hold"*.
   - **At run**, a mismatch fails the step clearly: *"expected 12 rows, got
     14"*, never silently.
   - It takes `rows` (an `int`, or `min=`/`max=`), `columns` (names, and
     optionally types: `{"part": str, "qty": int}`), and saves like any modifier.

5. **Show the known part, and mark the rest in place.** For a planned grid
   where only part is known:
   - known rows and columns render as in C8;
   - an unknown or bounded row count adds a trailing marker row, e.g.
     `‹+ 0–6 rows: join, 3 × 2›`;
   - unknown columns add a trailing marker column, `‹? columns›`;
   - an unknown type shows `any`;
   - each marker opens its `because` and `resolve` (point 3).

6. **Unknowns flow downstream, and checks wait for them.** A step reading an
   unknown is planned as far as it can be (a `map` over an unknown-row input
   still has a typed output column). Checks against unknown columns or rows
   are **deferred, not failed**, and re-run when the unknown is settled (K1).
   The UI can list a workflow's open unknowns in one place, like a list of
   open questions.

**Done when:**
- `expand` of `-> tuple[str, str]` over 3 rows plans exactly 6;
- the inner join above plans `0–6` rows with columns `k, n, m`;
- the untyped source plans rows and columns as `unknown` (never `[]`), with a
  `resolve` list that includes running it;
- `filter` with `mod.expect(rows=10)` over 3 rows is a declaration problem;
- `mod.expect(rows=12)` on a step that produces 14 fails with
  *"expected 12 rows, got 14"*;
- a `select(columns=["x"])` after the untyped source is deferred, not failed,
  and is checked once the source runs.

### C2. Shape settings can be functions

`filter` already takes behaviour, because its predicate is the step's tool. The
other reshaping verbs only take column names.

**Today:**

```python
op("identity")[mod.sort(by=lambda r: -r["n"])](wf["r"])      # TypeError: 'function' object is not iterable
op("identity")[mod.group(by=first_letter)](wf["r"])          # "group takes no parameter 'by'"
op("identity")[mod.rename(columns=str.upper)](wf["r"])       # TypeError: 'method_descriptor' object is not iterable
```

**Ask:**

- A key, predicate or name-mapping setting also accepts a **registered tool**:
  `sort(by=…)`, `group(by=…)`, `collapse(by=…)`, `distinct(columns=…)`,
  `select(columns=…)` (a predicate on column names), `rename(columns=…)`.
- Serialised as `{"$tool": "first_letter"}` and resolved from the `tools`
  mapping `run` already takes. **No raw lambdas in saved workflows:** accept
  one in Python only if `to_json` refuses it with a clear message.
- The function's signature is checked at declaration like any tool's; the
  verb's row rule doesn't change.
- `modifier_catalog()` marks settings that accept a tool, e.g.
  `{"name": "by", "type": "str | list | tool"}`, so the UI can show a tool picker.

**Done when:** `sort(by={"$tool": "neg_n"})` sorts by the tool's value,
survives `to_json`/`from_json`, and the catalog shows `by` accepting a tool.

### C6. Export an unbound `wf`: "a step in this workflow"

**Goal:** a formula is the right-hand side of a Python assignment, and reads
the same in the formula bar and in a Python workflow, whatever the workflow
variable is called.

```python
sales = grid.Workflow()
sales["orders"] = load_csv[mod.source()](path="orders.csv")
sales["scored"] = score[mod.map()](wf["orders"], weight=2, llm=res["claude"])
```

```
=score[mod.map()](wf["orders"], weight=2, llm=res["claude"])     # formula bar, step "scored"
```

**The reference language is two words:** `wf["…"]` is a step in this
workflow, `res["…"]` is a resource, and anything else is a literal.

**Today:** core exports `res` but nothing for steps, so `wf["orders"]` runs
only when the workflow variable happens to be named `wf`. Everything else is
already there:

- An unbound `grid.StepRef("orders")` resolves against the workflow it is
  assigned into. With two workflows, the same line gives `[10, 20]` in `wf1`
  and `[70, 80]` in `wf2`.
- A bound reference to the same workflow (`wf1["a"]` inside `wf1`) works and
  saves identically, as `{"$ref": "a"}`.
- A reference bound to a *different* workflow is refused at declaration:
  *"input 'a' reads a different Workflow…"*.

**Ask:** export `grid.wf`, an object whose `wf["id"]` returns an unbound
`StepRef("id")`, next to `grid.res`. A non-string key raises; attribute access
(`wf.run`) raises a message saying this `wf` is the reference, not a workflow.

**Settled alongside, so the spelling doesn't move again:**

- **Not `ref`:** too close to `res` when reading.
- **Not `step`/`steps`:** `wf.step("x")` and `grid.Step` already mean the Step
  object, and `step` is a common loop variable (11 uses in the app, 25 in
  core). The app's legacy API also exports a `step`.
- **No sigils:** `$`, `@`, `?`, `!` aren't valid Python as a prefix, and a
  marked string (`"@orders"`) makes some literals secretly references. That's
  the ambiguity K5 removes.
- **A workflow named `wf`** replaces the import harmlessly: its own `wf["…"]`
  means the same step.
- **Across workflows, copy, don't link:** `wf2["from1"] = wf1.step("x").output.data`.
  A live link would be a source step that runs another workflow, which is a
  separate feature.

**Done when:** `from simple_steps_core.grid import wf` works, and the same
line `x = scale[mod.map()](wf["r"])` gives `[10, 20]` in `wf1` and `[70, 80]`
in `wf2`.

### C3. A public surface made of functions

**Today** the app reads core in three ways it shouldn't:

| App file | Engine (retiring) | Grid globals / private |
|---|---|---|
| `core_bridge.py` | `REGISTRY`, `ResourceSpec`, `register_tool` | `MODIFIERS`, `SHAPE_VERBS`, `check_modifier`* |
| `grid_runner.py` | — | `SHAPE_VERBS`, `PAYLOAD`, `BUILTIN_TOOLS`, `TOOLS` |
| `main.py` | `REGISTRY.freeze`, `REGISTRY.items` | — |
| `agent/scope.py` | `REGISTRY.items`, `REGISTRY.get` | — |
| `agent/proposals.py` | — | `BUILTIN_TOOLS` |
| `resources.py` | — | `RESOURCE_TYPES` |

\* not in `grid.__all__`.

**Most of this is the app's job.** `grid.catalog()` already reports everything
the app shims onto the engine's registry: per-parameter `description` (from the
docstring's `Args:`), `choices` for a `Literal`, a `type` for every parameter
even when one is a DataFrame, and `returns: "DataFrame"`. So `SHIM(core §A,
§B, §E, §G, §J)` go away when the app reads `grid.catalog()` instead.

**Ask of core:**

1. **Functions for what the app reads as globals:** `builtin_tools()`,
   `shape_verbs()`, `resource_types()`, a payload-kind check instead of
   `PAYLOAD`, and `freeze()` on the grid's tool registry. The globals can then
   become private.
2. **A public modifier check:** make `check_modifier(kind, params)` public, or
   give `Operation` a `check()` that returns problems without a workflow (see O).
3. **Free-form `tags` on a tool.** The app's tool "types" (`step`, `rowmap`, …)
   are app labels. Tags let the app keep them without core owning an enum.

**Done when:** `grep -r "from simple_steps_core import" src` shows only `grid`,
and no `grid.<UPPERCASE>` name is read in `src/`.

### O. A missing required modifier setting passes declaration

**Today:**

```
Operation.from_dict({... "modifiers": [{"kind": "retry", "params": {}}, {"kind": "map", ...}]})
wf.step("s").problems  -> ()
wf.run("s", tools)     -> TypeError: _d_retry() missing 1 required keyword-only argument: 'times'
```

A misspelt setting is already a good declaration problem (*"map takes no
parameter 'nme'; it accepts axis, name, retries"*), and the catalog already
marks `times` as `required`. Both checks need a workflow, which a formula bar
checking as you type doesn't have.

**Ask:** report a missing required setting like a misspelt one, and expose
both checks without a workflow (C3.2).

**Removes:** `SHIM(core §O)` in `core_bridge.modifier_settings_problem`.

### K12. A whole-table verb

**Today:** no verb hands a tool the whole grid.

```python
@tool
def piv(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("city", as_index=False)["n"].sum()
piv[mod.collapse()](wf["r"])   # AttributeError: 'NoneType' object has no attribute 'groupby'
piv[mod.map()](wf["r"])        # invalid: piv() needs 'df', which 'r' does not have
```

The app has `pivot`, `unpivot`, `pandas_eval`, `merge_steps`, `select_cell`,
and users write their own. The catalog already flags these
(`takes_whole_row`, `params[0].type == "DataFrame"`).

**Ask:** a shape verb (for example `table`) that passes the input grid as the
first parameter and uses a returned DataFrame as the step's grid: the mirror
of the tool-backed `source`. One ledger unit; row rule "generated".

**Done when:** `piv[mod.table()](wf["r"])` returns the grouped frame.

**Removes:** `SHIM(core §K)` (routes these steps to the legacy `dataframe` orchestrator).

### N1. A `dict | None` resource setting refuses every value

**Today:** in a module with `from __future__ import annotations`,
`Workflow().define("db", DB, table={"SF": "n"})` →
`TypeError: … setting 'table' is declared dict | None, got {'SF': 'n'}`.
`table=None` fails the same way. `Optional[dict]` works. Core's own `FakeDB`
hits this.

**Ask:** resolve string annotations with `get_type_hints` before checking.

**Done when:** both calls define the resource.

---

## Priority 3 — editor, consistency, resources, features

### C12. Tools have named, typed parameters: discourage `*args` and `**kwargs`

**Rule:** a tool's parameters are its contract. The catalog, the formula's
keyword checks, the C1/C7 type conversions and the C8 plan all depend on
every parameter having a name and a type. Variadic parameters have neither.

**Today:**
- `*args` is **already refused** at registration, with a good reason:
  *"cannot declare tool 'star': \*args declares no names, so the tool would be
  called with no arguments at all and return a plausible wrong answer."*
- `**kwargs` is **accepted silently.** `kw(n: int, **opts)` called with
  `color="red", size=3` runs and receives both, unchecked and untyped. A
  misspelt keyword can't be caught, because every keyword is accepted.

**Ask:**

1. Keep refusing `*args`.
2. **`**kwargs` registers with a warning:** *"kw accepts \*\*opts: its extra
   keywords can't be checked, typed or shown in a form. Name the parameters
   you expect."* The catalog marks the tool `open: true` and `typed: false`.
3. **A strict setting refuses it,** for deployments that want every tool
   fully declared (the app would turn this on for workspace tools).
4. **In a formula,** a keyword that matches no named parameter and lands in
   `**kwargs` gets a warning on the step, so a typo is at least visible.

**Done when:** registering a `**kwargs` tool warns and the catalog marks it
`open`; strict mode refuses it; and `kw(…, colr="red")` declares with a
warning naming `colr`.

### C15. Tool versions and determinism decide when results are reused

Staleness today follows **data**: a step is stale when its formula or an
upstream step changes. Two more things decide whether an old result is still
right:

- **The tool's code changed.** A step run with yesterday's `score` keeps
  yesterday's results, with nothing saying the code is different now.
- **The tool isn't deterministic.** An LLM call or a web request can give a
  different answer for the same input. Re-running should be a choice, not an
  accident.

**Ask:**
1. **A tool version.** Each tool has a version: a declared `version=` on the
   decorator, or a hash of its source. Results record the version they were
   produced with, and a change marks the steps that used it `stale`, as a
   data change does.
2. **A `deterministic` flag** on a tool (default `True`). For a
   non-deterministic tool, unchanged inputs keep their results unless the
   user asks for a re-run. K15's "re-run failed rows" reruns only the failed
   ones either way.
3. **Both appear in the catalog,** so the UI can show "this step's tool has
   changed since it ran" and mark non-deterministic tools.

**Done when:** editing a tool's body (or bumping `version=`) marks the steps
that ran it `stale`, and re-running a non-deterministic step with unchanged
inputs reuses its results unless asked.

### C17. `mod.table()` binds the parameter typed `DataFrame`

**Today (9a86a0d):** the grid goes to the tool's *first* parameter.

```python
def later(n: int, data: pd.DataFrame) -> pd.DataFrame: return data.head(n)
wf["l"] = Operation.from_dict({"tool_id": "later", "input": {"$ref": "a"},
    "arguments": {"n": 1}, "modifiers": [{"kind": "table", "params": {}}]}, tools)
wf.step("l").problems
# ("later() needs 'data', which 'a' does not have (it has k, n, x)",)
```

**Ask:** hand the grid to the one parameter annotated `pd.DataFrame` (the
first, if none is). **Removes:** `SHIM(core §C17)`,
`core_bridge.needs_whole_frame_shim`, and with it the last use of the legacy
`dataframe` orchestrator from the grid path. **Done when:** the step above
runs and returns one row.

### C18. `catalog()`'s description is the docstring's first paragraph

**Today (9a86a0d):** it is the first *line*, so a wrapped summary is cut
mid-sentence. Of the app's 29 built-in tools, 8 were cut, e.g. `to_rows`:
*"Create a step from a single raw value. The value is stored in a"*.

**Ask:** take the first paragraph (up to the first blank line), joined with
spaces. **Removes:** `SHIM(core §C18)`, `core_bridge.docstring_summary`.
**Done when:** `catalog()["to_rows"]["description"]` ends with *"…that you can
reference from later steps."*

### C19. A one-cell step passed to a parameter typed `dict`

**Today (9a86a0d):** refused, though an untyped parameter gets the value:

```python
wf["d"] = {"a": 1, "b": 2}                    # one cell
typed(cfg=wf["d"])     # cfg: dict
# problem: "cfg: dict, but 'd' is a cell — an argument is passed whole, not one value per row"
untyped(cfg=wf["d"])   # → "{'a': 1, 'b': 2}"
scal(n=wf["k"])        # n: int, wf["k"] = 5 → 10
```

The same refusal with an explicit cell selection (`rows: 0, columns:
{"names": ["value"]}`). **Ask:** a cell is its value for any parameter whose
type the value fits, `dict` included. **Removes:** the app's inlining of a
one-value step as a literal in `grid_runner._plan` (then a `$ref`, so the
step is tracked for stale/rename). **Done when:** `typed(cfg=wf["d"])` runs.

### C20. A selection as a tool's input is silently ignored in JSON

**Today (9a86a0d):** Python refuses it, but the same operation as JSON is
accepted, saved with the selection, and run on **every** row:

```python
inc[mod.map()](wf["r"][0:2])
# TypeError: a selection can't be a tool's input: make it its own step …

Operation.from_dict({"tool_id": "inc",
    "input": {"$ref": "r", "rows": {"start": 0, "stop": 2}},
    "arguments": {}, "modifiers": [{"kind": "map", "params": {}}]}, tools)
# problems: ()          → runs on 3 rows, not 2
```

The app builds every step from JSON, so it can't rely on the Python refusal.
**Ask:** `from_dict` refuses a selection in `input` with the Python message
(or applies it, if 009 decision 7 allows row-only selections). **Done when:**
the JSON above has that problem and doesn't run.

### C21. Whether a step's failures stop a run is public

**Today (9a86a0d):** `run_all` decides with the private
`grid._uncaught_failure(output)`: a failed row stops the run unless
`try_except` caught it (`caught: true`) or it was blocked upstream (it has a
`cause`). It returns only the first such row. The app runs one step at a time
and needs the same answer per step, to stop its own Run All the same way
(spec 009 REQ-RUN-004), so it re-implements the rule from the public ledger.

**Ask:** a public function or `Output` property, e.g. `Output.uncaught` (the
failed rows that stop a run). **Removes:** `SHIM(core §C21)`,
`core_bridge.uncaught_failed`. **Done when:** a `map` with one raising row
reports one uncaught row, and the same step under `mod.try_except()` reports
none.

### C16. Stable row ids, guaranteed per verb

C7 selects rows by **position**. Re-running failed rows (K15), reusing
results (C15), tracing a failure to its root (C10) and showing what changed
between runs all need the **row id** to stay stable.

**Today:** `filter`, `sort` and `map` keep the input's row ids (`['a', 'c']`,
`['b', 'c', 'a']`, `['a', 'b']`). `expand` replaces them with new numbers
(`[0, 1, 2, 3, 4, 5]`), so an expanded row no longer says which row it came
from.

**Ask:** state, and test, what each verb does with row ids:

| Verb | Row ids |
|---|---|
| `map`, `filter`, `sort`, `select`, `slice`, `distinct`, `drop`, `rename` | kept |
| `expand` | derived from the parent: `a.0`, `a.1` |
| `collapse` | one new id |
| `group` | one id per group, from the group key |
| `join` | derived from both parents |
| `stack` | kept, prefixed by input when they'd collide |
| `source` | new ids, stable across re-runs of the same data where possible |

**Done when:** `expand` over rows `a, b, c` gives ids `a.0, a.1, b.0, …`, and a
test asserts the table above for every verb.

### N. A written `mod.auto()`

The step editor needs an explicit "pick the verb from the data" state that
survives saving: `is_big[mod.auto()](wf["readings"])`.

**Today:** `'auto' in grid.MODIFIERS -> False`.

`infer_verb`'s docstring objects that a stored auto has a shape no one can know
before running. The ask is scoped to answer that:

- **Stored, never run.** `auto` lives in the JSON and the formula; `run`
  resolves it with `infer_verb` against the input's actual data and runs the
  concrete verb. The resolved verb and reason are reported on the step.
- **Unknown only until the input has run.** Before that, the signature still
  answers most cases (`-> bool` → filter, a list → expand). Staging shows that
  verb, marked provisional.
- **Round trip holds.** `auto` saves as `auto`. Choosing a verb replaces it.

**Ask:** `mod.auto()` in the catalog (class `shape`, no settings,
`row_rule: "unknown"`), resolved in `run`.

**Removes:** `SHIM(core §N)` — `AUTO`, the catalog wrapper and `resolve_auto` in
`core_bridge`. Verified end to end: `is_big` → filter, `fan_out` → expand,
`add_n` → collapse, `scale[auto, retry]` → `['retry', 'map']`.

### P. `Operation.to_source()`

The editor edits a formula as parts and writes it back, so it needs
operation → `tool[mod.verb(…)](wf["x"], k=v)`. Core has `from_dict`/`to_dict`
only; `repr` is a debug form (`<Operation map() ∘ scale over='r'>`).

**Ask:** `Operation.to_source() -> str`, with `compile(to_source(op)) == op` as a
tested invariant.

**Replaces (not a shim):** the app's `operation_formula.format_parts`, which
round-trips all 60 example formulas (57 character-for-character).

### M. `infer_verb` reads a bound method's `self` as a column

**Today:** `grid.infer_verb(DB.lookup, upstream, {})` →
`('collapse', "'self' is not a column but 'key' is…")`. With `self` bound, it
gives `map`. Core's own `res["db"].lookup(wf["keys"])` infers `map`
correctly; only the public function gets it wrong.

**Ask:** accept a bound tool (or a `(type, method)` pair).

**Removes:** `SHIM(core §M)` in `core_bridge.inferable_method`.

### K13. `modifier_catalog()` says which verbs take a tool

**Today:** `modifier_catalog()['select']` has keys `class, name, row_rule,
settings`. The app hard-codes which verbs apply a tool, in `grid_runner.py` and
`OrchestrationControl.tsx`.

**Ask:** add `takes_tool` (`true` / `false` / `"optional"`) and `default_tool`
(`identity`, `gather` or `null`) to each entry.

### K5. In Python, `over` takes only a `StepRef`

**Today:** `mod.map(over="readings")` treats the string as a reference;
`scale[mod.map()]("readings")` treats it as data.

**Ask:** in Python, raise *"pass wf['readings']"* for a string. Keep string ids
in `from_dict` JSON, where the setting's type says what they are.

### K8. Tool-less modifiers callable on a reference

**Today:** `mod.select(columns=["n"])(wf["r"])` → `'Modifier' object is not callable`.

**Ask:** make it the same as `op("identity")[mod.select(…)](wf["r"])`, for every
verb that applies no tool.

### R3/R4. Secrets and loaded resources

**Today:** no `Secret` type; `to_dict` writes only `"source": "defined"`.

**Ask:**
- A setting annotated `Secret` accepts only a pointer (`"env:ANTHROPIC_API_KEY"`
  or a loaded resource's name), never a value, and is saved as the pointer.
- *(Optional for the app.)* `"source": "loaded"` with `as_loaded` and
  `overrides`. The app already merges deployment settings and overrides
  itself and hands core a plain `define`. Core needs this only for its own
  Python users.
- An optional health check on a resource type.

**Done when:** `define("llm", T, api_key="sk-123")` is refused,
`api_key="env:FAKE_KEY"` is accepted and saved as the pointer.

### R5. Unknown top-level sections survive a round trip

**Today:** a blob with `stages` added comes back from
`from_dict(d).to_dict()` as `['version', 'steps']`.

**Ask:** either (a) `from_dict` keeps unknown top-level keys and `to_dict` writes
them back, or (b) core states its blob is one section of a larger file the
app owns. The app will add `stages`, `ui`, `description`, step `notes` and
`extensions`.

### K14. Progress callback on `run`

**Today:** `Workflow.run(step_id, tools=None, resources=None)`. `Output.progress`
is readable only after the step finishes.

**Ask:** `run(…, on_unit=None)`, calling `on_unit(step_id, unit, record)` as each
unit finishes. The app streams it to the progress bar.

### K15. Re-run only the failed rows

**Today:** no `Workflow.redrive`. `Output.failed` lists the rows.

**Ask:** `wf.redrive(step_id)` re-runs failed units and keeps completed ones;
`attempts` goes up for the re-run units.

### K16. A pluggable results store

**Today:** no `Output.ref`. Anything that isn't plain data raises `PayloadError`
on `to_session_json()`.

**Ask:** `Output.ref` plus a store interface (`put`, `get`, `delete`) the app
can back with its per-session parquet store (core's D5).

### C4. The tool registry can be cleared and re-filled in-process

The app's planned kernel restart (`docs/dev_plan/200` B2) re-imports workspace
tools without restarting the process. That needs core's registry to drop the
workspace's tools and accept them again, including after `freeze()`.

**Ask:** `unregister(tool_id)` or `reset(origin="workspace")` on the grid
registry. Not verified yet: run core to confirm before building B2.

---

## Priority 4 — later

### K11. Refuse `over=[a, b]` clearly

**Today:** adding the step raises `TypeError: __str__ returned non-string
(type list)` (`Operation._add` wraps any `over` in `StepRef`). Combining steps
already works through `join`/`stack`/`zip_`; the app's compiler never
produces this form.

**Ask:** in `_add`, accept only a `StepRef` or a string; otherwise raise *"one
step reads one input; to combine steps use join, stack or zip_"*.

### K17. Keep JSON v1 loadable across P0

**Today:** `to_json` writes `version: 1`. C1 and C2 change the JSON too.

**Ask:** when the operation JSON changes, bump `version` and keep loading
version 1 for at least one release.

### K18. Enforce `timeout`

**Today:** 4 units × 0.3 s with `timeout=0.05` take 1.2 s and all complete.

**Ask:** fail a unit that runs past its timeout, with a timeout error in the
ledger. Needs core's async engine (B5).

### K19. A column argument pairs per row, by type

**Decided by the owner (2026-10-25):** modifiers make a tool run per cell, so a
column passed as an argument should be paired row by row. The orchestration is
inferred from type matching, not written by the user.

**Today** (run on the current pin, `make` = `n: [3, 1, 2]`, `w: [10, 20, 30]`):

- `scale(n, weight=1)` untyped, `weight=wf["r"][cols["w"]]`, under `mod.map()`:
  every row gets the whole list → `[[10, 20, 30]×3, [10, 20, 30], [10, 20, 30]×2]`.
- `scale(n: int, weight: int = 1) -> int`, same call, under `mod.map()` or
  `mod.auto()`: problem *"weight: int, but 'r' is a column; to pair its rows with
  the input's, join first"*, output `[None]`.
- The working route today: `wf["z"] = zip_(wf["r"], wf["w"])`, then
  `scale[mod.map()](wf["z"])` → `[30, 20, 60]`.

**Ask:** in a row-wise verb (`map`, `filter`, `expand`, `auto` resolving to one
of them), decide a column argument by the parameter's type:

| Parameter type | Column argument |
|---|---|
| scalar (`int`, `str`, …) or untyped | one value per row, row *i* with row *i* |
| `list`, `Series`, `DataFrame` | the whole column, as today |

A row-count mismatch is a problem on the step, naming both counts. Under a
whole-grid verb (`table`, `collapse`) the column stays whole.

**Row id (decided by the owner, 2026-10-25):** pairing by position breaks when
an earlier step re-sorts or filters one side but not the other, and cell
selections (C1) have the same problem: after a sort, `wf["srt"][0]` picked a
different row. Both use the **row id** instead, and the row id is the frame's
index: the default index unless a tool sets its own. So:

- a column argument pairs with the input's rows by index, not by position;
- a selection such as `wf["r"][0]` or `wf["r"][0:2]` picks rows by index label,
  so it follows the row through a sort;
- verbs that keep rows (`map`, `filter`, `sort`) keep each row's index;
- an index label missing on the other side is a problem on that row, not a
  silent `NaN`.

Still to settle in core: what id the new rows get from verbs that make rows
(`expand`, `stack`, `join`, a source).

The owner is making this core update.

**Not yet confirmed as a core change.** This is the requirement; the edit to core
is confirmed separately before it lands.

### K20. Kernel and run identifiers, by hashing specs

**Decided by the owner (2026-10-26):** users should be able to tell they are
running exactly the same workflow, and whether a tool changed under the data.

**Today** (run on the current pin): core hashes a step's **output data**
(`wf.version("f")` → `'1ea84a71beb3'`, SHA-1 of row ids, columns and values),
the versions a step **read** (`read: {'p': 'f3868e7634d7'}`) and a
**resource's** type and settings. It stores the formula a step ran with as
text. Tool code and the kernel as a whole are not hashed.

A tool's source hashes cheaply: `inspect.getsource(handle.fn)` → SHA-256 took
0.11 ms, and works on library functions too (`pandas.read_csv`).

**Ask:**

```
tool hash     = sha256(name, source of handle.fn, library name + version)
resource hash = sha256(type, settings without secret ones)
step hash     = sha256(name, operation spec, hashes of its tools,
                       hashes of the steps and resources it reads)
kernel id     = sha256(step hashes in order, catalog hash)
run id        = kernel id + the data versions of the source steps
```

- **Step names count** (owner): a name is part of the spec, so a rename changes
  the hash.
- **Tool hashes are computed once**, when the catalog is built, not per run.
  The source hash changes on any edit, comments included; that's acceptable.
  It doesn't see changes inside packages a tool imports; the library version
  is the line.
- **A changed tool marks its steps stale**: put the tool hash in `ran_with`,
  so "the tool changed under this data" shows the same way a changed formula
  does.
- **Secrets:** resources need secret settings for now (API keys). A resource
  type marks which settings are secret, and they're left out of the hash.
  Today's resource hash includes every setting.
- **Tools that aren't deterministic** (an LLM call, random sampling): the same
  id can't promise the same output. For now, recommend developers give such
  tools a `seed` literal parameter, so the seed is part of the spec and the
  hash. Nothing more is enforced yet.
- **Canonical form:** JSON with sorted keys, never `repr`. Full SHA-256 stored,
  shown short (`ss:4be0c19a…`).
- **Terminal:** `k.id`, `k.run_id`, `k.step("f").id`, and `k.diff(other)`
  giving the first step whose hash differs and why (formula, tool code, input).

### K21. Room in each spec for the app's additions

**Decided by the owner (2026-10-26):** this repo augments core's specs (a
tool's, a resource's, a step's) with its own information, and developers will
want custom UI components for their tools, such as a date picker for one
argument.

**Ask:** each spec carries an open `extras` mapping, keyed by namespace
(`"simple_steps.ui"`), that core stores, saves and loads but never reads.

- **Not part of the hash.** A changed input widget doesn't change what a step
  computes.
- **Declared with the tool:** `@tool(extras={"simple_steps.ui": {"date": "date-picker"}})`,
  or added to a catalog entry. The app maps names to components; core never
  knows about UI.

### K22. Keep earlier outputs while something still reads them

**Decided by the owner (2026-10-26):** when a step re-runs, its new output
becomes current, but a later step that read the old output and hasn't re-run
keeps showing what it was computed from.

**Today:** core keeps only each step's latest output. This repo's
`DATA_STORE` keeps every run's output, per session, keyed by a ref id, and
never frees any (the leak in [how-simple-steps-works.md §5 item 6](../how-simple-steps-works.md)).

**Ask:** store outputs by their data version, which core already computes.

- An output is immutable once written; equal data is stored once.
- A step points at the version it produced; a reader records the version it
  read (core's `read` stamps already do).
- A reader that hasn't re-run is `stale` and still shows the version it read.
- A version no step points at or reads is freed. That ends the leak.
- Where versions are kept (memory now, disk or a database later) is the
  pluggable store of C32.

### K23. Progress and cancellation as modifiers

**Decided by the owner (2026-10-26):** progress is defined with modifiers, and
can be defined for any cell output.

**Ask:** execution modifiers (beside `retry` and `breaker`) that report each
cell as it moves through its states (pending → running → known / failed), to
a callback the host passes in, plus `cancel()` on a running step. The host
(terminal or app) decides how to show it; core only reports.

### K24. No state shared between workflows

**Decided by the owner (2026-10-26):** users and workflows must never share
anything that could mix them up, across users and across live kernels. Core
assumes one workflow per interactive session; this repo isolates sessions.

**Today:** `grid.TOOLS` is one process-wide dict, so a tool defined for one
workflow is usable by all of them in the process.

**Ask:** no mutable state at module level in core. Everything a workflow uses
(catalog, resources, outputs, caches) hangs off its kernel, so two kernels in
one Python process can't see each other.

### K25. Resource defaults are literals

**Decided by the owner (2026-10-26):** a resource's settings for a context are
hardcoded defaults, always literals. Two kernels connected to exactly the same
database should behave the same.

**Open:** a tool that queries a resource (a database in a `map`) reads data
that isn't a step, so its data version isn't in the run id (K20). The same run
id can then give different results if the database changed. Possible answer:
a resource may report a version (a snapshot id, a last-modified time) that goes
into the run id.

**Decided (owner, 2026-10-26):** do that. A resource type may report a data
version; it goes into the run id (K20) and into the `read` stamps of the steps
that use it, so a changed database marks them stale like a changed input step.

### K26. Size estimates, and output in pages

**Decided by the owner (2026-10-26):** memory limits are Python's own for now.
The UI shows 50–100 rows at a time and loads the next page at the bottom. The
user must still see the scale of the data. UI limits go on the *estimated
size* of the data being processed; scaled solutions are a later layer.

**Ask:** every output reports its row count and estimated size in bytes, in
`meta`, before and after it runs (staged steps estimate). `wf.preview(step,
rows=(start, stop))` already pages; keep it the one way to read a page.

**Unknown is an answer (owner, 2026-10-26).** For reshaping and dynamic
operations (`expand`, `filter`, `join`, `group`) the size often can't be known
before running. Report that as `unknown` with the reason, so the user sees it,
rather than leaving it blank. Core already has the wording in its plan:
*"expand: how many items … returns per row is only known by running"*.

### K27. Return types: unknown until it runs, then what it returned

**Decided by the owner (2026-10-26):** `Annotated` parameters are fine for
extras (K21). When a tool's return type isn't declared, its type is
**unknown**. Once it has run without error, the type observed is used when
staging later steps; if rows returned different types, the union of them.

**Ask:** `meta["type"]` per output column: declared, else `unknown`, else after
a run the observed type or union. Check first, by running, that core's type
checks look through `Annotated`.

### K28. Cell-to-cell lineage stored in each output

**Decided by the owner (2026-10-26):** each step's output metadata includes
the exact cells that led to each of its cells: which cell maps to which.

**Today** (run on the current pin): `wf.cell(step, row, column)` works this
out on request: `wf.cell("e", 1, "value")` → id `'0.1'`, inputs
`[{'step': 'p', 'id': 0, 'columns': ['n'], 'argument': 'n', ...}]`. Rows made
by `expand` already get child ids (`0.0`, `0.1`, `1.0`, `1.1`) that point at
their parent. The lineage isn't stored with the output.

**Ask:**

- every output stores, per cell, the input cells (step, row id, column) and the
  argument each fed;
- a row from `expand` maps to the same source row as its siblings (as the
  child ids already do);
- when a step re-runs with changed arguments, the cells that are new or
  changed are marked, and the steps downstream show which of their cells came
  from them.

- a tool can return several outputs for one row (a dict or tuple), spread
  into several cells (columns, as `widen` does). Each of those cells maps to
  the same input cells (owner, 2026-10-26).

This is also what K19's row ids and K22's kept versions are built on.

### K29. Renames: references follow, and reading old data warns

**Today** (run on the current pin): `wf.rename("p", "q")` rewrites later
references: `d`'s formula becomes `dbl[mod.map()](wf["q"])` and `d` stays
`completed`.

**Decided by the owner (2026-10-26):** a step that reads data older than its
reference's current output warns the user that it is reading old data (a
stale reference), with the step it read and the version.

### R7. A standard handle for media

**Today:** saving an output that holds an image is refused, clearly.

**Ask:** port the engine's `MediaAsset` / `MediaStore` as the grid's handle,
saved as a content-hashed reference.

### R8. Failed rows turn integer columns into floats

**Today:** `risky` over `n = [1, 2, 3, 2]` gives `out: float64`
(`100.0, NaN, 300.0, NaN`).

**Ask:** use nullable `Int64` (or `object`) for a payload column with failures.

### R9. Stages

**Ask:** a named group of consecutive steps that runs as one, with
`run_stage(name)` and a section in R5's format.

---

## How each ask is verified

Every ask's **Done when** is written as a check that can be run against core.

- **`scripts/core_asks.py`** runs one probe per K-item today. Each C-item's
  "Done when" should become a probe there, so `python scripts/core_asks.py`
  reports the whole list as OPEN/DONE.
- **Core's own tests** should carry the same checks, so a fix can't regress
  after the app adopts it.
- **End-to-end examples** (`examples/all_orchestrations`, and the planned
  example repos) run real formulas through the app against a pinned core.
  They are the regression suite for adoption: bump the pin, run them, and
  any change in behaviour shows up there first.

## Suggested order for core

1. **Priority 1: K1, K2, K3, N2, K4, C10, C11, C13, C14.** Each is a wrong
   answer that looks right, or a failure that spreads further than it should.
2. **The saved-format changes together: C1, C2, C7, C11.** Each changes how a
   value, setting or selection is written in the operation JSON, so do them
   under one version bump (K17).
3. **Planning: C5, then C8 and C9.** Typed columns make the staged grid
   possible; partial plans build on it. C6 is small and can go in anywhere.
4. **The boundary: O, C3, K12, N1.** Small, and they let the app drop the
   engine and most shims.
5. **The rest in table order.**

## What stays on the app's side

- **The `=` formula grammar.** Core has no formula parser; `safe_formula.py`
  and `operation_formula.py` stay local.
- **The formula bar never runs `eval`.** A formula is Python syntax, so
  `__import__("os").system(…)` is also valid Python. The app parses formulas
  with `ast` in expression mode and accepts only the grammar: `wf[…]`,
  `res[…]`, `rows[…]`, `cols[…]`, `mod.…`, tool names, and C11's literals.
  Everything else is refused before anything is evaluated.
- **Reading `grid.catalog()` instead of the engine registry** (C3). This is
  app work and doesn't wait on core.
- **Live resource objects and sessions** (Q1): the app owns them and passes
  them to `run`.

## Old IDs and shim tags

| Old ID / tag | Here |
|---|---|
| 001 §A/§B (select, project) | done; rows → C7 |
| 001 §D, §F · 003 §L · 004 B6 · 120/121 C8 | K10 (done), C1 |
| 001 §G · 004 B6 | done (`join`/`stack`/`zip_`); K11 |
| 002 §4 | settled (`select`/`slice`) |
| 003 §A, §B, §E, §J · `SHIM(core §A,§B,§E,§J)` | done in `grid.catalog()`; shims removed at 9a86a0d |
| 003 §C, §D, §H | not asked (engine) |
| 003 §G · `SHIM(core §G)` | C3.3 (tags) |
| 003 §K · 121 C9 · `SHIM(core §K)` | K12 — done, removed |
| 003 §M · 006 N3 · `SHIM(core §M)` | M — done, removed |
| 003 §N · `SHIM(core §N)` | N — done, removed |
| 003 §O · `SHIM(core §O)` | O — done, removed |
| 003 §P | P |
| 004 B7 / B8 / B9 · 121 C10 | K14 / K15 / K16 |
| 004 C10 | K17 |
| 004 C11 | K18 |
| 120 C1 / C2 / C4 / C5 / C6 | K4 / K5 / K8 / K1 / K2 |
| 120 C3 | K6, K7 (done) |
| 121 C7 / C11 | C7 (as K9) / K3 |
| 006 R1, R2 | done |
| 006 R3–R9, N1, N2 | same IDs here |
| 006 R6 | K1, K2, K3 |
| `dev_plan/117` SR-12, SR-13 (engine `ReferenceResolver` subscripts) | C7 (on the grid's `StepRef`; the engine resolver is retiring) |
| `dev_plan/117` SR-14 (contradiction with 001 §C) | settled by C7: selections are explicit and typed |
| `SHIM(core §A6)` in `grid_runner.py` | K12 (whole-table tools) — done, removed |
| `SHIM(core §C17)` | C17 |
| `SHIM(core §C18)` | C18 |
| `SHIM(core §C21)` | C21 |
| `dev_plan/200` B2 (kernel restart) | C4 |
