# Reshaping: the rules and the laws

> The ten rules on one page are [rules.md](rules.md); this is the detail behind
> them. What a user of core needs to know to reshape data and trust the result. This
> describes the system as designed, closed and airtight; how far today's core
> is from it is in reshaping-plan.md. The rules are the owner's (2026-10-27);
> the laws are tests, in
> [tests/unit/test_reshape_closure.py](../../tests/unit/test_reshape_closure.py).
> What is built, what is left and in what order is in
> [reshaping-plan.md](reshaping-plan.md). The words are in
> [object-model.md §1](object-model.md#1-the-words).

## 1. The model

**Every step's output is a grid.** A grid has rows and two kinds of columns:

| Column | Is | Written by |
|---|---|---|
| **variables** | the data: one kind of value per column, one sample per row | your tools, and the verbs |
| **`#`** | each row's id: a stable label that follows the row through sorts and filters | core |
| **`#v`, `#w`, …** | the row of step `v` (`w`, …) each row came from: one id, or a list of ids | core, for steps whose rows aren't their input's rows |

Rows are samples and variables are columns: the tidy table of
[outputs-and-reshaping.md §1](outputs-and-reshaping.md#1-the-grid-is-a-tidy-table).
A list or a dict in a cell is still a grid. The `#` columns are ids, not
data, and §2 says what core promises about them.

```
join(v, w, on="ward")                    total[collapse(by="ward")](vt)
#  #v  #w  name ward temp head            #  #vt        ward  temp
0  0   0   Ada  A    37.0 Dr X            A  [0, 1, 3]  A     114.6
1  1   0   Ada  A    38.5 Dr X            B  [2]        B     36.9
2  2   1   Ben  B    36.9 Dr Y
3  3   0   Cy   A    39.1 Dr X
```

## 2. The five guarantees

Everything else in this document follows from these. Each one is checked by
the laws in §10.

1. **Ids are core's.** Your tools see variables only: never a `#` column, not
   through `**kwargs`, not in a `table` tool's DataFrame. Only core writes `#`
   columns. Column positions (`cols[0]`) and "all columns" count variables
   only.
2. **Every row knows where it came from.** Its `#` columns name the exact
   input rows it was made from. Clicking a cell, "what goes stale", and
   "undo" all follow those columns back, and nothing else: core never reads
   meaning out of how an id looks, and never pairs by position.
3. **Rows line up only when core recorded how they match**, so that every
   row has exactly one partner: the same row, or a row and the one it came
   from (§6). `zip_`, a column argument and the table view check this.
   Anything else is refused, pointing to `join`, or to
   `zip_(…, match_ids=True)` when you know two grids' ids mean the same
   samples.
4. **The shape is known from the verbs.** Each step moves one level along one
   axis. Its plan says the rows and columns (`#` columns included) before it
   runs, and a result that breaks the plan fails loudly.
5. **Nothing is lost silently.** The lossless moves can be undone. A step
   that loses values (a filter, a statistic) still traces to the rows it
   used. The only ways to lose provenance are steps you write: dropping a
   `#v` column, or renaming it into a variable.

### 2.1 Airtight, precisely

The guarantees, as checks that hold for **every step `S` of every workflow
over valid variables** (§10). They are what the invariant check (L39) asserts
after each step runs, and what the property test (L40) asserts on generated
workflows.

| | Check | Guarantee |
|---|---|---|
| A1 | `S`'s row ids are unique, and keep their type (`1` is not `"1"`) | 2 |
| A2 | no tool `S` called was given a `#` column; no tool set `S`'s ids, except a source's or a `table`'s, which are then their own origin | 1 |
| A3 | every value in a `#v` column of `S` (or every item, for a list) is a row id of step `v`; `None` only where §5 allows it (the other side of a `stack`, the unmatched side of an outer `join`) | 2 |
| A4 | if `S` keeps ids, each of its ids is one of its input's | 2 |
| A5 | where `S` puts rows of two grids in one row (`zip_`, a column argument), each row has exactly one partner, through a link core recorded (one origin, or `#` columns), or the step says `match_ids=True` | 3 |
| A6 | where `S`'s plan was exact, `S`'s variables, `#` columns and row count are the plan's | 4 |
| A7 | every value `S` lost is the "Loses" column of its move (§3); every trace that stops at `S` is a `#` column `S` dropped or renamed | 5 |
| A8 | where `S`'s inverse is `rebuild`, running the inverse on `S`'s output gives `S`'s input back | 5 |

**Airtight means A1–A8 hold for every step of every workflow whose variables
are valid.** Nothing else is promised, and nothing less is accepted: a step
that would break one of them fails or is refused, with the reason.

## 3. The moves

Every reshape is built from these. Nothing else changes a grid's shape.

| Move | Does | Verb | Loses |
|---|---|---|---|
| **pack rows** | each column's cells → a list (per group with `by=`) | `collapse` with `gather` | nothing |
| **unpack rows** | a list → one row per item | `expand` | nothing |
| **pack columns** | a row's variables → a dict | `pack` | nothing |
| **unpack columns** | a dict → one column per key | `widen` | nothing |
| **reorder** | change the row order | `sort` | nothing |
| **rename** | change the column names | `rename` | nothing |
| **place beside** | rows of the same samples, side by side | `zip_` | nothing |
| **place below** | one grid's rows after another's | `stack` | nothing |
| **match** | rows paired on a key: many-to-many | `join` | unmatched rows, with `how="inner"` |
| **choose** | keep some rows or columns | `filter`, `slice`, `distinct`, `select`, `drop` | what's left out |
| **reduce** | many cells → one value | `collapse` with a reducer (`count`, `total`, …) | the values |
| **compute** | one value per row, from a tool | `map`, `group` | what the tool decides |
| **make rows** | a tool returns new samples | `expand` with a tool, `sweep`, `source` | — (new data) |
| **opaque** | a tool returns a whole grid | `table` | what the tool decides |

`expand` appears twice. With a tool, it **makes rows**: the tool decides the
items, and the output is only its results. Without one
(`mod.expand(columns=…)`), it **unpacks** lists already in the grid, several
together in lockstep, and keeps the other columns of the grid it is given:
the reference decides which (`wf["l"]` keeps them all;
`wf["l"][cols[["name", "temp"]]]` keeps none).

## 4. Any selection to any cell, and back

A **selection** is part of a grid: a cell, a row, a column or a block. Its
**packed** form is one cell, and only two packed forms exist:

| Selection | Packs into | With | Unpacks with |
|---|---|---|---|
| a column | a **list**, in row order | `gather[collapse()]` | `expand` |
| a row | a **dict** `{column: value}` | `pack` | `widen` |
| a block | a **list of dicts** (one per row) | `pack`, then `gather` | `expand`, then `widen` |
| a block | a **dict of lists** (one per column) | `gather`, then `pack` | `widen`, then `expand(columns=…)` |

So **any selection reaches any cell in at most two packs, and comes back in at
most two unpacks.** With `choose` to pick the selection and `zip_` or `stack`
to place the result, that is every cell-to-cell reshape.

- **A packed value is plain:** `[37.0, 38.5, 39.1]`, never `[(0, 37.0), …]`.
  Its row ids travel beside it, as a list in a `#` column.
- **Only variables are packed.** A row's dict holds its variables, never its
  `#` columns.
- **Built-in reducers work on each variable separately:**
  `gather[collapse()]` on three columns gives one row of three lists. The
  `by` key is never part of what they reduce.
- A DataFrame in a cell is not a packed form. It stays the exception for a
  `table` tool's result.

## 5. Where each row comes from

| Step | Its rows | Writes |
|---|---|---|
| keeps ids: `map`, `group`, `widen`, `pack`, `sort`, `rename`, `select`, `drop` | its input's rows, same ids | nothing new; carries its input's `#` columns |
| chooses: `filter`, `slice`, `distinct` | some of its input's rows, same ids | the same; `distinct` adds `#v`, the rows each kept row stands for |
| `expand` | new rows, one per item | `#v`: each item's parent row |
| `collapse` | one row per group | `#v`: the group's rows, in the order they were reduced |
| `join` | one row per matched pair | `#v` and `#w`: one row of each side |
| `stack` | each input's rows, one after another | `#a` and `#b`: one of them, `None` for the other |
| `source`, `sweep`, a value | generated | nothing |
| `table` | what the tool returns | nothing: it traces to the whole input |

- **`#v` is named after the step's name**, never its position, and a step
  rename relabels it. A step read twice (a self-join) gets `#v_1` and `#v_2`.
- **Further back is found by following `#` columns step by step.** A grid
  records only its direct inputs.
- **You may drop or rename `#v`**, and the trace stops there: lineage says
  *"provenance dropped at 'x'"*, and grouping by it is refused. `#` itself
  can't be dropped: every grid has row ids.

## 6. Matching rows

**The rule** (owner, 2026-10-27): *core lines up row `r` of one grid with row
`s` of another only when core itself recorded that `r` came from `s`, or they
are the same row, so that every row has exactly one partner.* Otherwise the
step is refused, and you `join` first, or say `match_ids=True`.

Two words in it do the work:

- **recorded:** the link is in a `#` column core wrote, or the two rows are
  one row (the same id in one origin). Ids that merely look alike are not a
  record, and neither is a column name.
- **exactly one:** a row with no partner is refused or blocked, never
  invented; a row with several partners is refused, because core can't
  choose. Reduce first.

So direction matters. A child knows its one parent; a parent has many
children.

### 6.1 Every case

| Rows meet as | Recorded link | Partners per row | |
|---|---|---|---|
| one origin: `v` and `map(v)` | the same rows | exactly 1 | ✓ |
| a child and its parent: `expand(v)`'s items and `v` | each item's `#v` | exactly 1 | ✓ each item beside its parent; a parent may repeat, or have no items |
| a grandchild and its grandparent | `#e`, then `e`'s `#v` | exactly 1 | ✓ |
| a parent and its children, the parent's rows leading | each parent has 0…n | 0…n | ✗ `collapse(by="#v")` first; then it is one row per parent |
| siblings: item *j* of two `expand`s of `v` | each knows its parent, nothing links them | — | ✗ zip each with `v`; or pack the lists together and `expand(columns=[…])` them in lockstep |
| one origin, rows missing from one: `v` and `filter(v)` | the same rows, where both have them | 0 for some rows | `zip_` ✗ refused, naming the rows; a column argument blocks those rows and runs the rest (below) |
| two sources, or two DataFrames you assigned, whose ids look alike | none: core made neither id | — | ✗ unless `zip_(…, match_ids=True)` |
| two sources both indexed by the same name (`patient`) | none: a name is not a link | — | ✗ `join(a, b, on="patient")`, or `match_ids=True` (owner, 2026-10-27) |
| a `join`'s rows and one of its inputs | each row's `#a` | exactly 1 | ✓ |
| a `table`'s rows and its input | none: the tool chose the index | — | ✗ always its own origin |

**The same rule for every way rows meet:** `zip_`, a column argument, and the
table view's lines. A column argument from a parent into its child
(`scale[mod.map()](wf["e"], temp=wf["v"][cols["temp"]])`: each item gets its
parent's `temp`) is the same match as `zip_(e, v)`, so it is allowed (owner,
2026-10-27).

**What needs no matching:**
- a cell reference as an argument: one value for every row;
- a column given to a `list`, `Series` or `DataFrame` parameter: the whole
  column, for every row (K19);
- `join`, which matches on a key you name and records the pairs;
- `stack`, which puts rows below each other.

**When some rows have no partner** (owner, 2026-10-27, keeping K19): no row is
dropped or invented, ever.
- A column argument **blocks** the rows it can't match, naming them, and the
  other rows run.
- A `zip_` would have to drop or invent rows, so it **refuses** the step and
  points to `join`.

**`match_ids=True`** is you vouching that two grids number the same samples
the same way. Core then still holds you to it: the id sets must be equal,
and of the same type (`1` is not `"1"`).

**When it's checked:** whether a match is recorded is known from the verbs, so
an unrecorded match is refused when the step is declared. Which ids are
present is known when it runs.

### 6.2 Origins

A row's **origin** is the step that decided which samples the rows are. Two
rows with the same id are the same row only within one origin.

| Origin | Steps |
|---|---|
| **its input's** | steps that keep ids, and steps that choose (§5) |
| **a child of its input's** | `expand`: each row knows its parent through `#v` |
| **`s`'s** | `collapse(by="#s")` (§7); an `expand` that gives back packed ids (below) |
| **its own** | `source`, a value, `sweep`, any other `collapse`, `join`, `stack`, `table` |

**Unpacking what core packed gives back the same samples.** When `expand`
unpacks a list that `gather` made, and no tool rewrote it on the way, the
items get back the ids and origin they were packed from: `expand(gather(v))`
is `v`'s rows. A list a tool wrote or rewrote is new to core: its items get
new ids (`"0.1"`, a label only) and a child origin.

## 7. Going back

Every step's plan says how to go back from its output to its input. The verb
decides which, never the data:

Every step's plan has `plan["inverse"]`:

| Inverse | Means | Steps |
|---|---|---|
| **rebuild** | the input can be computed from this output alone, exactly: the plan gives the formula of the step that does it (L52 runs every one) | `rename` → `rename` back; `pack` → `widen`; `widen` (of a `value` column) → `pack`; `gather[collapse(by=k)]` → `expand(columns=…)`; a `zip_` of one origin → a `select` per input |
| **trace** | the values or the order are lost here, but `#` columns lead to the exact input rows, which are still in the workflow | `sort` (the rows are all there; their order is the input's), `filter`, `slice`, `distinct`, `select`, `drop`, `expand`, `stack`, `join`, reductions, every tool call |
| **opaque** | the trace leads to the whole input | `table` |
| **generated** | there is no input to go back to | `source`, `sweep`, a value, the empty step |

```python
k["r"] = mod.rename(columns={"temp": "t"})(wf["v"])
k.step("r").plan["inverse"]
# {'kind': 'rebuild', 'formula': "mod.rename(columns={'t': 'temp'})(wf[\"r\"])"}
```

`stack`, `join` and `expand` go back by regrouping, `collapse(by="#s")`
(below): that gets the input's rows back exactly, but not always its
columns, so the plan says `trace`, not `rebuild`.

Every intermediate grid is kept, so "lossy" only means that this output alone
can't rebuild its input. You can always trace back, unless you dropped the
`#` column that leads there.

**`collapse(by="#s")` regroups rows by the row of an earlier step `s` they
came from**, following `#` columns back as far as needed:

```python
k["e"] = readings[mod.expand()](wf["v"])                       # 2 readings per visit
k["back"] = op("gather")[mod.collapse(by="#v")](wf["e"])       # one row per visit: v's ids
k["side"] = zip_(wf["v"], wf["back"])                          # each visit beside its readings
```

- The result has **a row for every row of `s`**, with `s`'s ids and origin.
  A row of `s` that nothing traces to gets an empty group (`[]` under
  `gather`).
- Rows that trace to no row of `s` (the other input of a `stack`) are left
  out, and the plan says how many.
- Each row must trace to **at most one** row of `s`. If a `collapse` or
  `distinct` lies between `s` and here, grouping by `#s` is refused.

## 8. Reductions and statistics

**Grouping is a composition of moves you already have** (owner, 2026-10-27):

```
f[collapse(by="ward")](g)   =   f[map()](  gather[collapse(by="ward")](g)  )
                                 reduce     re-index by the key, and pack
```

- `gather[collapse(by=k)]` makes **a new index**: one row per key, with `#`
  the key. Each column becomes a list of the group's values, in order, and
  `#v` lists the group's rows. It loses nothing (§4).
- A reducer is **a `map` over those lists**: each parameter named after a
  column gets that row's list; a parameter named after the key gets the key;
  a parameter typed as a list of dicts gets the group's rows. Its lineage,
  plan and types follow from the composition.
- The fold form, `(acc, temp) -> acc`, computes the same answer one row at a
  time, for groups too large to hold as lists.
- The key becomes the index only as the rows are packed: while they are
  separate rows, several share a key, and ids are unique (V4). `group`
  writes a key column and leaves the rows alone.

### 8.1 What happens to each column

Following `vt` (`ward`, `temp`, rows 0–3) through the two moves:

```
vt                     gather[collapse(by="ward")](vt)            mean_temp[map()](…)
#  ward  temp          #  #vt        ward  temp                   #  #vt        value
0  A     37.0    →     A  [0, 1, 3]  A     [37.0, 38.5, 39.1]  →  A  [0, 1, 3]  38.2
1  A     38.5          B  [2]        B     [36.9]                 B  [2]        36.9
2  B     36.9
3  A     39.1
```

| Column of the input | After the pack, `gather[collapse(by=k)]` | After the reducer's `map` |
|---|---|---|
| **the key** (`ward`) | one value per row, and it is also the row id `#` | gone from the variables: `map` outputs only its results. It is still `#` |
| **each other variable** (`temp`) | a list of the group's values, in the order of `#v`; every list in a row has the same length | the reducer's parameter named after it gets the list; columns it doesn't name aren't in its output |
| **the row id `#`** (0–3) | becomes `#vt`: the list of the group's rows | carried, as for any `map` |
| **the input's own `#` columns** (an `expand`'s `#v`, say) | not carried: the rows are new. Reached through `#vt`, step by step; or used as the key, `by="#v"` | — |
| **types** | `T` becomes `list[T]` | checked as `list[T]` (R-D13 e) |

**So `f[collapse(by=k)]` is `f[map()]` over the pack, plus one thing: it keeps
the key as a column** (`#  #vt  ward  value`). The key is the row id too, but
tools never see ids, so a later step that needs `ward` as a value (a `join`
on it, a label) needs the column. L49 checks the rest is the same.

- **One key column.** A key is a single value, because it becomes a row id
  (an `int` or a `str`). To group by two columns, make one key from them with
  a tool (`f"{ward}/{day}"`) under `group`, and group by that.
- **The order inside each list is the input's row order.** `sort` before
  `collapse` decides what `first`, `last` and `gather` see.
- **Unpacking the lists again** (`expand(columns=["temp"])`) gives back
  `vt`'s rows, ids and origin (§6.2), because every list in a row has the same
  length and lines up with `#vt`.

A reduction loses the values on purpose. It never loses which rows it
reduced: its `#v` lists them.

| | |
|---|---|
| its rows' ids | `0` with no `by`; the key with `by="ward"`; `s`'s ids with `by="#s"` |
| what changes when an input row changes | only the groups whose `#v` holds that row go stale |
| a group holding a failed row | `blocked`, naming the row. To leave failed rows out, `filter` them first |
| a group with no rows | the reducer's empty value: `count` 0, `total` 0, `gather` `[]`; one with no empty value (`first`, a mean) gives `absent` |
| several statistics at once | a reducer returning a record (`n`, `mean`, `sd`): a column per field, one shared `#v` |

**To put a statistic back beside its rows**, unpack the reduction's `#v`. Each
row was in exactly one group, so this gives one row per original row, with
its id, carrying its group's statistic:

```python
k["tot"] = op("total")[mod.collapse(by="ward")](wf["vt"])   # #vt: [0, 1, 3], [2]
k["each"] = mod.expand(columns=["#vt"])(wf["tot"])          # rows 0, 1, 3, 2: each its ward's total
k["side"] = zip_(wf["names"], wf["each"])                   # each visit beside its ward's total
```

A statistic computed by a `table` tool (`df.describe()`) is opaque. To keep
the rows behind each number, use `collapse`.

## 9. Uneven data: jagged JSON

**Nothing inconsistent is silent, and core never tidies data for you.** Every
choice that loses something is a step you can see.

**Three things that look alike stay apart:**

| In the JSON | In the grid | Packs back to |
|---|---|---|
| `"x": null` | `None`, a known value | `"x": null` |
| no `"x"` key | `None`, in state **`absent`** | no key |
| a column one input of a `stack` doesn't have; the unmatched side of an outer or left `join` | `None`, in state **`absent`**; the column keeps its type (an int stays an int) | — |
| `"tags": []` | no rows; `collapse(by="#s")` still gives its record a row | `[]` |

A tool given an `absent` cell gets the parameter's default if it has one,
else `None`, as a Python call does for a missing argument.

**`absent` is not empty.** An *empty step* is a step with no expression yet
(`k["x"] = None`, G17): a 1×1 grid holding `"empty"`, staged; a step that
reads it is refused until it has an expression. `absent` is a cell whose
source had no value.

| Uneven | Rule |
|---|---|
| lists of different lengths | fine: `expand` gives 0…n rows each, and packs back exactly |
| records with different keys | `widen` takes every key seen, or `columns=`. A key a record lacks is `absent`, not an error. Types are kept |
| `null` where a list belongs | `expand` gives no rows, with a warning, and packs back to `[]` |
| a list in one record, a bare value in the next | that row fails, *"not a list: str"*; the others run. If a bare `"c"` means `["c"]`, say so with the built-in `as_list` tool, as a step |
| keys that are data (`{"2026-01": 3, …}`) | a **mapping**: `expand` it into `key`, `value` rows. `widen` warns when keys look like data |
| depth | one level per step: a nested dict stays a cell until another `widen` |
| broken JSON | parsing is a tool under `map`: that row fails, the others run |

**A group function gets each column it names as a list** (a reducer under
`collapse`): `def mean_temp(temp: list[float])`. A parameter typed as a list
of dicts or records gets the group's rows; a parameter named after the `by`
key gets the key. A first parameter named `acc` still means a fold, one row
at a time.

**The verb says what a dict is:** `widen` treats it as a record (its keys are
variables), `expand` as a mapping (its keys are data). To make the plan exact
before running, declare the shape with a `TypedDict`: `NotRequired[...]` may
be absent, `X | None` may be null.

## 10. The laws

**Given valid variables, the moves are closed:** every move takes grids to a
grid that keeps the five guarantees, every lossless move has its inverse
among the moves, and every other move traces. "Valid" means:

| | Your data must | Otherwise |
|---|---|---|
| V1 | hold lists (or dicts) in a column you `expand` | the row fails: *"not a list: str"* |
| V2 | have lists of the same length in a row, where several are unpacked together | the row fails |
| V3 | have dict keys that are valid, unique column names | a problem on the step |
| V4 | have unique row ids in a step | the step fails, naming the id |
| V5 | have one type per column (missing allowed) | a warning |
| V6 | have `by=` keys that are hashable scalars | the row fails |
| V7 | not hold `None` where a list belongs, or accept that it packs back as `[]` | a warning |
| V8 | hold one kind of value in a column you `expand` (not lists mixed with scalars) | the row fails; `as_list` accepts it, as a step |
| V9 | have no `absent` cells in a column you `gather`, or accept that they pack as `None` | a warning |

Each law is one test, `test_L<n>_…`. Grouped by the guarantee it checks:

**1. Ids are core's**

| Law | |
|---|---|
| L28 | `cols[0]` is the first variable, with `#v` beside it |
| L29 | a `**kwargs` tool never sees a `#` column |
| L30 | `zip_` of two steps of one origin keeps one `#v` |
| L31 | after `drop(columns=["#v"])`, grouping by `#v` is refused, saying the trace was dropped |
| L46 | a tool can't write an id column: a source or `table` returning `#v` fails its step |
| L47 | `mod.name("#v")` and `rename(columns={"x": "#v"})` are refused; renaming `#v` into a variable is allowed |
| L48 | `.header` and a name-choosing tool (`select(columns=a_tool)`) see variables only |

**2. Every row knows where it came from**

| Law | |
|---|---|
| L14 | a `collapse` cell traces to exactly its group's rows |
| L15 | a `join` cell traces to its pair of input rows |
| L17 | ids are never parsed: a source with ids `a`, `a.1`, expanded, traces each row to its true parent |
| L19 | `distinct` traces each kept row to every row it stands for |
| L32 | a reduction's `#v` lists its group's rows |
| L35 | a group holding a failed row is `blocked` |
| L41 | changing one input row makes only the groups that hold it stale |

**3. Rows line up only when they are the same sample**

| Law | |
|---|---|
| L16 | `zip_` of two origins is refused when declared |
| L16b | the items of a list a tool rewrote don't pair with the rows it was packed from |
| L20 | a `table` is its own origin: its rows don't pair with its input's |
| L36 | a column argument from another origin is refused |
| L37 | ids keep their type: `1` and `"1"` don't pair |
| L38 | `zip_(…, match_ids=True)` pairs equal ids, on purpose |
| L42 | a column argument from a parent into its child gives each item its parent's value |
| L43 | a scalar column argument from a child into its parent is refused when declared, pointing to `collapse(by="#v")` |
| L44 | two `expand`s of one step (siblings) don't pair item by item |
| L45 | two sources indexed by the same name don't pair; `join` on it, or `match_ids=True` |

**4. The shape is known from the verbs**

| Law | |
|---|---|
| L21 | the plan says `inverse: rebuild`, `trace` or `opaque` |
| L39 | on every step of every test, the run matches its plan and the guarantees hold (the invariant check) |
| L40 | on generated grids and generated chains of verbs, the guarantees hold (the property test, `tests/unit/test_reshape_properties.py`; `STRESS=1` for 2,000 examples) |

**5. Nothing is lost silently**

| Law | |
|---|---|
| L1 | unpacking a packed column gives back the column: values, ids, origin |
| L2 | packing an unpacked list gives back the list |
| L3 | widening a packed row gives back the row |
| L4 | a block through a list of dicts comes back |
| L5 | a block through a dict of lists comes back |
| L6 | unpacking groups gives back the rows, ids kept |
| L7 | `expand` then `collapse(by="#v")` gives one row per parent, lined up with it |
| L8 | `sort` is a permutation: same ids, same rows |
| L9 | rename, then rename back, is the grid |
| L10 | `zip_` of two selections of a grid is the grid |
| L11 | `filter` and `sort` commute |
| L12 | `stack(a, b)` splits back into `a` |
| L13 | a `join` collapses back to one side, lined up with it |
| L18 | packing no rows gives `[]`; unpacking `[]` gives no rows, columns kept |
| L33 | unpacking a reduction's `#v` puts each row beside its group's statistic |
| L34 | reducers over no rows give their empty value |
| L52 | every `rebuild` formula, run on its step's output, gives back that step's input: rows, ids and variables |
| L49 | `f[collapse(by=k)](g)` is `f[map()](gather[collapse(by=k)](g))`: same values, ids and `#` columns |

**Uneven data**

| Law | |
|---|---|
| L22 | jagged lists round-trip, `[]` included |
| L23 | `widen` of uneven dicts takes every key; a missing key is `absent`; ints stay ints |
| L24 | packing widened uneven dicts gives them back: absent keys left out, `null` kept |
| L25 | `expand` doesn't tidy: a bare string fails its row, the others run |
| L26 | `expand` of a mapping gives `key`, `value` rows |
| L27 | `expand` of `None` gives no rows |

**The system is closed when every law passes as a plain test**, with the
invariant check (L39) running on every test and the property test (L40)
passing. [reshaping-plan.md](reshaping-plan.md) is the path there.

## 11. What you can't do, even when it's closed

These are limits of the design, not missing work.

| You can't | Because | Instead |
|---|---|---|
| see which part of an input a tool actually used | a tool is opaque: core records which cells it was given, not what it did with them | split the tool, so each step reads only what it needs |
| trace inside a `table` tool's result | the tool decides the whole grid | use `collapse`, `filter`, `join` where you want rows traced |
| keep the identity of items in a list a tool rewrote | after `sorted(…)` or a filter inside a tool, core can't know which item is which | do the sort or filter as a step on the unpacked rows |
| rebuild the input of a lossy step | its values are gone from that output | trace back to the input step, which is still there |
| undo a tool's computation | core knows no tool's inverse | write the inverse as a tool and a step |
| pair two unrelated grids without saying so | rows pair only as the same sample | `join` on a key, or `zip_(…, match_ids=True)` |
| tell `None` from `[]` after packing a missing list, or `absent` inside a list | a list has no way to say either | keep the record's own column, or check V7 and V9 |
| flatten JSON of any depth in one step | each step moves one level | one `widen` or `expand` per level |
| have core decide whether a dict is a record or a mapping | it's a meaning, not a shape | choose the verb; core warns when keys look like data |
| know an undeclared tool's shape before it runs | only running can say | declare the return type, or `mod.expect(...)` |
| keep references when a source changes its own row ids between runs | a source's ids are its own; core trusts them | give the source stable ids, or let core number the rows |
| trace across kernels or saved files | provenance lives inside one workflow | — |

## 12. Coming from pandas

**pandas never asks you to merge two DataFrames before an operation between
them: it lines them up by their labels automatically.** Rows line up by index
label, columns by name. Run with pandas 3.0:

| pandas | Run | Result |
|---|---|---|
| arithmetic aligns rows by label, not position | `a + b`, `b`'s index `[2, 0, 1]` | each row added to the row with the same label |
| labels with no match give `NaN`, silently | `a` (0, 1, 2) `+ c` (1, 5) | four rows, three of them `NaN` |
| assigning a column aligns too | `a["w"] = series` indexed `[2, 1, 0]` | values reordered to match |
| unrelated frames align when their labels look alike | two frames with the default `0…n-1` index | paired row by row, whatever they hold |
| `.values` drops the labels | `a.temp.values + b.temp.values` | added by position |
| `1` and `"1"` are different labels | `concat([x, y], axis=1)` | four rows, not two |
| duplicate labels are allowed | `a + dup`, `dup` indexed `[0, 0]` | `NaN`s, and no error |
| `merge` matches on key columns | `merge(wards, visits, on="ward")` | a new `0…n-1` index; which input rows each came from is lost |

**Core keeps the convenience and removes the guessing.** `zip_` and column
arguments are pandas' alignment by label: rows line up by id with no `join`
first. What changes is *when* ids are allowed to line up:

| pandas | core |
|---|---|
| any two frames whose labels match | only rows of the same samples (one origin, or a child and its parent), or `zip_(…, match_ids=True)` when you say so |
| unmatched labels become `NaN` | refused, naming the rows; for a partial match, `join` |
| the default `0…n-1` index lines up unrelated frames | ids made by counting never line up across origins |
| `.values` lines up by position | never by position |
| duplicate labels allowed | ids unique in a step (V4) |
| columns with the same name are added together | `zip_` refuses a variable both grids have: rename one |
| `merge` gives a new index and forgets its inputs | `join` gives new ids and records `#a`, `#b`: each row's pair of input rows |

So you can treat a grid like a DataFrame whose index is trustworthy: when core
lines two grids up, their rows are the same samples, or you said they are.
