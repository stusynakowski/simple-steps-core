# Writing tools

How to write functions the grid model can drive, and how to serve them. Every
example here was run; the outputs are copied from the terminal, not typed.

Companion docs: [defining-operations.md](defining-operations.md) for the grammar
of wiring a tool into a step, [grid-model.md](grid-model.md) for how the
machinery works, [react-api.md](react-api.md) for the HTTP contract.

---

## 1. The one rule

**A tool declares the values it needs. Supplying rows is the modifier's job.**

```python
from simple_steps_core.grid import tool

@tool
def to_fahrenheit(celsius):
    """Convert one Celsius reading to Fahrenheit."""
    return celsius * 9 / 5 + 32
```

That is a whole tool. It takes one reading, returns one number, and knows
nothing about grids, rows, iteration or the workflow. You can call it:

```python
to_fahrenheit(100)      # 212.0
```

When a step maps it over a table, `map` binds the **`celsius` column** to the
**`celsius` parameter**. The column name is the contract.

### What not to write

```python
@tool
def bad(row):                      # ✗
    return row["celsius"] * 9 / 5 + 32
```

This names the row twice — once as a parameter, once as a lookup — hard-codes
the column inside the body, and cannot be called on its own. It is also caught
the moment you wire it:

```
bad() needs 'row', which 'readings' does not have (it has celsius, city)
```

---

## 2. The declaration contract

The grid drives your function **by name**: it reads your signature to bind
columns, to infer a verb, to validate a step before running, and to build the
palette. That only works if a declaration is well formed, so it is worth being
precise about what "well formed" means.

Three tiers, and the difference matters: what `@tool` refuses today, what
*should* be refused because it currently fails silently, and what cannot be
enforced but is load-bearing anyway.

The broken examples below all run against the same two-row grid, so each is
reproducible on its own:

```python
wf = grid.Workflow()
wf["raw"] = pd.DataFrame({"n": [1, 2]})
```

### 2.1 Enforced today

| rule | if you break it |
|---|---|
| the id may not shadow a builtin (`identity`, `gather`, `count`, `total`, `first`, `last`) | `ValueError` at import |
| **every parameter and the return must be annotated** — when `grid.STRICT_TYPES` is on, or `@tool(strict=True)` | `TypeError` at import |

The typing rule is **off by default** so tools written before it existed keep
working; turn it on once, at import time, and it applies to everything declared
after. It is the rule that pays for itself: the annotations are what let
declaration compare a parameter against the upstream column's real dtype
([defining-operations.md §10](defining-operations.md#10-typed-steps)).

```python
from simple_steps_core import grid
grid.STRICT_TYPES = True

@tool
def sloppy(x):
    return x
# TypeError: tool 'sloppy' is not fully typed: parameter 'x' has no type
#            annotation; it has no return annotation.
```

Everything below is still unchecked.

### 2.2 The rules worth hardcoding

Each of these is a declaration the system cannot drive correctly, and each
fails *late* today — three of them with a wrong answer and no error at all.

**a. No positional-only parameters.** Binding is by name, so a positional-only
parameter can never be filled:

```python
@tool
def poso(n, /): return n * 2          # accepted at import

wf["out"] = poso[mod.map()](wf["raw"])
wf.step("out").problems               # ()  — nothing wrong, apparently
wf.run("out")
#    n value
# 0  1  None      every row failed
# 1  2  None
```

**b. No `*args`.** This is the worst case in the set, because it produces a
plausible number rather than a failure. `_d_apply` passes only what the
signature declares by name, and `*args` declares nothing:

```python
@tool
def var(*args): return sum(args)

wf["out"] = var[mod.map()](wf["raw"])
wf.run("out")
#    n  value
# 0  1      0      sum(()) — the tool was called with no arguments
# 1  2      0
```

`catalog()["var"]["params"]` is `[]`, so the palette shows a tool that takes
nothing. A `*args` tool is structurally undrivable; refusing it at import costs
nothing.

**c. The id must be a valid Python identifier.** It is a JSON key, a palette
entry and a dropdown label, and today anything is accepted:

```python
tool(lambda n: n * 2).id        # '<lambda>'   — and every lambda collides
@tool(id="my tool!")            # accepted
```

**d. No mutable default arguments.** A step must be re-runnable — re-driving a
failed unit is central to the model — and a mutable default quietly makes a tool
stateful across runs:

```python
@tool
def accum(n, seen=[]): seen.append(n); return len(seen)

wf.run("out")   # [1, 2]
wf.run("out")   # [3, 4]   same input, different answer
```

**e. One id, one tool — but as a warning, not an error.** A duplicate
registration silently overwrites:

```python
@tool
def dup(n): return "first"
@tool
def dup(n): return "second"      # no complaint; "first" is simply gone
```

For a server importing two tool modules this is a real hazard, and it is
[already noted as a known limit](#10-known-limits). But re-declaration is
legitimate in the two places tools are usually written — re-running a notebook
cell, and a test that declares a throwaway tool per case (this repo's own suite
re-declares `again` five times). So the recommendation here is a warning by
default, with a strict mode for servers, rather than a hard refusal that would
make the model painful in a notebook.

### 2.3 Reserved names

Two names are load-bearing elsewhere in the system and will collide silently.

**`column` is reserved as a grid column name.** The builtins resolve which cell
is the payload by popping `column` from the row, so a data column of that name
hijacks the resolver:

```python
wf["raw"] = pd.DataFrame({"column": ["nope"], "celsius": [10]})
wf["g"]   = op("gather")[mod.collapse()](wf["raw"])
wf.run("g")
wf.step("g").status                          # 'failed'
wf.step("g").output.ledger["error"]          # ["KeyError: 'nope'"]
```

Worse, when the value *happens* to name a real column it silently redirects
rather than failing. A tool parameter called `column` is fine — only the grid
column is reserved.

**`sweep` reserves `name`, `retries` and `over`**, so a swept parameter cannot
use those names. Today the collision surfaces as a cryptic pandas error:

```python
@tool
def cell(name): return name

wf["s"] = cell[mod.sweep(name=["a", "b"])]   # `name` is the payload column name
wf.run("s")
# TypeError: unhashable type: 'list'
```

### 2.4 Load-bearing conventions

These cannot be enforced from a signature, but something downstream reads them,
so breaking one degrades the system quietly rather than loudly.

**The return annotation changes the inferred verb.** It is optional, but when
present it decides behaviour — `bool` means `filter`, `list`/`tuple`/`set` means
`expand`. An annotation that lies is obeyed:

```python
@tool
def liar(n) -> bool: return n * 10

wf["out"] = liar(wf["raw"])
# <Operation filter(over='raw') ∘ liar>   — a filter, and 10 is truthy
```

So annotate a predicate `-> bool` and a fan-out `-> list[...]`, and make sure a
mapper's annotation is true.

Note the tension this creates with strict typing (§2.1): once **every** tool is
annotated, an ordinary `map` that happens to return a bool is indistinguishable
from a predicate, so inference will read it as a `filter`. The two are
compatible in one direction only — **the more you type your tools, the more you
should name the verb explicitly** rather than letting it be inferred.

**The docstring's first line is the palette description.** Omit it and the
client shows an empty string:

```python
catalog()["undocumented"]["description"]     # ''
```

Write it as a user-facing sentence, not a developer note.

**`**kwargs` opts out of input checking.** A tool that takes the whole row can't
be verified against the upstream, so the "required value the upstream cannot
supply" check goes quiet for it. `catalog()` reports this as
`takes_whole_row: True`. Use it when you mean it (§7), not as a shortcut.

**A tool should be a pure function of its arguments.** Nothing checks it, but a
step may be re-run, re-driven after a failure, or run per row in any order.

**Name the payload column you write, and don't collide with your input.** A map
whose `name=` matches an existing column overwrites it, which loses the lineage:

```python
@tool
def bump(value): return value + 1

wf["a"] = bump[mod.map()](wf["raw"])   # writes the default column, `value`
wf["b"] = bump[mod.map()](wf["a"])     # reads `value`, overwrites `value`
#    value
# 0      3    right answers, but what they were computed from is gone
# 1      4
```

### 2.5 The contract, as a checklist

A tool is well formed when:

- [ ] every parameter can be filled **by name** — no positional-only, no `*args`
- [ ] the id is a valid identifier, unique, and not a builtin's name
- [ ] no mutable default arguments
- [ ] no parameter needs a grid column called `column`, and no swept parameter is
      called `name`, `retries` or `over`
- [ ] a predicate is annotated `-> bool`; a fan-out `-> list[...]`; nothing else
      is annotated unless it is true
- [ ] the first docstring line is a sentence a user would read
- [ ] it is pure, and safe to run twice

The first three tiers are mechanical and could be checked at import; the rest is
why the checklist exists.

---

## 3. A worked example

```python
import pandas as pd
from simple_steps_core.grid import Workflow, tool, mod

@tool
def to_fahrenheit(celsius):
    return celsius * 9 / 5 + 32

@tool
def is_freezing(celsius) -> bool:
    return celsius <= 0

@tool
def warmest(hottest, fahrenheit):
    return fahrenheit if hottest is None else max(hottest, fahrenheit)

wf = Workflow()
wf["readings"] = pd.DataFrame({
    "city":    ["Oslo", "Cairo", "Lima"],
    "celsius": [-5, 38, 19],
})

wf["f"]    = to_fahrenheit[mod.map(name="fahrenheit")](wf["readings"])
wf["cold"] = is_freezing(wf["readings"])
wf["peak"] = warmest(wf["f"])
```

Nothing has run. The workflow already knows its shape:

```
  readings  completed  source identity · 3 cells
  f         staged     map to_fahrenheit · 3 cells
  cold      staged     filter is_freezing · at most 3 cells
  peak      staged     collapse warmest · 1 cell
```

Note `is_freezing` and `warmest` got `filter` and `collapse` without being told
(§5), and `filter` promises *at most* 3 — never more than it can guarantee.

```python
wf.run_all()
```

```
    city  celsius  fahrenheit
0   Oslo       -5        23.0
1  Cairo       38       100.4
2   Lima       19        66.2
```

`map` **keeps the input columns** and adds one. That is the whole difference
between a spreadsheet and a list comprehension: `city` is still there.

---

## 4. One tool shape per verb

### `map` — one value in, one value out

```python
@tool
def to_fahrenheit(celsius):
    return celsius * 9 / 5 + 32
```

Use `mod.map(name="fahrenheit")` to name the column it writes. Worth doing:
downstream tools read columns by name, so a named column makes the next tool
read `fahrenheit` instead of the anonymous default `value`.

### `filter` — return a bool

```python
@tool
def is_freezing(celsius) -> bool:
    return celsius <= 0
```

The `-> bool` annotation is what makes this a filter rather than a column of
flags. The data keeps the survivors; the **ledger keeps every unit**, so you can
still see what was dropped:

```
data                    ledger
   city  celsius           status   kept
0  Oslo       -5        0  completed   True
                        1  completed  False
                        2  completed  False
```

### `collapse` — take an accumulator first

```python
@tool
def warmest(hottest, fahrenheit):
    return fahrenheit if hottest is None else max(hottest, fahrenheit)
```

The **first** parameter is the running value and gets `None` on the first row —
handle that. Every later parameter binds from columns as usual. Read the result
with `.item()`, since collapse returns a one-row grid:

```python
wf.step("peak").output.item()      # 100.4
```

### `expand` — return many values

```python
@tool
def words(note) -> list[str]:
    return note.split()
```

Each input row becomes several output rows:

```
expand words · 5 cells -> ['clear', 'sky', 'heavy', 'rain', 'today']
```

### `sweep` — no input at all

```python
@tool
def area(width, height):
    return width * height

wf["grid"] = area[mod.sweep(width=[2, 3], height=[10, 20])](None)
```

Every swept parameter becomes a column, so the result is a tidy table you can
group and filter:

```
   width  height  value
0      2      10     20
1      2      20     40
2      3      10     30
3      3      20     60
```

---

## 5. Let the verb be inferred

`score(wf["raw"])` picks the iteration from the tool's signature:

| what you wrote | inferred | why |
|---|---|---|
| `def f(x)` | `map` | one value in, one out |
| `def f(x) -> bool` | `filter` | a predicate |
| `def f(x) -> list[str]` | `expand` | many values per row |
| `def f(acc, x)` | `collapse` | the first value is not a column, so it is an accumulator |

Two things make this safe rather than magic:

**The verb is stored concretely.** Nothing named `auto` reaches the data — the
step holds an ordinary `map`, indistinguishable from one you typed, so it shows
up in a repr or a dropdown and you can replace it:

```python
wf["as_lists"] = words[mod.map()](wf["notes"])   # I really do want lists
```

**It is inferred once, when you wire the step.** A later change upstream never
silently rewrites a verb you chose.

Annotations are the whole signal here, so `-> bool` and `-> list[str]` earn
their keep. Without them everything is a `map`, which is a fine default and
trivially overridden.

---

## 6. Constants: `bind`

Parameters with defaults are knobs, not columns:

```python
@tool
def scaled(celsius, factor=1.0):
    return celsius * factor

wf["scaled"] = scaled(wf["readings"], factor=2.0)     # [-10.0, 76.0, 38.0]
```

`factor` is fixed for the whole step and travels with it as data. A bound value
also **satisfies a required parameter the grid cannot supply**, which is how you
fill in a column that isn't there:

```python
wf["x"] = score(wf["odd"])            # score() needs 'n', which 'odd' does not have
wf["y"] = score(wf["odd"], n=7)       # valid
```

A column always wins a collision with a bound literal — the row is the unit of
work.

---

## 7. When you really do want the whole row

```python
@tool
def summary(**row):
    return f"{row['city']}: {row['celsius']}C"
```

```
['Oslo: -5C', 'Cairo: 38C', 'Lima: 19C']
```

`**kwargs` receives every column. Use it for genuinely row-shaped work —
formatting, serializing, a summary line. Reach for it rarely: a tool with named
parameters is checkable at declaration and one with `**row` is not.

---

## 8. Serving them

`@tool` registers the function in `TOOLS`, so a workflow that arrives as JSON
can be turned back into something runnable by importing the module that declares
them.

```python
# tools.py — import this once at startup
from simple_steps_core.grid import tool

@tool
def to_fahrenheit(celsius): ...
```

```python
# server.py
import tools                                    # registers everything
from simple_steps_core.grid import Workflow

wf = Workflow.from_json(request.body)           # no name→function map needed
wf.run_all()
return wf.to_session_json()
```

Two export modes, differing only in payloads: `to_json()` is the recipe
(structure only, a few hundred bytes — cheap enough to autosave on every
keystroke), `to_session_json()` adds the data.

A workflow reloaded from the **light** export has no source data, and says so
rather than computing something wrong:

```
source step 'readings' has no data. Assign it: wf['readings'] = <a frame, list or value>
```

### Checklist for a servable tool

| | |
|---|---|
| **Takes named values, not a row** | otherwise nothing can be checked at declaration |
| **Returns something JSON-safe, or a handle** | object payloads cannot be exported — `to_json` writes `{}` silently, so the codec refuses them |
| **Annotate `-> bool` / `-> list`** | it is what inference reads |
| **Pure, or honest about not being** | nothing recomputes on its own today, but caching and staleness assume purity |
| **Deterministic names** | the tool id is its function name; renaming breaks saved workflows |

---

## 9. What gets caught before anything runs

Declaring a step never raises. An unusable step still exists, carrying its
problems, so an editor can show it mid-keystroke:

| mistake | message |
|---|---|
| takes a row | `bad() needs 'row', which 'readings' does not have (it has celsius, city)` |
| wrong column name | `needs_temp() needs 'temp', which 'readings' does not have (it has celsius, city)` |
| typo in a bound value | `score() takes no argument 'wieght'; it accepts weight` |
| reads a step that does not exist | `map over 'nope', which is not an earlier step` |
| a cycle | `map over 'b' is circular` |

Running is what refuses:

```
step 'twice' reads 'scored', which has not run. Run 'scored' first, or call run_all().
```

---

## 10. Known limits

- **No resources.** The engine injects databases and clients via `Resource()`;
  the grid prototype has no equivalent, so tools must take their inputs as
  values.
- **No async.** Tools are called synchronously. `timeout` records intent and
  does not yet enforce.
- ~~**Column types are not checked.**~~ **Resolved** for annotated tools:
  declaration compares each parameter's annotation against the upstream column's
  dtype, and each bound literal against its own. Only certain mismatches are
  reported; an undecidable annotation is not an error. See
  [defining-operations.md §10](defining-operations.md#10-typed-steps).
- **The tool id is the function name**, with no namespacing. Two tools with the
  same name in different modules collide in `TOOLS`.
