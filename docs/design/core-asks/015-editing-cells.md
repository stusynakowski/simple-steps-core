# 015 — The app's asks of core at `adfaf87` (v1.0.3): editing cells, runs

> **Core's answers, 2026-11-20**, each from running the ask's own run on
> `core-handover` at `1ca30f1` (after 1.0.4; the asks follow, as the app sent them):
>
> | # | Status |
> |---|---|
> | **C55** | **by-reference form done** (P7r, after 1.0.4): `k.cell("f", 1, "f")["recipe"]` = `{"formula": 'to_f(temp_c=wf["p"][1]["temp_c"], offset=1.0)', "of": "row", "as_step": 'to_f[mod.map()](wf["p"][1], offset=1.0)'}`. Columns are written as strings, not `cols[…]`. A collapse gives the column over the group's rows (a range where they run on); **expand, decided:** the item indexed, `split(x=wf["src"][0]["x"])[1]` (a record's field the same way, `channels(x=…)["g"]`); a copied cell gives its pick. Staged cells have one. Data, a value, a source, `table`, a combine give the step's formula (`"of": "step"`). `tests/unit/test_cell_recipe.py` runs each recipe back as a step and compares. **Open: the by-value form** (`to_f(38.2, offset=1.0)`) |
> | **C57** | **done** (with P7r, K-cell): for `wf["f"][1:3]`, `wf["f"][-1]` and `wf["f"][["f"]]`, `inputs[0]["row"]` is the row read (1, 2, 0) and agrees with lineage. (A step that reads its input row for row has no lineage to show; its inputs still name the row) |
> | **C53** | **done** (owner, 2026-11-20): **`k.clear(step)`** is move 1: `staged`, the formula kept, readers `stale`, the kept results dropped, so the same formula put back stays `staged` and the next run calls the tool (the ask's test, `tests/unit/test_clear.py`). **`k[name] = None` is move 2** and stays as it is: readers go `invalid`, since the columns they read are gone. A data step can't be cleared (its values are its formula): refused, naming `k[name] = None` |
> | C56 | confirmed, open: `mod.copy` with no `columns=` is invalid. Owner deciding |
> | C58 | confirmed, open: `arr(m: np.ndarray)` under `mod.table()` is called with a `DataFrame` |
> | C59 | holds today: 25,969 reads of `k.view`, `k.cell`, `needs_run` during a 300-row run, 0 errors. Not yet a test or a stated contract |
> | K23 | open: P7d (3) |
> | C48 | open, still: `tool(async def …)` is accepted |
> | C54 | open: `run_stage` takes `force`, not `fresh` |
> | C50, C52 | **done in 1.0.4** (see [014](014-big-sessions.md)) |
> | Housekeeping 1 | **done before this arrived**: `origin/main` is at `v1.0.4` (`6014109`) |
> | Housekeeping 2 | done before this arrived: the guide pins `@v1.0.3`, no commit |
> | Housekeeping 3 | done before this arrived: the guide names no plan number |

> **For simple-steps-core.** From the Simple Steps app, 2026-11-20, while
> planning cell editing (app plans 134, 135) and after making runs
> non-blocking (138 N0–N2). Every result below comes from running core
> alone, at the v1.0.3 tag (`adfaf87`), Python 3.13:
>
> ```bash
> python scripts/core_probes/probe_editing_asks.py
> ```
>
> [014](014-big-sessions.md) holds the big-session asks (C48–C52) and is
> still current. The entries that last are in the app's 008, under the same IDs.

**The rule these asks serve** (app 135): a cell can be typed into only when
it is a value written in the step's formula (an empty step, or a data step).
Every other cell is produced by an expression and is never edited in place.
It can be looked at, copied, or cleared. For that the user has to *see* the
expression behind a cell, and core has to be able to clear and copy.

## Summary

| # | Ask | Kind | Priority |
|---|---|---|---|
| **C55** | Each cell's own expression | new feature | **1** |
| **C53** | Clear a step's output (new finding: the old result comes back) | feature, owner adding | **1** |
| **C57** | `k.cell` inputs are wrong for a sliced input | bug | **1** (C55 builds on it) |
| C56 | A copy step: by value, and/or linked | feature, owner deciding | 2 |
| C58 | A parameter's declared type isn't checked under `mod.table()` | bug | 2 |
| C59 | Reading the kernel during a run stays safe | contract, plus a test | 2 |
| K23 | Progress and cancel as execution modifiers | decided, restated | 2 |
| C48, C54 | `async def` tools; run only a stage's steps | open | 3 |
| C50–C52, C49 | Big sessions (014) | open | C50 is 1 |
| — | Housekeeping | — | now |

Not asked of core: the `table` tool for typed data is the app's (135 §4).
The compact staged table (first rows, `⋮`, last row; or the first row and
`⋮` when the count isn't known) uses the row counts and column types
core's plan already gives.

---

## C55. Each cell's own expression

**Want:** for any cell, the expression that gives **exactly** that cell's
value: one plain call, no modifiers, no bindings left to work out. The app
shows it in the formula bar when a cell is clicked (app direction: "click a
cell to see its formula"). It lets a user check a single value, and it is
where "pull this cell out as a new step" starts.

**Run:** `k.cell("f", 1, "f")` for `f = to_f[mod.map()](wf["p"], offset=1.0)`:

```text
keys:   column, column_number, inputs, lineage, row, state, step, type, value
value:  101.76
inputs: [{"step": "p", "columns": ["temp_c"], "argument": "temp_c", "row": 1,
          "state": "known", "values": {"temp_c": 38.2}, "more": 0}]
```

It has the parts, but not the expression. The two forms wanted, both giving
`101.76`:

```python
to_f(temp_c=wf["p"][1][cols["temp_c"]], offset=1.0)   # by reference: traceable
to_f(38.2, offset=1.0)                                 # by value: what it ran on
```

**Ask:** `k.cell(...)["expression"]` with both forms (say `by_reference`,
`by_value`), for staged cells too (the by-reference form only, while inputs
are pending). Per verb:

| Verb | One cell's expression |
|---|---|
| `map` | the tool on one input row, as above |
| `collapse`, `group` | the tool on that cell's rows: `total(wf["p"][[0, 2]][cols["x"]])` |
| `source` | the whole call (one call made every cell) |
| `expand` | one call made several cells, so "exactly this cell" needs an index into its result. There's no modifier-free way to write that yet: **core to decide** |
| a shape verb (`select`, `sort`, `copy`, …) | a reference to the input cell it came from: `wf["p"][2][cols["temp_c"]]` |

**Test:** evaluating the by-reference expression, and the by-value one, gives
the cell's value for each verb (first, middle and last row, a failed row).

## C53. Clear a step's output (new finding)

Recorded on 2026-11-17; the owner is adding it to core's next version. **New
finding:**

```text
after k["f"] = None:      f staged | g (reads f) invalid
formula put back:         f completed | values [51.0, 101.76, 69.0]   ← the old result
Kernel methods named clear/reset/drop/invalidate: []
```

Core keeps finished results by run key, so a step cleared and given its
formula back is completed again without running. That's right for an undo,
wrong for a clear.

**Ask, both moves:**
1. **Clear the output, keep the formula:** back to `staged`; steps that read it
   go `stale`; the memory is freed; **the kept result is dropped too**, so the
   next run really runs.
2. **Clear to the empty step:** the formula and the output go (the 1×1
   `empty` frame). `k[name] = None` does this today, except readers go
   `invalid` rather than `stale`. Say which is meant.

**Test:** clear, put the same formula back, run: the tool is called again.

## C57. `k.cell` inputs are wrong for a sliced input

**Run:** `g = to_f[mod.map()](wf["f"][1:3])`, cell `g[0]`:

```text
lineage: {"#f": 1}                                         ← right
inputs:  [{"step": "f", "row": null, "rows": [0, 1, 2], "row_numbers": [0, 1, 2]}]   ← wrong
```

`g[0]` was made from `f[1]` alone. Its inputs list the whole of `f`, and no
row.

**Ask:** inputs name the row (or rows) each cell actually read, as lineage
does. C55's by-reference form is built from them.

**Test:** for `wf["f"][1:3]`, `wf["f"][-1]` and `wf["f"][cols[…]]`, `inputs.row`
agrees with `lineage`.

## C56. A copy step

**Run:** core's existing `mod.copy` is a shape verb that keeps lineage and
recomputes with its input. It refuses to run without columns:

```text
step 'q' is invalid and cannot run: copy needs columns= — it has no default, …
```

Editing needs a copy the user can type into. **Two kinds; the owner is
deciding which core gives:**

| Kind | What it is | Editable | App use |
|---|---|---|---|
| **By value** | a new data step holding the values as literals; no link | yes | 135 E8 "Copy as values", then edit |
| **Linked** | today's `mod.copy` | no, it recomputes | a second view of a step |

**Ask:** the by-value copy as one call (it may be "write the current values
as a literal step"); `mod.copy()` with no `columns=` copies every column.
Open question for the owner: does a by-value copy remember its source
(to refresh it later), or is it cut loose?

## C58. A parameter's declared type isn't checked under `mod.table()`

**Run:** `arr(m: np.ndarray)`, called as `arr[mod.table()](wf["n"][1:3])`:

```text
the tool was called with: ['DataFrame'] | step: failed
```

The tool ran with a `DataFrame`, though it declares `np.ndarray`. (The step
then failed for a different, correct reason: under `mod.table()` a tool
returns a table, and this one returns text.) Without `mod.table()`, core
refuses it before the call, with a clear message.

**Ask:** check the declared type before the call under `mod.table()` too,
and refuse it (or convert, if core decides `DataFrame → ndarray` is a
conversion it makes).

## C59. Reading the kernel during a run stays safe

**Run:** a 300-row `map` step running in one thread; another thread reads
`k.view`, `k.cell`, step states and `needs_run` in a loop:

```text
1750 reads during the run, 0 errors
```

**Since 2026-11-19 the app depends on this** (138 N1): while a step runs, the
app answers views and states from the kernel without waiting for the run, so
the user can keep looking at data. A running step's cells read `pending`.

**Ask:** make it part of core's contract, with a test that reads in a loop
during a run and fails on any error or torn state. If core later runs
tools on several threads or processes, these reads stay safe.

## K23. Progress and cancel as execution modifiers (restated)

**Owner, 2026-11-19:** progress changes how a tool is executed, so it is an
execution modifier beside `retry`, `timeout` and `breaker`. Modifiers chain,
so a mapped step with progress shows which cells are pending, running, known
or failed, and how far it has got. It matters most for big mapped steps.
`cancel()` goes with it.

**What the app does until then:** it stops a run by raising a
`BaseException` in the run's thread (`SHIM(core §K23)`). Run on 1.0.3: a
step that never ran is left `staged`; a forced re-run of a completed step
keeps its previous output; finished steps stay `completed`; the next run
completes. An `Exception` raised in a tool is recorded as a failed row, so a
cancel has to be a `BaseException`. Core's cancel should leave the same
states. Evidence in 008 K23.

## Still open from before

- **C48**: `async def` tools are stored as un-awaited coroutines; refuse
  them at declaration, or await them.
- **C54**: `run_stage(name, fresh=False)` runs only the stage's own steps;
  an input outside it that never ran blocks the stage, naming it.
- **C50** (priority 1), **C52**, **C51**, **C49**: big sessions, in 014.
  Update to C50's "why it matters": the app no longer holds the workflow's
  lock for a view during a run, but outside a run a view still takes
  13.5 s on a 1M-row step.
- **K31** (change per call) and **K32** (primitive modifiers with the other
  verbs built on them): decided, longer-term. The owner parked K32 as a lot
  of work.

## Housekeeping

1. **The v1.0.3 tag is only on `core-handover`.** The app's update steps
   check out `origin/main`, which still gives 1.0.2. Merge it, or say if the
   app should follow tags.
2. **`docs/design/app-update-1.0.3.md` §2 pins `5dcdac2`**, where core still
   reports itself as 1.0.2. The app pins `adfaf87`.
3. **The guide's link to `137-core-1.0.3.md` is dead:** the app's plan is
   `140-core-1.0.3.md`.

## Suggested order

1. C55 with C57, and C53: they unblock cell editing.
2. C50: a page costs a page.
3. K23 and C59: progress, cancel, and the read contract.
4. C56 (once decided), C58, C48, C54, then C52, C51, C49.
