# Combine: the conditions of putting tables side by side or one under another

> **Draft, 2026-11-23, for the owner.** The primitive **combine**,
> with **match** (which rows go together across tables), every case pinned
> down. Each condition: what it says, today (run 2026-11-23, beside pandas'
> `concat` and `merge`: [grid-probes/joins.py](../grid-probes/joins.py)),
> and **decided** or **proposed**. Ids: JN for conditions, JF for findings.

**What it is:** two or more tables made one.

| Form | Along | Rows matched by | Today |
|---|---|---|---|
| **stack** | rows: one under another | — (no matching: the rows are added) | `stack` |
| **zip** | columns: side by side | **the same rows**, as core recorded them (one origin; a row and the one it came from), or ids vouched for (`match_ids=True`) | `zip_` (never by position: corrected 2026-11-23) |
| **join** | columns: side by side | **a key**, inner, left, right or outer | `join` |
| **cross** | columns: side by side | **every pair** | *missing* |
| **lookup** | into one call's argument | **a key**, per row | *missing* (grammar.md N3) |

## A. Stack

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **JN1** | The row count is the **sum**; the columns are the **union** (`join="inner"`: only the shared ones) | ✓ | ✓ | decided |
| **JN2** | A column a table lacks: its cells **absent** | ✓ | `NaN` | decided: core's |
| **JN3** | Lineage: each row names the table it came from and its row there (`#a`, `#b`) | ✓ | — | decided |
| **JN4** | A column whose type differs between the tables: **mixed, and said** (N1) | mixed, **not said (JF1)** | mixed | proposed |

## B. Zip

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **JN5** | Rows match **only as core recorded them**, or by ids the user vouches for (`match_ids=True`); **never by position** | ✓ | by position (index) | decided: core's |
| **JN6** | A column name in both: refused, naming the fix (rename one) | ✓ | duplicate names | decided |

## C. Join, by a key

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **JN7** | **`on=` is written**: no join on "every shared column" | ✓ refused without it | joins on all shared columns, silently | decided: core's |
| **JN8** | `how=` inner, left, right, outer; **the unmatched side's cells absent** | ✓ | `NaN` | decided: core's |
| **JN9** | **A join expects each key at most once on each side: `one_to_one` by default.** Repeated keys are refused, naming the key and the counts, unless the relationship is written: `expect="one_to_many"`, `"many_to_one"` or `"many_to_many"` (pandas' `validate=`, made the default) | 4 rows, **silently** | silently, or `validate=` | **decided** (owner, 2026-11-23: "expect one to one") |
| **JN10** | **A missing key** (`None`, absent) **matches nothing**, as in SQL: a missing key identifies nothing; the row is kept or dropped by `how=` like any unmatched row, and said | **`None` matches `None`** | matches | **decided** (owner, 2026-11-23) |
| **JN11** | **Key types that differ** (text against integers): **refused when declared**, naming both types and the fix (convert one) | **the step fails at run, no reason shown (JF2)** | raises | proposed |
| **JN12** | **Shared non-key columns**: suffixed **`_left`, `_right`** (says which side) | ✓ | `_x`, `_y` | decided: core's |
| **JN13** | **Several keys**, `on=["k", "j"]` | ✓ (`on` takes a list) | ✓ | decided |
| **JN14** | **A key holding lists**: as nest.md's `key(…, read=…)`; with none written, refused naming the readings | — | — | decided (nest.md §A.1) |
| **JN15** | Lineage: each row names its row on each side; `None` for a side with no match | ✓ | — | decided |

## D. Cross

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **JN16** | **Every pair** of rows: the row count is the **product**, known exactly; shared names suffixed as JN12 | **refused: "needs on="** | `how="cross"` | decided |
| **JN17** | A product past a size (say, 1,000,000 rows): said before the run | — | — | decided |

## E. Lookup: another step's value, per row (grammar.md N3)

Excel's `VLOOKUP` / `XLOOKUP`: for each row of the calls' input, find the
row of another step with the same key, and give its cell to the call.
Written on the argument (an input modifier; placeholder
`mod.input.lookup(param, on=…)`).

| # | Condition | |
|---|---|---|
| **JN18** | **Exactly one match**: that row's cell, given to the call | decided |
| **JN19** | **No match**: the cell is **absent** (so the call gets what a missing value gets: grammar.md N2, the cell fails unless the parameter is `Optional`) | decided |
| **JN20** | **Several matches**: if the parameter takes a list, they are **nested into one** (H6), in their order; otherwise **refused when declared** if the keys are known to repeat, else that row fails, naming the key | decided |
| **JN21** | Keys follow JN10, JN11, JN14 (missing keys match nothing; types must agree; list keys need `read=`) | decided |

## F. Before the run (the plan)

| # | Condition | |
|---|---|---|
| **JN22** | Stack: the sum, **exact**. Zip: the rows of the one origin, **exact**. Cross: the product, **exact**. Join: **bounded**: inner at most the product; left at least the left's rows; outer at least the larger side's | proposed |

## G. The three places

| Place | Combine there |
|---|---|
| **a step** | `stack`, `zip_`, `join`, cross: everything above |
| **on a tool's input** | **lookup** (§E); data matched from another step for one call |
| **on a tool's output** | — (an output lands on its call's row; joining outputs is a step) |

## Decided, 2026-11-23

JN10 (a missing key matches nothing), JN9 (`one_to_one` by default; other
relationships written), **JN16–JN17** (the cross product added, said past a
size; its uses: showing gaps, a calendar scaffold, every pair, every
combination of two tables), **JN18–JN21** (lookup, Excel's `VLOOKUP`
without its silent first match or type mismatch). The terms may change
later (owner: "I might change the terms to something more intuitive later,
but these are fine").
5. JN4, JN11, JN22 follow decisions already made; accepted unless the owner
   objects.
