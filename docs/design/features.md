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

## Next: finishing phase 3

Each needs the owner's go-ahead, because it changes what the app imports or
the saved format.

| Item | What changes | For the app |
|---|---|---|
| **Renames to the agreed words**: `ToolHandle` → `Tool`, `tool_id` / `step_id` → `name`, `Modifier.params` → `settings`, `ResourceDecl` into `ResourceSpec`, `meta["payload"]` → `value_column` | the JSON keys too, so the format version goes up; older files don't load (decided: no compatibility) | re-save its workflows and examples |
| **`step.status` becomes the live part** (output, state, problems), as designed; `step.state` is the string | `.status` stops being a string | read `.state` |
| **Remove the `grid` module**: the public names are on `simple_steps_core`; tests move to the public API and to specific modules | `from simple_steps_core import grid` stops working | its migration point: imports, `core_bridge.py`, `main.py:139`, `kernels.py` onto `Kernel` |
| **Plain imports** between modules, replacing the bottom-of-module imports and fixed load order | internal only | none |

Recommended: the renames and `status` together (one format change), then
removing `grid`. Plain imports later, module by module, as phase 4 rewrites
each area, rather than one large restructure now.

## Phase 4: behaviour, one change at a time

Each is confirmed before it lands, and gets a probe.

### Seeing the data truthfully

| Feature | ID |
|---|---|
| **A step is re-checked when an upstream's columns change**, so a reader that lost its column is a problem at once, not a `TypeError` on every row. *Highest priority: reactive status depends on it* | G13 |
| `to_source()` prints every form as written (reshapes, selections), so step ⇄ formula round-trips | G4 |
| `k["x"] = None` is an empty step (1×1 `"empty"`), a placeholder line | G17 |
| Row count and estimated size per output, or `unknown` with the reason; pages of 50–100 rows | K26 |
| Column types: declared, else `unknown`, then observed or the union | K27 |
| Missing values are `None` and integer columns stay integers (`stack`, failed rows) | G2, R8 |
| An unrun source's planned columns come from its declared type, not a guessed `value` | K1 |

### References that follow the data

| Feature | ID |
|---|---|
| Selections pick rows by row id, so `wf["srt"][0]` is the same row after a sort | K19 |
| A column given as an argument pairs row by row, by the parameter's type | K19 |
| `zip_` pairs by row id; a source keeps the index its tool set | K19, G3 |
| Each cell's lineage stored with its output, including combines and multi-value cells | K28 |
| Reading an older version of a step warns, naming the step and version | K29 |

### Outputs and naming

| Feature | ID |
|---|---|
| A declared record type (`TypedDict`, `NamedTuple`, dataclass) spreads into one column per field | G8 |
| `mod.name`: a name, a list, a mapping or a pattern; replaces `name=`. The last modifier that defines names wins; with none, columns keep their defaults | G12 |
| Kernel-wide naming conventions (`Kernel(cat, naming=…)`) | outputs-and-reshaping.md §10 |
| `widen` reads declared fields, replaces the column it spreads, plans exactly | G9, G10 |
| A `try_except` default that doesn't fit the return type warns; a step that used defaults warns | G6, G7 |
| Failure notes say where a row failed: tool, timeout, retry, breaker, expect, upstream | G7 |
| `timeout` enforced | K18 |
| `group(by="column")` refused when declared (or means the column) | G1 |
| `collapse` with an accumulator and no `initial=` | G5 |

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
| `header[k]` picks one column name, or is refused; today the `[k]` is ignored | C28 |
| A header as a step: one row per name (in a column called `column`), or one cell holding the list | open |
| Selection steps print as written (`wf["p"][0:2]`, not `op("identity")[mod.select(…)]`) | G4 |
| Possibly accept `rows[1, 3]` and `cols["a", "b"]` as lists | open |

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

1. The finishing-phase-3 items above, and their order.
2. The autorun modifier's definition.
3. Whether a resource reports its data version by a method or a setting (K25).
4. A source tool that sets its own index: is that its row ids (G3)?
