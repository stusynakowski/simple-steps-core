# simple-steps backend (reference)

A drop-in FastAPI backend that exposes `simple-steps-core` to the `simple-steps`
React app and an optional LangGraph agent. Copy this folder into the
`simple-steps` repo and register your own operations.

## Files

| File | Role |
| --- | --- |
| [`app.py`](app.py) | `create_app(registry, engine, store=, planner=)` — the FastAPI factory. |
| [`store.py`](store.py) | In-memory workflow store (swap for a DB). |
| [`agent.py`](agent.py) | `Planner` protocol, step validation, and a reference LangGraph/LLM planner. |
| [`demo.py`](demo.py) | Runnable wiring: sample tools + a stub planner. |
| [`types.ts`](types.ts) | TypeScript types + a typed client for the React app. |

## Run the demo

```bash
python -m pip install -e ".[api]"
uvicorn examples.simple_steps_backend.demo:app --reload   # http://127.0.0.1:8000/docs
```

## Endpoints

| Method & path | Purpose |
| --- | --- |
| `GET /operations` | Tool palette: id, params, JSON Schema (for UI forms + agent grounding). |
| `POST /workflows` | Create a workflow from `{workflow_id, steps: StepSpec[]}`. |
| `GET /workflows/{id}` | Status + per-step results. |
| `POST /workflows/{id}/run` | Run all steps (async). |
| `POST /workflows/{id}/steps/{sid}/run` | Run one step. |
| `GET /workflows/{id}/dag` | Nodes + edges (from references and `orchestration.over`). |
| `POST /agent/propose` | Agent proposes/edits a validated `StepSpec[]`. |

## Wire it in your app

```python
from simple_steps_core import OperationRegistry, CoreEngine, register_orchestrators
from examples.simple_steps_backend.app import create_app
from examples.simple_steps_backend.agent import build_langgraph_planner

registry = OperationRegistry()
# register your operations here ...
register_orchestrators(registry)
registry.freeze()

engine = CoreEngine(registry)
planner = build_langgraph_planner(registry)   # needs langchain + an LLM (e.g. OPENAI_API_KEY)
app = create_app(registry, engine, planner=planner)
```

Without a planner, `/agent/propose` returns `503`; every other endpoint works.

## Frontend

Import [`types.ts`](types.ts) in the React app for typed models and a small
`SimpleStepsClient`:

```ts
import { SimpleStepsClient, singleStep } from "./types";

const api = new SimpleStepsClient("http://localhost:8000");
const ops = await api.operations();                 // render tool forms from input_schema
const plan = await api.propose({ goal: "square a list of 5" });
await api.createWorkflow({ workflow_id: "wf1", steps: plan.steps });
await api.runWorkflow("wf1");
```

See [docs/simple-steps-integration.md](../../docs/simple-steps-integration.md) for
the full integration guide (agent flow, references, security).
