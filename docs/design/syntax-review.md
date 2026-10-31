# The syntax review: what you want, what's open, what's next

> **The one page for the expression cleanup** (2026-10-30). It gathers the
> owner's thoughts and wishes from the review sessions, the concerns raised
> with them, the bugs found, every decision still to make, the dev plan and
> the tests. It replaces, as the place to read,
> [to-revisit.md](to-revisit.md), [referencing-proposal.md](referencing-proposal.md)
> and [expressions-plan.md](expressions-plan.md), which stay as background.
> Every *today* line was run on core at `20a7980`.

**How to use it.** Read §1–§3 (the model and its rules). Go through §5, the
decisions: most say what you have already said, so they only need a yes. Then
§7 (the plan) and §8 (the tests) follow from your answers.

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

## 5. The decisions

*You said* is what you said in the sessions; where it's there, the decision
only needs confirming. Old ids are kept so the background docs still line up.

### A. References

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D1 | The user's model is §2: a list of rows, each a dict | yes | yes | — |
| D2 | An integer is a row, a string a key; nothing else in brackets | yes | yes | N2, N3 |
| D3 | Keys: strings only; identifiers only? | strings only | identifiers too (`temp_f`, not `temp f`), so every key can be typed | X-D3, Q3 |
| D4 | Rows: numbers `0…n-1` in each step's order, or stable ids? | integers | numbers; core keeps a hidden key per row for staleness and lineage; anything that must last is written by value | X-D1, Q1 |
| D5 | `wf[…]` takes step names only (`wf[0]` goes) | — | yes | Q10 |
| D6 | A key or row selection can be a step's input | (implied) | yes | X4 |
| D7 | `cols[…]` / `rows[…]` stay? | — | only for ranges of keys (`cols["a":"c"]`); otherwise plain brackets | X-D6, Q9 |
| D8 | `.header` → `.keys` | — | yes | X-D7 |
| D9 | One key is named after its step, not `value` | (your "stepname is a variable") | yes; `mod.name` still wins | X-D5, N4 |
| D10 | `[i]` / `["k"]` never reach inside a cell | — | yes: `expand` / `widen` do | Q8 |
| D11 | A literal is one value | yes | yes | N5 |
| D12 | A source's return: rows or one value? | — | its declared type decides: `list[T]` is rows; `list` or no annotation is one value | X-D10 |

### B. What tools receive

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D13 | §3's table: by type, a list to a value parameter iterates | yes ("a mapping is implied") | yes | N6 |
| D14 | Never choose a key when there is more than one | yes | yes | N7 |
| D15 | Binding by key name | only when explicitly defined | opt-in: `tool[mod.map(by_name=True)](wf["p"])`, refused when a name is missing | X-D2, Q2 |
| D16 | Keys, row numbers and `#` never reach a tool unless asked | yes | yes | N8 |
| D17 | Tools get plain Python values | — | yes | X3, N12 |
| D18 | A reference to a step whose shape is unknown until it runs | — | a warning when declared; decided when it runs; re-checked after | Q6 |
| D19 | `collapse(by="ward")` on a list of values: where is `ward`? | — | from that list's own step, for `by=` only | Q7 |

### C. Verbs

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D20 | Remove `auto` | don't infer variables | remove; the editor may *suggest* a verb (`k.infer_verb`); what's saved is what was chosen | X-D4, V1 |
| D21 | Nothing added unseen (`breaker`) | — | shown in the formula, or not added | N11 |

### D. Modifiers

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D22 | Modifiers: structure and execution only; tools in them are catalog tools or references, never lambdas | yes | yes | V2 |
| D23 | Move `initial=` (→ `acc=` in the call), `sweep`'s values (→ the call, `mod.sweep("x", "y")`), `over=` (goes) | yes | yes | X-D8 |
| D24 | `try_except(default=)` stays: the tool never sees it | — | yes | V2 |
| D25 | A key table in `collapse(by=)` | — | no: that's a `join` | V2 |

### E. Ids and `#`

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D26 | `#` columns accepted by reshaping modifiers (`collapse(by="#s")`) | you like it | keep | V5 |
| D27 | Refuse a `#` column as a tool argument (B3) | — | yes, pointing to D28 | — |
| D28 | `mod.rename(columns={"#": "row"})` makes the row id data | — | yes: one explicit way | — |
| D29 | Refuse `stack` of an ids-only step (B4) | — | yes | — |
| D30 | `sort` / `join` / `collapse` by `#` | — | no: under D4 `#` is a position; use the `#<step>` links | V5 |

### F. Reshaping

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D31 | Fix `widen` (B1): name the column, `mod.widen("info")`; refused when it can't tell which | — | yes | — |
| D32 | `expand(columns=[…])` takes dicts as key/value rows (B2) | — | yes, so a melt keeps its keys | — |
| D33 | `mod.melt(columns=[…], into=("key", "value"))`, `mod.pivot(by=, key=, value=)`, built from existing moves | — | yes; a pivot's columns are unknown until it runs, and must be identifiers (D3) | — |
| D34 | `collapse(by="ward", keep=[…])`: columns constant in a group stay one value, checked | — | yes | — |
| D35 | Collapse's group order | — | first appearance (today); sorting is a `sort` | — |
| D36 | A reshaping cheat sheet in rules.md: "I have X, I want Y, write Z" | — | yes | — |

### G. States

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D37 | The empty step gets its own state, `empty` (today `staged`) | — | yes, to match rule 9 | — |
| D38 | The `"empty"` cell: only the state says a step is empty, never the string | — | yes | — |
| D39 | `maybe` and `pending`: keep both (shown differently) or merge | — | keep, and document the difference | — |
| D40 | New conditions are marks on `completed`, not states (*as of 10:42*, *read stale*) | — | yes | T-D3 |

### H. Staleness and time

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D41 | Track the exact cells an argument reads, so a cell argument is stale only when that cell changes | — | yes | — |
| D42 | Re-run only the stale rows | — | yes, with K15 (phase 4 step D) | — |
| D43 | Volatility classes: pure, seeded, versioned, volatile; a tool is pure unless it says `@tool(volatile=True)` | — | yes | T-D1 |
| D44 | A resource with no `data_version()` counts as volatile, with a note | — | yes | T-D2 |
| D45 | `run_id` includes *as of* for volatile steps | — | yes | T-D4 |
| D46 | A tool with `seed` that isn't given warns, and counts as volatile | — | yes | C-D2 |
| D47 | The plan carries the row class (aligned, subset, one→many, …) and a position into a step whose rows can shift warns | — | yes | — |

### I. Terminal and UI

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D48 | `k["p"]` stays a reference; `k.data("p")` gives the list of dicts, plain values | — | yes | — |
| D49 | The output UI (a value card, a list, a table, a lineage strip; headers select values, never names; `#` outside the selection) | — | yes, written in the app's dev plan | — |

### J. Carried over

| | Decision | Recommended | Was |
|---|---|---|---|
| D50 | A resource with bound tools may also be passed to a free tool | yes, both | R-D1 |
| D51 | **Order against the app's migration:** this cleanup's §7 phases 1–4 before the app moves, so its formulas change once | yes | X-D9, G-D1 |
| D52 | Older saved workspaces | refused with core's message | G-D2 |
| D53 | The app's own cleanups before it moves | yes | G-D3 |

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

Each phase keeps the suite green, ends with its laws passing, and each
behaviour change is confirmed before it lands.

| Phase | Work | Decisions |
|---|---|---|
| **0. Tests first** | §8's laws, each expected-to-fail until its phase; regression tests for B1–B6 | — |
| **1. Bugs** | B1 (`widen`), B2 (`expand` dicts), B3 (`#` argument), B4 (`stack`), B6 (string keys) | D27, D29, D31, D32, D3 |
| **2. Values and keys** | plain Python values to tools; identifiers | D17, D3 |
| **3. The heart** | brackets (string = key, int = row); selections as inputs; `wf[…]` by name; `.keys`; what tools receive by type; no binding by name (opt-in) | D2, D5–D8, D13–D16, D18, D19 |
| **4. Verbs and naming** | no `auto` (B5); nothing unseen; a single key named after its step; literals and sources | D20, D21, D9, D11, D12 |
| *the app moves here* | app-migration.md, with the new syntax | D51–D53 |
| **5. Row numbers** | `0…n-1` per step; links in `#`; core's hidden key; the reshaping laws re-run | D4, D10, D30, D47 |
| **6. Modifiers** | `initial=`, `sweep`, `over=` | D22–D25 |
| **7. Reshaping** | `melt`, `pivot`, `keep=`, the cheat sheet | D33–D36 |
| **8. States** | `empty`; marks | D37–D40 |
| **9. Staleness and time** | cell reads; volatility; *as of*; seed | D41–D46 (D42 with phase 4 step D) |
| **10. Docs** | rules.md opens with §2; step-expressions, kernel-session; the UI design to the app | D48, D49 |

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
