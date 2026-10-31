# Cleaning up expressions: the plan

> **Consolidated into [syntax-review.md](syntax-review.md)** (2026-10-30): read that first; this page is background.

> The dev plan for the basic syntax of expressions: how a step is referenced,
> and what a tool receives. Started 2026-10-30. It turns
> [referencing-proposal.md](referencing-proposal.md) and V1–V5 of
> [to-revisit.md](to-revisit.md) into ordered work. Nothing here is built.
> "Today" lines were run at `706c0b5`.

## 1. The idea in one paragraph

**A step is a list of rows. A row is a dict.** You iterate through the list;
the dict's keys are what you call the things in each row. A value inside a
row can be anything: a number, a string, or something complicated (a list, a
dict, a table), which stays one value until you unpack it. Tools receive
values, dicts and lists, exactly as a Python function would. They never
receive the keys on their own, or the row numbers, unless the formula asks
for them by name.

```python
patients = [                                   # wf["p"]: a list of rows
    {"name": "Ann", "temp": 36.6, "ward": "A"},  # wf["p"][0]: a dict
    {"name": "Ben", "temp": 38.2, "ward": "A"},
    {"name": "Cy",  "temp": 39.1, "ward": "B"},
]
[row["temp"] for row in patients]              # wf["p"]["temp"]: a list of values
patients[1]["temp"]                            # wf["p"][1]["temp"]: one value
```

That is the whole model a user needs. Everything below makes core behave
exactly like it, with no guessing in between.

## 2. The rules

### 2.1 What a step is

| | In the model | Core's grid |
|---|---|---|
| a step | a list of rows | the rows, in order |
| a row | a dict | one row; its keys are the variables |
| a key | a string naming a thing in every row | a column name |
| a value | anything | a cell |
| `#` columns | not there | core's bookkeeping: where each row came from. Never a key, never passed |

Two shorthands, both exact:
- **One row, one key → the value.** `k["limit"] = 38` is a step whose value
  is `38`. Any literal assigned to a step is one value (a list literal is
  one value too, until `expand`).
- **One key → its values.** A step with a single key is read as the list of
  its values. The key is the step's own name (`k["temp_f"] = …` has the key
  `temp_f`), so `wf["temp_f"]` is a list of numbers.

### 2.2 Referencing

| Written | Means | Python |
|---|---|---|
| `wf["p"]` | the list of rows | `patients` |
| `wf["p"][1]` | one row: a dict | `patients[1]` |
| `wf["p"][1:3]`, `wf["p"][-1]` | a shorter list; the last row | `patients[1:3]`, `patients[-1]` |
| `wf["p"]["temp"]` | the `temp` of every row: a list | `[r["temp"] for r in patients]` |
| `wf["p"][["name", "temp"]]` | every row, with only those keys | `[{k: r[k] for k in (…)} for r in patients]` |
| `wf["p"][1]["temp"]` = `wf["p"]["temp"][1]` | one value (printed key first) | `patients[1]["temp"]` |
| `wf["p"].keys` | the keys, as a list: the only way names become values | `list(patients[0])` |

**An integer is always a row, a string is always a key.** Row numbers are
`0…n-1` in the step's order, as a Python list's are. Keys are strings and
identifiers. Nothing else goes in the brackets.

### 2.3 What a tool receives

The parameter's type says what **one call** takes. If you give a list where
one call takes one item, the tool is called **once per item**: that is the
only iteration core ever adds on its own.

| You give | `T` (a value) | `list[T]` | `dict` / a record type | `list[dict]` / `DataFrame` |
|---|---|---|---|---|
| a value | 1 call | 1 call, if it is a list | 1 call, if it is a dict | 1 call, if it is a table |
| a list of values (`wf["p"]["temp"]`) | **a call per item** | 1 call, the list | refused | refused |
| a row (`wf["p"][1]`) | refused: pick a key | refused | 1 call, the dict | refused |
| a list of rows (`wf["p"]`) | **refused: pick a key** (*"p has name, temp, ward"*) | refused | **a call per row** | 1 call, the rows |

Several arguments in one call: a list iterates, a single value is the same in
every call, and two lists iterate together **only** when core knows their
rows match (rule 6). Otherwise: `join` first.

**What never reaches a tool:** a key on its own (unless you pass
`wf["p"].keys`), a row number, a `#` column.

### 2.4 Verbs

Iterating a list is implied by the types (§2.3). **Everything that changes
the list is written:** `filter`, `expand`, `collapse(by=…)`, `sort`, `slice`,
`distinct`, the reshapes and the combines. There is no `auto`.

A modifier says how the tool meets the list (which rows, which keys, order,
grouping, failures, time). It never hands the tool a value; values come in
the call (to-revisit V2, the owner's rule).

### 2.5 What a formula prints

Exactly what will happen: no hidden modifier, no verb chosen later, one
printed form per meaning.

## 3. Today, against the model

| The model says | Today | Gap |
|---|---|---|
| `wf["p"]["temp"]` is a list | refused: *"a plain bracket selects rows by int id… Columns use cols"*; and a selection can't be an input: *"make it its own step"* | X4 |
| a list of rows to a `T` parameter is refused | `to_f(wf["p"])` binds `temp` by name, silently | X5 |
| a list of rows to a `dict` parameter is a call per row | `keys(wf["p"])` with `row: dict` looks for a column named `row`: invalid | X5 |
| a list to `list[T]` is one call | as an argument it works; as the input it maps per row and fails on type | X5 |
| `is_hot(wf["p"]["temp"])` maps; `filter` is written | `is_hot(wf["p"])` is saved as `mod.auto()` and filters at run | X6 |
| keys are strings | a `DataFrame([[1, 2]])` gets keys `"0"`, `"1"` silently | X2 |
| a value is plain Python | a row dict holds `np.float64` | X3 |
| `[1]` is the second row | `[1]` is the row *id* 1; `expand` ids are `"0.1"`; `[-1]` is refused | X8 |
| one key is named after its step | it is `value` | X7 |
| `wf[…]` takes step names | `wf[0]` is the first step | X4 |
| modifiers don't hand the tool values | `collapse(initial=)`, `sweep(x=[…])`, `over=` do | X9 |

## 4. The steps

Each step is small, keeps the suite green, ends with its laws passing, and
is confirmed with the owner before it lands (CLAUDE.md). The laws are written
first (X1), marked expected-to-fail, and come off one by one.

| | Step | Changes for a user | Needs |
|---|---|---|---|
| **X1** | **The laws.** `tests/unit/test_expressions.py`: one law per row of §2.2 and §2.3 and per rule, each expected-to-fail until its step; the property test (L40) learns the new references | nothing yet | — |
| **X2** | **Keys are strings, and identifiers.** A tool returning other keys is refused, with the fix (`mod.name([…])`) | a table with numbered columns must be named | X-D3 |
| **X3** | **Tools receive plain Python values** (`float`, not `np.float64`; `None`, not `NaN`) | nothing, unless a tool relied on numpy types | — |
| **X4** | **The brackets.** A string is a key, an integer a row; a key or row selection can be a step's input; `wf[…]` takes names only; `.header` becomes `.keys` (X-D7). Saved form unchanged (`{"$ref", "rows", "columns"}`) | `cols[…]` and `rows[…]` become optional (X-D6) | X-D6, X-D7 |
| **X5** | **What a tool receives** (§2.3): by type, never by name; a list of rows to a value parameter is refused with the keys to choose from; to a `dict` parameter, a call per row | every formula that relied on binding by name says the key: `to_f(wf["p"]["temp"])` | X-D2 |
| **X6** | **No `auto`.** A bare call iterates by types (X5); `filter` and the rest are written; nothing is added unseen (`breaker` shown, or not added) | `is_hot(wf["p"])` maps to a list of bools; filtering says `mod.filter()` | X-D4 |
| **X7** | **One key named after its step** | `value` becomes the step's name; a rename renames it | X-D5 |
| **X8** | **Row numbers.** Every step numbers its rows `0…n-1`; the links live in `#` columns; core keeps its own key per row for staleness and lineage, never shown | `[i]` is a position; picks don't follow a sample after the data changes | X-D1; the reshaping laws re-run |
| **X9** | **Modifiers don't hand the tool values** (V2): `initial=` → the call (`acc=0`); `sweep` values → the call, `mod.sweep("x", "y")` names what is combined; `over=` goes | the forms in §3's last row | X-D8 |
| **X10** | **Docs and the app.** rules.md (§1 as its first page), step-expressions.md, kernel-session.md and its example; what changes for the app's parser and UI, for app-migration.md | the docs say §1 | — |

**Why this order.** X2 and X3 are small and change little. X4 and X5 are
the heart: once they land, the model in §1 is true. X6 depends on X5 (types
decide iteration). X7 is cosmetic but changes every single-key step's name,
so it goes after the heart is settled. X8 is the largest change (it touches
every reshaping law), so it goes last and alone. X9 is independent and can
move.

## 5. Decisions

| | Decision | Recommended |
|---|---|---|
| X-D1 | Row numbers (`0…n-1` per step, position) or stable row ids? (referencing-proposal Q1) | numbers, with core's internal key for staleness and lineage; anything that must last is written by value (`filter`, a key) |
| X-D2 | Binding by key name: never, or opt-in for workflows built on fixed names? (Q2) | opt-in, explicit: `tool[mod.map(by_name=True)](wf["p"])`, refused when a name is missing |
| X-D3 | Keys: any string, or identifiers only? (Q3) | identifiers, so every key can be typed and read as Python |
| X-D4 | `auto`: remove, or keep as a suggestion the UI shows? (Q4) | remove from formulas; the editor may suggest a verb (`k.infer_verb`); what's saved is what was chosen |
| X-D5 | A single key named after its step, or `value`? (Q11) | after its step; `mod.name` still wins |
| X-D6 | Keep `cols[…]` / `rows[…]`? (Q9) | keep for ranges of keys (`cols["a":"c"]`) and the old forms, printed as the new form; plain brackets are the main way |
| X-D7 | `.header` → `.keys`? | yes: the word the model uses; `.header` stays as a second name only if the app needs it |
| X-D8 | V2: move `initial=`, `sweep`'s values and `over=` into the call | yes, as to-revisit V2 lists |
| X-D9 | **Order against the app's migration** (app-migration.md G-D1): do X2–X7 before the app moves, so its formulas change once? | yes: X2–X7 before the app moves; X8 and X9 after, as their own passes |

## 6. Done means

1. Every law in `test_expressions.py` passes; nothing is expected-to-fail.
2. The property test generates formulas in the new syntax: each saves,
   reloads and prints back the same; two spellings of one reference save the
   same; no tool receives a key, a row number or a `#` column it didn't ask
   for.
3. The reshaping laws (reshaping.md §10) still pass, re-run under X8.
4. rules.md opens with §1, and a user can predict, from a formula alone,
   what each tool receives and how many times it runs.
5. The app's changes are listed in app-migration.md.

## 7. What it doesn't change

The grid underneath: tidy tables, `#` lineage, the matching rule (rule 6),
packing and unpacking without loss, plans before running, `absent`, the empty
step, specs, ids and staleness. This is the syntax on top, and what a tool is
handed.
