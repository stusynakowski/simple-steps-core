# Blocks, and the moves that rearrange cells

> **Evidence, 2026-11-22/23.** The runs and findings behind the expression
> grammar. **The design itself now lives in
> [expression-grammar/](expression-grammar/README.md)** (the grammar, the
> primitives, the conditions, a canonical form, the roadmap); §0 says how it
> got there. What stays here: §1 the words, pick, block, table, and a pick
> as a live address; §2 the block as an object, and freezing; §3 what a
> parameter accepts today, run ([grid-probes/blocks.py](grid-probes/blocks.py)),
> and A1–A7; §4 the moves that rearrange cells, and today's
> restructurings; §5 the kinds of iterable, I1–I2. Nothing here is built.

## 0. How we got here, and the runs kept

*Owner, 2026-11-23: "how do we enable a spreadsheet-like experience, but
with one expression mapping from sheet to sheet, in a way that is very easy
to understand and can handle cells containing any type of Python data
structure?"*

This section was where that idea was worked out, on 2026-11-23, in this
order. Each idea is now in the grammar folder, where it is kept current:

| Worked out here | Became | Now in |
|---|---|---|
| a step is one formula dragged over a sheet; four questions (which cells, how many calls, what each argument gets, where the output goes) | the five components: tool, input, call, execution, output | grammar.md §0, §6 |
| six rules: one cell per argument per call; modifiers prepare and never change a value (except a written conversion); packing is the only way many cells become one; columns go to parameters, rows to the split; any Python value; `auto` writes its defaults | the heuristics H1–H9, and the two levels of a value | grammar.md §5; canonical.md |
| today's verbs as preset answers | presets, as cells of the primitives table | primitives.md §5 |
| the ordered components, and how they depend on each other | the conditions between components | conditions.md |
| scope: what one call reads of an argument (row, window, group, everything) | the scopes of `nest`: `"group"`, `group(by=…)`, `"all"`, `window(n)` | canonical.md §3.1 |
| methods on a pick (`.tolist()`) as a second way of writing | a shorthand, a soft link to an input modifier; the full form `tool[modifiers](data)` | grammar.md H7; canonical.md |
| every modifier placed by its job | one primitive, three places | primitives.md §3 |
| a grammar that closes the system | the grammar, and the plan | grammar.md; roadmap.md |

**The runs from it, kept as evidence:**

| Run | What it showed |
|---|---|
| calls per verb, a 3-row input (2026-11-22) | `map` 3 calls; `collapse(by=…)` one per group; `table` 1; `sweep` one per combination of settings; `source` 1. A `retry` can make several attempts at one call, still one call |
| a block's two directions, `wf["p"][["x", "y"]]` (2026-11-22) | columns go to parameters by name, under every verb; rows are split: `f(x=1.0, y=10.0)`, `f(x=2.0, y=20.0)`, … under `map`; `g(x=[1.0, 3.0], y=[10.0, 30.0])`, `g(x=[2.0], y=[20.0])` under `collapse(by="k")` |
| **O1**, the order of modifiers (2026-11-23, [grid-probes/order.py](grid-probes/order.py)) | `flaky[mod.map(), mod.retry(times=2)]`: row 1 failed once, was retried, all three rows done. `flaky[mod.retry(times=2), mod.map()]`: **the retry did nothing** (it wrapped the whole map, which records a failed row rather than raising). Row 1 failed. The two levels of execution mixed (grammar.md §6.4) |
| each row against the whole column, today (2026-11-22) | two steps: `all = op("gather")[mod.collapse()](wf["p"][["x"]])`, then `z[mod.map()](wf["p"]["x"], ys=wf["all"][0]["x"])`, giving `[-2.0, -1.0, 3.0]` |
| picks have no `tolist` today (2026-11-23) | a pick has one such member, `wf["p"].header`; a column named `tolist` couldn't clash, since columns are picked with brackets |

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

**How the two levels are kept apart** (canonical.md, `mod.input.nest`): nesting is the
only way many cells become one, and it is always written, so the A7 row
above stops being a guess. (A first attempt, "cell or block, chosen by
`auto` from the types", stood here on 2026-11-22; the canonical form
replaces it: every argument is one cell per call, and a reduction is always
a written `nest`.)

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
| **F1** | Written into a data step, an **absent** cell becomes a **known `None`**: the gap is lost silently | absent stays absent. **Done 2026-11-25**: every gap in data given is absent (owner: "B") |
| **F2** | A nullable float column whose values are whole numbers, `Float64 [1.0, <NA>]`, is stored as **`Int64`**: `1.0` comes back as `1`. `[1.5, <NA>]` stays float | a column keeps its type. **Done 2026-11-25**: the dtype decides, for plain floats too; a warning, never a conversion (owner) |

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
| **A6** | `paired → list` is refused ("the verb decides what a column passes"), but `paired → DataFrame` passes the whole 3-row column, though each call should get one cell | in the canonical form: the argument is its row's cell; a list or table of the column needs a written `mod.input.nest` (a shorthand may write it) |
| **A7** | A whole cell holding a number, into `y: list`, arrives as `[9.0]`; a cell holding a list arrives as the list | in the canonical form: no silent wrapping; a cell is delivered as it is, and `9.0` doesn't fit `list`, unless a `nest` is written |

**Proposed: the table above is the contract**, with one row per verb,
redone under the canonical form (expression-grammar/canonical.md): each
cell becomes its row's cell, a fixed cell, nested, or refused. The delivery rule (a literal, cell or block × the verb ×
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

## 6. The plan

Superseded 2026-11-23 by [expression-grammar/roadmap.md](expression-grammar/roadmap.md):
a clean slate, names first. The findings named here (A1–A7, F1–F2, I1–I2,
O1, G1–G2) are placed there: the binding ones replaced by the new set, the
data layer's fixed in today's code.

## 7. Decided here

**Decided on this page** (2026-11-22/23), and still standing:

- **Block** is the general word; cell, row and column are its cases (the
  code's n×m case to be renamed, with the names: roadmap phase 1).
- **A pick gives a block, never a table; only a step makes a table** (§1).
- **A paired cell of the wrong type** is refused when declared (A2).
- **Freezing** copies whatever is there (§2).
- **The four kinds of iterable** (§5), and **I2**: an empty list or `None`
  under `expand` keeps its row, its item absent.

**Open questions** are kept in one place now: grammar.md §8 (a parameter
typed `Block`; N2–N9), canonical.md §7, primitives.md §6, and conditions.md's
proposed conditions. Two from here, carried there: which of pivot, window
and cross product comes first (when the app needs one); whether a frozen
step notes where it came from, for display only.
