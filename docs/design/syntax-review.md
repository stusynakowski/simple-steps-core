# The syntax review: what you want, what's open, what's next

> **The one page for the expression cleanup** (2026-10-30). It gathers the
> owner's thoughts and wishes from the review sessions, the concerns raised
> with them, the bugs found, every decision still to make, the dev plan and
> the tests. It replaces, as the place to read,
> [to-revisit.md](to-revisit.md), [referencing-proposal.md](referencing-proposal.md)
> and [expressions-plan.md](expressions-plan.md), which stay as background.
> Every *today* line was run on core at `20a7980`.

**How to use it.** This page is the design: §1–§3 (the model and its
rules), §4 (today and the bugs), §6 (concerns) and §8 (the tests). The
decisions are in [decisions.md](decisions.md); the order of work is in
[phase4-plan.md](phase4-plan.md).

## 1. What you want

In your words, condensed:

- **Think in lists and dicts.** A step is a list you iterate through; each
  row is a dict, whose keys are what you call the things you iterate
  through. What's inside a value can be complicated; that's the tool's
  business.
- **Tidy tables,** with small, clearly defined exceptions, so nothing is
  ambiguous.
- **Referencing without surprises.** Cells hold what you care about; you
  assign them deliberately and reference them without issues.
- **Names structure assignment; they aren't data.** Column names say which
  values go where. They aren't passed to tools as arguments unless that is
  explicitly asked for (a workflow built around a particular variable name).
- **No headers or row numbers sneaking into tools.**
- **No implicit behaviour.** `auto` must not choose variables when there is
  more than one option.
- **Excel's feel, Python's syntax,** without pandas' messiness.
- **Modifiers change how a tool runs on the grid** (indices, grouping,
  order, failures), never supply values the tool consumes. A reference in a
  modifier is fine when it acts as a tool on the structure.
- **Rows as integers.** Variable names as strings only.
- **Reshaping should be quick;** it is harder than the analysis.
- **Airtight:** closed by tests, like reshaping was.

Already settled in the sessions: the combines (`zip_`, `stack`, `join`) stay
as they are; both orders of a cell reference (`[i]["k"]`, `["k"][i]`) are
accepted and saved the same; commit times are not to be rewritten in this
repo.

## 2. The model

```python
patients = [                                   # wf["p"]: a list of rows
    {"name": "Ann", "temp": 36.6, "ward": "A"},  # wf["p"][0]: a dict
    {"name": "Ben", "temp": 38.2, "ward": "A"},
]
[row["temp"] for row in patients]              # wf["p"]["temp"]: a list of values
patients[1]["temp"]                            # wf["p"][1]["temp"]: one value
```

| | In the model | In core |
|---|---|---|
| a step | a list of rows | a grid, in order |
| a row | a dict | a row; its keys are the variables |
| a key | a string naming a thing in every row | a column name |
| a value | anything | a cell |
| `#` columns | not there | lineage: where each row came from; never a key, never passed |

Two shorthands, both exact: **one row and one key is the value** (any
literal: `k["limit"] = 38`, `k["xs"] = [1, 2, 3]` is one value until
`expand`); **one key is its list of values**, and that key is the step's
name (`wf["temp_f"]` is a list of numbers).

## 3. The rules

**References.** An integer is always a row, a string always a key.

| Written | Gives |
|---|---|
| `wf["p"]` | the list of rows |
| `wf["p"][1]`, `[-1]`, `[1:3]` | a row (a dict); the last; a shorter list |
| `wf["p"]["temp"]` | a list of values |
| `wf["p"][["name", "temp"]]` | the rows, with only those keys |
| `wf["p"][1]["temp"]` = `wf["p"]["temp"][1]` | one value (printed key first) |
| `wf["p"].keys` | the keys as a list: the only way names become values |

**What a tool receives.** The parameter's type says what one call takes.
A list where one call takes one item means a call per item: the only
iteration core adds.

| Given | `T` | `list[T]` | `dict` / record | `list[dict]` / `DataFrame` |
|---|---|---|---|---|
| a value | 1 call | 1 call, if a list | 1 call, if a dict | 1 call, if a table |
| a list of values | **a call per item** | 1 call | refused | refused |
| a row | refused: pick a key | refused | 1 call | refused |
| a list of rows | **refused: pick a key** | refused | **a call per row** | 1 call |

Several arguments: a list iterates, a value is the same in every call, two
lists iterate together only when core knows their rows match (rule 6).

**Verbs.** Iterating is implied by the types. Everything that changes the
list is written: `filter`, `expand`, `collapse(by=…)`, `sort`, `slice`,
`distinct`, the reshapes, the combines. No `auto`.

**Modifiers** say which rows, which keys, order, grouping, failures and
time. Values for the tool come in the call.

### 3.1 Broadcasting (`auto`)

`auto` is broadcasting, as numpy defines it, applied to the arguments of one
call (owner, 2026-10-31):

1. Each argument is a **value**, a **list** (n items) or a **list of rows**.
2. A list given to a parameter that takes one item is **iterated**; a list
   given to a `list[T]` parameter is **consumed whole** (numpy's "core
   dimension": `mean(temp: list[float])` is `(n) → ()`).
3. Every iterated list must have **the same rows** (rule 6). Equal length is
   not enough; otherwise refused, pointing to `join`.
4. Values are **the same in every call** (broadcast).
5. A list of rows given to a one-item parameter is **refused** unless it has
   exactly one key: `auto` never chooses a key.
6. Nothing iterated → **one call**, one value. Something iterated → **a call
   per row**, a list aligned with those rows.
7. Each argument reaches its parameter **by position or by keyword in the
   call**, never because a column happens to share the parameter's name.

It resolves when the step is written and prints as `map` (or one call), so
the saved form says what runs.

**Principles** for every choice: many spellings, one saved form; the explicit
form prints back; a shortcut resolves when written; look-alikes that differ
save differently; a second way only for a different intent; a refusal names
the right way; breaking an abstraction is one explicit step.

## 4. Today, and the bugs found

What core does today against §3, run at `20a7980`:

| §3 says | Today |
|---|---|
| `wf["p"]["temp"]` is a list | refused: *"Columns use cols"*; and a selection can't be an input: *"make it its own step"* |
| a list of rows to a `T` parameter is refused | `to_f(wf["p"])` binds `temp` by name, silently |
| a list of rows to `row: dict` is a call per row | looks for a column named `row`: invalid |
| a list to `list[T]` is one call | as the input, a call per row, then a type error |
| filtering is written | `is_hot(wf["p"])` is saved as `mod.auto()`, filters at run, and adds an unseen `breaker(after=5)` |
| keys are strings | `DataFrame([[1, 2]])` gets keys `"0"`, `"1"` silently |
| tools get plain values | a row dict holds `np.float64`; raw data shows `NaN`, `<NA>` |
| `[1]` is the second row | `[1]` is row id 1; `expand` ids are `"0.1"`; `[-1]` refused |
| a single key is named after its step | it is `value` |
| modifiers don't hand the tool values | `collapse(initial=)`, `sweep(x=[…])`, `over=` do |

**Bugs: wrong today whatever is decided**

| | Bug | Run |
|---|---|---|
| B1 | **`widen` on a step with other columns silently gives `None`** | `widen(columns=["age", "bed"])` on `name, info` → `age`, `bed` all `None`, no problem, no warning; `widen(columns=["info"])` → unchanged |
| B2 | `expand(columns=["value"])` refuses a dict that `expand()` accepts | *"not a list: dict"* vs key/value rows |
| B3 | a `#` column as a tool argument reaches the tool | `show(value=wf["p"][cols["#"]])` → the tool gets `0, 1` |
| B4 | `stack` of an ids-only step gives rows with nothing in them | `stack(wf["p"][cols["#"]], …)` |
| B5 | `auto` is stored, against `infer_verb`'s own docstring (*"never into a stored auto"*) | two spellings of one step have different specs and ids |
| B6 | non-string column names are coerced silently | as above |
| B7 | **a column in the data silently replaces a parameter's default** | `to_f(temp, scale=1.8)` on a step that happens to have a `scale` column (100.0) → 3692 °F, no warning |
| B8 | a one-key step can't feed a tool whose parameter has another name | `to_f_v(t)` on `expand`'s `value` → *"needs 't'"*; the message also lists `#xs` as a column |
| B9 | a one-key list given as an argument is called a "block": its `#` column is counted as a second column | `to_f_v(t=wf["list"])` → *"'list' is a block"*; rule 2 says `#` is never counted |
| B10 | **an object without a stable `repr` gets a new data version on every run** | a tool returning `Scan(...)`: re-running the same step makes every reader *"stale: input s changed"*; the version hashes the object's address |

## 5. The decisions

All of them, D1–D56, are in [decisions.md](decisions.md), grouped by the
step that needs them, with what you said and what is recommended.

A **single cell broadcasts like a literal** (§3.1 rule 4, checked by
`tests/unit/test_where.py`): `limit=38.0`, `limit=wf["lim"]` (a 1×1 step) and
`limit=wf["c"][0]["limit"]` give the same result. A column of a one-row step
is a list, not a cell: it pairs by row, so take its cell, `[0]`.

## 6. Concerns

1. **Row numbers don't follow a sample** (D4). After the data changes, `[3]`
   can be another patient. Fine for views and "top k"; anything that must
   last is written by value. Core's hidden key carries staleness and lineage.
2. **Shapes unknown until a step runs** (D18): an undeclared source's
   references can't be checked until it does.
3. **A rename renames the step's single key** (D9): references must follow
   it, as they follow step renames today.
4. **A list of rows to `dict` is where keys reach a tool:** explicit (the
   parameter says so), and the one place.
5. **Python's `sum`, `len`, … aren't tools.** `sum(wf["x"])` means nothing to
   core; built-ins (`total`, `count`) or your tools do. The formula bar
   should refuse names it doesn't know.
6. **A pivot turns data into names** (D33): its columns are unknown until it
   runs, and its keys must be strings.
7. **Freshness can't be checked for volatile steps** (D43): core says *as
   of*, never *up to date*.
8. **The app migrating twice** (D51) if the syntax changes after it moves.

## 7. The dev plan

In [phase4-plan.md](phase4-plan.md) §2: steps S0–S10 in order among the rest
of phase 4 (the app's move, sessions, storage, the table view).

## 8. The tests

`tests/unit/test_expressions.py`, one law per rule, written in phase 0 and
marked expected-to-fail until its phase lands (as `test_reshape_closure.py`
did). Then the property test learns the new references.

| Law | Written | Holds when |
|---|---|---|
| E1 | `wf["p"]["temp"]` | a list of `p`'s temps, in order |
| E2 | `wf["p"][1]` | a dict of row 1's keys; no `#` key |
| E3 | `wf["p"][1]["temp"]`, `wf["p"]["temp"][1]` | the same value; the same saved form |
| E4 | `wf["p"][-1]`, `wf["p"][0:2]` | the last row; the first two |
| E5 | `wf["p"][["name", "temp"]]` | rows with only those keys |
| E6 | `wf["p"].keys` | `["name", "temp", "ward"]` |
| E7 | `wf["p"][1.5]`, `wf["p"][None]` | refused, naming what brackets take |
| E8 | `to_f(wf["p"]["temp"])`, `temp: float` | a call per item; a list of the same length, aligned |
| E9 | `mean(wf["p"]["temp"])`, `temp: list[float]` | one call; one value |
| E10 | `describe(wf["p"])`, `row: dict` | a call per row, each a plain dict |
| E11 | `to_f(wf["p"])` | refused: *"p has name, temp, ward: pick one"* |
| E12 | `scale(wf["p"]["temp"], k=wf["limit"])` | the value is the same in every call |
| E13 | `add(wf["p"]["temp"], wf["w"]["temp"])`, unrelated | refused, pointing to `join` |
| E14 | any tool | never receives a `#` column, a key on its own or a row number unless asked |
| E15 | a row dict | holds `float` / `None`, never `np.float64` / `NaN` |
| E16 | a tool returning `DataFrame([[1, 2]])` | refused: keys must be strings, with the fix |
| E17 | `k["temp_f"] = to_f(wf["p"]["temp"])` | one key, `temp_f`; `wf["temp_f"]` is that list |
| E18 | `is_hot(wf["p"]["temp"])` | a list of bools; `filter` only when written |
| E19 | any step | its formula prints every modifier it runs with |
| E20 | `k["xs"] = [1, 2, 3]` | one value; `expand` makes three rows |
| E21 | after `sort`, `filter`, `expand`, `collapse` | rows are `0…n-1`; `#` links point at the right input rows |
| E22 | after an upstream change | per-row staleness still marks exactly the changed rows (core's hidden key) |
| E23 | `mod.widen("info")` on `name, info` | `name, age, bed`; without the column name: refused |
| E24 | `mod.expand(columns=["info"])` on a dict | key/value rows, `name` kept |
| E25 | `melt` then `pivot` | gives back the table (round trip) |
| E26 | a modifier setting | is never passed to the tool as an argument |
| E27 | every formula in §3 | saves, reloads and prints back the same |

Done when every law passes, the property test (at `STRESS=1`) generates
formulas in the new syntax without a failure, and the reshaping laws still
hold.
