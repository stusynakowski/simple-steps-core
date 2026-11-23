# The primitives: one primitive, three places

> **Draft, 2026-11-23, for the owner.** The organization asked for in the
> consolidation review (grammar.md §8): good classes of restructuring data
> in the grid, and the modifiers organized by them, so that **names come
> last**, from the organization. Nothing here is built, and no name here is
> final.

*Owner, 2026-11-23: "I could see these being tools on their own a user
might want to use as a step, modifying the input for a tool, or modifying
the output of a tool"; "we need good organizations of modifiers based on
what we described, and define good classes of restructuring data in the
grid, so we can build good primitives that encompass these components";
"restructuring and casting methods will be necessary components".*

## 1. The idea

A **primitive** is one way of moving or changing cells, defined once. It
can be used in **three places**, and means the same thing in each:

| Place | Applied to | Written as (full form, grammar.md H7) | Example: *keep rows* |
|---|---|---|---|
| **a step** | a table, on its own | core's tool over the data, `keep[…](wf["p"])` | keep the rows of `p` where `x > 1` |
| **on a tool's input** | an argument's block, **before** the calls | an **input** modifier | give the tool only the rows where `x > 1` |
| **on a tool's output** | the outputs, **after** the calls | an **output** modifier | keep the rows where the tool said yes (today's `filter`) |

So the organization is a table: **the primitives** down the side, **the
three places** across. Each cell of it is one modifier (or one core tool).
A shorthand (a preset) is several cells at once. The calls and the
execution are not primitives that move cells; they are their own classes
(§4).

## 2. The primitives

Built from blocks.md §4's moves (take, nest, unnest, concat; partition and
match), with the two the owner added: **converting** and **naming**. Each
acts along **rows** or **columns**:

| Primitive | Does | Along rows | Along columns | Changes a value? |
|---|---|---|---|---|
| **P1. take** | choose, reorder or repeat, none changed | keep rows by a condition or a test; sort; first n; distinct | choose columns; drop columns | no |
| **P2. nest** | many cells into one cell | a column's cells into a list (over everything, a group, a window) | a row's cells into a dict | no: the values are kept inside |
| **P3. unnest** | one cell into many | a list's items into rows | a dict's or record's fields into columns | no |
| **P4. join together** | tables side by side | one under another (stack) | matched rows side by side (zip, join) | no |
| **P5. convert** | each cell's value into another type | — (cell by cell) | — | **yes**: the one primitive that does, and only when written |
| **P6. name** | the columns' names | — | rename columns; name the outputs | no |

**Working out which rows go together** (not primitives that move cells;
they feed P1, P2 and P4):

| | Gives | Feeds |
|---|---|---|
| **partition** | one table's rows in groups, by a key | nest per group (P2); distinct (P1) |
| **match** | two tables' rows in pairs: by position, by row id, by key, or all pairs | join together (P4) |

## 3. Every primitive in every place, with today's modifiers

`—` means it has no sense there. *Gap* means it makes sense and core
doesn't have it yet.

| Primitive | As a step | On the input | On the output |
|---|---|---|---|
| **P1. take rows** | `filter` with a condition, `slice`, `sort`, `distinct` | the pick's row part (`wf["p"][cols["x"] > 1]`), `select(rows=)`, `slice` | `filter` (the tool's `bool` keeps or drops its row) |
| **P1. take columns** | `select`, `drop` | the pick's column part, `select` | *gap*: keep only some of the output's columns |
| **P2. nest rows** | `collapse` with `gather` | **packing** (to a list, over everything, a group, a window): *gap* as a modifier; today only by `collapse` (a group) | *gap*: the outputs gathered into one list |
| **P2. nest columns** | `pack` | packing a row to a dict: *gap* (blocks.md's `.to_dict()`) | *gap* |
| **P3. unnest rows** | `expand` with `identity` | *gap*: a cell's list given item by item | `expand` (a tool's list into rows) |
| **P3. unnest columns** | `widen` | *gap* | a record's fields into columns (automatic today); `widen` |
| **P4. join together** | `stack`, `zip_`, `join` | *gap*: data from several steps, matched for one call (grammar.md §8, N3) | — |
| **P5. convert** | *gap*: a step that converts a column | `cast` | *gap*: convert the outputs |
| **P6. name** | `rename` | — | `name` |
| (partition) | — | `by=` of a packing, or of `collapse` | — |
| (match) | inside `join`, `zip_` | inside N3 | — |

**What the table shows:**

- **Most gaps are on the input and the output.** Core has most primitives
  as steps, but only some as modifiers, so today a user often needs an
  extra step for what could be a modifier (the two-step z-score, a group's
  value beside each row).
- **The same primitive has different names in different places today**:
  taking rows is `filter` with a condition, a pick's row part, `slice` and
  `select(rows=)` as steps or input, and `filter` with a tool as output.
  One primitive, one name, three places would replace five spellings.
- **Today's names mix classes.** `filter` is P1 as a step and P1 on the
  output; `group` is P6-like (a new column beside) with per-row calls;
  `collapse` is calls per group plus P2 on the input plus a landing on the
  output. These are the presets of §5.

## 4. The classes that aren't primitives

| Class | What it decides | Members |
|---|---|---|
| **call** | how many times the tool runs: zero, one, many; over what (grammar.md §6.3) | one call; one per row; one per group; one per combination of settings |
| **execution** | how the calls are run, each primitive at a level: each call, or the step (grammar.md §6.4) | time limit, progress, on failure, cancel, pace |
| **output's landing** | where each output goes: its row, a new row per call, every row of its scope (grammar.md §6.5) | — |

So a tool's modifiers are of four kinds (grammar.md H7): **input**
(primitives on the input), **call**, **execution** (primitives at a level),
**output** (primitives on the output, and the landing).

## 5. The presets, as cells of the table

Each of today's verbs is a preset: several cells at once.

| Preset today | Call | On the input | On the output |
|---|---|---|---|
| `map` | one per row | — | one cell, on its row |
| `filter` (with a tool) | one per row | — | P1 take rows: keep or drop |
| `expand` | one per row | — | P3 unnest rows |
| `group` | one per row | — | one cell beside the input's columns |
| `collapse(by=k)` | one per group | P2 nest rows, per group (partition by `k`) | one new row per group |
| `table` | one | P2 nest the whole block into a table | the tool's table |
| `sweep` | one per combination | — | one row per combination |

## 6. To settle with the owner

1. **The six primitives**: take, nest, unnest, join together, convert,
   name. Is anything missing (for example *fill*, a missing value from the
   one above; or *split*, one column's text into several), or should two
   be one?
2. **The three places**: does every primitive need all three, or are some
   places never wanted (naming the input; joining on the output)?
3. **Names**: once 1 and 2 are settled, one name per primitive, the place
   given by where it is written (a step, the input, the output). Proposed
   only then.
