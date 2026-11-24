# Convert: the conditions of changing a value's type

> **Draft, 2026-11-23, for the owner.** The primitive **convert**: the one
> that **changes a value**, and only when written (grammar.md §8, X3). Each
> condition: what it says, today (`mod.cast`, run 2026-11-23, beside
> pandas' `astype` and `to_numeric`:
> [grid-probes/convert.py](../grid-probes/convert.py)), and **decided** or
> **proposed**. Ids: CV for conditions, CF for findings.

**The principle** (proposed, CV1): **a conversion keeps the value's
meaning exactly, or that cell fails, with its reason.** Never a silent
loss: no truncation, no rounding, no "anything non-empty is true".

## A. What converts to what

Today's targets: `str`, `int`, `float`, `bool` (others refused, naming
these: run). More targets (dates, decimals, categories) are **extensions,
later** (closure.md §1).

| # | From → to | Condition | Today | pandas | |
|---|---|---|---|---|---|
| **CV2** | text → `float` | Python's reading: spaces trimmed, `1e3` allowed (`"1.5"`, `" 3 "`, `"1e3"` → 1.5, 3.0, 1000.0) | ✓ | ✓ | decided |
| **CV3** | text → `float`, **not a number** (`"abc"`, `"1,000"`) | that cell fails, with its reason | ✓ | `to_numeric(coerce)`: **`NaN`, silently** | decided: core's |
| **CV4** | text → number, **thousands separators** (`"1,000"`) | fails (CV3): a separator depends on the locale; reading it is a later extension | ✓ fails | `NaN` | **to decide** |
| **CV5** | `float` → `int` | **a whole number only**: `2.0` → 2; `1.7` fails, "isn't a whole number" | ✓ | `astype(int)`: **1.7 → 1, silently** | decided: core's |
| **CV6** | text → `int`, written with a decimal point (`"2.0"`) | read as a number, then CV5: `"2.0"` → 2, `"2.5"` fails; **or** fails (text must be an integer) | fails | raises | **to decide** |
| **CV7** | `int` → `float` | **exact only**: an integer past 2⁵³ that a float can't hold exactly **fails** | **precision lost silently** (2⁶⁰+1, **CF2**) | the same | proposed (CV1) |
| **CV8** | text → `bool` | `"true"`, `"false"`, any case; `"False"` is false | ✓ | **`"False"` → True** | decided: core's |
| **CV9** | text → `bool`, other words (`"yes"`, `"no"`, `"1"`, `"0"`) | fail; **or** accepted | fail | → True | **to decide** |
| **CV10** | `int` → `bool` | **0 and 1 only**; any other integer fails | **2 → True, silently (CF1)** | the same | proposed (CV1) |
| **CV11** | `bool` → `int` | 1, 0 | ✓ | ✓ | decided |
| **CV12** | anything → `str` | **a unit** (a number, a bool) → its text; **a structure** (a list, a dict) → fails, "use a tool to write it as text (JSON, …)"; **or** any value's text (`"[1, 2]"`) | any value's text | the same | **to decide** |

## B. Missing values, failures

| # | Condition | Today | |
|---|---|---|---|
| **CV13** | **A missing value stays missing**: absent stays absent, `None` stays `None` (tidy.md T9) | ✓ | decided |
| **CV14** | **A cell that doesn't convert fails, with its reason** ("cast x to int: 1.7 isn't a whole number"); its row's call is blocked, naming it; the other rows run (grammar.md N1) | ✓ | decided |
| **CV15** | **A target core doesn't have**, or **a column that isn't there**: refused when declared, naming what there is | ✓ | decided |

## C. Place, types

| # | Condition | Today | |
|---|---|---|---|
| **CV16** | **An input modifier** (decided, X3), in its fixed place: each cell converted **before** it is nested or given to the call (blocks.md §0: convert, then nest) | **its place in the written order changes what it does**: before the verb it converts the input grid, after it one row at a time (the code's own note) | decided: the canonical form fixes the place |
| **CV17** | After it, the column's type is the target, **known before the run**; converting a **mixed** column (N1) is how a user makes it one type | — | proposed |
| **CV18** | A converted column **keeps its name** (converted in place) | ✓ | decided |

## D. The three places

| Place | Convert there |
|---|---|
| **on a tool's input** | `cast` today: each named argument's cells converted before the calls |
| **a step** | a column of a table converted, as a step of its own: *missing* (primitives.md §7); in scope |
| **on a tool's output** | the outputs converted: *missing*; in scope |

## To decide

1. **CV6**: text `"2.0"` to an integer: read as a number then a whole
   number (→ 2), or fails (text must be an integer)?
2. **CV9**: text to yes/no: only `"true"` and `"false"`, or also `"yes"`,
   `"no"`, `"1"`, `"0"`?
3. **CV12**: a list or dict to text: fails (a tool writes it), or its
   Python text (`"[1, 2]"`)?
4. **CV4**: thousands separators: fail now, an extension later?
5. **CV1, CV7, CV10, CV17**: proposed, by the principle; accepted unless the
   owner objects.
