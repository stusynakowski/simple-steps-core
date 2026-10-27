<!-- from docs/system_design/12-core-and-app.md -->

## The core update: what moves, what's fixed, what must work

> Planned 2026-10-26 with the owner, who is making the core changes. Checked
> by running core at the current pin; each claim below was run, not read.
> Each behaviour change is still confirmed one piece at a time before it lands.

**The goal.** Everything Simple Steps can do to a workflow can be done on a
`grid.Workflow` in a Python terminal: define steps, run them, read values,
states and problems, save and load. That is the isolation test. The app adds
only transport (HTTP, UI), identity (sessions), storage location (workspace,
snapshots), concurrency (kernels, locks) and the agent's conversation. If the
app works out a fact about a workflow, that fact belongs in core.

**Two words.** A **workflow** is core's object, the steps and their outputs. A
**kernel** is one workflow together with the tools it runs with: a workflow
and its catalog. **`kernel.spec`** is the structure needed to reproduce that
workflow with that particular set of tools (owner, 2026-10-26). Hosting a
kernel on a server (key, lock, last-used, snapshots) is the app's job and is
not part of its spec. A **registry** is everything a decorator added (one per library, if
kept); a **catalog** is what a workflow may use, chosen from it. Nothing runs
from a registry directly.

### Core's object model, after the update

| Object | Does | Contains | Today |
|---|---|---|---|
| **Catalog** | says what a workflow may use | tools, modifiers, combines, resource types, literal types; agent permission per entry | missing as an object. `grid.TOOLS` is one process-wide dict; `grid.catalog(tools)` only *describes* tools; `Workflow()` takes no catalog |
| **Tool** | one Python function, described | function, name, typed parameters and defaults, docstring and `Args:`, return type, tags | exists (`@tool`, `ToolHandle`) |
| **Modifier** | how a tool meets the grid | kind (`map`, `filter`, `expand`, `collapse`, `table`, `sort`, `select`, …) and settings | exists (`mod.*`) |
| **Resource** | something tools use | type, config (`ResourceDecl`), the live instance | exists (`define`, `res["x"]`) |
| **Reference** | points at earlier data | `StepRef`, a selection (rows, columns, cell) by row id, `ResRef` | exists; selections are by position |
| **Operation** | a step's description, nothing run | tool, modifiers, arguments, input(s) | exists; prints itself (`to_source()`) but can't be parsed from text |
| **Step** | one line of the workflow | name, position (its id), operation, output, status, problems, warnings | exists |
| **Output** | what a step produced, always a DataFrame | `data` with its row id, `meta`, per-row `states` | exists |
| **Workflow** | the ordered steps | steps, resources | exists |
| **Kernel** | a workflow with the tools it runs with; what you hold in a terminal | a workflow, a catalog, the loaded resources | missing in core; the app's `Kernel` (`kernels.py`) holds a workflow but no catalog |
| **Formula** | a step's line of text, both ways | `parse(text, catalog) → Operation`, `to_source()` | half: the printer is in core, the parser is in this repo |
| **Problem** | why a step can't run or ran badly | step, code, message, row if any | plain strings today |

### One step, several forms

Decided by the owner on 2026-10-26. "Step" names several things that overlap.
They are different things, but they all point to **the same output**.

| Form | Where you meet it | What it is | Has data? |
|---|---|---|---|
| **The line** | the formula bar, a terminal, an agent's proposal | `wf["spec"] = tool[mod.map()](wf["x"], a=1)`. A valid line on its own is a valid step | no |
| **The operation** | inside core | the line parsed: tool, modifiers, arguments, inputs (`Operation`) | no |
| **The step spec** | a workflow file (`to_json`), `step.spec` | the recipe: everything needed to produce the same output, assuming the steps and resources it references hold the same data | no |
| **The live step** | the kernel, the UI, `wf.step("x")` | the spec plus its status: output, state, problems | yes |

What this asks of core:

- **Every form converts to the others without loss.** Line → operation →
  step spec → operation → line gives the same line (`to_source()` exists; the
  parser moves to core).
- **Same recipe, same references, same output.** Two forms of one step can
  never run differently, whether it's typed in a terminal, clicked in the UI,
  or loaded from a file.
- **The recipe names tools; it doesn't contain them.** So "the same output"
  also assumes the same tool code from the catalog. A step spec records which
  catalog entry it used. Whether it should also record that entry's version,
  so a changed tool marks the step stale, is open.

### Spec and status, for every object

Decided by the owner on 2026-10-26. Every object has a **spec**, its saved
form: everything needed to produce the same output, assuming what it
references holds the same data. What's live about it is its **status**. A live
object is its spec plus its status. Saving writes the spec; loading builds the
object from a spec and a catalog.

| Object | Spec (the recipe, never data) | Status (live) |
|---|---|---|
| Workflow | its step specs in order, and its resource specs | its live steps |
| Step | name, position, operation | output, state, problems, warnings |
| Operation | tool name, modifiers, arguments, references | none; an operation is all spec |
| Resource | `ResourceSpec`: the type and settings needed to load the right resource (today's `ResourceDecl`) | the loaded instance, such as an open connection |
| Catalog | the entry names it allows, and their permissions | the functions themselves |
| Kernel | `kernel.spec`: the workflow spec plus the catalog spec, everything needed to reproduce the workflow with that set of tools | the live workflow and loaded resources. The app's hosting (key, lock, last-used) is outside both |

Rules for core:

- `spec` is an attribute holding a plain value (a frozen dataclass or dict):
  `wf.spec`, `wf.step("f").spec`, `res["db"].spec`. `to_json()` is the spec as
  JSON; `Workflow.from_spec(spec, catalog)` builds it back.
- A spec never holds output data. A file that also carries outputs (core's
  `to_session_dict`) is a spec plus a snapshot of outputs, not a spec.
- A step is stale when its spec, or the spec of a step it reads, changed after
  it ran (core tracks this as `ran_with`).
- `docs/spec/` is unrelated: the requirements docs of spec-driven development.

### Migrate from this repo to core

| From here | Becomes in core | Why |
|---|---|---|
| `operation_formula.py`, the safe AST parser | `Formula.parse` beside `to_source()` | it defines the language. The terminal, UI and agent then share one parser, and text ⇄ operation round-trips in one place |
| `App`'s tool scoping (`application.py`) | `Catalog`, passed to `Workflow(catalog=…)` and `from_json(…, catalog=…)` | a limit is only real on something a workflow is given ([how-simple-steps-works.md §7, item 11](../how-simple-steps-works.md)) |
| the formula checks in `agent/proposals.py` (`check_step`, `check_proposal`) | `Workflow.validate` taking a proposed formula | they're about formulas, not chat |
| `kernels.summary()` (status, stale reason, problems per step) | the workflow's own display | a fact about the workflow |
| the empty-step rule: a 1×1 frame, one cell `"empty"` | `Output` | part of what an output is |
| plain-text summaries in `cell_types.py` | a terminal view of a cell | optional; PNG and Plotly views stay here, as UI |

### Fix in core

| What | Today (run on the current pin) | Should |
|---|---|---|
| Catalog is global | a `@tool` defined anywhere is usable by every workflow in the process | a workflow runs only tools in its catalog; anything else is a problem on the step |
| A column as an argument | untyped: every row gets the whole list; typed `int`: refused, output `None` | per row by the parameter's type ([008 K19](../core-proposals/008-core-changes.md#k19-a-column-argument-pairs-per-row-by-type)) |
| Selections by position | after a sort, `wf["srt"][0]` picks a different row | pick by row id, which is the frame's index (K19). Reconcile with the existing `#` (`grid.ROW_ID`) so there is one id, not two |
| Row ids from verbs that make rows | unsettled for `expand`, `stack`, `join`, sources | defined, and unique, so `wf["r"][0]` can't match two rows |
| Reading a workflow in a terminal | `wf` prints `<Workflow 3 step(s): [...]>`; `wf["f"]` prints `<f>`; values are `wf.step("f").output.data` | `repr(wf)` is a table: step, formula, status, shape, first problem. A short way to get a step's values |
| `ResourceSpec` means something else | in the older engine it's a namespace of tools; this repo uses it for built-in tool groups. A resource's spec is `ResourceDecl` in the grid | `ResourceSpec` is a resource's spec: the type and settings to load the right resource (rename `ResourceDecl`). Tool groups get their own name in the catalog |
| No `spec` attribute | `to_json`, `to_dict`, `to_session_dict` | `wf.spec`, `step.spec`, `res[…].spec`, and `Workflow.from_spec(spec, catalog)` |
| No identity for a kernel | data versions and resource hashes exist; tool code and the kernel aren't hashed | `k.id`, `k.run_id`, `k.diff(other)`; a changed tool marks its steps stale ([008 K20](../core-proposals/008-core-changes.md#k20-kernel-and-run-identifiers-by-hashing-specs)) |
| No room for the app's additions | the app keeps UI information beside core's specs | an `extras` mapping per spec, saved but not hashed, for custom UI components ([008 K21](../core-proposals/008-core-changes.md#k21-room-in-each-spec-for-the-apps-additions)) |
| Only the latest output is kept | a stale reader can't show what it was computed from; the app's `DATA_STORE` keeps every copy and frees none | outputs stored by data version, freed when nothing reads them ([008 K22](../core-proposals/008-core-changes.md#k22-keep-earlier-outputs-while-something-still-reads-them)) |
| Progress and cancelling | the app watches from outside (`progress.py`) | progress modifiers that report each cell's state to a callback; `cancel()` ([K23](../core-proposals/008-core-changes.md#k23-progress-and-cancellation-as-modifiers)) |
| Shared state | `grid.TOOLS` is process-wide | nothing mutable at module level; each kernel holds its own ([K24](../core-proposals/008-core-changes.md#k24-no-state-shared-between-workflows)) |
| Resource settings per context | — | literal defaults; whether a resource reports a data version is open ([K25](../core-proposals/008-core-changes.md#k25-resource-defaults-are-literals)) |
| Data scale | — | row count and estimated size per output; pages of 50–100 rows ([K26](../core-proposals/008-core-changes.md#k26-size-estimates-and-output-in-pages)) |
| Unknown return types | — | `unknown` until it runs, then the observed type or union ([K27](../core-proposals/008-core-changes.md#k27-return-types-unknown-until-it-runs-then-what-it-returned)) |
| Cell lineage | worked out on request by `wf.cell` | stored per cell in each output, with changed cells marked ([K28](../core-proposals/008-core-changes.md#k28-cell-to-cell-lineage-stored-in-each-output)) |
| Reading old data | — | a warning naming the step and version read ([K29](../core-proposals/008-core-changes.md#k29-renames-references-follow-and-reading-old-data-warns)) |
| Literal types | listed in the catalog but not defined | core defines the set (owner, 2026-10-26); the parser accepts only those |
| Problems | strings | structured: step, code, message, row |
| Two models in one package | the older engine's `Workflow`, `Operation`, `Step` sit beside the grid's, with different meanings (core's `__init__` says so) | one model, the grid |

### Remove from core: everything that isn't the grid model

Decided by the owner on 2026-10-26: **the grid model is the main model.**
Every component of core that isn't the grid model is updated onto it or
removed.

Checked on the current pin: `grid.py` (7,444 lines) imports nothing from the
rest of core. Every other module belongs to the older engine and its server,
reached only through core's `__init__` re-exports. So removing them can't
break the grid itself.

| In core now | Lines | What it is | Do |
|---|---|---|---|
| `grid.py` | 7,444 | the grid model | **keep**. Split it by the object model once the rest is gone (catalog, formula, spec, run, combines) |
| `execution/` (`engine`, `workflow`, `data_store`, `resolver`, `context`, `resources`, `session_io`, `session_manager`) | 1,775 | the older engine, its stores and sessions | remove |
| `operations/` (`registry`, `orchestrations`, `validation`, `schema`, `resource_spec`, `dependencies`, `ui`) | 1,844 | the global `REGISTRY`, orchestrators, the old `ResourceSpec`, UI hints | remove. The catalog replaces the registry |
| `domain/` (`models`, `collections`, `media`, `references`, `tabular`) | 1,144 | the older engine's data types | remove. Carry `media` over first if wanted (R7) |
| `serving.py`, `api/`, `loader.py` | 436 | HTTP server, the old public API, loading a tools file onto `REGISTRY` | remove. Serving is the app's |
| `app.py` | 208 | a second `App`, `AppConfig`, `Session` | remove. The app has its own |
| `agent/` | 36 | agent types | remove. The agent is an app layer |
| `inspect.py` | 90 | `SummaryTable`, `repr` and `info()` for the old objects | remove, or reuse for the readable `repr(wf)` |
| `__init__.py` | 198 | re-exports the older engine; warns that `Workflow`, `Operation`, `Step` mean two things | cut down to the grid |
| tests | 24 files | only 3 mention `grid` (`test_grid`, `test_008_asks`, `test_all_orchestrations`). The other 21 test the older engine | remove with their code |
| `example_server.py`, `runme.py`, `examples/`, `tutorial_notebook/` | — | written against `register_tool`, `Server`, `CoreEngine` | rewrite on the grid; the acceptance session above is the new `runme.py` |
| `docs/` (`object-model`, `api-reference`, `migration-plan`, …), `specs/` | — | describe both models | keep `grid-model.md`, `shape-algebra.md`, `step-expressions.md`; rewrite or drop the rest |
| `[agent]` extra in `pyproject.toml` | — | `langgraph`, `langchain-core` | remove |

**Only the older engine has these.** Each is carried onto the grid before its
code goes, or dropped on purpose:

| Older engine | On the grid |
|---|---|
| `MediaAsset` / `MediaStore` (images as handles) | R7 asks to port it |
| `ArgGuardrail` (limits on argument values) | the catalog's per-entry rules, if wanted |
| `CodecRegistry` (saving values that aren't tables) | the output store (K22, C32) and C29 |
| `SummaryTable` (`info()` tables) | the readable `repr` |

**What this repo changes first,** since it still reaches the older engine in
two files: `core_bridge.py` (`register_tool`, `REGISTRY`, `ResourceSpec`) and
`main.py:139` (`REGISTRY`). Both move to the catalog. The name `ResourceSpec` is
then reused for a resource's spec. `CLAUDE.md` and `context.md` give
`cannot import name 'ResourceSpec'` as the symptom of pin drift; that line
changes to a name that's actually new.

### Stays in the app

The kernel host, cut to key, workflow, lock and last-used (its `formulas`,
`operations`, `reads`, `uses`, `problems` duplicate core's step; `ids` is
replaced by `wf.rename`; `loaded` goes with the old syntax). Sessions, HTTP
routes, the workspace and workflow files, cell views, the UI, the agent's
conversation and chat history.

### What should work: the acceptance session

Each line runs in a plain `python` prompt with only core installed. The ones
marked **now** pass at the current pin; the rest are the update.

```python
from simple_steps_core import grid
from simple_steps_core.grid import mod, tool

@tool
def patients(): ...                                   # a source
@tool
def to_f(temp_c: float) -> float: ...
@tool
def feverish(temp_c: float, limit: float = 38) -> bool: ...

cat = grid.Catalog([patients, to_f, feverish])        # update: a catalog object
wf = grid.Workflow(catalog=cat)                       # update

wf["p"]    = patients[mod.source()]()                 # now
wf["sick"] = feverish[mod.filter()](wf["p"])          # now
wf["f"]    = to_f[mod.map()](wf["sick"])              # now
wf["g"]    = "to_f[mod.map()](wf['p'])"               # update: formula text, parsed against the catalog
wf.validate()                                         # now: {step: problems}
wf.run_all()                                          # now
wf                                                    # update: table of step, formula, status, shape
wf.step("f").output.data                              # now: Ben's row keeps label 1
wf.step("f").operation.to_source()                    # now: 'to_f[mod.map()](wf["sick"])'
wf.cell("f", 0, "value")                              # now: value, type and the input row it came from

wf["sick"] = feverish[mod.filter()](wf["p"], limit=37)
{n: wf.step(n).status for n in wf.steps}              # now: p completed, sick and f stale

wf["x"] = os_remove[mod.map()](wf["p"])               # update: not in the catalog → a problem, never runs
wf["late"] = to_f[mod.map()](wf["later"])             # now: refused, a step reads only earlier steps
wf["w"] = to_f[mod.map()](wf["p"], temp_c=wf["p"][grid.cols["temp_c"]])   # update: paired per row (K19)
wf["s"] = wf["srt"][0]                                # update: the same row after a re-sort (row id)

text = wf.to_json()                                   # now
grid.Workflow.from_json(text, catalog=cat)            # update: today it takes a tools dict
```

When every line passes, the app's [`example_check.py`](../../src/SIMPLE_STEPS/examples/README.md)
twins and this session are the same contract: what the UI does, the terminal
does.
