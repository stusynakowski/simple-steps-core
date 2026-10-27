# Working with a kernel in a Python session

> Proposed 2026-10-26. This is the acceptance session: when every line does
> what its comment says, core meets goal 4 ("run simple-steps-core through a
> kernel"). Each line is marked with the phase that makes it pass (see
> [cleanup-plan.md §4](cleanup-plan.md#4-order-of-work)). It becomes
> `runme.py` at the repo root and the first test in the new suite.

The same session works in `python`, IPython and Jupyter. In Jupyter, `k` and
`k.step(...)` show as HTML tables.

```python
import pandas as pd
from simple_steps_core import Catalog, Kernel, tool, mod, wf, cols

# ── tools: plain functions, described ──────────────────────────────────────
@tool
def patients() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "temp_c": [36.6, 38.2, 37.1]})

@tool
def to_f(temp_c: float) -> float:
    return round(temp_c * 9 / 5 + 32, 2)

@tool
def feverish(temp_c: float, limit: float = 38) -> bool:
    return temp_c >= limit

# ── a kernel: one catalog, one workflow ────────────────────────────────────
cat = Catalog(tools=[patients, to_f, feverish])        # phase 3
k = Kernel(cat)                                         # phase 3

k["p"]    = patients[mod.source()]()                    # phase 3 (wf["p"] = … today)
k["sick"] = feverish[mod.filter()](wf["p"])
k["f"]    = to_f[mod.map()](wf["sick"])

k.validate()               # {} : nothing wrong                     phase 3
k.run_all()
k                          # index | step | formula | state | shape | problem   phase 3
k.step("f").data           # Ben's row, still row id 1               phase 3 (.output.data today)
k.step(2).operation.to_source()   # 'to_f[mod.map()](wf["sick"])'    phase 3 (by index)
k.cell("f", 1, "value")    # the value, its type, and the input cell it came from

# ── editing makes downstream stale, never recomputes on its own ────────────
k["sick"] = feverish[mod.filter()](wf["p"], limit=37)
{s.name: s.state for s in k.workflow.steps}
# {'p': 'completed', 'sick': 'stale', 'f': 'stale'}       phase 3 (.status today)

# ── what core refuses, as problems on the step ─────────────────────────────
import os
k["x"] = tool(os.remove)[mod.map()](wf["p"])
k.step("x").problems[0].code        # 'not_in_catalog'; it never runs     phase 3
k["late"] = to_f[mod.map()](wf["later"])
k.step("late").problems[0].code     # 'missing_step': there is no 'later' phase 3
k.check("y", to_f[mod.map()](wf["p"]))   # () : would be fine; not added  phase 3

# ── references that follow the data ────────────────────────────────────────
k["w"] = to_f[mod.map()](wf["p"], temp_c=wf["p"][cols["temp_c"]])
# paired row by row, by row id                                          phase 4 (K19)
k["srt"] = mod.sort(by="temp_c")(wf["p"])
k["first"] = wf["srt"][0]
# the row with row id 0 (Ada), wherever the sort put it                phase 4 (K19)

# ── stages: manage a run of steps as one ───────────────────────────────────
k.stage("triage", ["p", "sick", "f"])                                # phase 4 (R9)
k.run("triage")                     # its steps, in order
k.stages["triage"].state            # 'completed'

# ── save and load: the spec, against a catalog ─────────────────────────────
text = k.to_json()                  # the spec; no output data
k2 = Kernel.from_json(text, cat)    # phase 3 (Workflow.from_json(text, tools=…) today)
k2.spec == k.spec                   # True                                phase 3
```

## What a session shows

`repr(k)` (phase 3):

```
Kernel: 5 steps, 3 tools (+ built-ins), 0 resources
 #  step   formula                                        state      shape  problem
 0  p      patients[mod.source()]()                       completed  3×2
 1  sick   feverish[mod.filter()](wf["p"], limit=37)      stale      1×2
 2  f      to_f[mod.map()](wf["sick"])                    stale      1×1
 3  x      remove[mod.map()](wf["p"])                     invalid    —      'remove' is not in this kernel's catalog
 4  late   to_f[mod.map()](wf["later"])                   invalid    —      input 'later' comes after 'late'; …
```

`repr(k.step("f"))` shows the step's formula, state, why it is stale, and the
first rows of `output.view()`. `repr(cat)` lists its entries by kind.

## Examples

Every example is a script that runs a kernel session like this one, and a test
that runs the script:

| Example | Shows |
|---|---|
| `runme.py` | this session |
| `examples/all_orchestrations/` | every shape verb, combine and execution modifier, failure, staging, save and load (rewritten on the kernel) |
| `examples/resources/` | a resource type with settings, a bound tool, a secret setting |
| `examples/notebook.ipynb` | the same session in Jupyter, with the HTML views |
