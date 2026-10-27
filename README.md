# simple-steps-core

> **Redesigned (branch `core-handover`, phases 1–3 done).** Core is the grid
> model alone, driven through a `Catalog` and a `Kernel`. The design and its
> status are in [docs/design/](docs/design/README.md); the working guide is
> [kernel-session.md](docs/design/kernel-session.md).

**The engine of Simple Steps: workflows of expensive, impure, failable Python
functions, as tidy tables.** You write plain functions; a workflow applies them
to grids, step by step, and keeps a state per cell, so a workflow of
transcription, LLM or model-inference steps can be built, checked, run and
re-run a row at a time, in a Python session or behind the app's UI.

It is a **backend library — it ships no UI** and depends on `pandas` alone.

## Install

```bash
python -m pip install simple-steps-core

# local dev
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## The model in one minute

```python
import pandas as pd
from simple_steps_core import Catalog, Kernel, tool, mod, wf

@tool
def readings() -> pd.DataFrame:
    return pd.DataFrame({"city": ["SF", "NYC", "LA"], "n": [1, 2, 3]})

@tool
def scale(n: int, weight: int = 1) -> int:
    return n * 10 * weight

k = Kernel(Catalog(tools=[readings, scale]))      # what this workflow may use
k["r"] = readings[mod.source()]()                 # a source step
k["scored"] = scale[mod.map()](wf["r"], weight=2) # one value per row
k.run_all()

k.step("scored").data["value"].tolist()           # [20, 40, 60]
k                                                 # a table of the steps
```

```
Kernel: 2 steps, 2 tools (+ built-ins), 0 resources
#  step    formula                              state      shape  problem
0  r       readings[mod.source()]()             completed  3×2
1  scored  scale[mod.map()](wf["r"], weight=2)  completed  3×1
```

Three ideas carry the whole model:

- **A tool call produces one cell.** How calls become rows and columns is the
  step's **shape verb** (`map`, `filter`, `expand`, `collapse`, `group`,
  `widen`, `sweep`, `table`, …), written in brackets or inferred from the
  tool's types: `scale(wf["r"])` is a `map`.
- **Every output is a tidy grid:** a DataFrame with row ids, typed columns
  and a state per cell (`known`, `failed`, `blocked`, …), so a failure stays
  pinned to its row.
- **Status reacts, computing waits.** Editing a step marks what it affects
  `stale`, with the reason; nothing runs until you ask (`k.needs_run()`).

## Examples

| Example | Shows | Run |
|---|---|---|
| [examples/kernel_session.py](examples/kernel_session.py) | a kernel session start to finish: a catalog, building a workflow, seeing and changing its data, saving, loading and running | `python examples/kernel_session.py` |
| [examples/all_orchestrations/](examples/all_orchestrations/) | every shape verb, both fan-out chains (`group`→`collapse`, `expand`→`widen`), execution modifiers, resources, saving, checking, failure handling and verb inference | `python examples/all_orchestrations/pipeline.py` |

Each has a test that runs it (`tests/integration/`).

## Documentation

| doc | what |
|---|---|
| [docs/design/](docs/design/README.md) | **the redesign**: the object model, the grid model, step expressions, outputs, extensions, interactive sessions, and the plan |
| [shape-algebra.md](docs/shape-algebra.md) | the concept: verbs, tidy intent, row/column conventions |
| [grid-model.md](docs/grid-model.md) | how `grid.py` was built, before it was split into modules |
| [step-expressions.md](docs/step-expressions.md) | the step grammar, as written before the redesign |

The three older docs use some retired words (ledger, `over=`, payload). They
are folded into `docs/design/` as the redesign lands.

## Develop

```bash
./scripts/run_checks.sh          # lint + tests
pytest -q                        # the suite
```

## Project structure

- `src/simple_steps_core` — the library: one module per object (`kernel`,
  `catalog`, `workflow`, `step`, `operation`, `modifiers`, `references`,
  `output`, `specs`, `problems`, …). The public API is what the package
  exports; see [cleanup-plan.md §3](docs/design/cleanup-plan.md#3-the-new-package-layout).
- `examples` — the two examples above.
- `tests` — unit and integration suites.
- `docs` — the documents above.
