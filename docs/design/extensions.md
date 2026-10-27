# Extensions, and running the app's workflows in Python

> Proposed 2026-10-26. The app adds its own information to core's objects:
> notes on a step, a step's colour in the UI, a custom input widget for a
> tool's argument, which tools the agent may use. This document says where
> that information goes and what guarantees hold around it.

## 1. The guarantee

> **A workflow saved by the app loads and runs in a plain Python session with
> only core installed, and gives the same results, provided the catalog's
> tools and the resources are the same.** The app's extensions are kept but
> ignored.

```python
from simple_steps_core import Kernel
from my_lab_tools import catalog              # the same tools the app was given

k = Kernel.from_json(open("fever.workflow.json").read(), catalog)
k.run_all()                                   # the same outputs the app showed
k.step("f").extras["simple_steps.ui"]         # the app's additions, untouched
```

"The same" is checked, not assumed:

| What must match | How core checks it | If it doesn't |
|---|---|---|
| each tool a step names | the catalog has a tool of that name, and its hash equals the one saved | a missing tool: a problem (`not_in_catalog`). A changed tool: the step is `stale`, with the reason `tool changed` |
| each resource type | the catalog has the type | a problem on the resource and the steps that use it |
| each resource's settings | saved in its `ResourceSpec`, except secret ones | a secret must be supplied (`k.resources.attach`, or an environment setting the type reads) before the resource loads |
| the data a source or resource reads | the source step's data version; a resource's reported data version (K25) | the step is `stale` after its next run shows different data |

**Loading is safe.** Loading a spec imports nothing and runs nothing. Every
name in the file is looked up in the catalog the caller passes; a file can't
bring code. A step runs only when asked to.

## 2. The rule for extensions

> **If removing it could change an output, it isn't an extension.**

An extension is information *about* a workflow for a particular front end. It
never affects what is computed. Anything that does affect it is part of the
spec, in core's terms, so a Python session reproduces it.

So, for each kind of thing the app might add:

| The app adds | Where | Why there |
|---|---|---|
| notes on a step, a step's colour, layout, a section title | `step.extras["simple_steps.ui"]` | display only |
| a custom input for an argument (a date picker, a colour picker, a map) | the tool's entry: `@tool(extras={"simple_steps.ui": {"when": "date-picker"}})`, or `Annotated` on the parameter | how a value is *entered*. What the widget produces is saved as the step's literal argument, so Python reproduces it from the argument alone |
| a tool's own interactive UI (a panel to draw a region, pick frames) | the tool's entry extras name the component | same: whatever the user chooses becomes literal arguments, or a file in the workspace read by a resource or tool. Never hidden state in extras |
| which tools the agent may use | the catalog entry: `extras["simple_steps.agent"]` | the agent is the app's |
| a workflow's title, description, owner | `workflow.extras["simple_steps.meta"]` | display and hosting |
| how a column or cell is shown (PNG, Plotly, a format) | the app's cell views, by type | display only |

Not extensions, because they change outputs or which code runs. These are
core features, or code given through the catalog:

| Wanted | Belongs in |
|---|---|
| progress and cancelling | core: an observing modifier (K23) |
| re-using results when nothing changed, tool versions | core: hashes and `ran_with` (K20, C15) |
| grouping steps that run as one | core: a stage ([object-model.md §4.11](object-model.md#411-stage)). How a stage is drawn (collapsed, coloured) is an extension on the stage's extras |
| a new kind of resource (a database, a model) | developer code: a `@resource` type in the catalog |
| a new tool | developer code: a `@tool` in the catalog |
| a new execution modifier (a rate limit, a cache) | later: developer code in the catalog, under the rules in §5 |
| where outputs are stored (parquet beside the workflow) | core: a pluggable output store (C32), chosen by the host |

## 3. Extras, precisely

- Every spec has `extras`: a mapping from **namespace** to a JSON value.
  Namespaces are dotted strings owned by whoever writes them:
  `simple_steps.ui`, `simple_steps.agent`, `simple_steps.meta`. Core owns none.
- Specs that carry extras: tool, catalog entry, resource, step, stage,
  workflow, kernel.
- **Core never reads extras.** It stores them, saves them and loads them.
- **Extras are never hashed.** Two kernels that differ only in extras have the
  same `k.id`. (`spec ==` still compares them; `spec.same_recipe(other)`
  ignores them.)
- **Unknown namespaces survive** a load and save in any environment (R5).
- **Extras hold values, never code:** the same literal types as arguments.
  Core refuses anything else, so an extra can't smuggle a callable into a file.
- Editing extras doesn't make a step stale.

## 4. What the app's save file is

```
kernel spec  (core):  catalog spec + workflow spec, each with extras
outputs      (core's output store, optional):  outputs by data version
app's own    (not core's):  sessions, chat history, user, hosting
```

The first part is all a Python session needs. The second lets it open with
outputs already shown, without re-running; without it, steps are `staged` until
run. The third never goes in a core file.

## 5. Developer-defined modifiers: later, under these rules

Decided 2026-10-26: not built yet, but planned. When they are, a developer
defines a modifier the way they define a tool, and these rules hold. They are
written down now so the built-in modifiers are built to the same rules.

1. **Through the catalog only.** A modifier is code, so it enters the way
   tools do: defined in the developer's package, passed to a `Catalog`. A file
   can name it, never bring it.
2. **Not a shape.** The shape verbs are core's, because staging, row ids and
   lineage must understand every one. A developer modifier is execution, error
   handling, expectation or observation, and says which.
3. **It wraps one call.** It receives the call (`fn`) and returns a call with
   the same signature. It never sees the grid, other rows or other steps.
4. **Settings are typed literals,** declared like a tool's parameters, checked
   when the step is declared.
5. **Failures are reported the standard way:** it raises, or returns a handled
   value, and the row's note records `where` as the modifier's name.
6. **The return type is kept,** except for error handling, which declares the
   type its fallback adds (the `try_except` rule, grid-model.md §5.1).
7. **Hashed like a tool:** its name, source and settings are part of the
   step's hash; a changed modifier makes its steps stale. Observation
   modifiers are not hashed, and must not change the value they observe.
8. **No module-level state.** Anything it keeps between calls (a rate limit's
   clock) lives on the kernel, so two kernels can't share it.

## 6. Open

- **Annotated parameters.** K27 allows `Annotated[...]` on parameters for
  extras. Core must check that its type checks look through `Annotated`
  (to verify by running).
