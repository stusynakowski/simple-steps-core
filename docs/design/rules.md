# The rules of the game

> The rules for how data moves through a workflow. If you know these, you
> know what core will do. Updated 2026-11-09, in step with the code on
> `core-handover`; the detail behind each rule is in [model.md](model.md).

**1. Everything is a grid.** Rows are samples, columns are variables. One
value is a 1×1 grid; a list or dict in a cell is still a grid. A step with
no expression yet (`k["x"] = None`) is **empty**: one cell, `"empty"`, that
nothing can read until it has an expression. That is the only step without
an input: `dbl[mod.map()]` on its own is refused (*map reads a step*), and a
source takes none.

**2. Rows are numbered `0…n-1`, as you see them.** `wf["s"][3]`, `[-1]`,
`[[0, 2]]`, `[1:3]` pick rows by number; a string picks a column,
`wf["s"]["temp"]`, and `wf["s"][0:2]["name", "temp"]` is rows, then columns.
`[0, 2]` is refused: rows 0 and 2 are `[[0, 2]]`. A row you pick is saved as the row
it is, so the pick follows it when rows are sorted or filtered upstream.
Core keeps its own identity for each row; you never see or type it.
A pick can be a tool's input: `to_f(wf["p"]["temp"])`, `double(wf["r"][0:2])`.
In the brackets, `select`, `slice` and `sort` may come before the verb:
`double[mod.sort(by="n"), mod.map()](wf["r"])`.

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

Packing takes anything. Unpacking needs one shape: `widen` takes dicts (by
key, the union of their keys; a key a row lacks is absent) or sequences,
lists and tuples (by position, as wide as the longest row: `var0, var1, …`,
a namedtuple's fields, or `columns=[…]`; a position a row lacks is absent),
never both. A string, a number or an array fails its own row; a set has no
order, so sort it into a list first. A field's name is text (a key `1` is
`var1`, a `#` is dropped); one taken by another field, or by a column kept
beside it, is named `name_1`, and you're told (`replace=True` lets it take
the column's place).
`expand` never loses a row: an empty list, `None` or a gap keeps its row, its item absent, said in a warning; no tool is called for it, and nesting it back gives the empty list again. `expand` takes lists and tuples; a string is one value, and a set has no
order, so sort it first.

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
`stack` or `join` gap) and `[]` are three different things. **A gap in data
you give** (`NaN`, `pd.NA`, `None`) **is absent**: a blank you write is "no
value". Column names are text: two columns with one name are named `a`,
`a_1` (you're told), and hierarchical columns are joined by `_` (`t_am`).
**A conversion keeps the value's meaning, or that cell fails**: `1.7` isn't
an integer, `2` isn't `True`, a huge integer isn't a float; `"2.0"` is 2,
`"yes"` is `True`, and a list becomes text as JSON.
**A column keeps its type as you gave it**: a float column holding
whole numbers and gaps stays float, and you're told to give it as `Int64`
(or convert it) if it's integers. Core never tidies your data and never
matches rows by position.

**10. A pick keeps its row.** `wf["p"][1]` picks Ben; insert a row above
him and the pick is rewritten to `wf["p"][2]`. Delete him and the step is
`invalid`, saying Ben is gone, until you pick again.

**11. An edit is checked at once; a run is on request.** Editing a step
re-checks everything after it straight away: a step that can't run is
`invalid`, naming why. A step is checked against what its inputs' expressions
will produce, never against the old values they still show: after
`k["s"] = label[mod.map()](wf["p"])`, a `sort(by="s")` on `s` is fine
before `s` runs. Steps that ran keep their values, marked `stale`, until you
run them again. **Running brings steps up to date**: `run_all()` and `run(x)`
run only what has never run or is stale, and leave a current step as it is,
so nothing slow is redone; `force=True` runs it again. A tool with no input
(a source) reads the outside world, so running it by name reads it again. A
failure nothing handles still stops `run_all()`, saying so. A step is stale only when its own inputs changed; a step
reading a stale one says so (*read stale 's'*), and `run(x)` runs what `x` needs. Runs go in workflow order.

**12. A step's output is named after it.** `k["temp_f"] = to_f[mod.map()](wf["v"])`
writes a column `temp_f`, and renaming the step renames it; `mod.name("x")`
names it otherwise. So is a value's: `k["limit"] = 38` is a column `limit`,
and so are a source's and the empty step's. A tool that returns a `dict` gives
one column per key; a `DataFrame` keeps its own.

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
what it holds, `True` is never `1`, and `1` and `1.0` are one key. A column you bind yourself, `temp=wf["v"]["am"]`, gets each group's values too, never the whole column.

**14. Formula text means what the Python means.** `formula(text)` reads the
same line Python would and never runs it. Text goes in quotes: a bare name
is a tool, and only where a tool goes, as the tool in front of the brackets
or `mod.sort(by=first_letter)`; `mod.sort(by=n)` is refused, *text needs
quotes, "n"*. A step is `wf["s"]`, a resource `res["db"]`, and a resource may
follow the input by position, as in Python. Settings are literals, or a step;
never a resource.

**15. A saved session is exact, or says where it isn't.** `k.save(folder)`
writes the workflow and, in a folder for each step, the data you gave it or,
with `outputs=True`, its results: its table as a Parquet file you can open
anywhere, and the arrays, images and Plotly figures its cells hold as their
own files, once each; `Kernel.load(folder, catalog)` reads it
back and runs nothing. Anything that couldn't be kept exactly is listed in
the save's report, and a step whose data is missing or changed loads
`invalid`, saying why. A saved result shows as current only if nothing it
was made from has changed: a tool whose code changed shows `stale`.

**16. Steps that do one part of the work can be a stage.**
`k.stage("clean", first="a", last="c")` groups consecutive steps under a
name, to show folded as one big step (`k.stage_status("clean")`) and run
together (`k.run_stage("clean")`). You edit the steps inside it. A stage
changes no result. A step you insert inside it joins it, one you move out
leaves it, and a step is in one stage.

**17. Bulky cells can live on disk.** `Kernel(catalog, spill_over=1_000_000)`
keeps each array, image or figure of a megabyte or more on disk when its step
runs; the cell holds a small handle with a summary ("RGB image 256×256"). A
tool still gets the image itself, and `k.value(step, row, column)` gives it
to you. Results and staleness are the same either way.

**18. Every cell has its recipe, and a staged map's cell can run on its own.**
`k.cell(step, row, column)["recipe"]["formula"]` is the call that makes the
cell, on the cells it read: `add(x=wf["src"][2]["x"], y=wf["src"][2]["y"])`.
Rows are integers, columns strings. A group is its rows (`wf["v"][0:3]["am"]`)
and one of several outputs is indexed (`channels(x=…)["g"]`, an expand's item
`[1]`). `recipe["as_step"]` is the same call written as a step you can
declare. `recipe["by_value"]` is the same call on the values it
read, `add(x=3.0, y=30.0)`: run it and you get the cell. There is none, and
`by_value_because` says why, while a value it reads isn't known, can't be
written (an array, an image), or has changed since the cell ran. `k.run_cell(step, row)` runs one row of a staged `map`: that row
fills in, the rest stay pending, and the step stays staged. The cell keeps to
its row if rows are added or removed above it. It goes stale if a cell it read
changes, and is dropped if the step's formula changes. A full run replaces
it, and a saved session keeps it.

**19. Clearing a step drops its output and keeps its formula.** After
`k.clear(step)` the step is staged again and the steps that read it are stale.
Results core kept for it are dropped too, so its next run calls the tool
again, even if you put the same formula back. `k[step] = None` is different:
it makes the step the empty step, formula and all. A data step's values are
its formula, so clearing one is refused.

## What core can't do, by design

- See inside a tool, or inside a `table` tool's result.
- Remember which item is which in a list a tool rewrote.
- Rebuild the input of a lossy step. You can trace back to it.
- Line up unrelated grids without being told.
- Flatten JSON of any depth in one step: one level per step.
- Tell an edited row from a new one when rows are also added or deleted in the
  same change to a source: core matches rows by their values, so that edited
  row counts as gone (rule 10). A declared key column, to say which row is
  which, is later ([model.md §10](model.md#10-uncertain-operations-and-their-boundaries)).
