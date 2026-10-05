# Defining an operation for a step

You have a `Workflow` and a registered tool. This is how you turn them into a
step. Every example here was run; the outputs are copied from the terminal, not
typed.

Companion docs: [writing-tools.md](writing-tools.md) for the function side (how
to write a tool the grid can drive), [grid-model.md](grid-model.md) for how the
machinery works, [shape-algebra.md](shape-algebra.md) for why.

```python
import pandas as pd
from simple_steps_core import grid
from simple_steps_core.grid import mod, op, tool

wf = grid.Workflow()
```

Import the **module** for `grid.Workflow` — `Workflow`, `Operation` and `Step`
also exist in the engine and mean different things there. `mod`, `op` and `tool`
are unambiguous, so importing those by name is fine.

---

## 1. The whole grammar in one line

A step is an assignment into the workflow:

```python
wf[step_id] = <tool>[ mod.<verb>(**verb_params), mod.<exec>(...) ](<input>)
```

Read it as three separate decisions, because that is what it is:

| position | decides | example |
|---|---|---|
| `<tool>` | **what** runs on one unit of work | `to_fahrenheit` |
| `[mod.<verb>(...)]` | **how** it iterates — the shape change | `mod.map(name="fahrenheit")` |
| `(<input>)` | **which step** it reads | `(wf["readings"])` |

Each thing is named exactly once. The input is data, so it arrives in the call
position; `over=` (§2b) is the same step written the other way round.

Nothing is applied and nothing runs. The right-hand side evaluates to an
`Operation`, which is **data** — a tool id, an ordered list of modifiers, and
bound literals. `wf[...] =` stores it and stages it.

---

## 2. Ways to write the right-hand side

They all produce the same kind of `Operation`. One is the form to write; the
others are worth knowing because you will read them.

### a. The canonical form — verb in brackets, data in parens

```python
wf["with_f"] = to_fahrenheit[mod.map(name="fahrenheit")](wf["readings"])
```

**Brackets decorate, parens apply.** Read left to right it is the sentence you
mean: *this tool, mapped, writing this column, over this data.*

Three different names are being set, and it is worth separating them before they
blur together:

| | names | lives in |
|---|---|---|
| `wf["with_f"]` | the **step** — a node in the graph | the workflow |
| `mod.map(name="fahrenheit")` | the **column** this step writes | the grid |
| `(wf["readings"])` | the **input** — which step this one reads | the graph again |

They are not redundant with each other because a `map` step does not produce *a
value*, it produces **the input grid plus one column**. So `with_f` is the whole
table and `fahrenheit` is one column in it. Naming the step and the column the
same word is possible but misleading — this document used to, which made `name=`
look like ceremony.

**You never type `over=`.** The call position is the input:

```python
wf["with_f"] = to_fahrenheit[mod.map()](wf["readings"])
wf.step("with_f").operation.to_dict()["modifiers"]
# [{'kind': 'map', 'params': {'over': 'readings'}}]      <- `over` is what the parens became
```

### b. `over=` — the same step, and what actually gets stored

```python
wf["with_f"] = to_fahrenheit[mod.map(over=wf["readings"], name="fahrenheit")]
```

These two are **the same `Operation`**, byte for byte:

```python
to_fahrenheit[mod.map()](wf["readings"]) == to_fahrenheit[mod.map(over=wf["readings"])]
# True
```

Wiring writes `over` into the shape verb, so the stored data is identical either
way. That is deliberate: `over` is where `check`, staging, cycle detection and
the light export all read a step's input, so it has to end up in the modifier.
The call position is sugar over it, not a second mechanism — which is why you can
write the readable form and still get a workflow that serializes and validates.

You will see `over=` in a `repr`, in `to_dict()`, and in anything a UI round-trips.
Two details, once you are writing the call form:

- **`over` lands on the shape verb**, never on an execution modifier:

  ```python
  to_fahrenheit[mod.map(), mod.retry(times=2)](wf["readings"])
  # [{'kind': 'retry', 'params': {'times': 2}},
  #  {'kind': 'map',   'params': {'over': 'readings'}}]
  ```

- **the call position wins.** Wiring overwrites an `over=` already in the
  brackets rather than complaining, so the last thing you wrote is the input.

### c. A bare value — a source step

```python
wf["readings"] = pd.DataFrame({
    "city": ["SF", "NYC", "LA", "Boston"],
    "celsius": [18.0, 31.0, 29.0, 9.0],
})
```

```
<Step 'readings' completed · source identity · 4 cells>
```

Already `completed`, not `staged`: a source step's data **is** its output — it
arrived with the declaration, so there is nothing to compute. Lists, dicts,
Series and scalars work too; `rows()` coerces them.

### d. A bare shape verb — reshaping with no tool of your own

```python
wf["flat"] = mod.expand(over=wf["nested"])
wf["all"]  = mod.collapse(over=wf["xs"])
```

The verb resolves to **the tool that discards nothing** — `identity` for the
mapping verbs, `gather` for `collapse`. This is the one form that **must** use
`over=`: there is no tool to put brackets on, and a bare `Modifier` is not
callable. Reach for `op("identity")[mod.expand()](wf["nested"])` if you would
rather keep the data last everywhere.

An *execution* modifier alone is refused, since a pass-through that retries is
inert:

```python
wf["bad"] = mod.retry(times=2)
# TypeError: 'retry' needs a tool: it is an execution modifier, which changes
#            nothing on its own. Write <tool>[mod.retry(...)] instead.
```

### e. The bare shorthand — and what it costs

```python
wf["with_f"] = to_fahrenheit(wf["readings"])
```

With no verb to place, the verb is **inferred** — once, at this moment, and
stored concretely:

```
<Operation map(over='readings') ∘ to_fahrenheit>
```

Nothing named `auto` is ever stored, so what you get back is indistinguishable
from a `mod.map()` you wrote, and it is visible in a repr and replaceable.
Inference reads the tool's signature:

| signal | verb | example |
|---|---|---|
| first required parameter matches no column, second does | `collapse` | `warmest(acc, fahrenheit)` |
| return annotation is `bool` | `filter` | `is_hot(fahrenheit) -> bool` |
| return annotation is `list` / `tuple` / `set` | `expand` | `split(n) -> list` |
| otherwise | `map` | `to_fahrenheit(celsius)` |

`grid.infer_verb` also returns its reason, which a UI can show as a caption:

```python
grid.infer_verb(warmest.fn, wf.step("with_f").output, {})
# ('collapse', "'acc' is not a column but 'fahrenheit' is, so this reads as a reducer")
```

It is convenient, and it has three consequences worth knowing before you rely
on it.

**1. It cannot name the column it writes.** Keyword arguments in that call are
*tool* literals — they go to `bind`, not to the verb. So there is no way to pass
`name=`:

```python
wf["x"] = score(wf["raw"], weight=2)      # weight -> bind, fine
wf["x"] = score(wf["raw"], name="points")
# problems: ("score() takes no argument 'name'; it accepts weight",)
```

Which means the shorthand always writes the default column, `value` — and a
chain of shorthand steps has every step overwriting the last one's output
column, so the lineage is gone. Naming the column is the main reason to prefer
the bracket form (§5).

**2. A reducer can silently become a mapper.** Inference recognizes a reducer by
seeing that the second parameter *is* a column. When it is not — because the
upstream writes `value` and your reducer asks for `points` — it falls through to
`map`, and reports no problem at all:

```python
wf["scored"] = score[mod.map()](wf["raw"])          # writes `value`
wf["total"]  = add_pts(wf["scored"])                # add_pts(acc, points)

wf.step("total").operation      # <Operation map(over='scored') ∘ add_pts>  — not collapse
wf.step("total").problems       # ()
```

It fails at run time, per row, with `add_pts() missing 2 required positional
arguments`. Writing `mod.collapse()` would have been checked instead.

**3. It depends on the return annotation being true.** `-> bool` means `filter`,
so an annotation that lies is obeyed — see
[writing-tools.md §2.4](writing-tools.md#24-load-bearing-conventions).

> **The rule of thumb.** Use the shorthand while exploring, in a notebook, where
> you can see the repr and fix it in place. Write the verb in brackets in
> anything you keep: it is one token longer, it names the column, and it moves
> two of the three failures above from run time to declaration.

---

## 3. A worked pipeline

Four tools, registered the ordinary way. Each takes the values it needs and
knows nothing about grids:

```python
@tool
def to_fahrenheit(celsius: float) -> float:
    """Convert one Celsius reading to Fahrenheit."""
    return celsius * 9 / 5 + 32

@tool
def is_hot(fahrenheit: float) -> bool:
    """Keep the readings above 80F."""
    return fahrenheit > 80

@tool
def coast(city: str) -> str:
    """Which coast a city is on."""
    return "west" if city in ("SF", "LA") else "east"

@tool
def warmest(acc: float | None, fahrenheit: float) -> float:
    """The highest reading seen so far."""
    return fahrenheit if acc is None else max(acc, fahrenheit)
```

Every parameter and every return is annotated. That is not decoration: `check`
compares those types against the upstream's real dtypes, and the palette
publishes them (§10).

### `map` — n rows in, n rows out, plus a column

```python
wf["with_f"] = to_fahrenheit[mod.map(name="fahrenheit")](wf["readings"])
```

The step exists and is already staged. Before anything runs:

```python
wf.step("with_f")
# <Step 'fahrenheit' staged · map to_fahrenheit · 4 cells>

wf.step("with_f").operation.to_dict()
# {'tool_id': 'to_fahrenheit',
#  'arguments': {},
#  'modifiers': [{'kind': 'map', 'params': {'over': 'readings', 'name': 'fahrenheit'}}]}
```

That dict is the entire step definition — which is why exporting a workflow is
nearly free. Now run it:

```python
wf.run("with_f")
```

```
     city  celsius  fahrenheit
0      SF     18.0        64.4
1     NYC     31.0        87.8
2      LA     29.0        84.2
3  Boston      9.0        48.2
```

**Input columns are kept.** Mapping a conversion over a table gives you the
table plus a column, not a bare list of numbers.

### `filter` — keep the rows that pass

```python
wf["hot"] = is_hot[mod.filter()](wf["with_f"])
wf.run("hot")
```

```
  city  celsius  fahrenheit
1  NYC     31.0        87.8
2   LA     29.0        84.2
```

Columns unchanged, no new column, and the **index is preserved** — row 1 is
still row 1. The dropped rows are not gone, they are in the ledger:

```python
wf.step("hot").output.ledger[["status", "kept"]]
```

```
      status   kept
0  completed  False
1  completed   True
2  completed   True
3  completed  False
```

So "excluded" and "failed" stay distinguishable, and either is re-drivable.

### `group` — mark each row with a key

```python
wf["coast"] = coast[mod.group(name="coast")](wf["with_f"])
wf.run("coast")
```

```
     city  celsius  fahrenheit coast
0      SF     18.0        64.4  west
1     NYC     31.0        87.8  east
2      LA     29.0        84.2  west
3  Boston      9.0        48.2  east
```

Nothing nests. `group` only labels; reducing is `collapse(by=...)`.

### `collapse` — reduce, optionally per group

The tool takes an **accumulator first**. That arity is the whole difference
between a reducer and a mapper:

```python
wf["peak"] = warmest[mod.collapse(by="coast", name="peak_f")](wf["coast"])
wf.run("peak")
```

```
  coast  peak_f
0  west    84.2
1  east    87.8
```

Without `by`, one row for everything:

```python
wf["overall"] = warmest[mod.collapse(name="peak_f")](wf["with_f"])
wf.run("overall")
```

```
   peak_f
0    87.8
```

Use `initial=` when `None` is not a valid starting accumulator.

### `select` / `drop` — rearrange columns, run nothing

```python
wf["report"] = op("identity")[mod.select(columns=["city", "fahrenheit"])](wf["with_f"])
wf.run("report")
```

```
     city  fahrenheit
0      SF        64.4
1     NYC        87.8
2      LA        84.2
3  Boston        48.2
```

`columns=` is ordered — reordering is half the reason to reach for it. These
verbs apply **no tool**, so `op("identity")` (or the bare-verb form in §2b) is
the only legal tool and anything else is refused. You rarely need `select`
*before* a map, since binding already hands a tool only what it declares; its
job is narrowing what downstream sees.

### `widen` — a record's fields become columns

The column-axis twin of `expand`: that one makes a collection **longer**, this
makes a record **wider**. Reach for it when a tool hands you dicts.

```python
wf["recs"] = fetch[mod.expand()](wf["seed"])       # one row per record
wf["wide"] = mod.widen(columns=["city", "temp"], over=wf["recs"])
wf.run_all()
```

```
   n                          value city  temp
0  1   {'city': 'SF', 'temp': 18.0}   SF  18.0
1  1  {'city': 'NYC', 'temp': 31.0}  NYC  31.0
```

Now a downstream tool can bind to `temp` by name, which it could not do while the
fields were inside one cell.

**`columns=` is required, and that is the design.** The fields live in the data,
so discovering them at run time would make this the one verb whose *column set*
is unknowable before it runs. `expand` is allowed not to know its row **count**;
unknown **columns** are not survivable, because `check` validates every
downstream step against column names — each would become unvalidatable until this
step ran. Declaring them keeps staging exact:

```python
predicted_columns(wf.step("wide").output)    # ['n', 'value', 'city', 'temp']
```

It applies **no tool** (`identity` finds the cell holding the record), but unlike
`select` and `drop` it does read something per row, so it keeps a real ledger. A
cell that is not a mapping, or a record missing a declared field, is a **per-unit
failure** — the row keeps `None` there, the rest of the fields still land, and the
unit is re-drivable:

```
      status                                       error
0  completed                                         NaN
1     failed  KeyError: the record has no 'b' (it has a)
```

The input cell is **kept**, like every carried column. `drop` it in a later step
if the raw record is noise.

### `slice` — rows by position

The one selection no tool can make: a tool never sees its row index, not even
with `**row`.

```python
wf["first2"] = mod.slice(stop=2, over=wf["raw"])            # the first two
wf["mid"]    = mod.slice(start=1, stop=3, over=wf["raw"])   # half-open, like Python
wf["picked"] = mod.slice(at=[0, 3], over=wf["raw"])         # exactly these
```

`at=` and `start=`/`stop=` are exclusive — one names positions, the other a
range. Applies no tool, so nothing can fail.

**Positional selection is brittle**, and worth saying out loud: position 2 is a
different row the moment upstream data changes. `filter` with a predicate
survives that and records in its ledger which rows it kept. Use `slice` for
"the first N" and fixed offsets, not for picking records.

### `rename` — change a column's name

```python
wf["r"] = mod.rename(columns={"n": "count"}, over=wf["raw"])
```

The piece between a step's output and the next tool's parameter names. Without
it, matching the two took a `map` over `identity` and then a `select` — two
steps of pure plumbing. Strict about a name that is not there, and it **refuses
to overwrite** an existing column rather than silently losing it.

### `sort` / `distinct` — reorder, and drop duplicates

```python
wf["asc"]  = mod.sort(by="n", over=wf["raw"])                   # one column
wf["desc"] = mod.sort(by=["city", "n"], ascending=False, over=wf["raw"])
wf["uniq"] = mod.distinct(columns=["city"], over=wf["raw"])
```

`sort` moves rows without renaming them — **the index travels with its row**, so
a cell keeps its address and the ledger stays joinable. `distinct` keeps the
**first** of each duplicate group, and its index, so what survives is still
addressable. With no `columns=`, a whole-row comparison.

### `sweep` — generate the grid from parameter lists

```python
wf["cells"] = render[mod.sweep(model=["a", "b"], window=[7, 30], name="label")]
```

```
  model  window label
0     a       7   a-7
1     a      30  a-30
2     b       7   b-7
3     b      30  b-30
```

No `over=` — `sweep` has no input; it builds its rows from the cross product,
and every swept parameter becomes a column you can then group and filter by.

### Running a chain

```python
wf.run_all()      # every valid step, each after the steps it reads
```

`run(step_id)` refuses a step whose input has not run, rather than coercing a
staged upstream into a grid of `None`:

```
ValueError: step 'hot' reads 'fahrenheit', which has not run.
            Run 'fahrenheit' first, or call run_all().
```

Nothing ever recomputes on its own.

---

## 4. The grammar, precisely

```
step          := workflow "[" step_id "]" "=" operand

operand       := operation                       # (a) / (b) / (e)
               | literal                         # (c) source step
               | shape_modifier                  # (d) bare verb, default tool

operation     := tool_expr [ decoration ] [ wiring ]

tool_expr     := tool_handle                     # a @tool-decorated function
               | tool_handle ".bind(" literals ")"
               | "op(" tool_id [ "," literals ] ")"

decoration    := "[" modifier { "," modifier } "]"

wiring        := "(" step_ref [ "," literals ] ")"   # the input — canonical

modifier      := "mod." shape_verb "(" [ verb_params ] [ "over=" step_ref ] ")"
               | "mod." exec_mod "(" exec_params ")"

step_ref      := workflow "[" step_id "]"        # preferred — a typo is a KeyError
               | string                          # accepted; serializes the same
```

Four rules govern the whole thing:

1. **At most one shape verb per operation.** Two shape changes in one step would
   make an intermediate grid with no cell address, so a unit that failed there
   could not be inspected or re-run.
2. **The input belongs to the shape verb.** Whether you pass it in the call
   position or as `over=`, it is stored on that verb — and never on an execution
   modifier: `score[mod.map()](wf["raw"]) == score[mod.map(over=wf["raw"])]`.
3. **Written order is outermost-first**, like stacked `@` lines.
4. **Everything is data.** A plain decorator would not serialize, so a bracket
   layer must be a `Modifier`; passing anything else is a `TypeError`.

`wiring` and `over=` are alternatives, not both — and if you write both, the
call position wins. The only operand that *requires* `over=` is the bare shape
verb, which has no tool to decorate (§2d).

### Verb reference

Every shape verb takes its input from the call position, or equivalently from
`over=`. `name=` sets the column the step writes.

| verb | modifier params | tool signature | writes | rows out |
|---|---|---|---|---|
| `source` | — | no tool (`identity`) | — | same |
| `map` | `name="value"`, `retries=0`, `axis="rows"` | `(cols…) -> Any` | `name` | same |
| `filter` | `retries=0`, `axis="rows"` | `(cols…) -> bool` | nothing | at most n |
| `group` | `name="group"`, `retries=0`, `axis="rows"` | `(cols…) -> key` | `name` | same |
| `expand` | `name="value"`, `retries=0`, `axis="rows"` | `(cols…) -> Iterable` | `name` | unknown |
| `collapse` | `by=None`, `initial=None`, `name="value"` | `(acc, cols…) -> acc` | `name`, `by` | 1, or 1 per group |
| `sweep` | `name="value"`, `retries=0`, `**lists` | `(params…) -> Any` | `name` + one per param | the cross product |
| `select` | `columns=[…]` **(required)** | no tool (`identity`) | — | same |
| `drop` | `columns=[…]` **(required)** | no tool (`identity`) | — | same |
| `widen` | `columns=[…]` **(required)**, `retries=0` | no tool (`identity`) | one column per field | same |
| `slice` | `stop=`, `start=0`, or `at=[…]` | no tool (`identity`) | — | at most n |
| `rename` | `columns={old: new}` **(required)** | no tool (`identity`) | — | same |
| `sort` | `by=` **(required)**, `ascending=True` | no tool (`identity`) | — | same |
| `distinct` | `columns=[…]` (default: the whole row) | no tool (`identity`) | — | at most n |
| `retry` | `times=` | *(shape-preserving)* | — | — |
| `timeout` | `seconds=` | *(shape-preserving)* | — | — |

Notes: `axis="columns"` raises `NotImplementedError` — column verbs need a
ledger indexed by column, which is designed but unbuilt. `sweep` reserves
`name`, `retries` and `over`, so a parameter of yours cannot use those names.
`expand` treats a returned `str`, `bytes` or `dict` as one item rather than
unpacking it.

### Builtin tools

Nameable with `op(...)` without registering anything. They resolve a row's
payload by convention — an explicit `column=`, else `value`, else the only
column — so they work on any grid:

| id | | shape |
|---|---|---|
| `identity` | returns what the previous step produced | mapper |
| `gather` | collects every payload into one list | reducer |
| `count` | how many rows reached this step | reducer |
| `total` | sum of the payloads | reducer |
| `first` / `last` | first / last payload in row order | reducer |

When the payload column is not `value`, say which with `column=`:

```python
wf["gathered"] = op("gather", column="fahrenheit")[mod.collapse()](wf["with_f"])
# value
# 0  [64.4, 87.8, 84.2, 48.2]

wf["sum"] = op("total", column="fahrenheit")[mod.collapse()](wf["with_f"])
# value
# 0  284.6
```

Your tools may not shadow these names — `@tool` refuses at import, because the
verbs resolve `identity` and `gather` *by name*.

---

## 5. How a column reaches a parameter

This is the part that decides whether a step works, so it is worth stating
separately from the syntax.

> **The tool's parameter names must match the input's column names.**

The requirements a declaration has to meet for this to work at all — no
positional-only parameters, no `*args`, and the reserved names — are specified in
[writing-tools.md §2](writing-tools.md#2-the-declaration-contract).

`map` binds each row's columns to the tool's parameters by name. Hence:

| rule | |
|---|---|
| columns bind **by name** | anything the tool does not declare is not passed |
| `**kwargs` gets the whole row | for the cases that want it |
| bound literals fill the rest | `score.bind(weight=2)` |
| a **column wins** a collision | the unit is the row, and the unit wins |
| a non-dict input is passed positionally | an unorchestrated step over a bare value |

Which is why `name=` matters more than it looks — **it is the wiring between two
steps.** In §3, `map(name="fahrenheit")` is the only reason `is_hot(fahrenheit)`
and `warmest(acc, fahrenheit)` can bind. Leave it off and the column is `value`,
so the next tool must say `value`:

```python
wf["f"] = to_fahrenheit[mod.map()](wf["readings"])    # writes `value`
wf["hot"] = is_hot[mod.filter()](wf["f"])
# "is_hot() needs 'fahrenheit', which <f> does not have (it has celsius, value)"
```

So `name=` is not decoration and it is not a label for humans — it is the only
thing that makes a chain connect. Two ways to satisfy it, and both are fine:
name the column after the parameter the next tool declares, or name the
parameter after the column the last step wrote.

### Why the default is `value`

It looks arbitrary and is not. The six builtins resolve *which cell is the
payload* by convention — an explicit `column=`, else a column literally named
`value`, else the only column. That convention is what lets `gather`, `total`,
`count`, `first` and `last` work on **any** grid without being told its shape:

```python
wf["sum"] = op("total")[mod.collapse()](wf["f"])       # finds `value`, works
```

So `value` is a protocol, not a placeholder. It also explains why a smarter
default is not free: making a `map` name its column after the step (or the tool)
would mean no grid ever has a `value` column, and every bare builtin would need
an explicit `column=`. Tried it — it breaks the chaining idiom and makes the
stored `Operation` depend on which slot it was assigned to, so
`score[mod.map()]` would no longer equal what the workflow holds. The redundancy
you may feel is better fixed by not naming the step and the column the same word
(§2a).

`bind` fixes arguments that do not come from the grid:

```python
wf["scaled"] = to_fahrenheit.bind(weight=2)[mod.map()](wf["readings"])
```

Literals are applied innermost — inside every modifier — so a `retry` re-runs
the same call and a `map` passes them to every row.

---

## 6. Execution modifiers, and stack order

Execution modifiers preserve the signature, so they never change the shape:

```python
to_fahrenheit[mod.map(), mod.retry(times=2)](wf["readings"])
# <Operation map(over='readings') ∘ retry(times=2) ∘ to_fahrenheit>
```

`map(retry(tool))` — the retry is **inside** the map, so it retries per row,
which is almost always what you want. The list reads outermost-first; the last
layer listed sits closest to the tool. Order matters and is not commutative:
`[map, retry] != [retry, map]`.

Two orders exist and both are named, so nothing has to be reversed by hand:

```python
o.layers      # (map(over='readings'), retry(times=2))   written  — for display
o.modifiers   # (retry(times=2), map(over='readings'))   stored   — innermost first
o.shape_verb  # map(over='readings')                     the one that sets the shape
```

Anything showing a user their own stack reads `layers`. `mod.retry(times=2)` is
shorthand for the `retries=` parameter the verbs also take directly.

`timeout` currently records intent only; real enforcement needs the async
engine.

---

## 7. What is checked, and when

`check()` never raises. An invalid step still exists, carrying its problems —
a reactive editor has to be able to *show* a bad step mid-keystroke. `run()` is
what refuses.

```python
wf.step("oops").problems
wf.validate()            # every step's problems, keyed by step id
```

Caught at declaration:

| check | message |
|---|---|
| unknown tool or modifier kind | `unknown tool 'scoer'` |
| `over` dangles, self-references, is circular, or names an invalid step | `map over 'raw', which is not an earlier step` |
| two shape verbs in one step | `2 shape verbs in one step (map, select); at most one is allowed…` |
| `source` / `select` / `drop` given a real tool | `select applies no tool; use map to compute` |
| `select` / `drop` naming a column the input lacks | `select names 'temp', which the input does not have (it has city, celsius)` |
| a bound literal the signature rejects | `score() takes no argument 'wieght'; it accepts weight` |
| **a required value the upstream cannot supply** | `is_hot() needs 'fahrenheit', which 'readings' does not have (it has celsius, city)` |

That last one is the payoff of binding by name, and it has a timing
qualification worth knowing:

> The column check runs only against an upstream that has **run**.

A staged output holds placeholder rows rather than real columns, so checking one
would invent errors. So it depends on how you build:

```python
# incremental — run as you go: the mismatch is caught at declaration
wf.run("with_f")
wf["bad"] = wrong[mod.filter()](wf["with_f"])
wf.step("bad").problems
# ("wrong() needs 'value', which 'with_f' does not have (it has celsius, city, fahrenheit)",)

# declare everything first, then run: nothing to check against yet
wf["bad"] = wrong[mod.filter()](wf["with_f"])    # problems == ()
wf.run_all()
wf.step("bad").status                                    # 'failed'
```

And it lands in the ledger rather than raising:

```
      status                                                               error   kept
0  failed  TypeError: wrong() missing 1 required positional argument: 'value'  False
1  failed  TypeError: wrong() missing 1 required positional argument: 'value'  False
```

Note the interaction that makes this worth watching on `filter` specifically: a
row whose predicate **failed** is not kept, so a wholly broken filter yields an
empty grid rather than an error. `status` and the ledger are where you look;
`len(out.failed)` is the quick check.

**Not checked at all:** modifier parameter names. Unlike a bound literal, a typo
in a verb's own parameter passes declaration and surfaces at run time:

```python
wf["t"] = to_fahrenheit[mod.map(nmae="f")](wf["readings"])
wf.step("t").problems                 # ()
wf.run("t")
# TypeError: map_() got an unexpected keyword argument 'nmae'
```

Column *types* **are** checked, when the tool is annotated and the upstream has
run — see §10.

---

## 8. Staged claims, and what they will not tell you

A staged step promises only what its verb can guarantee:

```python
wf.step("with_f").describe()   # 'map to_fahrenheit · 4 cells'
wf.step("hot").describe()          # 'filter is_hot · at most 4 cells'
wf.step("overall").describe()      # 'collapse warmest · 1 cell'
wf.step("expanded").describe()     # 'expand splitter · unknown count from 4 rows'
```

`describe()` answers two different questions and they must not be blurred: a
staged step reports what staging can *promise*; a step that has run reports what
it actually *holds*. Only the first is a prediction.

Two rough edges here, so they are not mistaken for facts about your workflow:

- `collapse(by=…)` stages as `1 cell` regardless of `by`, because the row rule
  is per-verb and cannot see how many groups the data has. After running it
  reports the real count (`2 cells` for the two coasts above).
- `sweep` stages as `one cell per upstream row`, which is simply wrong wording
  for a verb with no upstream — its count is knowable from its own parameter
  lists. After running it is correct.

---

## 9. Checklist

Before you run a new step:

- [ ] one shape verb, and it is the one whose iteration you want
- [ ] the input is a step that exists — pass `wf["id"]`, not a string, so a typo
      is a `KeyError` and a borrowed reference is refused (§11)
- [ ] the tool's required parameters are column names the input actually has
- [ ] the tool is fully annotated, so the dtype check can run (§10)
- [ ] `name=` set, if a downstream tool has to bind to what this step writes
- [ ] `problems` is empty — check it, do not wait for the run
- [ ] after running, `status == 'completed'`, not just "the grid looks right"

---

## 10. Typed steps

A step's boundary is its tool's annotations: what values go in, what value comes
out. Nothing else in the model records that, so annotating is how you and the
machine come to agree on it.

### Turning it on

Off by default, so tools written before the rule keep working. Turn it on once,
before declaring anything:

```python
from simple_steps_core import grid

grid.STRICT_TYPES = True
```

or per tool, `@tool(strict=True)`. Either way an incomplete declaration is
refused where it is written:

```python
@tool
def sloppy(x):
    return x
# TypeError: tool 'sloppy' is not fully typed: parameter 'x' has no type
#            annotation; it has no return annotation. A step's boundary is its
#            annotations — they are what `check` compares against the upstream's
#            dtypes and what a palette shows a user. Annotate it, or declare it
#            with strict=False.
```

`**kwargs` is exempt, because a whole-row tool has no per-column parameter to
type — the return still needs one.

### What the annotations then do

**1. A dtype mismatch becomes a declaration-time problem.** Previously
`check` could only ask whether a column *existed*:

```python
@tool
def needs_text(celsius: str) -> str: ...

wf["bad"] = needs_text[mod.map()](wf["readings"])
wf.step("bad").problems[0]
# "needs_text() declares celsius: str, but 'readings' has celsius as float64"
```

Same timing rule as the missing-column check (§7): it runs against an upstream
that has **run**, because a staged Output holds placeholder rows, not dtypes.

Because this reads real dtypes, the session export records them beside the data:
JSON carries no type information, so `read_json` re-infers and a float column of
whole numbers would come back `int64` — which could change a step's verdict after
a reload. Dtypes now survive the round trip.

**2. A bound literal is checked immediately** — no data needed, since the value
is in hand:

```python
wf["bad"] = scaled.bind(factor="three")[mod.map()](wf["raw"])
# "scaled() declares factor: int, but it is bound to 'three' (str)"
```

**3. The palette publishes the boundary.** `catalog()` carries a `type` per
parameter plus `returns` and `typed`, so a client can show what a step consumes
and produces rather than only naming its parameters:

```python
catalog()["to_fahrenheit"]
# {'tool_id': 'to_fahrenheit',
#  'description': 'Convert one Celsius reading to Fahrenheit.',
#  'origin': 'declared',
#  'params': [{'name': 'celsius', 'required': True, 'default': None,
#              'type': 'float'}],
#  'returns': 'float',
#  'typed': True,
#  'takes_whole_row': False}
```

### What is deliberately *not* refused

Type checking here reports only **certain** mismatches. An undecidable
annotation is not an error, because a false positive would refuse a step that
runs. Specifically:

| case | verdict |
|---|---|
| `int` column into `float` parameter | fine — widening, not a mismatch |
| `str`, `list`, `dict` into a matching object column | fine, decided by the first non-null value |
| `object`, `Any`, a union, a protocol | undecidable, so not checked |
| an all-null column | undecidable |
| a `collapse` accumulator | never checked — the verb supplies it, not the grid |

So the guarantee is one-directional: a reported mismatch is real, but silence is
not proof that every value fits.

### The tension worth knowing about

**Mandatory return annotations and verb inference pull against each other.**
Inference reads `-> bool` as "this is a `filter`" (§2e). Once every tool is
annotated, a perfectly ordinary `map` whose result happens to be a boolean —
`is_valid(n) -> bool`, written to a column — is indistinguishable from a
predicate:

```python
wf["flag"] = is_valid(wf["raw"])     # inferred filter; you wanted a map column
wf["flag"] = is_valid[mod.map(name="valid")](wf["raw"])   # says what you mean
```

The two goals are compatible, but only in one direction: **the more you type
your tools, the less you should lean on inference.** Which is the same
conclusion §2e reaches from the other side.

---

## 11. References belong to one workflow

A step is **named by its id**. That is what makes a step definition
serializable, and it has a consequence worth being explicit about: an id is
resolved against *whatever workflow the step lives in*.

So if you hold more than one workflow, the id alone cannot tell them apart. With
`wf1["raw"]` holding `1, 2, 3` and `wf2["raw"]` holding `100, 200`, writing

```python
wf2["x"] = double[mod.map()](wf1["raw"])     # note: wf1
```

would have silently run against **wf2's** `raw`. Not an error — the id exists
here, so everything downstream looked consistent. Just the wrong numbers.

### What the guard does

The fix is not to add a mechanism — it is to **stop throwing information away**.
`wf["raw"]` already returns a `StepRef` that knows its workflow:

```python
wf1["raw"].workflow is wf1        # True
```

That ref used to be flattened to `"raw"` the moment it was stored, so the
workflow was lost before anything could check it. Now the ref is simply **kept**,
and flattened only at the JSON boundary:

```python
double[mod.map(over=wf1["raw"])].modifiers[0].params
# {'over': <raw>}                          the ref, which knows wf1

double[mod.map(over=wf1["raw"])].to_dict()["modifiers"][0]["params"]
# {'over': 'raw'}                          flat, where JSON begins
```

This costs nothing at read time because every reader already went through
`str(over)`, and `StepRef.__str__` is its id. So the check is one comparison:

```python
wf2["x"] = double[mod.map()](wf1["raw"])
wf2.step("x").problems[0]
# "map over 'raw' reads a different Workflow. A reference is stored as a step
#  id, so this would resolve to *this* workflow's 'raw' instead of the one you
#  named. Read the step from this workflow, or pass the id as a plain string to
#  say you mean whatever 'raw' is here."
```

It is a **problem**, not an exception — consistent with everything else in §7,
and `run()` refuses an invalid step, so it cannot execute. It is also diagnosed
*before* a dangling reference, because borrowing is the cause and "no such step"
is only the symptom.

Naming a step two ways stays the same step, so nothing else moves — `Modifier`
compares its params flattened:

```python
score[mod.map(over=wf["raw"])] == score[mod.map(over="raw")]       # True
score[mod.map(over=wf["raw"])].to_dict() == score[mod.map(over="raw")].to_dict()
```

Both export modes are byte-for-byte unchanged, because `to_dict()` is exactly
where the flattening happens.

### The escape hatch, and when you want it

A **plain string** ref has no provenance, so it is never flagged — it means
*whatever `"raw"` is in this workflow*. That is the honest way to write an
operation meant for more than one:

```python
template = double[mod.map(over="raw")]
wf1["x"] = template        # fine
wf2["x"] = template        # fine — each resolves locally
```

The corollary: an Operation built from a **ref** is pinned to that workflow, so
it is not a reusable template. Use a string when reuse is the point.

### Export, then import as a second workflow

The common way to end up with two workflows. Reloading rebuilds every reference
from a string, so an imported workflow carries no stale provenance and is never
self-flagged:

```python
wf1 = grid.Workflow.from_json(wf.to_json(), TOOLS)
wf1.validate()          # {'raw': (), 'd': ()}
```

Two things to know about that pair:

**A light export carries no payloads,** so a reloaded source step needs its data
again — and can be given *different* data, which is usually the point:

```python
wf1.run_all()
# ValueError: source step 'raw' has no data. Assign it: wf['raw'] = <...>

wf1["raw"] = pd.DataFrame({"n": [10, 20]})
wf1.run_all()           # wf1 -> [20, 40];  wf is untouched -> [2, 4, 6]
```

`to_session_json()` carries the payloads, so a full import runs immediately. Two
imports of one export are fully independent.

**Extending the import is where the old variable bites.** `wf` is still in scope,
and `wf["d"]` is the easy slip:

```python
wf1["e"] = double[mod.map()](wf1["d"])    # ✓ its own reference
wf1["f"] = double[mod.map()](wf["d"])     # ✗ refused — wf, not wf1
```

Before the guard, the second line ran quietly against `wf1["d"]`.

### The one thing still not caught

Provenance only exists where a `StepRef` does. A **string** ref is unchecked by
design, so `over="raw"` in the wrong workflow still resolves locally without
complaint — that is the same property that makes it a reusable template, so it
cannot be both. If you want the guard, pass `wf["raw"]` rather than `"raw"`,
which is the advice §9's checklist already gives, now with a second reason.

---

## 12. Raw values: what becomes a row, what becomes a column

Two different questions, and they are easy to run together. **Returning** a raw
value from a tool is governed by the verb. **Assigning** a raw value as a source
step is governed by `rows()`.

### 12.1 What a tool returns

A tool returns **one value per unit**, and the verb decides what happens to it.
`map` puts it in a cell, whatever it is:

| returned | cell holds | dtype |
|---|---|---|
| `int` / `float` / `bool` | the value | `int64` / `float64` / `bool` |
| `str` | the value | `str` |
| `list` / `tuple` / `dict` | **the whole collection, in one cell** | `object` |
| `DataFrame` / `Series` | the frame itself, in one cell | `object` |
| `None` | `None` | `object` |

So `map` never unpacks. A tool returning `[1, 2, 3]` gives you one cell holding
that list — which is usually what you want for a plot, a table, or a media
handle. To turn it into rows you ask for `expand`.

**`expand` is the only verb that unpacks**, and it is deliberately narrow about
what counts as "many":

| returned | rows produced |
|---|---|
| `list`, `tuple`, `set`, `range`, any other iterable | one row per element |
| `str` | **one row** — a string is not a collection |
| `dict` | **one row** — the dict is one item, not a set of entries |
| a scalar | one row |
| `[]` | **zero rows**, columns kept |
| `DataFrame` | **refused** per unit — iterating one yields its *column names* |

`str` and `dict` are the two that surprise people, and both are deliberate: a
string would fan out into characters, and a dict would silently lose the
distinction between "one record" and "several values". To turn a dict into
columns, that is `widen` (§12.5).

A returned `DataFrame` is refused rather than iterated, because iterating one
yields its column names. Assign it as a source step if it is meant to *be* the
grid, or `widen` it if it is one record.

`collapse` is the mirror: it takes `(accumulator, row)` and returns the
accumulator, so whatever it returns ends up as a single cell — a list, a frame,
a number, all the same to it.

### 12.2 What a raw value becomes as a source

`rows()` coerces whatever you assign. The payload column is always `value`;
the differences are in the **index**.

| assigned | columns | index | rows |
|---|---|---|---|
| `42`, `None`, any scalar | `value` | `[0]` | 1 |
| `[1, 2, 3]`, tuple, set, `range` | `value` | `0…n-1` | one per element |
| `{"a": 1, "b": 2}` | `value` | **`['a', 'b']`** — the keys | one per entry |
| `pd.Series([7, 8])` | `value` | the Series' index | one per element |
| `pd.DataFrame(...)` | **its own columns** | its own index | as-is |
| `"hi"` | — | — | **`TypeError`** |

Three things worth knowing:

- **A dict keeps its keys as the index.** This is how a named set of tables stays
  named: `wf["tables"] = {"q1": df1, "q2": df2}` gives you two rows indexed `q1`
  and `q2`, each cell a frame.
- **A string is refused**, rather than fanning out into characters:
  `Cannot fan out over the string 'hi': a string is not a collection.` Wrap it —
  `["hi"]` — if you meant one row.
- **A Series' own name is discarded.** `pd.Series([7, 8], name="temp")` becomes a
  column called `value`, not `temp`. Pass a one-column DataFrame if you want the
  name kept.

### 12.3 Index and columns, by verb

The full table. "Carried" means the input's columns pass through untouched.

| verb | columns out | index out |
|---|---|---|
| `source` | the value's own | the value's own |
| `map` | carried **+** payload | **input index preserved** |
| `filter` | carried, none added | input index, **subset** |
| `group` | carried **+** the key column | input index preserved |
| `select` | exactly the ones named, in that order | input index preserved |
| `drop` | carried minus the ones named | input index preserved |
| `widen` | carried **+** one per declared field | input index preserved |
| `slice` | carried, none added | input index, **subset** |
| `rename` | carried, renamed in place | input index preserved |
| `sort` | carried, none added | input index, **reordered with its row** |
| `distinct` | carried, none added | input index, **first of each group** |
| `expand` | carried **+** payload | **reset** to `0…n-1` |
| `collapse` | **only** `[by] + [payload]` — carried columns are dropped | `0…n-1`, one per group |
| `sweep` | one per swept parameter **+** payload | `0…n-1` |

Two of these are the ones to remember:

- **`collapse` drops the input's columns.** It reduces many rows to one, so there
  is no single value of `city` to carry. If you need a column to survive a
  collapse, group by it: `collapse(by="city")` keeps it.
- **`expand` cannot preserve the index**, because it produces more rows than it
  consumed. Which input row produced each output row is recorded in the ledger's
  `unit` column, so the lineage is not lost — it moves to the ledger.

### 12.4 Zero rows is a result, not an absence

A verb that legitimately produces nothing — every row filtered out, every unit
expanding to `[]` — still produces a **typed, named, empty grid**:

```python
wf["gone"] = nothing[mod.expand()](wf["raw"])     # every unit returns []
wf.run("gone")

wf.step("gone").status                  # 'completed'  — it ran
len(wf.step("gone").output.data)        # 0
list(wf.step("gone").output.data.columns)   # ['n', 'city', 'value']
```

The columns and their dtypes survive, so a downstream step still validates and
runs. That matters because "this grid is empty" and "this grid has no columns"
are different problems, and only the first is true here.

### 12.5 A list of records into columns

The common shape: something hands you `[{"city": "SF", "temp": 18}, …]` and you
want columns `city` and `temp`, not one column of dicts. Two paths, and which one
you want depends on *where the records come from*.

**If you have the records in hand**, normalize before they enter the grid. The
grid has no opinion to apply yet, and `pandas` already does this:

```python
wf["readings"] = pd.DataFrame(RECORDS)       # -> columns: city, temp
```

Note that assigning the list itself does **not** do this — `rows()` treats a list
of dicts as *values*, giving one `value` column of dicts. That is the opposite of
`pd.DataFrame(records)`, and it is deliberate: every non-frame becomes a `value`
column, so the rule stays one rule. Call `pd.DataFrame(...)` when you mean records.

**If a tool produces them mid-pipeline**, you cannot reach outside the grid, and
this is what `widen` is for. Two steps, because two shape changes:

```python
wf["recs"] = fetch[mod.expand()](wf["seed"])                    # longer: one row per record
wf["wide"] = mod.widen(columns=["city", "temp"], over=wf["recs"])   # wider: fields to columns
```

`expand` then `widen` is the full unnesting idiom, and it stays two steps on
purpose — each shape change keeps its own cell addresses and its own ledger, so a
record that fails to parse is inspectable at the step that failed on it.

A tool returning a whole `DataFrame` is not a third path: `map` puts it in one
cell, and `expand` refuses it. A step's grid comes from its verb, never from what
a tool returned — `source` is the only verb that adopts a frame's columns
wholesale.
