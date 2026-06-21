# Integration Guide

How to embed `simple-steps-core` into a backend service (e.g. behind a React
API) where end users author and run their own workflows.

This guide is task-oriented. For the conceptual overview see the
[README](../README.md).

---

## 1. Install

```bash
python -m pip install simple-steps-core
```

The only runtime dependency is `pydantic>=2.6`. Everything below imports from
the single stable entrypoint:

```python
from simple_steps_core import (
    CoreEngine, OperationRegistry, Workflow,
    register_orchestrators, make_session_id, SessionManager,
    SessionSnapshot, CodecRegistry, ToolCall, MapResult,
)
```

> Import only from `simple_steps_core`. Submodule paths are internal and may
> change.

---

## 2. Mental model

The backend owns the only Python callables. The frontend never executes
anything — it **authors formulas** (strings like `=load_csv(filepath='x.csv')`)
and reads back step status/results.

```
React UI  ──(JSON: steps as formulas)──▶  Backend API
   ▲                                          │
   │                                          ├─ REGISTRY.list_definitions()  → operation palette
   └──(status + results)──────────────────────┤─ Workflow.export_session()    → persist run
                                              └─ engine.arun()                → execute
```

Three roles:

| Concept | Role |
| --- | --- |
| **Operation** | A registered Python function (the unit of work). |
| **Workflow** | An ordered list of steps; each step is a formula. |
| **SessionContext** | Per-run payload store, isolated by `session_id`. |

---

## 3. Startup: register operations once, then freeze

Register every operation (and the built-in orchestrators) during application
startup, **before** serving requests, then freeze the registry. A frozen
registry is read-only, which makes concurrent reads safe across requests
without locks.

```python
from simple_steps_core import OperationRegistry, register_orchestrators

registry = OperationRegistry()

def load_csv(filepath: str) -> list[dict]:
    ...

def filter_rows(data: list[dict], min_value: int = 0) -> list[dict]:
    ...

registry.register("load_csv", load_csv, description="Load a CSV file")
registry.register("filter_rows", filter_rows, description="Keep rows >= min_value")

# Add map / filter / expand / collapse
register_orchestrators(registry)

# Lock it for the lifetime of the process.
registry.freeze()
```

Registering after `freeze()` raises `RegistryFrozenError`.

### Shipping operations as "packs"

Group related operations in a module and load it on boot:

```python
# my_app/ops/csv_ops.py
from simple_steps_core import register_operation

@register_operation("load_csv", description="Load a CSV file")
def load_csv(filepath: str) -> list[dict]:
    ...
```

```python
from simple_steps_core.packs.loader import load_pack_module
load_pack_module("my_app.ops.csv_ops")  # self-registers into the global REGISTRY
```

---

## 4. Expose the operation palette to the frontend

```python
def list_operations() -> list[dict]:
    return [d.model_dump() for d in registry.list_definitions()]
```

Each entry is JSON-ready:

```json
{
  "operation_id": "filter_rows",
  "description": "Keep rows >= min_value",
  "params": [
    {"name": "data", "type_name": "list", "required": true, "default": null},
    {"name": "min_value", "type_name": "int", "required": false, "default": 0}
  ]
}
```

The frontend renders these as form fields or graph nodes. `required` and
`default` drive validation in the UI.

---

## 5. Build and validate a workflow from user input

The frontend sends steps as `{step_id, formula}`. Validate each formula at the
API boundary before persisting:

```python
from simple_steps_core import (
    CoreEngine, Workflow, parse_formula, validate_tool_call, ValidationError,
)

engine = CoreEngine(registry)

def build_workflow(session_id: str, steps: list[dict]) -> Workflow:
    wf = Workflow(engine, session_id=session_id)
    for step in steps:
        call = parse_formula(step["formula"])
        validate_tool_call(call, registry)   # raises ValidationError on bad input
        wf[step["step_id"]] = step["formula"]
    return wf
```

### Reference rules (important)

A step output is referenced by **another step's id**, but the reference grammar
requires the token to **start with `step`** and be written as a **quoted
string** in a formula:

```python
wf["step_load"]   = "=load_csv(filepath='data.csv')"
wf["step_filter"] = '=filter_rows(data="step_load", min_value=100)'
#                                       ^^^^^^^^^^^ quoted reference to step_load
```

- Valid references: `"step_load"`, `"step_load.field"`, `"step_load.rows[0]"`.
- A step id that does **not** start with `step` cannot be referenced by other
  steps. Name any referenceable step `step_*`.

---

## 6. Run the workflow

### Synchronous (simple/scripts)

```python
steps = wf.run()
for s in steps:
    print(s.step_id, s.status, s.output.value)
```

### Asynchronous (recommended for a web backend)

Async lets orchestrator steps fan out concurrently and keeps the event loop
free. Steps still run in order (a later step may depend on an earlier one);
concurrency happens *inside* orchestrator steps.

```python
steps = await wf.arun()
```

Read a result by step id:

```python
value = wf.context.value_for_step("step_filter")
```

---

## 7. Iterative processing with orchestrators

Orchestrators apply an existing operation across a collection produced by a
prior step, isolating per-item failures.

```python
wf["step_ids"]   = "=load_ids()"                                  # -> [1, 2, 3, ...]
wf["step_fetch"] = '=map(over="step_ids", op="fetch_record", concurrency=8, retries=2)'
await wf.arun()

result = wf.context.value_for_step("step_fetch")   # MapResult
result.ok            # list of successful values
result.failed        # list of ItemOutcome (index, error)
result.ok_count
result.failed_count
```

| Orchestrator | Shape | Default `on_error` |
| --- | --- | --- |
| `map` | N → N outcomes (`MapResult`) | `collect` |
| `filter` | keep truthy items | `skip` |
| `expand` | flat-map (1 → many, flattened) | `collect` |
| `collapse` | reduce N → 1 via a 2-arg op | n/a |

Common parameters: `over` (quoted reference), `op` (sub-operation id),
`concurrency`, `retries`, `on_error` (`collect` | `fail_fast` | `skip`),
`arg` (override which sub-op param receives each item).

`result.ok` / `result.failed` are themselves referenceable, so you can re-drive
only the failures or feed successes onward:

```python
wf["step_total"] = '=collapse(over="step_fetch.ok", op="sum_amounts", initial=0)'
```

---

## 8. Persistence: save and resume an entire run

`to_json()` saves **structure only** (formulas/status), not the data. To
persist a run *with its computed payloads*, use the session snapshot.

```python
# Save full session (structure + payloads) to your DB
snapshot_json: str = wf.export_session_json()
db.save(workflow_id, snapshot_json)

# Later / another worker: restore and continue
wf2 = Workflow.import_session_json(snapshot_json, engine)
value = wf2.context.value_for_step("step_filter")   # payload is back
```

Structure-only persistence (re-runs from scratch) remains available:

```python
wf_json = wf.to_json()
wf = Workflow.from_json(wf_json, engine, session_id="run-2")
```

### Custom payload types (DataFrames, domain objects)

The snapshot codec handles JSON-native values and Pydantic models
automatically. For other types, register a codec **before** exporting. Pickle
is intentionally *not* used (it is an arbitrary-code-execution risk on load);
unencodable values raise `SnapshotError`.

```python
import pandas as pd
from simple_steps_core import CodecRegistry

codecs = CodecRegistry()
codecs.register(
    "dataframe",
    pd.DataFrame,
    encode=lambda df: df.to_dict(orient="records"),
    decode=lambda rows: pd.DataFrame(rows),
)

snapshot_json = wf.export_session_json(codecs)
wf2 = Workflow.import_session_json(snapshot_json, engine, codecs)
```

---

## 9. Per-user isolation and concurrency

Nothing in the execution layer is implicitly shared, so isolation is a matter
of giving each run its own `SessionContext`.

- **Namespace sessions per user** so refs never collide:

  ```python
  session_id = make_session_id(user_id, workflow_id, run_id)  # "u1:wf9:run3"
  wf = Workflow(engine, session_id=session_id)
  ```

- **One `SessionContext` per run — never shared across users.**

- **Serialize writes within a session** using `SessionManager`:

  ```python
  manager = SessionManager()

  async def run_for_user(user_id, workflow_id, run_id, steps):
      sid = make_session_id(user_id, workflow_id, run_id)
      await manager.get_or_create(sid)
      async with manager.lock(sid):           # serialize this session's writes
          wf = build_workflow(sid, steps)
          return await wf.arun()
  ```

| Component | Sharing rule |
| --- | --- |
| `OperationRegistry` | One per process; `freeze()` after startup; read-only thereafter. |
| `CoreEngine` | Stateless; safe to share (takes context as an argument). |
| `SessionContext` | One per run; never shared. |
| `SessionManager` | One per process; in-memory (single process — see below). |

---

## 10. Multi-worker / task-queue deployment

An in-memory `SessionManager` is single-process. To scale across workers, make
the **snapshot** the unit of hand-off:

1. API builds the workflow, persists `export_session_json()` to the DB.
2. A task-queue worker (Celery / RQ / arq) loads it with
   `import_session_json()`, runs `await wf.arun()`, and writes the new snapshot
   back.
3. The API polls step status for the frontend.

```python
# worker.py
async def execute_run(workflow_id: str):
    snapshot_json = db.load(workflow_id)
    wf = Workflow.import_session_json(snapshot_json, engine, codecs)
    await wf.arun()
    db.save(workflow_id, wf.export_session_json(codecs))
```

---

## 11. Suggested HTTP endpoints

| Method & path | Purpose | Core call |
| --- | --- | --- |
| `GET /operations` | Palette for the UI | `registry.list_definitions()` |
| `POST /workflows` | Create/save a workflow | `build_workflow()` → `export_session_json()` |
| `POST /workflows/{id}/run` | Execute (enqueue) | `import_session_json()` → `arun()` |
| `GET /workflows/{id}` | Status + results | read `Step.status`, `context.value_for_step()` |

Minimal FastAPI sketch:

```python
from fastapi import FastAPI, HTTPException
from simple_steps_core import ValidationError

app = FastAPI()

@app.get("/operations")
def operations():
    return [d.model_dump() for d in registry.list_definitions()]

@app.post("/workflows")
def create_workflow(payload: dict):
    sid = make_session_id(payload["user_id"], payload["workflow_id"], "draft")
    try:
        wf = build_workflow(sid, payload["steps"])
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    snapshot = wf.export_session_json()
    db.save(payload["workflow_id"], snapshot)
    return {"workflow_id": payload["workflow_id"]}
```

---

## 12. Optional: agent/planner layer

To let an LLM suggest the next step, implement the `Planner` protocol and route
through `AgentService`. It only *suggests* a `ToolCall`; execution stays with
the engine.

```python
from simple_steps_core.agent.service import AgentService
from simple_steps_core.agent.types import AgentRequest, AgentResponse

class MyPlanner:
    def plan(self, request: AgentRequest) -> AgentResponse:
        # call your LLM with request.message + request.available_operations
        return AgentResponse(message="...", suggested_tool_call=None)

agent = AgentService(MyPlanner())
reply = agent.invoke(AgentRequest(
    message="summarize the failures",
    available_operations=[d.model_dump() for d in registry.list_definitions()],
))
```

---

## 13. Gotchas checklist

- [ ] Referenceable steps are named `step_*` and references are **quoted strings**.
- [ ] `registry.freeze()` is called after all `register(...)` calls.
- [ ] Each run uses its own `session_id` via `make_session_id(...)`.
- [ ] `to_json()` drops payloads; use `export_session_json()` to keep data.
- [ ] Custom payload types have a registered codec before export.
- [ ] Don't call `engine.execute()` from inside a running event loop — use
      `await wf.arun()` / `await engine.aexecute()` there.
