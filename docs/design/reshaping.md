# Reshaping: from any selection to any cell

> Proposed 2026-10-27, for the owner. Replaces the draft `row-maps.md`, which
> it absorbs. *Today* lines were run at `8efe6fd`; every law in §10 is a test
> in [tests/unit/test_reshape_closure.py](../../tests/unit/test_reshape_closure.py),
> marked `xfail` until it holds. Decided by the owner: the rules in §1, `#`
> columns (§5.1, R-D10), `#` as the row id (R-D11), and that an untouched
> round trip gives back the original ids (R-D3). Everything else is proposed: §12 lists the decisions,
> each with a recommendation.

## 1. The rules

Owner, 2026-10-27:

1. **Data is always in a grid.** Every step's output is a grid. A list or a
   dict in a cell is still a grid (a 1×1 one, or a column of them).
2. **Rows are samples, variables are columns.** This is the tidy table of
   [outputs-and-reshaping.md §1](outputs-and-reshaping.md#1-the-grid-is-a-tidy-table).
   A grid also has `#` columns, which say which rows these are and where they
   came from; they are ids, not variables (§5.1).
3. **A selection can be packed into a cell, and a cell unpacked back into a
   selection, without losing anything**, given valid variables (§10). A
   column becomes a **list**, a row becomes a **dict**.
4. **Reductions and statistics lose values on purpose.** That is what they
   are for. They never lose which rows they reduced.
5. **Every step whose rows aren't its input's rows records where they came
   from.** `join` (many-to-many) is the case that can't work without it: no
   id in its output could say.

Three principles follow, and every section below holds to them:

- **Ids are core's.** Tools never see or set them, and core never parses
  them: `"0.1"` is a label.
- **Provenance is never lost except by a step you can see:** dropping a `#`
  column (§5.1, rule 5).
- **When core can't know, it says so** and falls back to the nearest row it
  does know. It never guesses by position or by the look of an id.

## 2. Shapes

A **selection** is part of a grid, picked with a reference
(`wf["v"][rows[…]][cols[…]]`) or `select`:

| Selection | Size | Its **packed** form: one cell holding |
|---|---|---|
| a cell | 1×1 | itself |
| a column | n×1 | a **list**, in row order |
| a row | 1×m | a **dict**, `{column: value}`, in column order |
| a block | n×m | a **list of dicts** (one dict per row) or a **dict of lists** (one list per column) |

- **Only two packed forms exist: list and dict**, and their nestings. A
  DataFrame in a cell is not a packed form; it stays the exception for a
  `table` tool's result.
- **A packed value is plain:** `[37.0, 38.5, 39.1]`, never `[(0, 37.0), …]`
  or `{0: 37.0, …}`. Tools get plain Python and the value stays JSON. The row
  ids travel beside it, in a `#` column (§5.1).
- **Only variables are packed.** A row's dict holds its variables; its `#`
  columns stay outside it.
- **Each step moves one level along one axis** (the "one change per step"
  principle): rows ↔ list, or columns ↔ dict. A block takes two steps, and
  their order decides which packed form you get (§4).

## 3. The moves

Every reshape is built from these moves. Nothing else changes a grid's shape.

| Move | Axis | Does | Verb | Loses |
|---|---|---|---|---|
| **pack rows** | rows | each column's cells → a list (per group with `by=`) | `collapse` with `gather` | nothing |
| **unpack rows** | rows | a list → one row per item | `expand` | nothing |
| **pack columns** | columns | a row's variables → a dict | `pack` (R-D2) | nothing |
| **unpack columns** | columns | a dict → one column per key | `widen` | nothing |
| **reorder** | rows | change the order | `sort` | nothing |
| **rename** | columns | change the names | `rename` | nothing |
| **place beside** | columns | rows of one origin, side by side | `zip_` | nothing |
| **place below** | rows | one grid's rows after another's | `stack` | nothing |
| **match** | both | rows paired on a key: N–M | `join` | unmatched rows (`how="inner"`) |
| **choose** | either | keep some rows or columns | `filter`, `slice`, `distinct`, `select`, `drop` | what's left out |
| **reduce** | rows | many cells → one value | `collapse` with a reducer (`count`, `total`, …) | the values |
| **compute** | values | one value per row, from a tool | `map`, `group` | the tool decides |
| **make rows** | rows | a tool returns new samples | `expand` with a tool, `sweep`, `source` | — (new data) |
| **opaque** | both | the tool returns a grid | `table` | the tool decides |

The first eight moves are **lossless**: each one has an inverse among them
(§7). `choose`, `reduce`, `compute` and `opaque` can lose values, and `match`
loses only the rows it can't match. None of them loses provenance.

`expand` appears twice: with a tool it **makes rows** (the tool decides the
items); without one (`mod.expand(columns=…)`) it **unpacks** lists already in
the grid.

## 4. Any selection to any cell

**Packing** (selection → cell):

| From | To | Steps | Today |
|---|---|---|---|
| a column | a list | `gather[collapse()]` on that column | ✓ `[37.0, 38.5, 36.9, 39.1]` |
| a column, by group | a list per group | `gather[collapse(by="ward")]` | ✓, but the key is inside each item (R9) |
| a row | a dict | `pack(columns=…)` | a `map` with `identity` gives a dict only when the row has 2 or more columns; with one column it gives the bare value (R3) |
| a block | a list of dicts | `pack`, then `gather[collapse()]` | `gather[collapse()]` on 2 or more columns does it **in one step**, two axes at once (R4) |
| a block | a dict of lists | `gather[collapse()]` (one list per column), then `pack` | not possible: `gather` makes one list (R4) |

**Unpacking** (cell → selection):

| From | To | Steps | Today |
|---|---|---|---|
| a list | a column | `expand` | ✓, but with new ids `"0.j"`, not the ids it was packed from (R1) |
| a dict | a row | `widen` | ✓, but the dict column is kept beside its fields (G10) |
| a list of dicts | a block | `expand`, then `widen` | ✓, with both caveats |
| a dict of lists | a block | `widen`, then `expand(columns=…)` on all the lists together | not possible: `expand` reads one list (R5) |

So **any selection reaches any cell in at most two packs, and any packed cell
reaches its selection in at most two unpacks.** With `choose` to pick the
selection and `zip_` or `stack` to place the result, that is every
cell-to-cell reshape.

## 5. Where each row comes from

**Every step has a row map**: for each output row, the input rows it is made
from. A list keeps values and order but not ids, and a `join`'s ids say
nothing about its inputs, so ids alone can't do this.

| Kind | Each output row comes from | Each input row reaches | Verbs |
|---|---|---|---|
| keeps ids | 1 input row, the same id | 1 | `map`, `group`, `widen`, `pack`, `sort`, `rename`, `select`/`drop` of columns, `zip_` |
| choose | 1 input row, the same id | 0 or 1 | `filter`, `slice`, row `select` |
| `distinct` | the rows it stands for (it keeps the first's id) | 1 | `distinct` |
| unpack, make rows | 1 input row (its parent) | 0…n | `expand` |
| pack, reduce | a group of input rows, in order | 1 | `collapse` |
| N–M | 1 row of each side | 0…n | `join` |
| below | 1 row of one input | 1 | `stack` |
| generated | none | — | `source`, `sweep`, a value |
| opaque | the whole input | all | `table` |

For steps that keep ids the map is the identity: the row id is the trace.
For every other step, the map is written into the grid as `#` columns.

### 5.1 `#` columns

Owner, 2026-10-27. **A grid has two kinds of column: `#` columns (ids) and
variables (data).** Both are grid columns: shown, saved and hashed.

| Column | Holds | Written by |
|---|---|---|
| `#` | this row's id (the index, shown) | core, for every grid |
| `#v`, `#w`, … | the row of direct input `v` (`w`, …) each row came from: one id, or a list of ids | core, for steps whose rows aren't their input's rows |

```
join(v, w, on="ward")                 total[collapse(by="ward")](vt)
#  #v  #w  name ward temp head         #  #vt        ward  temp
0  0   0   Ada  A    37.0 Dr X         A  [0, 1, 3]  A     114.6
1  1   0   Ada  A    38.5 Dr X         B  [2]        B     36.9
2  2   1   Ben  B    36.9 Dr Y
3  3   0   Cy   A    39.1 Dr X
```

| Step | Writes |
|---|---|
| keeps ids, choose | nothing new; carries the `#` columns it has |
| `expand` that makes new rows | `#v`: the parent row |
| `expand` that restores ids (§6) | `#v`: the parent row (the group); `#` gets the restored ids |
| `collapse`, any reducer | `#v`: a list of the group's rows, in the order they were reduced |
| `distinct` | `#v`: a list of the rows each kept row stands for |
| `join` | `#v` and `#w`: one row of each side; the unmatched side of an outer join is `None` |
| `stack` | `#a` and `#b`: one of them, `None` on the other |
| `table` | nothing: it traces to the whole input |
| `source`, `sweep`, a value | nothing: generated |

**Five rules keep them out of the way of references:**

1. **Positions count variables only.** `cols[0]` is the first variable, with
   or without `#` columns, so saved selections keep their meaning.
2. **Tools get variables only.** `**kwargs`, `identity`'s row and a `table`
   tool's DataFrame leave `#` columns out; a parameter can't be named `#v`;
   and a `#` column given as an argument is a problem
   (*"'#v' holds row ids; copy it into a variable with rename first"*).
3. **"All columns" means all variables:** `widen()`, `pack()`,
   `expect(columns=…)`, the naming checks. A `select(columns=[…])` keeps the
   `#` columns unless they're dropped.
4. **Combines merge `#` columns, never collide them.** Inputs of one origin
   have the same `#` columns, so `zip_` keeps one of each. `join` and `stack`
   write a `#` column per direct input. A step read twice (a self-join,
   `stack(a, a)`) gets `#a_1` and `#a_2`.
5. **Dropping `#v` is a loss you choose.** `drop(columns=["#v"])` is allowed:
   after it, lineage stops there (*"provenance dropped at 'x'"*), `by="#v"`
   further on is a problem at declaration, and staleness falls back to the
   whole step. `rename` of `#v` → `visit_id` turns it into a variable, with
   the same effect. This is the only way provenance is lost.

And:

- **`#` can't be dropped.** Every grid has row ids. Renumbering rows `0…n-1`
  makes a new origin, so it is never a `drop`: if it's wanted, it's a step of
  its own.
- **`#` is the row id, not the row number** (R-D11, decided). The row number is the
  position on screen and has no name; slices (`[0:2]`) already work by
  position. *Today* `#` is a reserved column of row **numbers**: `cols["#"]`
  selects it, and after a sort it stores the positions `[0, 1, 2]` as data
  while the ids are `[1, 2, 0]` (R8). `cols[0]` already skips it, which is
  rule 1.
- **Named by the step's name**, which is its id in core, never by its
  position (`insert` and `move` shift positions). The saved form stores `#v`
  as a reference to step `v`, so `k.rename` relabels it.
- **The hash covers the ids, not the labels.** A row whose source changed
  makes later steps stale even when its values didn't, and renaming a step
  doesn't. Every saved version changes once, with the saved-format bump.
- **One per direct input, never one per column.** Ids label rows. A cell's
  input cells are its row's input rows plus the columns its call read, which
  the formula says. Further back is reached by following the `#` columns
  step by step.

### 5.2 Reductions and statistics

A reduction (`count`, `total`, a mean, any reducer under `collapse`) loses the
values on purpose. **Its `#v` lists the rows it reduced.**

**Built-in reducers reduce each variable separately, under its own name**
(R-D1): `total[collapse(by="ward")](vt)` gives `ward` (the key) and `temp`
(its total). The `by` key is never part of what they reduce. A reducer
written as a tool, `(acc, temp) -> float`, gives one result: `value`, or what
`mod.name` calls it.

| Question | Answer |
|---|---|
| the row's `#` | `0` with no `by`; the key with `by="ward"` (D3); `s`'s id with `by="#s"` (§7.1) |
| its `#v` | the group's rows, in the order the reducer saw them (which matters for `first`, `last`, `gather`) |
| a statistic's lineage | the rows in `#v`, restricted to the columns the reducer read |
| an input row changes | only the groups whose `#v` holds it go stale; a row that changes group marks both; a new group marks the whole step (D3) |
| a group holds a failed row | the group's cells are `blocked`, naming the row. Core never skips it: to leave failed rows out, `filter` them first, as a step you can see. *Today:* ✓ |
| a group with no rows (`collapse()` over no rows, or an empty group from `by="#s"`) | the reducer's empty value: `count` 0, `total` 0, `gather` `[]`. A reducer with no empty value (`first`, a mean) gives `absent` (§9.1). *Fixed* 2026-10-27 for `count`, `total` and `gather` (R6); `first` and `last` give `None` until `absent` exists |
| several statistics at once | a reducer returning a record (`n`, `mean`, `sd`): a column per field, one shared `#v` |
| going back | `trace`, never `rebuild` (§7) |

**Putting a statistic back beside its rows.** Each row of `vt` is in exactly
one group, so unpacking a reduction's `#vt` gives one row per row of `vt`,
with `vt`'s ids and origin (§6), each carrying its group's statistic. That
lines up with `v` again: "each row against its group's total" needs no new
verb.

```python
k["vt"] = mod.select(columns=["ward", "temp"])(wf["v"])
k["tot"] = op("total")[mod.collapse(by="ward")](wf["vt"])   # #: A, B · #vt: [0, 1, 3], [2]
k["each"] = mod.expand(columns=["#vt"])(wf["tot"])          # #: 0, 1, 3, 2 · #tot: A, A, A, B
k["names"] = mod.select(columns=["name"])(wf["v"])
k["side"] = zip_(wf["names"], wf["each"])                   # each visit beside its ward's total
```

A row-wise statistic (`map` over several columns of one row) keeps ids: no
`#v`, and its lineage is the columns it read. A statistic from a `table` tool
(`df.describe()`) is opaque: to keep the rows behind each number, use
`collapse`.

## 6. Origins: when two rows are the same sample

A row id means "the same sample" only among steps that got their ids from the
same place. The step that decided which samples the rows are is their
**origin**. Each step's origin follows from its verbs:

| Origin | Steps |
|---|---|
| **its input's** | the steps that keep ids, choose, and `distinct` (§5) |
| **`s`'s** | `collapse(by="#s")` (§7.1); an `expand` that restores ids (below) |
| **a child of its input's** | every other `expand`: its rows know their parent through `#v` |
| **its own** | `source`, a value, `sweep`, any other `collapse`, `join`, `stack`, `table` |

- **Rows pair by id only within one origin.** `zip_`, a column argument and
  the table view check the origin first. A child origin pairs with its
  parent, through the child's `#v`: each child row beside its parent row, as
  `zip_` does today. Any other mix is refused, pointing to `join`.
- **The origin is known when a step is declared.** So pairing across origins
  is a problem at declaration, not a failure at run. Only differences in
  which ids are present (rows a `filter` dropped) wait until the step runs.

**Unpacking what core packed gives back the same samples** (R-D3, owner
2026-10-27). `expand` restores ids when the list it unpacks was **written by
core**, either:

- a column written by `gather` that reached here through steps that call no
  tool on it (reshapes, `zip_`, `filter` on another column, a selection), or
- a `#s` list itself (§5.2).

Then the lists are unpacked together with the `#s` list beside them: each
item gets back the id it was packed from, the step takes `s`'s origin, and
`#v` holds the group each item came from. `expand(gather(v))` is `v`'s rows,
and pairs with `v`.

**Any other list gets new ids.** A list a tool wrote (`readings`, a `map` that
sorts a gathered list) is new to core, whatever it holds: its items get child
ids `"i.j"`, a child origin, and `#v` holds the parent row. A `#s` list
carried beside a list a tool rewrote is not unpacked with it: it no longer
says which item is which. It stays a list on each item, which is true: each
item came from that whole group. Which case applies is decided from the
verbs, so the plan knows before anything runs.

## 7. Going back: rebuild or trace

Every step's plan says how to go back from its output to its input. The verb
decides which, never the data:

| Inverse | Means | Steps |
|---|---|---|
| **rebuild** | the input can be computed from this output alone; the plan writes the inverse step | `sort`, `rename`, `pack` ↔ `widen`, `gather` ↔ an `expand` that restores ids, `zip_` → `select` per input, `stack` → `first[collapse(by="#a")]` per input, `join(how="outer")` → `first[collapse(by="#a")]` per side |
| **trace** | the values are lost here, but the `#` columns (or, for steps that keep ids, the ids) lead to the exact input rows, which are still in the workflow | `filter`, `slice`, `distinct`, `select`/`drop`, `join(how="inner")`, reductions, every tool call (`map`, `group`, `expand` with a tool, `sweep`) |
| **opaque** | the trace leads to the whole input | `table` |

Every intermediate grid is kept ("nothing is hidden"), so "lossy" only means
that a step's output alone can't rebuild its input. Going back works for
every step: **rebuild** when the verb allows it, **trace** otherwise. The one
exception is a `#` column you dropped (§5.1, rule 5): the trace stops there,
and the plan says so.

### 7.1 Back to an earlier step: `by="#s"`

`collapse(by="#s")` **groups each row by the row of step `s` it traces to.**
`s` is any earlier step. Core follows the `#` columns back to it, so `s`
needn't be the direct input.

- **The result has a row for every row of `s`**, with `s`'s ids and origin,
  so it pairs with `s` again. A row of `s` that nothing traces to gets an
  empty group (`[]` under `gather`), so the round trip keeps it (J-D5).
- **Naming the step picks the rows.** After `f = filter(v)` and
  `e = expand(f)`, `by="#f"` gives a row per row of `f`, and `by="#v"` a row
  per row of `v`: rows of `v` that `f` dropped get empty groups. The ids are
  the same; the row set is the named step's.
- **Each row must trace to at most one row of `s`.** That is known from the
  verbs: there's no `collapse` or `distinct` between `s` and here, and `s` is
  on one side of any `join`. Otherwise it's a problem at declaration:
  *"rows of 'c' come from several rows of 'v'; group by '#v' isn't defined"*.
- **Rows that trace to no row of `s` are left out**, and the plan says how
  many: the other input of a `stack`, the unmatched side of an outer `join`.
  That is what makes `first[collapse(by="#a")]` the inverse of
  `stack(a, b)`.
- `by="#s"` is a grouping key only. A tool never sees a row id.

```python
k["e"] = readings[mod.expand()](wf["v"])                     # 8 readings, 2 per visit
k["back"] = op("gather")[mod.collapse(by="#v")](wf["e"])     # 4 rows: v's ids 0…3
k["side"] = zip_(wf["v"], wf["back"])                        # each visit beside its readings

k["j"] = join(wf["v"], wf["w"], on="ward", how="left")       # N–M
k["per_visit"] = op("first")[mod.collapse(by="#v")](wf["j"])  # v's rows again
```

## 8. The open questions, answered

### 8.1 How do I know the inverse, when it can be known?

**By construction, from the verbs, at declaration.** The plan of every step
carries `inverse: rebuild | trace | opaque`, and for `rebuild` the inverse
step's formula, so the app can offer "undo this reshape" as a new step. Core
never infers invertibility from the data: a `map` whose tool happens to be
one-to-one on today's data is still `trace`.

A tool is opaque to core. If tools ever declare their own inverse
(`@tool(inverse=to_c)`), the declaration is recorded and hashed, and staging
checks it by a round trip on the rows it ran. Not proposed now: nothing needs
it yet.

### 8.2 What if the inverse can't be known, by definition?

| Case | Example | What core does |
|---|---|---|
| a tool rewrote a packed value | `gather` → `map(sorted)` → `expand` | new child ids `"i.j"`; each item traces to its whole group, and the plan says why: *"items of 's' were rewritten by sorted; which sample each is isn't known"* (§6) |
| a tool made the rows | `readings[expand()]`, `sweep`, `source` | new samples: a child origin tracing to the parent row, or a new origin for generated rows |
| a tool made the grid | `table` | `opaque`: traces to the whole input, and is always its own origin, whatever index the tool returns |

Each is the principle of §1: **when core can't know, it says so and falls
back to the nearest row it does know.**

## 9. Uneven data: jagged JSON

Real JSON is uneven: lists of different lengths, keys some records lack,
`null`s, a field that is a list in one record and a string in the next, keys
that are data. The rule is the one from
[outputs-and-reshaping.md §5](outputs-and-reshaping.md#5-inconsistent-data-what-each-case-does):
**nothing inconsistent is silent, and core never normalises data for you.**
Every choice that loses something is a step you can see.

### 9.1 Three things that look alike

No unpack is lossless unless these stay apart:

| In the JSON | Means | In the grid | Packs back to |
|---|---|---|---|
| `"x": null` | a value: nothing | `None`, state `known` | `"x": null` |
| no `"x"` key | not there | `None`, cell state **`absent`** (J-D1) | no key |
| `"tags": []` | a list with no items | no rows; `collapse(by="#s")` still gives its record a row, with `[]` | `[]` |

`absent` is a new cell state: *known to be not there*. It isn't a problem, so
it doesn't make a row `failed`.

- A tool given an absent cell gets **the parameter's default** if it has one,
  else `None`, as a Python call does for a missing argument.
- `pack` leaves absent cells out of the dict, so `pack(widen(d)) = d`.
- A list has no way to say "absent", so `gather` packs an absent cell as
  `None`, with a warning counting them (V9).

### 9.2 Each kind of unevenness

| Uneven | Example | Rule |
|---|---|---|
| list lengths | `["a", "b"]`, `[]`, `["d"]` | fine: `expand` gives 0…n rows each, and `collapse(by="#s")` packs them back, `[]` included |
| keys | `{"x": 1, "y": 2}`, `{"x": 3}` | `widen` takes the union of keys in first-seen order, or `columns=`. A key a row lacks is `absent`, not failed. Types are kept (`Int64`, not `float`, C14) |
| `null` where a list belongs | `"meta": null` | `expand` gives no rows, with a warning counting them, and packs back to `[]` (V7): the one loss, and it's said |
| kind of value | `"tags": "c"` here, `["c"]` there | **not normalised:** under `expand` that row fails, *"not a list: str"*, and the others run. To accept it, say so with a step: the built-in tool `as_list` (`x` → `[x]`, `None` → `[]`) under `map`, so the loss is visible and traced |
| keys that are data | `{"2026-01": 3, "2026-02": 4}` | a **mapping**, not a record: `expand` it into one row per key, with columns `key` and `value` (J-D4). `widen` warns when its keys look like data: more keys than rows, or most keys in only one row |
| depth | `{"z": {"deep": true}}` | one level per step: the nested dict stays a cell, and another `widen` spreads it. Depth that varies from row to row is a "kind of value" difference |
| broken JSON | `'{"id": '` | parsing is a tool (`json.loads` under `map`), so that row fails and the others run. `try_except` lets it through |

**The verb says what a dict is.** `widen` treats it as a record (keys are
variables → columns); `expand` treats it as a mapping (keys are data → rows).

### 9.3 Declaring the shape

Undeclared, the columns are `unknown` until the step runs, then they're what
was seen (K27). A declaration makes the plan exact, and Python's typing
already tells absent apart from null:

```python
class Meta(TypedDict):
    x: int | None             # always there, may be null
    y: NotRequired[int]       # may be absent
    z: NotRequired[dict]      # stays one cell; widen it later
```

A required key that's missing fails that row (*"missing field 'x'"*). An extra
key is dropped with a warning naming it. To keep every key, don't declare:
`widen` takes the union. In strict mode the warnings are problems.

### 9.4 A recipe for any JSON column

```python
k["p"] = parse_json[mod.map()](wf["raw"])                   # str → dict; bad JSON fails its row
k["rec"] = mod.widen()(wf["p"])                             # union of keys; missing → absent
k["tl"] = as_list[mod.map(), mod.name("tags")](wf["rec"])   # only if a bare "c" means ["c"]
k["tag"] = mod.expand(columns=["tags"])(wf["tl"])           # 0…n rows per record; #tl
k["score"] = mod.expand(columns=["scores"])(wf["rec"])      # a mapping: key, value rows; #rec
k["back"] = gather[mod.collapse(by="#rec")](wf["tag"])      # one row per record, [] kept
```

Each step moves one level, every loss is a step of its own, and every row
traces to its record: `#tl` holds `tl`'s ids, which are `rec`'s, so
`by="#rec"` follows it back.

## 10. Closure: the laws

**Assuming the variables are valid**, the moves are closed: every move takes
grids to a grid, every `rebuild` move has its inverse among the moves, and
every other move has a trace. "Valid" means:

| | Validity condition | Broken: what happens |
|---|---|---|
| V1 | a column `expand` unpacks holds lists or dicts | the row fails: *"not a list: str"* |
| V2 | lists unpacked together have the same length in each row | the row fails: *"name has 3 items, temp has 2"* |
| V3 | dict keys are valid, unique column names | a problem, as for `mod.name` |
| V4 | row ids are unique in a step | the step fails, naming the id |
| V5 | each column has one type (nullable) | a warning (K27) |
| V6 | `by=` keys are hashable scalars | the row fails |
| V7 | a list cell is never `None`, or the loss is accepted | `None` unpacks to no rows and packs back to `[]`, with a warning |
| V8 | a column `expand` unpacks holds one kind of value, not a mix with scalars | the row fails, as V1; `as_list` accepts it, as a step |
| V9 | a column `gather` packs has no `absent` cells, or the loss is accepted | absent packs as `None`, with a warning |

Each law is a test in `tests/unit/test_reshape_closure.py`, comparing data,
row ids and (once origins exist) pairing.

| Law | Statement | Today |
|---|---|---|
| L1 | unpack(pack(column)) = the column: same values, ids, origin | values ✓; ids ✗ (`"0.j"`, R1) |
| L2 | pack(unpack(list)) = the list | ✓ |
| L3 | widen(pack(row)) = the row | ✗ (no `pack`; `widen` keeps the dict column) |
| L4 | block → list of dicts → block | values ✓ (with `identity` packing the row), ids ✗ |
| L5 | block → dict of lists → block | ✗ (R4, R5) |
| L6 | unpack(pack by group) = the rows, ids kept | values ✓, ids ✗ (`"A.0"`) |
| L7 | `expand` → `collapse(by="#v", gather)` = one list per `v` row, pairs with `v` | ✗ (M1): there is no `#v` column; the step ends `invalid` |
| L8 | sort is a permutation: same ids, same rows | ✓ |
| L9 | rename then rename back = the grid | ✓ |
| L10 | `zip_` of two `select`s of `v` = `v` | ✓ |
| L11 | `filter` and `sort` commute | ✓ |
| L12 | `stack(a, b)` → `first[collapse(by="#a")]` = `a` | ✗ |
| L13 | `join` → `first[collapse(by="#v")]` = `v`'s rows, pairs with `v` | ✗ (M4) |
| L14 | a `collapse` cell traces to exactly its group's rows | ✓ (from the row's note), read by id: `k.cell("c", "A")` (M7, fixed) |
| L15 | a `join` cell traces to its pair of input rows | ✗ (M4) |
| L16 | `zip_` across origins is refused at declaration | ✗: completes, wrong (M5, M9) |
| L17 | ids are never parsed: a source with ids `a`, `a.1`, expanded, traces each row to its true parent | ✗ (M8) |
| L18 | packing zero rows gives `[]`; unpacking `[]` gives a 0×n grid with its columns | ✓ (R6, fixed) |
| L19 | `distinct` traces each kept row to every row it stands for | ✗ (M3) |
| L20 | `table` is its own origin: its rows don't pair with its input's | ✗ (M6) |
| L21 | the plan says `inverse: rebuild`, `trace` or `opaque` | ✗ (R-D8) |
| L22 | jagged lists round-trip: `expand` → `collapse(by="#r", gather)` gives each list back, `[]` included | ✗ (J3) |
| L23 | `widen` of uneven dicts: the union of keys; a missing key is `absent`, not failed; ints stay ints | ✗ (J4) |
| L24 | `pack(widen(d))` = `d` for uneven dicts: absent keys left out, `null` kept | ✗ (J4, R-D2) |
| L25 | `expand` doesn't normalise: a bare string fails its row, the others run | ✗ (J1) |
| L26 | `expand` of a mapping gives `key`, `value` rows | ✗ (J5) |
| L27 | `expand` of `None` gives no rows | ✗ (J2) |
| L28 | positions count variables only: `cols[0]` is the first variable beside `#v` | ✗ (no `#` columns yet) |
| L29 | tools get variables only: a `**kwargs` tool sees no `#` column | ✗ (no `#` columns yet) |
| L30 | `zip_` of two steps of one origin keeps one `#v` | ✗ |
| L31 | after `drop(columns=["#v"])`, `by="#v"` is a problem at declaration | ✗ (no `#v` column yet) |
| L32 | a reduction's `#v` lists its group's rows | ✗ (kept in the row's note, not a column; and R9) |
| L33 | unpacking a reduction's `#vt` puts each row beside its group's statistic, lined up with `v` | ✗ |
| L34 | reducers over no rows give their empty value: `count` 0, `total` 0, `gather` `[]` | ✓ (R6, fixed) |
| L35 | a group holding a failed row is `blocked` | ✓ |

## 11. Found while checking

Run at `8efe6fd`. M1–M7 come from the `row-maps.md` draft; the rest are new.

| # | What |
|---|---|
| M1 | `expand` → `collapse` doesn't round-trip per parent: there's nothing to group by |
| M2 | *Corrected from the draft:* `collapse(by=…)` **does** record its group's rows (in the row's note, `unit`), and `k.cell` shows them (`rows [0, 1, 3]`). D3's per-group staleness doesn't use them yet |
| M3 | `distinct` traces a kept row only to itself |
| M4 | `join` and `stack` trace to whole steps: *"join doesn't keep row links yet"* |
| M5 | `zip_(v, select(join(w, v)))` completes with **Ben beside Dr X**: counted ids pair by accident |
| M6 | `table` keeps the tool's index, so its rows claim to be the input's rows |
| M7 | *Fixed 2026-10-27:* `k.cell` took a position, so `k.cell("c", "A")` and `k.cell("e", "0.1")` raised `TypeError`. It now takes a row id, as selections do; `Workflow.cell`, which takes a screen position, is unchanged |
| **M8** | **Lineage parses id strings.** Source ids `a`, `a.1`, then `expand`: output row `a.1` (item 1 of `a`, value `p1`) traces to source row `a.1` (`q`). A wrong answer, given silently |
| **M9** | **`zip_` parses id strings.** `zip_(v, expand(gather(v)))` completes and puts **all four unpacked rows beside `v`'s row 0** (Ada, 37.0): `"0.j"` is read as "child of `v`'s row 0", though its parent is the `collapse`'s row 0. A wrong answer, given silently |
| R1 | unpacking a gathered list gives new ids (`"0.j"`, `"A.j"`), not the ids it was packed from |
| R2 | no way to pack a row whatever its width (`pack`) |
| R3 | `identity` under `map` packs a row into a dict only when it has 2 or more columns; the shape of the result depends on how wide the input is |
| R4 | `gather` on 2 or more columns packs both axes in one step (a list of dicts), against "one change per step"; there's no way to get a dict of lists |
| R5 | `expand` unpacks one list; several lists can't be unpacked together |
| R6 | *Fixed 2026-10-27:* every reducer gave `None` over no rows: `gather` (not `[]`), `total` (not 0) and **`count` (not 0)**, a wrong answer given silently. Each built-in reducer now starts from its empty value |
| R7 | *Corrected:* not a bug. `collapse(by="nosuch")` is refused at declaration once the input's columns are known (*"collapse groups by 'nosuch', which 'v' does not have"*); before then, the step ends `invalid` with that message when it runs |
| R8 | `cols["#"]` stores row **numbers** as data: after a sort, `[0, 1, 2]` while the ids are `[1, 2, 0]`. A value that changes when an earlier step reorders: the position pairing K19 retired (tested in test_008_asks: `{"#": [0, 1, 2, 3]}`) |
| R9 | under `collapse(by=…)`, the built-in reducers get **the key in each row's payload**: `gather` gives dicts holding `ward`, and `total[collapse(by="ward")]` on `(ward, temp)` fails, *"unsupported operand type(s) for +: 'int' and 'dict'"* |
| J1 | `expand` wraps a bare string: `"c"` gives one row `c`, so `"c"` and `["c"]` can't be told apart afterwards |
| J2 | `expand` of `None` gives one row holding `None`, the same as `[None]` |
| J3 | `expand` of `[]` gives no rows, and nothing can bring the parent back with `[]` (M1) |
| J4 | `widen(columns=["x", "y", "z"])` fails every row missing a key (`KeyError: the record has no 'z'`), against outputs-and-reshaping §6 (missing → `None`); ints become floats (`NaN`, C14); `null` and a missing key both become `NaN` |
| J5 | `expand` of a dict gives one row holding the whole dict, not a row per key |

## 12. Decisions for the owner

Each is one small piece, confirmed before it lands.

| | Decision | Recommended | Fixes |
|---|---|---|---|
| R-D1 | **Built-in reducers reduce each variable separately, under its own name; the `by` key is never in what they reduce.** `gather[collapse()]` on m columns gives one row of m lists, not a list of dicts | yes. It changes today's output for grids with 2 or more columns | R4, R9 |
| R-D2 | **`mod.pack(columns=…)`**: packs a row's variables into a dict, whatever its width. `widen` is its inverse and drops the dict column (G10) | yes; the name is open (`pack` follows tidyr) | R2, R3 |
| R-D3 | **An `expand` of a list core wrote restores its ids and origin** (§6); every other list gets child ids | **decided**, 2026-10-27 | R1, L1, L4, L6 |
| R-D4 | **`expand(columns=[…])`** unpacks several lists together (V2). As a reshape (no tool) it **carries the other columns**, repeated per item | yes. It refines the 2026-10-20 decision for the tool-less form only | R5, L5 |
| R-D5 | **`collapse(by="#s")`** groups by the row of any earlier step `s` (§7.1); the output has `s`'s ids and origin | yes | M1, L7, L12, L13 |
| R-D6 | **Core never parses ids:** lineage, `zip_`'s parent pairing and staleness read only the `#` columns, and `_ancestors` goes | yes, **first**: M8 and M9 are wrong answers given silently | M8, M9, L17 |
| R-D7 | **Rows pair by id only within one origin (or child to parent, through `#v`), checked at declaration** | yes | M5, M9, L16 |
| R-D8 | **The plan says `inverse: rebuild \| trace \| opaque`**, with the inverse formula for `rebuild` | yes | §8.1, L21 |
| R-D9 | `distinct` records the rows it stands for; `table` is always its own origin | yes | M3, M6, L19, L20 |
| R-D10 | **`#` columns are grid columns** (§5.1) under the five rules | **decided**, 2026-10-27 | M2, M4, L28–L31 |
| R-D11 | **`#` names the row id; the row number has no name.** `cols["#"]` then selects ids, not positions: a change to a tested behaviour (test_008_asks). grid-model §2, object-model §1, step-expressions §2, kernel-session, interactive-sessions and row-ids §1 say so | **decided**, 2026-10-27 | R8 |
| R-D12 | **Reductions** (§5.2): `#v` lists the group's rows; over no rows, the reducer's empty value (`count` 0, `total` 0, `gather` `[]`, else `absent`); a group with a failed row stays `blocked` | yes | R6, L32–L35 |
| J-D1 | **A cell state `absent`**: a key that wasn't there. Tools get the parameter's default, else `None`; `pack` leaves it out; `gather` packs it as `None`, with a warning | yes | J4, L23, L24 |
| J-D2 | **`widen` takes the union of keys** (or `columns=`); missing is `absent`, never failed; types kept | yes: it builds what outputs-and-reshaping §6 already says | J4, L23 |
| J-D3 | **`expand` never normalises:** a non-list fails its row; `None` gives no rows, with a warning; a built-in `as_list` tool accepts them on purpose | yes. It changes today's output for bare strings and `None` | J1, J2, L25, L27 |
| J-D4 | **`expand` of a dict gives `key`, `value` rows**; its inverse is `collapse(by="#s")` with a built-in reducer that builds a dict (name open: `gather_dict`) | yes | J5, L26 |
| J-D5 | **`collapse(by="#s")` gives a row for every row of `s`**, an empty group for a row nothing traces to | yes | J3, L22 |

**New words**, for object-model.md §1 if accepted: *packed form*, *pack*,
*row map*, *`#` column*, *origin*, *rebuild*, *trace*, *absent*, *mapping*
(a dict whose keys are data).

### Order, once decided

1. ~~Fixes: M7 (`k.cell` takes a row id), R6 (empty values over no rows).~~
   Done 2026-10-27. (R7 turned out not to be a bug.)
2. R-D6, R-D10 and R-D11 for the steps that keep ids and for `expand`: `#`
   and `#v` columns, and `_ancestors` goes. Fixes M8 and M9.
3. R-D7: origins, and pairing checked at declaration. Fixes M5.
4. R-D10 for `collapse`, `distinct`, `join` and `stack`, with R-D12; then
   D3's per-group staleness.
5. R-D1, then R-D3, R-D5 and J-D5: lossless round trips.
6. R-D2 and R-D4: the missing moves.
7. R-D8 and R-D9.
8. J-D1 and J-D2 (`absent`, `widen`'s union), then J-D3 and J-D4.
