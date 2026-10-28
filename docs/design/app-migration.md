# Moving Simple Steps onto the new core

> Step G of [phase4-plan.md](phase4-plan.md), brought forward: what the app
> repo (`Simple_Steps`) changes to run on this core, in what order, and what
> it adopts later. Derived 2026-10-27 at core `fdd3b62`, from the app at
> `1139779` (pin `86170a3`, 69 core commits behind). The app's own maps of
> the same work are its `docs/cleanup-map.md` (round 4, stages A–D) and
> `docs/system_design/12-core-and-app.md`; this page says which of their
> rows core now makes possible.

## 1. Can the app move now?

**Yes.** Nothing left in phase 4 blocks it. Steps D, E and F add features
the app either does without today or does for itself, and none of them
renames or removes anything the app will use. So the move is one breaking
pass now, then small additive passes as each core step lands (§5).

| Left in core | What the app does meanwhile | Blocks the move? |
|---|---|---|
| D: K22 outputs by data version | keeps `DATA_STORE` / `RAW_STORE` | no |
| D: K23, K14 progress and `cancel()` | keeps `progress.py`; only the legacy orchestrators call it | no |
| D: K15 re-run failed rows; R9 stages; autorun | not used yet | no |
| E: C32, K16 output store; R7 media | saves the spec; a reloaded workflow re-runs, as today | no |
| F: G18 the workflow as a table | its own UI | no |
| C-D2 the seed recommendation | — | no |

The one thing that would be worse later: every core commit from here on is
written against an app that isn't on it. Moving now means the app's tests
check core's changes as they land.

## 2. Before the pin moves (on the old pin)

Shrink what has to move. These are the app's own decided cleanups
(cleanup-map.md round 4), none of which needs the new core, and each removes
code the move would otherwise have to port:

1. **Stage A:** eval mode (L1), the engine switch (L2), the unused routes.
2. **Stage D, under "the best code is no code"**: `pack_loader.py` (L3),
   the old-syntax formulas and orchestrators (L4), `safe_formula.py` and the
   console (L7), `step_proxy.py` and `helpers.py` (L8), duplicate tools
   (L9). About 3,200 lines; the old engine's last users go with them.
3. **Stage B:** split `grid_runner.py` into what the kernel needs and the
   legacy per-step path; `models.StepConfig` and `example_check.py` onto
   `operation_formula`; `@simple_step_tool` stops wrapping in `StepProxy`.

Checks after each, as the app has them: `pytest`, `scripts/preflight.py`,
`examples/runme.py`.

## 3. Moving the pin

One branch in the app, in this order. Each item ends with the app's tests
passing, except where it says otherwise.

### 3.1 Pin and imports

Move `pyproject.toml`'s pin and `external/simple-steps-core` together. Then
**import from the package; `simple_steps_core.grid` is gone**:

```python
from simple_steps_core import (Catalog, Kernel, tool, resource, bound_tool, Secret,
    mod, wf, res, rows, cols, join, stack, zip_, Operation, Step, Output, Problem)
```

Anything else comes from its module and may still change:

| The app uses | Now |
|---|---|
| `grid.Workflow` (61 uses) | `Kernel` for everything the app hosts; `simple_steps_core.workflow.Workflow` only inside core |
| `grid.Operation`, `grid.op`, `grid.Output` | `Operation`, `op`, `Output` |
| `grid.mod`, `wf`, `res`, `cols`, `zip_`, `join`, `stack`, `tool`, `resource`, `bound_tool` | the same names, from the package |
| `grid.ResourceNotLoaded` | `ResourceNotLoaded` (also `StepFailed`, `SelectionError`, `PayloadError`) |
| `grid.catalog`, `tool_entry`, `resource_entry`, `modifier_catalog`, `builtin_tools`, `shape_verbs`, `MODIFIERS`, `BUILTIN_TOOLS` | `cat.describe()` (`tools`, `modifiers`, `combines`, `resource_types`) |
| `grid.TOOLS`, `grid.RESOURCE_TYPES`, `REGISTRY`, `register_tool` | gone: a `Catalog` |
| `grid.ToolHandle` | `Tool` |
| `grid.payload_column(output)` | `output.value_column` |
| `grid.grid(value)` (`example_check.as_table`) | `k["x"] = value` then `k.step("x").data`; or `simple_steps_core.verbs.grid` |
| `grid.infer_verb` (the editor's `/api/infer_verb`) | `k.infer_verb(tool, input, arguments, bound_to=…)` → `(verb, why)`, declaring nothing |
| `grid.formula_names` | `cat.formula_names()` |
| `grid.check_modifier`, `predicted_columns`, `check` | `k.check(name, op)` and `step.plan` |

The pin-drift symptom in the app's `CLAUDE.md` and `docs/context.md`
becomes *`cannot import name 'grid' from 'simple_steps_core'`*.

### 3.2 One catalog

`application.App` builds the catalog; nothing registers itself.

- `@simple_step_tool` = core's `@tool` plus `extras={"simple_steps.ui": {name,
  category, widgets}}`; its description goes in the docstring.
- `core_bridge.register_with_core` and `main.py:139` stop using `REGISTRY`;
  `OPERATION_REGISTRY` becomes `Catalog(tools=[…], resources=[…])` or
  `Catalog.from_modules(app_tools)`. `agent/scope.py` reads the catalog.
- The palette is `cat.describe()`; restricting is `cat.without(…)`.
- `core_bridge.py`'s built-in tool groups (the old `ResourceSpec`) become
  plain tools in the catalog, with a tag for the group.

Dead afterwards: `OPERATION_REGISTRY` (56 references), `DEFINITIONS_LIST`,
`core_bridge.py`'s shims (C17, C18, G).

### 3.3 Host core's kernel

`kernels.Kernel` keeps what hosting needs (key, lock, last-used) and holds a
core `Kernel`. The rest it reads from core:

| The app computes | Core gives |
|---|---|
| `Kernel.formulas`, `operations`, `reads`, `uses`, `problems`, `loaded`, `ids` | `k.steps`, `step.formula`, `step.operation.reads`, `step.problems` (each a `Problem` with `code`), `k.resources.loaded`, `step.id` |
| `kernels.summary()` | `repr(k)`, `k.needs_run()` |
| a step's status | `step.state` (`staged`, `completed`, `stale`, `failed`, `invalid`), `step.output.stale_reason` |
| change notifications | `k.on_change(callback)` |
| data for the grid view | `k.view(step, …)` (pages of 50, `window`), `k.cell(step, row id)`, `step.plan` (`size`, types, `inverse`) |
| checking a proposal | `k.check(name, op)` |

`agent/proposals.check_step` calls `k.check`.

### 3.4 Formulas

The parser stays in the app (`operation_formula.py`) and builds
`Operation.from_spec(spec, catalog)`; core prints with `step.formula`.
`formula_parser.py`'s canonical half goes; the UI's `/api/parse_formula`
keeps its response shape.

### 3.5 Saving and loading

`file_manager.py` saves `k.to_json()` and loads `Kernel.from_json(text,
catalog)`. Core reads format 4 only and refuses others with a message, so
**re-save** the mock projects and examples. Under the app's own rule (no
converters without a named user) older workspace files get that message;
a converter is the owner's call (K17, §6).

Secrets: a resource setting typed `Secret[str]` is never saved, so a loaded
kernel asks for it (`k.define(…)` again, or `k.resources.attach`).

### 3.6 What reads differently

Renames from phase 3:

| Was | Now |
|---|---|
| `ToolHandle`, `BoundToolHandle`, `ResourceDecl` | `Tool`, `BoundTool`, `Resource` |
| `op.tool_id`, `step.step_id` | `op.tool`, `step.name` |
| `modifier.params` | `modifier.settings` |
| `step.status` (a string) | `step.state`; `step.status` is a `StepStatus` |
| `PAYLOAD`, `payload_column()`, `meta["payload"]` | `VALUE_COLUMN`, `value_column()`, `output.value_column` |
| preview `["status"]` | `["state"]` |
| JSON `step_id`, `tool_id`, `params` | `name`, `tool`, `settings` (format 4) |
| `name=` on a step | `mod.name(…)` |

Behaviour from phase 4, which the UI and its tests will see:

| Change | Rule ([rules.md](rules.md)) |
|---|---|
| a step's `.data` has its row id `#` as the index, and starts with the `#` columns that say where each row came from (`#v`, …); tools never see them | 2, 3 |
| `k.view` rows carry the row id under `#`, the screen position under `position`; `k.cell` takes a row id | 2 |
| selections and column arguments go by row id, not position | 2, 6 |
| `zip_` and column arguments between unrelated steps are refused; `zip_(…, match_ids=True)` | 6 |
| `collapse`, `distinct`, `join`, `stack` add `#` columns; `gather[collapse()]` gives one list per column; a reducer gets lists | 3, 10 |
| `expand` of a bare string or `None` fails the row; a dict expands to key/value rows | 9 |
| a cell state `absent`; ints stay ints when rows fail | 9 |
| `k["x"] = None` is the empty step | 9 |
| a `-> Record` return spreads into one column per field; `mod.name` takes a list, mapping or pattern; `Kernel(cat, naming=…)` | — |
| `timeout` is enforced; failures say `where`; defaults used warn; a stale read warns | — |
| `plan` has `size` and observed types, or `unknown` with the reason | 7 |
| `k.id`, `k.run_id`, `step.id`, `k.diff(other)`; tool hashes in the catalog spec; a resource's `data_version()` | — |
| a resource passed by position binds as the tool's argument; a plain call with `res[…]` is refused | — |

The `ref_id` the frontend uses (12 references) keeps its name; its value
becomes the step's data version (`step.output.version`), as cleanup-map.md
recommends.

### 3.7 Probes and the handover folder

Regenerate the app's `scripts/core_probes/` and `scripts/core_asks.py`
against the package API (they import `grid`), then rebuild
`core-handover/` with `scripts/core_handover.py`.

## 4. Done means

1. The app's tests pass, with the tests of removed code removed with it, and
   no test of behaviour that stays edited to pass.
2. `scripts/preflight.py` and `examples/runme.py` run.
3. The acceptance session in the app's doc 12: every *update* line passes.
4. `grep -r "simple_steps_core.grid\|REGISTRY\|OPERATION_REGISTRY"` finds nothing.
5. The UI runs a workflow end to end: declare, run, edit (stale), save, load.

## 5. Later, as each core step lands

Additive, each a small pass in the app (cleanup-map.md stage C rows):

| Core step | The app then | Removes |
|---|---|---|
| D: K22 outputs by data version | `/api/data`, `/api/cell`, `/api/data-meta` read from the kernel | `DATA_STORE`, `RAW_STORE`, the leak |
| D: K23, K14 progress, `cancel()` | `progress.py` and `/api/progress/{step_id}` relay core's callback | its own progress bookkeeping |
| D: K15, R9, autorun | a "re-run failed rows" action; stages shown as one block | — |
| E: the output store | `file_manager.py` passes a store; a reloaded workspace opens with its data | — |
| E: R7 media handles | `cell_types.py` reads handles | — |
| F: G18 | the table view from core's step blocks | its own row alignment |

## 6. Decisions

| | Decision | Recommended |
|---|---|---|
| G-D1 | move the app now, before steps D–F | yes: §1 |
| G-D2 | older saved workspaces (K17) | refuse with core's message, as the app's own rule says; a converter only if a named user has files to keep |
| G-D3 | the app's stage A, B, D deletions before the move | yes: less to port, and none of them needs the new core |

## 7. To do in core

What `simple-steps-core` does for this move, then after it. Each item is
one piece, confirmed before it lands; ✓ when done.

### Before the app moves

| | To do | Why |
|---|---|---|
| T1 ✓ | **Tag a release** (`0.2.0`, from `0.1.0`) at the commit the app pins, and bump `__version__` | the app pins a commit today; a tag says which core the migration was checked against |
| T2 ✓ | **Export what the app needs publicly**: `ResourceNotLoaded` (and the other errors), `op`; or say which module each comes from in `docs/integrating.md` | §3.1 sends the app to internal modules for these; an internal name may change |
| T3 ✓ | **A public way to infer a verb and list formula names** (`k.infer_verb`, `cat.formula_names()`): the UI calls `/api/infer_verb` and the parser needs `formula_names` (today `checks.infer_verb`, `catalog.formula_names`, both internal) | the app shouldn't reach into `checks` |
| T4 ✓ | `cat.describe()` gives each tool's **`hash`** beside its tags and extras | the palette and the workflow file show `k.id`; a changed tool should be visible there too |
| T5 ✓ | **Update kernel-session.md and its example** (`examples/kernel_session.py`) with step C: ids, `diff`, `Secret`, `data_version()` | the working guide is what the app's developer reads first (phase-4 *done means*, 4) |
| T6 | **Run the app's acceptance session against core alone** (its doc 12, and the regenerated probes), and fix what fails here, not in the app | "if the app works out a fact about a workflow, that fact belongs in core" |

### Decisions waiting on the owner

| | Decision | Recommended |
|---|---|---|
| C-D2 | the seed recommendation | a tool with a `seed` parameter its step doesn't give warns |
| R-D1 | a resource whose type has bound tools: also passable to a free tool as an argument, or only through its bound tools? | both allowed (today's behaviour), unless you mean to refuse |
| G-D1–3 | §6 | as recommended there |

### Leftovers from step A

| | To do |
|---|---|
| T7 ✓ | `where: expect` on a failure note from an `expect` modifier, like `where: timeout` |
| T8 ✓ | a source tool returning a record gives one row, a list of records a row per record, a column per field; an item that doesn't fit fails the step, `where: declared`. An undeclared `list[dict]` stays one cell |

### After the move: the rest of phase 4

In order, each as its step in [phase4-plan.md](phase4-plan.md), and each
followed by its small pass in the app (§5):

| | Step | Needs first |
|---|---|---|
| T9 | **D. Sessions**: K22 outputs by data version, K23/K14 progress and `cancel()`, K15 re-run failed rows, R9 stages, the autorun modifier | D-D1 (autorun design), D-D2 (progress callback) |
| T10 | **E. Storage**: C32/K16 the output store, R7 media handles | E-D1 (the store's interface) |
| T11 | **F. The workflow as a table** (G18) | nothing new |
| T12 | `scripts/core_asks.py` at 39 of 39 (K14, K15, K16 close with D and E) | T9, T10 |
| T13 | **Phase 5, the final docs** (cleanup-plan.md §6): README, writing-tools, resources (secrets, data versions), modifiers, integrating (for the app), problems | phase 4 done |
