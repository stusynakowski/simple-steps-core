# Referencing and assignment: a proposal

> **Status: a proposal, nothing built** (owner, 2026-10-30). It formalises
> the owner's thoughts on how steps, variables, rows and cells are referenced
> and handed to tools, so the rules can be decided one by one. "Today" lines
> were run at `30d83ff`. It answers V1, V3 and V4 of
> [to-revisit.md](to-revisit.md), and touches V2 and V5.

## 1. The goal

A formula should say, by reading it, what each tool receives and how many
times it runs. No guessing which column, no meaning that depends on where a
reference sits, and nothing core decides later that the formula didn't say.

The data stays a tidy table: **rows are samples, columns are variables, a
cell holds one value**. Where that isn't enough, the exception is named and
bounded (§5).

The syntax should feel like a spreadsheet's (a table, its columns by name,
its rows by number) and read as plain Python (`wf["s"]["temp"][3]` is
indexing), without pandas' habits leaking through.

## 2. The picture

Every step's output is one of three shapes. `#` columns aren't variables and
don't count.

| Shape | What it is | Spreadsheet | Python |
|---|---|---|---|
| **cell** | 1 row × 1 variable | one cell | a value |
| **vector** | n rows × 1 variable | one column | a list |
| **table** | n rows × m variables (m > 1) | a table | a list of dicts |

And four ways to reach into one:

| Reference | Gives | Example |
|---|---|---|
| `wf["s"]` | the step, whatever its shape | the cell, the column or the table |
| `wf["s"]["temp"]` | one variable: a vector | the `temp` column |
| `wf["s"][3]` | one row: a cell (vector step) or a record (table step) | row 3 |
| `wf["s"]["temp"][3]` = `wf["s"][3]["temp"]` | one cell | row 3's temperature |

**A string is always a variable; an integer is always a row.** That is what
makes the brackets unambiguous, and why the two rules below (N2, N3) are
needed.

## 3. Proposed rules

**N1. A step is a cell, a vector or a table, and its plan says which before
it runs.** The shape comes from the plan (declared types, `mod.expect`). A
reference that needs the shape of a step whose shape is unknown is a
problem until the step runs or declares it (see Q6).

**N2. Variable names are strings, and only strings.** A tool that returns a
table with other column names (`pd.DataFrame([[1, 2]])` has `0`, `1`) is
refused, with the fix: name them, `mod.name(["var0", "var1"])`. A name is
not empty, doesn't start with `#` (core's), and (Q3) is a valid Python
identifier.
*Today:* `0`, `1` are silently turned into the strings `"0"`, `"1"`.

**N3. Rows are referenced by integer, 0 to n-1, in the step's order.** `[3]`
is the fourth row as the step shows it. Negative numbers count from the end
(`[-1]`), ranges are half-open (`[0:3]`), and past the end is refused, never
trimmed. A row's number is its id **within that step**; how it relates to
rows of other steps is held only in `#` columns (N9).
*Today:* `[3]` is a row id, which follows a row through `sort` and
`filter`; `expand` makes string ids (`"0.1"`); ranges are positions.

**N4. A single variable is named after its step.** `k["temp_f"] =
to_f(wf["p"]["temp"])` writes one variable, `temp_f`, so `wf["temp_f"]` *is*
that variable: the vector, and also the step. A step that writes several
variables (a record, a table) names them as they are named (fields,
columns, `mod.name`).
*Today:* the variable is `value` unless named.

**N5. A value assigned to a step is one cell.** `k["x"] = [1, 2, 3]`,
`k["cfg"] = {"limit": 38}`, any JSON literal: a 1×1 step holding that
value. To make rows from it, `expand` it. (*Today:* the same.)

**N6. What a tool receives follows from the reference's shape and the
parameter's type, and nothing else** (§4). A vector given to a parameter
that takes one value means *one call per cell*: a mapping is implied. A
vector given to a `list` parameter means *one call with the whole list*.

**N7. Core never picks a variable for you.** A table given where one value
is expected is refused, naming the variables to choose from:
`to_f(wf["p"])` → *"p has name, temp: pass one, to_f(wf["p"]["temp"])"*. A
step with exactly one variable needs no choice.
*Today:* parameters bind to columns of the same name, silently.

**N8. Variable names structure the data; they aren't arguments.** A name
says *which* values go where. A tool doesn't receive names as values unless
the formula says so explicitly: `wf["p"].header` (the names, as a list), or
a tool that declares it wants the whole row (`row: dict`, a record type).
Binding a tool's parameters to columns *by name* is opt-in (Q2), for
workflows built around fixed variable names.

**N9. Rows of different steps line up only through a link core recorded.**
Unchanged from rule 6: the same step; a step core knows is row-aligned with
its input (`map` keeps the input's rows in order); or a `#` column. Equal
length is never enough, and equal row numbers between unrelated steps
aren't a match. Two vectors from unrelated steps, given to one tool, are
refused: `join` them first.

**N10. Only the verbs that change the rows are written.** Whether a call
runs once or once per cell follows from the types (N6), so `map` and the
whole-list call need no verb. `filter`, `expand`, `collapse(by=…)`,
`sort`, `slice`, `distinct`, the reshapes and the combines are always
written. `auto` goes (Q4).

**N11. The formula prints exactly what will happen.** No hidden modifier
(*today* `auto` adds `breaker(after=5)` unseen). Defaults that apply are
shown in the plan.

**N12. Tools receive plain Python values.** `float`, `int`, `str`, `None`,
`list`, `dict`: never `np.float64`, `NaN` or a pandas object, unless the
parameter asks for a `pd.DataFrame` or `pd.Series`.
*Today:* a row passed as a `dict` holds `np.float64(38.2)`.

## 4. What a tool receives

Rows: the reference's shape. Columns: the parameter's declared type. "Map"
means one call per cell (or per row), results in a vector aligned with the
reference.

| | `T` (one value) | `list[T]` | `dict` / a record type | `pd.DataFrame` |
|---|---|---|---|---|
| **cell** | one call, the value | one call, if the cell holds a list | one call, if the cell holds a dict | one call, if the cell holds a table |
| **vector** | **map**: a call per cell | one call, the whole list | refused | refused (Q5) |
| **row of a table** | refused: pick a variable | refused | one call, the row as a dict | refused |
| **table** | **refused** (N7): pick a variable | refused | **map**: a call per row, each as a dict | one call, the table |
| **unknown shape** | Q6 | Q6 | Q6 | Q6 |

Several references in one call:

| Given | Means |
|---|---|
| a vector and cells | map over the vector; each cell is the same in every call |
| two vectors, both to `T` | map over both, row by row, **only** if they line up (N9); otherwise refused |
| a vector to `T` and a vector to `list[T]` | map over the first; the second whole in every call |
| a table to `dict` and a vector to `T` | map over rows, paired by N9 |

A reduction is then just a type: `def mean(temp: list[float])` given
`wf["p"]["temp"]` runs once. Per group is still written:
`mean[mod.collapse(by="ward")](wf["p"]["temp"])` (Q7).

## 5. The exceptions to tidy tables, all of them

| Exception | Where it's bounded |
|---|---|
| a cell may hold a list, a dict or a table | it stays one value until `expand` (rows), `widen` (variables) or a tool unpacks it; `[i]` and `["x"]` never reach inside a cell (Q8) |
| a 1×1 step is a cell, not a table of one | N1: `wf["s"]` is the value |
| a single variable takes its step's name | N4 |
| `#` columns sit beside the variables | they aren't variables: never counted, never passed, never named by a tool (rule 2); only `#`-aware verbs read them (`collapse(by="#s")`) |
| a row as a record | only to a parameter that declares `dict` or a record type (N8) |

Nothing else bends.

## 6. A session under these rules

```python
k["p"] = patients[mod.source()]()                 # table: name, temp, ward
k["limit"] = 38.0                                 # cell

k["temp_f"] = to_f(wf["p"]["temp"])               # vector temp_f: one call per cell
k["hot"] = is_hot[mod.filter()](wf["p"]["temp"], limit=wf["limit"])
                                                  # rows of p where is_hot; a written verb
k["avg"] = mean(wf["p"]["temp"])                  # cell: mean takes list[float], one call
k["by_ward"] = mean[mod.collapse(by="ward")](wf["p"]["temp"])
k["label"] = describe(wf["p"])                    # describe(row: dict): one call per row

wf["temp_f"][0]                                   # a cell: row 0 of temp_f
wf["p"]["temp"][0] == wf["p"][0]["temp"]          # the same cell, saved the same way

to_f(wf["p"])                                     # refused: p has name, temp, ward; pick one
zip_(wf["p"]["name"], wf["hot"]["temp"])          # refused: hot's rows don't line up with p's
```

## 7. What would change from today

| Today | Proposed | Cost |
|---|---|---|
| parameters bind to columns by name (`to_f(wf["p"])` reads `temp`) | pick the variable: `to_f(wf["p"]["temp"])` (N7); by name only on request (Q2) | every existing formula that relies on it is rewritten |
| `auto` chooses the verb at run, and is saved as `auto` | types decide map vs one call; row-changing verbs are written (N10) | `is_hot(wf["p"])` no longer filters; it maps to a bool vector |
| a selection can't be an input: *"make it its own step"* | `to_f(wf["p"]["temp"])` is the normal form | references in the input slot, saved and reloaded |
| `wf["s"]["x"]` refused; columns go through `cols["x"]` | a string in brackets is a variable | `cols[…]` / `rows[…]` become optional or go (Q9) |
| `[3]` is a row id; ids follow rows through `sort`, `filter`; `expand` ids are strings | `[3]` is the fourth row of that step; every step numbers its rows 0…n-1; `#` columns hold the links | `sort` and `filter` must write a `#` column (as `expand` does); a pick names a position, so "row 3" can be another sample after an upstream change (Q1) |
| `wf[0]` is the first step | `wf[…]` takes step names only (Q10) | |
| the single variable is `value` | it is the step's name (N4) | renaming a step renames its variable (Q11) |
| non-string column names become strings | refused, with the fix (N2) | |
| a row dict holds numpy values | plain Python values (N12) | |

## 8. Concerns

1. **Row numbers versus stable ids.** Under N3, `wf["hot"][0]` is "the first
   hot row", whichever sample that is now. That's what a spreadsheet does,
   and what the owner asked for. What it costs:
   - a click or a pick doesn't follow a sample: after the data changes,
     the same number can be another patient;
   - per-row staleness ("only rows 2 and 5 re-run") can't be keyed by
     number. Core would keep an internal key per row (the input row, and
     the position within it for `expand`) that is never shown or typed. That
     key is core's business, like a cache.
   The alternative keeps today's ids and makes only ranges positional (Q1).
2. **A step renamed renames its variable** (N4), so `wf["temp_f"]["temp_f"]`
   in another step must follow the rename. References already follow
   renames (K29); the variable's name would too.
3. **Shape known before running** (N1). Sources returning an undeclared
   DataFrame have no shape until they run; every reference to them would be
   unresolved until then (Q6).
4. **The table → `dict` mapping** is the one place a whole row reaches a tool.
   It's explicit (the parameter declares it), but it is where variable names
   become a tool's keys (N8's exception).
5. **Python's `sum`, `len`, … aren't tools.** `sum(wf["integers"])` can't
   mean anything to core: it would call Python's `sum` on a reference.
   Built-ins (`total`, `count`, …) or user tools are the way; the formula
   bar can refuse names it doesn't know.

## 9. Questions

| | Question | Recommended |
|---|---|---|
| Q1 | **Row numbers or stable row ids** for `[i]`? | numbers, as you said (N3), with core's internal per-row key for staleness and lineage; `#` columns stay the visible links |
| Q2 | Binding parameters to columns **by name**: never, or opt-in? | opt-in, explicit: `tool[mod.map(by_name=True)](wf["p"])`, for workflows built around fixed variable names; refused when a name is missing |
| Q3 | Variable names: any string, or **identifiers** only? | identifiers (`temp_f`, not `temp f`), so a formula reads as Python and every name can be typed; others refused with a suggested name |
| Q4 | Remove `auto`, or keep it as a printed suggestion? | remove from formulas; the UI may *suggest* a verb (`k.infer_verb`), and what's saved is what was chosen |
| Q5 | A vector to a `pd.DataFrame` parameter: refused, or a one-column table? | refused: say `pd.Series` or `list` |
| Q6 | A reference to a step of unknown shape: refused, or decided at run? | a warning when declared, decided when the step runs, re-checked after (as G13 does for columns); the plan says *unknown* until then |
| Q7 | `collapse(by="ward")` on a vector: where does `ward` come from? | from the vector's own step (`p`): a vector carries its step's other variables for `by=` only, never to the tool |
| Q8 | Can `[i]` / `["x"]` reach inside a cell holding a list or dict? | no: a cell's contents are the tool's; reach in with `expand` / `widen` |
| Q9 | Keep `cols[…]` / `rows[…]`? | keep only for what brackets can't say: several variables (`["a", "c"]` is fine; `cols["a":"c"]` is a range of names) and string row keys after `collapse` |
| Q10 | `wf[0]` as "the first step"? | remove: steps by name only, so an integer in brackets is always a row |
| Q11 | N4: name the single variable after the step, or keep `value`? | after the step; a `mod.name` still wins |
| Q12 | `collapse(by="ward")` gives one row per ward: is its row reference the number (`[0]`) or the key (`["A"]`)? | the number, by N3; the key is a variable (`ward`), so `filter` picks a ward. (*Today* the key is the row id.) |

## 10. How we'd know it's airtight

The same way reshaping was closed (reshaping-plan.md):

- one law per row of §4's tables, and per rule N1–N12, in a test file, each
  marked expected-to-fail until built;
- every refusal names its fix (principle 6), checked by the law;
- the property test generates formulas from these references and checks:
  each saves, reloads and prints back the same; two spellings of one
  reference (`["x"][i]`, `[i]["x"]`) save the same; nothing is passed that
  §4 doesn't allow;
- the reshaping laws are re-run under the new row numbering (N3), with the
  internal key doing what row ids did for staleness and lineage.
