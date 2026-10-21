# 010 — The app's asks of core at `b9f66d5`

> **Received from the app** (2026-10-21), after it moved to core `b9f66d5`
> (core 009). Filed here as core's 010. The app tracks them as C21–C27 in its
> `docs/core-proposals/008-core-changes.md`. Progress and answers are in
> [010-status.md](010-status.md).

| # | Ask | Kind | Priority |
|---|---|---|---|
| **C22** | `zip_` refuses grids that share a column name, instead of silently keeping the first | wrong result, silently | **1** |
| **C23** | `collapse(by=…)` naming a column the input lacks is refused at declaration | crash at run | 1 |
| **C27** | `wf.cell(...)["inputs"]` lists every input cell: argument references too, and the columns read | incomplete | 2 |
| **C24** | `wf.cell(...)["inputs"][].state` uses cell states (`known`), not step statuses | inconsistent | 2 |
| **C25** | Per-cell staleness (009 step 7) | feature | 2 |
| **C21** | Make "would this output stop a run" public (still open) | boundary | 3 |
| **C26** | `009-status.md` and `ui-context.md` still call `wf.preview` / `wf.cell` uncommitted | docs | 3 |

## C22. `zip_` silently drops a column both grids have

`zip_(r, d)` where `r` has `city, n` and `d = double_n[mod.map(name="n")](r)`
declared with no problems and ran with columns `['city', 'n']`; `d`'s `n` was
gone. **Ask:** refuse at declaration, naming the shared column(s) and both
steps and how to fix it (rename one side). **Done when:** the zip has a problem
like *"zip_: 'n' is in both 'r' and 'd'; rename one (mod.map(name=…) or
mod.rename)"* and `run` records it invalid.

## C23. `collapse(by=…)` on a missing column crashes at run

`add_total[mod.collapse(by="city", initial=0)](s)` where `s` has only `value`
declared clean, then raised a bare `KeyError: 'city'`. **Ask:** check `by=`
against the input's known columns at declaration (*"collapse groups by
'city', which 's' does not have (it has value)"*); when they aren't known, fail
the step with that message at run instead of raising.

## C27. `wf.cell(...)["inputs"]` is incomplete

`s = scale[mod.map()](r, weight=w[0][cols["w"]])`: `wf.cell("s", 1,
"value")["inputs"]` listed only `r`'s row, not the argument cell (`w` row 0,
column `w`) or the column read (`n`). **Ask:** each input names `step`, `id`,
`columns` and the `argument` it was bound to:

```json
[{"step": "r", "id": 1, "columns": ["n"], "argument": "n", "state": "known"},
 {"step": "w", "id": 0, "columns": ["w"], "argument": "weight", "state": "known"}]
```

## C24. Cell inputs use step statuses for `state`

`"state": "completed"` is a step status; use the cell's state (`known`,
`failed`, `blocked`, …) so the UI reads one vocabulary.

## C25. Per-cell staleness (009 step 7)

Editing one input row should mark only the cells that read it out of date,
not the whole column.

## C21. Whether an output stops a run (still open)

The app re-implements the private `grid._uncaught_failure` rule. **Ask:** make
it public (`Output.uncaught`, or a count).

## C26. Docs behind the code

`009-status.md` and `ui-context.md` say `wf.preview`, `wf.cell` and the
data/states/meta output are uncommitted; they are in `b9f66d5`.
