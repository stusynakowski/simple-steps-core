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
| **CV4** | text → number, **thousands separators** (`"1,000"`) | fails now (CV3): a separator depends on the locale. **A locale-aware reading method later** (`thousands=`, `decimal=`, as pandas' `read_csv`) | ✓ fails | `NaN` | **decided** (owner, 2026-11-23) |
| **CV5** | `float` → `int` | **a whole number only**: `2.0` → 2; `1.7` fails, "isn't a whole number". **`round=` written** (`"nearest"`, `"down"`, `"up"`) converts it, as written | ✓ | `astype(int)`: **1.7 → 1, silently** | decided: core's; `round=` added (§E) |
| **CV6** | text → `int`, written with a decimal point (`"2.0"`) | **by default, read as a number, then CV5**: `"2.0"` → 2, `"2.5"` fails. **`strict=True`**: the text must be an integer | fails | raises | **decided** (owner, 2026-11-23: "default to yes, but add a condition for strict") |
| **CV7** | `int` → `float` | **exact by default**: an integer past 2⁵³ that a float can't hold exactly **fails**. **`lossy=True`** accepts the nearest float, written | **precision lost silently** (2⁶⁰+1, **CF2**) | the same | decided |
| **CV8** | text → `bool` | `"true"`, `"false"`, any case; `"False"` is false | ✓ | **`"False"` → True** | decided: core's |
| **CV9** | text → `bool`, other words | **by default** `"true"`/`"false"`, `"yes"`/`"no"`, `"1"`/`"0"`, any case; any other text fails. **`strict=True`**: only `"true"`, `"false"` | fail | → True | **decided** (owner, 2026-11-23: "make extensions for either cases") |
| **CV10** | `int` → `bool` | **0 and 1 only, by default**; any other integer fails. **`nonzero=True`**: any non-zero is `True`, written | **2 → True, silently (CF1)** | the same | decided |
| **CV11** | `bool` → `int` | 1, 0 | ✓ | ✓ | decided |
| **CV12** | anything → `str` | **a unit** (a number, a bool) → its text. **A structure** (a list, a dict) goes to and from text **through a named data format, JSON by default** (`format="json"`), never Python's own text (`"[1, 2]"`). The same method **reads** text back into a list or a dict (text → `list`, `dict`: new targets) | any value's Python text | the same | **decided** (owner, 2026-11-23: "yes, need a data reading method") |

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

### Built in today's `cast`, 2026-11-25

CV5 (whole numbers only), CV6 (`"2.0"` → 2), CV7 (an integer a float can't
hold exactly fails: CF2), CV9 (true/false, yes/no, 1/0), CV10 (only 0 and 1
to a bool: CF1), CV12 (a list or dict to text as JSON; a set, an array, a
table fail, naming a tool; a unit such as a date keeps its own text),
CV13. **The arguments for the other way** (§E: `round=`, `strict=`,
`lossy=`, `nonzero=`, `format=`) **come with the canonical `convert`**
(roadmap phase 3): today's `cast` takes column names as its keywords, so
`round=` would read as a column named "round".

## E. A reasonable default, and an argument for the other way

*Owner, 2026-11-23: "use a reasonable option, but ensure we have extensions
for either case, in these cases (arguments in the modifier or tool
needed)."* Every conversion that could reasonably go two ways has a default
and a written argument for the other:

| Conversion | Default | The other way, written |
|---|---|---|
| `float` → `int`, not whole | fails | `round="nearest" \| "down" \| "up"` |
| text → `int`, `"2.0"` | read as a number, then whole | `strict=True`: integer text only |
| `int` → `float`, past 2⁵³ | fails | `lossy=True` |
| text → `bool` | true/false, yes/no, 1/0 | `strict=True`: true/false only |
| `int` → `bool`, not 0 or 1 | fails | `nonzero=True` |
| a list or dict ↔ text | JSON | `format=` another data format (later) |
| text with thousands separators | fails | `thousands=`, `decimal=` (later, a locale-aware reading method) |

(The names are placeholders until phase 1.)

## Decided, 2026-11-23

CV4, CV6, CV9, CV12 (the owner's answers); CV1, CV7, CV10, CV17 (by the
principle), each with its argument for the other way (§E).
