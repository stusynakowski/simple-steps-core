# Row ids: the rules (K19)

> Decided by the owner, 2026-10-27 (D1, D3, D4; D2 taken as recommended).
> Being built in phase 4, in pieces: **selections — done**; **column arguments — done**; **`zip_` — done**;
> `zip_`; the ids new rows get. *Today* notes were run at `6435a98`. This is what makes a reference keep pointing
> at the same row when the data shifts: selections, column arguments, `zip_`,
> lineage, and later the row-aligned table view all rest on it.

## 1. What a row id is

- A step's output is a DataFrame; **its index is the row ids**. The row
  number `#` is only the position, as displayed.
- **A row keeps its id through every step that keeps it**: `map`, `filter`,
  `group`, `widen`, `sort` and the other reshapes. *Today:* yes.
- **Row ids are unique within a step.** A step whose rows would share an id
  fails, saying which id.
- A row id is an `int` or a `str`. Integers come from counting; strings come
  from `expand` (`"0.1"`: item 1 of row 0) or from a source that names its
  rows (`"Ada"`).

## 2. Which ids new rows get

| Step | Row ids | Today |
|---|---|---|
| a value (`k["x"] = [3, 1, 2]`), a DataFrame assigned in Python | its own index if it isn't the default `0…n-1`, else `0…n-1` | always `0…n-1` |
| a source tool | the index the tool returned, if it isn't the default and is unique; else `0…n-1`. **Decision D2** | always `0…n-1`; the tool's index becomes a column called `index` (G3) |
| `expand` | `"i.j"`: item `j` of row `i` | as proposed |
| `collapse` with no `by` | `0` | as proposed |
| `collapse(by="ward")` | the group's key (`"A"`, `"B"`), so a reference to a group follows it when groups are added or reordered. **Decision D3** | `0…k-1` |
| `sweep` | `0…n-1`, in the order of the combinations | as proposed |
| `table` | the index the tool returned, as for a source | `0…n-1` |
| `join`, `stack` | `0…N-1`; each cell's lineage points at the input rows (decided 2026-10-27) | `0…N-1`, no lineage |

## 3. Selections pick by row id

| Written | Means | Today |
|---|---|---|
| `wf["srt"][0]` | the row whose id is `0`, wherever a sort put it | the row at position 0 |
| `wf["srt"][[0, 2]]` | the rows whose ids are `0` and `2` | positions |
| `wf["e"][rows["0.1"]]`, `wf["n"][rows["Ada"]]` | a row whose id is a string: through `rows[…]`, because a bare string in brackets would read like a column name | not possible |
| `wf["srt"][0:2]` | **Decision D1** (below) | positions |
| an id the step doesn't have | a problem on the step when it's known (`bad_selection`: *"'srt' has no row 9"*); else the step fails when it runs | positions out of range |

**D1: what a slice means.** Two readings, both reasonable:

- **(a) A slice is positions: the first rows.** `wf["srt"][0:2]` is "the top
  two after the sort", which is what a slice usually means to a reader, while
  `wf["srt"][0]` and `[[0, 2]]` are ids. Recommended.
- **(b) Everything is ids.** `wf["srt"][0:2]` is the rows whose ids are 0 and
  1, as the owner first decided (2026-10-25). Consistent, but a slice over
  ids means little once ids are strings or out of order, and "the first n
  rows" then needs another way to say it.

## 4. A column as an argument pairs row by row (K19)

Under a row-wise verb (`map`, `filter`, `expand`, `group`), an argument that
is a column, `scale[mod.map()](wf["p"], w=wf["w"][cols["w"]])`:

| Parameter type | The argument | Today |
|---|---|---|
| a scalar (`float`, `str`, …) or untyped | **one value per row: the row with the same id** | typed: refused (`wrong_shape`); untyped: the whole list for every row |
| `list`, `Series`, `DataFrame` | the whole column, for every row | as proposed |

- A row whose id isn't in the argument's step isn't run: it is `blocked`,
  with the cause *"w: 'few' has no row 2"*. The other rows run, and the run
  doesn't stop (as for a row whose input failed).
- Under `table` and `collapse` a column stays whole.

## 5. `zip_` pairs by row id

`zip_(wf["p"], wf["f"])` puts rows with the same id side by side. The two
steps must have the same ids; otherwise the step fails, naming the rows that
have no match. *Before K19* it already paired by id, strictly, except that
grids sharing no ids at all were paired by position when their lengths
agreed. That fallback is gone: they are refused, pointing to `join`.

## 6. What it changes

- **What saved selections mean.** A selection saved before this picked
  positions; after it, ids. The saved format goes to **version 5**, so a file
  saved with positions is refused rather than silently picking other rows.
  **Decision D4.**
- **Labels.** Where a row is shown with its reference (the table view, G18),
  the label is its id: `wf["srt"][0]` is Ada's row.
- **Lineage (K28)** is built on these ids: each cell points at the input rows
  it came from.

## Decisions

| | Question | Decided |
|---|---|---|
| D1 | A slice `[a:b]`: positions or ids | **Positions**: `wf["srt"][0:2]` is the top two rows (the header isn't a row). Single rows and lists are ids |
| D2 | A source tool's own index: its row ids | Taken as recommended: yes, when it isn't the default and is unique |
| D3 | `collapse(by=…)`'s row ids | **The key**, for its output. And a collapsed row keeps which input rows were in its group, so a change to one of them marks only that group's row stale |
| D4 | Bump the saved format | **Yes**: version 5 (done with the selections piece) |
