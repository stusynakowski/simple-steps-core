# 010 - Core Runtime Contract (simple-steps-core)

## 1. Overview

Spec [009 - Core Library Split](009-core-library-split.md) defines *where* code
lives (core library vs. application host). This spec defines the **runtime
contract** that `simple-steps-core` must expose so the application host
(`simple-steps`) can become a thin translation layer over it.

The contract is organized around three pillars that the existing application
already implements informally and that future backend work depends on:

1. **Single-step execution** — execute one step, return an opaque *reference*,
   never inline data.
2. **Session & workflow isolation** — every run owns its references; writes are
   serialized per session; saved workflows are not sessions.
3. **References, views, and metadata** — values are fetched and paginated
   through the reference, decoupled from execution.

Two supporting concerns are also specified: **progress streaming** and a
**structured error model**.

This spec assumes the tool-first production model from spec 009: operations are
the only executable units, and the formula is the durable encoding of a tool
call.

## 2. Scope

**In Scope:**
- The frozen public API surface of `simple_steps_core`.
- The single-step execution contract (inputs, outputs, semantics).
- The reference / value-store / view contract.
- The session and workflow isolation contract.
- The progress-reporting contract.
- The structured error model.
- A normative mapping from this contract to the current `simple-steps`
  `/api/*` routes (so the host refactor is unambiguous).

**Out of Scope:**
- HTTP transport shape, cookies, CORS, and SSE framing (owned by the host —
  see §12).
- Disk persistence of projects/pipelines, pack discovery directories,
  workspace/file browsing, and agent HTTP routes (host concerns per spec 009).
- Frontend changes. This contract is explicitly designed so the existing
  frontend service layer requires **no** changes (see §12).

## 3. Public API Surface

- **REQ-RT-001:** `simple_steps_core` shall expose a single documented import
  surface. Consumers shall import only from `simple_steps_core`; submodule
  paths are internal and may change.
- **REQ-RT-002:** The frozen surface shall include at least the following
  symbols, grouped by concern:

```python
from simple_steps_core import (
    # Registry / palette / formulas
    OperationRegistry, register_operation, register_orchestrators,
    OperationDefinition, OperationParam,
    parse_formula, build_formula, validate_tool_call,
    ToolCall, ValidationError,

    # Execution
    CoreEngine, Workflow, StepResult, Shape,

    # Sessions / isolation
    SessionManager, SessionContext, make_session_id,

    # Values / persistence
    CodecRegistry, StoreBackend, SnapshotError,

    # Progress
    ProgressReporter, ProgressEvent,
)
```

- **REQ-RT-003:** Symbols not in the documented surface shall be treated as
  internal. The package shall ship a `py.typed` marker and type annotations for
  the public surface.
- **REQ-RT-004:** Adding a symbol to the public surface is a minor-version
  change; removing or changing the signature of a public symbol is a
  major-version change.

## 4. Single-Step Execution Contract

### 4.1 A step is `{step_id, formula}`

- **REQ-RT-EXEC-001:** A step shall be fully described by its `step_id` and its
  `formula`. The formula is the single source of truth for the operation and
  its arguments, including references to upstream step outputs.
- **REQ-RT-EXEC-002:** The contract shall not require separate transmission of
  operation id, argument dict, input reference id, or step-id→reference map as
  distinct inputs to execution. All of these shall be derivable from the formula
  plus the session context. (The host may accept legacy fields at its boundary
  and translate them; see §12.)
- **REQ-RT-EXEC-003:** Upstream wiring shall be expressed exclusively as quoted
  step-id references inside the formula (e.g. `data="step_load"`). The execution
  context resolves a referenced `step_id` to that step's *current* reference and
  value at execution time.

### 4.2 Execution entry points

- **REQ-RT-EXEC-004:** The engine shall expose a single-step execution call of
  the form:

  ```python
  engine.execute_step(call: ToolCall, ctx: SessionContext, *,
                      step_id: str, preview: bool = False) -> StepResult
  ```

- **REQ-RT-EXEC-005:** `Workflow` shall expose `run_step(step_id)` for
  single-step execution and `arun()` for whole-workflow execution. Both shall
  route through the same engine call so their semantics cannot diverge.
- **REQ-RT-EXEC-006:** Synchronous (`run`, `run_step`) and asynchronous
  (`arun`, `arun_step`) variants shall be provided. Asynchronous variants are
  required for use inside an event loop; synchronous variants must not be called
  from within a running event loop.

### 4.3 Result shape

- **REQ-RT-EXEC-007:** A successful step shall return a `StepResult` carrying an
  opaque `ref_id` and a `Shape`, and shall **not** include the computed value
  inline.

  ```python
  class StepResult(BaseModel):
      step_id: str
      ref_id: str                 # opaque handle; value lives in the context
      status: Literal["success", "failed"]
      shape: Shape                # {kind, rows, columns, value_type}
      error: StepError | None = None
  ```

  ```python
  class Shape(BaseModel):
      kind: Literal["dataframe", "raw"]
      rows: int
      columns: list[str]
      value_type: str | None = None   # populated when kind == "raw"
  ```

- **REQ-RT-EXEC-008:** Executing a step shall bind `step_id → ref_id` in the
  session context. Re-executing the same `step_id` shall replace its binding;
  downstream references to that `step_id` shall resolve to the most recent
  reference.
- **REQ-RT-EXEC-009:** `Shape` reported at execution time shall be identical to
  the metadata returned by the view-metadata call (§6) for the same reference,
  so the host reports consistent shape from both paths.
- **REQ-RT-EXEC-010:** `preview` shall select the same execution path as a
  normal run. Preview-specific concerns (row caps, time-to-live, eviction) are
  policy the host may apply; the core shall not branch operation logic on
  `preview`.

## 5. Operation Palette & Formula Contract

- **REQ-RT-OP-001:** The registry shall expose `list_definitions() ->
  list[OperationDefinition]`, where each definition is JSON-serializable and
  sufficient for the frontend to render a form or graph node.
- **REQ-RT-OP-002:** `OperationDefinition` shall include at least:
  `operation_id`, `description`, `category`, an orchestration `type`, and
  `params` (each with `name`, `type_name`, `required`, `default`).
- **REQ-RT-OP-003:** The orchestration `type` vocabulary shall be stable and
  shall cover the modes the host currently renders: `source`, `map`, `filter`,
  `dataframe`, `expand`, `raw_output`, and `orchestrator`. Any addition is a
  minor-version change.
- **REQ-RT-OP-004:** The registry shall be frozen after startup
  (`registry.freeze()`); registration after freeze shall raise. A frozen
  registry shall be safe for concurrent reads without locks.
- **REQ-RT-OP-005:** `parse_formula(text) -> ToolCall` and `build_formula(call)
  -> str` shall be inverse operations for all valid formulas, preserving
  argument values and quoted references.
- **REQ-RT-OP-006:** `validate_tool_call(call, registry)` shall raise
  `ValidationError` for unknown operations, unknown/missing required arguments,
  and references that violate the reference grammar. Validation shall be
  callable at the host boundary before any execution or persistence.
- **REQ-RT-OP-007:** A step output is referenceable by another step only if its
  `step_id` begins with `step`. Valid reference tokens shall include
  `"step_x"`, `"step_x.field"`, and `"step_x.rows[0]"`.

## 6. References, Values, and Views

### 6.1 One value store, codec-driven

- **REQ-RT-REF-001:** The session context shall own a single value store keyed
  by reference id. The contract shall not expose separate stores for DataFrames
  versus raw values; type-specific behavior shall be provided by codecs.
- **REQ-RT-REF-002:** `CodecRegistry` shall allow registering a codec per value
  type with at least: `encode`/`decode` (for snapshot persistence), `shape`
  (row/column/kind introspection), and `to_view` (paginated, JSON-safe
  serialization). DataFrame support shall be provided as a registered codec, not
  as core special-casing.
- **REQ-RT-REF-003:** The value store shall be backed by a pluggable
  `StoreBackend` interface (e.g. in-memory, parquet-on-disk). Backend selection
  shall not change the reference contract or the view output.

### 6.2 View and metadata access

- **REQ-RT-REF-004:** The context shall expose value access decoupled from
  execution:

  ```python
  ctx.get_meta(ref_id) -> Shape
  ctx.get_view(ref_id, offset: int = 0, limit: int = 50) -> list[Cell]
  ctx.value_for_step(step_id) -> Any      # raw value, for internal/agent use
  ```

- **REQ-RT-REF-005:** `get_view` shall return a stable, JSON-safe cell shape
  suitable for the existing grid viewer. Each cell shall carry `row_id`,
  `column_id`, `value`, and `display_value`. The mapping rules shall be:
  - `dict` → one row, one cell per key;
  - `list[dict]` → N rows, one cell per (key, value) per row, with stable
    column order (first-row insertion order, then later-discovered keys);
  - `list[scalar]` → N rows, one cell per row under column `"value"`;
  - scalar / object → one 1×1 cell under column `"value"`;
  - `None` → empty list.
- **REQ-RT-REF-006:** Pagination shall slice without materializing the full
  value where the backend/codec supports it (e.g. DataFrame `iloc`).
- **REQ-RT-REF-007:** Reference ids shall be opaque to consumers. Consumers
  shall not parse a reference id to determine ownership, session, or storage
  location.

## 7. Session & Workflow Isolation

### 7.1 Sessions own references

- **REQ-RT-SESSION-001:** A `SessionContext` shall be the unit of isolation.
  References minted within a context shall be owned by that context, and the
  context shall expose `ctx.owns(ref_id) -> bool` as the authoritative ownership
  check.
- **REQ-RT-SESSION-002:** A lookup for a reference not owned by the calling
  context shall be indistinguishable from a lookup for a non-existent reference
  (no information leak about existence). Embedding a session token in the
  reference id is permitted as defense-in-depth but shall not be the authority;
  `ctx.owns()` is.
- **REQ-RT-SESSION-003:** `make_session_id(*parts)` shall produce a stable,
  collision-resistant session id from caller-supplied parts (e.g. user,
  workflow, run). The core shall not mandate any particular id source (cookie,
  header, token); that mapping is a host concern.
- **REQ-RT-SESSION-004:** A `SessionContext` shall be used by exactly one run
  and shall never be shared across users or runs.

### 7.2 Workflows are not sessions

- **REQ-RT-SESSION-005:** A saved workflow (the durable list of
  `{step_id, formula}`) shall be independent of any session. The same saved
  workflow shall be runnable by many sessions concurrently without their
  references or values colliding.
- **REQ-RT-SESSION-006:** `Workflow` shall bind to exactly one `SessionContext`
  for the duration of a run and shall resolve step references against that
  context only.

### 7.3 Concurrency

- **REQ-RT-SESSION-007:** `SessionManager` shall provide `get_or_create(sid)`
  and an async `lock(sid)` that serializes writes within a single session while
  allowing different sessions to proceed concurrently.
- **REQ-RT-SESSION-008:** `CoreEngine` shall be stateless with respect to
  session data (it takes the context as an argument) and therefore safe to share
  across requests. `OperationRegistry` shall be one-per-process and read-only
  after `freeze()`.
- **REQ-RT-SESSION-009:** Orchestrator steps (`map`/`filter`/`expand`/`collapse`)
  shall fan out concurrently within a single step while preserving step-order
  dependencies across the workflow, and shall isolate per-item failures.

## 8. Progress Reporting

- **REQ-RT-PROG-001:** Long-running operations shall be able to report progress
  through an opt-in `ProgressReporter` injected by the engine when the operation
  declares it (e.g. a `progress` keyword parameter). Operations that do not
  declare it shall be unaffected.
- **REQ-RT-PROG-002:** A `ProgressEvent` shall carry at least `current`,
  `total`, `message`, and `elapsed`. Progress shall never be carried in
  `StepResult`.
- **REQ-RT-PROG-003:** Progress channels shall be scoped by `(session_id,
  step_id)`. The context shall expose a way to subscribe to or drain progress
  events for a `(session_id, step_id)` pair so the host can bridge it to a
  transport (e.g. SSE). A subscriber for one session shall never receive another
  session's events.

## 9. Persistence Contract

- **REQ-RT-PERSIST-001:** `Workflow.to_json()` / `Workflow.from_json()` shall
  persist **structure only** (step ids, formulas, status) and shall not include
  computed payloads. This is the representation the host writes to project/
  pipeline files.
- **REQ-RT-PERSIST-002:** `Workflow.export_session_json(codecs)` /
  `Workflow.import_session_json(...)` shall persist **structure plus payloads**
  via the codec registry, enabling run resume and worker hand-off.
- **REQ-RT-PERSIST-003:** Snapshot encoding shall not use pickle. Values without
  a registered codec shall raise `SnapshotError` rather than silently dropping
  or executing arbitrary code on load.

## 10. Error Model

- **REQ-RT-ERR-001:** Argument/formula/reference problems detected before
  execution shall raise `ValidationError` (a client error, mapped by the host to
  HTTP 422).
- **REQ-RT-ERR-002:** A failure during operation execution shall be reported as
  a `StepResult` with `status="failed"` and a populated `StepError`
  (`message`, `type`, optional `traceback`). The engine shall not raise for
  expected per-step operation failures.
- **REQ-RT-ERR-003:** `StepError` shall carry enough structured detail for the
  host to render a log panel without re-deriving it: at minimum `message`,
  `type`, and (when available) `traceback`, with the failing `operation_id` and
  `step_id` recoverable from the surrounding `StepResult`.

## 11. Acceptance Criteria

- **AC-RT-001:** Given a registered operation and a session context, a host can
  execute a single step from `{step_id, formula}` alone and receive a
  `StepResult` with a reference and shape but no inline value.
- **AC-RT-002:** Re-running a step replaces its reference; a downstream step
  referencing it by `step_id` resolves to the new value.
- **AC-RT-003:** Two session contexts running the same saved workflow do not see
  each other's references; `ctx.owns()` returns false for the other's refs and
  lookups behave as not-found.
- **AC-RT-004:** `get_view` returns the documented cell shape for dict,
  list[dict], list[scalar], scalar, and None inputs, and paginates a DataFrame
  without materializing all rows.
- **AC-RT-005:** Shape reported by `execute_step` equals `get_meta` for the same
  reference.
- **AC-RT-006:** A DataFrame value round-trips through `export_session_json` /
  `import_session_json` with a registered DataFrame codec; an unencodable value
  raises `SnapshotError`.
- **AC-RT-007:** An operation that declares a `progress` parameter emits
  `ProgressEvent`s observable only within its `(session_id, step_id)` channel.
- **AC-RT-008:** The application host can implement `POST /api/run` as a thin
  handler (parse formula → validate → resolve session → `execute_step` → return
  `StepResult`) without engine, store, or formula logic of its own.

## 12. Mapping to Current `simple-steps` `/api/*` Routes

This mapping is normative: it defines what the host keeps versus what it
delegates, so the refactor preserves the existing frontend contract.

| Host route (kept, unchanged shape) | Core call(s) it delegates to |
| --- | --- |
| `GET /api/operations` | `registry.list_definitions()` |
| `POST /api/parse_formula` | `parse_formula()` |
| `POST /api/build_formula` | `build_formula()` |
| `POST /api/run` | `parse_formula` → `validate_tool_call` → `engine.execute_step` |
| `GET /api/data/{ref}` | `ctx.get_view(ref, offset, limit)` |
| `GET /api/data-meta/{ref}` | `ctx.get_meta(ref)` |
| `GET /api/progress/{step}` | subscribe to context `(session_id, step_id)` channel |

- **REQ-RT-MAP-001:** The host shall keep ownership of session **identity**
  (cookie minting in `session.py`), CORS, SSE framing, and HTTP error mapping.
  It maps the cookie value to a core `session_id` and obtains a
  `SessionContext` from `SessionManager`.
- **REQ-RT-MAP-002:** The host shall keep ownership of project/pipeline disk
  persistence (`/api/projects/**`), pack discovery directories and the
  three-tier loader (`/api/packs`, `/api/loader`, `/api/developer-packs`),
  workspace/file browsing (`/api/workspace`, `/api/files`), and agent HTTP
  routes (`/api/agent/*`). The core shall expose only the registration and
  metadata hooks these need (`register_operation`, a pack-loader entry point,
  `list_definitions`).
- **REQ-RT-MAP-003:** During migration, the host's `/api/run` may accept the
  legacy payload fields (`config`, `input_ref_id`, `step_map`, `result_store`)
  and translate them into a formula plus context configuration at the boundary,
  so the frontend needs no change. New development shall target the
  `{step_id, formula, preview}` shape.

## 13. Migration Order (host refactor)

- **REQ-RT-MIG-001:** Replace formula handling in the host with core
  `parse_formula` / `build_formula` / `validate_tool_call`; delete the
  app-local `formula_parser.py` / `safe_formula.py`.
- **REQ-RT-MIG-002:** Replace the dual `DATA_STORE` / `RAW_STORE` and the
  hand-rolled parquet cache in the host engine with a `SessionContext` value
  store plus a DataFrame codec and a parquet `StoreBackend`.
- **REQ-RT-MIG-003:** Move `_raw_to_cells` logic into a codec `to_view`; reduce
  `GET /api/data/{ref}` to a `ctx.get_view` call.
- **REQ-RT-MIG-004:** Reduce `POST /api/run` to the thin handler described in
  AC-RT-008, translating legacy fields per REQ-RT-MAP-003.
- **REQ-RT-MIG-005:** Make session isolation authoritative via `ctx.owns()`;
  keep cookie→session mapping as the only session-identity logic in the host.

## 14. Open Questions

- Should `Cell` be a core-exported type, or remain a host-side view contract
  with the core returning a more neutral page envelope?
- Should the progress channel be a pull (drain a queue) or push (async
  generator) interface at the core boundary?
- Should `result_store` (memory vs. parquet) be a per-step argument, a
  per-context default, or purely host configuration of the `StoreBackend`?
- Should structured `ToolCall` become the canonical internal save format (with
  formulas as the UI-visible projection), as raised in spec 009 §10?
