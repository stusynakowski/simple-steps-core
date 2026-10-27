# Step expressions: what a step may say

> Proposed 2026-10-26. A step is declared as `k["name"] = <expression>`. The
> same expression is a line in a Python session and, as text, a formula in the
> app's formula bar. This document is the grammar both must accept. Core
> checks the meaning; the app's parser checks the text ([object-model.md §6](object-model.md#6-the-boundary-with-the-apps-formula-bar)).

## 1. The general form

```
tool[modifiers](input, arguments)

with_tax[mod.map(), mod.name("total"), mod.retry(times=2)](wf["items"], rate=0.1)
└ tool  └ one shape verb, then naming and execution modifiers  └ input  └ arguments
```

| Part | Allowed |
|---|---|
| **tool** | a tool's name in the catalog, a built-in (`identity`, `count`, …), or a resource's bound tool: `res["db"].lookup` |
| **modifiers** | at most one shape verb, written first, then any naming, execution, error-handling, expectation or observation modifiers. Settings are literals (or a tool, for `group(by=…)`) |
| **input** | at most one reference to an **earlier** step: `wf["p"]` or `wf[0]` |
| **arguments** | by keyword. Each is a literal or a reference (§3) |

## 2. The other forms

Each is a short way to write something the general form also says.

| Form | Example | Means |
|---|---|---|
| no brackets | `scale(wf["r"])` | the verb is inferred from the tool's types; saved as `auto` |
| a source | `patients[mod.source()]()`, `to_rows[mod.source()](data="…")` | no input: the step makes a grid |
| a sweep | `fit[mod.sweep(model=["a", "b"], k=[1, 2])]()` | no input: one row per combination |
| a literal | `7`, `[3, 1, 2]`, `{"x": 1}`, a DataFrame (Python only) | a source holding that value |
| a reshape | `mod.sort(by="n")(wf["r"])`, `mod.select(columns=["n"])(wf["r"])` | a verb that runs no tool. `identity[mod.sort(by="n")](wf["r"])` is the same step |
| a selection | `wf["r"][0:2]`, `wf["r"][cols["n"]]`, `wf["r"][0][cols["w"]]` | part of a step, as its own step |
| a built-in reducer | `count[mod.collapse(by="city")](wf["r"])` | `count`, `total`, `gather`, `first`, `last` |
| a combine | `join(wf["a"], wf["b"], on="id")`, `stack(…)`, `zip_(…)` | the **only** way to read several steps |
| a bound tool | `res["db"].lookup[mod.map()](wf["ids"])` | a tool that lives on a resource instance |

## 3. References and selections

| Written | Refers to |
|---|---|
| `wf["p"]`, `wf[0]` | step `p`; the first step. Saved by name either way |
| `wf["p"][1:5]`, `wf["p"][1]`, `wf["p"][rows[[1, 3]]]` | rows, by row id (K19; *today* by position). A list of rows is a list: `rows[[1, 3]]`, not `rows[1, 3]` |
| `wf["p"][cols["n"]]`, `wf["p"][cols["a":"c"]]`, `wf["p"][cols[["a", "c"]]]`, `wf["p"][cols["#"]]` | columns; `#` is the row id (R-D11, owner 2026-10-27; *today* it is the row number, [reshaping.md](reshaping.md) R8) |
| `wf["p"][0][cols["w"]]` | one cell |
| `wf["p"].header` | the column names. As an argument, a list (`['name', 'temp_c']`). As a step, *today* one row per name in a column called `name`; whether it should be one row per name (in a column called `column`) or one cell holding the list is open. `header[k]` should pick one name; *today* the `[k]` is ignored (C28) |
| `res["db"]` | a resource, passed to a tool's parameter |

Where each may go:

| | as a step | as the input | as an argument |
|---|---|---|---|
| a step, `wf["p"]` | — | yes | yes: one-cell steps are their value (C19) |
| rows or columns | yes | **no**: make it its own step first | yes: a column pairs per row by type (K19) |
| a cell | yes | no | yes: the same value for every row |
| a resource, `res["db"]` | no | no | yes |

Rules:

- **A step reads only earlier steps.** A reference to a later or missing step
  is a problem on the step. There are no cycles.
- Bare integers select rows; `cols[...]` selects columns; column names are
  strings. `rows` and `cols` are reserved names.

## 4. Literals

The literal types are fixed by core: `None`, `True` / `False`, `int`, `float`,
`str`, and `list`, `tuple`, `dict`, `set` of literals. They are saved exactly:
a tuple stays a tuple, an `int` key stays an `int` (C11). Anything else in an
argument is refused when the step is declared.

## 5. Printing: `to_source()`

`op.to_source()` prints the expression in its canonical form. The app's parser
must read back everything it prints, and reading it back must give the same
operation (the round trip the app tests). Canonical means: verb always written
(an inferred step prints `mod.auto()`), modifiers in written order, keyword
arguments.

**A step's formula** is `step.formula`: a literal step's value, or its
operation's `to_source()`. Since phase 4 (G4, 2026-10-27), every form prints as
it is written, and declaring the printed formula gives back the same step
(tested for each form in `tests/unit/test_formulas.py`):

| Written | Prints |
|---|---|
| `[3, 1, 2]` | `[3, 1, 2]` |
| `mod.sort(by="n")(wf["r"])` | `mod.sort(by="n")(wf["r"])` (likewise `drop`, `rename`, `slice`, `distinct`, `widen`) |
| `wf["r"][0:2]`, `wf["r"][1][cols["n"]]`, `wf["r"].header`, … | as written |
| `mod.select(columns=["n"])(wf["r"])` | `wf["r"][cols["n"]]`: the same step, so one printed form |
| `mod.select(columns=wf["which"])(wf["r"])` | as written: a reference as a setting isn't a selection |
| `wf["r"].header[1]` | `mod.select(rows=1, columns={"header": True})(wf["r"])`, until C28 settles what `header[k]` means |
| `count[mod.collapse()](wf["r"])` | `op("count")[mod.collapse()](wf["r"])`: built-in tools print through `op` |
| `join(a, b, on="id")` | with its defaults spelled out (`how="inner"`, `suffixes=[…]`) |

A DataFrame assigned in Python prints as `<DataFrame 3×2>`: it is data, not a
formula.

## 6. What an expression can't contain, and why

| Not allowed | Why | Core does |
|---|---|---|
| a reference to a later step | steps run in order; it would allow cycles | a problem (`later_step`). **Never allowed** |
| a selection as a tool's input | one step, one job: a selection is its own step | a problem (`selection_as_input`) |
| a tool not in the kernel's catalog | the catalog is the only source of code | a problem (`not_in_catalog`); never runs |
| a step as a modifier setting (`mod.sort(by=wf["r"])`) | settings decide shape; data-dependent shape can't be planned | a problem (`wrong_type`) |
| two shape verbs | one step has one shape; it couldn't be planned or followed row by row | a problem, whose message says to split the step and group the parts with a stage |
| `*args` in a tool | arguments are named | refused when the tool is made |

**Allowed, with a warning when declared:** a shape verb written after an
execution modifier, `dbl[mod.retry(times=2), mod.map()]`. Order is meaning, so
`retry` then covers the whole step rather than each row
([grid-model.md §6](grid-model.md#6-modifiers-are-decorators-applied-at-run-time)).
A `try_except` default that doesn't fit the tool's return type is also a
warning ([grid-model.md §5.1](grid-model.md#51-handled-failures)).

**The Python session and the formula bar differ in one way.** In Python,
anything written in an argument is worked out by Python before core sees it:
`weight=len("abc")` reaches core as `3`, and core only ever sees the literal. In
the formula bar nothing is worked out: the parser accepts only literals,
references and names in the catalog (`wf`, `res`, `mod`, `rows`, `cols`, the
combines and the tools), because running a computed argument would mean running
Python a user typed. A computation worth keeping becomes a catalog tool, so its
result is a step.

## 7. Saved form

A step's spec saves the expression as data, never as text:

```json
{"name": "f",
 "operation": {"tool": "to_f",
               "modifiers": [{"kind": "map", "settings": {}}],
               "inputs": [{"$ref": "sick"}],
               "arguments": {}},
 "extras": {}}
```

Modifiers are saved in written order. References are `{"$ref": name}` (with
`rows` / `columns` for a selection) and `{"$res": name}`. Literals that JSON
can't hold exactly are tagged (`{"$tuple": […]}`, `{"$set": […]}`).
