# Cleanup and restructure plan

> Proposed 2026-10-26, branch `core-handover`. Checked at `86170a3`:
> 599 tests pass; `grid.py` imports nothing else from core; the app reaches the
> older engine in two places only (`core_bridge.py`, `main.py:139`).

## 1. Remove: everything that isn't the grid model

The package holds two models. The grid (`grid.py`) is the one we keep; the rest
is the older engine and its server, reached only through `__init__.py`'s
re-exports, so removing it can't break the grid.

| Path | What it is |
|---|---|
| `src/simple_steps_core/execution/` | older engine, data store, resolver, sessions |
| `src/simple_steps_core/operations/` | global `REGISTRY`, orchestrators, old `ResourceSpec`, UI hints |
| `src/simple_steps_core/domain/` | older engine's data types (`media.py` is in git at `0b8cfb1`, for R7) |
| `src/simple_steps_core/api/`, `serving.py`, `loader.py`, `app.py`, `agent/`, `inspect.py` | old public API, HTTP server, tools-file loader, a second `App`, agent types, `SummaryTable` |
| `src/simple_steps_core/__init__.py` | rewritten to export the new public names (§3) |
| 21 test files under `tests/`, and `tests/unit/_pipeline_tools.py` | every test except `test_grid.py`, `test_008_asks.py`, `test_all_orchestrations.py`. The helper is used only by `test_example_pipeline.py` (older engine) |
| `example_server.py`, `runme.py`, `desired_functionality.md`, `specs/` | written against `register_tool`, `Server`, `CoreEngine` |
| `tutorial_notebook/` | older engine walkthrough. Replaced by `examples/notebook.ipynb` |
| `skills/video-transcript-pipeline/` | a skill for the older engine |
| `.claude/skills/simple-steps-core/` | teaches `@register_tool`, `Server().run()`, `Dashboard`. Rewritten for the kernel once phase 3 lands; removed in phase 1 so it can't mislead |
| `docs/*` except the three below, and `docs/core-proposals/` | describe both models, or are history. Git keeps the history |
| `pyproject.toml`: `pydantic`, extras `agent`, `api` | only the older engine uses them. Core depends on `pandas` alone. `examples` keeps `notebook` |

Kept for now, then folded into the new docs and removed: `docs/grid-model.md`,
`docs/shape-algebra.md`, `docs/step-expressions.md`. They explain the verbs and
the algebra well but use retired words (ledger, `over=`, payload).

Local clutter, not tracked: `build/`, `.coverage`, the root `__pycache__/`.

**Carried onto the grid before its code goes, or dropped on purpose:**

| Older engine | Decision |
|---|---|
| `MediaAsset` / `MediaStore` | removed; ported as R7 in phase 4 from `domain/media.py` at `0b8cfb1` |
| `ArgGuardrail` | dropped. Limits on arguments are the tool's job |
| `CodecRegistry` | dropped; replaced by the output store (K22, C32) |
| `SummaryTable` | dropped; replaced by `repr(k)` |

## 2. Remove or change inside the grid

| Today | Becomes |
|---|---|
| `TOOLS`, `TOOL_TAGS`, `declared_tools()` | gone. `@tool` registers nothing; tools go into a `Catalog` |
| `RESOURCE_TYPES`, `resource_types()` | gone. Resource types go into a `Catalog` |
| `freeze()`, `is_frozen()`, `_FROZEN` | gone. A catalog is immutable |
| `STRICT_TYPES`, `settings` / `SIMPLE_STEPS_IMPLICIT_AUTO` | kernel options |
| `_VIEWS` (cache of method views) | held by the resource type or catalog |
| `catalog()`, `tool_entry()`, `modifier_catalog()`, `resource_entry()`, `resource_catalog()`, `builtin_tools()`, `shape_verbs()`, `formula_names()` | `Catalog.describe()` and catalog methods |
| public tables: `MODIFIERS`, `DECORATORS`, `PARAM_TYPES`, `PARAM_TYPES_BY_VERB`, `REQUIRED_PARAMS`, `ROWS_RULE`, `DEFAULT_PAYLOAD`, `COMBINE`, `BUILTIN_TOOLS`, `DEFAULT_TOOL`, `TOOL_SETTINGS`, `CARRIES_COLUMNS` | private |
| verb functions `map_`, `filter_`, … `rows`, `grid()` | private: the kernel runs them |
| `over=` in modifiers | refused: the input is the call's argument |
| `run(tools=…, resources=…)`, `from_json(tools=…)` | `Kernel.run`, `Kernel.from_json(text, catalog)` |
| `to_session_dict` / `to_session_json` | the output store's snapshot (phase 4, C32) |
| `ToolHandle`, `tool_id`, `step_id`, `ResourceDecl`, `Modifier.params`, `Step.status`, `meta["payload"]` | `Tool`, `name`, `name`, `ResourceSpec`, `Modifier.settings`, `Step.state`, `Output.value_column` |
| problems as strings | `Problem` |

## 3. The new package layout

`grid.py` (7,444 lines) is split along the object model. Each module holds one
object or one job. **Phase 2 built the first fifteen rows**, moving code
unchanged; the last three arrive in phase 3, and the phase-3 contents of each
module are in *italics*.

| Module | Holds (phase 2) | Lines |
|---|---|---|
| `workflow.py` | `Workflow` (*`WorkflowSpec`*) | 1,400 |
| `step.py` | `Step`, staleness helpers (`_ran_with`, `_changes_text`, `_row_fps`) (*`StepSpec`, `StepStatus`*) | 172 |
| `checks.py` | declaration checks and staging: `check`, `warn`, `stage`, `infer_verb`, plan helpers | 1,316 |
| `run.py` | compiling an operation into a callable (`compile_operation`), and `auto` | 163 |
| `verbs.py` | the shape verbs and reshapes on DataFrames, and calling a tool per row | 941 |
| `combines.py` | `join`, `stack`, `zip_` | 245 |
| `operation.py` | `Operation`, `op`, formula printing (*`from_spec()`*) | 461 |
| `references.py` | `StepRef`, `ResRef`, `ToolRef`, selections, the proxies `wf`, `res`, `rows`, `cols` | 492 |
| `modifiers.py` | `Modifier`, the modifier kinds and their run-time decorators, `mod` | 596 |
| `catalog.py` | `@tool`, `ToolHandle`, `@resource`, `ResourceDecl`, bound tools, tool and resource descriptions, the registries (*`Catalog`, `Tool`; no registries*) | 738 |
| `system_tools.py` | `identity`, `gather`, `count`, `total`, `first`, `last` | 127 |
| `output.py` | `Output`, cell states, notes, versions, `PAYLOAD`, `ROW_ID` | 416 |
| `values.py` | literal types, type checks, saving arguments and outputs to JSON | 704 |
| `errors.py` | `SelectionError`, `StepFailed`, `PayloadError`, `ResourceNotLoaded` | 73 |
| `options.py` | `Settings` (*becomes kernel options*) | 34 |
| *`kernel.py`* | *`Kernel`: editing, running, resources, store* | — |
| *`problems.py`* | *`Problem` and its codes* | — |
| *`display.py`* | *`repr` and `_repr_html_` for kernel, step, catalog* | — |

`grid.py` is now a 94-line compatibility layer: it loads the modules in
dependency order and re-exports every name, so the tests didn't change.
**How the modules refer to each other** (phase 2 only): each imports at the top
what it needs while loading, and at the bottom the names it uses only inside
functions. Phase 3 replaces this with plain imports as the objects are
rebuilt, and removes `grid.py`.

The public names, all from `simple_steps_core`:

```python
Kernel, Catalog, tool, resource, Secret, mod, wf, res, rows, cols,
join, stack, zip_, Operation, Step, Output, Problem, ResourceSpec,
KernelSpec, WorkflowSpec, StepSpec
```

The `grid` module goes. The app changes its imports once, in phase 3.

## 4. Order of work

Each phase ends with every test passing. Phases 1 and 2 change no behaviour.

| Phase | Work | Done when |
|---|---|---|
| **0** | These design docs | the owner confirms them |
| **1. Remove** | §1: delete the older engine, its tests, docs and extras; cut `__init__.py` down to the grid; drop `pydantic` | the 3 grid test files pass; `python examples/all_orchestrations/pipeline.py` runs |
| **2. Split** | §3 layout, moving code without changing it. `simple_steps_core.grid` re-exports everything for this phase only | the same tests pass, unchanged |
| **3. Object model** | §2 and [object-model.md](object-model.md): `Catalog`, `Tool`, `Kernel`, specs, `Problem`, step state, `Output` fields, `insert`/`move`, `k.check`, display. Remove `grid`. Rewrite the tests and examples on the kernel | `examples/kernel_session.py` and its test pass (the guide in [kernel-session.md](kernel-session.md)); every example runs |
| **4. Behaviour** | the K-asks, one at a time, each confirmed before it lands: K19 (row ids, column arguments), K20 (hashes, ids), K22 (outputs by version), K23 (progress, cancel), K25–K29, R7, R8, R9 (stages), C28–C32, K18, G1–G15 found while writing these docs, and the autorun modifier once its design is settled ([interactive-sessions.md §6.2](interactive-sessions.md#62-an-autorun-modifier-planned-to-be-designed)) | each ask's probe passes; for reshaping, every law in [reshaping.md §10](reshaping.md#10-the-laws) passes ([reshaping-plan.md](reshaping-plan.md) is that path) |
| **5. Docs** | the final docs set (§6) | each doc's examples run as tests |

### Phase 3, piece by piece

Each piece keeps every test passing. The process-wide registry stays as the
fallback for a workflow made without a catalog until the last piece, when the
tests and examples have moved onto the kernel.

| Piece | What | Status |
|---|---|---|
| 3a | `Catalog`: tools, resource types, built-ins, modifiers, combines; `without`, `from_modules`, `describe`. A workflow with a catalog checks every step against it (declared, re-checked or loaded) and runs the catalog's functions. Tools carry their `tags` and `extras` | done |
| 3b | `Kernel`: a catalog, a workflow, loaded resources (built from their spec when first needed, or attached); declare, edit, rename, delete; `run` (never-run inputs first, stale ones pass through), `run_all`; `view`, `cell`; `to_json`, `from_json(text, catalog)`; a table `repr` and `_repr_html_`. The public names are exported from `simple_steps_core` | done |
| 3c | `Problem` (a `str` with `code`, `step`, `argument`, `row`, `severity`; 33 codes in `problems.CODES`), given by every section of `check()` and `warn()` and by the catalog; `step.state`, `step.name`, `step.data`; `Output.version`, `read`, `plan`, `value_column`, `staged`, `stale`, `stale_reason`, `ran_with` (read from `meta` until 3e); `step.status` stays an alias of `state` until 3e | done |
| 3d | `spec` on every object (`StepSpec`, `WorkflowSpec`, `ResourceSpec`, `CatalogSpec`, `KernelSpec`; `Kernel.from_spec`); `extras` on steps, resources and the workflow, saved and loaded; warnings name their step; `k.check(name, op)`; `k.needs_run()` and a *read stale* mark (a step run on a stale input is `completed`, and becomes stale only when that input's data changes); `k.on_change(callback)`; `k.insert`, `k.move` | done |
| 3e (1) | isolation (K24): `@tool` and `@resource` register nothing; `TOOLS`, `TOOL_TAGS`, `RESOURCE_TYPES`, `freeze`, `is_frozen`, `declared_tools`, `resource_types()`, `STRICT_TYPES` and `settings.implicit_auto` are gone. Strictness is per tool or `Catalog(..., strict=True)`; implicit auto is always on. A workflow without a catalog uses only the functions its operations carry, or a `tools=` table passed to `from_json`, which also resolves tools saved as settings. Tests and examples name their tools explicitly | done |
| 3e (2) | renamed to the agreed words (`Tool`, `BoundTool`, `Resource`, `Operation.tool`, `Step.name`, `Modifier.settings`, `VALUE_COLUMN`, `value_column()`); `step.status` is a `StepStatus` and `step.state` the string; saved format v4 (`name`, `tool`, `settings`), other versions refused; `grid` removed, the package exports the public API and loads the modules in order; `Operation.from_spec(spec, catalog)`. Plain imports deferred to phase 4 | done |

**Isolation was finished in 3e (1).** Before it, a kernel never *read*
process-wide state, but core still *wrote* it: `@tool` adds every
tool to `TOOLS` and `TOOL_TAGS`, and `@resource` and `define()` add resource
types to `RESOURCE_TYPES`. Two same-named tools in one process therefore swap
the global entry (with a warning), which only affects workflows made without a
catalog. 3e removes these writes, together with:

- the bottom-of-module imports and fixed load order from phase 2, which break
  if a module adds an ordinary top-level import of another; 3e replaces them
  with plain imports;
- the old-path tests: the 405 tests from before phase 3 run on workflows
  without a catalog, so 3e moves them onto the kernel, where only 31 tests run
  today.

**Known limitation: a kernel's catalog is fixed** (accepted 2026-10-26). A
catalog holds the exact functions it was made with. Editing a tool in a
notebook and re-running its cell makes a new function: steps written with it
are refused as *"a different function from the tool of that name"*, and
existing steps keep running the old code. To use the edited tool, make a new
catalog and kernel (`Kernel.from_json(k.to_json(), new_cat)` keeps the steps).
A way to swap a kernel's catalog, marking steps whose tool changed as stale
(K20), can be added later if tinkering needs it.

**Any catalog entry can be removed, core ones included** (decided 2026-10-26).
`identity`, `source` and `select` are what literal and selection steps are built
on, and they can still be left out. A step that uses an entry its catalog
doesn't have can't run (a problem on the step); if it already has an output,
that output is kept and shown as stale, and so are the outputs of the steps
after it. This matters when a kernel's catalog changes (the swap above) or a
saved workflow with its outputs is loaded against a smaller catalog.

## 5. What the app changes

Its pin is a fixed commit, so nothing breaks until it moves. Phase 3 is the
migration point. Moving to it:

1. **Import from the package, not `grid`.** `from simple_steps_core import
   Catalog, Kernel, tool, resource, bound_tool, mod, wf, res, cols, rows, join,
   stack, zip_, Operation, Step, Output, Problem`. Anything else comes from its
   module (`simple_steps_core.catalog`, `.checks`, …), which may change.
2. **Build a catalog** where `core_bridge.py` used `register_tool`,
   `REGISTRY` and `ResourceSpec`, and `main.py:139` used `REGISTRY`:
   `Catalog.from_modules(app_tools)` or `Catalog(tools=[...], resources=[...])`.
   `@tool` and `@resource` register nothing.
3. **Read the palette from the catalog.** `cat.describe()` replaces
   `grid.catalog()`, `tool_entry`, `modifier_catalog`, `resource_catalog`,
   `builtin_tools`, `shape_verbs`, `TOOLS`, `RESOURCE_TYPES` and `freeze`.
4. **Host core's `Kernel`.** `kernels.py` keeps key, lock and last-used; the
   rest comes from core: `k.step(n).state`, `.problems` (with `.code`),
   `k.needs_run()`, `k.on_change(callback)`, `k.view`, `k.cell`, `k.check`.
5. **Hand formulas to core as operations.** The parser (`operation_formula.py`)
   stays in the app and builds `Operation.from_spec(spec, catalog)`;
   `agent/proposals.py`'s `check_step` calls `k.check(name, op)`.
6. **Rename what it reads:**

   | Was | Now |
   |---|---|
   | `ToolHandle`, `BoundToolHandle`, `ResourceDecl` | `Tool`, `BoundTool`, `Resource` |
   | `op.tool_id`, `step.step_id` | `op.tool`, `step.name` |
   | `modifier.params` | `modifier.settings` |
   | `step.status` (a string) | `step.state`; `step.status` is a `StepStatus` |
   | `PAYLOAD`, `payload_column()`, `meta["payload"]` | `VALUE_COLUMN`, `value_column()`, `output.value_column` |
   | preview `["status"]` | preview `["state"]` |
   | JSON `step_id`, `tool_id`, `params` | `name`, `tool`, `settings` (format version 4) |

7. **Re-save its workflows and examples.** Files in other format versions are
   refused, with a message.
8. **Regenerate `core-handover/`'s probes** against the new API; they import
   `grid` and no longer run here.
9. The "symptom of pin drift" in the app's docs becomes
   `cannot import name 'grid' from 'simple_steps_core'`.

## 6. The documentation after the work

| Doc | For |
|---|---|
| `README.md` | what core is, install, the kernel session in 20 lines |
| `docs/object-model.md` | this design's object model, updated to what was built |
| `docs/kernel-session.md` | working in a terminal or notebook |
| `docs/grid-model.md`, `docs/outputs-and-reshaping.md`, `docs/step-expressions.md`, `docs/extensions.md` | these design docs, updated to what was built; they replace the three older docs of the same subjects |
| `docs/writing-tools.md` | `@tool`, types, docstrings, built-ins, bound tools |
| `docs/resources.md` | resource types, settings, secrets, data versions |
| `docs/modifiers.md` | every modifier and combine: what it does to the grid, its settings, examples |
| `docs/integrating.md` | for the app: catalog descriptions, `Operation.from_spec`, problems and their codes, specs, extras, hosting many kernels |
| `docs/problems.md` | every problem code and what fixes it |
| `CLAUDE.md` | the rules (design README) and the words |

## 7. Decided here, for the owner to confirm

Choices this plan makes that the handover didn't settle:

1. **The kernel is the object you hold;** `k["x"] = …` declares steps. Formulas
   still write references as `wf["p"]`, so a line reads the same in a terminal
   and in the formula bar.
2. **A step's name is its identity in a spec;** its index is a lookup. A
   reference written by index is saved by name.
3. **`step.state`** replaces `step.status`, so "status" means only "the live
   part of an object".
4. **Agent permissions are catalog `extras`** (`"simple_steps.agent"`), not a
   core field, since the agent is the app's.
5. **`to_source()` stays in core** (the terminal view needs it); the parser
   stays in the app.
6. **`over=` is retired.**
7. **The `grid` module name goes** at phase 3; phase 2 keeps it as a
   compatibility layer only.
8. **One kernel per terminal session is a convention,** not enforced, since the
   app holds many per process.
9. **Extensions never change outputs** ([extensions.md §2](extensions.md#2-the-rule-for-extensions)).
   A tool's custom UI is an extension; what it collects is saved as literal
   arguments.
10. **Modifiers have five classes** (shape, execution, error handling,
    expectation, observation); observation isn't hashed.

Decided by the owner, 2026-10-26:

- A row caught with a `try_except` default is `known`; the step gets a
  warning. A default that doesn't fit the return type makes a union type and a
  warning when declared.
- An execution modifier before the verb is allowed, with a warning; every
  failure's note says where it happened.
- Modifiers read left to right as decorator layers, outermost first.
- One shape verb per step, so a step never hides an intermediate grid; long
  sequences are managed with **stages**, a feature defined on top of steps for
  execution management. A stage can't be referenced; steps inside it can.
- A grid should be a tidy table: columns are variables, rows are
  observations, with named exceptions (objects in cells, several objects per
  call, deliberate wide tables).
- A tool's declared return type is its contract: a declared record type
  spreads into one column per field, under an explicit verb or `auto`. A
  typed tuple spreads only when named.
- Outputs are named with a new modifier, `mod.name` (a name, a list, a mapping
  or a pattern such as `"{step}_{field}"`)
  ([outputs-and-reshaping.md §4](outputs-and-reshaping.md#4-naming-outputs-modname)).
- Observing modifiers can be saved in a step, unhashed.
- Developer-defined modifiers come later, under the rules in
  [extensions.md §5](extensions.md#5-developer-defined-modifiers-later-under-these-rules).

Found by running core while writing these docs (to fix in phase 4,
[grid-model.md §8](grid-model.md#8-found-while-checking-to-fix-in-phase-4)): `group(by="city")`
fails at run instead of when declared (G1); `stack` writes `NaN` and floats
(G2); a source's own index becomes a column (G3); `to_source()` loses literal,
reshape and selection forms (G4); `collapse` without `initial=` (G5); a
mismatched `try_except` default is silent (G6); the new warnings and `where`
(G7); record returns aren't spread and `widen` ignores declared fields,
keeps the spread column and fails only at run (G8–G10); DataFrame returns per
row aren't flagged (G11); no naming modifier (G12); readers aren't re-checked when an upstream's
columns change (G13); `run` doesn't run never-run inputs first (G14); no `needs_run`, change
callbacks or stale-read mark (G15, done in 3d); a literal step's value isn't saved,
so `k["x"] = [3, 1, 2]` reloads with no data (G16, done: literals are saved; a DataFrame assigned in Python isn't).

- `mod.name` replaces `name=`; an undeclared dict stays one cell; kernel-wide
  naming conventions are a kernel option; one grid per step; combines number
  rows 0…N-1 with per-cell lineage
  ([outputs-and-reshaping.md §9](outputs-and-reshaping.md#9-decided)).
- Status is reactive, computing is explicit. `run("f")` computes from what its
  inputs show, stale ones included, and marks that it read them;
  `k.needs_run()` and `k.on_change` make it obvious what to re-run;
  nothing re-runs on its own unless a step opts in with an autorun modifier,
  which is planned and still to be designed
  ([interactive-sessions.md](interactive-sessions.md)).
- Stage rules: consecutive steps, no nesting, a step in at most one stage.

Still open: row ids from a source tool that sets its own index (G3); whether
a resource reports a data version by a method or a setting (K25).
