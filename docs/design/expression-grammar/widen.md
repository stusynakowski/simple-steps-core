# Widen: the conditions of unnesting into columns

> **Draft, 2026-11-23, for the owner**, who asked: "widen needs really
> robust conditions on how it works; we can tackle that one first." The
> primitive **unnest into columns** (primitives.md §8), every case pinned
> down. Each condition: what it says, today's behaviour (run 2026-11-23,
> [grid-probes/widen.py](../grid-probes/widen.py)), and **decided** or
> **proposed**. Built on pandas' rule for uneven rows, stricter where pandas
> is silent (primitives.md §8), and the tidy rules (tidy.md).

**What widen is:** each row's cell in one column is opened, and its parts
become **columns**: a mapping's keys, a record's fields, a sequence's
positions. **n rows in, n rows out**; the row map is *same* (each output
row is its input row). The tidy point: what was one variable holding
structure becomes several variables.

## A. What it opens

| # | Condition | Today | |
|---|---|---|---|
| **U1** | A **mapping** (`dict`) opens by key | ✓ | decided |
| **U2** | A **record** (`NamedTuple`, `dataclass`, a `TypedDict` instance) opens by field name | ✓ `NamedTuple` | decided |
| **U3** | A **sequence** (`list`, `tuple`) opens by position | ✓ tuples; **lists fail (W1)** | decided (pandas) |
| **U4** | A **unit** (a string, a number, an array, an image, a `DataFrame`) can't be opened: **its row fails**, naming the kind; the other rows run | ✓ strings | decided (N1) |
| **U5** | **`None`, an absent cell, `{}`, `()`**: nothing to open: **its fields are absent**, with a warning counting the rows | ✓ `None`, `{}`; **`()` fails the step (W3)** | decided |
| **U6** | A **failed or blocked** input cell: its fields are **blocked**, naming the failure they come from | — | proposed |
| **U7** | **Not openable as it is** (a `set`, a generator): its row fails, naming the fix | — | decided (blocks.md §5) |

## B. Which fields: the output's columns

| # | Condition | Today | |
|---|---|---|---|
| **U8** | The fields come from **exactly one** place, in this order: **declared** (`columns=[…]`); **the type** (a record's or `TypedDict`'s fields, from the tool's return type); **discovered** from the data | declared ✓; type: only at run (W4); discovered ✓ | decided |
| **U9** | **Discovered fields are written into the expression** after the first run, so they are declared from then on; the shape can't change because the data did | not written | **to decide** |
| **U10** | Discovered from **mappings**: the **union of the keys, first seen first** | ✓ | decided (pandas) |
| **U11** | Discovered from **sequences**: **positions 0 to the longest − 1**, named `var0`, `var1`, … | tuples ✓ | decided (pandas; tidy T1) |
| **U12** | **Nothing to discover from** (zero rows, every row empty): no fields, **said**; nothing is written until a row has a field | every row `None`: no columns, a warning that the rows held no dict ✓; **zero rows: no columns, nothing said** | proposed |

## C. Uneven rows

| # | Condition | Today | |
|---|---|---|---|
| **U13** | A row **missing** a field: that cell is **absent** | ✓ mappings; **sequences fail (W3)** | decided |
| **U14** | A field **present with the value `None`**: that cell is `None`, known, apart from absent (tidy T9) | ✓ | decided |
| **U15** | A row with a field **not among the fields** (declared, or written after discovery): **a warning naming the field and the rows**; not added | — (pandas drops it silently) | **to decide**: warning, or refused |
| **U16** | A declared field **missing from every row**: its column is all absent, with a warning | ✓ absent | proposed: the warning |

## D. Names

| # | Condition | Today | |
|---|---|---|---|
| **U17** | A field's name is a **string** (tidy T1). An integer key `1` is named `var1`, as a numeric column name is | **integer keys crash the view (W2)** | decided (T1) |
| **U18** | A key starting with `#` is renamed without it (`#a` → `a`), and said | **the field vanishes silently (W5)** | proposed |
| **U19** | Two fields with **one name** after naming (`1` and `"1"`; `#a` and `a`): **suffixed**, `a`, `a_1`, and said | **the step fails (W6)** | decided (tidy C2) |
| **U20** | A field named like **a column kept beside it**: suffixed the same way, `a_1`, and said; `replace=True` written: the field replaces the column | **the whole step fails**; `replace=True` ✓ | **to decide**: suffixed, or refused |
| **U21** | Each field keeps **its name and its position** together (tidy T3) | — | decided |

## E. Depth

| # | Condition | Today | |
|---|---|---|---|
| **U22** | **One level** by default: a nested mapping stays a value | ✓ | **to decide**: one level, or all (as `json_normalize`) |
| **U23** | A written **depth** opens more levels, names joined by an **underscore**: `a_z` | — | decided: the underscore (tidy T5) |

## F. Types, rows, the input column

| # | Condition | Today | |
|---|---|---|---|
| **U24** | A field's column type: from the record's type hints if there are any; else **observed**. **Mixed values** give a union type (`int \| str`), said when known (N1). **No upcasting** (tidy T9) | ✓ union, no upcasting | decided |
| **U25** | The opened column is **dropped**, its fields taking its place; `keep_input` written keeps it beside them | dropped ✓ | proposed: the option |
| **U26** | **Lineage and recipes**: each field's cell traces to its input cell and field: `wf["d"][1]["v"]["a"]` | **the recipe names a column the input doesn't have**, `wf["d"][1]["a"]` (found 2026-11-20) | proposed |

## G. Before the run (the plan)

| # | Condition | Today | |
|---|---|---|---|
| **U27** | **Declared or typed** fields: the plan knows the columns and their types, **exact** | declared ✓; **typed: not (W4)** | decided |
| **U28** | **Discovered** fields, before the first run: the plan says **"columns not known until it runs"**; a step reading one of them is shown **assumed**, checked once known | **a reader is accepted with no check** | decided (primitives.md §8) |

## H. Keeping tables tidy

| # | Condition | Today | |
|---|---|---|---|
| **U29** | **Many distinct fields** (say, more than 50), or fields that look like data (dates, ids): **a warning that the keys are probably values**, suggesting **unnest into rows** (`key`, value) instead: the tidy shape | — | **to decide**: the threshold |

## I. The three places

| Place | Widen there |
|---|---|
| **a step** | `widen` over a column of a table: everything above |
| **on a tool's output** | a tool returning a record or a mapping, its fields as columns (a record by default, today; a mapping after the run). The same conditions, with the fields from the return type where it says them (U8) |
| **on a tool's input** | a mapping cell's fields given to the tool's parameters by name: *new*; to decide whether it is wanted |

## To decide

1. **U9**: discovered fields written into the expression after the first
   run?
2. **U15**: a field not among the fields: a warning, or refused?
3. **U20**: a field named like a column kept beside it: suffixed (as
   duplicates are, tidy C2), or refused?
4. **U22**: one level by default, or every level?
5. **U29**: the threshold for "the keys are probably values".
6. **The input place** (§I): wanted?
