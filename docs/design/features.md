# What this migration delivers

> Updated 2026-10-26, at phase 3e. One list of every feature the redesign
> includes: what is built, what is next, and what still needs a decision.
> Details live in the documents linked; IDs (K…, C…, R…) are the app's asks in
> `core-handover/008-core-changes-full.md`, G… are gaps found while writing the
> design (grid-model.md §8, outputs-and-reshaping.md §8, interactive-sessions.md §9).
> How a session looks with these features is [kernel-session.md](kernel-session.md).

## Built

| Feature | Phase |
|---|---|
| One model: the older engine, its server, API, agent types, docs and `pydantic` removed | 1 |
| `grid.py` split into modules along the object model, unchanged | 2 |
| `Catalog`: tools, resource types, built-ins, modifiers, combines; `without`, `from_modules`, `describe`, `strict` | 3a |
| A workflow checked against its catalog when steps are declared, re-checked and loaded; steps run the catalog's functions | 3a |
| `Kernel`: declare, edit, rename, delete, insert, move; run; read pages and cells; a table `repr` and notebook HTML | 3b, 3d |
| Resources built from their spec when first needed, or attached by the host | 3b |
| `Problem`s with codes (33), on every problem and warning | 3c |
| `step.state`, `step.data`; `Output.version`, `read`, `plan`, `stale_reason`, `ran_with` | 3c |
| `spec` on every object; save and load with an equal spec; `extras` everywhere | 3d |
| Value steps saved with their value (G16); values as controls (`limit=wf["limit"]`) | 3e |
| `k.check` for proposals; `k.needs_run`; `k.on_change`; stale inputs pass through, marked *read stale* | 3d |
| No process-wide state: two kernels in one process share nothing (K24) | 3e (1) |
| The agreed words; `step.status` the live part; saved format v4; `grid` removed; `Operation.from_spec` | 3e (2) |

## Phase 3 is complete

The last piece (3e) renamed everything to the agreed words, made
`step.status` the step's live part, moved the saved format to version 4, and
removed the `grid` module: the package's exports are the public API. What the
app changes to move onto it is listed in
[cleanup-plan.md §5](cleanup-plan.md#5-what-the-app-changes).

Deferred on purpose: **plain imports between modules.** Today several modules
import each other at the bottom of the file and the package loads them in a
fixed order. Phase 4 replaces that module by module, as it rewrites each area.
Also not renamed, because the old names are used as plain identifiers
throughout: method parameters called `step_id` and `tool_id`, and the `.id` of
a tool or a reference (`Tool.id`, `StepRef.id`, `ToolRef.id`), which could
become `.name` later.

## Phase 4: behaviour, one change at a time

Each is confirmed before it lands, and gets a probe. The order of what's left
is [phase4-plan.md](phase4-plan.md). The reshaping work (row ids, `#` columns,
matching rows, round trips, uneven data) is finished:
[reshaping-plan.md](reshaping-plan.md).

### Seeing the data truthfully

| Feature | ID |
|---|---|
| **A step is re-checked when an upstream's columns change**, so a reader that lost its column is a problem, not a `TypeError` on every row. *Done (phase 4, 2026-10-27)*: a warning as soon as the input is edited (`column_will_be_missing`), the problem once it re-runs | G13 |
| `to_source()` prints every form as written (reshapes, selections), so step ⇄ formula round-trips *Done (phase 4)* | G4 |
| `k["x"] = None` is an empty step (1×1 `"empty"`), a placeholder line *Done (phase 4, 2026-10-27)* | G17 |
| Row count and estimated size per output, or `unknown` with the reason; pages of 50–100 rows | K26 |
| Column types: declared, else `unknown`, then observed or the union | K27 |
| Missing values are `None` and integer columns stay integers (`stack`, failed rows) *Done (phase 4): a gap is `absent`, ints stay ints* | G2, R8 |
| An unrun source's planned columns come from its declared type, not a guessed `value` | K1 |

### References that follow the data

The rules, with four decisions for the owner, are in [row-ids.md](row-ids.md).

| Feature | ID |
|---|---|
| Selections pick rows by row id, so `wf["srt"][0]` is the same row after a sort *Done (phase 4)* | K19 |
| A column given as an argument pairs row by row, by the parameter's type *Done (phase 4)* | K19 |
| `zip_` pairs by row id; a source keeps the index its tool set *Done (phase 4)* | K19, G3 |
| Each cell's lineage stored with its output, including combines and multi-value cells *Done (phase 4): the `#` columns are the row map; a cell's inputs are its row's, by the columns it read ([reshaping.md](reshaping.md) §5)* | K28 |
| Reading an older version of a step warns, naming the step and version | K29 |

### Outputs and naming

| Feature | ID |
|---|---|
| A declared record type (`TypedDict`, `NamedTuple`, dataclass) spreads into one column per field *Done (phase 4)* | G8 |
| `mod.name`: a name, a list, a mapping or a pattern; replaces `name=`. The last modifier that defines names wins; with none, columns keep their defaults *Done (phase 4): every form* | G12 |
| Kernel-wide naming conventions (`Kernel(cat, naming=…)`) *Done (phase 4)* | outputs-and-reshaping.md §10 |
| `widen` reads declared fields, replaces the column it spreads, plans exactly *Done (phase 4): replaces the column, takes the union of keys, and reads declared record types* | G9, G10 |
| A `try_except` default that doesn't fit the return type warns; a step that used defaults warns *Done (phase 4)* | G6, G7 |
| Failure notes say where a row failed: tool, timeout, retry, breaker, expect, upstream *Done (phase 4), all but expect* | G7 |
| `timeout` enforced *Done (phase 4)* | K18 |
| `group` labels rows: the input's columns plus its key, so `collapse(by="key")` follows directly; `group(by=…)` is dropped and a column name refused when declared (owner, 2026-10-27). *Done (phase 4)* | G1 |
| `collapse` with an accumulator and no `initial=` *Done (phase 4): it starts from its accumulator type's empty value, or is refused when declared* | G5 |

### Sessions

| Feature | ID |
|---|---|
| Outputs kept by data version while a stale reader shows them | K22 |
| Progress per cell to a host callback, and `cancel()`: observing modifiers, saved, not hashed | K23 |
| Stages: consecutive steps run, checked and shown as one; not referable | R9 |
| An autorun modifier: a step re-runs on its own when what it reads changes. *Its triggers, chains, cost guards and pacing are still to be designed* | interactive-sessions.md §6.2 |
| Swapping a kernel's catalog, marking steps whose tool changed as stale | possible later (cleanup-plan.md, phase 3 notes) |

### Identity and reproducibility

| Feature | ID |
|---|---|
| Tool hashes; `k.id`, `k.run_id`, `k.step(…).id`; `k.diff(other)`; a changed tool marks its steps stale | K20 |
| A resource may report a data version, which marks its users stale | K25 |
| Secret resource settings, left out of saves and hashes | R3 |
| Tools that aren't deterministic: a `seed` literal recommended | K20 |

### Storage

| Feature | ID |
|---|---|
| A pluggable output store: outputs saved beside the spec, so a reloaded kernel opens with its data | C32 (replaces C29, C30) |
| Media handles for images and other objects, saved as content-hashed references | R7 |

### Seeing a workflow as a table (later)

Decided by the owner, 2026-10-27, to add later. **Each step is a column, and a
workflow is a table.** `repr(k)` shows the steps side by side, each as a block:

1. the step's name;
2. its operation;
3. a summary of its data, column by column: type, how many values (missing,
   failed), and the range, trues or distinct values.

Printing one step (`k.step("sick")`, `k.show("sick", rows=…)`) shows its
rows, each labelled on the left with how to reference it (`wf["sick"][0]`), so
what you see is what you'd write. Rows line up across steps by their row
mapping (the row ids of K19), so one patient sits on one line through `p`,
`sick` and `f`. `k.table()` keeps today's one line per step. Long formulas and
values are cut with "…". A draft that does all but the row alignment was
written on 2026-10-27 and set aside until then.

| Feature | ID |
|---|---|
| The workflow as a table of step blocks (name, operation, data summary) | G18 |
| A step's rows labelled with their reference | G18 |
| Rows aligned across steps by row mapping | G18, needs K19 |

### Selections (later)

| Feature | ID |
|---|---|
| `header[k]` picks one column name, or is refused; today the `[k]` is ignored. Deferred (owner, 2026-10-27) | C28 |
| A header as a step: one row per name (in a column called `column`), or one cell holding the list | deferred (owner, 2026-10-27) |
| Selection steps print as written (`wf["p"][0:2]`, not `op("identity")[mod.select(…)]`) *Done (phase 4)* | G4 |
| `rows[1, 3]` and `cols["a", "b"]` as lists | decided: no; a list is written `rows[[1, 3]]` (owner, 2026-10-27) |

## Phase 5: documentation

The final docs set (cleanup-plan.md §6), each with its examples run as tests,
as `examples/kernel_session.py` already is.

## Later, by decision

| Feature | Why later |
|---|---|
| Developer-defined modifiers, under the rules in extensions.md §5 | decided: not yet |
| A "verb must be written" mode (implicit auto off) | the global switch was removed in 3e; could return as a kernel option if wanted |
| Two shape verbs in one step | decided: never; use separate steps and a stage |
| Steps with several named outputs | decided: one grid per step |

## Decisions still open

They are in [phase4-plan.md §5](phase4-plan.md#5-decisions), each with a
recommendation: G5's starting value, how `timeout` is enforced (K18), how a
resource reports its data version (K25), the autorun modifier's design, the
progress callback, and the output store's interface. (G3, a source's own
index as its row ids, was decided as D2 in row-ids.md and is built.)
