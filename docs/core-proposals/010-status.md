# 010 status — reply to the app's asks at `b9f66d5`

> **For the app team.** 2026-10-21. Answers
> [010-core-asks.md](010-core-asks.md) (the app's C21–C27). Everything below
> was checked by running core with the app's reproduction script and the
> tests in `tests/unit/test_008_asks.py` (`test_C21_*` … `test_C27_*`).
>
> **Where the code is:** all of this is **uncommitted** on top of `b9f66d5`,
> together with the changes under "Also in this change" (none of which are
> in `b9f66d5` either). Commit it, and pin to that commit, before adopting.
>
> 594 tests pass; `python scripts/core_asks.py` reports 35 of 39 asks done.

## Summary

| # | Ask | Status |
|---|---|---|
| **C22** | `zip_` refuses a shared column | **done** |
| **C23** | `collapse(by=…)` on a missing column | **done** |
| **C27** | `wf.cell(...)["inputs"]` lists every input cell | **done** |
| **C24** | input `state` is a cell state | **done** |
| **C25** | per-cell staleness | **done** for row-aligned steps |
| **C21** | "would this output stop a run" is public | **done** |
| **C26** | docs behind the code | **done** |

## C22. `zip_` refuses a column both grids have

- **At declaration**, when the columns are known: *"zip_: 'n' is in both 'r'
  and 'd'; rename one (mod.map(name=…) or mod.rename)"*. The step is
  `invalid`; `wf.run` refuses it.
- **When an input's columns aren't known yet** (an unrun tool-backed source),
  the step declares clean, is re-checked when that input runs, and gets the
  same problem then.
- **At run**, as a last guard, a clash fails the step with the same message.
  It never keeps the first column silently.

## C23. `collapse(by=…)` checks its column

- **At declaration**: *"collapse groups by 'city', which 's' does not have
  (it has value)"*.
- **When the input's columns aren't known yet**, it's checked when they are
  (the same deferral as `select`). If the column is missing only at run,
  the step **fails with that message**, not a bare `KeyError`.

## C27 and C24. Every input cell, with its argument and a cell state

`wf.cell(step, row, column)["inputs"]` is **one entry per binding**:

```json
[{"step": "r", "id": 1, "columns": ["n"], "argument": "n", "state": "known",
  "values": {"n": 2}, "more": 0},
 {"step": "w", "id": 0, "columns": ["w"], "argument": "weight", "state": "known",
  "values": {"w": 1.5}}]
```

| Field | Meaning |
|---|---|
| `step` | the step the cells are in (or `resource` for a resource argument) |
| `id` / `rows` | the row id; `rows` (a list) when the binding reads several, e.g. a `collapse` group or a column argument |
| `columns` | the columns read |
| `argument` | the parameter they were bound to; `"<verb>.<setting>"` for a setting reference (`"select.columns"`); `null` when the step copies the cell without a tool |
| `state` | a **cell** state: `known`, `failed`, `blocked`, `pending`, `stale`, `missing` (C24) |
| `values` | the values read (first 6; `more` counts the rest) |

How each kind of step reports its inputs:
- **A tool step** (`map`, `group`, `filter`, `expand`): one entry per
  parameter that was read from the input's columns. A `**kwargs` tool
  reads every column.
- **A step with no tool** (`select`, `rename`, `sort`, …): the same cell in
  the input; a renamed column names its original (`count` ← `n`).
- **A `zip_` cell:** only the input that supplied that column.
- **A `collapse` row:** the group's rows (`rows`).
- **An `expand` item:** its parent row.
- **Argument and setting references:** the cells their selection reads.
- **Resources:** `{"resource": "llm", "argument": "llm"}`.

Nothing is stored per cell for this; it's worked out from row ids and the
formula. `join` and `stack` don't keep row links yet; their cells report
`"state": "unknown"` with a `because`.

## C25. Per-cell staleness

For **row-aligned** steps (`map`, `group`, `filter`, `select`, `drop`,
`rename`, `sort`, `slice`, `distinct`, `widen`):

- When a step runs, it records a short hash of each input row, over **only
  the columns it reads** (`output.meta["row_reads"]`).
- When the input changes:
  - only rows whose read columns changed are stale: `wf.stale_rows("s")` →
    `[1]`; `wf.preview` and `wf.cell` mark only those cells `stale`;
  - a change to a column the step doesn't read leaves it **fresh**;
  - rows added or removed make every row stale (`wf.stale_rows` → `None`).
- Partial staleness flows on through further row-aligned steps.
- An edited argument, a changed resource, or a non-row-aligned step
  (`expand`, `collapse`, `join`, …) still makes the whole step stale.
- The hashes survive a saved session.

`step.status` is still `stale` while any row is stale.

## C21. Whether an output stops a run

- `output.uncaught`: the row ids whose failure would stop `run_all`. That's
  state `failed`, not `caught`, not `blocked`; a breaker stop counts.
- `output.stops_run`: `bool(output.uncaught)`.
- `run_all` uses the same rule, so the app can drop its copy of
  `_uncaught_failure`.

## C26. Docs

`009-status.md`, `ui-context.md` and `009-step-output-model.md` now say 009 is
in `b9f66d5`. `ui-context.md` shows the new `inputs` shape and per-cell
staleness.

## Also in this change

Two smaller changes from the same session, both uncommitted:

- **A stale value says what it was computed with.** Each run records its
  formula and arguments (`meta["ran_with"]`). `wf.arg_changes(step)` lists
  what's different now (`[{"name": "weight", "was": "1.5", "now": "2.0"}]`;
  an unset argument shows the default it used). A stale cell's `because`
  reads *"stale output · computed with weight=1.5, the default (now 2.0)"*,
  and `wf.preview` adds `computed_with` for the caption.
- **Editing a run step keeps its output**, marked `stale output (updated
  args)`, instead of resetting it to staged. Every stale step also carries a
  short reason (`meta["stale_reason"]`): `updated args`, `input r changed`,
  `resource llm changed` or `r is stale`.

## Changes the app may notice

1. `inputs` entries gained `columns` and `argument`. `values` holds only
   the columns read, not the whole input row. A `zip_` cell lists one input,
   not all of them.
2. A `zip_` of grids that share a column is now `invalid`. It used to
   complete with one of the columns.
3. `collapse(by=…)` on a missing column is a problem or a failed step. It
   used to raise `KeyError` from `run`.
4. Editing one input row may leave some cells of a step `known` and others
   `stale`. Read `wf.stale_rows(step)`, or the per-cell states in
   `wf.preview`, rather than assuming the whole step.
5. Editing a step that has run keeps its old output (stale) instead of
   resetting it to staged.
