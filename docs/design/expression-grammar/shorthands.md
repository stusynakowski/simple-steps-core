# The shorthands: is each one any good?

> **Draft, 2026-11-23, for the owner.** The start of the shorthand map
> (roadmap phase 1b). The full map, each shorthand written out in the
> canonical form, comes once the primitives and their conditions are solid;
> this page judges **whether each of today's verbs is worth keeping as a
> shorthand at all**.

*Owner, 2026-11-23: "I see these as potentially fine modifiers and tools
within an expression. The point is to consolidate multiple primitives
across components into one shorthand verb. They will be built off the
primitives. My question is whether they are any good, or any useful."*

## The tests

A shorthand earns its place when it is:

1. **a common need**: people reach for it often;
2. **one reading**: it opens into exactly one canonical form (H1);
3. **one meaning**: every spelling of a primitive opens into the **same**
   canonical form, and a spelling is **defined only by its mapping**, never
   by code of its own, so two spellings can't drift apart (today they do:
   "take rows" has five spellings, five implementations);
4. **clearly named**: no clash with the grammar's own words.

## Several spellings, one primitive

*Owner, 2026-11-23: "people think in different ways and do the same thing
(same primitives) but write them in different ways. `select` is one of
them, similar to a pick but in functional or modifier form."* Verbs taking
plain values as settings are the norm (dplyr `select(df, x, y)`, pandas
`df.filter(items=[…])`, SQL `SELECT x, y`). So a primitive may have
**several spellings**, each a soft link to it:

| Thinks in | Writes | Opens into |
|---|---|---|
| addresses | `wf["p"][["x", "y"]]` | take columns `x`, `y` of `p` |
| verbs | `select(wf["p"], columns=["x", "y"])` | the same |
| addresses | `wf["p"][0:10]` | take rows 0–9 of `p` |
| verbs | `slice(wf["p"], start=0, stop=10)` | the same |

The UI shows the canonical form whichever was written.

**Layers** (owner: "primitives are valid expressions; we can consolidate
them, or define functions and modifiers built off of them"):

| Layer | Is |
|---|---|
| a primitive | a valid expression on its own, written directly |
| a shorthand | a named composition of primitives (`filter`, `collapse`) |
| *a user's own shorthand* (later) | a composition a user names and reuses; it opens into primitives like any other, so the system stays closed |

## Today's, judged

"Built from" uses the placeholders of canonical.md and primitives.md.

| Shorthand | Built from | Verdict | Why |
|---|---|---|---|
| **`map`** | each row · land on its row | **keep** | the most common of all; known from functional programming |
| **`filter`** | each row · keep or drop its row (a tool's `bool`, or a condition) | **keep** | very common; one name for keeping rows, by a test or by a condition |
| **`expand`** | each row · unnest into rows | **keep** | common (pandas' `explode`) |
| **`collapse(by=)`** | each group · nest over the group · a new row per group | **keep** | the group-by aggregate (Stata's word) |
| **`group`** | each row · land beside the input's columns | **keep the idea, rename** | "add a column, keep the others" (dplyr's `mutate`, pandas' `assign`): very useful; "group" names something else |
| **`table`** | one call · nest the whole block as a table | **keep the idea, rename** | whole-table tools (transpose, describe); "table" names what a step holds |
| **`sweep`** | each combination of settings | **keep** | parameter studies, grid searches: niche, valuable |
| **`source`** | one call, no input | **keep** | loading data: essential |
| **`auto`** | writes the most likely of the others | **keep, as the resolver** | it is H2; never stored as a verb (written as what it chose) |
| **`sort`** | take rows: reorder | **keep** | common; no pick does it |
| **`distinct`** | take rows: one per key | **keep** | common; no pick does it |
| **`drop`** | take columns: all but these | **keep** | easier than listing what to keep |
| **`widen`** | unnest columns (a dict or record) | **keep** | JSON in |
| **`pack`** | nest columns into a dict | **keep** | JSON out; less common |
| **`rename`**, **`name`** | name: as a step, on the output | **merge into one** | one primitive in two places, one word |
| **`cast`** | convert: on the input, or as a step | **keep** | str → float is everyday |
| **`expect`** | a check on the output | **keep** | cheap robustness |
| **`retry`**, **`timeout`**, **`try_except`**, **`breaker`** | one execution primitive each, at a level | **keep, as the primitives themselves** | not consolidations: each is already one primitive (grammar.md §6.4) |
| **`join`** | match by key · join together along columns | **keep** | essential |
| **`stack`** | join together along rows | **keep** | essential |
| **`zip_`** | match by position or by id · join together along columns | **keep, by id only** | pairing by position goes silently wrong when the two orders differ |
| **`select`** (rows, columns) | take | **keep, as the verb spelling of take** | for those who think in verbs; the same as a pick (owner, 2026-11-23) |
| **`slice`** | take rows by position | **keep, as a spelling** | the same as a pick's row part, `wf["p"][0:10]` |
| **`copy`** | take, with lineage columns made data | **keep** | the only way to turn `#p` lineage into ordinary data (grid.md §8); *corrected 2026-11-23: first judged redundant* |

**Count:** all kept, as shorthands or spellings, but two merged into one
and two renamed; `zip_` by id only.

## Useful ones that are missing

Each built from the same primitives (primitives.md):

| Shorthand (placeholder) | Built from | Like |
|---|---|---|
| a group's value beside each row | each row · nest over `group(by=…)` · land on its row | pandas' `transform` |
| a window | each row · nest over `window(n)` · land on its row | rolling means, lags, running totals |
| pivot | partition by a key · nest columns named by a column's values · unnest columns | `pivot_wider` |
| melt | nest columns · unnest into rows | `pivot_longer` |
| a cross product | match all pairs · join together | `crossing` |
| fill | take each missing cell's value from the row above | `fillna(method="ffill")` |
| split | one text column into several (a tool returning a record) | `separate` |

## To settle with the owner

1. The verdicts: anything kept that shouldn't be?
4. **A user's own shorthands**: wanted, and when?
2. Which missing ones are worth adding, and when (phase 5)?
3. Names for the two renamed and the one merged: with the rest of the
   naming (phase 1).
