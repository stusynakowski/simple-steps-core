# Tidy tables, enforced

> **Draft, 2026-11-23, for the owner.** The rules core holds every table
> to, and where they tweak pandas' conventions. Everything the grammar does
> (picks, binding, nesting, unnesting) assumes them.

*Owner, 2026-11-23: "I want to make minor tweaks to the pandas framework. I
find the pandas syntax rather frustrating at times … I stand with column
names being strings; however, we can reference them via indices if we have
a good method for the structure … like the index `loc`, but for columns.
The point is to work really hard to enforce the tidy tables principle."*

## The rules

| # | Rule | pandas, by contrast |
|---|---|---|
| **T1** | **Every column has a name: a string**, unique, not empty, not starting with `#` (core's index columns) | labels can be integers, tuples, duplicates |
| **T2** | **A column is addressed by its name or by its position**: `cols["am"]`, `cols[1]`, `cols[1:3]`, `cols[-1]`. **A string is always a name, an integer always a position**, so they can't be confused | `df[0]` is the *label* 0; a position needs `iloc` |
| **T3** | **A column's name and position are kept together** (owner, 2026-11-23). Both are written down when the step is declared, and shown "am (column 1)". **The name is what the pick follows; the position is rewritten when the column moves**, as a row's number is. If the name is gone, the pick is refused, naming both: it never falls back to whatever is at that position now (fixes C1 below) | — |
| **T4** | **No meaningful row index.** Rows have core's hidden ids and shown row numbers; a key is an ordinary column | `set_index`, `reset_index`, an index that is data and isn't |
| **T5** | **No hierarchical columns.** Flattened to string names joined by an **underscore**, `t_am` (owner, 2026-11-23), as `json_normalize` does with its separator | MultiIndex columns, from `groupby(…).agg(…)` and others |
| **T6** | **One variable per column**: one type per column; a mixed column is said when declared (grammar.md N1) | `object` columns of anything |
| **T7** | **One observation per row.** A move that changes what a row is (nest, unnest, pivot, melt) is written, and lineage (`#<step>`) records it | reshaping leaves no trace |
| **T8** | **One value per cell**, any Python object counting as one; nested and unnested only by written moves (primitives.md) | — |
| **T9** | **A missing value is absent**, apart from `None`; no upcasting (an integer column with a gap stays integers). **In data given, every gap is absent** (F1), and **a column keeps its dtype** (F2): integers with a gap are given as `Int64`; a float column of whole numbers and gaps is warned, not converted (built 2026-11-25) | `NaN` everywhere, integers upcast to floats |

## Run 2026-11-23: today against the rules

| A data step with | Today | |
|---|---|---|
| integer column names | renamed `var0`, `var1` | ✓ T1 |
| a name starting with `#` | refused, naming why | ✓ T1 |
| an empty name | renamed `var0` | ✓ T1 |
| a meaningful pandas index (`who`) | becomes an ordinary column `who` | ✓ T4 |
| **duplicate names** | refused, but with **a raw pandas error**: "The truth value of a Series is ambiguous" (**C2**) | ✗ T1. **Decided** (owner, 2026-11-23): **suffixed**, `a`, `a_1`, `a_2` (the next free number, if `a_1` is taken), and said |
| **MultiIndex columns** | named **`"('t', 'am')"`**, the tuple as text (**C3**) | ✗ T5: flattened, `t_am` |

Columns by position (run): `cols[1]` → `am`; `cols[1:3]` → `am`, `pm`;
`cols[[0, 2]]` → `name`, `pm`; `cols[-1]` → `pm`; `cols["am":"pm"]` → `am`,
`pm`. Each written back as typed.

**C1, a position pick's text and its meaning come apart.** A pick
`wf["p"][cols[1]]` declared when `p` was `name, am, pm` gives `am`. After a
column `id` is inserted in front, it **still gives `am`** (it follows its
column), but its text is unchanged; a fresh `wf["p"][cols[1]]` on the same
table gives **`name`**. Two identical texts, two columns (H1 broken). Row
picks don't have this problem: their numbers are rewritten as rows move.
T3 is the fix: the name is written down.

## Decided

- **T3**: a column's name and position kept together; the name followed,
  the position rewritten (owner, 2026-11-23: "position and name, they
  should be kept together").
- **T5**: an underscore joins flattened names. The same separator for
  nested mappings unnested more than one level (primitives.md §8).
- **C2**: duplicate names suffixed, `a`, `a_1`, `a_2`, and said.
