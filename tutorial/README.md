# Learning simple-steps-core, from the top

> A walkthrough of what the library is for, what it refuses to do, and why,
> one part at a time. Every claim is a lesson in [tutorial.py](tutorial.py),
> run against the code: `.venv/bin/python tutorial/tutorial.py`. Written
> 2026-11-03 at `2bd150e`: 109 lessons, **89 ✓ · 17 ✗ · 3 ?**. What the app
> asked for is checked by [handover.py](handover.py) (§5), and everything at
> once by `scripts/sweep.py` (§6). The rules in full are in
> [docs/design/model.md](../docs/design/model.md).

## 0. The idea: a spreadsheet's usability, inside Python's limits

People use Excel because it is easy to follow. Every value has a name, a
formula points at earlier values, you see the result straight away, and one
bad cell shows `#VALUE!` without breaking the sheet. We want that for data
work whose formulas are **Python functions**. Python functions can't be used
the way Excel cells are, for four reasons:

| Python's limit | What it rules out | What we do instead |
|---|---|---|
| **A function is opaque.** Core can't see inside it | tracing a value through the function, or recomputing only the part that changed | core handles everything *around* the call: which rows go in, what comes out, and where each output row came from (lineage) |
| **Running isn't free.** A function may be slow, cost money, or call the outside world | recalculating everything after every keystroke, as Excel does | **checking is immediate and running is on request.** An edit marks readers `stale` and keeps their old values. You run when you choose |
| **The workflow is linear.** Steps run in order, and each one reads only earlier steps | cycles, and forward references | a step that reads itself, a later step or a missing step is a problem, never a cycle |
| **A step is a whole grid, not one cell** | Excel's freedom to write a different formula in each cell | one expression per step, applied by a **verb** (per row, per group, once…) |

What follows from that, in Excel's terms:

| Excel | Here | Lessons |
|---|---|---|
| a sheet and its function list | a **kernel** and its **catalog** | K1–K2 |
| a typed-in cell, a pasted table | a **literal**, a **DataFrame**, a **source** tool | D1–D11 |
| `A3`, `A1:A5`, a filter | a **pick**: `wf["s"][3]`, `[1:3]`, `[cols["t"] > 37]` | P1–P16 |
| filling a formula down a column | `map` | V1 |
| autofilter | `filter` | V2 |
| SUMIF, a pivot table | `collapse(by=…)` and the built-in reducers | V4–V5, B1–B5 |
| VLOOKUP | `join` | C6–C9 |
| `#VALUE!` | a `failed` cell; the other rows still run | W1–W5 |
| recalculation | `run` / `run_all`, with `stale` marks in between | S1–S13 |
| *(no equivalent)* | **lineage**: each row knows which rows it came from | P9, P13–P15, C7–C9 |

Lineage is the one thing Excel lacks, and the reason for most of the rules.
Once rows are filtered, expanded or grouped, Excel loses track of which
output row belongs to which input row, and so does pandas (it lines rows up
by position or index label). Core keeps track and **refuses to guess**.

## 1. The principles

The rest of this page holds each part to seven principles. Observation H5
asks for a short list like this; it is proposed here, for the owner to
confirm.

1. **Everything is a grid.** One value is a 1×1 grid; a list or dict in a cell is one cell until a verb unpacks it.
2. **A step is one named expression that reads only earlier steps.**
3. **One step, one change.** At most one verb per step; longer changes are several steps.
4. **Rows meet only through a link core recorded**, never by position. When there's no link, core refuses and writes the fix.
5. **Nothing is lost silently.** A failure is a cell state, and every dropped row was dropped by a step you wrote.
6. **The shape is known before running** wherever the verbs decide it. Where they don't, the plan says what is unknown and why.
7. **States are facts about the workflow now**, not a record of past edits. This one is the session-model decision, SM, and isn't built yet.

## 2. The parts, one at a time

Each part says what we want it to do, what we deliberately don't do, and
what the lessons found. ✗ marks a gap; ? marks a choice still open.

### 2.1 Kernel and catalog (K)

**Want:** one kernel is one workflow. Its catalog is fixed when it's made,
so a workflow can use only the tools you gave it. That is what makes a saved
workflow safe to load: loading runs and imports nothing.
**Don't want:** global state, or tools found by import path.
**Status:** ✓ K1–K2.

### 2.2 Data in (D)

Seven ways in: a **source tool**, a **literal**, a **list or dict** (one cell
each), a **DataFrame**, an **empty step** (`None`), a **sweep** (one row per
combination of settings), and a **resource** (a live object built from
settings, such as a database or an LLM client, whose methods are tools).

**Want:** a value is one cell until a verb says otherwise. A list never turns
into rows by itself, because `[1, 2, 3]` could mean three samples or one
vector, and only you know which. Changing a resource's settings makes its
readers stale.
**Don't want:** sources silently reshaped, or placeholders in place of an
empty step.
**Status:** ✓ D1–D10. **? D11**: `k["x"] = some_function` stores the function
as a value. Should it be refused, pointing to `@tool` and the catalog?

### 2.3 Picks (P)

**Want:** an integer is a row number and a string is a column, as in a
Python list or an Excel range. A picked row is **saved as the row it is**:
`wf["srt"][1]` is stored as `rows[row["v"] == 0]`, so it still gives Ada
after a re-sort (P14). A condition is data, saved and printed back, never
run as Python.
**Don't want:** picks that silently change meaning. Lineage (`#v`) is
read-only and becomes data only through `mod.copy` (P13).
**Status:** ✓ P1–P10, P12–P14.
- ✗ **P15, a silent wrong answer.** A pick into a source follows the row's *position* when the source's data is replaced. Insert Zed at the top and `wf["src"][0]` gives Zed, `completed`, with no warning. Decision **D-picks**.
- ✗ P11: `wf["v"]["temp"]` is refused; columns still need `cols["temp"]`. Planned S3 (D2).
- ✗ P16: a pick can't be a tool's input; it must be its own step first. Planned S3 (D6).
- ✗ **P9b, new:** a lineage condition, `wf["e"][row["v"] == 1]`, warns that its rows "are positions and expand doesn't fix row order". It is lineage, not position, so the warning is wrong.

### 2.4 Verbs (V)

`tool[verb](input, arguments)`: the brackets say *how* the function is
applied, and the parentheses apply it.

| Verb | Calls the tool | Excel | Lessons |
|---|---|---|---|
| `map` | once per row | fill down | V1 ✓ |
| `filter` | once per row, `-> bool` | autofilter | V2 ✓ |
| `expand` | once per row, `-> list` | *(none)*: one row becomes several | V3 ✓ |
| `collapse(by=)` | once per group | SUMIF, pivot | V4–V5 ✓ |
| `group` | once per row, returns a key | a helper column | V6 ✓ |
| `table` | once, with the whole grid | a macro | V7 ✓ |
| `sweep` | once per combination | a data table | D8 ✓ |
| `source` | once, no input | an import | D1 ✓ |
| none written (`auto`) | inferred from the types | — | V8 ✓ |

**Want:** at most one verb per step (V9 ✓), and every setting does
something.
**Status:**
- ✗ V1b: one output column is named `value`, not after its step. Planned S4 (D9). This is what breaks A10.
- ✗ **V8b, decided but not built:** a bare `hot(wf["v"])` (`-> bool`) is inferred as a `filter` and drops rows. D20b (2026-11-02) decided `auto` never filters.
- ✗ **V10, new:** `mod.map(axis="columns")` is accepted and ignored. The code it calls raises `NotImplementedError`, but the step runs by rows. Remove `axis` from `map`, `filter`, `widen`, `group` and `expand`?
- ? V11: `map(where=, replace=)` takes a tool that returns `bool`. It overlaps `filter` followed by `join`. Keep it?

### 2.5 Reshapes with no tool (R)

`select`, `drop`, `rename`, `copy`, `sort`, `slice`, `distinct`, `pack`,
`widen`, `expand()` (a list cell into rows), and `expand(columns=…)` (unpack
lists core packed). Written `mod.sort(by="temp")(wf["v"])`.
**Want:** each one moves the data one level along one axis, and pack and
unpack round-trip without loss (R8–R9).
**Status:** ✓ R1–R10, R12.
- ✗ **R11, new:** `mod.widen(wf["i"])`, with the step put where a setting belongs, is accepted and the step fails with `None`. The other reshapes refuse with "takes settings by keyword".

### 2.6 Built-in tools (B)

`count`, `total`, `gather`, `first`, `last`, `identity`. **Status:** ✓ B1–B5.

### 2.7 Arguments and binding (A)

**Want:** a parameter binds to the input column of its name. An argument is a
literal, a pick or a resource. A cell pick is one value for every row; a
column pick pairs row by row, and only from an aligned step (principle 4).
When binding is unclear, the step is `invalid` and names the fix.
**Status:** ✓ A1–A6, A9.
- ✗ **A4b, new:** a `filter` given a column argument (`limit=wf["srt"][cols["temp"]]`) adds `limit` to its output columns. A filter should return only its input's columns.
- ✗ **A7, new:** the unknown-argument message says `to_f()` "accepts (none)"; it accepts `temp`.
- ✗ A8: a missing binding names the gap, not the fix. Planned S3 (CA-A).
- ✗ A10: `map` after `map` fails, because the first map's column is `value`. S4 naming and S3 binding fix it together. **This is the most common friction for a new user.**

### 2.8 Combines (C)

`zip_` puts each row beside the same row. `join` matches on a value or on
lineage. `stack` puts rows one after another.
**Want:** rows pair by identity, never by position (C2: after a sort, each
row still meets its own). A refusal writes the join for you (C3, C8).
**Status:** ✓ C1–C10. **? C11:** a combine's input can't be an inline
expression; it must be its own step. Is that the rule (every grid shown is a
named step), or should it be allowed?

### 2.9 Wrappers (W)

`retry`, `timeout`, `breaker`, `try_except`, `expect`. Each is saved in the
spec, because each can change the output.
**Want:** a failure is one cell, `failed`, and the other rows run. Without
`try_except`, `run_all` stops and names the fix. `expect` is a promise about
shape, and breaking it fails loudly.
**Status:** ✓ W1–W8.

### 2.10 Plans (L)

**Want:** before running, each step says its rows and columns as `exact`,
`stated`, `bounded` or `unknown`, with the reason. **Status:** ✓ L1–L2.

### 2.11 The session (S)

**Want:** an edit checks everything downstream at once and runs nothing. Old
values stay, marked `stale`, until a run replaces them. `run(x)` makes `x`
current. Putting something back exactly as it was is free.
**Status:** ✓ S1–S3, S6, S10–S13. Every ✗ here has one cause: states are kept
as flags, not derived (decision **SM**).
- ✗ **S5:** `run("f")` computes `f` from `h`'s outdated rows and shows `completed`, while `h` stays `stale`. A warning on `f` names `h` and the version it read, so unlike P15 it isn't silent, but the state is wrong.
- ✗ S7: an expression put back stays `stale`.
- ✗ S8: a step made `invalid` upstream loses its values.
- ✗ S9: when the column is put back, that step is `staged` and has to re-run.
- ✗ S4: the stale reason isn't among the step's warnings (SS7).

### 2.12 Save, load, provenance (Y)

**Want:** saving writes specs, never data. Loading runs nothing, and the same
catalog gives the same data and the same id. Extras survive and are never
hashed. Each cell can say what it was computed from.
**Status:** ✓ Y1–Y4.

## 3. To hash out

What to do about these is proposed as **EX1–EX9** in
[decisions.md §0](../docs/design/decisions.md#0-needed-from-you-now): one way
to write each thing, and a saved expression that says exactly what runs.

**New: not in the design docs yet.** Each is small, and each changes
behaviour, so each needs your yes before it lands.

| | Finding | Proposed |
|---|---|---|
| P9b | a lineage condition warns that it is positional | drop the warning for `row[…]` conditions |
| V10 | `axis="columns"` is accepted and ignored | remove the setting |
| R11 | `mod.widen(<step>)` is accepted and fails with `None` | refuse it, as the other reshapes do |
| A4b | a filter's column argument becomes an output column | the filter keeps only its input's columns |
| A7 | "accepts (none)" | list the tool's parameters |

**Open choices**

| | Question |
|---|---|
| D11 | Refuse a bare Python function assigned as a value? |
| V11 | Keep `map(where=, replace=)`, or leave that to `filter` and `join`? |
| C11 | Must every input to a combine or tool be a named step? |
| F7 | One way to write each thing? Today a reshape has three spellings: `mod.sort(by=…)(wf[…])`, `op("identity")[mod.sort(by=…)](wf[…])`, and `examples/all_orchestrations`' `mod.sort(over=wf[…], by=…)` |

**Known, already planned:** P15 (D-picks), S4–S9 (SM, SS7), P11, P16 and A8
(S3), V1b and A10 (S4), and V8b (D20b, decided).

## 4. How to use this page

Work through it in order, with `tutorial.py` open beside it; chapter *n*
there is §2.*n* here. When a decision lands, change the lesson's `want` in
`tutorial.py` to what was decided, run it, and update this page's count.

## 5. The handover: did core do what the app asked?

[`core-handover/`](../core-handover/) is what the app asked of core on
2026-10-26. [handover.py](handover.py) runs all of it against today's core:
`.venv/bin/python tutorial/handover.py`. Run 2026-11-03: **58 checks,
50 ✓ · 6 ✗ · 2 ?**.

| Part | What | Result |
|---|---|---|
| A | the acceptance session (`plan.md`, "What should work"), line by line, on `Kernel` and `Catalog` | 13 of 14 ✓ |
| B | the requests K19–K29, R7–R9, and the "Fix in core" table (K1–K18 are `scripts/core_asks.py`'s: 36 of 39 done) | 24 ✓ · 5 ✗ · 1 ? |
| C | the six probes in `core-handover/probes/`, ported | 13 ✓ · 1 ? |

**Not done (✗):**

| | Ask | Where it stands |
|---|---|---|
| A3 | formula text parsed against the catalog: `k["g"] = "to_f[mod.map()](wf['p'])"` | **stored as a string literal, silently.** No parser in core; the app's `operation_formula.py` is still to port (S3) |
| K22 | earlier outputs kept while something reads them | one output per step; decision ST, built with SM (S11) |
| K23 | progress modifiers and `cancel()` | not built (plan step D) |
| K28b | each output stores, per cell, the cells it came from | worked out on request by `k.cell`; ST's row map is the stored part |
| R7 | media handles | not built: ST's third piece |
| R9 | stages | not built. model.md said *built*; corrected |

**Changed by a later decision (?):** K19 asked for a column argument to pair
by position and type, and the probes ran `zip_` of two unrelated sources by
position. CA-11 (2026-11-02) made pairing by identity only: both are refused
now, and the refusal writes the join or `match_ids=True`.

**The probes as written don't run:** all six import `simple_steps_core.grid`,
which is gone. [app-migration.md](../docs/design/app-migration.md) lists the
renames; part C is each probe on today's names.

**The sweep corrected three things the docs said:** stages aren't built;
running a step on a stale input gives `completed` *with a warning* naming the
input (S5 isn't silent; only P15 is); and an undeclared return type is already
planned `unknown` (K27).

## 6. The whole sweep

`.venv/bin/python scripts/sweep.py` runs every check core has under coverage:
the tests, both tutorials, both examples, `scripts/core_asks.py` and the
core-asks probe (`--stress` adds the property test at 2,000 examples). Run
2026-11-03, every suite exits 0:

| Suite | Result |
|---|---|
| tests | 783 passed, 1 skipped, 27 xfailed |
| tutorial.py | 109 lessons: 89 ✓ · 17 ✗ · 3 ? |
| handover.py | 58 checks: 50 ✓ · 6 ✗ · 2 ? |
| both examples | run |
| core_asks.py | 36 of 39 done |
| core-asks probe | 65 pass, 19 fail, 1 skip |

Together they run **92% of core** (6,509 of 7,047 lines). The least run:
`references.py` and `values.py` (86%), `run.py` (87%), `verbs.py` (88%).
