# simple-steps-core

A lightweight backend workflow runtime that makes tool-based execution and intermediate data references easy to manage.

It is designed for services that need:

- Deterministic step execution
- Clear operation contracts
- Session-scoped data references
- Serializable, structured tool calls

## Design goals

- Tool-first runtime: operations are the only executable units.
- Structured-call persistence: workflows store tool calls as structured data.
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
from simple_steps_core import CoreEngine, ToolRegistry, ToolCall, Workflow

registry = ToolRegistry()


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

For a top-to-bottom explanation of how the pieces fit together, see
[How simple-steps-core works](docs/how-it-works.md).

Building the `simple-steps` app (React + a LangGraph agent) on top of this? See
the [simple-steps integration guide](docs/simple-steps-integration.md) and the
runnable reference backend in
[examples/simple_steps_backend](examples/simple_steps_backend).

A complete, runnable FastAPI server is in [examples/api_server](examples/api_server):

```bash
python -m pip install -e ".[api]"
uvicorn examples.api_server.app:app --reload   # http://127.0.0.1:8000/docs
```

## One-command tool server

Write a script that only declares tools, then serve it with the bundled command
— no server boilerplate:

```python
# mytools.py
from simple_steps_core import register_tool

@register_tool("add", description="Add two numbers.")
def add(a: int, b: int) -> int:
    return a + b

CONFIG = {"title": "My Tools", "port": 8000}   # optional
```

```bash
python -m pip install -e ".[api]"
simple-steps-core-server mytools.py            # http://127.0.0.1:8000/docs
```

The command imports your script, adds the built-in orchestrators, and serves
`GET /tools`, `POST /call` (run one tool), and `POST /run` (run a workflow of
steps). A runnable script is in [example_server.py](example_server.py). Optional
script settings: `CONFIG` (`title`/`host`/`port`/`orchestrators`/`freeze`) and
`RESOURCES` (name → factory) for tools that declare `Resource()` parameters.

## Streamlit dashboard (optional UI)

The same tools file can also drive a local **Streamlit** dashboard for building
and running workflows — a UI counterpart to the server:

```bash
python -m pip install -e ".[dashboard]"
simple-steps-core-dashboard mytools.py
```

The tool **contract** is the generic UI schema, rendered many independent ways.
A tool's `ui` is a `ToolUI` holding per-surface declarations keyed by target.
The recommended declaration separates the pre-execution `input` view from the
interactive post-execution `result` view. An advanced `full` view can instead
own the entire visual experience. The serializable `prefab` input is always
present when no prefab declaration is supplied.

The dashboard reads Streamlit input renderers with
`render(st, key, defaults) -> arguments` and result renderers with
`render(st, key, result)`. Missing renderers use generated form and `st.write`
fallbacks:

```python
def _make_list_ui(st, *, key, defaults):
    return {"n": st.slider("How many?", 1, 20, value=defaults.get("n", 5), key=key)}

def _make_list_result(st, *, key, result):
  st.bar_chart(result.value)

@register_tool("make_list", ui={
  "streamlit": {"input": _make_list_ui, "result": _make_list_result},
})
def make_list(n: int) -> list[int]:
    return list(range(n))
```

Because `ui` is a map, one tool can carry several targets at once — e.g. a
hand-written prefab view for React *and* a Streamlit view — each surface picks
its own; omit `prefab` to keep the auto-built default:

```python
@register_tool("pick_region", ui={
    "prefab": my_prefab_protocol,     # React frontend
    "streamlit": _pick_region_form,   # this dashboard
})
def pick_region(region: str) -> str:
    return region
```

Legacy single renderers remain input views. Use
`operation.ui.input(target)`, `operation.ui.result(target)`, or
`operation.ui.full(target)` for lifecycle-aware access; `get(target)` remains a
compatibility alias for the input or full primary view. See the
[Tool UI developer contract](docs/tool-ui.md) before implementing a full UI.

A runnable example — with a walkthrough of each tool — is in
[streamlit_example/](streamlit_example/README.md).

## Roadmap: tool decoration, orchestration & agents

We are extending the core so that a single decorated function can drive both an
**MCP server** and an **agentic workflow UI** — fusing MCP tool-calling with
LangGraph-style session management. Full design in
[specs/011](specs/011-tool-orchestration-and-agent-workflows.md).

What we are adding:

- **Real JSON Schema tool definitions** — decoration derives an `input_schema`
  (and `output_schema`) from type annotations, consumable as-is by MCP, OpenAI
  function-calling, and the UI.
- **Two-layer model** — a static **tool definition** (the contract) vs. a
  per-call **step config** (`StepSpec`) that carries its own orchestration and
  execution settings.
- **Three-kind parameters** — `data` (a value the caller/agent supplies),
  `reference` (a data slot wired to a prior step's output via `{"$ref": ...}`),
  and `resource` (an injected runtime object like a db connection, hidden from
  the schema).
- **Orchestration & execution config** — per-step `map`/`filter`/`expand`/
  `collapse` with concurrency and per-item error policy, plus sync/async,
  manual/auto run, timeouts, whole-step retries, and caching.
- **Data-centric session** — `SessionContext` reorganized into a `DataStore` of
  self-describing `DataEntry` records plus a separate `ResourceContainer`.
- **Integration adapters** — thin, optional, bidirectional adapters for MCP,
  LangGraph, and OpenAI; the core stays Pydantic-only.
- **Agent planner** — proposes and modifies a validated list of steps that users
  trace, edit, and run under their own control.

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
