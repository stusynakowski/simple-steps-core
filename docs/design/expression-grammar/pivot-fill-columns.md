# Pivot, fill, and one call per column

> **Draft, 2026-11-23, for the owner.** The three tasks closure.md §4 found
> missing, all in scope (owner, 2026-11-23), each **built from the
> primitives** and pinned down as they were. Core has none of them today
> (pivot is refused: `gather_dict` needs columns named `key` and `value`),
> so beside each is pandas' convention, run 2026-11-23
> ([grid-probes/pivot_fill_columns.py](../grid-probes/pivot_fill_columns.py)).
> Each follows the principles (README.md): a reasonable default and an
> argument for the other way; an error handled over not knowing.

## 1. Pivot: long to wide

**Built from:** partition the rows by the row key; nest each group's values
into columns **named by the names column's values**; unnest into columns.
The reverse of melt (nest columns, unnest into rows): **pivot then melt
gives the rows back** (as nest.md NS1).

```python
pivot(wf["long"], rows="who", names="when", values="temp")
#  who  when  temp           who   pm    am
#  Ada  pm    37.4    →      Ada   37.4  37.0
#  Ada  am    37.0           Ben   ·     39.5      (· absent)
#  Ben  am    39.5
```

| # | Condition | pandas | |
|---|---|---|---|
| **PV1** | **One row per row key**, in the order first seen (nest.md NS3); several keys allowed (NS5) | sorted | decided |
| **PV2** | **One column per distinct name**, in the order first seen; a name is **its value's text** (`2020` → `"2020"`), held to tidy.md T1 (no `#`, duplicates suffixed); **`prefix=`** written puts text before each (`prefix="year_"` → `year_2020`) | sorted; integers kept | decided |
| **PV3** | **Several value columns**: names joined by an underscore, `temp_am`, `pulse_am` (tidy.md T5) | tuple names, `('temp', 'am')` | decided |
| **PV4** | **A combination with no row** (Ben, pm): its cell **absent** | `NaN` | decided |
| **PV5** | **Two rows for one combination** (Ada, am twice): **refused by default**, naming the key and the name (as joins.md JN9's `one_to_one`); **`agg=` written** combines them: a tool, or `"list"` (nested), `"first"`, `"last"` | `pivot` raises; **`pivot_table` averages silently** | decided |
| **PV6** | **A missing name** (`None`, absent): those rows are **dropped and said** by default; **`missing_name="keep"`** puts them under a column named for missing (said) | **a column named `nan`, silently** | decided |
| **PV7** | **More than 50 names**: a warning that the names are probably values, as widen.md U29 | — | decided |
| **PV8** | **Before the run**: the columns are known only from the data, as widen's discovered fields (widen.md U9, U28); **`names=[…]` written** declares them, exact | — | decided |
| **PV9** | **Lineage**: each output row names its input rows (nest.md NS13) | — | decided |

## 2. Fill: a gap from the nearest value

**Built from:** take, a cell copied into a gap. **No value is changed and
none is made up**: a filled cell holds a copy of a known cell, and its
recipe is that cell's pick (`wf["d"][1]["x"]`).

| # | Condition | pandas | |
|---|---|---|---|
| **FL1** | A gap takes the nearest known value **above** (`direction="down"`, the default) or **below** (`"up"`), in the table's current order | `ffill`, `bfill` | decided |
| **FL2** | **What a gap is**: absent and `None`, by default (a blank, as a user sees it); **`only="absent"`** leaves `None` as a value (tidy.md T9) | `NaN`, `None` | decided |
| **FL3** | **Within groups**: **`by=`** written keeps a fill inside its group. **Without `by=`, the whole column is one run**, and opened, the expression says so ("fills over the whole column": H1). **No guessing at a group key**: a heuristic warning would be noisy and sometimes wrong (H2) | **crosses groups silently** without `groupby` | decided |
| **FL4** | **A gap with nothing above it** (the first rows): stays a gap, said | stays `NaN` | decided |
| **FL5** | **`limit=n`**: at most n gaps in a row filled from one value | `limit=` | decided |
| **FL6** | **A failed cell is not a gap**: not filled; a failure stays visible | — | decided |
| **FL7** | **Each filled cell's recipe** names the cell it was copied from (blocks.md: a copied cell's recipe is its pick) | — | decided |

## 3. One call per column

**Built from:** calls split **over columns** (a new split, grammar.md
§6.3); each call gets one column's cells, **nested into a list** (nest over
everything, for that column); the outputs land by their length.

```python
centre[mod.call.each_column(cols[["a", "b"]])](values=…)
```

| # | Condition | pandas | |
|---|---|---|---|
| **PC1** | One call per chosen column; the tool's parameter takes the column's cells as **a list** (`list[float]`); optionally a parameter `column` gets the column's name | `apply(axis=0)`: a `Series` | decided |
| **PC2** | **One value per call**: lands as **one row**, a column per input column (a summary: a mean, a count) | a `Series` | decided |
| **PC3** | **As many values as rows**: lands **on the rows**, the same shape (a transform: centring, ranking) | the same shape | decided |
| **PC4** | **Any other length**: that column's cells **fail**, "returned 2 values for 3 rows"; **`land="list"`** keeps the output as one cell instead | **a table of the other length, silently: the rows no longer match** | decided |
| **PC5** | The output columns **keep the input columns' names** | the same | decided |
| **PC6** | **A call that fails**: that column's cells fail, with the reason; the other columns run | raises | decided |
| **PC7** | **Lineage**: PC2 names every input row; PC3 keeps each row's own | — | decided |

## Decided, 2026-11-23

*Owner: "add conditions for each of them, defaulting to what you think
makes the most sense."* Every condition above is decided as written, each
with its default and its argument for the other way:

| # | Default | The other way, written |
|---|---|---|
| PV2 | a name is its value's text | `prefix=` |
| PV5 | two rows for one combination refused | `agg=`: a tool, `"list"`, `"first"`, `"last"` |
| PV6 | rows with a missing name dropped and said | `missing_name="keep"` |
| PV8 | columns discovered from the data | `names=[…]`: declared |
| FL1 | filled from above | `direction="up"` |
| FL2 | a gap is absent or `None` | `only="absent"` |
| FL3 | one run over the whole column; no guessing at groups | `by=` |
| FL5 | every gap in a run filled | `limit=n` |
| PC4 | an output of another length fails its cells | `land="list"` |
