# The rules of the game

> Ten rules for how data moves through a workflow. If you know these, you
> know what core will do. Updated 2026-11-03, in step with the code at
> `d69b5f1`; the detail behind each rule is in [model.md](model.md).

**1. Everything is a grid.** Rows are samples, columns are variables. One
value is a 1×1 grid; a list or dict in a cell is still a grid. A step with
no expression yet (`k["x"] = None`) is **empty**: one cell, `"empty"`, that
nothing can read until it has an expression.

**2. Rows are numbered `0…n-1`, as you see them.** `wf["s"][3]`, `[-1]`,
`[[0, 2]]`, `[1:3]` pick rows by number; a string picks a column,
`wf["s"]["temp"]`, and `wf["s"][0:2]["name", "temp"]` is rows, then columns.
`[0, 2]` is refused: rows 0 and 2 are `[[0, 2]]`. A row you pick is saved as the row
it is, so the pick follows it when rows are sorted or filtered upstream.
Core keeps its own identity for each row; you never see or type it.

**3. Every row remembers where it came from.** Its lineage, `#v`, is the row
of step `v` it came from, carried all the way down:

```
expand(v): items of each row          collapse(by="ward"): one row per ward
#e  #v  #v.idx  value                 #c  #v      ward  value
0   0   0       3                     0   [0, 2]  A     2
1   0   1       30                    1   [1]     B     1
```

Lineage is read-only. To use it as data, copy it: `mod.copy(columns={"#v": "parent"})`.

**4. Choose rows by what they hold, or by where they came from.**
`wf["s"][cols["n"] > 15]` keeps the rows where `n > 15`; `wf["s"][row["v"] == 3]`
keeps the rows that came from row 3 of `v`. A condition that matches nothing
gives zero rows and a warning.

**5. One step, one change.** A step moves its data one level along one axis:
rows ↔ a list, or columns ↔ a dict. Longer changes are several steps.

**6. Anything packs into a cell, and unpacks back, without loss.**

| Pack | Unpack |
|---|---|
| a column → a list: `gather[collapse()]` | `expand` |
| a row → a dict: `pack` | `widen` |

Packing takes anything. Unpacking needs one shape: `widen` takes dicts (a
key a row lacks is absent) or tuples all of one length (`c0, c1, …`, or a
namedtuple's fields), never both, never padded. A list is items: `expand` it.

**7. Rows line up only when they are the same rows.** `zip_` and a column
argument pair each row with the same row, in any order: a step beside its
`map` or its `sort`. Anything else is refused, and core writes the join for
you: a filtered copy, or a child and its parent, meet in
`join(…, on="#v")`. A group meets its rows after unpacking,
`mod.expand(columns=["#v"])`. Equal size is never enough.

**8. You see the shape before you run.** Each step's plan says its rows and
columns, and how to go back: `rebuild`, `trace`, `opaque` or `generated`. A
result that breaks the plan fails.

**9. Nothing is lost silently, and core never guesses.** Filters and
statistics drop values on purpose, but every row still traces back. A `null`
(a value: nothing), `absent` (no value here at all: a key a record lacks, a
`stack` or `join` gap) and `[]` are three different things. Core never tidies
your data and never matches rows by position.

**10. A pick keeps its row.** `wf["p"][1]` picks Ben; insert a row above
him and the pick is rewritten to `wf["p"][2]`. Delete him and the step is
`invalid`, saying Ben is gone, until you pick again.

**11. An edit is checked at once; a run is on request.** Editing a step
re-checks everything after it straight away: a step that can't run is
`invalid`, naming why. A step is checked against what its inputs' expressions
will produce, never against the old values they still show: after
`k["s"] = label[mod.map()](wf["p"])`, a `sort(by="s")` on `s` is fine
before `s` runs. Steps that ran keep their values, marked `stale`, until you
run them again. A step is stale only when its own inputs changed; a step
reading a stale one says so (*read stale 's'*), and `run(x)` runs what `x` needs. Runs go in workflow order.

**12. A step's output is named after it.** `k["temp_f"] = to_f[mod.map()](wf["v"])`
writes a column `temp_f`, and renaming the step renames it; `mod.name("x")`
names it otherwise. A tool that returns a `dict` gives one column per key.

**13. A tool's parameters take columns by name, then by type.**
`double(n: int)` on a step with no `n` takes the one `int` column, and the
step is saved saying so: `double[mod.map()](wf["d"], n=wf["d"][cols["d"]])`.
Two that fit, or none, and the step is `invalid`, writing the binding or a
`mod.cast`. An `int` fits a `float`. A parameter with a default takes a
column only when you bind it. `mod.cast(n="str")` before the verb converts a
column first (to `str`, `int`, `float` or `bool`); a cell that won't convert
fails its row.

*Grouping* is a new index plus a map: `mean_temp[collapse(by="ward")]` packs
each ward's rows into lists, then calls `mean_temp(temp: list[float])` once
per ward, keeping `ward` as a column. Every row lands in a group: a row
with no `ward` (`None`) makes a group of its own, shown, never dropped. To
leave it out, filter it first. Any value is a key: a list or dict groups by
what it holds, `True` is never `1`, and `1` and `1.0` are one key.

## What core can't do, by design

- See inside a tool, or inside a `table` tool's result.
- Remember which item is which in a list a tool rewrote.
- Rebuild the input of a lossy step. You can trace back to it.
- Line up unrelated grids without being told.
- Flatten JSON of any depth in one step: one level per step.
- Follow a picked row when a source's own data is replaced underneath it
  (open: [model.md §10](model.md#10-uncertain-operations-and-their-boundaries)).
