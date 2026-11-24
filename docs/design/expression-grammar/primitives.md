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

> **Names decided 2026-11-23/24** ([names.md](names.md)): the placeholders on this page are **take, nest, unnest, combine** (its forms **append, align, join, cross, lookup**), **convert, rename**; previous terms kept in [spellings/](spellings/README.md).

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
| **P4. combine** | tables side by side | one under another (stack) | matched rows side by side (zip, join) | no |
| **P5. convert** | each cell's value into another type | — (cell by cell) | — | **yes**: the one primitive that does, and only when written |
| **P6. rename** | the columns' names | — | rename columns; name the outputs | no |

**Working out which rows go together** (not primitives that move cells;
they feed P1, P2 and P4):

| | Gives | Feeds |
|---|---|---|
| **partition** | one table's rows in groups, by a key | nest per group (P2); distinct (P1) |
| **match** | two tables' rows in pairs: by position, by row id, by key, or all pairs | combine (P4) |

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
| **P4. combine** | `stack`, `zip_`, `join` | *gap*: data from several steps, matched for one call (grammar.md §8, N3) | — |
| **P5. convert** | *gap*: a step that converts a column | `cast` | *gap*: convert the outputs |
| **P6. rename** | `rename` | — | `name` |
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

1. **The six primitives**: take, nest, unnest, combine, convert,
   name. Is anything missing (for example *fill*, a missing value from the
   one above; or *split*, one column's text into several), or should two
   be one?
2. **The three places**: does every primitive need all three, or are some
   places never wanted (naming the input; joining on the output)?
3. **Names**: once 1 and 2 are settled, one name per primitive, the place
   given by where it is written (a step, the input, the output). Proposed
   only then.

## 7. What we have, and what is missing

*Owner, 2026-11-23: "what are the primitives we have, and what are we
missing?"* By component (conditions.md, *Each component's own primitives*):

| Component | Primitive | Have today | Missing |
|---|---|---|---|
| **input** | bind | by name, by position, written | — |
| | take | the pick's rows and columns | — |
| | convert | `cast` | — |
| | nest | only inside `collapse` (per group) | over everything, a window, this row's group, written on the argument |
| | match | only as a `join` step | another step's rows matched inside one call (grammar.md N3) |
| **call** | split | one; each row; each group; each combination | each column |
| **execution** | time limit | per attempt (`timeout`) | the whole step |
| | on failure | retry, a default, stop after n | — |
| | progress, cancel, pace | — | all three (the app's K23) |
| **output** | land | its own row; a new row per call | every row of the group |
| | unnest into rows | `expand` | a row whose list is empty kept (I2) |
| | **unnest into columns** | `widen`; records | **uneven rows: §8** |
| | take, name | `filter`; `name` | convert on the output |
| **as steps** | take, sort, distinct, nest, unnest, combine, name, copy | all | pivot (nest named by values), a cross product (match all), fill, convert |

## 8. Unnest into columns, and uneven rows

*Owner, 2026-11-23: "I believe the widen component is a key problem, and I
think we can fix it with having good primitives (with additional
modifications to the other components if necessary)"; "I see it as a
problem with the potential for data to be uneven across rows."*

**The root:** unnesting into columns is the one move whose **output
columns come from the data**, and rows can disagree: different keys,
different lengths, different kinds. So the columns aren't known until every
row is read, and each row can disagree with the others.

**Run 2026-11-23** ([grid-probes/widen.py](../grid-probes/widen.py)):

| Cells | Today |
|---|---|
| ragged dicts `{a}`, `{a, b}` | ✓ columns `a`, `b`; row 0's `b` absent |
| a dict and `None` | ✓ the `None` row's fields absent, with a warning |
| a dict and a string | the string's row fails, the dict's works ✓ |
| a nested dict | ✓ one level: the inner dict stays a value |
| tuples `(1, 2)`, `(3, 4)` | ✓ `var0`, `var1` |
| records (`NamedTuple`) | ✓ `r`, `g`, `b`, at run |
| declared `columns=["a", "b"]`, a key missing | ✓ in the plan before the run; the missing key absent |
| **lists** `[1, 2]`, `[3]` | **every row fails** (W1), though the docstring says lists widen by position |
| **integer keys** `{1: …, 2: …}` | **the view crashes**, `KeyError: 'var1'` (W2) |
| **ragged tuples** `(1, 2, 3)`, `(4,)` | **fail** (W3), where ragged dicts give absent cells |
| **the plan, before the run** | **no widened column**, even for typed records (W4); a step reading one is accepted without a check |
| a string, an array | no columns; the column dropped silently (I1, blocks.md §5) |

**Proposed: the primitive, defined once, the same for every kind of cell.**

1. **The fields come from exactly one place**, in this order:
   **declared** (`columns=[…]`, works today); **from the type** (a record's
   or a `TypedDict`'s fields, from the tool's return type); **discovered**
   from the data on the first run, then **written into the expression**, so
   declared from then on (H2: decided once, written down, never re-guessed).
   Uneven data then can't make a step's shape unstable.
2. **A row missing a field: absent cells**, for mappings and sequences
   alike (fixes W3). Unevenness never fails a row and never drops one.
3. **A row with a field not in the fields: a warning naming it.** Nothing
   is added silently.
4. **A cell that can't be opened** (a unit: a string, an array; blocks.md
   §5) **fails its row**, with the reason; the other rows run (grammar.md
   N1). Fixes I1.
5. **Sequences open by position**, a list as a tuple (fixes W1); **keys
   that aren't strings are named by a convention** (fixes W2).

**The other components, changed to support it:**

| Component | Change |
|---|---|
| the plan (staging) | carries the fields from types and declarations (W4) |
| the surface (`auto`) | writes the discovered fields into the expression after the first run |
| a step reading a field not known yet | shown as **assumed**, checked once known, not accepted silently |

### pandas' conventions, and where core is stricter

*Owner, 2026-11-23: "consider the conventions on how pandas handles these
issues; I know they can."* Run on the same cases, pandas 3.0.6
([grid-probes/pandas_widen.py](../grid-probes/pandas_widen.py)):

| Case | pandas | core today | Proposed |
|---|---|---|---|
| ragged mappings | the union of the keys, first seen first; missing → `NaN` | the union; missing → absent | **as pandas**; missing stays **absent** (pandas can't tell a gap from `None`) |
| ragged sequences (lists, tuples, arrays, `str.split(expand=True)`) | **by position, as wide as the longest row**; missing → `NaN` | lists fail (W1); ragged tuples fail (W3) | **as pandas**: by position, to the longest; missing → absent |
| records, dataclasses | their field names | ✓ at run, not in the plan (W4) | the same, and from the type before the run |
| a `None` row | `json_normalize`: its fields missing | absent, with a warning | keep |
| a value that can't be opened, among mappings | `.apply(pd.Series)` **adds a column `0` holding it, silently**; `DataFrame(…)` raises | its row fails, with the reason | **stricter**: keep core's |
| a key not in declared columns | `DataFrame(…, columns=[…])` **drops it, silently** | — | **stricter**: a warning naming it |
| integers with a gap | **upcast to float** (`1` → `1.0`) | nullable: `1` stays `1` | keep core's |
| integer keys | integer column labels | the view crashes (W2) | core's own rule, column names are strings and numeric ones become `var<n>` (grid.md §7), applied everywhere |
| nested mappings | `json_normalize`: **every level**, `a.z.q` (`sep=`, `max_level=`) | one level; the inner mapping stays a value | **one level by default**; a written depth and separator, as `json_normalize`'s |
| `explode` of `[]`, `None` | **the row kept**, `NaN` | the row dropped (I2) | as pandas: the row kept, its item absent (owner, I2) |

**So the rule for uneven rows is pandas'**: mappings unnest **by key, the
union of the keys**; sequences **by position, as wide as the longest row**;
anything missing is a gap. **Where pandas is silent, core is stricter**: an
unopenable value fails its row; an extra key against declared fields is
warned; a gap is absent, never an upcast `NaN`.

To settle with the owner: discovered fields written into the expression
after the first run (rule 1); an extra field a warning, not a refusal (rule
3); nested mappings one level by default, with a written depth (the
separator decided: an underscore, as tidy.md T5).
