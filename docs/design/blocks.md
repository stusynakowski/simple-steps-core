# Blocks, and the moves that rearrange cells

> **Draft, 2026-11-22, for the owner**, to choose the next dev plan. §1 is
> the words; §2 the **block**, an object core doesn't have yet; §3 **what a
> parameter accepts**, run today
> ([grid-probes/blocks.py](grid-probes/blocks.py)), and where it disagrees
> with itself; §4 the **primitives** that rearrange cells, with every
> modifier and combine written in them; §5 the dev plan; §6 the questions.
> It builds on [grid.md](grid.md) (§8 the definitions, §10 every move) and
> doesn't replace it. Nothing here is built.

## 1. Pick, block, table

Keep **the address** and **the contents** apart:

| Word | Is | Lives in | Example |
|---|---|---|---|
| **pick** | an **address**: a step, at most one row part, at most one column part | an expression; saved | `wf["p"][1:3][["x", "y"]]` |
| **block** | **what a pick holds now**: a rectangle of cells, with their states and types | the kernel, at the moment it is asked; never saved | rows 1–2 of `p` × columns `x`, `y` |
| **table** | a block with its **header** and **index columns** (`#`, `#<step>`); one per step | a step's output | all of `p` |
| **cell**, **row**, **column** | a block of 1×1, 1×n, n×1 | — | `wf["p"][2]["x"]` |

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

**Proposed rule:**

1. **A cell passes its value**, never wrapped. A 1×1 block is a cell.
2. **The structure comes from the block and the verb, never from the
   parameter's type.** Under `map` a paired argument gives one cell; under
   `collapse`, the group's cells as a list. A whole block gives its shape's
   container: a column → a list of its values, in row order; a row → a dict,
   name → value; rows × columns → a table. A parameter may ask for another
   spelling of the same structure (a `Series` for a column or a row; a
   `DataFrame` for any block), never for another structure.
3. **The parameter's type then checks the units**: `list[float]` takes a
   column of floats, or a cell holding a list of floats; `float` takes one
   cell holding a float.

Under this rule, a column whose cells are lists, passed whole, is
`list[list[int]]`: a list made by the block, of lists held by the cells.
The UI can show both levels: the block's structure, and the type of its
cells.

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
| **A6** | `paired → list` is refused ("the verb decides what a column passes"), but `paired → DataFrame` passes the whole 3-row column, though each call should get one cell | one answer for both: a paired column passes one cell under `map` (§1, rule 2: the verb decides the structure) |
| **A7** | A whole cell holding a number, into `y: list`, arrives as `[9.0]`: the block is wrapped because of the parameter's type; a cell holding a list arrives as the list (§1, *Two levels*) | a cell passes its value: refused, since a number isn't a list (§1, rule 1) |

**Proposed: the table above is the contract**, with one row per verb. The
delivery rule (a block or literal × the verb × the parameter's form →
passed as is, converted, or refused with a reason) lives in one function.
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

## 5. A dev plan

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
| (K32) | Verbs rebuilt on the primitives | large, parked | R1 |

**Suggested order:** B0, B1, then B3's A1 and A4 (the two that crash or
fail raw), B2, B4. R1 alongside, since it's docs only. R2 when the app
needs a window or a pivot.

## 6. To settle with the owner

1. **Block** as the general word, with cell, row and column as its cases;
   and the n×m case renamed (`rows × columns`?). **The two levels** (§1):
   the block's structure from the pick and the verb, the cell's value never
   wrapped; the parameter's type checks the units. Does that rule hold?
2. **A tool never receives a block**, only its values in the parameter's
   form. Or should a parameter typed `Block` receive one?
3. **A2**: refuse a paired cell whose type doesn't fit, or convert where
   `mod.cast` would (str → float)?
4. **A6**: does a paired column ever pass whole, as a `DataFrame` or a list,
   under `map`? Proposed: no, it passes one cell; a whole column is a whole
   block from a step whose rows aren't the input's.
5. **R2**: which of pivot, window and cross product first?
