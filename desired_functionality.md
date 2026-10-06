# Desired functionality — row/column naming conventions

The reshaping rules I'm standardizing on, with the verb that produces each shape.
Every example here was run against `grid.py`; see
[docs/shape-algebra.md §2.1 / §3](docs/shape-algebra.md) for the full algebra and
[examples/all_orchestrations/](examples/all_orchestrations/) for a runnable copy.

## Every output is a DataFrame; a value is one cell

`Output.data` is always a DataFrame — a scalar is a 1-row, 1-column frame. A tool
invocation **always produces exactly one cell** (one value, any Python type).
Turning that cell into rows and columns is a separate declaration: the shape verb.

So a tool that returns `["a.csv", "b.csv"]`, undecorated, is **one cell** holding
the list — not a table. It becomes rows/columns only when a verb says what the
value means.

## Default column names — the payload column is `value`

The column that holds whatever a verb produced is the **payload column**, and its
default name is `value` (the `PAYLOAD` constant). Override it with `name=`.

| verb | adds column | default name |
|---|---|---|
| `map`, `expand`, `collapse`, `sweep` | the produced value | `value` |
| `group` | the key | `group` |
| `widen` | the lifted fields | the names in `columns=` |
| `select`/`drop`/`rename`/`slice`/`sort`/`distinct`/`filter`/`source` | none (reshape only) | — |

Carried input columns always keep their names; `map`/`expand`/`group`/`filter`
pass them through.

## Row identity — the index

- **Preserved** (the address travels with the row): `map`, `filter`, `group`,
  `select`, `drop`, `rename`, `widen`, `slice`, `sort`, `distinct`.
- **Reset** to a positional `RangeIndex`: `expand` (rows outnumber inputs — origin
  recorded in the ledger's `unit` column) and `collapse` (new rows).
- **From the value** on a `source`: a list → positional `0,1,2…`; a dict → its
  **keys** as the index.

## If I expand a list → rows, in the `value` column

```python
fan_out(n) -> [n] * n
wf["bursts"] = fan_out[mod.expand(over=wf["readings"])]      # no name= → "value"
```
```
 n  value
 3      3
 3      3
 3      3
```

## If I expand a list of dicts → rows of records (then `widen`)

`expand` makes it **longer** only — each dict lands whole in `value`; it does not
spread keys into columns. A bare `dict` is *not* iterated (only list/tuple/set
are), so each dict stays one item.

```python
make_coords(n) -> [{"axis": "x", "val": n}, {"axis": "y", "val": n * 2}]
wf["coords"] = make_coords[mod.expand(over=wf["readings"])]  # value = a dict per row
wf["spread"] = mod.widen(over=wf["coords"], columns=["axis", "val"])
```
```
 n                   value  axis  val
 1 {'axis':'x','val':1}    x    1
 1 {'axis':'y','val':2}    y    2
```

## If a tool produces more than one output → return a record, then `widen`

A tool returns one cell, and `map` writes exactly **one** new column. Several named
results = return a **dict**; its keys become the column names.

```python
describe(n) -> {"tenx": n * 10, "sq": n * n}
wf["stats"] = describe[mod.map(over=wf["readings"])]         # value = the dict
wf["wide"]  = mod.widen(over=wf["stats"], columns=["tenx", "sq"])
```

Two genuinely different-shaped results = two steps (a step's output is one grid).

## `widen` matches mappings by key, sequences by position

`widen` lifts a cell's fields into columns, and how it names them depends on the
cell:

- a **mapping** is matched **by key** — `columns=` is required, because a
  record's fields are not guessed;
- a **sequence** (tuple/list) is matched **by position** — with `columns=` you
  name the positions, and **without it the columns default to `c0, c1, …`**
  (width = the longest row; ragged rows pad with `None`).

So a column of tuples widens on its own:

```python
wf["raw"]  = pd.DataFrame({"value": [(10, 1), (20, 4)]})
wf["wide"] = mod.widen(over=wf["raw"])            # no columns= → value, c0, c1
```
```
  value  c0  c1
(10, 1)  10   1
(20, 4)  20   4
```

An explicitly declared column a cell cannot supply is still a per-unit failure:
a short tuple against `columns=["a","b"]` → "too few"; a scalar cell → "needs a
mapping per row (or a sequence)".

## Meaningful names for tuple positions

`c0, c1` are positional; for real names either name them in `columns=`, or — best
— have the producing tool return a dict so the keys *are* the names:

```python
# option A: name the positions at widen time
wf["wide"] = mod.widen(over=wf["mapped"], columns=["tenx", "sq"])

# option B (best): the tool returns a record, so no naming step is needed
describe(n) -> {"tenx": n * 10, "sq": n * n}
```

The naming always traces to either a dict key or a position — a tuple has only
positions, so `c0, c1` is the honest default until you give them meaning.