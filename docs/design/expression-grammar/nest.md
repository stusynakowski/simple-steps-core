# Nest: the conditions of many cells into one

> **Draft, 2026-11-23, for the owner.** The primitive **nest**, the reverse
> of widen and expand ([widen.md](widen.md), [expand.md](expand.md)), every
> case pinned down. Each condition: what it says, today (run 2026-11-23,
> beside pandas' `groupby(…).agg(list)` and `to_dict`:
> [grid-probes/nest.py](../grid-probes/nest.py)), and **decided** or
> **proposed**. Ids: NS for conditions, NF for findings.

**What nest is:** many cells become **one cell**, their values kept inside
it, none changed. Three forms:

| Form | Many | Into one | Today |
|---|---|---|---|
| **nest rows** | a column's cells, over a scope | a **list** | `collapse` with `gather` (per group; everything) |
| **nest columns** | a row's cells | a **dict**, column name → value | `pack` |
| **nest a block** | rows × columns | a **table** (`DataFrame`) | `table` (the whole block, for a tool) |

**Nest and unnest undo each other** (proposed, NS1): pack a row, then widen
it, gives the row back; nest a column, then expand it, gives the column
back. Every condition below is chosen so that this holds, and a test checks
it on every case.

## A. Scopes: which cells go together

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **NS2** | The scopes are canonical.md §3.1's: **everything**, a **group** (by key), **this row's group**, a **window** | everything ✓; a group ✓; this row's group, a window: **missing** | — | decided (canonical.md) |
| **NS3** | **Groups in the order their keys are first seen** | ✓ | **sorted** by default | decided: core's (the data's order) |
| **NS4** | **A missing key (`None`, absent) is a group of its own** | ✓ | **dropped silently** by default | decided: core's (stricter) |
| **NS5** | **Several keys**, `by=["k", "j"]`: a group per combination, the keys kept as **separate columns** (no tuple keys: tidy.md T5) | **refused: "by= must be str" (NF1)** | ✓, tuple keys | proposed |
| **NS6** | **A key that isn't a single value** (a list): **refused**, naming it: a key is a unit (tidy.md T8) | grouped by value | raises | **to decide**: refused, or grouped by value (today) |
| **NS7** | **Within a group, the rows' order** is kept | ✓ | ✓ | decided |
| **NS8** | **Zero rows**: zero groups; **everything** over zero rows: **one row holding `[]`** (everything is one piece, even empty) | zero groups ✓; everything: one row holding `[]` ✓ (run) | — | decided: today's |

## B. Gaps and `None` inside

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **NS9** | **Nest columns (pack): a gap becomes a missing key**; `None` stays a key holding `None`. Widen undoes it exactly (widen.md U13, U14) | **both become `None` (NF2)** | `NaN`, `None` | proposed |
| **NS10** | **Nest rows: a gap inside the list** | **becomes `None` (NF2)**: then expand gives `None` back, not absent | `<NA>` | **to decide**: `None` kept, or a marker expand turns back into absent (core's own, never shown as a value) |

## C. Types, lineage, names

| # | Condition | Today | |
|---|---|---|---|
| **NS11** | Nest rows gives **`list[T]`**, `T` the column's type (a union if mixed: N1) | ✓ | decided |
| **NS12** | Nest columns gives **a record type**, the columns' names and types, so widen knows the fields **from the type** (widen.md U8) | a `dict` | proposed |
| **NS13** | **Lineage**: the nested cell names the rows it came from, `#d` = `[0, 2]`, in order | ✓ | decided |
| **NS14** | The key columns are **kept**, one row per group; the nested column **keeps its name**; pack's column is named by the step, or written | ✓ | decided |

## D. Before the run (the plan)

| # | Condition | Today | |
|---|---|---|---|
| **NS15** | The columns and their types are **known** (NS11, NS12) | ✓ columns | decided |
| **NS16** | The row count: everything, **exactly 1**; nest columns, **the input's**; groups, **between 1 and the input's** (0 if no rows) | unknown | proposed |

## E. The three places

| Place | Nest there |
|---|---|
| **a step** | `collapse` with `gather`, `pack`: everything above |
| **on a tool's input** | **packing an argument** over a scope (canonical.md `mod.input.nest`): the main use; this row's group and a window are new |
| **on a tool's output** | the outputs gathered into one list: *missing*; to decide whether wanted |
| **a group as a table** | each group's rows nested into **one table cell** (a `DataFrame` per group), for a tool that takes a table per group (a model per group): *new*; to decide |

## To decide

1. **NS6**: a key that is a list: refused (a key is a single value), or
   grouped by value (today)?
2. **NS10**: a gap inside a nested list: `None` (today, pandas), or a
   marker that expand turns back into absent, so nest and expand undo each
   other exactly?
3. **NS5, NS9, NS12, NS16**: proposed; accepted unless the owner
   objects.
4. **E**: the outputs gathered into one list, and a group as a table:
   wanted?
