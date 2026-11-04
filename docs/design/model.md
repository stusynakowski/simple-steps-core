# The model

> **The one description of what core is.** Consolidated 2026-11-03 at
> `d69b5f1` from object-model, grid-model, outputs-and-reshaping, reshaping,
> row-ids, step-expressions, extensions, interactive-sessions and
> session-states, which now sit in [history/](history/). Every *built* rule
> was run at `d69b5f1`; every *planned* one names the work that builds it.
> What the app needs from core is [core-asks/model.md](core-asks/model.md);
> what's decided and what's open is [decisions.md](decisions.md); the order of
> work is [plan.md](plan.md). Where this page and the code disagree, this page
> is the intent and the gap is a bug or a planned item. The model as a map,
> with examples of the behaviour we want, is [model-map.md](model-map.md).

## 1. What core is

`simple-steps-core` is the engine of Simple Steps: the part that knows what a
workflow is and how it runs. **Everything the app can do to a workflow can be
done to a `Kernel` in a plain Python session**, with only core installed. If
the app works out a fact about a workflow (why a step is stale, where a cell
came from, whether an expression is valid), that fact belongs in core.

| Core | The app (`Simple_Steps`) |
|---|---|
| the objects below; checking, staging and running steps; states, staleness, versions; saving and loading specs; a terminal view | hosting many kernels; the expression bar's parser (text → operation); users, sessions, files; cell views and the UI; the agent |

Core keeps no mutable state at module level: one process holds many kernels
that can't see each other. The app's own data lives in `extras` (§11).

## 2. The words

One word per idea, in code, API and docs. Retired words are in the right
column.

| Word | Means | Retired |
|---|---|---|
| **kernel** | one live workflow with what it runs with: its catalog, loaded resources and outputs | *engine*, *session* |
| **catalog** | what a kernel may use: tools, resource types, modifiers, combines. Fixed when the kernel is made | *registry*, *pack* |
| **tool** | one Python function, described: name, typed parameters, return type, docstring | *ToolHandle* |
| **resource type**, **resource** | a class whose instances tools use; one named instance of it in a workflow | — |
| **workflow** | the kernel's steps, in order, and its resources | *pipeline* |
| **step** | a unique name, one expression, and the output it produces | *node*, *task* |
| **expression** | what a step does, as written: a literal, a pick, a tool call or a combine | *formula* |
| **operation** | an expression as an object: tool, modifiers, input, arguments; nothing run | — |
| **pick** | part of an earlier step: `wf['s']` with up to one row part and one column part | *selection* |
| **condition** | a test that chooses rows, on data (`cols['x']`) or lineage (`row['s']`) | — |
| **modifier** | `mod.<name>(…)` in a tool call's brackets: a **picker** (narrows the input), a **verb** (how the tool is applied), a **column modifier** (rename, copy, name, widen, pack) or a **wrapper** (retry, timeout, breaker, try_except, expect) | *orchestration*, *mode*, *shape verb* |
| **combine** | `join`, `zip_` or `stack`: reads several steps | — |
| **binding** | which column reaches which tool parameter | — |
| **spec**, **status** | an object's saved form (never output data), and what is live about it | *declaration* |
| **spec id** | a hash of a step's spec, its tool's code, its resources' settings and the spec ids of what it reads. Never data, never extras (K20) | — |
| **output** | what a step produced: data, lineage, row numbers, a state per cell | *result*, *ledger* |
| **data version** | a hash of an output's values | — |
| **state** | a **step state** (`staged`, `completed`, `stale`, `failed`, `invalid`) or a **cell state** (`absent`, `known`, `maybe`, `pending`, `blocked`, `failed`, `invalid`) | step *status* |
| **problem**, **warning** | a structured reason a step can't run or ran badly (code, message, step, row or argument); a warning doesn't block | plain-string problems |
| **row id** | core's identity for a row. **Never shown or written** | — |
| **row number** | a row's position, `0…n-1`, in its step's current order, shown as `#<step>` | *placement* |
| **lineage** | the `#<ancestor>` columns: for each ancestor, the row number(s) this row came from | *trace column* |
| **aligned** | two steps whose rows are the same rows, in any order | *origin* |
| **pack**, **unpack** | a selection into one cell (a column into a list, a row into a dict), and back | *squeeze* |
| **absent** | a cell with no value at all (a key a record lacks, a `stack` or `join` gap), apart from a `None` value | — |
| **empty step** | a step with no expression yet: a 1×1 output holding `"empty"` | placeholder |
| **extras** | an open mapping on every spec, by namespace, that core stores but never reads or hashes | — |

## 3. The objects

```
Kernel ── catalog (tools, resource types, modifiers, combines) ── resources
  └─ Workflow: steps, in order
       └─ Step: name · expression (an operation) · problems · warnings
            └─ Output: data · lineage · row numbers · a state per cell
                       · data version · what it read · its plan
```

- **Brackets decorate, parens apply.** `to_f(36.6)` calls the function;
  `to_f[mod.map()]` is an operation waiting for an input;
  `to_f[mod.map()](wf["p"])` reads step `p`. *Built.*
- **A step uses only what its kernel's catalog holds**; anything else is a
  problem and the step never runs. *Built.*
- **A step reads only earlier steps.** A reference to itself, a later or a
  missing step is a problem, never a cycle. *Built.*
- **Declaring stages the step at once:** it's checked, gets its problems, and
  its output is a plan (§7) until it runs. *Built.*
- **Saving writes specs, never output data.** Loading builds objects from a
  spec and a catalog, imports nothing and runs nothing. A tool whose code
  changed makes its steps `stale` ("tool changed"). *Built.*
- **Stages** group consecutive steps to run and show them as one; a stage is
  not a reference and changes no output. *Planned* (R9; marked built until
  2026-11-03, when the handover sweep found no stage in core or its tests).

## 4. Rows: identity, position, lineage

Every output has three parts, kept apart: **lineage**, the **row number**
`#<step>`, and **data**. Only data reaches a tool.

### 4.1 Row ids: core's, never shown

Each row has an id that follows it through every step that keeps it. Ids
decide pairing (§5), staleness per row, and what a saved pick follows. A user
never sees or types one. *Built* (S5a).

| Step | Its rows' ids |
|---|---|
| keeps rows: `map`, `group`, `sort`, `select`, `drop`, `rename`, `widen`, `pack` | the input's |
| chooses rows: `filter`, `slice`, `distinct`, a row pick, a condition | the input's, for the rows kept |
| `expand` with a tool | new: item *j* of row *i* |
| `expand` that unpacks a list core packed | the packed rows' own ids, given back |
| `collapse` | one row; with `by="ward"` the key; with `by="#s"` `s`'s ids |
| `source`, a DataFrame assigned, `sweep`, `table` | their own: the DataFrame's index if it set one, else counted `0…n-1` |
| `join`, `stack` | new, counted |

### 4.2 Row numbers: what you see and type

`#<step>` is `0…n-1` in the step's current order. **Integers in a pick are row
numbers**, as in a Python list: `wf['s'][3]`, `[-1]`, `[[0, 2]]`, `[1:3]`.
*Built* (S5a, S5d).

### 4.3 Lineage: where each row came from

- **Every step carries its input's lineage**; a step that isn't one-to-one
  adds `#<parent>`. An expand also adds `#<parent>.idx`, the item's place in
  its parent's list. The same ancestor by two paths is `#r`, `#r.2`. *Built*
  (S5b).
- **A lineage cell is the ancestor row's current row number**: an integer, a
  list of them (after `collapse` or `distinct`), or empty (a `stack` or outer
  `join` gap). Rows an expand gives back from a collapse carry their own row's
  number, not their group's list. *Built* (S5b, `41a575a`).
- **Lineage is read-only.** It becomes data only by copying it,
  `mod.copy(columns={'#r': 'parent'})`; `mod.rename` of a `#` column is saved
  as a copy; a pick of a `#` column is refused. *Built* (S5e).

Run, for `v` = Ada, Ben, Cy:

| Step | Row ids | Data columns | Lineage |
|---|---|---|---|
| `dbl[map](v)` | 0, 1, 2 | `value` | none: one-to-one |
| `hot[filter](v)` | 1 | `name`, `ward`, `temp` | `#v`: 1 |
| `two[expand](v)` | 0.0, 0.1, 1.0, … | `value` | `#v`: 0, 0, 1 · `#v.idx`: 0, 1, 0 |
| `count[collapse(by="ward")](v)` | A, B | `ward`, `value` | `#v`: [0, 2], [1] |
| `sort(by="temp")(v)` | 2, 0, 1 | carried | `#v`: 2, 0, 1 |
| `join(v, w, on="ward")` | 0, 1, 2 | both sides' | `#v`: 0, 1, 2 · `#w`: 0, 1, 0 |
| `stack(v, w)` | 0…3 | the union | `#v`: 0, 1, 2, – · `#w`: –, –, –, 0… |

### 4.4 Picks and conditions

- **A typed row number is saved as the row's lineage**, so the pick follows
  its row: `wf['srt'][1]` is saved as `wf['srt'][rows[row['p'] == 0]]`. Into a
  source it stays a number; a range stays a range. *Built* (S5d).
- **`rows[condition]` names rows that must exist** (one that's gone fails the
  step, naming it); a plain `[condition]` filters, and matching nothing gives
  zero rows and a warning. A row number out of range fails. *Built* (S5c, S5d).
- **A condition** uses only `cols['x']`, `row['s']`, `row['s'].idx`,
  comparisons, `.isin`, `&`, `|`, `~` and literals. It is data, saved and
  printed back as written, never run as Python. On a list cell `==` means
  "contains"; an empty cell fails every test. *Built* (S5c).
- Text row ids (`rows["A"]`) and a list naming one row twice are refused.
  *Built.*
- **Planned (S3):** strings choose columns in a pick (`wf['s']['n']`); a pick as
  a tool's input; `[0, 2]` refused, pointing to `[[0, 2]]`.

**A pick follows its row when a source's data is replaced** (D-picks, built
2026-11-04). The source matches its rows to the ones it has seen by their
values and keeps their ids, and every row number a step names into it is
rewritten to that row's number now: `wf["p"][1]` becomes `wf["p"][2]` when
a row is inserted above, and so does `row["p"] == 1` in any later step. A
picked row that is gone makes the step `invalid` (`row_gone`), naming the
row and its values, until it is picked again or comes back. See §10.

## 5. How rows from two steps meet

Rows of two steps are put side by side in four ways, and nowhere else.

| Two steps' rows are | Example | `zip_` / a column argument | `join(…, on="#s")` |
|---|---|---|---|
| **aligned**: the same rows, any order | `v`, `dbl[map](v)`, `sort(v)`, `collapse(by="#v")` beside `v`, rows an expand gives back | **pair each row with the same row, by id** | yes |
| one is a **subset** of the other | `filter(v)` and `v` | refused, writing the join | yes; `how="left"` keeps every row of `v`, the other side `absent` |
| a **child and its parent** | `expand(v)` and `v` | refused, writing the join | yes: each child beside its parent |
| a **group and its members** | `collapse(by="ward")(v)` and `v` | refused | refused: unpack the group first, `mod.expand(columns=["#v"])`, which the refusal writes; then pair row with row |
| **unrelated** | two sources | refused (`unmatched_rows`) | — : `join(…, on="key")`, or `zip_(…, match_ids=True)` to vouch |

- **Pairing is by identity, never by position** (CA-11, amended 2026-11-02).
  A refusal names the rows' relation and writes the join, `on="#s"` for the
  nearest shared ancestor. *Built* (`aa2b09b`, `d69b5f1`).
- **A join on lineage pairs one row with one row.** A column both sides carry
  unchanged from the shared ancestor appears once; one that differs keeps
  `_left` / `_right` suffixes. *Built* (S5e, `d69b5f1`).
- **A join on a value** (`on="ward"`) matches by the column's values; `how=`
  is `inner`, `left`, `right` or `outer`. **`stack`** puts rows one after
  another; a column one input lacks is `absent` there. *Built.*
- **`match_ids=True`** is the user vouching that two steps number the same
  samples; core still requires equal id sets. *Built.*

**Open (D-child, D-subset):** [reshaping.md §6](history/reshaping.md) let a child read
its parent's column directly and let a column argument block unmatched rows
and run the rest; CA-C and today's code refuse both, pointing to a join. Which
holds is in [decisions.md](decisions.md).

## 6. Verbs and modifiers

A tool call is `tool[modifiers](input, arguments)`. **Modifiers apply in the
order written**, outermost first, like stacked decorators, and are stored as
data in the step and applied each time it runs. *Built.*

**Verbs** (at most one; none written means `auto`, inferred from the tool's
types: `-> bool` filters, `-> list` expands, a first parameter `acc` collapses,
anything else maps). *Built.*

| Verb | Calls the tool | Output rows | Data columns out |
|---|---|---|---|
| `source` | once, no input | what it returns | a DataFrame's, a record's fields, else `value` |
| `map` | once per row | one per row | `value`, or a record's fields |
| `filter` | once per row | the rows it approves | the input's |
| `expand` | once per row; returns a list | one per item | `value`, or each item's fields |
| `collapse` | once per group (`by=`) | one per group | the key, and `value` or the fields |
| `group` | once per row; returns a key | one per row | the input's, plus the key |
| `sweep` | once per combination of settings | one per combination | the settings, and `value` |
| `table` | once, with the whole input | what it returns | what it returns |

**Pickers and reshapes** call no tool: `select`, `drop`, `rename`, `copy`,
`sort`, `slice`, `distinct`, `widen`, `pack`, `expand(columns=…)` (unpack
lists core packed, keeping the other columns). **Built-in tools:** `identity`,
and the reducers `count`, `total`, `gather`, `first`, `last`. *Built.*

**Wrappers** (each in the spec and the spec id, since each can change the
output): `retry`, `timeout`, `breaker`; `try_except` (a failure becomes a
`failed` cell that doesn't stop `run_all`, or a default value with a warning);
`expect` (what staging promises). A failed row's note says where it failed:
`tool`, `timeout`, `retry`, `breaker`, `expect`, `upstream`. *Built.*

**Naming:** one output column is `value` unless `mod.name` names it; a
declared record spreads into one column per field. Data column names are
unique, never start with `#`, and two that would collide are a problem.
*Built.* **Planned (S4):** one output column named after its step; a dict's
keys as columns; numeric names become `var<n>`; step names are identifiers,
no `.`.

**Arguments and binding:** a parameter binds to the input column of its name;
an argument is a literal, a pick or a resource. A cell pick is one value for
every row. A column pick pairs row by row only from an aligned step (§5);
passed to a `list`, `Series` or `DataFrame` parameter it is the whole column.
A tool never receives a `#` column. *Built.* **Planned (S3):** binding decided
at staging and written into the expression (by keyword, then by name for a
parameter without a default, then the one column whose type fits, else
`invalid` naming the candidates); `mod.cast`.

## 7. Plans and going back

- **Each step's plan says its rows, columns and types before it runs**, each
  `exact`, `stated` (`mod.expect`), `bounded` or `unknown` with the reason. A
  result that breaks an exact plan fails loudly. *Built.*
- **Each plan says how to go back**: `rebuild` (with the expression that
  gives the input back exactly), `trace` (the rows are reached through
  lineage), `opaque` (a `table`: only the whole input), `generated` (no
  input). *Built.*
- **Grouping is a pack plus a map:** `f[collapse(by=k)](g)` is
  `f[map()](gather[collapse(by=k)](g))`, keeping the key as a column. A
  statistic goes back beside its rows by unpacking the reduction's `#v`. *Built.*

## 8. States in a session

**Step states**, decided in this order (*built*):

| State | When |
|---|---|
| `invalid` | it has problems: its own, or an input (or `collapse(by="#s")`'s `s`) that is `invalid` or empty |
| `staged` | it has no output from a run (never run, or its output was dropped). An empty step is `staged`, holding `"empty"` |
| `stale` | it ran, and since then its expression, an input's data, an input's staleness, a tool's code or a resource changed |
| `failed` | it ran, and a cell `failed` or is `blocked` |
| `completed` | it ran, and none of the above (zero rows included) |

**The session rules** (*built*):

- **Checking is immediate; running is on request.** An edit re-checks every
  step downstream at once, in workflow order: a step `invalid` because of what
  it read is re-decided, and one whose input became `invalid` is `invalid`
  too, naming it (`baec929`). Nothing runs on its own.
- **Old values stay until a run replaces them**, marked `stale`.
- **Runs go in workflow order**, after everything a step depends on.
- **The reason is kept**: "updated args", "input p changed", "tool changed".
- **Staleness isn't passed down the chain** (owner, 2026-11-04): a step is
  stale only when its own arguments changed: an input's data, a resource, its
  tool, its expression. A step whose input is stale, that input's data still
  what it read, stays `completed`, and `needs_run()` names the input:
  *read stale 's'*. `run(x)` still makes `x` current, asking each step it
  depends on in turn.
- **Re-assigning identical data changes nothing**: equal data, equal data
  version, nothing goes stale.
- A rename rewrites every reference core wrote; a move that puts a reader
  before what it reads is refused; deleting a step something reads is refused,
  naming the reader.

**Where it falls short** (each run 2026-11-03; detail in
[history/session-states.md](history/session-states.md)):

| | Today | Decision |
|---|---|---|
| F1 | an expression put back to exactly what last ran stays `stale` | SM: **fixed 2026-11-03**, its result is still in the store |
| F2 | a reader made `invalid` by an upstream change loses its values, and is `staged` when the upstream is restored | SM: **fixed 2026-11-03**, it shows its newest result, and is `completed` when restored |
| F3 | running one step on a `stale` input gives `completed`, with a warning naming the input and the version read (K29) | C9: **fixed 2026-11-03**, `run(x)` runs what's stale first; `run(x, fresh=False)` reads it as it is, on purpose |
| F4 | an `invalid` step can still carry a stale reason | SM |
| F5 | `needs_run()` lists an empty step | SS5 |
| F6 | a failed step isn't listed by `needs_run()` | SS5 |
| — | the stale reason isn't among the step's warnings, where the app reads (core-asks L42); no delete-anyway (L43d) | SS7 |

They share one cause: **states are kept as flags**, marks set by an edit and
cleared by a run, so a state remembers the order of events instead of saying
what the workflow is now. Each kind of edit has to set and clear the right
marks on the right steps, and a path that forgets leaves a wrong state behind.

### 8.1 The proposed session model (SM)

*Proposed 2026-11-03; decision SM in [decisions.md](decisions.md). Planned,
plan step S11.* The session is managed the way build tools manage a build:
the workflow, plus a store of results, and every state read off the two.

**Two things are kept, and nothing else:**

- **the workflow**: each step's expression, as it is now;
- **a result store**: every output computed, filed under its **run key**, a
  hash of the step's spec id and the data versions of the inputs it read:
  *this expression, with this tool code, on exactly this data*.

**Two kinds of action:**

- **Edit** (assign, rename, move, delete, insert) changes the workflow. Core
  re-checks every step after it at once and runs no tools. No stored result
  changes. A step is checked against its inputs' plans (PL): an input with a
  new, unrun expression is checked as what that expression will produce, not
  as the last result it shows.
- **Run** computes the run keys missing from the store, in dependency order,
  and adds them. `run(x)` means *make `x` current*: it first runs whatever
  `x` needs that isn't. Computing on outdated inputs on purpose is an
  explicit option, and its result is itself `stale`.

**Every state is derived, when asked:**

| A step is | When | It shows |
|---|---|---|
| `invalid` | its expression has problems now | its last result, marked; the problems |
| `completed` | the store holds a result for its run key now | that result |
| `failed` | as `completed`, and that result has failed cells | that result |
| `stale` | no result for its run key now, but an earlier one | the latest earlier result, marked, with the reason: the difference between the two keys ("the step changed", "input p's data changed", "tool changed") |
| `staged` | no result at all | its plan |

**What follows:**

- **Undo is free.** An expression put back is `completed` at once: its result
  is still in the store (F1).
- **The order of edits never matters.** States depend only on the workflow
  and the store, so any sequence of edits ends where a fresh kernel with the
  same workflow and store would (F2–F4; the law L40c).
- **Nothing shown is ever dropped**: an `invalid` step keeps showing its last
  result (F2).
- **Autorun is a policy, not new machinery**: after an edit, run what is
  stale and marked cheap (the planned scheduling modifier).
- **The flags go**: `edited`, `stale`, `stale_reason`, `read_stale`, and the
  code that keeps them in sync, replaced by *compute the key, look it up*.

**What exists already:** spec ids (`workflow.identity()`), data versions,
each output's `read` stamps, and per-row staleness, all built. **To build:** the
store keeping several results per step (K22, plan step D, brought into S11),
and states derived from it. **How it is stored** is decision **ST**
([decisions.md §0](decisions.md#0-needed-from-you-now)): a step keeps only a
row map and the columns it makes, columns and large values (images, files)
are filed once by content hash, and a result is a run key pointing at them.

**To decide with it:** how many results the store keeps per step in a
terminal session (the app's eviction is its hosting); tools that read the
outside world, whose run key needs an *as of* (D43–D46); source data
replaced underneath is decided (D-picks, §10).

## 9. The guarantees, and how they're checked

1. **Ids are core's.** Tools see data only; only core writes `#` columns.
2. **Every row knows where it came from**, through lineage.
3. **Rows pair only through a link core recorded** (§5).
4. **The shape is known from the verbs** (§7).
5. **Nothing is lost silently**: every loss is a step you wrote; a missing
   pair or a failed call is a `failed` or `absent` cell, never a null.

They are checked, not assumed (*built*):

| Check | What | Where |
|---|---|---|
| A1–A8 (the invariant check) | after every step of every test: unique ids, lineage names real rows, kept ids are the input's, rows paired only through a recorded match (and each side of a join on lineage traced back by id to the same row), the plan kept, every `rebuild` round-trips | `tests/conftest.py`, `Workflow.check_invariants` |
| L40 | generated grids and chains of every verb: no crash, A1–A8 hold | `tests/unit/test_reshape_properties.py` (`STRESS=1`: 2,000 examples) |
| L40b | a saved workflow, loaded and run, gives the same data | same |
| L40c | an edited workflow, run, equals a fresh run of it | same |
| the failure list | every property-test failure, with its shrunk example; fixed ones pinned | `tests/stress-failures.md` |

## 10. Uncertain operations, and their boundaries

Everything not in this table is decided from the verbs, before anything runs.

| Operation | What core can't know | Its boundary |
|---|---|---|
| a source's data is replaced | whether row *k* is the same sample as before | **by its values** (D-picks): a row it has seen, now or before, gets its id back (duplicates in order); rows left over on both sides, as many each, are values edited in place and keep their ids in order (so only their cells go stale, and a pick follows them); any other row is new, with an id never used. Each row number a step names is rewritten to its row's number now; a pick whose row is gone is `invalid`. Negative numbers, ranges and comparisons are positions, and stay as written. A source with an index of its own keeps it: that's its identity. A declared key column, for value edits alongside added rows, is later |
| a `table` tool | which output row came from which input row | its own ids; traces only to the whole input; never pairs |
| a list a tool wrote | whether item *j* means the same across runs | new ids, a child of its row |
| `match_ids=True` | whether two sources number the same samples | vouched: the id sets must be equal at run |
| a pick into a step that hasn't run | which row the number will mean | resolved when that step runs, and written into the expression |
| row counts (`filter`, `expand`) | how many rows | the plan says `unknown`; never used to decide pairing |
| an undeclared tool's return | the output's columns and types | `unknown` until run; declare the return type or `mod.expect` |

## 11. Extras and the saved file

- **If removing it could change an output, it isn't an extension.** Notes,
  colours, widgets, agent permissions live in `extras["simple_steps.…"]` on
  the spec they're about. Core never reads them, never hashes them, and keeps
  unknown namespaces through a load and save. *Built.*
- **A workflow the app saved runs the same in plain Python** with the same
  catalog: `Kernel.from_json(text, catalog).run_all()`. *Built.*

## 12. What core can't do, by design

| You can't | Because | Instead |
|---|---|---|
| see inside a tool, or trace inside a `table` result | a tool is opaque | split the tool; use `collapse`, `filter`, `join` where rows must trace |
| keep the identity of items in a list a tool rewrote | core can't know which item is which | sort or filter as a step on the unpacked rows |
| rebuild the input of a lossy step from its output | its values are gone there | trace back: the input step is still there |
| pair unrelated steps without saying so | rows pair only as the same rows | `join` on a key, or `match_ids=True` |
| flatten JSON of any depth in one step | one level per step | one `widen` or `expand` per level |
| have core decide whether a dict is a record or a mapping | it's a meaning, not a shape | choose `widen` or `expand` |
| know an undeclared tool's shape before it runs | only running can say | declare the return type |
| trace across kernels or saved files | lineage lives inside one workflow | — |
