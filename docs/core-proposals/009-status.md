# 009 status — what changed in core for the app

> **For the app team, backend and front end.** 2026-10-21. Covers every
> change since the app's current pin, **`9a86a0d`** ("updated phase 5"). The
> design and the owner's decisions are in
> [009-step-output-model.md](009-step-output-model.md); what to draw is in
> [../ui-context.md](../ui-context.md).
>
> **Where the code is:** everything below is in **`b9f66d5`**, the app's
> current pin. Later changes (the app's 010 asks: strict `zip_` columns,
> `collapse(by=)` checks, complete cell inputs, per-cell staleness,
> `Output.uncaught`) are in [010-status.md](010-status.md).

## In short

1. **A step stores only its results.** `map`, `group` and `expand` no longer
   carry their input's columns. Row ids link results back to their inputs.
   `expand` derives ids from the parent (`1.0`, `1.1`).
2. **An output is `data`, `states`, `meta`.** The ledger is gone. `states` is
   one state per cell; `meta["notes"]` holds errors and causes only for the
   rows that have one. `print(output)` shows everything as one grid.
3. **`zip_` pairs rows by id, strictly,** and carries each cell's state.
4. **Stale means an input's data really changed** (data-hash versions).
5. **Auto is the default when no orchestration is written:** saved as
   `mod.auto()`, with a default circuit breaker on row-wise steps.
6. **Known unknowns are shown:** `wf.preview(step)` and `wf.cell(step, row,
   column)`.

---

## Changes that can break the app

Ordered by how likely the app is to hit them.

1. **`output.ledger` no longer exists.** Read `output.states` (per cell),
   `output.row_states` (worst per row) and `output.notes` (row id → note).
   `LEDGER_COLUMNS` is gone; `STATES` replaces it.
2. **A `map`/`group`/`expand` output has only its result column.** Anything
   that read an input column *through* one of these steps must read a
   `zip_(wf["in"], wf["out"])` instead. `group` → `collapse(by=…)` goes
   through that zip.
3. **An implicit step saves `mod.auto()`,** not the verb picked when it was
   written: `score(wf["r"])` saves `{"kind": "auto"}`. The verb it ran as is
   in `output.meta["auto"]["verb"]`. Code that reads the saved stack to find
   the verb must read `meta["auto"]`.
4. **Auto adds `breaker(after=5)` to row-wise steps.** Five failures in a row
   of the same kind stop the step; the rest are marked *"not run: stopped
   after 5 failures in a row (…)"*. A step whose verb is written gets nothing
   added.
5. **`zip_` refuses rows it can't pair** (*"row 2 of 'r' has no matching row in
   'kept'. For a partial match, use join"*). It used to return fewer rows. A
   `zip_` or `join` that can't be made now **fails the step** (and `run_all`
   raises `StepFailed`) instead of raising from `run`.
6. **A `filter` predicate that raises keeps its row,** marked `failed`. It used
   to drop the row. Rejected rows are listed in `meta["excluded"]`.
7. **A direct call on a frame runs over its rows** when the tool's first
   parameter is typed and a frame doesn't fit it: `plus_one(df)` with
   `n: int` returns an `Output`. Tools typed to take a frame, and untyped
   tools, still get the frame as-is.
8. **Re-running a step with an identical result no longer makes later steps
   stale.** Staleness compares data versions.
9. **Saved files are version 3, and sessions changed shape.** Each output
   saves `data`, `states` (per column), `meta` and `notes` (as id/note pairs),
   not `ledger`. Versions 1–2, and sessions saved with a ledger, still load. A
   core at `9a86a0d` refuses version 3 files with a clear message.
10. **`output.failed`** now returns the failed and blocked rows' notes
    (`state`, `error`, `cause`, `caught`), not ledger rows.

## The saved format is now version 3

Files saved by this core say **`"version": 3`** (they contain a `breaker`
modifier, implicit `auto`, and outputs without a ledger). This core reads
versions 1, 2 and 3. A core at `9a86a0d` (which reads 1–2) **refuses** a
version 3 file with a clear message (*"saved in format version 3; this core
reads versions 1 to 2. Upgrade simple-steps-core to load it."*) instead of
half-reading it. This follows K17's rule: when the saved format changes, the
version is bumped and older versions keep loading.

---

## 1. Results only, linked by row id

| Verb | Output | Row ids |
|---|---|---|
| `map` | the result column only | the input's |
| `group` | the key column only | the input's |
| `expand` | the items only | derived from the parent: `"1.0"`, `"1.1"`, nested `"1.0.0"` |
| `filter`, `sort`, `select`, `slice`, `distinct`, `drop`, `rename`, `widen` | carry their columns (they compute nothing new) | the input's |
| `collapse`, `source`, `sweep`, `table` | their own columns | new |

To see inputs beside results: `zip_(wf["readings"], wf["score"])`, by id.
`zip_(wf["items"], wf["readings"])` gives each expanded item its parent row's
columns.

**`zip_` is strict.** Every row of the finest grid must find its row (or
parent row) in every other grid, and every row of a same-level grid must be
used, or the step fails pointing at `join`. Only a parent grid may have rows
nothing points to (a row that expanded to nothing). Grids with unrelated ids
pair by position when their lengths agree.

## 2. An output is data, states, meta

```python
output.data        # DataFrame: the results, typed, indexed by row id
output.states      # DataFrame, same shape: one state per cell
output.meta        # dict, open-ended
output.notes       # = meta["notes"]: row id → note, only where there's one
output.row_states  # Series: each row's worst cell
```

| State | Meaning |
|---|---|
| `known` | has its value (a caught failure **with a default** is known; its note keeps the error) |
| `maybe` | planned; the row may not survive (`filter`) |
| `pending` | planned; the row exists |
| `blocked` | not run: an input cell failed (the note has `cause`) |
| `failed` | its tool raised (the note has `error`) |
| `invalid` | the step can't run |

`stale` is step-level (`meta["stale"]`), shown over known cells; the old
values stay readable.

**A note** (only for rows that have something to say):

```json
{"error": "ValueError: negative", "caught": true}
{"error": "upstream cell s[2] failed", "cause": "s[2]: ValueError: negative"}
{"error": "not run: stopped after 5 failures in a row (ValueError: bad key)"}
```

`attempts` appears only when a unit was retried, and `unit` only when the row
id doesn't already say where the row came from (`collapse` groups).
Per-row timing is no longer kept.

**`zip_` carries states per cell:** a cell that failed in its own step is
`blocked` in the zip, with its cause, while the rest of the row stays
`known`. (`join` and `stack` don't carry states yet.)

**Printing** shows it all:

```
<Output zip · 3 row(s) × 3 col(s), 1 failed>
  city  n  value    state                                   note
0   SF  1    1.5    known
1  NYC  2    3.0    known
2   LA -1   <NA>  blocked  blocked by s[2]: ValueError: negative
```

A staged output prints its plan: `columns city (str), n (int) · rows unknown
until it runs`.

**Size:** for 100,000 rows the states take 0.10 MB (the ledger took
12.9 MB, 16× the data), and there are no notes when every row succeeds.

**Saved session output:**

```json
{"data": {...},
 "states": {"value": ["known", "failed"]},
 "meta": {"auto": {...}, "version": "…", "read": {"r": "…"}, "stale": false, ...},
 "notes": [[1, {"error": "ValueError: negative", "caught": true}]]}
```

## 3. Staleness from data versions

- `wf.version(step_id)` is a 12-character hash of the step's data.
- When a step runs, `meta["read"]` records the version of each step it read
  (`{"r": "47b6…"}`), plus `"res:<name>"` for resources.
- A step is **stale** when something it read has a different version now, or
  is stale itself. An identical re-run, or changing a source and changing it
  back, leaves later steps fresh.
- Stamps survive a saved session. Older sessions without `read` keep the old
  rule (any upstream change marks them stale).

## 4. Auto

- **What it is:** the defaults core applies when a formula doesn't say how to
  orchestrate. It picks the verb from the tool and the data (map, filter,
  collapse, expand, table) and adds default modifiers.
- **Saved as `mod.auto()`**, decided again from the data at each run.
  `meta["auto"] = {"verb", "reason", "provisional"}`: `provisional` is true
  before the run and false after. The reason ends *"…; adds
  breaker(after=5)"* when a breaker was added.
- **`mod.breaker(after=5)`**: stop after N failures in a row of the same kind.
  `after=None` never stops early. A stated breaker replaces auto's.
  `try_except` before `mod.auto()` sits outside the breaker; after it, inside.
- **Writing a verb** (`score[mod.map()](…)`) means no auto and no defaults.
- **Setting:** `grid.settings.implicit_auto` (env
  `SIMPLE_STEPS_IMPLICIT_AUTO=0` to turn it off). Off: `score(wf["r"])` raises
  *"score needs an orchestration: write score[mod.map()](…) or
  score[mod.auto()](…)"*, and direct calls pass frames as-is.

## 5. Showing known unknowns

- **`wf.preview(step_id, rows=(start, stop))`**: `columns` (name, type),
  `rows` (each with `state` and `cells`), `row_count` (the plan's row axis),
  and **`markers`**, the known unknowns to draw in place: *"‹rows unknown — its
  input 'r' doesn't know its row count yet›"*, *"‹0–4 rows — filter keeps at
  most the 4 rows it reads›"*, *"‹+ maybe more columns›"*, *"‹can't run — …›"*.
  Each marker has `because` and `resolve`.
- **`wf.cell(step_id, row, column)`**: one cell's `state`, `type`, `value`,
  `error`, `cause`, `id` and `inputs` (the input cells it came from, by row
  id). Before a run: `unknown` ("row 2, if it exists") with the type and how
  to resolve it. `missing` for a row or column that can't exist.
- A step waiting on an unrun step names it: *"its input 'r' doesn't know its
  row count yet"*, resolve *"run 'r'"*.

## New and changed API

| Name | What |
|---|---|
| `Output(data, states, meta)`, `output.states`, `output.row_states`, `output.notes`, `output.ids_in(*states)` | the output model |
| `grid.STATES` | `("known", "maybe", "pending", "blocked", "failed", "invalid")` |
| `output.view()` | `data` plus `state` and `note` columns |
| `str(output)` | the merged grid, or the plan when staged |
| `wf.preview(step_id, rows=)`, `wf.cell(step_id, row, column)` | what the UI draws |
| `wf.version(step_id)` | the data-hash version |
| `mod.breaker(after=5)` | the circuit breaker |
| `grid.settings.implicit_auto` | the auto setting |
| **removed:** `output.ledger`, `grid.LEDGER_COLUMNS` | use `states` / `notes` / `STATES` |

## What the app should change

1. Replace every `output.ledger[...]` read with `output.states`,
   `output.row_states` or `output.notes`.
2. Anywhere a step's input columns were read from a `map`/`group`/`expand`
   output, read a `zip_` of the input and the result instead.
3. Read the chosen verb from `meta["auto"]`, not from the saved stack, for
   implicit steps.
4. Draw grids from `wf.preview` (columns, row states, markers) and answer
   clicks with `wf.cell`, instead of reconstructing staged grids client-side.
5. Update the app's JSON reader for the new session output shape (`states`,
   `notes` pairs).
6. Re-run the app's `core_asks.py` against the new pin. Its **K1 probe**
   (`select(city, score)` after a map) can't pass under results-only steps;
   core's copy checks the same thing through `zip_`.

## Still open

- `join` and `stack` don't carry cell states; row ids for `collapse`, `join`
  and `stack` (009 recommendation 11).
- Selection *steps* over rows that may not exist yet; `step.references()`;
  per-cell staleness (009 steps 5–7).
- K14 (progress callback), K15 (re-run only failed rows), K16 (results store),
  K18 (enforced timeout).
- The walkthrough notebook still describes the ledger.
