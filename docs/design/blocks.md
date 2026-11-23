# Blocks, and the moves that rearrange cells

> **Draft, 2026-11-22, for the owner**, to choose the next dev plan. **§0 is
> the idea everything else serves** (owner, 2026-11-23: "this is
> important"). §1 is the words; §2 the **block**, an object core doesn't have yet; §3 **what a
> parameter accepts**, run today
> ([grid-probes/blocks.py](grid-probes/blocks.py)), and where it disagrees
> with itself; §4 the **primitives** that rearrange cells, with every
> modifier and combine written in them; §5 the **kinds of iterable** a cell
> can hold, and what core opens; §6 the dev plan; §7 the questions.
> It builds on [grid.md](grid.md) (§8 the definitions, §10 every move) and
> doesn't replace it. Nothing here is built.

## 0. The idea: one expression, from sheet to sheet

*Owner, 2026-11-23: "how do we enable a spreadsheet-like experience, but
with one expression mapping from sheet to sheet, in a way that is very easy
to understand and can handle cells containing any type of Python data
structure?" And: "every function should operate from cell to cell"; "I
would like the modifiers to handle the preparation and leave the data
alone"; "collapse … just to list".*

**A step is one formula dragged over a sheet.** The tool sits in the middle
and only ever sees cells:

```
 sheet in ──pick──► block ──split into calls──► each call: one cell per argument ──► tool ──► output ──place──► sheet out
            (1)              (2)                 (3) prepared; values untouched                      (4)
```

**A call** is one run of the tool's function, one Python invocation with
one output. A step is the set of calls its split makes (run 2026-11-22, a
3-row input: `map` 3 calls, `collapse(by=…)` one per group, `table` 1,
`sweep` one per combination, `source` 1). A wrapper such as `retry` can make
several *attempts* at one call; it is still one call.

### The four questions

Every step answers four questions. Each has a default:

| Question | Choices | Default | Excel's version |
|---|---|---|---|
| **1. Which cells?** | a pick, `wf["p"][rows][columns]`: the block | the whole step | the range you point at |
| **2. How many calls?** | one per row · one per group (`by="k"`) · one in total | one per row | dragging a formula down |
| **3. What does each argument get?** | its **row's** cells, or a **fixed** pick, the same every call. When that is many cells: **packed** into one cell, as a list, a dict or a table | its row's cell | `B2` against `$B$2:$B$4`; and a function such as `SUM` taking a range |
| **4. Where does each call's output go?** | one cell · spread into rows · spread into columns · keep or drop its row | one cell | a value, or a spill |

Plus how each call runs: the wrappers, `retry`, `timeout`, `breaker`,
`try_except` (and progress and cancel, K23).

### The rules

1. **Every argument becomes exactly one cell per call.** A tool goes from
   cells to cells.
2. **Modifiers prepare; they never change a value**, except a conversion,
   written as an input modifier (owner, 2026-11-23). Splitting, fixing and
   packing only decide which cells reach a call and how many become one.
   A cell holding a list reaches the tool as that list.
3. **Packing is the only way many cells become one**, and it is always
   written: `to_list` (the default for a column), `to_dict` (a row's cells,
   by column name), `to_table` (a block). So "a block made into a list" and
   "a cell that holds a list" can't be confused: one is packed, in the
   expression; the other is a cell's value.
4. **A block's two directions do different jobs** (run 2026-11-22 on
   `wf["p"][["x", "y"]]`): **columns go to parameters**, by name, under every
   modifier; **rows are what the split decides**: one row per call,
   `f(x=1.0, y=10.0)` … under `map`; or the rows of a group packed into
   lists inside one call, `g(x=[1.0, 3.0], y=[10.0, 30.0])`, under
   `collapse(by="k")`.
5. **Any Python value works**, because values are never touched. The one
   check is whether a cell's type, or a packed cell's (`list[float]`), fits
   the parameter's type.
6. **The tool's signature sets the defaults, through `auto`.** It reads the
   parameter types and the modifiers and writes every choice into the
   expression, where it is shown before anything runs, never re-guessed
   after a run, and changed with one edit. Writing a choice yourself
   overrides it, and is never second-guessed.

### Today's verbs are preset answers

| Verb today | 2. Calls | 3. Each argument | 4. Output |
|---|---|---|---|
| `map` | per row | its row's cell | one cell |
| `filter` | per row | its row's cell | keep or drop its row |
| `group` | per row | its row's cell | one cell, beside the input's columns |
| `expand` | per row | its row's cell | spread into rows |
| `collapse(by="k")` | per group | the group's cells, **packed into a list** | one cell |
| `table` | one in total | everything, **packed into a table** | a table |
| `sweep` | one per combination of settings | its combination | one cell |

So `collapse` is two answers together: "one call per group" and "pack each
column to a list". Taken apart, packing is a preparation that leaves the
data alone, and the verbs become presets of four independent choices
(K32's direction, with the four questions as the primitives' names).

### The ordered components of a step

*Owner, 2026-11-23: "this is the general process for writing a good step";
"we are defining the ordered components needed to write any step"; "the
modifiers for each of these ordered components depend on each other.
Sometimes one modifier, say in calls, implies how we need to prepare the
data, and land the outputs."*

Every step that calls a tool is written from six components, in this order.
The four questions above are the same ideas; this is their order, with the
wrappers and the checks given their places:

```
pick ──► prepare each argument ──► calls ──► run each call ──► land the outputs ──► check
 (1)            (2)                  (3)          (4)                 (5)             (6)
```

| # | Component | Answers | Modifiers in it | How many |
|---|---|---|---|---|
| 1 | **pick** | which cells | the pick, `wf[…]`; `select`, `slice` (which repeat the pick's own row and column parts) | one per argument |
| 2 | **prepare each argument** | what each call's argument holds | packing (to a list, per group, per window); converting (`cast`) | per argument; each cell converted first, then packed |
| 3 | **calls** | how many calls | `map`, `collapse`, `table`, `sweep`, `source` | **exactly one** (core already refuses two: "2 shape verbs in one step") |
| 4 | **run each call** | how one call runs | `retry`, `timeout`, `breaker`, `try_except`; progress and cancel to come (K23) | several; **their written order is meaningful** |
| 5 | **land the outputs** | where each output goes, in what shape | one cell (the default); beside the input's columns (`group`); keep or drop its row (`filter`); into rows (`expand`); into columns (`widen`, a record); then the columns' names (`name`) | one way of landing, then names |
| 6 | **check** | is the output what was expected | `expect` | several |

**The components' order is fixed, not the order they are written in.**
Today it is the written order, and it changes what a step does without a
word (**O1**, run 2026-11-23,
[grid-probes/order.py](grid-probes/order.py)):

| Written | What happened |
|---|---|
| `flaky[mod.map(), mod.retry(times=2)]` | row 1 failed once, was retried, succeeded; all three rows done |
| `flaky[mod.retry(times=2), mod.map()]` | **the retry did nothing**: it wrapped the whole map, and a map records a failed row rather than raising, so there was nothing to retry. Row 1 failed |

Proposed: core keeps the modifiers in component order, so a `retry` is
always component 4 and runs on each call, whatever order it is written in.

**Within component 4 the written order is kept, because there it means
something**, and the UI shows it as nesting:

| Written | Means |
|---|---|
| `timeout` inside `retry` | each attempt has its own time limit |
| `retry` inside `timeout` | one time limit for all the attempts |
| `try_except` outside `retry` | retry first; if it still fails, the default |
| `try_except` inside `retry` | the default catches the first failure, so there is no retry |

**Rearranging without a tool** (`drop`, `rename`, `sort`, `distinct`,
`copy`, `pack`) is a step of its own: no calls. Its order matters (sort then
take three is not take three then sort), and it is the workflow's order of
steps.

### How the components depend on each other

A modifier in one component **implies defaults in the others, and limits
what they can be**. Component 3 drives the most:

| Calls (3) | Prepare (2): the input's arguments | Land (5): allowed | Land (5): default |
|---|---|---|---|
| `map`: one per row | its row's cell; any wider scope allowed (a window, a group, everything) | a cell, beside, keep or drop, into rows, into columns | a cell |
| `collapse(by=)`: one per group | **packed per group** (required: a row's cell has no single meaning in a group's call) | one row per group; *or on every row of the group (missing today)* | one row per group |
| `table`: one in total | **the whole block, as a table** | a table: its rows and columns | a table |
| `sweep`: one per combination of settings | its combination | one row per combination | one row per combination |
| `source`: one, no input | no input | a table | a table |

The others depend in the same way:

- **Prepare → calls.** If every argument is packed per group, the calls are
  one per group. If any argument is its row's cell, they are one per row.
  So a `collapse` can be read off its arguments, and a per-row argument
  under `collapse` is refused, naming the fix.
- **The tool's return type → land.** A `bool` can keep or drop (only when
  written: `auto` never picks `filter`); a list can go into rows; a record
  goes into columns. A tool that returns one value has nothing to spread.
- **Land → check.** What `expect` can state (rows, columns) depends on how
  the outputs landed.

**This is what the shorthands are:** a modifier in component 3 that fills
in components 2 and 5 with what it implies. `collapse(by="k")` is "one call
per group, every input argument packed per group, one row per group out".
Writing component 2 or 5 yourself overrides the default, within the limits
above.

### Scope: what one call reads of an argument

*Owner, 2026-11-23: "2–3–4 are intertwined components that I want to figure
out."* An argument's **scope** is the set of input rows whose cells go into
one call's value for that argument. It is about rows only: which column an
argument reads is fixed by its pick. For the call made for row 1 of

| # | k | y |
|---|---|---|
| 0 | a | 10 |
| 1 | b | 20 |
| 2 | a | 30 |
| 3 | b | 40 |

| Scope of `ys` | Rows it reads | `ys` receives |
|---|---|---|
| **row** | 1 | `20`, the cell as it is |
| **window**, the row and the one before | 0, 1 | `[10, 20]`, packed |
| **group**, `by="k"` | 1, 3 | `[20, 40]`, packed |
| **everything** | 0–3 | `[10, 20, 30, 40]`, packed |

- **One row in scope: the cell as it is. More than one: packed.** That is
  the only time packing happens.
- **The calls and the scopes must agree.** Under one call per row, any
  scope works: a wider one is read from that row's window, group, or
  everything. Under one call per group, every argument from the input is
  group-scoped (or everything); a row-scoped one is refused, naming the fix.
  Two different groups (`by="k"` and `by="j"`) with no row-scoped argument
  are refused.
- **An argument from outside the input's rows** (another step's pick) is
  everything, or one fixed cell. A literal is the same every call.
- *The word is open:* "scope" also means something in programming (and in
  core's code); "span" says the same.

### Written two ways: argument methods, and modifiers as shorthands

*Settled 2026-11-23 (owner): the full form is `tool[modifiers](data)`; a
method on a pick is **a shorthand, a soft link to an input modifier**, kept
because it reads well. See [expression-grammar/grammar.md](expression-grammar/grammar.md) §5, H7.*

*Owner, 2026-11-23: "methods that cast the data properly, like
`wf["step"]["col"].tolist()`, for the argument, to make it more explicit";
"I would want modifiers to be good shorthands"; "certainly the modifiers
handle the number of calls of the function. But we need to organize."*

**Layer 1, the argument: a pick and how its cells are prepared.** A pick
with no method gives **its row's cell**. A method **packs**, with the scope
as its arguments, in pandas' words:

| Method | Packs | Into |
|---|---|---|
| `.tolist()` | a column's cells | a list |
| `.to_dict()` | a row's cells | a dict, column name → value |
| `.to_frame()` | a block | a `DataFrame` |
| `.to_numpy()` | a column or a block | an array (the app's 015 C58: the user says so) |

```python
wf["p"]["y"]                     # its row's cell
wf["p"]["y"].tolist()            # everything, one list, the same every call
wf["p"]["y"].tolist(by="k")      # its group's cells
wf["p"]["y"].tolist(window=2)    # this row and the one before
```

A method is **written into the expression; it fetches nothing**: the pick
stays an address with its packing noted, saved, printed back as written,
resolved when the step runs. A pick already has one such member,
`wf["p"].header` (the column names, one per row); picks have no `tolist`
today (run 2026-11-23), and a column named `tolist` can't clash, since
columns are picked with brackets.

**Layer 2, the step: modifiers.** They decide **how many calls**, where
each call's output lands, and how each call runs. A modifier that decides
the calls is **a shorthand**: it also gives every argument read from the
input the matching preparation, unless the argument says otherwise.

```python
sumup[mod.collapse(by="k")](wf["p"]["x"])       # the shorthand
sumup(xs=wf["p"]["x"].tolist(by="k"))           # what it means: one call per group
```

**Every one of today's modifiers, by its job** (the 25 kinds in
`modifier_catalog()`, run 2026-11-22), and the ones that don't fit:

| Job | Modifiers | Shorthand for |
|---|---|---|
| **how many calls**, and the input's preparation | `map` (per row) · `collapse(by=)` (per group; `.tolist(by=)`) · `table` (one; `.to_frame()`) · `sweep` (one per combination of settings) · `source` (one, no input) | the scopes of the input's arguments |
| **where the output lands, and its shape** | `expand` (into rows) · `widen` (into columns) · `filter` (keeps or drops its row) · `group` (a cell beside the input's columns) · *a group's output on every row of the group: missing* | how each call's output is unpacked and placed |
| **rearranging, no tool** (§4's moves) | `select`, `drop`, `rename`, `name`, `copy`, `sort`, `slice`, `distinct`, `pack` | take, nest, unnest |
| **how each call runs** | `retry`, `timeout`, `breaker`, `try_except` (progress and cancel to come, K23) | — |
| **checks** | `expect` | — |
| **don't fit** | **`cast`**: it changes values, which no modifier should (rule 2): a tool, or an argument method that says so (`.astype(float)`) · **`auto`**: not a modifier at run; it writes the others · **`select(rows=)`, `slice`**: the same as a pick's row part · **`copy`**: the same as a pick declared as a step | to settle |

Several steps read together (`join`, `zip_`, `stack`) are question 1 for
more than one step: which cells, from where, matched how.

**`auto` writes Layer 1 too.** When a tool's type calls for a packing,
`auto` writes `.tolist()` (or `.to_dict()`, …) into the expression: the
same text a user would type, shown, removed by deleting it.

### What the user sees before running

`def z(x: float, ys: list[float])`, one call per row. `x` takes one value,
so it gets its row's cell. `ys` takes a list and `p`'s cells are floats, so
`auto` writes **`.tolist()`**: the whole column, as one list, the same
every call.

```
zs = z[mod.map()](x=wf["p"]["x"], ys=wf["p"]["y"].tolist())     one call per row · 3 calls

  x   ← its row's cell of p                float ✓
  ys  ← all of p["y"], packed to a list    list[float] ✓   (auto: z takes a list)
```

With `.tolist(by="k")`, each row gets its own group's list: **a group's
value beside each row in one step**, which takes a `collapse` then a `join`
today. The
same expression today takes two steps: `all = op("gather")[mod.collapse()]
(wf["p"][["x"]])`, then `z[mod.map()](wf["p"]["x"], ys=wf["all"][0]["x"])`
(run 2026-11-22: `[-2.0, -1.0, 3.0]`).

### Still to settle

- **A grammar that closes the system** (owner, 2026-11-23: "I am wondering
  if we need a grammar that closes this system to be very robust"): the
  components, their order and their dependencies written as one grammar
  and its rules, so every step is either a sentence of it or refused with
  the rule it breaks. Proposed as the next piece (§6, G0).
- **The packings**: `.tolist()`, `.to_dict()`, `.to_frame()`, `.to_numpy()`
  proposed; others?
- **The scope's word** ("scope" or "span") and its arguments (`by=`,
  `window=`).
- **The missing landing**: a group's output on every row of the group, as a
  modifier (the shorthand for `.tolist(by=)` with per-row calls).
- **The modifiers that don't fit** (`cast`, `auto`, `select(rows=)`,
  `slice`, `copy`): where each goes.

## 1. Pick, block, table

Keep **the address** and **the contents** apart:

| Word | Is | Lives in | Example |
|---|---|---|---|
| **pick** | an **address**: a step, at most one row part, at most one column part | an expression; saved | `wf["p"][1:3][["x", "y"]]` |
| **block** | **what a pick holds now**: a rectangle of cells, with their states and types | the kernel, at the moment it is asked; never saved | rows 1–2 of `p` × columns `x`, `y` |
| **table** | **where cells live**: everything one step holds, its **header**, **index columns** (`#`, `#<step>`) and grid; one per step, named by the step | a step's output; saved with the session | all of `p` |
| **cell**, **row**, **column** | a block of 1×1, 1×n, n×1 | — | `wf["p"][2]["x"]` |

**A pick gives a block, never a table; only a step makes a table** (owner,
2026-11-22). The two don't differ in structure. A block of the whole grid,
`wf["p"]`, has the table's rows and columns. They differ in role: a table
*has* its cells, a block *points at* some of them, like a range `B2:D5` on
a sheet.

| | Table | Block |
|---|---|---|
| owned by | its step: one table per step | no one: it refers to a table's cells |
| made by | declaring a step | resolving a pick |
| lifetime | the step's; saved | while it's looked at; never saved |
| before a run | a plan | a planned block: shape known, cells pending |
| header, index columns | its own | borrowed: the names of the columns it covers, its rows' numbers in the table |

**A pick is an address, and it stays live** (run 2026-11-23, for the
owner's "picks versus addresses … when is this needed, for tables that are
constantly dynamic, but sometimes it's just Excel sheets"). As in Excel,
`=SUM(A1:A3)` is an address and the values there now are its contents.
When the data changes, the address follows:

| Written | After a row is inserted on top of `p` |
|---|---|
| a pick by position, `wf["p"][1]["x"]` (Ben's row) | rewritten `wf["p"][2]["x"]`: it followed Ben, still `2.0`, as Excel shifts `A2` to `A3` |
| a pick by condition, `wf["p"][cols["x"] > 1.5]` | read again: it now includes the new row's `9.0`, like a filter |
| a tool over the step, `dbl[mod.map()](wf["p"])` | three rows become four: stale, then run again |

There is nothing to choose between "dynamic" and "a sheet": every pick is
an address. Into data that never changes, it behaves as a fixed sheet. Only
**freezing** (§2) gives contents that don't follow: the values copied, the
address dropped.

A block becomes a table by being declared as a step: `k["cp"] =
wf["f"]["x"]` makes that block step `cp`'s own table, with lineage back to
`f` (today's linked copy, 015 C56).

A pick is always a rectangle: every chosen row × every chosen column, not
necessarily next to each other. "Block" is the general word, and cell, row
and column are its special cases. (Today's code, `_shape_kind`, says
`block` only for n×m. It needs another name, say `rows × columns`, if the
owner agrees.)

**Does a tool ever receive a block?** *Open* (§7, question 2: the owner
would give one to a parameter typed `Block`). Otherwise a parameter *accepts* a block: core
checks it, and the UI shows it. At the call, core hands the tool the block's
values in the parameter's form (a value, a list, a dict, a `Series`, a
`DataFrame`). Tools stay plain Python. No `#` columns, states or row ids
reach a tool.

### Two levels: the block's structure, the cell's value

*Owner, 2026-11-22: "you can have a block making a list or a block where
each cell is a list … cells contain the unit of data that is useful to the
user; they are using the block to help organize it."*

| Level | Is | Who decides it |
|---|---|---|
| **the cell's value** | the unit of data: a number, a string, a list, an image. Core never wraps or unwraps it | the data |
| **the block's structure** | how the user has organized those units: one cell, a column of them, a row, rows × columns | the pick, and the verb |

A list can live at either level: **a block made into a list** (a column of
numbers handed over as `[5.0, 6.0]`) or **a cell whose value is a list**
(`[1, 2]` in one cell). Moving between the levels is a move of its own:
**nest** puts many cells into one cell's list; **unnest** spreads one
cell's list into many cells (§4).

**Run 2026-11-22**, parameter `y: list`:

| `y=` | The tool got | Level |
|---|---|---|
| `map`, a paired column whose cells are lists | `[1, 2]`, then `[3, 4, 5]` | the cell's value ✓ |
| `map`, a paired column of numbers | refused: "the verb decides what a column passes" | ✓ a number isn't a list |
| `collapse`, a group of number cells | `[5.0, 6.0]` | the block, as a list, by the verb ✓ |
| `collapse`, a group of list cells | `[[1, 2], [3, 4, 5]]` | the block as a list; each cell's list kept ✓ |
| `map`, a whole cell holding a list | `[7, 8]` | the cell's value ✓ |
| `map`, a whole cell holding a number | `[9.0]` | **the block wrapped into a list (A7)**: the parameter's type chose the level |

**How the two levels are kept apart is §0's rule 3**: packing is the
only way many cells become one, and it is always written, so the A7 row
above stops being a guess. (A first attempt, "cell or block, chosen by
`auto` from the types", stood here on 2026-11-22; §0 replaces it: every
argument is one cell per call, and a reduction is always a written packing.)

## 2. The block, as an object

**Proposed:** `k.block(pick)` gives the block a pick holds now. It is
read-only, and built from what core already has:

| Part | What | From today's code |
|---|---|---|
| `pick` | the address it came from | `StepRef` |
| `shape` | `cell`, `row`, `column`, `rows × columns`; its size | `_shape_kind` |
| `rows` | row numbers as `#` shows them (ids underneath, never shown) | `_apply_selection` (its docstring already says "the block a selection names") |
| `columns` | names, each with a **type** and its certainty (declared, stated, observed, unknown) | the plan's columns |
| `states` | a state per cell; whether the step is stale | `Output.states` |
| `values` | a page of values, on request (a block of 1M rows doesn't read them) | `k.view`'s paging |
| `rows_of` | **whose rows these are**: the step whose rows they are, through lineage. Two blocks pair row by row only when this matches | the alignment check behind "the rows of 'o' aren't the rows of 'd'" |
| `planned` | true before its step runs: shape and types from the plan, every cell `pending` | `Step.plan` |

What it buys:

- **The UI asks one question per parameter.** `k.accepts(operation,
  parameter)` says what that parameter takes **under the tool's modifiers**,
  before the user picks anything (§3's table, as data). Once the user picks
  something, `k.fits(block_or_literal, operation, parameter)` says how it
  would be delivered, or why not.
- **One check instead of four.** Literals, paired cells, whole picks and
  `table` are checked by different code today, and they disagree (§3).
  Through the block, all of them ask one rule: does this block (or literal),
  under this verb, fit this parameter?

### Freezing a block

*Owner, 2026-11-22: "freezing makes more sense", with good saving.* This
settles the app's 015 C56.

**Proposed:** `k.freeze(name, pick)` declares a **data step** holding the
block's values as they are now. A data step's values are its expression, so
the copy can be typed into, and it is **cut loose**: no lineage and no link,
and a change upstream doesn't reach it. (Today's linked copy stays as it is:
a pick declared as a step, `k["cp"] = wf["f"]["x"]`.)

| A cell of the block that is | Freezing |
|---|---|
| `known` | its value, exactly, with its type |
| **absent** (a `stack` or `join` gap) | absent, not `None` (needs F1) |
| `pending` (its step hasn't run) | absent: it holds no value yet (run: stored as `None`) |
| `failed` or `blocked` | absent: a failed cell holds no value (run: `<NA>`; its error is kept beside the cell, not in it) |
| in a `stale` step | its value, as it is |

**Whatever is there** (owner, 2026-11-22): nothing is refused. A cell with
no value is copied as a cell with no value, so a failure never becomes data
that looks real.

**Saving already holds it** (run 2026-11-22,
[grid-probes/freezing.py](grid-probes/freezing.py)): a data step of floats
with gaps, strings, lists, dicts, numpy arrays (dtype kept) and nullable
integers comes back from `k.save`/`Kernel.load` identical, with the same cell
states, with or without outputs.

**Two things to fix first**, found by the same run. Each also matters for
any data the user pastes in:

| # | Found | Should be |
|---|---|---|
| **F1** | Written into a data step, an **absent** cell becomes a **known `None`**: the gap is lost silently | absent stays absent |
| **F2** | A nullable float column whose values are whole numbers, `Float64 [1.0, <NA>]`, is stored as **`Int64`**: `1.0` comes back as `1`. `[1.5, <NA>]` stays float | a column keeps its type |

## 3. What a parameter accepts

Every argument reaches a call in one of three ways:

| Kind | Reaches each call as | Example |
|---|---|---|
| **literal** | the same value, every call | `offset=1.0` |
| **paired** | one part of the block **per call**: under `map`, the cell of the same row; under `collapse`, the group's cells as a list | `y=wf["d"]["y"]`, its rows the input's |
| **whole** | the same block, every call, converted to the parameter's form | `y=wf["o"][0]` |

**Run today**, `t[mod.map()](wf["d"]["x"], y=…)`: what the tool received,
or `refused` (a problem when declared), or `crash` (an exception when
declared). `o`'s rows aren't `d`'s.

| `y=` ╲ parameter `y:` | float | str | list | dict | Series | DataFrame | ndarray | Any |
|---|---|---|---|---|---|---|---|---|
| literal `5.0` | float | refused | refused | refused | refused | refused | refused | **crash** |
| literal `'hi'` | refused | str | refused | refused | refused | refused | refused | **crash** |
| literal `[1, 2]` | refused | refused | list | refused | refused | refused | refused | **crash** |
| literal `{'a': 1}` | refused | refused | refused | dict | refused | refused | refused | **crash** |
| paired: column of `d`, float | float | **float** | refused | **float** | **float** | DataFrame 3 | **float** | float |
| paired: column of `d`, str | **str** | str | refused | **str** | **str** | DataFrame 3 | **str** | str |
| whole: cell of `o` | **float64** | **float64** | list 1 | refused | refused | DataFrame 1 | float64 | float64 |
| whole: row of `o` | refused | refused | list 2 | dict 2 | Series 2 | DataFrame 1 | refused | dict 2 |
| whole: block of `o` | refused | refused | refused | refused | refused | DataFrame 2 | refused | DataFrame 2 |
| column of `o` (not `d`'s rows) | refused, saying to `join` or `zip_` first | | | | | DataFrame 2 | | |

The literal and whole rows follow rules (the literal's type; the whole
block's conversion table, `_CONVERTS` in `values.py`). **Where it disagrees
with itself**, each found by running:

| # | Found | Should be (proposed) |
|---|---|---|
| **A1** | A literal for a parameter typed `Any` **crashes** when declared: `TypeError: typing.Any cannot be used with isinstance()` | accepted: `Any` takes anything |
| **A2** | A paired cell's type **isn't checked**: a str column into `y: float` reaches the tool as `'a'`; a float into `dict` or `ndarray` as a float | refused when declared, as a whole block is |
| **A3** | The same number arrives in two forms: paired as `float`, from a whole cell as `numpy.float64` | one form, plain Python |
| **A4** | A pick narrower than its step is checked against **the step's** columns: `h(x: float)` on `wf["d"]["s"]`, when `d` also has a column `x`, is accepted, then every row fails with a raw `TypeError: h() missing … 'x'`. On its own the same pick is refused with a clear message | checked against the block: the pick's columns |
| **A5** | Under `mod.table()` the parameter's type isn't checked at all (the app's 015 C58: `np.ndarray` gets a `DataFrame`) | the same rule, block → the parameter's form |
| **A6** | `paired → list` is refused ("the verb decides what a column passes"), but `paired → DataFrame` passes the whole 3-row column, though each call should get one cell | under §0: the argument is its row's cell; a list or table of the column needs a written **fixed + packed** (`auto` may write it) |
| **A7** | A whole cell holding a number, into `y: list`, arrives as `[9.0]`; a cell holding a list arrives as the list | under §0, rule 3: no silent wrapping; a cell is delivered as it is, and `9.0` doesn't fit `list`, unless a packing is written |

**Proposed: the table above is the contract**, with one row per verb,
redone under §0: each cell becomes what the four questions answer
(its row's cell, a fixed cell, packed, or refused). The delivery rule (a literal, cell or block × the verb ×
the parameter's type → delivered, or refused with a reason) lives in one function.
`k.accepts` is that function's table read by parameter, and a test pins
every cell, the way this probe prints them.

## 4. The primitives that rearrange cells

A **rearrangement** moves cells and computes no new values. grid.md §10
lists every move core has. Here they reduce to **four moves, each along
either axis**, plus **two ways of working out which rows go together**:

| Move ╲ axis | **rows** | **columns** |
|---|---|---|
| **take**: choose, reorder or repeat | `filter`, `slice`, `sort`, `distinct`, a condition, `select(rows=)` | `select`, `drop`, `rename`, `mod.name`, `copy` |
| **nest**: many into one cell | `collapse` with `gather` (a group's rows into a list) | `pack` (a row's columns into a dict) |
| **unnest**: one cell into many | `expand` with `identity` (a list into rows) | `widen` (a dict or record into columns) |
| **concat**: side by side | `stack` | `zip_` |

| Working out | Gives | Used by |
|---|---|---|
| **partition**: one table's rows into groups, by a key | the groups | `collapse(by=…)`, `distinct` |
| **match**: two tables' rows into pairs, by position, by id (lineage) or by key | the pairs | `join` (by key), `zip_` (by position; `match_ids=True` by id) |

Every row move is a **row map**: for each output row, the input row(s) it
came from. That is grid.md §5's same / reorder / choose / many-from-one /
one-from-many / pair / concat / new. Column moves have the same shape, with
columns. So a combine is one of these too: **`join` is match by key, then
take rows on each side, then concat columns.**

**Tool verbs are the same moves, with a tool working out the map.** Each
gives the tool its unit (a row, a group, the table), and a primitive puts
the tool's output in place:

| Verb | The tool works out | Then the primitive |
|---|---|---|
| `filter` | keep or not, per row | take rows |
| `group` | a key per row | a new column (partition's label) |
| `collapse` | a value per group | partition, nest rows, the tool on each |
| `expand` | a list per row | unnest rows |
| `map` | a value per row | a new column |

That is K32's direction ("primitive modifiers with the other verbs built on
them"), here as a list rather than a rebuild.

**The analysis restructurings, as primitives** (rerun 2026-11-22 with
[grid-probes/moves.py](grid-probes/moves.py)):

| You want | As primitives | Today |
|---|---|---|
| wide → long (melt) | nest columns, then unnest rows | ✓ two steps |
| long → wide (pivot) | partition, nest columns **named by a column's values**, unnest columns | ✗ refused: `gather_dict` needs columns named `key` and `value` (it was a silent wrong answer on 2026-11-16; now refused) |
| a group's value beside each row | partition, nest, tool, match by key | ✓ two steps, `collapse` then `join` |
| a window (running total, rank, lag) | nest rows, tool on the list, **unnest back onto the same rows** | ✗ the last step: unnested rows get new ids, so they can't sit beside the old ones |
| a cross product | **match all pairs**, take, concat columns | ✗ `join` needs `on=` |
| transpose | melt, then pivot | ✓ only opaque, by a `table` tool; blocked by pivot |

**Each gap is one missing option on a primitive**, not a new verb:

| Gap | The missing option |
|---|---|
| pivot | nest columns, named by a column's values |
| window | unnest rows **aligned**: when the list is as long as the rows it was nested from, each item goes back to its row |
| cross product | match **all** (every pair) |

## 5. Iterables: what core iterates, and what it opens

*Owner, 2026-11-22: "this is why I think we need to define good primitives
and build off of them. Different kinds of iterables."*

Core iterates at the two levels of §1:

| Level | Core iterates | Over | Verbs |
|---|---|---|---|
| **the block** | its rows | one call per row | `map`, `filter`, `group`, `expand` |
| | its groups | one call per group (partition) | `collapse` |
| | the whole block | one call | `table` |
| | a grid of settings | one call per combination | `sweep` |
| | *its columns* | *one call per column* | *none: a gap* |
| | *a window of rows* | *one call per window* | *none: the window gap (§4)* |
| **a cell's value** | its items, into rows | unnest rows | `expand` |
| | its fields, into columns | unnest columns | `widen` |

At the value level, everything depends on **what kind of iterable** the cell
holds. **Run 2026-11-22**
([grid-probes/iterables.py](grid-probes/iterables.py)):

| Cell value | `expand` (into rows) | `widen` (into columns) |
|---|---|---|
| list `[1, 2]` | ✓ 2 rows | **completes with no columns: the list is dropped silently** (I1) |
| tuple `(1, 2)` | ✓ 2 rows | ✓ `var0`, `var1` |
| dict `{'a': 1, 'b': 2}` | ✓ rows `key`, value | ✓ columns `a`, `b` |
| set, str, ndarray, range, DataFrame | the cell fails at run | **dropped silently** (I1) |
| `[]`, `None` | **the row disappears** (I2) | dropped silently (I1) |

There is no rule, only behaviour per type: a list and a tuple are both
sequences, and `widen` opens one and drops the other.

**Proposed: four kinds, decided by what the value is, the same for every
verb:**

| Kind | Python | Unnest into rows | Unnest into columns |
|---|---|---|---|
| **sequence**: ordered, by position | list, tuple | an item per row, with `#<step>.idx` | a column per position, `var0…` |
| **mapping**: by key | dict, a record (`NamedTuple`, `dataclass`, `TypedDict`) | a row per key: `key`, value | a column per key or field |
| **unit**: core never opens it | str, bytes, numbers, None, arrays, images, DataFrames, any other object | refused when declared, if the column's type says so; else the cell fails, naming the kind | the same |
| **not openable as it is** | set (no order), range and generators (lazy) | refused, naming the fix: a tool that sorts, or makes a list | the same |

An array is a unit: a tool says what its parts are (pixels, channels, tiles;
decisions.md AR), and returns a sequence or a record. **No kind is ever
dropped silently** (P-D2's "nothing is lost silently").

**To decide:** an empty sequence or `None` under `expand`. Its row
disappears today. pandas keeps one row with a gap. Proposed: keep the row,
its item **absent**, so a row is never lost by unnesting.

| # | Found | Should be |
|---|---|---|
| **I1** | `widen` of a list, set, str, array, range or DataFrame completes with no columns: the column is gone, nothing said (the arrays were plan P1's W-arr; it's wider than arrays) | a list opens by position, as a tuple does; any other kind is refused, naming it |
| **I2** | `expand` of `[]` or `None` drops the row | one row, its item absent (to decide) |

## 6. A dev plan

> **Superseded 2026-11-23** by [expression-grammar/roadmap.md](expression-grammar/roadmap.md) (a clean slate, names first). Kept as the record of the pieces found here.

Each piece is small, and each behaviour change is confirmed first.

| # | Piece | Kind | Needs |
|---|---|---|---|
| **G0** | **The step grammar** ([expression-grammar/grammar.md](expression-grammar/grammar.md), started 2026-11-23): the ordered components as a grammar (each component a slot, its modifiers the words that fill it), and the dependencies as numbered rules, each with the problem it gives. A probe that parses and prints back every expression in the tests, and a property test that generates sentences from the grammar: each one is accepted and runs, or is refused when declared, naming its rule; never a crash, never a silent output | docs, then a test | the owner's yes on §0 |
| **O1** | Modifiers kept in component order, so `[retry, map]` retries each call | behaviour | G0 |
| **E0** | **§0 into model.md and rules.md**: the four questions, the six rules, the verbs as presets | docs | the owner's yes on §0's open points |
| **B0** | The words into model.md §2: pick (the address), block (what it holds; cell, row, column its cases), table, grid (the data cells only). Rename `_shape_kind`'s n×m case | docs, one rename | the owner's yes |
| **B1** | The delivery contract: §3's table as rules.md text, and a test that runs the whole matrix and pins every cell (today's answers, A1–A7 marked expected-to-change) | test, no behaviour change | B0 |
| **B2** | `k.block(pick)`: read-only, from today's parts (§2) | additive | B0 |
| **B3** | One delivery rule, fixing A1–A7 one at a time (A1 and A4 first: a crash and a raw error) | behaviour, one piece each | B1 |
| **B4** | `k.accepts(operation, parameter)` and `k.fits(…)` for the UI: what a parameter takes under its modifiers, and how a pick would reach it | additive | B2, B3 |
| **R1** | The primitives (§4) in rules.md, every modifier and combine listed as one; the restructurings as recipes | docs | B0 |
| **R2** | The three missing options: match all, aligned unnest, nest by a column's values | behaviour, one piece each | R1, the owner's choice of which |
| **F1, F2** | A data step keeps absent cells absent, and a column its type | behaviour, one piece each | — |
| **F3** | `k.freeze(name, pick)` (§2, *Freezing*) | additive | F1, F2, B2 |
| **I1** | `widen` opens a list by position, and refuses any kind it can't open | behaviour | R1 |
| **I2** | `expand` of an empty sequence or `None` keeps the row (once decided) | behaviour | the owner's choice |
| **I3** | The four kinds of iterable (§5) in rules.md; a column's type says its kind, so unnesting a unit is refused when declared | docs, then behaviour | R1 |
| **E1** | Pick methods that pack, written into the expression: `.tolist()`, `.to_dict()`, `.to_frame()`, `.to_numpy()`, with `by=` and `window=` scopes; the calls and scopes checked to agree; `collapse(by=)` the shorthand for `.tolist(by=)` | additive, then behaviour | E0 |
| **E2** | `auto` writes the packing methods from the tool's types | behaviour | E1 |
| **E3** | The modifiers that don't fit (§0): `cast`, `select(rows=)`, `slice`, `copy` | behaviour, one at a time | E0, the owner's choice for each |
| (K32) | Verbs rebuilt on the primitives, the four questions | large, parked | R1, E1 |

**Suggested order:** G0 first, since it closes the system the rest is built in; then E0; then B0, B1, then B3's A1 and A4 (the two that crash or
fail raw), B2, B4. Freezing next: F1, F2, then F3. R1 and I3 alongside, since
they're docs; I1 with them, since it loses data silently. R2 and I2 when the
app needs a window or a pivot.

## 7. To settle with the owner

**Decided, 2026-11-22:**

- **Block** is the general word; cell, row and column are its cases. The
  code's n×m case is renamed (`rows × columns`).
- **§0, one expression from sheet to sheet** (2026-11-23): every argument
  is one cell per call; modifiers prepare and never change a value; packing
  is the only way many cells become one, always written; `auto` sets the
  defaults from the tool's signature, and writing a choice yourself
  overrides it. A call is one run of the tool.
- **A paired cell of the wrong type** is refused when declared (A2).
- **Freezing** copies whatever is there (§2).
- **The four kinds of iterable** (§5).
- **I2**: an empty list or `None` under `expand` keeps its row, the item
  absent.

**Open:**

1. **§0's open points**: the packings, the scope's word, the missing
   landing, and the modifiers that don't fit. (Settled 2026-11-23: packing
   is an input modifier, and `.tolist()` on a pick is its shorthand; no
   method means its row's cell; `auto` writes the same method when the types call for it;
   modifiers decide the calls and are shorthands for the arguments'
   preparation.)
2. **A tool's parameter typed `Block`** receives a block (owner). Without
   row numbers and lineage, so recipes, single-cell runs and staleness keep
   working, or with them, relaxing core-asks' "lineage never reaches a
   tool"? Wait until a tool needs it?
3. **R2**: which of pivot, window and cross product first? (When the app
   needs one.)
4. **Freezing**: should a frozen step note where it came from, for display
   only?
