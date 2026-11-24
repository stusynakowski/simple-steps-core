# Take: the conditions of choosing rows and columns

> **Draft, 2026-11-23, for the owner.** The primitive **take**: choose and
> reorder rows and columns, **no value changed**. Each condition: what it
> says, today (run 2026-11-23, beside pandas:
> [grid-probes/take.py](../grid-probes/take.py)), and **decided** or
> **proposed**. Ids: TK for conditions, TF for findings.

**What take is:** a subset of the rows or columns, in some order. Its
spellings (shorthands.md): a pick's row and column parts, `select`,
`slice`, a condition (`wf["p"][cols["x"] > 1]`), `filter` with a tool,
`sort`, `distinct`, `drop`. **Repeating a row** is not take's: a pick that
names a row twice is refused ("names row 0 twice", run); rows are repeated
only by join together (joins.md), where the reason is written.

## A. Rows by position

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **TK1** | A row number, a list, a range, negative from the end (`[-1]`) | ✓ | ✓ (`iloc`) | decided |
| **TK2** | **A row that isn't there** (row 10 of 4): refused, naming the rows there are | ✓ | raises | decided |
| **TK3** | **A range past the end** (`2:10` of 4): refused, naming the count and the shorthand for "up to n" | ✓ | **clips silently** | decided: core's |
| **TK4** | **A row named twice**: refused | ✓ | repeats it | decided |
| **TK5** | **An empty pick**: refused ("selects nothing") | ✓ | an empty table | decided |
| **TK6** | A position pick **follows its rows** when rows are added or removed above (its numbers rewritten: blocks.md §1) | ✓ | — | decided |

## B. Rows by a condition

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **TK7** | A condition on columns (`cols["x"] > 1`, `&`, `\|`, `~`) or on lineage (`row["s"]`) keeps the rows where it is true | ✓ | ✓ | decided |
| **TK8** | **Types the condition can't compare** (`"a" > 1`): refused when declared, naming the value | ✓ | raises at run | decided |
| **TK9** | **A missing value** in a compared column (a gap, `None`): the test can't be decided, so **the row is dropped and it is said**, in **the step's warnings** (as widen's "rows held no dict"): how many rows, and the first few row numbers. Nothing per cell. **Cost, run on 1M rows: 0.16 ms to count the gaps, beside 0.71 ms for the comparison**, in the same pass (owner's concern: "more overhead on the computation"). **`undecided="keep"`** written keeps the row instead, marked undecided (§C.1) | **dropped silently** | dropped silently | **decided** (owner, 2026-11-23): the default, and the option |

## C. Rows by a tool's test (`filter`)

| # | Condition | Today | |
|---|---|---|---|
| **TK10** | One call per row; `True` keeps the row, `False` drops it | ✓ | decided |
| **TK11** | **A call that fails**: the row is **kept, as failed**, with its reason | ✓ (run) | decided |
| **TK12** | **A call that returns something other than `True` or `False`**: the tool's return type decides, as `Optional` does for a missing value going in (grammar.md N2). **`-> bool`**: `None` is a broken promise, the test didn't cover that case: the row is **kept, as failed**, "the test returned None, not yes or no", as TK11, so the rows to fix are shown. **`-> Optional[bool]`**: `None` is "can't tell", on purpose: **as TK9**, the row dropped and said (owner, 2026-11-23: "filtering because you didn't have the right condition"). **`undecided=`** written chooses either (§C.1) | **treated as `False`: the row dropped silently (TF2)** | **decided** (owner, 2026-11-23): the defaults, and the option |

### C.1 `undecided=`: either, written; the defaults above

*Owner, 2026-11-23: "add an extension to do either, but default to the
first."* One written option on taking rows by a test (a condition, or
`filter`'s tool):

| Undecided because | Default | `undecided="drop"` | `undecided="keep"` |
|---|---|---|---|
| a condition on a missing value (TK9) | dropped, and said | the default | kept, marked undecided |
| a `-> bool` tool returning `None` (TK12) | kept, marked failed | dropped, and said | the default |
| a `-> Optional[bool]` tool returning `None` (TK12) | dropped, and said | the default | kept, marked undecided |

Dropped rows are always said, in the step's warnings; kept ones are always
marked. Never silent either way.

## D. Sort

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **TK13** | By one or more columns, ascending or descending | ✓ | ✓ | decided |
| **TK14** | **Ties keep their order** (a stable sort) | ✓ | ✓ | decided |
| **TK15** | **Gaps go last**, ascending or descending | ✓ | ✓ (`na_position="last"`) | decided |
| **TK16** | **Types that can't be compared**: refused when declared if the types are known (as TK8); else the step fails, **naming the values** | **the step fails with no reason shown (TF1)** | raises | proposed |
| **TK17** | **A column of lists, dicts**: sorted by `key(…, read=…)` (nest.md §A.1); with none written, refused naming the readings | — | — | proposed |

## E. Distinct

| # | Condition | Today | pandas | |
|---|---|---|---|---|
| **TK18** | The **first row** of each distinct value is kept, in order | ✓ | ✓ | decided |
| **TK19** | **`None` is a value of its own** (as nest.md NS4) | ✓ | ✓ | decided |
| **TK20** | **Lists, dicts**: compared by `key(…, read=…)` (nest.md §A.1); with none written, refused naming the readings | compared by value | by value | proposed (follows NS6) |

## F. Columns

| # | Condition | Today | |
|---|---|---|---|
| **TK21** | By name, position, range, list (`cols["am"]`, `cols[1]`, `cols[1:3]`); a string is a name, an integer a position | ✓ | decided (tidy.md T2) |
| **TK22** | A column picked by position keeps its name with it, and follows it (tidy.md T3) | follows, **its text unchanged (C1)** | decided |
| **TK23** | **A column that isn't there** (a pick, a `drop`): refused, naming the columns there are | ✓ | decided |
| **TK24** | **A column named twice**: refused, as a row (TK4) | not run | proposed |

## G. Before the run (the plan)

| # | Condition | |
|---|---|---|
| **TK25** | The **columns** are known, exactly. The **row count**: a position pick and `sort`, **exact**; a condition, `filter`, `distinct`, **at most the input's** | proposed |

## H. The three places

| Place | Take there |
|---|---|
| **a step** | a pick declared as a step; `sort`, `distinct`, `drop` |
| **on a tool's input** | the pick's row and column parts: which cells reach the calls |
| **on a tool's output** | `filter`: the tool's `True` or `False` keeps or drops its row |

## Decided, 2026-11-23

TK9 and TK12, with `undecided=` to choose either (§C.1). TK16, TK17, TK20,
TK24, TK25 accepted, following decisions already made.
