# The rules of the game

> Ten rules for how data moves through a workflow. If you know these, you
> know what core will do. The detail behind each rule, with the laws that
> test it, is in [reshaping.md](reshaping.md).

**1. Everything is a grid.** Rows are samples, columns are variables. One
value is a 1×1 grid; a list or dict in a cell is still a grid.

**2. Every row has an id, `#`.** It follows the row through sorts and filters.
Core makes the ids: your tools never see them, and nothing but core can write
a column whose name starts with `#`.

**3. Every row remembers where it came from.** `#v` holds the row of step `v`
it came from:

```
expand(v): the readings of each visit      collapse(by="ward"): one row per ward
#    #v  value                             #  #v         ward  temp
0.0  0   3                                 A  [0, 1, 3]  A     114.6
0.1  0   30                                B  [2]        B     36.9
```

**4. One step, one change.** A step moves its data one level, along one axis:
rows ↔ a list, or columns ↔ a dict. Longer changes are several steps.

**5. Anything packs into a cell, and unpacks back, without loss.**

| Pack | Unpack |
|---|---|
| a column → a list: `gather[collapse()]` | `expand` |
| a row → a dict: `pack` | `widen` |

**6. Rows line up only when core knows how they match.** That means the same
row, or a row beside the one it came from. Anything else is refused: `join` on
a key, or say `zip_(…, match_ids=True)` if you know the ids mean the same
samples. Equal size is never enough.

**7. You see the shape before you run.** Each step's plan says its rows and
columns, and how to go back. A result that breaks the plan fails.

**8. Nothing is lost silently.** Filters and statistics drop values on
purpose, but every row still traces back to the rows it came from. Only you
can drop a trace, by dropping its `#` column.

**9. Core never guesses.** It never tidies your data, never matches by
position, and never reads meaning into an id. Uneven data stays visible: a
`null`, a missing key (`absent`) and an empty list `[]` are three different
things.

**10. Grouping is a new index; a reduction is a map over lists.**
`gather[collapse(by="ward")]` re-indexes by the key and packs: one row per
ward, each column a list of the group's values. A reducer is then an
ordinary `map` over those lists (`def mean_temp(temp: list[float])`), so
`mean_temp[collapse(by="ward")]` is exactly that pack followed by that map.
A parameter named after the key gets the key.

## What core can't do, by design

- See inside a tool, or inside a `table` tool's result.
- Remember which item is which in a list a tool rewrote.
- Rebuild the input of a lossy step. You can trace back to it.
- Line up unrelated grids without being told.
- Flatten JSON of any depth in one step: one level per step.
