# Outputs and reshaping

> Proposed 2026-10-26. What a step's output should look like, how a tool that
> returns several values is laid out, how outputs are named, what happens with
> inconsistent data, and how the reshapes fit together. *Today* lines were run
> at `86170a3`. Verb by verb detail is in
> [grid-model.md §4](grid-model.md#4-what-each-verb-does).

## 1. The grid is a tidy table

Decided by the owner, 2026-10-26: **a step's output should be a tidy table
wherever it can be.**

- **Each column is a variable**: one kind of value, one type, one name.
- **Each row is an observation**: one sample, one item, one combination.
- **Each cell is one value** of one variable for one observation.
- **Each step has one kind of observation.** A step's rows are all the same
  kind of thing. When the kind changes (patients → their visits), that is a
  shape verb (`expand`, `collapse`), so the change happens in a step of its
  own.

Core steers towards tidy outputs: a declared record spreads into variables
(§3), a list becomes rows with `expand`, a nested record becomes columns with
`widen`. It doesn't refuse untidy ones, because some are the point:

| Exception | Example | Why it's fine |
|---|---|---|
| an object in a cell | an image, a figure, a model, a document | the object is the value; a cell view shows it |
| several objects from one call | a tool returning a figure and its data table | each object is its own variable: two columns (§3) |
| a wide table on purpose | a pivot, a correlation matrix, from a `table` tool | the developer chose that shape |
| one value | a total, a config dict | a 1×1 grid |
| a list in a cell, before it's expanded | `-> list` under `map` | the next step can `expand` it |

## 2. Output principles

1. **Every output is a grid.** A DataFrame with row ids, typed columns and a
   state per cell. One value is a 1×1 grid. An empty step (no expression
   yet) is a 1×1 grid holding `"empty"`; a result with no rows is a 0×n grid
   that keeps its columns.
2. **One call, one unit of output.** Each call fills the cells of one unit (a
   row, a group, a combination): one cell, or one cell per variable when the
   call returns several (§3).
3. **Shape comes from declarations.** Rows, columns and types follow from the
   verb, its modifiers and the tool's declared types. Where they can't be known
   before running (an `expand`'s row count, an undeclared return), the plan
   says `unknown` and why, and the observed shape is used once it has run
   (K27).
4. **The tool's return type is its contract.** A tool should be a good
   abstraction of what it returns: declare `-> LoHi`, and the step's columns
   are `lo` and `hi` before anything runs.
5. **Nothing is hidden.** One step does one shape change, so every
   intermediate grid can be seen, referenced and traced. Stages group steps
   for running and showing them, and hide none of them.
6. **A step that makes new values outputs only those; a step that keeps the
   observations carries their columns.** `map`, `expand`, `collapse`, `sweep`
   and `table` output only their results (owner, 2026-10-20), and `zip_` puts
   them beside their inputs. `filter`, the reshapes and `group` keep the
   observations and filter or label them, so they carry the columns: `group`
   adds its key as one more column (owner, 2026-10-27; built in phase 4).
   *Proposed:* `expand` without a tool only unpacks lists, so as a reshape
   it carries the other columns ([reshaping.md](reshaping.md) R-D4).
7. **Every column name is chosen, never collided.** Names come from the
   tool's declaration, `mod.name` (§4), or a default (`value`). Two columns
   that would share a name are a problem; nothing silently replaces another
   (C13).
8. **Missing is `None`, types are kept.** A missing value is `None`, and a
   column with gaps keeps its type as nullable (`Int64`, not `float`) (C14).
9. **Every cell knows where it came from.** Its lineage names the input cells
   and arguments that fed it (K28). Cells written by one call share it.
10. **A failure belongs to its call.** If the call raised, every cell it would
    have written fails; if it returned something incomplete, only the cells it
    couldn't fill fail (§5). The row's note says where
    ([grid-model.md §5.2](grid-model.md#52-where-an-error-happened)).

## 3. Tools that return several values

A tool may return several values for one call: a record of named fields, a
fixed-width sequence, a list of items, a table. Decided 2026-10-26: **declared
record types spread into columns automatically**, under an explicit verb or
`auto`. Anything without names stays in one cell unless it is named with
`mod.name` (§4).

| Return | Under `map` (or `auto` resolving to it) | Today |
|---|---|---|
| a scalar (`-> float`) | one column, `value` unless named | as proposed |
| a **record type**: `TypedDict`, `NamedTuple`, dataclass | **one column per field**, typed and ordered as declared | one cell holding the record |
| a sequence, `tuple[int, int]` or `list` | one cell. Spread when named: `mod.name(["lo", "hi"])` | one cell |
| a plain `dict`, or undeclared | one cell. Spread later with `widen` (§6) | one cell |
| `pd.DataFrame` | one cell holding a table, with a warning when declared: a table per row is usually meant for `expand` or `table` | one cell, no warning |

Under the other verbs:

| Verb | A record | A list of records | A DataFrame |
|---|---|---|---|
| `map` | one row, a column per field | one cell (a list) | one cell, with a warning |
| `expand` | — | a row per item, a column per field; ids `"i.j"` | a row per table row, the table's columns; ids `"i.j"` (proposed; *today* refused at run) |
| `collapse` | a row per group: the `by` column, then the fields | — | — |
| `source` | one row | a row per item | the table, as it is |
| `sweep` | a row per combination: the swept settings, then the fields | — | — |
| `table` | — | — | the step's grid |
| `filter` | refused: a filter returns `bool` | | |
| `group` | refused: a key is a scalar | | |

Rules:

- **Field names are the column names,** in declared order, after any `by` or
  swept-setting columns. `mod.name` renames them (§4).
- **One level only.** A field that is itself a record stays one cell; a later
  `widen` spreads it.
- **To keep a record in one cell,** give it one name: `mod.name("bounds")`
  (§4).
- **Lineage:** every field cell of one call maps to the same input cells (K28,
  owner 2026-10-26).

## 4. Naming outputs: `mod.name`

A modifier that names the columns a step writes. It belongs to a new class,
**naming**: it changes no rows and no values, only the names, which are what
later steps bind to. So it is saved and hashed like the others, and written
after the verb, where it wraps each call and labels what the call returns.

| Written | On a single value | On a record | On a sequence |
|---|---|---|---|
| `mod.name("temp_f")` | the column is `temp_f` | the record stays in one cell, column `temp_f` | one cell, column `temp_f` |
| `mod.name(["lo", "hi"])` | a problem: one value, two names | a problem: rename fields with a mapping | **spread** into `lo`, `hi`, by position |
| `mod.name({"lo": "low"})` | a problem | those fields renamed, the rest kept | a problem |
| `mod.name(pattern="{step}_{field}")` | `f_value` | `f_lo`, `f_hi` | needs names first |

```python
bounds[mod.map(), mod.name(pattern="{field}_c")](wf["p"])        # lo_c, hi_c
split[mod.map(), mod.name(["first", "last"])](wf["people"])       # -> tuple[str, str]
fit[mod.sweep(model=["a", "b"]), mod.name("score")]()             # model, score
```

- A **pattern** is a naming convention: `{field}` is the field's name
  (`value` for a single value), `{step}` the step's name, `{tool}` the tool's.
  It can be combined with a list or mapping, which apply first.
- Works on the verbs that write values: `source`, `map`, `expand`, `collapse`,
  `group`, `sweep`, `table` (mapping and pattern only). Not on `filter` or the
  reshapes: they write no new values. To rename a step's columns afterwards,
  `mod.rename` in a later step.
- **Names are checked when declared:** strings, unique, not empty, and not
  starting with `#`, which core keeps for its id columns (`#`, `#v`:
  [reshaping.md](reshaping.md) §5.1). A
  name that isn't a Python identifier (`"temp c"`) is allowed, with a warning
  that it can't bind to a tool's parameter.
- A row whose sequence has the wrong length for its names fails, with the
  note *"returned 3 values for 2 names"*.

**The last naming modifier wins** (owner, 2026-10-27). A step's column names
come from the last modifier in its list that defines them; with none, each
column keeps its default: `value` for a single value, the declared field names
for a record, or the column's own name for verbs that carry columns. So
`to_f[mod.name("a"), mod.map(), mod.name("b")]` writes `b`.

**`mod.name` replaces `name=`** on `map`, `expand`, `collapse`, `group` and
`sweep` (decided 2026-10-27): `name=` on a verb is a problem pointing to
`mod.name`. *Built (phase 4):* a single name, `mod.name("temp_f")`, on every
verb that writes a value column, with the naming checks above. *Next:* the
list, mapping and pattern forms, which come with spreading records (§3).

## 5. Inconsistent data: what each case does

Real data is uneven: fields missing on some rows, types that drift, a few rows
that error. The rule: **the declaration decides the columns; each row is held
to it cell by cell; nothing inconsistent is silent.**

With a declared record type:

| A row… | Its cells | The step |
|---|---|---|
| raises | all `failed`, with the error | `failed` unless handled (`try_except`) |
| returns a record missing a field | that field's cell `failed` (*"missing field 'hi'"*); the rest `known` | `failed` for that row |
| returns an extra field | the extra is dropped | a warning naming the field and how many rows had it |
| returns a field of another type | `known`; the column's type becomes the union | a warning (K27); a problem in strict mode |
| returns `None`, declared `LoHi \| None` | every field `None`, `known` | — |
| returns `None`, declared `LoHi` | all `failed` (*"returned None; declared LoHi"*) | `failed` for that row |
| was `blocked` by an upstream failure | all `blocked` | as for any blocked row |

With no declaration, a returned dict stays in one cell; types are observed
over the rows that ran (failed rows don't count), and a mix is a union. To
make columns of it, `widen` (§6).

`try_except(default=…)` on a record tool takes a record of that type, or
`None` for every field `None`.

## 6. `widen`, precisely

`widen` lifts the fields of a column holding records or sequences into
columns. It is the way to spread a value whose fields weren't declared.

- **Declared fields:** a column whose type is a record type spreads into its
  fields, no settings needed. The plan is exact.
- **Undeclared dicts:** `columns=` names the fields to take. Without it, the
  columns are **every key seen in the rows that ran**, in first-seen order;
  the plan is `unknown` until the input has run. A row without one of those
  keys gets `None` there (missing, not failed, since nothing promised it), and
  the step warns how many rows were missing each key. *Proposed:* that cell
  is `absent`, a state apart from a `null` value, so packing it back is
  lossless ([reshaping.md](reshaping.md) §9.1, J-D1).
- **Sequences:** named by `columns=`, else `c0, c1, …`.
- **A row that isn't a record** fails (*"not a record: str"*); a `None` row
  gives `None` in every column.
- **It replaces the column it spreads,** as `unnest_wider` does. Other columns
  are carried.

*Today:* record types aren't read (a `TypedDict`, dataclass or `NamedTuple`
column needs `columns=`, and a `NamedTuple` is named `c0, c1`); without
`columns=` it raises at run, and the plan says the column is `value`; the
record column is kept beside its fields.

## 7. Reshaping principles

Every shape verb changes a grid along one of two axes, in one direction. Some
call a tool to decide how (`expand`, `collapse`, `sweep`, `table`, `group`); the
**reshapes** (`select`, `drop`, `rename`, `sort`, `slice`, `distinct`, `widen`)
and the **combines** run no tool.

| Axis | Longer / wider | Shorter / narrower | Same size |
|---|---|---|---|
| **rows** | `expand` (one row per item), `stack` (another grid's rows), `sweep` (generated) | `filter`, `slice`, `distinct`, `collapse` (one row, or one per group) | `sort` (reorder) |
| **columns** | `widen` (a cell's fields), `zip_` and `join` (another grid's columns), `group` (a key column) | `select`, `drop` | `rename` |
| **both** | `table`: the tool decides the grid | | |

1. **One change per step.** A step reshapes along one axis once. Chains are
   steps, run together with stages.
2. **The plan is honest.** Each verb has a row rule (`same`, `at most n`,
   `one`, `unknown`, `generated`) and a column rule, so staging can say what's
   known before running.
3. **Kept rows keep their ids; new rows get derived ones** (`"i.j"` from
   parent `i`), so references and lineage survive a reshape
   ([grid-model.md §7](grid-model.md#7-row-ids-per-verb)). *Proposed:* a
   derived id is only a label: the parent is recorded in `#` columns and
   never read from the id ([reshaping.md](reshaping.md) §5.1, R-D6).
4. **Reshapes and combines are cheap and deterministic.** They run no tool, so
   they never fail per row, can't be retried and need no execution modifiers.
5. **The pairs undo each other** where nothing is lost: `expand` ↔ `collapse`
   with `gather`; `widen` ↔ a record-building tool under `map`; `select` ↔
   `zip_`. `filter`, `slice` and `distinct` drop rows on purpose. *Proposed:*
   the conditions that make each pair exact, and `pack` as `widen`'s inverse,
   are in [reshaping.md](reshaping.md) §6, §7.
6. **Reshapes carry columns;** verbs that call a tool don't (§2.6).
7. **Combines are the only way to read several steps** (`join`, `stack`,
   `zip_`), pairing rows by row id (`zip_`, K19) or by a key (`join`).

## 8. Found while checking (to fix in phase 4)

| # | What |
|---|---|
| G8 | a record type returned under `map`, `expand`, `collapse`, `source` or `sweep` isn't spread into its declared fields |
| G9 | `widen` ignores declared record types; `mod.widen()` on a `TypedDict` column passes declaration, plans `['value']`, then raises at run |
| G10 | `widen` keeps the spread column beside its fields |
| G11 | a tool declared `-> pd.DataFrame` under `map` gives no warning; under `expand` it's refused only at run |
| G12 | no `mod.name`; naming is `name=` per verb, one column only |

## 9. Decided

By the owner, 2026-10-26:

1. **`mod.name` is the one way to name outputs;** `name=` on verbs is retired.
2. **An undeclared dict stays in one cell,** under its default column name
   (`value`). `widen` spreads it in a later step.
3. **Kernel-wide naming conventions** exist, as a kernel option (§10).
4. **One grid per step.** A tool that produces objects at different levels
   (a figure of the whole input and a score per row) returns them as one
   record; later steps select the figure or `expand` the scores. Outputs shown
   interactively in the UI (a figure, a chart) are their own steps.
5. **Combines number their rows 0…N-1,** and each cell's lineage points at the
   input cells it came from, in the steps it read
   ([grid-model.md §7](grid-model.md#7-row-ids-per-verb)).

## 10. Kernel-wide naming conventions

A kernel option, saved in the kernel spec (it changes column names, so it is
hashed):

```python
k = Kernel(cat, naming=Naming(pattern="{field}", case="snake"))
```

| Setting | Does |
|---|---|
| `pattern` | the default for steps without `mod.name`: `"{field}"` (today's behaviour), or e.g. `"{step}_{field}"` so every column says which step wrote it |
| `case` | `"snake"`, `"camel"` or `None`. A column name that doesn't follow it is a warning; in strict mode, a problem. Core never renames silently |

A step's own `mod.name` wins over the kernel's pattern. Field names a tool
declares are kept as written, and checked against `case`.
