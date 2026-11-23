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
| **NS6** | **A key that isn't a single value** (a list): **three readings**, so with none written it is **refused, naming them**; written with **`key(…, read=…)`**, one reading (§A.1) | grouped by the exact list: `["a", "b"]` and `["b", "a"]` are two groups (run) | raises | **decided** (owner, 2026-11-23); its name in phase 1 |
| **NS7** | **Within a group, the rows' order** is kept | ✓ | ✓ | decided |
| **NS8** | **Zero rows**: zero groups; **everything** over zero rows: **one row holding `[]`** (everything is one piece, even empty) | zero groups ✓; everything: one row holding `[]` ✓ (run) | — | decided: today's |

### A.1 How a key is read: `key(column, read=…)` (accepted, owner 2026-11-23)

Run 2026-11-23: `tags` holding `["a", "b"]`, `["b", "a"]`, `["a", "b"]`,
`["a"]` (x = 1–4), `collapse(by="tags")` gives three groups: `[a, b]` → 1,
3; `[b, a]` → 2; `[a]` → 4. "Group by a list" has three reasonable
readings:

| `read=` | Groups | Opens into (primitives.md) |
|---|---|---|
| `"each"` | `a` → 1, 2, 3, 4; `b` → 1, 2, 3: a row in several groups (usually what is meant: "for each tag, its rows") | unnest the key into rows, then partition; lineage records each row's groups |
| `"exact"` | `[a, b]` → 1, 3; `[b, a]` → 2; `[a]` → 4 (today) | convert each key to a tuple, then partition |
| `"set"` | `{a, b}` → 1, 2, 3; `{a}` → 4 | convert each key to a sorted tuple, then partition |
| a tool, `read=first_tag` | as the tool says ("by the first tag", "by lowercase") | the tool computes each row's key, then partition |

```python
mod.collapse(by=key("tags", read="each"))
mod.collapse(by="tags")          # tags holds lists: refused, naming the readings
```

- **H2**: with no `read=`, several readings: refused, the message naming
  them. Written, one.
- **No behaviour of its own**: each reading is a combination of
  primitives (README.md, the principle).
- **Open-ended**: more readings can be added later; a tool covers the rest.
- **Everywhere a key is used**: `collapse`, `distinct`, `join` and match,
  nesting over `group(by=…)`. One `key(…, read=…)` for all of them.

## B. Gaps and `None` inside

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **NS9** | **Nest columns (pack): a gap becomes a missing key**; `None` stays a key holding `None`. Widen undoes it exactly (widen.md U13, U14) | **both become `None` (NF2)** | `NaN`, `None` | proposed |
| **NS10** | **Nest rows: a gap inside the list is core's own marker**, never shown as a value, and **expand turns it back into absent**, so nest and expand undo each other exactly | **becomes `None` (NF2)**: then expand gives `None` back, not absent | `<NA>` | **decided** (owner, 2026-11-23: "turn back into absent") |

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
| **on a tool's output** | **the outputs gathered into one list** (§E.1): *new*, wanted (owner, 2026-11-23) |
| **a group as a table** | **each group's rows nested into one table cell** (§E.2): *new*, wanted (owner, 2026-11-23) |

### E.1 The outputs gathered into one list

One call per row, then **the outputs nested over a scope** (everything, or
a group by key): "run this per row, and give me the results as one list".
The same as two steps (calls per row, then nest), in one.

| # | Condition | |
|---|---|---|
| **NS17** | The calls are one per row; the outputs are nested over everything (one row out) or over a group (one row per group), as NS2–NS8 | proposed |
| **NS18** | A **failed** call's output is a marker in the list, as a gap is (NS10); expand turns it back into **a failed cell, with its reason** | proposed |
| **NS19** | Lineage: the nested cell names the input rows of its outputs, in order (NS13) | proposed |

### E.2 A group as a table

Each group's rows, **with their columns**, nested into **one cell holding a
table**, for a tool that takes a table per group (a model fitted per
group).

| # | Condition | |
|---|---|---|
| **NS20** | One row per group: the key columns, and one cell holding the group's rows as a table; the table's columns are the block's, **without index columns** (lineage stays outside, on the row: NS13) | proposed |
| **NS21** | The cell's type is a **table type**, its columns and their types, known before the run | proposed |
| **NS22** | **Unnesting a table cell** (its rows and columns back): a later method; until then a table in a cell is a unit (expand.md V6: passed through) | proposed: later |

## To decide

1. ~~NS6~~ decided: `key(column, read=…)`.
3. **NS5, NS9, NS12, NS16**: proposed; accepted unless the owner
   objects.
4. ~~E~~ decided: both wanted (§E.1, §E.2); their conditions NS17–NS22
   proposed.
