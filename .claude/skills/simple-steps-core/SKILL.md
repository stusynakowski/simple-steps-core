---
name: simple-steps-core
description: Author tools, resources, and workflows for the simple-steps-core orchestration runtime, and stand them up as a FastAPI server or a Streamlit dashboard. Use whenever writing @register_tool functions, Resource() dependencies, Operation/Workflow specs, orchestrated map/filter/expand/collapse steps, or a tools file that ends in Server().run() / Dashboard().run().
---

# simple-steps-core: tools, resources, and surfaces

A tool-first workflow runtime. You write plain Python functions; the library
introspects them into contracts, stores each call as serializable data, and
executes calls against a session-scoped payload store.

## Vocabulary (use these words exactly)

| Term | What it is | Where |
|---|---|---|
| **Tool** | a registered capability (one Python function) | `operations/registry.py` |
| **ToolDefinition** | its public contract: id, params, JSON Schema, guardrails | `domain/models.py` |
| **ToolCall** | a durable `{operation_id, arguments}` record — nothing executed | `domain/models.py` |
| **Operation** | a Tool *equipped* with arguments + orchestration + execution config | `domain/models.py` |
| **Step** | `Operation + Data` — the spec plus its status/output | `domain/models.py` |
| **Workflow** | ordered steps, dict-like API, run against one session | `execution/workflow.py` |
| **Stage** | a computed groupby view over steps sharing a `stage` tag | `execution/workflow.py` |
| **Resource** | an injected runtime dependency (db, client, config) — *not* data | `operations/dependencies.py` |
| **SessionContext** | the per-session payload store (`ref -> value`, `step_id -> ref`) | `execution/context.py` |

Import everything from the top-level package (`from simple_steps_core import ...`);
the curated surface is [api/public.py](src/simple_steps_core/api/public.py). Do not
reach into sub-packages in user-facing code.

---

## 1. Defining a tool

```python
from simple_steps_core import register_tool

@register_tool("load_orders", description="Load orders for a region.", category="io", type="dataframe")
def load_orders(region: str, limit: int = 100) -> list[dict]:
    ...
```

Rules that actually matter:

- **Annotate every parameter and the return type.** `build_input_schema` /
  `build_output_schema` ([operations/schema.py](src/simple_steps_core/operations/schema.py))
  run the signature through Pydantic. Unannotated params degrade to `Any`; an
  unannotated return yields `output_schema=None`, which silently disables static
  reference type-checking for downstream steps.
- **Keyword-only at call time.** The `Tool` wrapper only accepts `**kwargs`
  (`registry.py` `__call__` / `run`). Positional-only params will break.
- `description` falls back to the first paragraph of the docstring.
- `type` is `"source" | "dataframe" | "raw_output"` (default `raw_output`) — a
  frontend hint, not behavior.
- The decorator returns a **dual-mode `Tool`**, not the raw function:
  ```python
  call  = load_orders(region="EMEA")      # -> ToolCall, deferred, nothing runs
  value = load_orders.run(region="EMEA")  # -> immediate escape hatch
  ```
  So a tool cannot directly call another tool by name — inside a workflow, wire
  them with references; inside an orchestrator, use the injected handle.
- `async def` is detected automatically (`is_async`); the engine awaits it.
  Sync tools are run off the loop via `asyncio.to_thread`.

### Guardrails

```python
from simple_steps_core import ArgGuardrail, Guardrails, register_tool

@register_tool("charge", guardrails=Guardrails(
    usage="Only after the user confirms.",
    rules=["Never charge twice for one order id."],
    destructive=True,
    requires_confirmation=True,
    arguments={"amount": ArgGuardrail(minimum=1, maximum=1000, note="USD")},
))
def charge(amount: int) -> str: ...
```

- `arguments` **is enforced** — twice: on literal values at validation time, and
  again on *resolved* values after reference substitution
  (`enforce_arg_guardrails`, called from both `CoreEngine.execute` and
  `aexecute`). A bad value raises `ValidationError`.
- `usage`, `rules`, `read_only`, `destructive`, `requires_confirmation` are
  **declarative only** — nothing in the runtime enforces them today. If a host
  needs a confirmation gate, it must read the flag and implement it.
- Guardrail `enum` / bounds / `note` also shape the auto-generated form widgets
  (`build_default_ui`).

### Tool UI (optional)

`ui=` is a `{target: declaration}` map. Each target may be composed
(`{"input": ..., "result": ...}`) or exclusive (`{"full": ...}`) — never both.
A bare value is treated as the `input` view.

```python
def _make_list_ui(st, *, key, defaults):        # Streamlit renderer contract
    n = st.slider("How many?", 1, 20, value=defaults.get("n", 5), key=f"{key}_n")
    return {"n": n}                              # -> arguments dict

@register_tool("make_list", ui={"streamlit": _make_list_ui, "prefab": _prefab_doc})
def make_list(n: int) -> list[int]: ...
```

`prefab` (a JSON-safe protocol document for a React frontend) is **auto-built**
from the input schema when omitted, so you rarely write one by hand. Full rules:
[docs/tool-ui.md](docs/tool-ui.md).

---

## 2. Defining a resource

A resource is a runtime object a tool needs but that is **not part of the data
flow**: a DB connection, an HTTP/LLM client, a config object. Mark it with a
`Resource()` default:

```python
from simple_steps_core import Resource, register_tool

@register_tool("load_orders")
def load_orders(region: str, db = Resource()) -> list[dict]:
    return db.query(region)
```

What that changes:

- `region` is a **data param** — in the JSON Schema, suppliable by a caller/agent.
- `db` is a **resource param** — `kind="resource"`, excluded from the schema,
  listed in `definition.dependencies`, rejected if a caller tries to supply it,
  and filled by `CoreEngine._inject_resources` from the session's container.
- `Resource("orders_db")` overrides the container key; it defaults to the
  parameter name.

Registering the actual object — declare → load → check → use
([execution/resources.py](src/simple_steps_core/execution/resources.py)):

```python
workflow.context.resources.register("db", lambda: connect(), check=lambda db: db.execute("SELECT 1"))
workflow.context.resources.register_value("cfg", settings)   # already-built instance

workflow.context.resources.check_all()   # SummaryTable of hello-world results
workflow.missing_resources()             # names required by this workflow but unregistered
```

- Factories are built **lazily on first use** and cached per container.
- Resources are **never serialized** into a session snapshot; on load they are
  rebuilt from their factories.
- `App.register_resource(...)` declares a default that each new `Session` gets
  via `container.clone()` — factories and checks are copied so every session
  builds its own instance, but already-built *values* are shared by reference.
- In a tools file, the `RESOURCES` module-level dict is the ergonomic form:
  `{"db": connect}` (callable → factory) or `{"cfg": settings}` (instance).

---

## 3. Wiring steps together

### References — the sharp edge

An argument may be a literal or a **reference token** naming an earlier step:

```python
wf["step1"] = load_orders(region="EMEA")
wf["step2"] = summarize(rows="step1")        # resolved from the session store
wf["step3"] = report(n="step2.total")        # dotted field / bracket index allowed
```

> **The token must match `^step[\w-]*(?:\.\w+|\[...\])*$` (case-insensitive).**
> Step ids that don't start with `step` (e.g. `"load_csv"`) can **never** be
> referenced — the resolver treats the argument as a literal string and the tool
> silently receives `"load_csv"`. Conversely, a literal string value that
> happens to start with `step` *will* be misread as a reference. Name steps
> `step1`, `step_totals`, … and avoid `step*`-shaped literal data.

Validation is layered: `validate_tool_call` checks existence/arity/types of
literals only (references stand in for any type), `check_reference_types`
does a best-effort static pass over a whole workflow, and
`Workflow.validate()` returns a `SummaryTable` of unknown tools, forward/unknown
references, and missing resources — run it before executing.

### Orchestration (breadth)

Declare it on the step, not by calling an orchestrator yourself:

```python
from simple_steps_core import Operation, OrchestrationConfig, StepExecutionConfig

wf.add(Operation(
    step_id="step2",
    name="process_item",                       # the per-item tool
    stage=1,
    arguments={"threshold": 0.8},              # constant kwargs shared by every sub-call
    orchestration=OrchestrationConfig(mode="map", over="step1"),        # shape
    execution=StepExecutionConfig(concurrency=8, retries=2),            # conduct
))
```

**The two configs are isolated by concern and share no fields.**
`OrchestrationConfig` is shape only — `mode`, `over`, `item_arg`, `initial`.
Conduct — `concurrency`, `on_item_error`, `retries`, `timeout`, `cache`, `run` —
lives on `StepExecutionConfig`. Both set `extra="forbid"`, so passing a conduct
field to the orchestration config raises. `mode` defines the *unit of work*
(the whole call when `single`, one item when fanned out) and every conduct field
acts on that unit. See [docs/config-isolation.md](docs/config-isolation.md).

`to_tool_call()` compiles that into `map(over="step1", op="process_item", ...)`.
Modes: `single` (default), `map`, `filter`, `expand` (flat-map), `collapse`
(reduce, needs a 2-arg tool: accumulator, item).

- The item parameter is inferred as the tool's first **required** param unless
  you set `item_arg`.
- `map` returns a `MapResult`; downstream steps consume `step2.ok` (successful
  values) or `step2.failed` (outcomes to re-drive). Per-item failures are
  isolated by default (`execution.on_item_error="collect"`); `"fail_fast"`
  aborts, `"skip"` drops.
- Orchestrators are registered by `register_orchestrators(registry)` — `App`,
  `Server`, and `Dashboard` all do this for you at startup.

### Running

```python
wf.run()                  # sync, every step in order
await wf.arun()           # async
wf.run_by_stages()        # one stage at a time
wf.info(); wf.preview("step1")
```

`CoreEngine.execute()` drives async/orchestrator tools via `asyncio.run` — it
**raises inside an already-running event loop**. In async code (FastAPI handlers,
notebooks with a live loop) use `aexecute` / `arun`.

For multi-user serving, give every logical run its own `SessionContext` via
`SessionManager.get_or_create(make_session_id(user, workflow, run))` and hold
`manager.lock(session_id)` around mutations.

---

## 4. Standing it up

Both surfaces read the **same tools file**: a plain script that registers tools
plus two optional module-level dicts, `CONFIG` and `RESOURCES`. Pick the surface
by which line you put at the bottom.

### A. HTTP server (FastAPI)

```python
# my_tools.py
from simple_steps_core import Resource, register_tool
from simple_steps_core.serving import Server

@register_tool("add", description="Add two numbers.")
def add(a: int, b: int) -> int:
    return a + b

CONFIG = {"title": "My Tools", "host": "127.0.0.1", "port": 8000,
          "orchestrators": True, "freeze": True}
RESOURCES = {"db": connect}          # callable -> factory, else an instance

if __name__ == "__main__":
    Server().run()
```

```bash
pip install -e ".[api]"
python my_tools.py
```

Endpoints ([serving.py](src/simple_steps_core/serving.py)):

| Route | Body | Returns |
|---|---|---|
| `GET /tools` | — | the palette: every `ToolDefinition` as JSON |
| `POST /call` | `{"operation_id": "add", "arguments": {...}}` | `{"value": ...}` (422 on validation failure) |
| `POST /run` | `{"steps": [ <Operation>, ... ]}` | `{"steps": [{step_id, status, value, error}]}` — stops at the first failure |

Notes:
- **It is stateless.** Each request builds a fresh `Workflow`, so references
  only resolve *within* one `/run` body; nothing survives between requests. For
  durable sessions, build your own app around `SessionManager` +
  `engine.aexecute_step(...)` rather than using `build_app`.
- `freeze` defaults to **True** here: the registry is locked after load, so any
  later `register` raises `RegistryFrozenError`. Register everything at import time.
- `App(...).serve()` is the alternative launcher when you're already holding an
  `App` facade; it rebuilds default resources per request from the container.

### B. Streamlit dashboard

```python
# my_tools.py
from simple_steps_core import register_tool
from simple_steps_core.streamlit import Dashboard

@register_tool("add", description="Add two numbers.")
def add(a: int, b: int) -> int:
    return a + b

CONFIG = {"title": "My Tools Dashboard"}
RESOURCES = {"names": _NameService}

if __name__ == "__main__":
    Dashboard().run()
```

```bash
pip install -e ".[dashboard]"
python my_tools.py          # re-execs itself under `streamlit run`
# or: streamlit run my_tools.py   (detected, renders in-process)
```

`Dashboard().run()` inspects the caller's globals for `CONFIG` / `RESOURCES`,
registers orchestrators, and renders the generic Step Manager: a tool palette,
per-step argument forms, a literal-vs-earlier-step source picker per argument,
orchestration/execution tabs, and workflow JSON load/save.

Per-tool Streamlit views are opt-in via `ui={"streamlit": fn}` with the contract
`render(st, *, key, defaults) -> args dict`. Key every widget with the supplied
`key` prefix so two steps using the same tool don't collide. Tools without a
view get an auto-built form from the contract.

Streamlit is imported lazily throughout, so importing
`simple_steps_core.streamlit` never requires the extra to be installed.

---

## Checklist before you hand back a tools file

1. Every param and return annotated; description or docstring present.
2. Resource params marked `Resource()` and present in `RESOURCES` (or on the
   session container) — cross-check with `workflow.missing_resources()`.
3. Step ids are `step*`-shaped if anything references them.
4. `wf.validate()` reports `✓ ok`.
5. Orchestrated steps name a real collection-producing step in `over=`.
6. Async tools reached through `arun`/`aexecute`, never `execute` inside a loop.
7. Exactly one of `Server().run()` / `Dashboard().run()` under
   `if __name__ == "__main__":`, with the matching extra installed.

## Known sharp edges in the current tree

- `Guardrails.requires_confirmation` / `destructive` / `read_only` are never read
  by the runtime — hosts must enforce them.
- `Workflow.run_step` records the failure on the step *and* re-raises, so
  `Workflow.run()` aborts the remaining steps; catch per-step if you need
  continue-on-error semantics.
- `StepExecutionConfig.concurrency` / `on_item_error` / `retries` are honored
  when a step fans out. `retries` on a `single` step, plus `run`, `timeout`,
  `cache`, `StageExecutionConfig` and `WorkflowExecutionConfig`, are still
  declared but never read — authoring intent a host must implement.
