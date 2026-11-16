# The grid: what a step holds, and how steps map

> **Draft, 2026-11-16, for the owner**, to consolidate the grid's design.
> §1–§3 are **what core has today**, every table run on 2026-11-16 at
> `dbaf4c7` ([grid-probes/chain.py](grid-probes/chain.py): one source through
> every verb). §4 lists where today's representation is inconsistent. §5 is a
> **starting shape** for the consolidated design, to change with the owner's
> own thoughts; §6 the questions to settle. The rules a user sees are
> [rules.md](rules.md); the full model is [model.md](model.md).

## 1. Two levels

```
        step level: a grid in, a grid out
   ┌──────────┐   pick    ┌──────────┐   verb cuts it    ┌────────┐
   │ input    │ ────────► │ the part │ ─────────────────►│ values │──► tool(...)
   │ grid     │ (a grid)  │ (a grid) │ into what each    │ (plain │      │
   └──────────┘           └──────────┘ call receives     │ Python)│      │ returns values
        ▲                                                └────────┘      ▼
        │ row map: which input row(s)          the verb assembles the values into
        └───────────────────────────────────── the output grid ◄─────────────────
```

- **A step maps grids to a grid** (owner, 2026-11-16). Its output is one
  table: data columns, a row identity, lineage, a state per cell.
- **A tool receives values**: the part of a pick its verb hands each call,
  plain Python, never `#` columns, states or row ids (*run*, §3).
- **Every part of a grid is a pick, and every pick is a grid**: a cell is
  1×1, a row 1×n, a column n×1 (*run*, plan.md §1).

## 2. What a step holds today

```
Step  name · expression (Operation) · state · problems · warnings · plan · extras · id
 └─ Output
     data     a DataFrame
                index    = row ids (core's identity; never shown)
                columns  = data columns, and some lineage columns (#v …)
     states   a DataFrame, the same shape: a state per cell
     meta     verb · form · value_column · n_in · inverse (the way back)
              version (data version) · run_key · read (inputs' versions)
              row_reads (a fingerprint per input row) · tool_hash · ran_with · stale
 └─ plan      before it runs: rows, columns, types, size (each exact / stated /
              bounded / unknown) and inverse
```

*Run* for `d = dbl[mod.map()](wf["v"])`, `v` = Ada, Ben, Cy:

| Part | Holds |
|---|---|
| `output.data` | one column, `d` = 2, 4, 6; index `[0, 1, 2]` (v's ids) |
| `output.states` | `d`: known, known, known |
| `output.meta` | `verb: map`, `inverse: trace`, `read: {v: 405ad5…}`, `run_key`, `tool_hash`, `row_reads` |
| `plan` | rows exact 3; columns exact `[d]`; types `{d: int}`; size 156 bytes; inverse `trace` |

What a user sees is not the DataFrame but **`k.view(step)`**: its columns,
rows by row number `#` (`0…n-1`), each row's lineage worked out from the ids,
cells with value, type and state. **`k.cell(step, row)`** adds the input
cells a value came from.

## 3. How each verb maps a grid to a grid

*Run* on `v` (name, ward, temp, n; 3 rows) and `w` (ward, beds; 2 rows).

| Step | Row ids | Data columns out | Lineage (as the view shows it) | Way back | The tool received, per call |
|---|---|---|---|---|---|
| `dbl[map](v)` | v's: 0, 1, 2 | **only `d`** | none | trace | `n=1` (int), 3 calls |
| `hot[filter](v)` | v's kept: 1, 2 | v's, all | `#v`: 1, 2 *(derived)* | trace | `temp=37.0`, 3 calls |
| `split[expand](v)` | new: `"0.0"`, `"0.1"`, `"1.0"`… | only `e` | `#v`: 0, 0, 1… · `#v.idx`: 0, 1, 0… *(`#v` stored, `.idx` derived)* | trace | `name="Ada"`, 3 calls |
| `mean[collapse(by="ward")](v)` | the key: `"A"`, `"B"` | `ward`, `c` | `#v`: [0, 2], [1] *(stored)* | trace | `temp=[37.0, 38.2]` (a list), 2 calls |
| `ward_of[group](v)` | v's: 0, 1, 2 | v's, plus **`group`** | none | trace | `name="Ada"`, 3 calls |
| `sort(by="temp")(v)` | v's, reordered: 0, 2, 1 | v's, all | `#v`: 0, 2, 1 *(derived)* | trace | no tool |
| `select(columns=["name"])(v)` | v's | `name` | none | trace | no tool |
| `wf["v"][cols["temp"] > 38]` | v's kept: 1, 2 | v's, all | `#v`: 1, 2 *(derived)* | trace | no tool |
| `wf["srt"][0]`, saved as `wf["srt"][rows[row["v"] == 0]]` | v's: 0 | srt's | `#srt`: 0 · `#v`: 0 | trace | no tool |
| `zip_(v, d)` | v's | v's and `d` | `#v`: 0, 1, 2 · `#d`: 0, 1, 2 | **rebuild** | no tool |
| `join(v, w, on="ward")` | new, counted: 0, 1, 2 | both sides' | `#v`: 0, 1, 2 · `#w`: 0, 1, 0 *(stored)* | trace | no tool |
| `stack(v, w)` | new, counted: 0…4 | the union | `#v`: 0, 1, 2, –, – · `#w`: –, –, –, 0, 1 *(stored)* | trace | no tool |
| `summary[table](v)` | its own: 0…5 | what it returned | none | **opaque** | the whole of v's data as one DataFrame (no `#` columns), 1 call |

And, from `k.cell("e", 1)`: one value's inputs, `[{step: "v", row: 0,
argument: "name", values: {name: "Ada"}}]`.

**Between any two steps**, core answers *how do their rows relate?* (model.md
§5): **aligned** (the same rows, any order), **subset**, **child and parent**,
**group and members**, **unrelated**. That decides whether a `zip_` or a
column argument may pair them, and which join a refusal writes.

## 4. Where the representation is inconsistent today

| | Seam | Seen in §3 | Consequence |
|---|---|---|---|
| G1 | **Lineage has three forms.** Stored as `#` columns in the data (expand, collapse, join, stack), worked out from row ids when shown (filter, sort, a pick, `#v.idx`), or none (map, group, select) | the *stored* / *derived* marks | every reader of lineage needs all three paths; F1, F5 |
| G2 | **A row id has three kinds**: an int (a source's row), a dotted string (`"0.1"`, an expand's item), the group key (`"A"`, a collapse); join and stack count new ones | the Row ids column | identity depends on the verb; ids from two joins can look alike |
| G3 | **What a grid holds depends on the verb.** A `map` or `expand` holds only the column it makes; a `filter`, `sort` or `group` holds a copy of every input column | Data columns out | two meanings of "a step's table"; copies cost memory (decisions.md ST: 35 MB a step before the fixes) |
| G4 | **Aligned steps show lineage differently.** `map`, `group` and `select` (one-to-one, in order) show none; `zip_` of two aligned steps shows both `#v` and `#d`; `sort` (one-to-one, reordered) shows `#v` | Lineage column | "same rows" isn't visible as one thing |
| G5 | **Row facts live in five places**: the data's index (ids), `#` columns in the data, `meta["row_reads"]` (fingerprints), `states`, and lineage worked out by `trace` | §2 | each must agree; the order-of-edits bugs sat between them (stress-failures.md) |
| G6 | **"How do two steps' rows relate?"** is answered by five helpers, each covering some cases | — | observations F4; WR1 |
| G7 | **The way back** is `trace` for nearly everything, `rebuild` for `zip_`, `opaque` for `table` | Way back | `rebuild` (the expression that gives the input back) is rare in practice |
| G8 | **`group`'s key is named `group`**, not after its step, while every other one-column output takes its step's name (D9) | `g` has `group` | one naming rule with an exception |

## 5. A starting shape for the consolidated design

*Proposed, to edit.* It takes what decisions.md has already said yes to (ST:
a step stores only what it adds; PL2: each verb declares its row map; WR1: one
relation) and makes them the representation.

**A step's grid is four things, and only these:**

| Part | What | Replaces |
|---|---|---|
| **columns it makes** | data columns, typed; a carried column is never copied | G3: the copies |
| **a row map** | for each output row, the input row(s) it came from, of one of eight kinds (below) | G1, G2, G5: stored `#` columns, id kinds, the fingerprints' pairing |
| **cell states** | one per cell it makes | — |
| **a plan** | the same three, before it runs, each exact / stated / bounded / unknown | — |

**The row map's kinds**, one per verb:

| Kind | Each output row is | Verbs |
|---|---|---|
| **same** | the same input row, same place | `map`, `group`, `select`, `drop`, `rename`, `copy`, `widen`, `pack` |
| **reorder** | the same input row, another place | `sort` |
| **choose** | one input row, some left out | `filter`, `slice`, `distinct`, a row pick, a condition |
| **many from one** | item *j* of input row *i* | `expand` |
| **one from many** | a group of input rows | `collapse` |
| **pair** | one row from each input (or a gap) | `join`, `zip_` |
| **concat** | one row from one of the inputs | `stack` |
| **new** | no input row | `source`, a value, `sweep`, `table` |

**Everything else is derived from the row maps, never stored:**

- **row identity**: a source row's own id; any other row is its path through
  the row maps (G2 goes: one kind of id);
- **lineage** as shown, `#v`, `#v.idx`: the row maps composed back to `v`, as
  row numbers (G1, G4 go: one form);
- **a carried column**, `wf["h"]["name"]`: read from the step that made it,
  through the row maps (G3);
- **how two steps' rows relate**: compose both maps to the nearest shared
  ancestor; aligned when every row meets one row (G6: one function);
- **which rows go stale**: an input's changed rows, pushed through the maps
  (PL3, and incremental runs);
- **the way back**: `trace` is the row maps themselves; `opaque` is a `new` map
  from a `table` (G7).

**The mapping between two steps is the expression**, in three moves, each
already a rule:

1. **the pick** narrows the input grid to a grid (a `choose` or `same` map);
2. **the verb** cuts that grid into what each call receives (a row's cells, a
   group's columns as lists, the whole grid), and binding says which column
   reaches which parameter;
3. **the verb assembles** what the tool returned into the columns it makes,
   and its row map.

**Saving follows** ([saving.md](saving.md)): a step saves its columns, its
row map and its states. Nothing else, since everything else is derived.

## 6. To settle with the owner

| | Question | Today | Starting shape says |
|---|---|---|---|
| GQ1 | What does a user see as a step's table: only the columns it made, or everything it carries? | depends on the verb (G3) | shown with everything it carries, stored as only what it made. The view decides, not the storage |
| GQ2 | One kind of row identity, a path through the row maps | three kinds (G2) | yes; the saved form (picks, `#` shown) doesn't change, since users see row numbers |
| GQ3 | Is lineage shown on one-to-one steps (`map`, `group`, `select`)? | not shown; `zip_` shows it (G4) | one rule: a step shows `#<input>` when its rows aren't its input's in the same order |
| GQ4 | `group`'s key column takes the step's name | named `group` (G8) | yes, as D9 |
| GQ5 | The row map's eight kinds: enough, and each verb's right? | — | your call; the property tests check each verb against its declared kind (PL2) |
| GQ6 | Is this the order: the row map (P3) before stages, typed saving and incremental runs? | plan.md P-D1 | yes: they all read it |

## 7. The owner's model (2026-11-16), against core

Drawn, with the run behind each figure, in the page *The step table* (an
artifact; its figures are this page's §1–§3 drawn). In the owner's words:

| The owner's model | Against core | |
|---|---|---|
| every step holds a table; `wf["s"]` is its **title** | every pick of it is also a table | matches |
| **column names** are strings, the variables; the **header** is the list of them | numeric names become `var<n>`; never starting with `#` | matches |
| **`#`**, `0…n-1`, is every step's index column, and **divides the table**: reference columns on its left, the data the step produced on its right (owner, 2026-11-16) | it is what users see and type; core also keeps a hidden row identity, so a pick follows its row when a source is edited (rule 10) | matches; the hidden identity stays |
| **`#<previous step>`** columns are stored on every step made from earlier ones | stored for expand, collapse, join, stack; derived for filter, sort, picks; none for map, group, select (G1, G4) | sharper than core: one form. To settle: every ancestor or the parent only; a collapse's list and an expand's `.idx` |
| the `#` cells say how one cell produced another | they give the row; the column comes from the binding in the expression; `k.cell` answers both | sharper, plus the binding |
| **click a cell and know how to reproduce it**: this tool, these literal args, these previous cells (owner, 2026-11-16) | `k.cell` gives the input cells and values for a `map`; not the tool, its hash, the verb, literals or defaults; after a `collapse`, rows without values; for a column argument, the whole column (a bug, plan P1 K-cell) | partly there: a cell's recipe, plan P7r |
| the **grid** is the cells within the table | core says *grid* for the whole table | clearer words: title, header, index columns, grid, cell (for model.md §2) |
| a **cell** holds a value and its state | seven states plus the `stale` mark, and a failed cell's error | matches |
| before a slow run, know what will come back ("numpy arrays in this structure") | the plan knows the rows, the columns and the type name (`ndarray`); every cell `pending`; not the dtype or shape. Rows appearing as they finish: P7d | gap: expected structure |
| a row-wise map passes a grid of cells; modifiers run one function over a grid of arguments | the verb cuts: a row's cells (`map`), a group's lists (`collapse`), the settings' combinations (`sweep`) | matches |
| cells hold Python objects: arrays, images, plots | yes; `k.view` crashes on arrays today (C37, plan P1) | matches, with a bug |
| tables are **tidy**: rows are samples, columns are variables; but what a sample is can change between steps, and the user restructures (owner, 2026-11-16) | each step is tidy on its own terms; the reference columns record each change of sample; one level per step (rule 5) | matches |
| an operation with **several outputs** gives several columns: an RGB image split into `r`, `g`, `b` | a tool returning a `NamedTuple`, `dataclass` or `TypedDict` gives one column per field, planned before the run; a `dict` the same after the run; a tuple stays one cell (run) | matches. Found: `step.plan` shows a re-assigned step's old columns (plan P1, S-plan) |
| **group rows and columns into one cell** | `pack` (a row's columns into a dict), `collapse` with `gather` (a group's rows into lists); a block is both, two steps (run: ward A's cell holds its two patients as dicts) | matches. Gap: a `table` tool's one-value summary must be returned as a DataFrame |
| unpack objects into a new grid to explore them | lists and dicts, one level per step (`expand`, then `widen`); arrays don't: `expand` stops the run and `widen` drops the column silently (plan P1, W-arr) | gap for arrays |

**To decide:** the words (title, header, index columns, grid, cell; `#` as the divider); index
columns stored on every derived step, and how far back; the hidden identity
staying; a cell's expected structure (dtype, shape) before a run; what
unpacking an array means (rows on its first axis, pixels, channels); a cell's recipe as
`k.cell`'s answer (plan P7r); a `table` tool returning one value gives a 1×1 table.
