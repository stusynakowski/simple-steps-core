# Expand: the conditions of unnesting into rows

> **Draft, 2026-11-23, for the owner.** The primitive **unnest into rows**,
> widen's mirror ([widen.md](widen.md)), every case pinned down. Each
> condition: what it says, today (run 2026-11-23, beside pandas' `explode`:
> [grid-probes/expand.py](../grid-probes/expand.py)), and **decided** or
> **proposed**. The same principles: pandas' conventions where they're
> good, stricter where pandas is silent, and an error handled within the
> system over not knowing.

**What expand is:** each row's cell in one column (or several, together)
is opened, and **each item becomes a row**. The row's other columns are
repeated beside each item. **n rows in, one or more rows per input row
out.** The row map is *many from one*: lineage records the input row
(`#d`) and the item's place in it (`#d.idx`). The tidy point: what was one
observation holding several becomes several observations (tidy.md T7).

## A. What it opens

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **V1** | A **sequence** (`list`, `tuple`): one row per item, in order | ✓ | ✓ | decided |
| **V2** | A **mapping** (`dict`): one row per key, the key in a `key` column, the value beside it | ✓ | keys only, **values lost** | decided: core's |
| **V3** | A **record** (`NamedTuple`, `dataclass`): one row per field, like a mapping (`key` = the field's name) | **opened as a plain tuple: rows `1`, `2`, `3`, the field names lost** (run 2026-11-23, **E2**) | — | proposed, as widen opens records by field (widen.md U2) |
| **V4** | **Empty or missing** (`[]`, `()`, `{}`, `None`, an absent cell): **the row is kept, its item absent**, so a row is never lost by unnesting | **the row is dropped**; only `None` is warned (**E1**) | the row kept, `NaN` | **decided** (owner, I2) |
| **V5** | **Not openable as it is** (a `set`: no order; `range`, a generator: lazy): its row fails, naming the fix (sort it, or make a list) | the row fails ✓ | opened | decided (blocks.md §5) |
| **V6** | **A unit** (a string, a number): **passed through as one item**, as pandas does; the column is then **mixed** (lists' items beside the unit), so its type is a union and the mix is said (N1) | the row fails | passed through | **decided** (owner, 2026-11-23: "pass through, but it will be mixed") |
| **V7** | **A 1-D array: a unit, for now** (blocks.md §5): under V6 it **passes through as one item**, whole; a tool says what its parts are. **Opening it like a list is a later method** (*Later*, below) | the row fails | opened | **decided** (owner, 2026-11-23: "assume unit for now, but methods to open like a list later; make a note") |
| **V8** | **A failed or blocked input cell**: one blocked row, naming the failure it comes from | ✓ (one placeholder row) | — | decided |

## B. The rows

| # | Condition | Today | |
|---|---|---|---|
| **V9** | One row per item, **in the item's order**; the input rows in their order | ✓ | decided |
| **V10** | The row's other columns are **repeated** beside each item; `keep=False` written leaves them out | ✓ | decided |
| **V11** | **Lineage**: each row names its input row, `#d`, and the item's place, `#d.idx`; its row id is its parent's, `1.0`, `1.1`, so a later step can line items back up with their row | ✓ | decided |
| **V12** | **More than one column opened together**, with **the same lengths** on a row: item *j* of each in one row | ✓ | decided |
| **V13** | **Several columns, lengths that differ** on a row: **by position to the longest, the missing items absent**, as widen's sequences (widen.md U11, U13) | that row fails | **decided** (owner, 2026-11-23); pandas raises for the whole frame |

## C. Names

| # | Condition | Today | |
|---|---|---|---|
| **V14** | The opened column keeps **its name**; with a tool, the output column is named as a tool's output is | ✓ | decided |
| **V15** | A mapping's keys go in a column named **`key`**; if a column of that name is kept beside it, **suffixed**, `key_1`, and said (tidy.md C2, widen.md U20) | **refused when declared**, clearly | proposed, by the suffix rule already decided |

## D. Depth, types

| # | Condition | Today | |
|---|---|---|---|
| **V16** | **One level**: a nested list's items stay lists. **Recursive expansion is a later layer**, as widen's (widen.md, *Later*) | ✓ | decided |
| **V17** | The items' column type: observed; **mixed** items give a union type, said (N1); **no upcasting** (tidy.md T9) | ✓ union | decided |

## E. Before the run (the plan)

| # | Condition | Today | |
|---|---|---|---|
| **V18** | **The columns are known**: the input's, the opened one, and `key` for a mapping column | ✓ | decided |
| **V19** | **The row count**: unknown until it runs, but with V4 (a row never lost) **bounded below: at least the input's count**. The plan says so | unknown | proposed |
| **V20** | **More than 10,000 items** on one row: a warning naming the row; nothing refused | — | **decided** (owner, 2026-11-23) |

## F. The three places

| Place | Expand there |
|---|---|
| **a step** | `expand` over a column of a table: everything above |
| **on a tool's output** | a tool returning a list (or a mapping): each item a row. The same conditions; `auto` writes it for a tool whose return type is a list (checks.py's rule) |
| **on a tool's input** | each item of an argument's list given to its own call: the same as expand, then a call per row. **Left out for now**: two steps say it plainly |

## Decided, 2026-11-23

V6 (a unit passed through, the column mixed and said), V13 (to the
longest, the missing absent), V20 (a warning past 10,000 items). V3, V15,
V19 accepted, following decisions already made.

**Not symmetric with widen, on purpose:** under expand a unit passes
through as one item (V6), but under widen a unit **fails its row**
(widen.md U4). A unit is one item of a list naturally; it has no fields to
make columns of.

V7 (a 1-D array a unit for now: passed through whole, under V6).

## Later

- **Opening a 1-D array like a list**, one row per element, as pandas
  does: a method added later (owner, 2026-11-23). Until then an array is a
  unit, and a tool says what its parts are.
- **Recursive expansion**: nested lists opened every level down, a layer
  on the one-level primitive, as widen's (widen.md, *Later*).
