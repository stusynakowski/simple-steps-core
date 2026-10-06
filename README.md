# simple-steps-core

**A spreadsheet for expensive, impure, failable Python functions.** You write
plain functions; the library turns each call into serializable data, runs it
against a tabular grid, and keeps a per-row ledger of what happened — so a
workflow of transcription, LLM, or model-inference steps can be authored,
staged, validated, and re-driven a row at a time.

It is a **backend library — it ships no UI** and pulls in exactly two packages,
`pandas` and `pydantic`.

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
| [shape-algebra.md](docs/shape-algebra.md) | the concept — verbs, tidy intent, row/column conventions |
| [object-model.md](docs/object-model.md) | the objects and how they nest (Tool → Operation → Step → Output) |
| [grid-model.md](docs/grid-model.md) | how `grid.py` is built |
| [defining-operations.md](docs/defining-operations.md) | the authoring grammar |
| [writing-tools.md](docs/writing-tools.md) | writing functions the grid can drive |
| [api-reference.md](docs/api-reference.md) | the Python import surface |
| [integration.md](docs/integration.md) | embedding the grid core in a backend |
| [react-api.md](docs/react-api.md) | the proposed HTTP/React contract |
| [status.md](docs/status.md) | what is built, what is open |
| [migration-plan.md](docs/migration-plan.md) | retiring the legacy engine onto the grid |

> **A note on the two models.** A legacy *engine* runtime (`CoreEngine`,
> `OrchestrationConfig`, `MapResult`, `Server`) still ships alongside the grid
> model and is being retired onto it ([migration-plan.md](docs/migration-plan.md)).
> Build new work against the **grid** model, and import it as a module —
> `Workflow`, `Operation` and `Step` mean different things in each:
>
> ```python
> from simple_steps_core import grid      # the grid model
> wf = grid.Workflow()
> ```

## Not in the grid core yet

The grid core is authoring + execution + serialization. Resources (dependency
injection), media assets, guardrails/UI, an HTTP server, multi-user sessions,
and async/concurrency are **not in it yet** — you bring the transport. See
[migration-plan.md](docs/migration-plan.md) for the plan to land them.

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
