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
| **U9** | **Discovered fields are not written into the expression** (owner, 2026-11-23: "I would not do that; I would have hardcoded methods and conditions, conventions, to handle any possible issues"). They are discovered on every run, by the fixed conventions of this page (U10–U24), so every shape the data can take is handled the same way. A step reading a discovered field is checked when it runs: a field it needs that is absent fails that reader's rows, naming the field | not written | **decided** |
| **U10** | Discovered from **mappings**: the **union of the keys, first seen first** | ✓ | decided (pandas) |
| **U11** | Discovered from **sequences**: **positions 0 to the longest − 1**, named `var0`, `var1`, … | tuples ✓ | decided (pandas; tidy T1) |
| **U12** | **Nothing to discover from** (zero rows, every row empty): no fields, **said**; nothing is written until a row has a field | every row `None`: no columns, a warning that the rows held no dict ✓; **zero rows: no columns, nothing said** | proposed |

## C. Uneven rows

| # | Condition | Today | |
|---|---|---|---|
| **U13** | A row **missing** a field: that cell is **absent** | ✓ mappings; **sequences fail (W3)** | decided |
| **U14** | A field **present with the value `None`**: that cell is `None`, known, apart from absent (tidy T9) | ✓ | decided |
| **U15** | A row with a field **not among the declared fields**: **a warning naming the field and the rows**, and the convention applied: the declared fields are kept, the extra one is not added. Where a case can't be handled by a convention, it is **refused, or an error saying what happened** (owner, 2026-11-23: "warn, but have a good convention for what we have currently; do what you can, but refuse or put an error with w…", *the end of the sentence cut off: read as "with what happened"*) | — (pandas drops it silently) | **decided** |
| **U16** | A declared field **missing from every row**: its column is all absent, with a warning | ✓ absent | proposed: the warning |

## D. Names

| # | Condition | Today | |
|---|---|---|---|
| **U17** | A field's name is a **string** (tidy T1). An integer key `1` is named `var1`, as a numeric column name is | **integer keys crash the view (W2)** | decided (T1) |
| **U18** | A key starting with `#` is renamed without it (`#a` → `a`), and said | **the field vanishes silently (W5)** | proposed |
| **U19** | Two fields with **one name** after naming (`1` and `"1"`; `#a` and `a`): **suffixed**, `a`, `a_1`, and said | **the step fails (W6)** | decided (tidy C2) |
| **U20** | A field named like **a column kept beside it**: suffixed the same way, `a_1`, and said; `replace=True` written: the field replaces the column | **the whole step fails**; `replace=True` ✓ | **decided**: suffixed (owner, 2026-11-23) |
| **U21** | Each field keeps **its name and its position** together (tidy T3) | — | decided |

## E. Depth

| # | Condition | Today | |
|---|---|---|---|
| **U22** | **One level** by default: a nested mapping stays a value. **Recursive expansion is an extension**, written (U23) | ✓ | **decided** (owner, 2026-11-23: "yes, but we can add extensions to do the recursive expansion") |
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
| **U29** | **More than 50 distinct fields**, or fields that look like data (dates, ids): **a warning that the keys are probably values**, suggesting **unnest into rows** (`key`, value) instead: the tidy shape | — | **decided**: 50 (owner, 2026-11-23) |

## I. The three places

| Place | Widen there |
|---|---|
| **a step** | `widen` over a column of a table: everything above |
| **on a tool's output** | a tool returning a record or a mapping, its fields as columns (a record by default, today; a mapping after the run). The same conditions, with the fields from the return type where it says them (U8) |
| **on a tool's input** | **the spread**, §J: *new*; wanted, limited and clearly defined (owner) |

## J. The spread: a cell's parts as a tool's arguments

*Owner, 2026-11-23: "yes, but think really specific for now. Frankly some
kind of args or kwargs modifier to properly bind keys to tools makes sense,
but I want this scope limited and very clearly defined."*

**Definition: exactly Python's `f(**mapping)` and `f(*sequence)`, one call
per row, and nothing more.** An input modifier on one argument
(placeholder name `spread`).

| # | Condition | |
|---|---|---|
| **U30** | **Keywords**: a **mapping** cell's (or a record's) keys bind to the tool's parameters **by name**, as `f(**cell)` | proposed |
| **U31** | **Positions**: a **sequence** cell's items bind to the tool's parameters **by position**, as `f(*cell)` | proposed |
| **U32** | **At most one spread of each kind** per step, on one argument; **one level**; a mapping's keys are strings | proposed |
| **U33** | **A key that names no parameter**: that row fails, naming the key, unless the tool takes `**kwargs` (then it is passed). As Python | proposed |
| **U34** | **A required parameter the cell doesn't supply**, and nothing else binds: that row fails, naming it. As Python | proposed |
| **U35** | **A parameter given by the spread and also written**: refused when declared, if the fields are known (declared, or typed); else that row fails, "got multiple values". As Python (conditions.md R8) | proposed |
| **U36** | **Each value is checked against its parameter's type**, as any argument is (conditions.md R11: said when declared if known, the cells that don't fit fail) | proposed |
| **U37** | **A cell that isn't a mapping** (for keywords) **or a sequence** (for positions): that row fails, naming the kind | proposed |

**Out of scope for now:** spreading more than one argument, nested
mappings, renaming keys on the way in, defaults supplied by the spread.

## Decided, 2026-11-23

U9 (not written: fixed conventions instead), U15 (warn, the convention
applied; refuse or an error saying what happened where no convention
fits), U20 (suffixed), U22 (one level; recursive expansion an extension),
U29 (50), the input place (the spread, §J, limited).

## Still to settle

1. **U15**: the owner's sentence was cut off ("refuse or put an error with
   w…"): read as "with what happened". Right?
2. **§J**: the spread's conditions U30–U37, and its name.
