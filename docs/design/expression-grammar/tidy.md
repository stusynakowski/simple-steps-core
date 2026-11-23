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
| **T3** | **The canonical form stores the name.** A position is a spelling: `cols[1]` is written down as `cols["am"]` when the step is declared, and shown "am (column 1)" (fixes C1 below) | — |
| **T4** | **No meaningful row index.** Rows have core's hidden ids and shown row numbers; a key is an ordinary column | `set_index`, `reset_index`, an index that is data and isn't |
| **T5** | **No hierarchical columns.** Flattened to string names with a separator (`t_am`), as `json_normalize` does | MultiIndex columns, from `groupby(…).agg(…)` and others |
| **T6** | **One variable per column**: one type per column; a mixed column is said when declared (grammar.md N1) | `object` columns of anything |
| **T7** | **One observation per row.** A move that changes what a row is (nest, unnest, pivot, melt) is written, and lineage (`#<step>`) records it | reshaping leaves no trace |
| **T8** | **One value per cell**, any Python object counting as one; nested and unnested only by written moves (primitives.md) | — |
| **T9** | **A missing value is absent**, apart from `None`; no upcasting (an integer column with a gap stays integers) | `NaN` everywhere, integers upcast to floats |

## Run 2026-11-23: today against the rules

| A data step with | Today | |
|---|---|---|
| integer column names | renamed `var0`, `var1` | ✓ T1 |
| a name starting with `#` | refused, naming why | ✓ T1 |
| an empty name | renamed `var0` | ✓ T1 |
| a meaningful pandas index (`who`) | becomes an ordinary column `who` | ✓ T4 |
| **duplicate names** | refused, but with **a raw pandas error**: "The truth value of a Series is ambiguous" (**C2**) | ✗ T1: a clear refusal, naming the duplicates |
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

## To settle with the owner

1. **T3**: a position written down as the name when declared?
2. **T5**: the separator for flattened names, `_` or `.`?
3. **C2**: duplicate names refused (clearly), or suffixed (`a`, `a_1`)?
