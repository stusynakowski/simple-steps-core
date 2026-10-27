# Reshaping: the decisions, with examples

> For the owner. **Every decision here is made (2026-10-27).** Each decision in
> [reshaping-plan.md §5](reshaping-plan.md#5-decisions), with what core does
> **today** (run at `464e423`), what it does **with the decision**, the
> alternatives, and a recommendation. The rules the decisions serve are in
> [reshaping.md](reshaping.md).

Every example uses the same two steps:

```python
k["v"] = visits[mod.source()]()     # name ward temp            k["w"] = wards[mod.source()]()   # ward head
                                    # 0  Ada  A    37.0                                          # 0  A    Dr X
                                    # 1  Ada  A    38.5                                          # 1  B    Dr Y
                                    # 2  Ben  B    36.9
                                    # 3  Cy   A    39.1
```

Five decisions change what existing workflows get: **R-D7 (decided), R-D1,
J-D2, J-D3 and J-D4**. They are marked ⚠. The others add behaviour or close a gap.

---

## Step 4: same samples

### ⚠ R-D7. Rows pair only when they are the same sample — decided

**Decided by the owner, 2026-10-27:** *refuse the zip unless we know exactly
how to match; or join, then run it.* Made precise: core lines up two rows
only when it recorded how they match, so every row has exactly one partner:
one origin, a child and its one parent (through `#v`), or `match_ids=True`,
where the user vouches for the ids. Also decided: a shared index name
(`patient` in both) is not a match; missing rows block a column argument and
refuse a `zip_`, as K19 has it. Every case is in
[reshaping.md §6.1](reshaping.md#61-every-case).

**The question.** When `zip_` or a column argument lines up two grids whose
ids look alike but come from unrelated steps, should core pair them or
refuse?

**Today:** it pairs them, and the answer is wrong.

```python
k["jw"] = join(wf["w"], wf["v"], on="ward")     # its rows: Ada, Ada, Cy, Ben (ordered by ward), ids 0…3
k["heads"] = mod.select(columns=["head"])(wf["jw"])
k["z"] = zip_(wf["v"], wf["heads"])
# completed. head: Dr X, Dr X, Dr X, Dr Y       ← Ben (ward B) beside Dr X; Cy beside Dr Y

k["lab"] = label[mod.map()](wf["v"], head=wf["jw"][cols["head"]])
# completed. Ada/Dr X, Ada/Dr X, Ben/Dr X, Cy/Dr Y     ← the same mistake, as a column argument (M10)
```

`jw`'s ids `0…3` were made by counting. They don't mean "visit 0…3".

**With R-D7:** both steps are refused when declared:

> *"'v' and 'heads' don't come from the same rows ('heads' is from a join of
> w and v). To match on a column: join(v, w, on="ward"). If their ids mean
> the same samples: zip_(…, match_ids=True)."*

The right way says what to match on:

```python
k["vw"] = join(wf["v"], wf["w"], on="ward", how="left")   # Ada Dr X, Ada Dr X, Ben Dr Y, Cy Dr X
```

**Still allowed, unchanged:**
- steps of one origin: `zip_(v, f)` where `f = to_f[mod.map()](wf["v"])`;
- a child with its parent: an `expand`'s items beside their parent, or
  their grandparent.

**The opt-in, for when you know two grids number the same samples the same
way** (two tools reading the same file, both indexed by patient id):

```python
k["temps"] = load_temps[mod.source()]()       # indexed by patient id
k["names"] = load_names[mod.source()]()       # indexed by patient id
k["both"] = zip_(wf["temps"], wf["names"], match_ids=True)
```

With `match_ids=True`, the ids must still be the same set, and the same type:
`1` and `"1"` never pair (M11; today they do).

| Alternative | Why not |
|---|---|
| keep pairing equal ids silently | M5 and M10 stay: wrong answers with no warning |
| warn, but pair | a warning on a wrong answer is still a wrong answer, and warnings get ignored |
| always require `join`, no opt-in | `join` gives new ids `0…N-1`, so the result no longer lines up with either input |

**Recommended:** refuse when declared, with the `match_ids=True` opt-in.

**Changes for users:** a `zip_` or column argument between unrelated steps
that works today is refused. One argument puts it back, if it was meant.

### R-D9. A `table` is its own origin; `distinct` records what it stands for (R-D9b) — both decided 2026-10-27

The `table` half is decided (2026-10-27): it follows from R-D7, because a
tool's index is no known match.

**The question, part 1.** A `table` tool returns a whole grid with its own
index. Are its rows the input's rows?

**Today:** the tool's index is trusted as row ids.

```python
k["t"] = top2[mod.table()](wf["v"])          # df.sort_values("temp").tail(2)
# ids 1, 3: Ada 38.5, Cy 39.1               ← true here: they are v's rows 1 and 3

k["h"] = hottest[mod.table()](wf["v"])       # sorted, then .reset_index(drop=True)
k["zh"] = zip_(wf["names"], mod.select(columns=["temp"])(wf["h"]))
# completed. Ada 39.1, Ada 38.5, Ben 37.0, Cy 36.9      ← Ada beside Cy's temperature
```

**With R-D9:** a `table` is always its own origin. Its ids are kept as labels,
but its rows don't pair with its input's: `zh` is refused, as in R-D7. To keep
`v`'s rows, do it as steps core can trace: `mod.sort(by="temp")` then
`mod.slice(start=-2)`.

| Alternative | Why not |
|---|---|
| trust the index when every id is one of the input's | `hottest` above passes that test and is still wrong |

**The question, part 2.** `distinct` keeps one row per group. Which rows does
it stand for?

**Today:** `mod.distinct(columns=["ward"])(wf["v"])` keeps rows 0 (Ada, A) and
2 (Ben, B). Row 0 traces only to row 0.

**With R-D9:** it also writes `#v`: row 0 → `[0, 1, 3]` (every ward-A row),
row 2 → `[2]`. A click shows all three. Changing row 3 makes row 0 stale.

**Recommended:** both parts.

---

## Step 5: provenance for every verb

### R-D12. A reduction lists the rows it reduced, as `#v` — decided 2026-10-27

**Today:** the group's rows are recorded, but only in a note:

```python
k["cnt"] = op("count")[mod.collapse(by="ward")](wf["v"])
# ward value                k.cell("cnt", "A")["inputs"] → rows [0, 1, 3]
# A    3
# B    1
```

**With R-D12:** they are a column you can see and use:

```
#  #v         ward  value
A  [0, 1, 3]  A     3
B  [2]        B     1
```

This is what makes it possible to put a statistic back beside its rows
(reshaping.md §8): `mod.expand(columns=["#v"])` gives one row per visit,
each holding its ward's count. Two parts of R-D12 are already built:
- the empty value over no rows (step 1);
- a failed row blocks its group (L35).

| Alternative | Why not |
|---|---|
| keep the rows in the note | the grid then doesn't show where its rows came from, and `by="#v"` and `expand(columns=["#v"])` have nothing to read |

**Recommended:** yes.

---

## Step 6: round trips

### ⚠ R-D1. A reducer takes each column as a list — direction decided

**Owner, 2026-10-27:** *reductions almost always take a list for each
argument; sometimes a list of dicts, depending on the operation. The types
say which* (to be written up with the orchestration docs). So `collapse`
calls a reducer once per group, with each column it names as a list:

```python
@tool
def mean_temp(temp: list[float]) -> float: ...              # temp: the group's temps
@tool
def spread(temp: list[float], name: list[str]) -> Spread: ...  # two columns, as two lists
@tool
def hottest(rows: list[Visit]) -> str: ...                  # the group's rows, as records
```

**Today this form doesn't exist.** `collapse` only folds one row at a time,
`(acc, temp) -> acc`:
- `mean_temp` fails, *"got multiple values for argument 'temp'"*;
- `spread` is refused when declared, *"declares name: list, but 'v' has name
  as str"*.

The details are R-D13 below. The rest of this section is the built-in
reducers' part.

**Today:** a reducer gets each row as a whole when the grid has two or more
columns:

```python
k["g"] = op("gather")[mod.collapse()](wf["v"])
# one cell: [{'name': 'Ada', 'ward': 'A', 'temp': 37.0}, {…}, {…}, {…}]   ← both axes packed in one step

k["tot"] = op("total")[mod.collapse(by="ward")](wf["vt"])     # vt: ward, temp
# fails: "unsupported operand type(s) for +: 'int' and 'dict'"  ← the key is inside each row (R9)
```

**With R-D1:**

```
gather[collapse()](v)                                  total[collapse(by="ward")](vt)
#  #v            name                  ward             temp                 #  #vt        ward  temp
0  [0, 1, 2, 3]  [Ada, Ada, Ben, Cy]   [A, A, B, A]     [37.0, …, 39.1]      A  [0, 1, 3]  A     114.6
                                                                             B  [2]        B     36.9
```

To get a list of dicts, say so: `pack` each row first (R-D2), then `gather`.

| Alternative | Why not |
|---|---|
| keep the whole-row convention | the result's shape then depends on how many columns the input has (R3), and `total` by a key can't work (R9) |

**Recommended:** yes.

**Changes for users:** `gather` on a grid with several columns gives one list
per column, not a list of dicts.

### R-D13. How a group function gets its arguments — decided 2026-10-27 (a–e)

Follows from R-D1. The questions, with a recommendation each:

| | Question | Recommended |
|---|---|---|
| a | A parameter named after a column: what does it get? | the group's values of that column, as a list in the order of `#v`; untyped parameters too, since reducers almost always take lists |
| b | A parameter typed `list[dict]`, or a list of a record type, that isn't a column's name | the group's rows, each as a dict of its variables (never its `#` columns) |
| c | A parameter named after the `by` key, typed as a scalar | the group's key: `def f(ward: str, temp: list[float])` |
| d | The accumulator form `(acc, …) -> acc` | kept, for folds over very large groups; a first parameter named `acc` still means it |
| e | The type check | under `collapse`, a column parameter is checked as `list[<the column's type>]`: `spread` above passes |

### R-D5. `collapse(by="#s")` regroups by any earlier step — decided 2026-10-27

**Today:** it works when `#s` is a column of the input. That covers a direct
`expand`, and steps that carried it, such as a `sort`:

```python
k["e"] = readings[mod.expand()](wf["v"])
k["f"] = mod.sort(by="value")(wf["e"])
k["back"] = op("gather")[mod.collapse(by="#v")](wf["f"])     # one row per visit ✓
```

It doesn't work further back:

```python
k["ee"] = twice[mod.expand()](wf["e"])                        # items of items: has #e, not #v
k["gp"] = op("gather")[mod.collapse(by="#v")](wf["ee"])
# invalid: "collapse groups by '#v', which 'ee' does not have (it has #e, value)"
```

**With R-D5:** core follows `#e` to `e`, then `e`'s `#v` to `v`, and gives one
row per visit, holding all its readings' items. Grouping is refused only when
a row would trace to several rows of `s` (a `collapse` or `distinct` in
between).

| Alternative | Why not |
|---|---|
| every `expand` carries all its input's `#` columns | grids grow a `#` column per level, and it only moves the problem |
| collapse one level at a time | works, but needs a step per level for something core can follow |

**Recommended:** yes.

### J-D5. Regrouping gives a row for every row of `s` — decided 2026-10-27

**Today:** a record whose list was empty vanishes on the way back:

```python
# tags: ["a", "b"], [], "c", None        (rows 0…3)
k["te"] = op("identity")[mod.expand()](wf["tg"])           # a, b (#tg 0) · c (#tg 2) · None (#tg 3)
k["tb"] = op("gather")[mod.collapse(by="#tg")](wf["te"])
# rows 0, 2, 3: ["a", "b"], ["c"], [None]        ← row 1 (the []) is gone
```

**With J-D5 (and J-D3):**

```
#  tags
0  [a, b]
1  []          ← an empty group: nothing traced to row 1
3  []          ← None gave no rows (with a warning)
```

Row 2 fails, *"not a list: str"*, unless an `as_list` step came first.

**Recommended:** yes.

### R-D3 (decided). Unpacking what core packed gives back the same samples

For reference. `expand(gather(t))` gives back `t`'s ids `0…3` and lines up
with `v`. Today it gives new ids `"0.0"…"0.3"`, and `zip_` with `v` is
refused (M9, fixed in step 2).

---

## Step 7: the missing moves

### R-D2. `mod.pack(columns=…)`: a row into a dict, whatever its width — decided 2026-10-27, named `pack`

**Today:** `identity` under `map` packs a row only when it has two or more
columns:

```python
op("identity")[mod.map()](wf["v"])      # {'name': 'Ada', 'ward': 'A', 'temp': 37.0}, …
op("identity")[mod.map()](wf["t"])      # 37.0, 38.5, …      ← one column: the bare value, not a dict
```

**With R-D2:** `mod.pack(columns=["temp"])(wf["t"])` gives `{"temp": 37.0}`
every time. `widen` is its inverse, and drops the dict column it spread
(today it keeps it beside the fields, G10).

**The name is yours:** `pack` (tidyr's word), `record`, `nest`, `to_dict`.

**Recommended:** yes, named `pack`.

### R-D4. `expand(columns=[…])` unpacks several lists together — decided 2026-10-27

**Today:** `expand` without a tool unpacks one value per row. A row with
several columns arrives as one dict, which isn't a list, so it isn't
unpacked:

```python
# ward  name          temp
# A     [Ada, Cy]     [37.0, 39.1]
op("identity")[mod.expand()](wf["l"])
# one row: {'ward': 'A', 'name': ['Ada', 'Cy'], 'temp': [37.0, 39.1]}    ← nothing unpacked
```

**With R-D4:**

```python
mod.expand(columns=["name", "temp"])(wf["l"])
# #  #l  ward  name  temp
# …  0   A     Ada   37.0
# …  0   A     Cy    39.1         ← item j of each list in one row; ward repeated
```

A row whose lists differ in length fails (V2). This form calls no tool, so it
is a reshape, and reshapes carry columns (`ward` here).

**Decided (owner, 2026-10-27): it keeps the other columns of the grid it is
given, so the reference decides which.** `(wf["l"])` keeps `ward`;
`(wf["l"][cols[["name", "temp"]]])` keeps nothing else, because nothing else
was referenced.

**This refines your 2026-10-20 decision**, that `expand` outputs only its
results. That stays true for `expand` with a tool. The tool-less form is a
reshape and carries.

| Alternative | Why not |
|---|---|
| never carry | works (`zip_` with the parent through `#l`), but every unpack needs a second step |

**Recommended:** yes.

---

## Step 8: uneven data

### J-D1 and ⚠ J-D2. `absent`, and `widen` takes every key — decided 2026-10-27

**Today:**

```python
# meta: {"x": 1, "y": 2}, {"x": 3}, {"x": None}, {"x": 4}
mod.widen(columns=["x", "y"])(wf["m"])
# fails rows 1–3: "KeyError: the record has no 'y' (it has x)"
# x: 1.0, 3.0, NaN, 4.0      ← ints became floats; null (row 2) and missing look the same
```

**With J-D1 and J-D2:**

```
#  x     y
0  1     2
1  3     ·        ← absent: there was no "y" key
2  None  ·        ← x is null (a known value); y absent
3  4     ·
```

- `widen()` with no `columns=` takes every key seen.
- `x` stays an integer column (`Int64`).
- Nothing fails.
- `pack(widen(d))` gives back exactly `d`: absent keys left out, the null
  kept.

**`absent` is a new cell state.** The app must show it, for example as a dim
`·`. A tool given an absent cell gets the parameter's default, if it has one.

| Alternative | Why not |
|---|---|
| a missing key becomes `None` (no new state) | simpler, but packing back adds `"y": None` to records that had no `"y"`: not lossless |

**Recommended:** both.

**Changes for users:** rows missing a key stop failing.

### ⚠ J-D3. `expand` never tidies data for you — decided 2026-10-27

**Today:**

```python
# tags: ["a", "b"], [], "c", None
op("identity")[mod.expand()](wf["tg"])
# a, b · c · None        ← "c" is treated as ["c"]; None as [None]
```

**With J-D3:**
- `"c"` fails its row, *"not a list: str"*, and the other rows run.
- `None` gives no rows, with a warning: *"1 row held None, not a list"*.
- If a bare value means a one-item list, say so with a step:
  `as_list[mod.map()](wf["tg"])`, then `expand`.

| Alternative | Why not |
|---|---|
| keep wrapping | `"c"` and `["c"]` can't be told apart afterwards: a silent loss |
| wrap, with a warning | the loss happens anyway; the warning is easy to miss |

**Recommended:** yes.

**Changes for users:** a bare value or `None` where a list belongs no longer
expands to a row.

### ⚠ J-D4. `expand` of a dict gives `key`, `value` rows — decided 2026-10-27, named `gather_dict`

**Today:**

```python
# scores: {"2026-01": 3, "2026-02": 4}, {}
op("identity")[mod.expand()](wf["sc"])
# two rows, each holding its whole dict
```

**With J-D4:**

```
#    #sc  key      value
0.0  0    2026-01  3
0.1  0    2026-02  4         ← the {} gives no rows
```

It packs back with `collapse(by="#sc")` and a built-in reducer that builds a
dict. **Its name is yours:** `gather_dict`, `to_dict`, `mapping`.

`widen` stays the verb for records, whose keys are variables. `expand` is the
verb for mappings, whose keys are data, and `widen` warns when a dict's keys
look like data.

**Recommended:** yes, with `gather_dict`.

---

## Step 9

### R-D8. The plan says how to go back — decided 2026-10-27

**Today:** a plan has `rows`, `columns` and `types`.

**With R-D8:** it also has `inverse`:

```python
k.step("srt").output.plan["inverse"]    # {"kind": "rebuild", "formula": …the step that restores v's order…}
k.step("f").output.plan["inverse"]      # {"kind": "trace"}   (a filter)
k.step("tb").output.plan["inverse"]     # {"kind": "opaque"}  (a table)
```

The app can offer "undo this reshape" as a new step wherever it says
`rebuild`.

**Recommended:** yes.

---

## Step 10

### The property test: `hypothesis` — decided 2026-10-27, as a dev dependency only

The property test (L40) generates valid grids and chains of verbs, and checks
the guarantees on every result.

| Option | For | Against |
|---|---|---|
| **`hypothesis`** (a dev dependency) | when a check fails, it shrinks the example to the smallest grid and chain that still fails, so the bug is readable | one more dev dependency (not a runtime one) |
| a seeded random generator | no new dependency | a failure is a large random case you have to cut down by hand |

**Recommended:** `hypothesis`, as a dev dependency only.

---

## Already decided

| | Decision | Built |
|---|---|---|
| R-D3 | unpacking what core packed gives back its ids and origin | step 6 |
| R-D6 | core never parses ids | step 2 ✓ |
| R-D10 | `#` columns are grid columns, under the five guarantees | step 2 ✓ for `expand`; step 5 for the rest |
| R-D11 | `#` is the row id | step 2 ✓ |
