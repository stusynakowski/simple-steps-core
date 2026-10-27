# Working with a kernel

> Updated 2026-10-26, at phase 3e. How a workflow is built, changed, seen,
> saved, loaded and run, in a Python terminal, IPython or a notebook. The app
> does the same things through its UI ([interactive-sessions.md §8](interactive-sessions.md#8-the-same-session-in-the-app)).
>
> Everything marked **built** runs today. The walkthrough is
> [`examples/kernel_session.py`](../../examples/kernel_session.py), and
> `tests/integration/test_kernel_session_example.py` checks it, so the outputs
> below are real. **Planned** marks what this migration still adds, with where it
> is tracked ([features.md](features.md)).

## 1. Import core, and say what a workflow may use

```python
from simple_steps_core import Catalog, Kernel, tool, resource, bound_tool, mod, wf, res, cols, zip_

@tool
def patients() -> pd.DataFrame: ...                  # a source: no input

@tool(extras={"simple_steps.ui": {"temp_c": "slider"}})
def to_f(temp_c: float) -> float: ...                # the app's additions ride along

@tool
def feverish(temp_c: float, limit: float = 38) -> bool: ...

@resource
class Ward:
    def __init__(self, name: str = "A"): ...         # settings are literals
    @bound_tool
    def bed(self, name: str) -> str: ...             # a tool that lives on an instance

CATALOG = Catalog(tools=[patients, to_f, feverish], resources=[Ward])
```

| | | |
|---|---|---|
| `@tool`, `@resource` | describe a function or a class. **They register nothing**: a tool is used by putting it in a catalog | built |
| `Catalog(tools=…, resources=…)` | what a kernel may use. The built-in tools, modifiers and combines are in by default | built |
| `Catalog.from_modules(lab_tools)` | every tool and resource type in a module: how an app's tool package becomes a catalog | built |
| `cat.without("count", "retry")` | a smaller copy. Any entry can be removed | built |
| `Catalog(…, strict=True)`, `@tool(strict=True)` | every parameter and return must be annotated | built |
| `cat.describe()` | every entry as plain data, for a palette, a form or an agent | built |

## 2. Construct a workflow

A kernel is one workflow with its catalog. Each line declares a step, and is
checked and planned at once; nothing runs.

```python
k = Kernel(CATALOG)
k["p"]     = patients[mod.source()]()                         # a source tool
k["limit"] = 38.0                                             # a value: a control
k["sick"]  = feverish[mod.filter()](wf["p"], limit=wf["limit"])
k["f"]     = to_f[mod.map()](wf["sick"])                      # one value per row
k["side"]  = zip_(wf["sick"], wf["f"])                        # results beside inputs
k.define("ward", Ward, name="B")
k["beds"]  = res["ward"].bed[mod.map()](wf["sick"])           # a resource's tool
```

```
>>> k
Kernel: 6 steps, 3 tools (+ built-ins), 1 resource
#  step   formula                                             state      shape  problem
0  p      patients[mod.source()]()                            staged     —
1  limit  38.0                                                completed  1×1
2  sick   feverish[mod.filter()](wf["p"], limit=wf["limit"])  staged     —
3  f      to_f[mod.map()](wf["sick"])                         staged     —
4  side   zip_(wf["sick"], wf["f"])                           staged     —
5  beds   res["ward"].bed[mod.map()](wf["sick"])              staged     —
```

The kinds of step ([step-expressions.md](step-expressions.md) has the grammar):

| Step | Example | |
|---|---|---|
| a source tool | `patients[mod.source()]()` | built |
| a value (a literal), saved with the workflow | `k["limit"] = 38.0`, `[3, 1, 2]`, `{"k": 1}` | built |
| a table assigned in Python (data, not saved) | `k["t"] = df` | built |
| a tool over rows | `to_f[mod.map()](wf["p"])`; `filter`, `expand`, `group`, `collapse`, `widen`, `sweep`, `table` | built |
| the verb inferred from the tool's types | `to_f(wf["p"])`, saved as `auto` | built |
| a reshape, no tool | `mod.sort(by="temp_c")(wf["p"])`, `select`, `drop`, `rename`, `slice`, `distinct` | built |
| part of a step | `wf["p"][0:2]`, `wf["p"][rows[[0, 2]]]`, `wf["p"][cols["temp_c"]]`, `wf["p"][cols[["name", "ward"]]]`, `wf["p"][1][cols["temp_c"]]`, `wf["p"].header` | built, as steps and as arguments, and they reload the same (checked 2026-10-27). Rows by position; by row id is K19. `header[k]` is C28 |
| a combine, reading several steps | `zip_`, `join`, `stack` | built |
| a resource's tool, or a resource as an argument | `res["ward"].bed[...]`, `tool(..., ward=res["ward"])` | built |
| a value step as an argument: a control | `limit=wf["limit"]` | built |
| execution modifiers | `to_f[mod.map(), mod.retry(times=2), mod.try_except(default=None)]` | built (`timeout` isn't enforced yet, K18) |
| naming outputs | `mod.name("temp_f")`, `mod.name(pattern="{step}_{field}")` | planned ([outputs-and-reshaping.md §4](outputs-and-reshaping.md#4-naming-outputs-modname)) |
| a record return, spread into columns | `-> LoHi` gives `lo`, `hi` | planned (G8) |
| an empty step, a placeholder line | `k["x"] = None` gives a 1×1 `"empty"` | planned (G17: today it is the value `None`) |
| a stage: steps run and shown as one | `k.stage("triage", ["p", "sick", "f"])` | planned (R9) |

Editing the order: `k.insert(1, "c", op)`, `k.move("c", -1)`, `k.rename("f", "temp_f")`,
`del k["c"]`. Each is refused when it would make a valid step read a later one.
**Built.**

**What is refused, and how you hear about it.** A declaration never raises for
a problem in the workflow: the step is stored, marked `invalid`, and carries
its problems, each with a code (`not_in_catalog`, `missing_step`,
`later_step`, `missing_column`, `wrong_shape`, …; 33 in `problems.CODES`).
Only misuse of Python itself raises: passing a selection or an operation as a
step's input, giving the input twice, a value that isn't a step reference.
**Built.**

## 3. See the data

| | Shows | |
|---|---|---|
| `k` | the table above; in a notebook, an HTML table | built |
| `k.step("f")`, `k.step(3)` | the live step | built; its `repr` is one line today. Later: the workflow printed as a table of step blocks, and a step's rows labelled with their references (G18, [features.md](features.md#seeing-a-workflow-as-a-table-later)) |
| `k.step("f").data` | its values, a DataFrame on its row ids | built |
| `k.step("f").output.view()` | the grid as a user sees it: row number `#`, values, each row's state and note | built |
| `k.view("p", rows=(0, 50))` | a page of rows, with each cell's state and type, and how many rows there are in all | built |
| `k.cell("f", 0)` | one cell: value, type, state, and the input cells it came from, with their values | built |
| `k.step("f").output.plan` | before running: rows, columns, types, each `exact`, `bounded` or `unknown` and why | built |
| `k.step("f").problems`, `.warnings` | `Problem`s: message, code, step | built |
| sizes per output, unknown with the reason | row count and estimated bytes | planned (K26) |

After `k.run_all()`:

```
>>> k.step("side").data
  name  temp_c   value
1  Ben    38.2  100.76
>>> k.cell("f", 0)["inputs"][0]["values"]
{'temp_c': 38.2}
```

Row `1` is Ben's row id: it follows him through the filter and the zip.

## 4. Change it, and see what changed

Status reacts at once; computing waits until you ask
([interactive-sessions.md](interactive-sessions.md)).

```python
k["limit"] = 37.0                       # move the control
k.needs_run()
# {'sick': 'stale: limit changed', 'f': 'stale: sick is stale',
#  'side': 'stale: sick is stale', 'beds': 'stale: sick is stale'}

k.run("f")                              # sick is stale: it passes through as shown
k.needs_run()
# {'sick': 'stale: limit changed', 'f': "read stale 'sick'", ...}

k.run_all()                             # everything up to date
k.step("sick").data["name"].tolist()    # ['Ben', 'Cy']
```

| | | |
|---|---|---|
| editing a step | it, and the steps that read it, are `stale`, each with its reason; their outputs are kept and shown | built |
| editing one row of a source | only the rows that read it are stale (`k.workflow.stale_rows("f")` → `[1]`) | built |
| `k.run(step)` | runs on what its inputs show: inputs that never ran run first, stale ones pass through, and the result says it read them stale | built |
| `k.needs_run()` | every step not up to date, in run order, with why | built |
| `k.on_change(callback)` | after any edit or run, the host hears which steps changed and which were removed | built |
| `k.check(name, op)` | the problems a proposal would have, without adding it | built |
| a step that re-runs on its own when its input changes | an autorun modifier | planned, to be designed ([interactive-sessions.md §6.2](interactive-sessions.md#62-an-autorun-modifier-planned-to-be-designed)) |
| progress while a step runs; cancel | observing modifiers | planned (K23) |
| an edited tool, in a live kernel | a kernel's catalog is fixed: make a new catalog and kernel, keeping the steps (`Kernel.from_json(k.to_json(), new_cat)`) | built; swapping a kernel's catalog is a possible later feature |
| what a stale step showed before its input re-ran | outputs kept by data version while something reads them | planned (K22) |

## 5. Save, import and run kernels

```python
text = k.to_json()                      # the spec: steps, values, resources, extras; never output data
k2 = Kernel.from_json(text, CATALOG)    # checked against the catalog you pass
k2.spec == k.spec                       # True
k2.run_all()                            # the same data again
```

| | | |
|---|---|---|
| `k.spec`, `step.spec`, `k.workflow.spec`, `k.catalog.spec` | frozen plain values; never output data | built |
| `k.to_json()`, `Kernel.from_json(text, catalog)`, `Kernel.from_spec(spec, catalog)` | save and load; a reloaded kernel has an equal spec | built |
| loading against a different catalog | anything not in it is a problem on its step, and never runs | built |
| `extras` on steps, resources, the workflow | the app's notes, colours, widgets; kept, never read, never hashed | built |
| an app's saved workflow, in plain Python | `Kernel.from_json(app_file, Catalog.from_modules(app_tools))` runs the same steps; extras are kept and ignored ([extensions.md §1](extensions.md#1-the-guarantee)) | built |
| resources | built from their spec the first time a step needs them; `k.resources.attach(name, obj)` hands over one the host built | built |
| secret settings, left out of saves and hashes | `Secret[str]` | planned (R3) |
| saving outputs with the spec, so a reloaded kernel opens with its data | a pluggable output store | planned (C32) |
| `k.id`, `k.run_id`, `k.diff(other)`; a changed tool marks its steps stale | hashes of specs and tool source | planned (K20) |
| two kernels in one process | share nothing: own catalog, workflow, resources | built |

## 6. One kernel per session

A Python session works on one kernel; the app hosts many in one process, each
isolated. Hosting (which kernel belongs to which user, locks, saving to disk)
is the app's.
