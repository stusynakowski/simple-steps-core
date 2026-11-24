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

**In scope:** reshaping tidy tables (take, nest, unnest, combine,
convert, rename); running tools over them, per row, per group, once, per
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
| **CL8** | **Reactive staging**: what a step will give is known **quickly, before it runs**, enough to build a solid workflow without running any step; what the data alone decides is **marked**, and **an argument makes it exact** (owner, 2026-11-23) | §6: each piece's plan; a test that declares whole workflows, runs nothing, and checks every plan against the run that follows |

## 3. The coverage table: each kind of cell, under each primitive

✓ decided, with its page; · not decided yet; — has no sense there.

| Cell | unnest into columns | unnest into rows | nest | combine (as a key) | take | convert |
|---|---|---|---|---|---|---|
| a unit (number, text) | fails its row (widen U4) | passed through (expand V6) | ✓ | ✓ | compared, sorted (take TK7, TK13) | converted, or fails (convert CV2–CV11) |
| `None` | fields absent (U5) | row kept, item absent (V4) | kept `None` (NS9) | matches nothing (joins JN10) | a test undecided (TK9); sorted last (TK15); a value of its own (TK19) | stays `None` (CV13) |
| absent | fields absent (U5) | row kept (V4) | a marker / missing key (NS9, NS10) | matches nothing (JN10) | a test undecided (TK9); sorted last (TK15) | stays absent (CV13) |
| a sequence | by position (U3) | one row per item (V1) | ✓ | `key(read=)` (nest NS6) | `key(read=)` (TK17, TK20) | to text through JSON (CV12) |
| a mapping | by key (U1) | `key`, value rows (V2) | ✓ | `key(read=)` | `key(read=)` (TK17, TK20) | to text through JSON (CV12) |
| a record | by field (U2) | by field (V3) | a record type (NS12) | `key(read=)` (K1) | as a key: `key(read=)` (K1); in a condition: refused (TK8) | to text through JSON, as a mapping (CV12) |
| an array | a unit (U4) | a unit for now (V7) | ✓ | `key(read=)` (K1) | as a key: `key(read=)` (K1); in a condition: refused (TK8) | to text through JSON, as a list (CV12); its dtype not kept (said) |
| a table in a cell | a unit (U4) | passed through (V6); unnesting later (NS22) | a group as a table (NS20) | refused: a table isn't a key (K1) | as a key: refused (K1); in a condition: refused (TK8) | to text through a named format, later (CV12) |
| a set, a generator | its row fails (U7) | its row fails (V5) | ✓ | a set: `key(read="set")` (K1); a generator: refused | as a key: as the join column; in a condition: refused (TK8) | a set: to text through JSON as a sorted list (said); a generator: refused |
| failed, blocked | blocked (U6) | blocked (V8) | a marker (NS18) | as a key: its row blocked, naming the failure (K2) | a failed test keeps its row, failed (TK11); a failed cell in a condition: the row blocked (K2) | stays failed, not converted (K2) |
| pending (not run) | pending (K3) | pending (K3) | pending (K3) | pending (K3) | pending (K3) | pending (K3) |

**Every square is filled** (2026-11-23, in one pass: owner, "do all in
one pass and confirm"). Three general rules fill the last ones, each
following decisions already made:

- **K1. Any structure used as a key, or compared** (a list, a dict, a
  record, an array, a set: in a group, a join, a sort, `distinct`) needs
  **`key(…, read=…)`** (nest.md §A.1); with none written, refused, naming
  the readings. A table is never a key. In a condition (`>`, `==`), a
  structure is refused when declared (take.md TK8).
- **K2. A failed or blocked cell never becomes a value**: under every
  primitive it stays failed, or blocks what it feeds, naming where the
  failure came from (widen.md U6, expand.md V8, nest.md NS18). Never
  converted, never matched, never compared.
- **K3. A pending cell (its step hasn't run) is never an input at run**:
  running a step brings what it reads up to date first (owner, 2026-11-16).
  Before the run, every primitive's output is pending, and its plan is
  worked out from the plan of what it reads.

## 6. Reactive staging: what is known before the run (for CL8)

*Owner, 2026-11-23: "as long as we have the reactive staging, we have
arguments in the modifiers to change the conditions. The goal is reactive
staging, to know what you are going to get quickly before you run it; you
can still have a solid workflow without running the steps."*

**Quick:** the plan is worked out from the plans of what a step reads,
never by reading cells (grammar.md N9), so it costs the same on a million
rows as on ten. **Solid:** every condition that the plans can decide is
decided **when the step is declared** (a type that can't fit, a key of the
wrong type, a column that isn't there), not at the run. **Honest:** what
only the data can decide is shown as such, with the argument that decides
it in advance.

| Piece | Columns, types | Rows | Known only from the data | The argument that makes it exact |
|---|---|---|---|---|
| take: a position pick, sort | exact | exact | — | — |
| take: a condition, `filter`, `distinct` | exact | at most the input's | which rows | — (`expect(rows=…)` states it) |
| calls per row | exact, **if the tool's return type is written** | exact | the output's type, if untyped | the tool's return annotation |
| widen | **declared or typed**: exact | exact | **discovered fields** | `columns=[…]`, or a record return type |
| expand | exact | **at least the input's** | how many items | `expect(rows=…)` |
| nest | exact (`list[T]`, a record type) | everything: 1; columns: the input's; groups: 1 to the input's | how many groups | `expect(rows=…)` |
| stack, zip, cross | exact | exact (a sum, one origin, a product) | — | — |
| join, by key | exact | **`one_to_one` (the default): a left join exact; inner at most the smaller side** | which keys match | `expect=` the relationship |
| lookup | exact | exact (never changes the rows) | which keys match | — |
| convert | exact (the target) | exact | which cells fail | — |
| pivot | **`names=[…]`**: exact; else from the data | at most the input's | **the names** | `names=[…]` |
| fill | exact | exact | which gaps are filled | — |
| one call per column | exact | one row, or the input's | — | — |

**What a user sees for a step not yet run:** its columns and their types;
its row count, exact or bounded; every problem the plans can show; and,
marked, each thing only the data decides, with the argument that would
decide it now.

## 4. The catalogue of tasks (for CL2)

From blocks.md §4, dplyr and tidyr, and Excel:

| Task | In primitives | |
|---|---|---|
| keep rows by a test; choose columns; sort; distinct; first n | take | ✓ |
| a new column per row; a column beside the others | calls per row, land | ✓ |
| a value per group; per group, beside each row | nest over a group; land | ✓ (beside each row: new, decided) |
| join, stack, zip; every combination | combine | ✓ (cross: new, decided) |
| look a value up in another table (`VLOOKUP`) | lookup | ✓ new, decided |
| wide to long (melt) | nest columns, unnest into rows | ✓ |
| long to wide (pivot) | nest columns **named by a column's values**, unnest | · in scope; conditions proposed (pivot-fill-columns.md §1) |
| a window (running total, lag, rank, rolling mean) | nest over a window, land on its row | · *the scope decided; not built* |
| fill a gap from the row above | take: a cell copied into a gap | · in scope; conditions proposed (§2) |
| split a text column into several; unite several | a tool returning a record; a tool of several parameters | ✓ |
| unnest JSON, one level; every level | unnest | ✓; every level later |
| a formula per cell (`IF`, arithmetic) | a tool | ✓ |
| `$A$1`, a whole column for every row | nest over everything | ✓ |
| a calculation over the whole table | one call, nest the block | ✓ |
| one call per column | calls split over columns, each nested into a list | · in scope; conditions proposed (§3) |

## 5. Where it stands

| Part | State |
|---|---|
| widen, expand, nest, combine | **conditions decided** (widen.md, expand.md, nest.md, joins.md) |
| take, convert | **conditions decided** (take.md, convert.md) |
| pivot, fill, one call per column | **conditions decided** (pivot-fill-columns.md) |
| name | folded into tidy.md (T1–T5) and each primitive's names section |
| call (split), land, execution's primitives | in grammar.md §6 and canonical.md; **their conditions** not pinned down as the four above |
| CL1, the scope | **agreed**, §1 |
| CL4, the coverage table | **every square filled** (§3, K1–K3) |
| the conditions between components | **all decided** (conditions.md, 2026-11-23) |
| CL3, CL5, CL6: the property test | **to build** (roadmap phase 3) |

## Next

The **take** and **convert** pages, which fill the coverage table's last
columns; then **pivot**, **fill** and **one call per column**, the
catalogue's missing tasks, each pinned down as the others were.
