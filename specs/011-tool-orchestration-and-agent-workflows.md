# 011 - Tool Decoration, Orchestration & Agent Workflows (MCP × LangGraph)

## 1. Overview

Specs [009](requirements_for_frontend.md) and [010](core_contract_for_frontrnd%20.md)
define *where* code lives and the *runtime contract* for single-step execution.
This spec defines the next evolution of `simple-steps-core`: a first-class,
**structured** model for decorating functions as tools, composing them into
traceable workflows, running them in a data-centric session, and exposing the
whole thing to **MCP servers** and **LangGraph agents**.

The intent is to *fuse and extend* two ecosystems:

- **Extend MCP** — decorate a Python function once and expose it as an MCP tool
  (with a real JSON Schema), while adding capabilities MCP lacks: orchestration
  (map/filter/expand/collapse), references between calls, and injected resources.
- **Extend LangGraph-style session management** — manage a *flow of tool calls*
  that an agent can propose and modify, and that a user can trace, edit, and run
  step-by-step under their own control.

The structured `ToolCall` is the durable encoding of an operation invocation:
everything below layers a richer surface **on top of** the existing
`ToolCall` / engine. The legacy string *formula* parser has been removed.

## 2. Scope

**In Scope:**
- The two-layer model: **Tool definition** (static contract) vs. **Step config**
  (per-invocation).
- The three-kind **parameter model** (`data` | `resource`; a *reference* is a
  data param whose value is a `$ref`).
- **JSON Schema** generation for tool inputs/outputs.
- Structured **`StepSpec`**, **`OrchestrationConfig`**, and **`ExecutionConfig`**.
- A data-centric **session model**: `DataEntry` / `DataStore` / `ResourceContainer`.
- Canonical **serialization formats** for tools, workflows, and sessions.
- **Integration adapters** for MCP, LangGraph, and OpenAI (bidirectional, optional).
- The **agent planner** contract (propose / modify a `list[StepSpec]`).

**Out of Scope (v1):**
- Cross-session long-term memory store (deferred; see §11).
- HTTP/WebSocket transport, auth, and UI rendering (owned by the app host).

## 3. Architecture Intent

### 3.1 Two-layer model

A **tool** is defined once and describes the function. A **step** is one
configured invocation of that tool inside a workflow. Orchestration and
execution config belong to the **step**, never the tool.

| Layer | Role | Ecosystem it extends |
| --- | --- | --- |
| **Tool definition** | static contract: name, schema, dependencies, safety hints | MCP (tool calling) |
| **Step config** | one call: id, args, orchestration, execution, trace | LangGraph (flow of calls) |

### 3.2 Parameter model (three kinds, two at the signature level)

Every parameter is classified at decoration time:

- **data** — a JSON-safe value the caller supplies. Appears in `input_schema`.
  Its value form is either a **literal** or a **reference** `{"$ref": "stepN[.field]"}`.
- **resource** — a runtime object (db connection, client, config) injected from
  the `ResourceContainer`. Excluded from `input_schema`; listed in `dependencies`.

A **reference** is *not* a third kind — it is an alternate value-form of a data
param sourced from a prior step's output. Litmus test: *should the agent ever
choose this value?* Yes → `data`; no (it is infrastructure) → `resource`.

## 4. Data Model

### 4.1 Tool definition

```
ToolDefinition:
  id, name, title, description, version, category, tags
  params: list[ToolParam]        # data + resource params
  input_schema: dict             # JSON Schema (data params only)
  output_schema: dict | None
  is_async, is_orchestrator
  annotations: {read_only, destructive, idempotent, open_world}
  default_timeout: float | None
  dependencies: list[str]        # names of resource params

ToolParam:
  name, kind: "data" | "resource"
  type_name, required, default, description
```

### 4.2 Step config

```
StepSpec:
  id                             # stable, referenceable step id
  name                           # -> ToolDefinition.name
  arguments: dict[str, Literal | Ref]   # Ref serializes to {"$ref": "..."}
  orchestration: OrchestrationConfig
  execution: ExecutionConfig
  # runtime trace: status, output ref, shape, error

OrchestrationConfig:            # breadth: how the tool is applied across inputs
  mode: single | map | filter | expand | collapse     (default single)
  over: Ref | None              # required unless single; must be a $ref
  item_arg: str | None          # tool data param the item binds to
  concurrency: int = 1
  on_error: collect | fail_fast | skip
  retries: int = 0              # PER-ITEM
  retry_backoff: none | fixed | exponential

ExecutionConfig:                # invocation of the whole step (orthogonal)
  mode: sync | async = sync
  run: auto | manual = manual   # user controls execution (human-in-the-loop)
  timeout: float | None
  retries: int = 0              # WHOLE-STEP
  retry_backoff: none | fixed | exponential
  cache: bool = False
```

Mode output shapes: `single` → tool return; `map` → `MapResult` (`.ok`/`.failed`/
`.values`); `filter` → subset; `expand` → flattened list; `collapse` → reduced
value. `on_error` defaults by mode: `map`/`expand` → `collect`, `filter` → `skip`,
`single`/`collapse` → `fail_fast`.

### 4.3 Session model (data-centric)

```
DataEntry:                      # one rich, self-describing step output
  ref, value, step_id, kind, shape, codec, ephemeral, created_at

DataStore:                      # all step outputs
  _entries: {ref -> DataEntry}
  _by_step: {step_id -> ref}
  put(value, step_id) / get(ref) / entry(ref)
  value_for_step / entry_for_step / ref_for_step
  shape(ref) / preview(ref, offset, limit) / list()

ResourceContainer:              # runtime resources (separate lifecycle, never serialized)
  register(name, factory) / get(name) / names() / aclose()

SessionContext:                 # the facade
  session_id
  data: DataStore
  resources: ResourceContainer
  codecs: CodecRegistry
```

## 5. Serialization Formats

### 5.1 Tool (per decorated function)

```json
{
  "id": "load_orders",
  "name": "load_orders",
  "description": "Load orders for a region.",
  "params": [
    { "name": "region", "kind": "data",     "type_name": "str",      "required": true },
    { "name": "db",     "kind": "resource", "type_name": "Database", "required": true }
  ],
  "input_schema": {
    "type": "object",
    "properties": { "region": { "type": "string" } },
    "required": ["region"],
    "additionalProperties": false
  },
  "output_schema": { "type": "object" },
  "annotations": { "read_only": true },
  "dependencies": ["db"]
}
```

### 5.2 Workflow (ordered list of steps)

```json
{
  "workflow_id": "wf_orders_report",
  "steps": [
    { "id": "step1", "name": "load_orders",
      "arguments": { "region": "EMEA" },
      "orchestration": { "mode": "single" },
      "execution": { "mode": "sync", "run": "manual" } },
    { "id": "step2", "name": "summarize",
      "arguments": { "data": { "$ref": "step1" }, "by": "category" },
      "orchestration": { "mode": "single" },
      "execution": { "mode": "async", "run": "manual" } }
  ]
}
```

Stripping `id` + `orchestration` and resolving `$ref`s yields a literal MCP
`tools/call` (`{ "name", "arguments" }`) per step.

### 5.3 Session (live vs. snapshot)

```json
// live (objects are real)
{ "session_id": "user42__wf__run7",
  "outputs": { "sess__a1b2": "<DataFrame>", "sess__e5f6": { "north": 320 } },
  "step_to_ref": { "step1": "sess__a1b2", "step2": "sess__e5f6" },
  "resources": ["db"] }

// snapshot (objects via codecs; ephemeral omitted; resources by name)
{ "session_id": "user42__wf__run7",
  "workflow": { "workflow_id": "wf", "steps": [] },
  "payloads": { "sess__a1b2": { "codec": "dataframe", "data": {} } },
  "step_to_ref": {}, "resources": ["db"] }
```

## 6. Functional Requirements

### 6.1 Tool decoration & schema
- **REQ-TOOL-001:** Decorating a function shall produce a `ToolDefinition`
  including a JSON Schema `input_schema` derived from the real type annotations.
- **REQ-TOOL-002:** `output_schema` shall be derived from the return annotation
  when present.
- **REQ-TOOL-003:** Each parameter shall be classified `data` or `resource`;
  `resource` params shall be excluded from `input_schema` and listed in
  `dependencies`.
- **REQ-TOOL-004:** `$ref`/`$defs` in generated schemas shall be dereferenceable
  for clients that do not resolve references.
- **REQ-TOOL-005:** `*args`/`**kwargs` functions shall be rejected (no complete
  schema can be produced).

### 6.2 Step & workflow
- **REQ-TOOL-006:** A step shall be represented structurally (`StepSpec`), which
  supersedes the removed string-formula encoding.
- **REQ-TOOL-007:** A data argument shall accept either a literal or a reference
  `{"$ref": "stepN[.field]"}`; references shall validate without type-checking.
- **REQ-TOOL-008:** `OrchestrationConfig.over` shall be required iff `mode` is not
  `single`, and shall be a reference.
- **REQ-TOOL-009:** For `map`/`filter`/`expand`, the `item_arg` slot shall not
  also be supplied in `arguments`.
- **REQ-TOOL-010:** Orchestration retries (per-item) and execution retries
  (whole-step) shall be independent.

### 6.3 Session
- **REQ-TOOL-011:** Every step output shall be stored as a `DataEntry` carrying
  `kind`, `shape`, `codec`, and origin `step_id`.
- **REQ-TOOL-012:** The session shall separate the payload `DataStore` from the
  `ResourceContainer`; resources shall never be serialized.
- **REQ-TOOL-013:** Session snapshots shall serialize `DataEntry.value` by its
  `codec`; entries without a codec shall be treated as ephemeral and omitted.
- **REQ-TOOL-014:** Resources shall be reconstructed by the container on session
  load (referenced by name in the snapshot).

### 6.4 Integration adapters
- **REQ-TOOL-015:** The core shall depend only on Pydantic; MCP/LangGraph/OpenAI
  code shall live in optional adapter modules installed via extras.
- **REQ-TOOL-016:** The MCP adapter shall export registered tools to an MCP
  server and import remote MCP tools as `ToolDefinition`s (bidirectional).
- **REQ-TOOL-017:** The LangGraph adapter shall export tools as structured tools
  and expose the planner as a graph node.
- **REQ-TOOL-018:** Adapters shall reuse `input_schema` directly (no re-derivation).

### 6.5 Agent planner
- **REQ-TOOL-019:** The planner shall return a full workflow proposal
  (`list[StepSpec]`), not a single call.
- **REQ-TOOL-020:** Every proposed step shall be validated against the tool
  `input_schema` and registry before return; invalid steps shall be flagged,
  not executed.
- **REQ-TOOL-021:** Execution shall remain under user control; proposals default
  to `execution.run = "manual"`.

## 7. Integration Adapters (design)

- `adapters/mcp.py` (extra `mcp`): `to_mcp_server(registry)` exports tools;
  `import_mcp_tools(client)` imports remote tools as `ToolDefinition`s. Resources
  are auto-hidden; the engine injects them from the `ResourceContainer`.
- `adapters/langgraph.py` (extra `langgraph`): `to_langchain_tools(registry,
  session)`; `propose_workflow_node`; optional checkpointer bridge mapping
  `thread_id ⇄ session_id` while keeping objects in `DataStore` (State holds refs).
- `adapters/openai.py`: `to_openai_tools(registry)` wraps `input_schema` as
  function-calling tools.

## 8. Agent Planner

The planner receives the operation palette (`ToolDefinition`s with
`input_schema`) plus the current workflow/session state, and returns a validated
`list[StepSpec]`. The user reviews, edits, and runs each step; the agent may
propose modifications to an existing list. The agent never bypasses validation
and never authors arbitrary Python (consistent with spec 009's tool-first model).

## 9. Serialization Rules Summary

- References always serialize (pointer only, never the object).
- Session objects serialize only when a codec exists; otherwise ephemeral.
- Resources never serialize (rebuilt by name on load).

## 10. Implementation Phases

1. **Schema foundation** — real annotations → `input_schema`/`output_schema`.
2. **Parameter kinds** — `data`/`resource` split + `Resource()` marker.
3. **Structured step config** — `StepSpec` + orchestration/execution over `ToolCall`.
4. **Data-centric session** — `DataEntry`/`DataStore`/`ResourceContainer`.
5. **Workflow introspection/trace** — DAG, `available_refs`, per-step status.
6. **Agent planner** — validated `list[StepSpec]` proposals.
7. **Integration adapters** — MCP / LangGraph / OpenAI (bidirectional, optional).
8. **Session persistence** — `Checkpointer` protocol + per-step checkpoint.

## 11. Deferred / Out of Scope

- **Cross-session long-term store** — a namespaced, cross-session/cross-user
  store (saved workflows, reusable datasets, agent memory) keyed by
  `(namespace, key)`. Deferred to a later version; when added it shall be a
  *separate* component and shall not alter the session-scoped `DataStore`.
