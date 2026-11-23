# A canonical form: proposed

> **Draft, 2026-11-23, for the owner**, who asked: "can you propose a good
> canonical form?" The canonical layer of [conditions.md](conditions.md):
> what is parsed, checked, saved and run, and what a user sees when they
> open an expression. The surface (presets, methods on picks, `auto`) maps
> into it. Nothing here is built; every name is a placeholder until the
> primitives are named ([primitives.md](primitives.md) §6).

## 1. What it must be

| Requirement | From | How this form meets it |
|---|---|---|
| **one shape for every expression** | owner: "everything abides by `tool[modifiers](data)`" | it is that shape, always |
| **explicit beyond a reasonable doubt** | H1, H2 | every component is written; nothing is left for a reader to work out |
| **readable** | users open their expressions | the class of each modifier is in its name; one modifier, one job |
| **valid Python** | the app's `formula(text)` means what Python means (012 C40) | it is a Python expression |
| **closed** | grammar.md, the goal | every sentence runs, or is refused naming its condition (R1–R26) |

## 2. The shape

```
tool[ input modifiers , call modifier , execution modifiers , output modifiers ]( bindings )
```

- **Brackets: how. Parentheses: what.** (model.md §3, "brackets decorate,
  parens apply".)
- **Inside the brackets, the classes come in this order**: input, call,
  execution, output. The order a step works in (blocks.md §0, the ordered
  components). Core keeps them in this order whatever order they are typed
  in (fixes O1).
- **The class is in the modifier's name**: `mod.input.…`, `mod.call.…`,
  `mod.exec.…`, `mod.output.…`. The UI's widgets are these four groups.
- **Bindings are always by keyword**: `parameter=source`. A source is an
  address (a pick), a literal, or a resource. Never by position, never by a
  column's name or type left to be worked out (R2–R6 become one rule: what is
  written is what is bound).
- **Exactly one call modifier.** Any number of the others, each class
  optional except where a condition requires it.

## 3. The words, by class

Placeholders, to show the shape. One modifier, one job.

| Class | Modifier | Does |
|---|---|---|
| **input** | `mod.input.nest(param, over=…, form="list")` | many cells of that argument into one: `over="call"` (the call's own piece: a row gives one cell, a group its cells, one call everything), `over="all"`, `over=by(wf["p"]["k"])` (this row's group), `over=window(n)`; `form` list, dict, table, array |
| | `mod.input.convert(param, to=float)` | each cell's value converted, before nesting (the one change of value, written: X3) |
| | `mod.input.match(param, on=…)` | data from another step, matched to the call's rows (N3: to come) |
| **call** | `mod.call.once()` | one call |
| | `mod.call.each_row()` | one call per row |
| | `mod.call.each_group(by=wf["p"]["k"])` | one call per group of that key |
| | `mod.call.each_combination()` | one call per combination of settings (a sweep) |
| **execution** | `mod.exec.retry(times=3)` · `mod.exec.timeout(seconds=10)` · `mod.exec.on_failure(default=None)` · `mod.exec.stop_after(failures=5)` · `mod.exec.progress()` | each wraps every call; **written left to right, outside in**: `retry(3), timeout(10)` is three attempts, each with ten seconds |
| **output** | `mod.output.land("own_row" \| "new_row" \| "each_row_of_group")` | where each output goes |
| | `mod.output.keep_rows()` | the tool's `bool` keeps or drops its row |
| | `mod.output.unnest(into="rows" \| "columns")` | a returned list into rows, or a record into columns |
| | `mod.output.keep_input()` | the input's columns kept beside the output |
| | `mod.output.name("temp_f")` | the output columns' names |
| | `mod.output.expect(rows=…)` | a check on the output |

**Taking rows and columns is the pick's job** (the address's row and column
parts), so it has no input modifier.

## 4. Every kind of expression

| Whose function | Canonical form |
|---|---|
| **none**: data, the empty step | the value itself. Nothing is applied, so there is no `tool[…](…)` (grammar.md §6.1) |
| **core's**: a pick, a drop, a sort, a join, … | `core.take[mod.call.once()](table=wf["p"][["x", "y"]])`, `core.join[mod.call.once()](left=wf["a"], right=wf["b"], on="id")`: core's tool, its settings as bindings |
| **the user's** | `tool[…](…)`, as in §2 |

## 5. Examples: the surface, and what it opens into

**`map`**

```python
to_f[mod.map()](wf["p"], offset=1.0)                                     # surface
to_f[mod.call.each_row(), mod.output.land("own_row")](                    # canonical
    temp_c=wf["p"]["temp_c"], offset=1.0)
```

**`collapse` by a key**

```python
sumup[mod.collapse(by="ward")](wf["p"], xs=wf["p"]["x"])
sumup[mod.input.nest("xs", over="call"),
      mod.call.each_group(by=wf["p"]["ward"]),
      mod.output.land("new_row")](xs=wf["p"]["x"])
```

**Each row against the whole column** (two steps today)

```python
z[mod.map()](wf["p"]["x"], ys=wf["p"]["y"].tolist())
z[mod.input.nest("ys", over="all"),
  mod.call.each_row(),
  mod.output.land("own_row")](x=wf["p"]["x"], ys=wf["p"]["y"])
```

**A group's value beside each of its rows** (a collapse and a join today)

```python
mean[mod.input.nest("xs", over=by(wf["p"]["ward"])),
     mod.call.each_row(),
     mod.output.land("own_row")](xs=wf["p"]["x"])
```

**`filter` with a tool**

```python
hot[mod.filter()](wf["p"])
hot[mod.call.each_row(), mod.output.keep_rows()](temp=wf["p"]["temp"])
```

**`expand`**

```python
split[mod.expand()](wf["p"]["name"])
split[mod.call.each_row(), mod.output.unnest(into="rows")](name=wf["p"]["name"])
```

**Retries, in a fixed place** (O1)

```python
flaky[mod.retry(times=2), mod.map()](wf["p"])                  # retries nothing today
flaky[mod.call.each_row(), mod.exec.retry(times=2),
      mod.output.land("own_row")](x=wf["p"]["x"])               # each call retried
```

**A `drop`**

```python
mod.drop(columns=["k"])(wf["p"])
core.take[mod.call.once()](table=wf["p"][["x", "y"]])
```

## 6. What it fixes

| Finding | How |
|---|---|
| A4, H3's case b, G2 | bindings are always written by keyword: nothing chosen from a step's columns by name or type, so nothing chosen wrongly |
| O1 | the classes have a fixed order; execution always wraps each call |
| A6, A7, the two levels | a list only arrives as a list by `mod.input.nest`, written; a cell is always delivered as it is |
| `collapse` crossing classes | it opens into one modifier per class |
| the z-score and the group-beside-each-row in two steps | one step each |
| `group`, `table` name clashes | the class names (`input`, `call`, `exec`, `output`) and `land(...)` replace the verbs in the canonical form; verbs stay as surface presets |

## 7. To settle with the owner

1. **The shape and the order inside the brackets**: input, call, execution,
   output?
2. **Bindings always by keyword** in the canonical form (the surface keeps
   positions and names)?
3. **Defaults**: a parameter left at its default, written in the canonical
   form (`offset=0.0`) or left out? Written, a change to the tool's default
   wouldn't reach the step; left out, R6 keeps it unambiguous.
4. **`over="call"`**: nesting over the call's own piece, so `collapse` needs
   its key only once, in the call. Clear, or should the key be repeated?
5. **Execution order**, written left to right from the outside in?
6. **Core's tools as `core.<name>`**, and data as the value itself: the two
   exceptions to `tool[…](…)` being data and the empty step.
7. **Verbose**: the canonical form is longer than today's. That is the cost
   of being explicit; the surface keeps everyday writing short. Acceptable,
   given that users see it only when they open an expression?
