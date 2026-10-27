# simple-steps-core

> **Redesign in progress (branch `core-handover`).** Core is being cut down to
> the grid model, with a `Catalog` and a `Kernel` you can drive from a Python
> session. What follows describes the code as it is today; what it is
> becoming is in [docs/design/](docs/design/README.md).

**A spreadsheet for expensive, impure, failable Python functions.** You write
plain functions; the library turns each call into serializable data, runs it
against a tabular grid, and keeps a per-row ledger of what happened — so a
workflow of transcription, LLM, or model-inference steps can be authored,
staged, validated, and re-driven a row at a time.

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
from simple_steps_core import grid
from simple_steps_core.grid import tool, mod

@tool
def scale(n, weight=1):
    return n * 10 * weight

wf = grid.Workflow()
wf["readings"] = pd.DataFrame({"n": [1, 2, 3]})   # a source step
wf["scored"]   = scale(wf["readings"])            # pass a reference → inferred map
wf.run_all()

wf.step("scored").output.values        # [10, 20, 30]
wf.step("scored").output.view()        # the grid joined with its per-row ledger
```

Three ideas carry the whole model:

- **A value is one cell.** A tool invocation produces exactly one cell; turning
  it into rows and columns is a separate declaration — a **shape verb**.
- **Shape comes from the verb, not the payload.** `map` / `filter` / `expand` /
  `widen` / `collapse` / `group` / `sweep` / `select` / … reshape the grid;
  passing a reference infers the right one (`scale(ref)` → `map`), and you can
  always write it explicitly: `scale[mod.map(over=wf["readings"])]`.
- **Every output is a DataFrame plus a ledger.** `output.data` is the payload
  grid downstream steps consume; `output.ledger` records status/error per unit,
  so a failure stays pinned to the one row it belongs to and is re-drivable.

## The one example

[examples/all_orchestrations/](examples/all_orchestrations/) is a single
workflow over one registry of tools that exercises **every shape verb**, both
fan-out chains (`group`→`collapse`, `expand`→`widen`), execution modifiers,
serialization, staging/validation, failure handling, and verb inference.

```bash
python examples/all_orchestrations/pipeline.py        # prints every step
pytest tests/integration/test_all_orchestrations.py   # the same, asserted
```

## Documentation

| doc | what |
|---|---|
| [docs/design/](docs/design/README.md) | **the redesign**: the object model, the grid model, step expressions, outputs, extensions, interactive sessions, and the plan |
| [shape-algebra.md](docs/shape-algebra.md) | the concept: verbs, tidy intent, row/column conventions |
| [grid-model.md](docs/grid-model.md) | how `grid.py` is built today |
| [step-expressions.md](docs/step-expressions.md) | the step grammar, as written before the redesign |

The three older docs use some retired words (ledger, `over=`, payload). They
are folded into `docs/design/` as the redesign lands.

## Develop

```bash
./scripts/run_checks.sh          # lint + tests
pytest -q                        # the suite
```

## Project structure

- `src/simple_steps_core` — the library (`grid.py` is the grid model).
- `examples/all_orchestrations` — the one runnable example.
- `tests` — unit (`test_grid.py`) and integration suites.
- `docs` — the documents above.
