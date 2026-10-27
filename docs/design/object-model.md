# The object model

> Proposed 2026-10-26. *Today* notes say what exists at `86170a3` (checked by
> running), so the distance to the design is visible. Where this document and
> the code disagree, this document is the intent.
>
> **Build status:** `Catalog` and `Kernel` exist (phase 3a, 3b). Some *Today*
> notes are now out of date, and some of this design isn't built yet (for
> example, `@tool` still registers globally until 3e). What's built is tracked
> in [cleanup-plan.md, phase 3](cleanup-plan.md#phase-3-piece-by-piece).

## 1. The words

One word per idea, used the same way in code, API and docs. The right column
lists words that are retired: they are renamed in code and not used in new
docs.

| Word | Means | Retired |
|---|---|---|
| **kernel** | one live workflow together with what it runs with: its catalog, its loaded resources and its outputs. What you hold in a Python session. The app hosts many; a terminal session works on one | *engine*, *session* (in core), *app* (in core) |
| **catalog** | what a kernel may use: tools, resource types, modifiers, combines. Fixed when the kernel is made | *registry*, *pack*, *tool group* |
| **tool** | one Python function in the catalog, described: name, typed parameters, return type, docstring | *operation* (for a plain tool), *ToolHandle*, *ToolDefinition*, *ToolCall* |
| **resource type** | a class whose instances tools use (a database client, a model, a folder). Its settings are literals | *ResourceSpec* (the old tool namespace) |
| **resource** | one named instance of a resource type in a workflow: its spec, plus the loaded object | — |
| **modifier** | a decorator on a tool, stored as data in the step and applied each time it runs. It decides how the tool meets the grid (**shape**: `map`, `filter`, … and the tool-less **reshapes** `select`, `sort`, …), how each call runs (**execution**: `retry`, `timeout`, `breaker`), what a failure becomes (**error handling**: `try_except`), what staging promises (**expectation**: `expect`), what the output columns are called (**naming**: `mod.name`) when it runs (**scheduling**, planned: an autorun modifier) and, planned, what is reported while it runs (**observation**: progress) | *orchestration*, *orchestrator*, *mode* |
| **combine** | an operation that reads several steps: `join`, `stack`, `zip_` | — |
| **reference** | points at earlier data: a step (`wf["p"]`), part of a step (rows, columns, a cell) or a resource (`res["db"]`) | `step1.col`, *link* |
| **operation** | what a step does, and nothing run: tool, modifiers, inputs and arguments | *compiled step* |
| **step** | one named entry in a workflow: an operation, and once declared, its output | *node*, *task* |
| **output** | what a step produced: a DataFrame, a state per cell, notes per row | *result*, *ledger* |
| **workflow** | the ordered steps of a kernel, the stages that group them, and the resources they use | *pipeline* |
| **stage** | a named group of consecutive steps, managed and run as one. Defined on top of steps; changes no step | *section*, *block* |
| **formula** | a step's operation written as text, as in the formula bar. Text belongs to the app; core prints it (`to_source()`) but does not parse it | *expression* (same thing; one word now) |
| **spec** | the saved form of any object: everything needed to produce the same output, assuming what it references holds the same data. Never holds output data | *declaration*, *saved step*, `ResourceDecl` |
| **status** | what is live about an object: a step's output, state and problems; a resource's loaded instance. A live object is its spec plus its status | — |
| **state** | one value from a fixed list. A **step state** is one of `staged`, `completed`, `stale`, `failed`, `invalid`. A **cell state** is one of `known`, `maybe`, `pending`, `blocked`, `failed`, `invalid` | step *status* (the field is renamed `state`) |
| **problem** | a structured reason a step can't run or ran badly: code, message, step, and the row or argument when there is one. A **warning** is a problem that doesn't block | plain-string problems |
| **row id** | the stable label of a row: the output DataFrame's index. Kept by verbs that keep rows, so it follows a row through a sort | — |
| **row number** | `#`, a row's position 0…n-1 as displayed. Never stored, never used to pair rows | — |
| **value column** | the column a tool's result is written to: `value` unless named with `mod.name`. A declared record writes one column per field | *payload* |
| **extras** | an open mapping on every spec, keyed by namespace (`"simple_steps.ui"`), that core saves and loads but never reads or hashes. The app's extensions (step notes, colours, tool widgets, agent permissions) live here. Removing them never changes an output ([extensions.md](extensions.md)) | — |

Two pairs that are easy to mix up:

- **Spec and status.** `step.spec` is the recipe; `step.status` is what running
  it produced. The same pair exists on every object (§3).
- **Step state and cell state.** A step's state rolls up its cells' states: a
  step with one failed cell is `failed`; a step whose input changed after it ran
  is `stale`, while its cells keep their own states.

## 2. The objects at a glance

```
                       ┌──────────────────────── Kernel ────────────────────────┐
  developer code       │                                                        │
  ─────────────        │   Catalog ──────── allows ────────┐                    │
  @tool  def f ──► Tool ──►  tools, resource types,        │                    │
  @resource class ───────►   modifiers, combines           │ checked against    │
                       │                                   ▼                    │
                       │   Workflow                                             │
                       │     resources: name → ResourceSpec ──► Resource        │
                       │     steps (ordered, by name or index):     (live,      │
                       │       Step                                  loaded)    │
                       │         spec:   name, Operation                        │
                       │                   tool name, modifiers,                │
                       │                   inputs (References), arguments       │
                       │         status: Output (data, states, notes),          │
                       │                 state, problems, warnings, ran_with    │
                       │                                                        │
                       │   outputs store (by data version)                      │
                       └────────────────────────────────────────────────────────┘
```

A **tool** is defined once, in developer code. A **catalog** chooses tools and
other entries. A **kernel** is made from a catalog. Steps are declared on the
kernel's workflow, checked against the catalog when declared, and run by the
kernel.

## 3. Spec and status, for every object

Every object has a `spec` attribute holding a plain frozen value. Saving writes
specs; loading builds objects from a spec and a catalog.

| Object | `spec` (the recipe) | `status` (live) |
|---|---|---|
| Tool | name, hash of its source, parameters, return type, tags, extras | the function |
| Catalog | the entry names it allows, each with its hash and extras | the tools and types themselves |
| Resource | `ResourceSpec`: name, type name, settings (secret ones marked), extras | the loaded instance, such as an open connection |
| Operation | tool name, modifiers, inputs, arguments | none: an operation is all spec |
| Step | `StepSpec`: name, operation, extras | output, state, problems, warnings, `ran_with` |
| Stage | `StageSpec`: name, the names of its steps, extras | its state, rolled up from its steps |
| Workflow | `WorkflowSpec`: step specs in order, stage specs, resource specs, extras | its live steps |
| Kernel | `KernelSpec`: the workflow spec plus the catalog spec | the live workflow, loaded resources, stored outputs |

Rules:

- **A spec never holds output data.** A file that also carries outputs is a
  spec plus an output snapshot, written through the output store (§4.10), not a
  spec.
- **A spec names code, it doesn't contain it.** The catalog spec records each
  tool's hash, so a kernel loaded with a changed tool knows which steps that
  tool affects.
- **Position is not saved separately.** It is the order of steps in the
  workflow spec.
- `to_json()` is the spec as JSON; `from_json(text, catalog)` builds it back.
  Saved files carry a format version. Files from before this redesign are not
  loaded (decided 2026-10-26).

## 4. Each object

### 4.1 Tool

One Python function, described. `@tool` builds it, and **registers it nowhere**:
it returns the `Tool`, and the developer passes tools to a catalog.

| Field | |
|---|---|
| `name` | the function's name unless given: `@tool(name="to_f")` |
| `fn` | the plain function. Calling the tool with plain values calls it |
| `parameters` | name, type, default, description (from `Args:`), choices (from `Literal`) |
| `returns` | the declared return type, or `unknown` |
| `description` | the docstring's first paragraph |
| `tags` | free labels (`"source"`, `"io"`) |
| `extras` | namespaced, for the app (`{"simple_steps.ui": {"date": "date-picker"}}`) |
| `hash` | `sha256(name, source, library + version)`, computed once when the catalog is built |

The calling rule (exists today): **brackets decorate, parens apply.**
`to_f(36.6)` runs the function. `to_f[mod.map()]` is an operation waiting for
an input. `to_f[mod.map()](wf["p"])` is an operation reading step `p`.

A tool's parameters are named and typed. `*args` is refused; `**kwargs` gets a
warning (exists today).

*Today:* `ToolHandle`; `@tool` also writes into the process-wide `grid.TOOLS`
and `grid.TOOL_TAGS`.

### 4.2 Resource type and resource

A **resource type** is a class decorated `@resource`. Its settings are its
`__init__` parameters, each typed as a literal. A setting can be marked secret
(`Secret[str]`): left out of hashes and of anything displayed. Its methods
decorated `@tool` are tools bound to an instance, used in a formula as
`res["db"].lookup`. A type may define `data_version()`, which feeds the
staleness of steps that use it (K25).

A **resource** is one named instance in a workflow:

```python
k.define("db", ClinicalDB, url="sqlite:///clinic.db")   # writes a ResourceSpec
k.resources["db"]                                        # the live instance, loaded on first use
```

`ResourceSpec` is `name`, `type` (the type's name), `settings` (literals),
`extras`. The kernel loads the instance from the spec through the catalog's
resource type. The app can hand over an instance it already loaded
(`k.resources.attach("db", obj)`), for example one with locked settings.

*Today:* `wf.define(...)` writes `ResourceDecl`; the live instances are passed
into every `run(…, resources=…)` call; `grid.RESOURCE_TYPES` is process-wide.
The old engine's `ResourceSpec` (a namespace of tools) is removed, and the name
is reused here.

### 4.3 Catalog

What a kernel may use. Immutable: changing it makes a new catalog.

```python
cat = Catalog(tools=[patients, to_f, feverish], resources=[ClinicalDB])
cat = Catalog.from_modules(my_tools)          # every Tool and @resource class in the module
cat = cat.without("count", "retry")           # remove built-ins or modifiers
```

| Holds | Default |
|---|---|
| developer tools and resource types | what was passed |
| built-in tools: `identity`, `count`, `total`, `gather`, `first`, `last` | all, removable |
| modifiers: shape verbs, reshapes, execution modifiers | all, removable |
| combines: `join`, `stack`, `zip_` | all, removable |
| literal types: `None`, `bool`, `int`, `float`, `str`, `list`, `tuple`, `dict`, `set` | fixed by core, not removable |

- **A step can use only what is in its kernel's catalog.** Anything else is a
  problem on the step (`not_in_catalog`), and the step never runs.
- `cat.describe()` gives every entry as plain data (name, kind, parameters,
  types, description, extras): what the app needs for its palette, forms and
  agent. It replaces today's `grid.catalog()`, `tool_entry()`,
  `modifier_catalog()`, `resource_catalog()`, `builtin_tools()`,
  `shape_verbs()`.
- Per-entry rules such as "the agent may not use this" are the app's, kept in
  the entry's `extras` (`"simple_steps.agent"`). Core doesn't read them.
- There is no `freeze()`: a catalog can't change, so there is nothing to freeze.

*Today:* no catalog object. `grid.catalog(tools)` only describes tools, and
`Workflow()` takes no catalog; `run(tools=…)` and `from_json(tools=…)` take a
dict.

### 4.4 Modifier

A decorator on a tool, kept as data: a `kind` and its `settings` (literals).
It is stored in the step and **applied each time the step runs**, so the same
tool is bare in one step and decorated in another, and changing a step's
modifiers changes how it runs next time without touching the tool.

```python
to_f[mod.map(), mod.name("temp_f"), mod.retry(times=2), mod.timeout(seconds=5)]
#    shape                  execution: wraps each call
```

Read left to right as decorator layers, outermost first: the list is
`@mod.map()`, `@mod.name("temp_f")`, `@mod.retry(times=2)`,
`@mod.timeout(seconds=5)` stacked on `to_f`, so `map` calls
`name(retry(timeout(to_f)))` once per row: each attempt is timed, retried, and
its result labelled `temp_f`
([grid-model.md §6](grid-model.md#6-modifiers-are-decorators-applied-at-run-time)).

| Class | Decides | Modifiers | Hashed |
|---|---|---|---|
| shape | rows and columns | `source`, `map`, `filter`, `expand`, `collapse`, `group`, `widen`, `table`, `sweep`, `auto`; tool-less reshapes `select`, `drop`, `rename`, `sort`, `slice`, `distinct` | yes |
| execution | how each call runs | `retry`, `timeout`, `breaker` | yes |
| error handling | what a failure becomes | `try_except` | yes |
| expectation | what staging promises and checks | `expect` | yes |
| naming | what the output columns are called | `mod.name` | yes |
| scheduling (planned) | when the step runs | an autorun modifier, to be designed: re-run on a change it is told about | no |
| observation (planned, K23) | nothing: reports cell states to a callback | progress | no; a host may attach it at run time |

- At most one shape verb per step, written first.
- No verb written: inferred from the tool's types, saved as `auto`.
- The input is always the call's argument, never a setting. `over=` is
  retired.
- What each verb does to rows, columns and row ids is in
  [grid-model.md](grid-model.md); what may be written is in
  [step-expressions.md](step-expressions.md).

*Today:* `Modifier(kind, params)`; classes are only `shape` and `execution`
(`expect`, `try_except` and `breaker` are filed as execution); `over=` is
accepted and moved to the input; `timeout` isn't enforced (K18).

### 4.5 Reference

Points at earlier data. Built with the proxies `wf`, `res`, `rows`, `cols`,
which hold no state and resolve inside the workflow they're assigned into.

| Form | Means |
|---|---|
| `wf["p"]` or `wf[0]` | step `p`, or the first step, by name or by index |
| `wf["p"][0:2]`, `wf["p"][rows[3, 5]]` | rows of `p`, **by row id** |
| `wf["p"][cols["n"]]`, `wf["p"][cols["a":"c"]]` | columns of `p` |
| `wf["p"][0][cols["w"]]` | one cell |
| `res["db"]`, `res["db"].lookup` | a resource, or a tool bound to it |

- A reference written by index is saved by name, so inserting a step doesn't
  change what a saved reference points at.
- **A step reads only earlier steps.** A reference to a later or missing step
  is a problem, never a cycle.
- A selection can't be a tool's input: it is its own step, or an argument.
  This exists today.
- Selections by row id are K19 (phase 4). *Today* they select by position,
  so after a re-sort `wf["srt"][0]` picks a different row.

### 4.6 Operation

What a step does. All spec, nothing run.

| Field | |
|---|---|
| `tool` | the tool's name in the catalog (or a combine, or a resource's bound tool) |
| `modifiers` | in written order |
| `inputs` | references to the steps it reads: none for a source, one for a normal step, two or more only for a combine |
| `arguments` | name → a literal or a reference |

- `op.to_source()` prints the formula: `to_f[mod.map()](wf["sick"])`.
- `Operation.from_spec(dict)` builds one from plain data. This is the seam the
  app's parser uses: text → its own AST → `from_spec` → core checks it.
- Building an operation never raises for a wrong *workflow* fact. Declaring it
  on a kernel records problems (§4.7). It raises only for Python mistakes, such
  as passing something that isn't a reference as an input.

*Today:* `tool_id`, `input` plus `inputs` for combines, and `fn` carried along.

### 4.7 Step

One named entry in the workflow. Declaring a step stages it at once: it exists
with an output slot from the moment it is declared.

```python
k["f"] = to_f[mod.map()](wf["sick"])        # declare (or replace) step f
k.step("f")     k.step(2)                   # the live step, by name or index
```

| | |
|---|---|
| `name` | unique in the workflow. A rename makes later references follow (exists today) |
| `index` | its position, from the workflow's order |
| `operation` | §4.6 |
| `spec` | `StepSpec(name, operation, extras)` |
| `status` | `StepStatus(output, state, problems, warnings, ran_with)` |
| `state`, `output`, `problems`, `warnings`, `data` | shortcuts into `status`. `data` is `output.data` |

**Step states:** `staged` (declared, not run), `completed`, `stale` (its spec,
an input, a tool hash or a resource's data version changed after it ran; its
output is kept and shown), `failed` (some cells failed or were blocked),
`invalid` (has problems; never runs).

A step that ran on a stale input is `completed`, marked **read stale**, with the input and its reason; `k.needs_run()` lists it.

`ran_with` records what the output was computed from: the operation, the data
versions it read and the hashes of its tools. Staleness is decided from it.

*Today:* `step_id`; `step.status` is the step state; problems are strings.

### 4.8 Output

What a step produced. Always a DataFrame.

| Field | |
|---|---|
| `data` | the values, indexed by **row id** |
| `states` | one cell state per cell, same shape as `data` |
| `notes` | row id → what there is to say about it: the error, `where` it happened (tool, timeout, retry, breaker, expect, upstream), cause, attempts, whether caught ([grid-model.md §5.2](grid-model.md#52-where-an-error-happened)) |
| `version` | hash of the data. Equal data, equal version |
| `read` | `{step or resource: version}` it was computed from |
| `plan` | before running: rows, columns and types, each `exact`, `bounded` or `unknown` with the reason |
| `value_column` | the column the tool wrote, or none |

- `output.view()` is the grid as a user sees it: `#`, data, each row's state and
  note (exists today).
- An **empty step** is a step with no expression yet (`k["x"] = None`, or a
  blank line in the UI). Its output is a 1×1 frame holding `"empty"`, and its
  state is `staged`. A step that ran and kept no rows is different: a 0×n frame
  with its columns, `completed`.
- Today's open `meta` dict becomes these named fields. A new kind of
  information gets a named field when it's designed; the app's own information
  goes in the step's `extras`.

*Today:* `Output(data, states, meta)`, with `version`, `read`, `plan`,
`payload`, `stale` and others in `meta`.

### 4.9 Problem

```python
Problem(code="not_in_catalog", message="'os_remove' is not in this kernel's catalog",
        step="x", argument=None, row=None, severity="error")
```

`code` comes from a fixed list that core documents (`not_in_catalog`,
`later_step`, `missing_step`, `missing_column`, `wrong_type`,
`bad_modifier_setting`, `selection_as_input`, …). `message` keeps core's
current wording. `str(problem)` is the message. A warning is a `Problem` with
`severity="warning"`.

### 4.10 Workflow

The ordered steps and the resources they use. A workflow belongs to one
kernel: it is made by the kernel and checked against the kernel's catalog.

| | |
|---|---|
| `steps` | ordered; `wf[name]` or `wf[index]` |
| `stages` | name → `Stage` |
| `resources` | name → `ResourceSpec` |
| `spec` | `WorkflowSpec(steps, stages, resources, extras)` |

Editing: assign to declare or replace, `del k["x"]` to remove, `k.rename(old,
new)`, `k.insert(index, name, operation)` and `k.move(name, index)`. A move
that puts a step before something it reads is refused with a problem.

### 4.11 Stage

A named group of consecutive steps, for managing the execution of a long
workflow (R9): run, check and show several steps as one. It is defined on top
of the steps and changes none of them: each step keeps its own spec, output
and problems.

```python
k.stage("clean", ["p", "sick", "f"])        # or k.stage("clean", first="p", last="f")
k.run("clean")                              # its steps, in order
k.stages["clean"].state                     # worst of its steps' states
```

| | |
|---|---|
| `name` | unique among steps and stages |
| `steps` | consecutive step names, in order |
| `spec` | `StageSpec(name, steps, extras)` |
| `state` | rolled up: `invalid` if any step is, then `failed`, `stale`, `staged`, else `completed` |

Rules:

- Steps in a stage are consecutive. A step belongs to at most one stage.
  Stages don't nest (for now).
- Inserting a step between two steps of a stage puts it in the stage. Moving a
  step out of the middle of a stage is refused, with a problem; remove it from
  the stage first.
- A stage changes no output, so it isn't part of any hash.
- `repr(k)` shows a stage as one row that can be expanded to its steps.

**A stage is not a reference** (decided 2026-10-26). Steps read steps:
a later step may read any earlier step, inside a stage or not
(`wf["sick"]`), but `wf["clean"]` naming a stage is a problem. A stage has no
output of its own.

### 4.12 Kernel

One live workflow with what it runs with. The object you hold.

```python
k = Kernel(cat)                      # a catalog, an empty workflow
k = Kernel.from_json(text, cat)      # or a saved spec
```

| Holds | |
|---|---|
| `catalog` | fixed for the kernel's life |
| `workflow` | its steps and resource specs. `k[...]` is shorthand for `k.workflow[...]` |
| `resources` | the loaded instances |
| `store` | outputs by data version. Phase 3 keeps the latest; K22 keeps what a stale reader still shows |
| `options` | per kernel, never global: strict types, implicit `auto` |
| `extras` | the app's additions, by namespace; never read by core. *As built (3d):* the same mapping as the workflow's extras |

| Does | |
|---|---|
| `k["x"] = op`, `del k["x"]`, `rename`, `insert`, `move` | edit the workflow |
| `k.stage(name, steps)` | group consecutive steps; `k.run(stage)` runs them |
| `k.define(name, type, **settings)` | add a resource |
| `k.check(name, op)` | the problems this step *would* have, without adding it (what the app's agent proposals need) |
| `k.validate()` | `{step: problems}` for every step |
| `k.needs_run()` | the steps not up to date, in run order, with reasons |
| `k.on_change(callback)` | tells the host about every change of state, problems or plan |
| `k.run(name)`, `k.run_all()` | run on what the inputs show now: stale inputs pass through (the result is marked as having read them), never-run inputs run first. `observe=[…]` attaches observing modifiers (progress) for this run only, without editing any step |
| `k.cell(step, row, column)`, `k.view(step, rows=(a, b))` | read one cell with its inputs; read a page of rows |
| `k.spec`, `k.to_json()` | save |
| `repr(k)`, `k._repr_html_()` | a table: index, step, formula, state, shape, first problem |
| later: `k.id`, `k.run_id`, `k.diff(other)`, progress, `cancel()` | K20, K23 |

**One kernel per session.** In a terminal you work on one kernel. Core doesn't
enforce it, because the app holds many kernels in one process, and each is
fully isolated: nothing a kernel uses is shared through module state.

Hosting (keys, locks, last-used, eviction, snapshots on disk) is the app's.

*Today:* there is no kernel in core. `grid.Workflow` holds steps and resource
declarations; tools and resources are passed into each call. The app's
`kernels.py` builds a `Kernel` around a workflow.

## 5. What core does and doesn't hold at module level

Allowed: constants that never change (the cell states, the format version) and
the stateless authoring proxies `wf`, `res`, `mod`, `rows`, `cols`.

Removed from module level: `TOOLS`, `TOOL_TAGS`, `RESOURCE_TYPES`, `_VIEWS`,
`_FROZEN` / `freeze()`, `STRICT_TYPES`, `settings` (moved to kernel options).
The lookup tables (`MODIFIERS`, `PARAM_TYPES`, `ROWS_RULE`, `COMBINE`, …)
become private, read only through the catalog.

## 6. The boundary with the app's formula bar

The app owns text. Core owns meaning.

1. The app parses formula text with its own safe parser (no `eval`, only names
   in the catalog).
2. It builds an operation with `Operation.from_spec(...)` (or the same Python
   objects a terminal uses).
3. It declares it: `k[name] = op` or `k.check(name, op)`. Core returns problems
   in its own words, with codes the UI can act on.
4. It shows `op.to_source()`. The app's parser must read back everything
   `to_source()` prints; the app keeps a test for this.
