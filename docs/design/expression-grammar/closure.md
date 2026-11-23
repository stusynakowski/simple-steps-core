# Closed within the goals of the tool: what it means, and how it is checked

> **Draft, 2026-11-23, for the owner**, whose "biggest concern is that this
> system is closed within the goals of this tool". "Closed" made into
> criteria that can each be checked, and where each stands.

## 1. The goals (the scope): agreed, 2026-11-23

From the owner's words through these pages:

> **A spreadsheet-like experience: one expression maps sheet to sheet.**
> Cells hold **any Python value**. Tables are **tidy** (rows are samples,
> columns are variables). **Tools are plain Python functions**; core runs
> them over the grid. The user **knows what they will get before running**,
> with **minimal cognitive load**: simple to write, obvious when opened.

**In scope:** reshaping tidy tables (take, nest, unnest, join together,
convert, name); running tools over them, per row, per group, once, per
combination; how each call runs (time, failures, progress, cancel, pace);
reading the data in and showing it.

**Extensions, added later** (owner, 2026-11-23: "pretty much the out of
scope features would be extensions we can add later"): writing to
databases or files as a side effect; streaming and real-time data;
distributing work across machines; charts beyond a figure as a cell's
value. Not excluded: outside the first closed core. What a tool computes
inside itself stays the tool's own.

**In scope, confirmed** (owner, 2026-11-23): pivot, fill, and one call per
column (§4).

## 2. The criteria

| # | Closed means | Checked by |
|---|---|---|
| **CL1** | **The scope is written** (§1), so "within the goals" has an edge | **agreed**, 2026-11-23 |
| **CL2** | **Complete**: every task in scope can be written in the primitives | a catalogue of tasks (§4), each written in primitives, or marked out of scope |
| **CL3** | **Every combination is decided**: every combination of the components' classes (grammar.md §6) is valid, or refused naming its condition (conditions.md) | a property test that generates expressions from the grammar: each runs, or is refused with its condition; never a crash |
| **CL4** | **Every kind of cell, under every primitive, has a defined outcome** | the coverage table (§3), every square filled |
| **CL5** | **Every outcome is visible**: a value; absent; failed, with its reason; blocked, naming where from; or refused, naming the condition. **Never silent** (README.md: an error handled within the system over not knowing) | the property test checks every output cell's state, and every warning |
| **CL6** | **Round trips hold**: nest then unnest gives the cells back (nest.md NS1); every spelling opens into one canonical form; printing then parsing gives the expression back | the property test |
| **CL7** | **Decided once**: an expression's meaning doesn't change after a run (H2); a pick follows its rows and columns by identity (tidy.md T3) | tests that change the data and check the expression's text and meaning |

## 3. The coverage table: each kind of cell, under each primitive

✓ decided, with its page; · not decided yet; — has no sense there.

| Cell | unnest into columns | unnest into rows | nest | join together (as a key) | take | convert |
|---|---|---|---|---|---|---|
| a unit (number, text) | fails its row (widen U4) | passed through (expand V6) | ✓ | ✓ | · | · |
| `None` | fields absent (U5) | row kept, item absent (V4) | kept `None` (NS9) | matches nothing (joins JN10) | · | · |
| absent | fields absent (U5) | row kept (V4) | a marker / missing key (NS9, NS10) | matches nothing (JN10) | · | · |
| a sequence | by position (U3) | one row per item (V1) | ✓ | `key(read=)` (nest NS6) | · | · |
| a mapping | by key (U1) | `key`, value rows (V2) | ✓ | `key(read=)` | · | · |
| a record | by field (U2) | by field (V3) | a record type (NS12) | · | · | · |
| an array | a unit (U4) | a unit for now (V7) | ✓ | · | · | · |
| a table in a cell | a unit (U4) | passed through (V6); unnesting later (NS22) | a group as a table (NS20) | · | · | · |
| a set, a generator | its row fails (U7) | its row fails (V5) | ✓ | · | · | · |
| failed, blocked | blocked (U6) | blocked (V8) | a marker (NS18) | · | · | · |
| pending (not run) | · | · | · | · | · | · |

**Still open:** the **take** and **convert** columns; records, arrays,
tables and failed cells as **keys**; **pending** cells everywhere (a step
reading a step that hasn't run).

## 4. The catalogue of tasks (for CL2)

From blocks.md §4, dplyr and tidyr, and Excel:

| Task | In primitives | |
|---|---|---|
| keep rows by a test; choose columns; sort; distinct; first n | take | ✓ |
| a new column per row; a column beside the others | calls per row, land | ✓ |
| a value per group; per group, beside each row | nest over a group; land | ✓ (beside each row: new, decided) |
| join, stack, zip; every combination | join together | ✓ (cross: new, decided) |
| look a value up in another table (`VLOOKUP`) | lookup | ✓ new, decided |
| wide to long (melt) | nest columns, unnest into rows | ✓ |
| long to wide (pivot) | nest columns **named by a column's values**, unnest | · *missing; in scope* |
| a window (running total, lag, rank, rolling mean) | nest over a window, land on its row | · *the scope decided; not built* |
| fill a gap from the row above | — | · *missing; in scope* |
| split a text column into several; unite several | a tool returning a record; a tool of several parameters | ✓ |
| unnest JSON, one level; every level | unnest | ✓; every level later |
| a formula per cell (`IF`, arithmetic) | a tool | ✓ |
| `$A$1`, a whole column for every row | nest over everything | ✓ |
| a calculation over the whole table | one call, nest the block | ✓ |
| one call per column | calls, split over columns | · *missing; in scope* |

## 5. Where it stands

| Part | State |
|---|---|
| widen, expand, nest, join together | **conditions decided** (widen.md, expand.md, nest.md, joins.md) |
| take, convert, name | **not done**: the next pages |
| call (split), land, execution's primitives | in grammar.md §6 and canonical.md; **their conditions** not pinned down as the four above |
| the conditions between components | conditions.md: R1–R26, many still **proposed** |
| CL1, the scope | **agreed**, §1 |
| CL3, CL5, CL6: the property test | **to build** (roadmap phase 3) |

## Next

The **take** and **convert** pages, which fill the coverage table's last
columns; then **pivot**, **fill** and **one call per column**, the
catalogue's missing tasks, each pinned down as the others were.
