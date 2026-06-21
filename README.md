# simple-steps-core

A lightweight backend workflow runtime that makes tool-based execution and intermediate data references easy to manage.

It is designed for services that need:

- Deterministic step execution
- Clear operation contracts
- Session-scoped data references
- Serializable workflow formulas

## Design goals

- Tool-first runtime: operations are the only executable units.
- Formula-first persistence: workflows store tool calls as formulas.
- Session isolation: each run context is scoped by session ID.
- Optional agent layer: planner can suggest tool calls without owning execution.

## Install

For library users:

```bash
python -m pip install simple-steps-core
```

For local development:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

For notebook examples:

```bash
python -m pip install -e ".[examples]"
```

## Why this helps backend workflow management

- Operations are explicit and typed, so execution is predictable.
- Deferred calls let you author workflows before execution.
- Session context isolates run data and references.
- Engine validation and reference resolution reduce glue-code complexity.

## Quick example

```python
from simple_steps_core import CoreEngine, OperationRegistry, ToolCall, Workflow

registry = OperationRegistry()


def make_list(n: int) -> list[int]:
    return list(range(n))


def total(data: list[int]) -> int:
    return sum(data)


make_list_op = registry.register("make_list", make_list, description="Create [0..n-1]")
registry.register("total", total, description="Sum a list of ints")

engine = CoreEngine(registry)
workflow = Workflow(engine, session_id="demo")
workflow["step1"] = make_list_op(n=5)

steps = workflow.run()
ref_id, value = engine.execute(
    ToolCall(operation_id="total", arguments={"data": steps[0].output.value}),
    workflow.context,
)

print(ref_id, value)
```

## Run checks

```bash
./scripts/run_checks.sh
```

## Integrating into a backend

See the [Integration Guide](docs/integration.md) for a task-oriented walkthrough:
registering operations, exposing the operation palette to a frontend, building and
validating workflows from user input, async execution, orchestrators
(`map`/`filter`/`expand`/`collapse`), full-session snapshot persistence, per-user
isolation, and a suggested HTTP API surface.

A complete, runnable FastAPI server is in [examples/api_server](examples/api_server):

```bash
python -m pip install -e ".[api]"
uvicorn examples.api_server.app:app --reload   # http://127.0.0.1:8000/docs
```

## Publish to PyPI

1. Build distributions:

   ```bash
   python -m build
   ```

2. Validate metadata and artifacts:

   ```bash
   python -m twine check dist/*
   ```

3. Upload:

   ```bash
   python -m twine upload dist/*
   ```

## Project structure

- `pyproject.toml`: package metadata and dev extras.
- `src/simple_steps_core`: library source package.
- `tests`: unit and integration test suite.
- `scripts/run_checks.sh`: quick local validation command.
- `runme.py`: end-to-end smoke flow.
- `examples/simple_steps_core_walkthrough.ipynb`: interactive walkthrough notebook.
