# Row maps: reshapes that aren't one-to-one

> **Superseded by [reshaping.md](reshaping.md)**, which absorbs this draft.

> Proposed 2026-10-27, for the owner. *Today* lines were run at `8efe6fd`
> (the probes are in §7). Nothing here is decided: §6 lists five small
> decisions, each with a recommendation.

## 1. Why we keep coming back to this

Reshaping has been settled one verb at a time: which ids `expand` gives
(`"i.j"`), which ids `collapse(by=…)` gives (the key, D3), that combines number
their rows `0…N-1`, that a record's field cells share their lineage, that
`group` carries columns. Each answer was reasonable. But every feature built on
top asks the same question, and none of those answers covers it:

> **For this output row, which input rows is it made from, and is it the
> *same* observation as any of them?**

| Feature | Asks |
|---|---|
| `zip_`, a column as an argument (K19) | is row `2` here the same observation as row `2` there? |
| lineage (K28), a click on a cell | which input cells fed this one? |
| per-row staleness (D3) | an input row changed: which output rows are affected? |
| the workflow as a table (G18) | which rows go on one line across steps? |
| "the pairs undo each other" (outputs-and-reshaping.md §7.5) | can I get back to the rows I started from? |

When a step keeps its rows one-to-one (`map`, `sort`), the row id answers all
of these, which is why K19 felt finished. The answers stop working when a step
**isn't one-to-one**: one row becomes several, several become one, rows come
from two steps, or a tool decides. Then the row id alone can't answer them, and
each feature makes up its own answer. That is the wheel we keep spinning.

**The proposal:** answer the question once, per step, as data: **every output
records a row map**, and every feature above reads it.

## 2. What we want to achieve

These are the outcomes, in the user's terms. Everything below serves them.

1. **Click a cell, see where it came from:** the exact input rows and columns,
   for every verb, including `collapse`, `join` and `distinct`.
2. **Change one input row, and only the rows it fed go stale.**
3. **Rows never pair by accident.** Two rows are lined up (`zip_`, a column
   argument, the table view) only when they are the same observation. Anything
   else is refused, pointing to `join`.
4. **A reshape that loses nothing can be undone**, and the plan says which
   ones can.

Not a goal: following values *inside* a tool. A `table` tool or a reducer is
opaque. Core records which rows went in, not how the tool used them.

## 3. The two ideas

### 3.1 A row map

A step's **row map** says, for each output row, which input rows it is made
from: `{output id: [(step, input id), …]}`. Every step has one kind of map:

| Kind | Each output row comes from | Verbs |
|---|---|---|
| **one-to-one** | exactly one input row, the same observation | `map`, `group`, `widen`, `sort`, `rename`, `select`/`drop` of columns |
| **one-to-at-most-one** | one input row; some input rows are dropped | `filter`, `slice`, `select` of rows |
| **one-to-many** | one input row; each input row gives 0…n rows | `expand` |
| **many-to-one** | a group of input rows | `collapse`, `distinct` |
| **many-to-many** | one row of each input; an input row can appear in many output rows | `join` |
| **union** | one row of one of the inputs | `stack` |
| **side by side** | the row with the same id in each input | `zip_` |
| **none** | no input row: generated | `source`, `sweep`, a value |
| **opaque** | the whole input: the tool decides | `table` |

**Cells follow from rows.** An output cell's lineage is its row's input rows,
restricted to the columns the call read (or, for a reshape, the column the cell
was copied from). So cell lineage doesn't need storing cell by cell: the row
map, plus which columns fed which argument, gives it. That covers the cell-level
cases too: a record spread across columns (one call → k cells, all from the same
input cells, as decided 2026-10-26), `widen` (one cell → k cells from that one
cell), and a reducer (n cells → one cell).

### 3.2 Where an id comes from

A row id says "this is the same observation" only among steps whose ids
**come from the same place**. Call the step that made a row's ids its
**origin**:

- A step that keeps rows (one-to-one, one-to-at-most-one) keeps its input's
  origin. So does `distinct`, whose rows are input rows (M-D3).
- `expand` makes child ids (`"0.1"`) whose parent is in the input's origin.
- Every other step is its own origin: `source`, a value, `sweep`, `collapse`,
  `join`, `stack`, `table`.

**The rule:** rows pair by id only when the two steps share an origin.
Otherwise the ids are labels that happen to look alike.

## 4. Each verb, mapped

| Verb | Map | Ids out | Origin | Lineage today (§7) | Gap |
|---|---|---|---|---|---|
| `map`, `group`, `widen`, reshapes | one-to-one | kept | input's | the row | — |
| `filter`, `slice` | one-to-at-most-one | kept | input's | the row | — |
| `expand` | one-to-many | `"i.j"` | child of input's | **the parent row** (`e "0.1"` → `v 0`) | output has no parent column, so it can't be collapsed back per parent (M1) |
| `collapse(by=k)` | many-to-one | the key (D3) | own | **the whole step** (`id None`) | the group's rows aren't recorded; D3's per-group staleness has nothing to read (M2) |
| `collapse` | many-to-one | `0` | own | the whole step | the right answer here: one row from all rows |
| `distinct` | many-to-one | the first row's id | input's | **only the row kept** (`d 0` → `v 0`, not 0, 1, 3) | the rows it stands for aren't recorded (M3) |
| `join` | many-to-many | `0…N-1` | own | **the whole of both steps, no columns** | each row's pair of input rows isn't recorded (M4) |
| `stack` | union | `0…N-1` | own | the whole of both steps | which input row each came from isn't recorded (M4) |
| `zip_` | side by side | kept | input's | — | pairs counted ids by accident (M5) |
| `table` | opaque | the tool's index | own | the whole step | a tool's index can look like the input's ids (M6) |
| `sweep`, `source` | none | `0…n-1`, or the source's own index | own | — | — |

## 5. Found while checking

Run at `8efe6fd` (probes in §7). Numbered M to keep them apart from G and K.

| # | What |
|---|---|
| M1 | `expand` → `collapse` doesn't round-trip. `expand` outputs only `value` (§2.6 of outputs-and-reshaping), so there's no parent to group by: `gather` under `collapse` gives one list of all 8 items, not one list per parent. outputs-and-reshaping.md §7.5 says the pair undoes itself; today it doesn't |
| M2 | `collapse(by="ward")` gives ids `A`, `B` (D3, done), but its cells' lineage is `('v', None)` (the whole step). Row-ids.md says K19 is complete; D3's second half (*"a collapsed row keeps which input rows were in its group"*) isn't built |
| M3 | `distinct(columns=["ward"])` keeps rows `0` and `2`; row `0`'s lineage is `v 0` only, though it stands for rows 0, 1 and 3 |
| M4 | `join`, `stack`: lineage is `('v', None, [])`, `('w', None, [])`: whole steps, no rows, no columns. Decided 2026-10-26 to point at the input cells; not built |
| M5 | **Counted ids pair by accident.** `jw = join(w, v, on="ward")` is ordered by ward (Ada, Ada, Cy, Ben), ids `0…3`. `zip_(v, select(jw, columns=["head"]))` is `completed` and puts **Ben (ward B) beside Dr X (ward A)**. K19 retired pairing by position; ids made by counting bring it back |
| M6 | `table` keeps the tool's index (`top2` returns ids `1`, `3`), so its rows claim to be `v`'s rows 1 and 3. Here that's true; for a pivot returning `0, 1` (wards), they'd claim to be patients 0 and 1, and a column argument would pair them |
| M7 | `k.cell(step, row)` takes a position; `k.cell("e", "0.1")` raises `TypeError: '<=' not supported between 'int' and 'str'`. Everything else selects by id since K19 |

## 6. Decisions for the owner

Each is one small piece, confirmed before it lands.

**M-D1. Rows pair by id only within an origin** (§3.2). `zip_` and a column
argument refuse two steps of different origins, pointing to `join`. Fixes M5
and M6, and gives G18 its rule for which rows share a line.
*Recommended.* The alternative, ids that can't collide (`"j0"`, `"s0"`), makes
ids harder to read and still says nothing about which step a row belongs to.

**M-D2. `collapse` can group by the parent of an `expand`**, so the pair
undoes itself: `gather[mod.collapse(by=parent)](wf["e"])` gives one row per
parent, **with the parent's id and origin**, so it can be zipped back beside
the rows it came from. Fixes M1.
*Recommended.* Alternatives: `expand` carries its input's columns (reverses
the owner's 2026-10-20 decision), or drop the undo claim from §7.5.
How `parent` is written (`by=parent`, `by="#parent"`) is a further choice.

**M-D3. `distinct` keeps the first row's id and records every row it stands
for**, as `collapse(by=…)` does. Its origin stays the input's, since the kept
row is an input row. Fixes M3.
*Recommended.*

**M-D4. Every output stores its row map** (K28), for every verb, including
`collapse`'s groups, `join`'s pairs and `stack`'s sources. Staleness per row,
`k.cell` and lineage read it and nothing else. Fixes M2, M4.
*Recommended.* This is K28, narrowed: store the row map per row, not lineage
per cell (§3.1).

**M-D5. `table` is always its own origin**, whatever index the tool returns.
To keep some of the input's rows, use `filter` or `slice`. Fixes M6.
*Recommended.* Alternative: a `table` whose ids are all input ids keeps the
input's origin. That's convenient for a "top n" tool, but it trusts the tool's
index to mean what it looks like.

Not a decision, a fix: **M7**, `k.cell` takes a row id, like selections.

**Words.** *row map* and *origin* are new. If they're accepted, they go into
object-model.md §1.

### Order, once decided

1. M7 (`k.cell` by id): a fix, no new behaviour.
2. M-D4 for the verbs that keep rows and for `expand`: the map exists today in
   effect, so this only stores it.
3. M-D1: origin recorded, pairing checked. Fixes the silent wrong answer (M5)
   first.
4. M-D4 for `collapse`, `distinct`, `join`, `stack`; then D3's per-group
   staleness on top.
5. M-D2, M-D3, M-D5.

## 7. The probes

```python
@tool
def visits() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Ada", "Ben", "Cy"], "ward": ["A", "A", "B", "A"],
                         "temp": [37.0, 38.5, 36.9, 39.1]})
@tool
def wards() -> pd.DataFrame:
    return pd.DataFrame({"ward": ["A", "B"], "head": ["Dr X", "Dr Y"]})
@tool
def readings(name: str) -> list: return [len(name), len(name) * 10]
@tool
def top2(df: pd.DataFrame) -> pd.DataFrame: return df.sort_values("temp").tail(2)

k["v"] = visits[mod.source()]();  k["w"] = wards[mod.source()]()
k["e"] = readings[mod.expand()](wf["v"])                        # M1
k["back"] = Operation(tool="gather")[mod.collapse()](wf["e"])   # M1: one list of 8
k["c"] = Operation(tool="count")[mod.collapse(by="ward")](wf["v"])   # M2
k["d"] = mod.distinct(columns=["ward"])(wf["v"])                # M3
k["j"] = join(wf["v"], wf["w"], on="ward")                      # M4
k["t"] = top2[mod.table()](wf["v"])                             # M6: ids 1, 3
k["jw"] = join(wf["w"], wf["v"], on="ward")
k["jn"] = mod.select(columns=["head"])(wf["jw"])
k["z"] = zip_(wf["v"], wf["jn"])                                # M5: Ben beside Dr X
k.run_all()
k.cell("c", 0, "value")["inputs"]                               # M2: ('v', None)
k.cell("e", "0.1")                                              # M7: TypeError
```
