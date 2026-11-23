# The conditions between components

> **Draft, 2026-11-23, for the owner.** Level L3 of the grammar
> ([grammar.md](grammar.md) §0, *The levels*): **how one component's state
> limits the others'**, so that an expression is valid. Each condition is
> numbered, says **when** (the classes, from grammar.md §6) and **then**
> (what is allowed, implied or refused), and what the user is told. Marked
> **decided** (the owner has said so) or **proposed**.

*Owner, 2026-11-23: "In both of these cases they are conditional on each
other … your selection of one influences the possible valid cases of the
other. These conditional relationships would need to be specified and
documented."*

## The two layers

*Owner: "define primitives that encapsulate pretty much everything we could
ever want to do in this scope, into the canonical syntax that is parsed;
then from there build components that map intuitive, user-friendly syntax
into the canonical primitives."*

| Layer | Is | Must be |
|---|---|---|
| **canonical** | the primitives ([primitives.md](primitives.md)), in `tool[modifiers](data)` | **complete** (everything in scope can be said), **small**, **closed** (every sentence runs, or is refused naming its condition), and **readable**: users open their expressions and see it |
| **surface** | presets (`collapse(by="k")`), methods on picks (`.tolist()`), `auto` | each form maps to **exactly one** canonical form; opened, it shows it (H1) |

**The conditions below are the canonical layer's, and only its.** The
surface needs none of its own: its one job is to choose a canonical form
(the most likely, written and shown: H2) and let these conditions check it.

## Each component's own primitives

| Component | Its primitives | Combined |
|---|---|---|
| **input** | **bind** (by position, by name, given) and the restructurings on the input: take, convert, nest, join together | in a fixed order: bind, take, convert each cell, nest |
| **call** | **split into pieces, one call per piece**: one piece; each row; each group (a key); each combination of settings | exactly one per step |
| **execution** | the wrappers around each call: retry, time limit, catch a failure, stop after n failures, report progress | by nesting: the one place where order means something |
| **output** | **land** (its own row; a new row per call; every row of its scope) and the restructurings on the output: unnest, take, convert, name | in a fixed order: land, unnest, take, convert, name |
| **tool** | none of its own: the user's function, core's cell tools (`identity`, `gather`, `total`, …), or a restructuring used as a step | — |

Splitting into groups by a key is shared by two components: the **call**
(one call per group) and the **input** (each group nested into a list).
That is why `collapse` has crossed classes.

## The conditions

### Pick → input (binding)

*Owner: binding is part of the input, and picks influence it.*

| # | When | Then | Status |
|---|---|---|---|
| **R1** | always | binding chooses among **the pick's columns**, never the whole step's (today it uses the step's: A4, and two columns with no name match accepted) | proposed |
| **R2** | a parameter, and a column of the pick with its name | bound **by name** | decided (H3) |
| **R3** | a pick of **one** column, given by position | bound **by position**, to that parameter | decided (H3, case a) |
| **R4** | a parameter given `param=pick` | that binding, whatever the names | decided (H3) |
| **R5** | no column has the parameter's name, the pick has several | **refused**, naming the fix `param=wf[…][…]`; no column chosen by its type | decided (H3, case b) |
| **R6** | a column named like a parameter **with a default** | **refused**, naming both: the column, or the default (G2) | decided (H3, case c) |
| **R7** | a parameter with no default, and nothing bound | refused, naming the parameter | proposed |
| **R8** | a parameter given twice (by position and by name) | refused | proposed (N7) |

### Tool's types → input (the cells)

| # | When | Then | Status |
|---|---|---|---|
| **R9** | the parameter takes one value, and each cell holds one such value | each call gets its cell, as it is | proposed |
| **R10** | the parameter takes a list of what each cell holds | the cells are **nested** into a list (H6); the surface may leave it out, opened it is shown | decided (H6) |
| **R11** | a cell's type is known not to fit | **said when declared** (a warning); the cells that fit run; the others fail, naming the input cell | decided (N1) |
| **R12** | a missing value (absent, `None`, `NaN`) into a parameter that isn't `Optional` | that cell fails; into an `Optional` parameter it gets `None` | decided (N2; what else is returned, to clarify) |

### Input ↔ call

| # | When | Then | Status |
|---|---|---|---|
| **R13** | one call per row | each argument: its row's cell, or nested over a window, its group, or everything | proposed |
| **R14** | one call per group (a key) | each argument from the input **nested per that group** (or over everything); a per-row argument is refused, naming the fix | proposed (blocks.md §0) |
| **R15** | one call in all | each argument nested over everything, or a literal | proposed |
| **R16** | arguments nested by two different keys, and no per-row argument | refused: no single piece to make one call per | proposed (blocks.md §0) |
| **R17** | an argument from **another step's rows**, per row | refused unless matched (a join first, or matched in the call: N3); whole, or one fixed cell, is fine | proposed |

### Call ↔ output

*Owner: the call influences the output structure, and the output the call.*

| # | When | Then | Status |
|---|---|---|---|
| **R18** | land on **its own row** | needs one call per row | proposed |
| **R19** | **keep or drop** its row | needs one call per row, and a tool returning `bool` | proposed |
| **R20** | land on **every row of its scope** (a group's output beside each of its rows) | needs one call per group (or one in all) | proposed (missing today) |
| **R21** | one call per group, or one in all | lands as a new row per call, unless R20 is written | proposed |
| **R22** | **unnest into rows** | the tool returns a sequence | proposed |
| **R23** | **unnest into columns** | the tool returns a record or a mapping; a record is unnested by default | proposed |

### Calls → execution

| # | When | Then | Status |
|---|---|---|---|
| **R24** | zero calls (data, the empty step) | no input but the data, no execution, the output is the data | proposed |
| **R25** | execution wrappers | each wraps **every call**, whatever order they are written in among the other modifiers; among themselves, the written order is kept (O1) | proposed |

### Output → names

| # | When | Then | Status |
|---|---|---|---|
| **R26** | an output column's name clashes with an input column kept beside it | to settle (N6) | open |

## Next

- Go through the **proposed** ones with the owner.
- For each, the problem text the user sees.
- The surface's mappings: each preset and shorthand, and the canonical form
  it opens into.
