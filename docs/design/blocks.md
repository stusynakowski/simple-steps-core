# Blocks, and the moves that rearrange cells

> **Draft, 2026-11-22, for the owner**, to choose the next dev plan. §1 is
> the words; §2 the **block**, an object core doesn't have yet; §3 **what a
> parameter accepts**, run today
> ([grid-probes/blocks.py](grid-probes/blocks.py)), and where it disagrees
> with itself; §4 the **primitives** that rearrange cells, with every
> modifier and combine written in them; §5 the **kinds of iterable** a cell
> can hold, and what core opens; §6 the dev plan; §7 the questions.
> It builds on [grid.md](grid.md) (§8 the definitions, §10 every move) and
> doesn't replace it. Nothing here is built.

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

A block becomes a table by being declared as a step: `k["cp"] =
wf["f"]["x"]` makes that block step `cp`'s own table, with lineage back to
`f` (today's linked copy, 015 C56).

A pick is always a rectangle: every chosen row × every chosen column, not
necessarily next to each other. "Block" is the general word, and cell, row
and column are its special cases. (Today's code, `_shape_kind`, says
`block` only for n×m. It needs another name, say `rows × columns`, if the
owner agrees.)

**A tool never receives a block.** A parameter *accepts* a block: core
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

**The convention: cell or block, it depends, by a fixed rule** (owner,
2026-11-22: "cell and the block, the answer is it depends"; "a default
convention on how to handle the grid based on the type, but the user can
also specify if they know exactly what they want": what `auto` was made for).

Each argument is delivered one of two ways:

| Delivery | Each call gets | Like Excel's |
|---|---|---|
| **cell** | one cell: its row's (a paired argument), or one fixed cell of another step, the same every call | `B2` dragged down; `$B$1` |
| **block** | the whole block, the same every call, nested into the parameter's form: a column → a list, a row → a dict, rows × columns → a table | `SUM($B$2:$B$4)` |

1. **A cell's value is never changed**: a cell holding a list is that list,
   delivered as it is.
2. **The modifier decides what a call's share is**: under `map`, a row;
   under `collapse`, a group (its cells nested into a list); under `table`,
   everything.
3. **`auto` picks each argument's delivery from the types**, when the step is
   declared:

   | Parameter's type | `auto` writes |
   |---|---|
   | no type, `Any`, or a type one cell of the argument fits | **cell** |
   | a type one cell can't fit but the block does (`list[float]` on a float column; `pd.DataFrame` on cells that aren't tables) | **block** |
   | neither | refused when declared, naming both |
   | the argument's types not known yet | **cell**, shown as assumed |

   It picks the verb the same way (today's rules, `checks.infer_verb`), plus
   one it lacks: a tool whose input parameter takes a list of what the
   column's cells hold is a `collapse` (run: `auto` on `sumup(xs: list)`
   over a float column picks `map`, and the step is invalid).
4. **What `auto` picks is written into the expression**, as `auto` already
   does for the verb: shown, never re-guessed after a run, changed with one
   edit. **Writing it yourself overrides it**, and is never second-guessed.
5. **A block can be made in place or as its own step.** In place, the
   argument is marked as a block. As a step, a `collapse` (or `pack`) makes
   one cell, which is then delivered as a cell. It's the same nest move
   (§4); the in-place form is shorthand. (Run: `all = op("gather")
   [mod.collapse()](wf["p"][["x"]])`, then `z[mod.map()](wf["p"]["x"],
   ys=wf["all"][0]["x"])`, gives each row against the whole column.)

**How a block is marked in an expression is open** (§7): candidates are a
modifier on the argument, `ys=wf["p"]["y"][mod.collapse()]`, which says it
is the nest move, or a mark of its own.

Before anything runs, the UI can show each argument's delivery and whether
its type fits:

```
zs = z[mod.map()](wf["p"]["x"], ys=<block> wf["p"]["y"])     staged · 3 rows

  x   ← one cell per row of p         float ✓
  ys  ← all of p["y"], every row      list[float] ✓   (auto: one float isn't a list)
```

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
| **A6** | `paired → list` is refused ("the verb decides what a column passes"), but `paired → DataFrame` passes the whole 3-row column, though each call should get one cell | one rule for both (§1, the convention): `auto` writes **block** for both, since one float fits neither; written, so it shows |
| **A7** | A whole cell holding a number, into `y: list`, arrives as `[9.0]`; a cell holding a list arrives as the list | the same choice, made visible: `auto` writes **block** (a 1-cell block as a list), shown in the expression, instead of being decided silently at the call |

**Proposed: the table above is the contract**, with one row per verb,
redone under §1's convention: each cell becomes what `auto` writes (cell,
block, or refused). The delivery rule (a literal, cell or block × the verb ×
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

Each piece is small, and each behaviour change is confirmed first.

| # | Piece | Kind | Needs |
|---|---|---|---|
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
| (K32) | Verbs rebuilt on the primitives | large, parked | R1 |

**Suggested order:** B0, B1, then B3's A1 and A4 (the two that crash or
fail raw), B2, B4. Freezing next: F1, F2, then F3. R1 and I3 alongside, since
they're docs; I1 with them, since it loses data silently. R2 and I2 when the
app needs a window or a pivot.

## 7. To settle with the owner

**Decided, 2026-11-22:**

- **Block** is the general word; cell, row and column are its cases. The
  code's n×m case is renamed (`rows × columns`).
- **Cell or block, it depends, by a fixed convention** (§1): `auto` picks
  from the types and writes it into the expression; writing it yourself
  overrides. Both the in-place and the separate-step forms of a block exist.
- **A paired cell of the wrong type** is refused when declared (A2).
- **Freezing** copies whatever is there (§2).
- **The four kinds of iterable** (§5).
- **I2**: an empty list or `None` under `expand` keeps its row, the item
  absent.

**Open:**

1. **How a block is marked** in an expression: a modifier on the argument
   (`ys=wf["p"]["y"][mod.collapse()]`), or a mark of its own?
2. **A tool's parameter typed `Block`** receives a block (owner). Without
   row numbers and lineage, so recipes, single-cell runs and staleness keep
   working, or with them, relaxing core-asks' "lineage never reaches a
   tool"? Wait until a tool needs it?
3. **R2**: which of pivot, window and cross product first? (When the app
   needs one.)
4. **Freezing**: should a frozen step note where it came from, for display
   only?
