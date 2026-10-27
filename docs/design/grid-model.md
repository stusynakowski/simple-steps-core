# The grid model

> Proposed 2026-10-26. Behaviour marked *today* was run at `86170a3`
> (scripts in §8). This is what a step's output is and how each modifier
> shapes it. The words are defined in [object-model.md §1](object-model.md#1-the-words).

## 1. Three ideas

1. **Every output is a grid.** A step's output is a pandas DataFrame: named
   columns, rows with a row id, one value per cell, and one cell state per cell.
   A step that produces one value is a 1×1 grid. An **empty step** (declared,
   no expression yet) is a 1×1 grid holding `"empty"`; a step that ran and
   kept no rows is a 0×n grid with its columns.
2. **A tool call produces one cell.** A tool is a plain function that takes
   values and returns a value. It never sees a row or a grid, unless it asks
   for the whole table (`mod.table()`).
3. **The modifier decides the shape.** How many times the tool is called, what
   it is given, and how its results become rows and columns is decided by the
   step's shape verb, not by the tool or by what it returns.

## 2. The parts of a grid

A grid is meant to be a tidy table: columns are variables, rows are
observations ([outputs-and-reshaping.md §1](outputs-and-reshaping.md#1-the-grid-is-a-tidy-table)).

| Part | What it is |
|---|---|
| **column** | named by a string. Each column has a type: declared by the tool's return type, else `unknown` until it runs, then what was observed (K27) |
| **row id** `#` | the DataFrame's index: a row's stable label, shown and referenced as the `#` column (owner, 2026-10-27; [reshaping.md](reshaping.md) R-D11). Verbs that keep rows keep their ids, so a row can be followed through `filter` and `sort` |
| **row number** | a row's position, 0…n-1, as displayed. It has no name: never stored or used to pair rows |
| **value column** | where a computing verb writes the tool's results: `value` unless named with `mod.name`, or one column per field for a record ([outputs-and-reshaping.md](outputs-and-reshaping.md)) |
| **cell state** | `known`, `maybe`, `pending`, `blocked`, `failed`, `invalid`. A row's state is its worst cell's |
| **note** | per row, when there's something to say: the error, its cause, attempts, whether it was caught |

**Which steps carry their input's columns** (owner, 2026-10-27). Steps that
make new values per observation output only those values (`map`, `expand`,
`collapse`, `sweep`, `table`): `dbl[mod.map()](wf["r"])` has one column,
`value`, on `r`'s row ids, and `zip_` puts it beside its input. Steps that keep
the observations and filter or label them carry the columns: `filter`, the
reshapes and `group`, which adds its key as one more column (built in phase
4, 2026-10-27).

## 3. How a tool meets a row

Under a row-wise verb (`map`, `filter`, `expand`, `group`) the tool is called
once per row:

1. Each **parameter is bound to the column of the same name.** Columns the tool
   doesn't name are not passed.
2. **Arguments** fill the rest: `scale[mod.map()](wf["r"], weight=2)`.
3. An argument that names a column overrides it for every row, with a warning
   (*today*: *"n=100 overrides the 'n' column of 'r' for every row"*).
4. An argument that is a **cell reference** (`wf["o"][0][cols["w"]]`) is that
   one value for every row (*today*).
5. An argument that is a **column reference** (`wf["o"][cols["w"]]`) is paired
   row by row, by row id, when the parameter is a scalar type; it is passed
   whole when the parameter is `list`, `Series` or `DataFrame` (K19, phase 4).
6. `**kwargs` receives the whole row; `*args` is refused.

## 4. What each verb does

The **shape verbs** call a tool. At most one per step. When a tool returns several values
(a record, a list of records, a table), see
[outputs-and-reshaping.md §3](outputs-and-reshaping.md#3-tools-that-return-several-values).

| Verb | Tool's form | Rows | Columns out | Row ids out |
|---|---|---|---|---|
| `source` | `() -> anything` | what it returns | a DataFrame's columns, else `value` | 0…n-1 |
| `map` | `(columns…) -> value` | same | `value` | kept |
| `filter` | `(columns…) -> bool` | at most n | the input's | kept, for rows that pass |
| `expand` | `(columns…) -> list` | one per item | `value` | `"i.j"`: item *j* of row *i* |
| `group` | `(columns…) -> key` | same | the input's columns plus the key (`group`, or named with `mod.name`); a key named like an input column is refused unless `replace=True` | kept |
| `collapse` | `(acc, columns…) -> acc`, or a built-in reducer | 1, or one per `by=` group | `by` column and `value`; *proposed:* a built-in reducer gives one column per variable ([reshaping.md](reshaping.md) R-D1) | `0`, or the key with `by=` (D3) |
| `widen` | a cell holding a record or sequence | same | one per field (`columns=`), or `c0, c1, …` for sequences | kept |
| `table` | `(df: DataFrame) -> DataFrame` | what it returns | what it returns | what it returns |
| `sweep` | `(settings…) -> value`, no input | one per combination | one per swept setting, and `value` | 0…n-1 |
| `auto` | (none written) | the inferred verb's | | |

**Inferring the verb.** With no verb written, core reads the tool's types:
`-> bool` filters, `-> list` expands, a first parameter named `acc` (or `accumulator`, `memo`, `carry`) collapses,
anything else maps. The step is saved as `auto`, and the verb it resolved to is
recorded on the output.

The **reshapes** call no tool, and are written on a reference:
`mod.sort(by="n")(wf["r"])`.

| Reshape | Settings | Rows | Columns | Row ids |
|---|---|---|---|---|
| `select` | `columns=` and/or `rows=` | chosen | chosen | kept |
| `drop` | `columns=` | same | minus those | kept |
| `rename` | `columns={old: new}` | same | renamed | kept |
| `sort` | `by=`, `ascending=` | same, reordered | same | kept |
| `slice` | `start=`, `stop=`, `at=` | at most n | same | kept |
| `distinct` | `columns=` | at most n | same | kept |

The **combines** read several steps, call no tool, and are the only way a step
reads more than one input.

| Combine | Settings | Result | Row ids |
|---|---|---|---|
| `join(a, b, on=…)` | `on=`, `how=` (`inner`), `suffixes=` | matching rows, both sides' columns; row count unknown until run | 0…n-1 |
| `stack(a, b, …)` | `join=` (`outer`: union of columns; `inner`: shared ones) | `a`'s rows then `b`'s | 0…n-1 |
| `zip_(a, b, …)` | — | side by side; unequal lengths and a shared column name are refused | *today* by position; by row id under K19 |

The **built-in tools**: `identity` (the step's input, unchanged), and the
reducers `count`, `total`, `gather`, `first`, `last` for `collapse`.

## 5. How a step runs, cell by cell

1. **Declared:** the step is checked and staged. Its output is a plan: rows,
   columns and types, each `exact`, `bounded` or `unknown`, with the reason
   (*"expand: how many items each row returns is only known by running"*).
2. **Run:** for each unit (a row, a group or the whole table), the tool is
   called through its execution modifiers. A cell is `known` when its call
   returned, and `failed` when it raised.
3. **Failure flows, cheaply.** A row that failed upstream reaches the next
   step as `blocked`, with its cause; the tool is not called for it. A step's
   other rows still run.
4. **Stopping.** A failed row stops `run_all`, unless the step handles it
   with `try_except` (§5.1).
5. **Versions.** When a step finishes, its output gets a version (a hash of its
   data) and records the versions it read. If any of those change, the step is
   `stale`: its output is kept and shown, and nothing recomputes on its own.

### 5.1 Handled failures

`try_except` decides what a failure becomes. Decided 2026-10-26:

| Written | The row | Step state | Stops `run_all` |
|---|---|---|---|
| no `try_except` | `failed` | `failed` | yes |
| `mod.try_except()` | `failed`, note says `caught` | `failed` | no; rows that read it downstream are `blocked` |
| `mod.try_except(default=d)` | `known`, holding `d`; the note keeps the error | `completed`, **with a warning** naming how many rows used the default | no |
| `mod.try_except(on=["ValueError"], …)` | as above, for those errors; others are not handled | | |

*Today* all of this holds except the warning.

**The default's type.** A default becomes a value in the column, so it must fit
the column's type (the tool's declared return type, K27):

| Default | Column type | Core says |
|---|---|---|
| fits the return type (`0` for `-> int`) | the return type | nothing extra |
| `None` | `T \| None` (missing is part of the type, C14) | nothing extra |
| doesn't fit (`"n/a"` for `-> int`) | `int \| str` | a **warning when declared**: *"default 'n/a' is str, but risky returns int; the column will be int \| str"*. In strict mode, a problem |
| the tool's return type is unknown | the observed type of the other rows, joined with the default's | nothing extra |

*Today* a default that doesn't fit is accepted silently: `default="n/a"` on
`-> int` makes the column `object`, with no warning (G6).

### 5.2 Where an error happened

A failed or handled row's note says **where** it failed, so the user can see
which layer gave up, not only the exception:

| `where` | Means |
|---|---|
| `tool` | the tool raised; the note has the exception |
| `timeout` | the call ran past `seconds=` |
| `retry` | every attempt failed; the note has `attempts` and the last error |
| `breaker` | not called: the breaker had tripped after too many failures |
| `expect` | the output broke what `expect` promised |
| `upstream` | `blocked`: an input row failed; the note names the step and row |

*Today* notes have the error, `cause`, `caught`, `attempts` and `unit`, but no
`where`.

## 6. Modifiers are decorators, applied at run time

A modifier is like a Python decorator on the tool, except that it is **stored
as data in the step and applied each time the step runs**. Changing a step's
modifiers changes how it runs next time without touching the tool, and the
same tool can be bare in one step and decorated in another.

**Modifiers read left to right as decorator layers, outermost first**
(decided 2026-10-26). A modifier list is a stack of decorators written on one
line:

```python
dbl[mod.map(), mod.retry(times=2), mod.timeout(seconds=1)]

# is the same as
@mod.map()
@mod.retry(times=2)
@mod.timeout(seconds=1)
def dbl(n): ...

# which is map(retry(timeout(dbl)))
```

The leftmost modifier is the outermost layer. Each one wraps everything to
its right, so `map` calls `retry(timeout(dbl))` once per row, and `timeout`
applies to each attempt.

| Class | Changes | Modifiers | In the step's hash |
|---|---|---|---|
| **shape** | rows and columns | the shape verbs, the reshapes | yes |
| **execution** | how each call runs | `retry`, `timeout`, `breaker` | yes |
| **error handling** | what a failure becomes | `try_except` (a default value, which errors) | yes |
| **expectation** | what staging promises and checks | `expect` (rows, columns) | yes |
| **naming** | the names of the columns a call writes | `mod.name` ([outputs-and-reshaping.md §4](outputs-and-reshaping.md#4-naming-outputs-modname)) | yes |
| **observation** (K23, planned) | nothing; reports | progress, to a callback the host passes in | no |
| **scheduling** (planned) | when the step runs | an autorun modifier, to be designed ([interactive-sessions.md §6.2](interactive-sessions.md#62-an-autorun-modifier-planned-to-be-designed)) | no |

Two rules follow:

- **Everything that can change the output is in the spec and the hash.**
  `retry` and `timeout` can change which cells fail; `try_except` changes what a
  failure becomes.
- **An observing modifier never changes the output,** so it isn't hashed, and
  it can be **saved in a step** (decided 2026-10-26), and the host can also
  attach one for a single run without editing the step
  (`k.run("f", observe=[progress(cb)])`).

**Order is meaning.** Each modifier wraps everything written after it, so
where an execution modifier is written decides what it covers:

| Written | Means |
|---|---|
| `dbl[mod.map(), mod.retry(times=2)]` | retry **each row's call** |
| `dbl[mod.retry(times=2), mod.map()]` | retry **the whole step**: if any row fails, every row runs again |

Both are allowed (decided 2026-10-26). The second is rarely what's meant, so
it gets a **warning when declared**: *"retry is written before map, so it
retries the whole step, not each row"*. A failure's note says which layer it
came from (§5.2).

**One shape verb per step.** A step shouldn't hide what it does: two shape
verbs in one step would hide the grid between them, so it couldn't be seen,
referenced, planned or followed row by row. The tool should be the
abstraction; the step only says how it meets the grid. So the step is refused, with a message that says how to
split it: *"2 shape verbs in one step (filter, map): put each in its own step;
group them with a stage to manage them as one"*. Long sequences of steps are
consolidated with **stages** ([object-model.md §4.11](object-model.md#411-stage)),
not by stacking verbs in one step.

Modifier settings are literals, never references: a setting decides a step's
shape, and a shape that depends on data can't be planned before it runs. The
one exception is a tool as a setting (`collapse(by=key_tool)`, 008 C2; `group(by=…)`
goes in phase 4, since the step's own tool computes the key).

## 7. Row ids, per verb

Row ids are what make a reference stable: a selection or a column argument
should mean the same rows after an upstream sort. The rule (K19): **the row id
is the output's index; verbs that keep rows keep it; verbs that make rows
define it.**

| Verb | Rule | Today |
|---|---|---|
| keeps rows: `map`, `filter`, `group`, `widen`, reshapes | the input's ids | as the rule |
| `zip_` | pairs by row id | as the rule (K19, phase 4) |
| `expand` | `"i.j"` from the parent row `i`: a label; *proposed:* the parent is in `#v`, and an unpack of a list core packed gives back its ids ([reshaping.md](reshaping.md) §5.1, §6) | as the rule |
| `source` | the tool's own index if it set one, else 0…n-1 | **differs:** a tool's own index becomes a column named `index`, and ids restart at 0 |
| `collapse` | `0`, or the key with `by=` (D3) | as the rule (phase 4) |
| `sweep`, `table` | 0…k-1 (`table`: what the tool returns) | 0…k-1 |
| `join`, `stack` | 0…N-1, new rows; each cell's lineage points at the input cells it came from (decided 2026-10-26), through `#` columns ([reshaping.md](reshaping.md) §5.1) | 0…n-1; lineage not stored |
| selection `wf["srt"][0]` | by row id | **differs:** by position (picked row id 1 after a sort) |

## 8. Found while checking (to fix, in phase 4)

Run on `86170a3`, 2026-10-26:

| # | What | Run |
|---|---|---|
| G1 | `group(by="city")` passes declaration, then every row fails with `TypeError: 'str' object is not callable`. *Done (phase 4, 2026-10-27):* `group` drops `by=`, since its own tool computes the key; a column name is refused when declared: *"ward is already a column: collapse(by='ward')"* | `dbl[mod.group(by="city")](wf["r"])` |
| G2 | `stack` of grids with different columns fills `NaN` and turns integers into floats (`10.0`), against C14 (missing is `None`) | `stack(wf["r"], wf["o"])` |
| G3 | A source tool's own index is turned into an `index` column instead of being kept as row ids | §7 |
| G4 | `to_source()` loses forms: a literal step `[3, 1, 2]` prints as `op("identity")[mod.source()]()` (the value is missing from the text); reshapes print as `op("identity")[mod.sort(…)](…)` rather than `mod.sort(…)(…)`; a selection step prints as `mod.select(rows={…})` rather than `wf["r"][0:2]` | [step-expressions.md §5](step-expressions.md#5-printing-to_source) *Done (phase 4, 2026-10-27): every form prints as written; see step-expressions.md §5* |
| G5 | `collapse` with `(acc, n)` and no `initial=` starts `acc` at `None` and fails | `tot[mod.collapse()](wf["r"])` |
| G6 | a `try_except` default that doesn't fit the return type is silent: `default="n/a"` on `-> int` gives an `object` column | §5.1 |
| G7 | no warning for a step that used a default, for an execution modifier written before the verb, and no `where` in notes | §5.1, §5.2, §6 |

## 9. Open

- **Row ids from sources** that set their own index (G3).
