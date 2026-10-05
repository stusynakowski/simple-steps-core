# Migration determination — remove the engine, consolidate on the grid model

**As of 2026-10-05. Analysis only — no code changed.** Companion to
[contradictions.md](contradictions.md). Answers: *what must be removed,
consolidated, and fixed to retire the engine model and run everything on the
grid model.*

---

## 0. Reframe the size of it first

"Migrate to grid and delete the engine" sounds like a swap. It is not, because
**`grid.py` is only the core** — the authoring surface (tools, modifiers,
`Operation`, `Step`, `Workflow`, `Output`) plus *synchronous, in-memory*
execution and JSON export. It imports nothing but stdlib + pandas
([grid.py:28-40](../src/simple_steps_core/grid.py#L28)).

Everything that makes the library an *application* lives only on the engine and
has **no grid equivalent today**:

| capability | engine home | in grid? |
|---|---|---|
| payload store / `ref` indirection | [execution/context.py](../src/simple_steps_core/execution/context.py), [data_store.py](../src/simple_steps_core/execution/data_store.py) | **no** — payloads sit inline on each `Step` (status.md D5) |
| resources / dependency injection | [operations/dependencies.py](../src/simple_steps_core/operations/dependencies.py), [execution/resources.py](../src/simple_steps_core/execution/resources.py), [resource_spec.py](../src/simple_steps_core/operations/resource_spec.py) | **no** |
| media assets | [domain/media.py](../src/simple_steps_core/domain/media.py) | **no** |
| lazy/versioned sources | [domain/collections.py](../src/simple_steps_core/domain/collections.py) | partial — grid has a `source` verb but no `Collection` |
| guardrails · UI · schema | [operations/ui.py](../src/simple_steps_core/operations/ui.py), [schema.py](../src/simple_steps_core/operations/schema.py), `Guardrails` in models.py | **no** — grid `@tool` carries id + strict typing only |
| async + timeout/concurrency/cache/gate | [execution/engine.py](../src/simple_steps_core/execution/engine.py) | **no** — grid is sync; `timeout` is inert (status.md L1/B5) |
| session persistence / snapshots | [execution/session_io.py](../src/simple_steps_core/execution/session_io.py) | partial — grid has `to_dict`/`from_json`, no codecs/payload envelopes |
| multi-user sessions | [execution/session_manager.py](../src/simple_steps_core/execution/session_manager.py) | **no** |
| `App` / `Session` facade | [app.py](../src/simple_steps_core/app.py) | **no** — built on engine |
| HTTP `Server` | [serving.py](../src/simple_steps_core/serving.py) | **no** — built on engine |
| agent planner | [agent/](../src/simple_steps_core/agent/) | emits engine `ToolCall` |

So the migration is three streams, in this order of difficulty:

1. **Fix/build** — grow the grid core until it can host the application layer.
2. **Consolidate** — merge the duplicated primitives (registry, refs, validation,
   session IO) so there is one of each.
3. **Remove** — delete the engine's orchestration and re-point the consumers.

You cannot start with "remove." Deleting the engine today takes `App`, `Server`,
resources, media, snapshots and the agent with it.

---

## 1. REMOVE — pure engine orchestration, deleted outright

These have a grid replacement already and exist only to serve the inverted
"orchestrator-as-a-tool" design the grid model was built to end
([status.md §6](status.md)):

| delete | from | grid replacement |
|---|---|---|
| `ORCHESTRATORS`, `register_orchestrators`, `orchestration_resource`, the `orchestration-map/filter/expand/collapse/group` tools | [operations/orchestrations.py](../src/simple_steps_core/operations/orchestrations.py) (whole file) | `mod.map/filter/…` modifiers |
| `orchestrator_id`, `ORCHESTRATION_RESOURCE`, `Tool.is_orchestrator`, the higher-order branches in `CoreEngine.aexecute` | models.py, [registry.py](../src/simple_steps_core/operations/registry.py), engine.py | folded into `compile_operation` |
| `OrchestrationConfig`, `StepExecutionConfig`, `StageExecutionConfig`, `WorkflowExecutionConfig` | [domain/models.py:234-](../src/simple_steps_core/domain/models.py#L234) | `Modifier` stack (shape verb + execution modifiers) |
| `MapResult`, `ItemOutcome` | models.py | `Output.data` + `Output.ledger` |
| `Group`, `Groups` | [domain/collections.py:154-](../src/simple_steps_core/domain/collections.py#L154) | `group` adds a key column; no nesting |
| engine `Operation` (StepSpec), `Step`, `Data`, `StepStatus`, `StepOutput`, `StepError`, `StepResult` | models.py | grid `Operation`/`Step`/`Output` |
| engine `Workflow`, `Stage`, `stage_config` | [execution/workflow.py](../src/simple_steps_core/execution/workflow.py) | grid `Workflow` (stages become a modifier/meta concern) |

**Watch-out:** `config-isolation.md` describes the two-config split as a shipped
feature. When `OrchestrationConfig`/`StepExecutionConfig` are deleted, that doc
becomes historical — mark it so, do not silently leave it describing removed
classes (contradictions.md C7).

---

## 2. CONSOLIDATE — two of the same thing collapse into one

### 2a. The tool registry — the make-or-break consolidation
There are **two complete, unrelated tool systems**:

| | engine | grid |
|---|---|---|
| decorator | `@register_tool` | `@tool` |
| store | `REGISTRY` / `ToolRegistry` | module-level `TOOLS` + `BUILTIN_TOOLS` |
| wrapper | `Tool` + `ToolDefinition` + `ToolParam` | `ToolHandle` + `catalog()` entry |
| carries | guardrails, UI, JSON schema, resource binding, category, async flag | id + strict-typing annotations only |
| resolution | `registry.get_operation(id)` | `{**BUILTIN_TOOLS, **TOOLS, **tools}` dict ([grid.py:1427](../src/simple_steps_core/grid.py#L1427)) |

Nothing bridges them. **Decide one direction before anything else**, because every
other consumer (forms, agent, frontend, resource binding) reads the *engine's*
`ToolDefinition`. Recommended: grid's `@tool`/`ToolHandle` **absorbs** the
engine's contract — gains `guardrails=`, `ui=`, resource params, and produces a
`ToolDefinition`-shaped `catalog()` entry — so the frontend/agent surface
survives unchanged. The alternative (grid keeps reaching into `REGISTRY`) keeps
two stores alive and defeats the migration.

### 2b. The colliding nouns
`Workflow`, `Operation`, `Step` exist in both and are exported bare as the
*engine's* ([api/public.py](../src/simple_steps_core/api/public.py#L44),
contradictions.md L3). Consolidation = grid wins, engine versions deleted, and
the dual export disappears so `from simple_steps_core import Operation` can only
mean one thing.

### 2c. References
Engine refs are `^step[\w-]*…` string tokens resolved by
[execution/resolver.py](../src/simple_steps_core/execution/resolver.py) +
[domain/references.py](../src/simple_steps_core/domain/references.py). Grid uses
`StepRef` objects carrying workflow provenance (status.md §2). Consolidate to the
grid form; delete the resolver's engine-ref machinery. Keep the accessor-path
syntax (`step2.ok`, `step2[0]`) — map it onto `Output` (`.ok`/`.failed`/`.ledger`
per shape-algebra §5).

### 2d. Validation
Engine `validate_tool_call` / `check_reference_types`
([operations/validation.py](../src/simple_steps_core/operations/validation.py))
vs grid `check()` / `declaration_problems` / `annotation_problems`. Consolidate to
grid's `check()` (it already covers unknown tools, bad modifier params, dangling
refs, cycles, dtype/type mismatches). `Workflow.validate()` → grid's equivalent.

### 2e. Session IO — consolidate *into* grid, don't delete
[execution/session_io.py](../src/simple_steps_core/execution/session_io.py)
(`SessionSnapshot`, `PayloadEnvelope`, `CodecRegistry`, `DEFAULT_CODECS`,
`StoreBackend`) is the no-auto-pickle, codec-based persistence grid still lacks.
Grid's flat `to_dict`/`from_json` only serializes structure. **Port the codec +
payload-store machinery onto grid's `Output.ref`** (see §3.1) rather than
re-inventing it.

---

## 3. FIX / BUILD — gaps grid must close before the engine can go

Ordered by how much else is blocked on them.

### 3.1 Recursive `ToolCall` — the unblocker (status.md §6, shape-algebra §10)
A modifier stack can't serialize or execute until a call can contain a call.
**Nothing else lands before this.** It is the load-bearing first commit.

### 3.2 Payload store / `Output.ref` (status.md D5)
Today every `Step` holds its grid inline, so two steps reading one grid each copy
it, and storage can't move off-heap. Adding `Output.ref` + a `StoreBackend`
(reuse §2e) is the prerequisite for: downstream references by `ref`, snapshots,
`cache` (B5), and resource-sharing across sessions.

### 3.3 Resources / dependency injection
Grid tools cannot declare a `Resource()` param. Port
[dependencies.py](../src/simple_steps_core/operations/dependencies.py) +
[resources.py](../src/simple_steps_core/execution/resources.py) +
[resource_spec.py](../src/simple_steps_core/operations/resource_spec.py) so
`compile_operation` injects non-data params (the engine's `_inject_resources`
equivalent). Required by `App`, every `ResourceSpec` tool, and media tools.

### 3.4 Media + collections as grid sources
Port [media.py](../src/simple_steps_core/domain/media.py) and keep
`Collection`/`ListCollection` from collections.py (drop only `Group`/`Groups`).
The grid `source` verb must accept a `Collection`/`MediaAsset` and iterate it
lazily — the behavior the skill documents for the engine today.

### 3.5 Guardrails · UI · schema on grid tools
Fold into §2a. Without this the dashboard forms, the prefab/React UI, the agent's
argument bounds, and `info()` all lose their data source.

### 3.6 Async + real `timeout` / `concurrency` / `cache` / `gate` (status.md B5)
Grid executes synchronously; `timeout` is recorded but inert. The `Server` and any
large fan-out need the async engine's behavior reimplemented as execution
modifiers over the grid run loop.

### 3.7 Session persistence + `SessionManager`
After §2e + §3.2, re-home `SessionManager` + `make_session_id` (per-user isolation,
per-session lock) onto grid `Workflow`s.

### 3.8 Multi-input / merge verbs (status.md D1, P1-P5)
Grid reads exactly one upstream per step. Real pipelines need `stack` / `zip` /
`join` (and maybe `broadcast`). This is genuine design work (P1-P5 undecided).
**Do not block the migration on it** — it is additive and can land after the
engine is gone.

---

## 4. RE-POINT — consumers that must move onto grid

| consumer | today | change |
|---|---|---|
| [app.py](../src/simple_steps_core/app.py) (`App`/`AppConfig`/`Session`) | engine `CoreEngine`, `Workflow`, `ResourceContainer` | rebuild on grid `Workflow` + ported resources |
| [serving.py](../src/simple_steps_core/serving.py) (`Server`) | engine `Workflow.run_step`, `Operation`, `ToolCall` | grid run loop; `/run` body becomes a modifier-stack `Operation` |
| [agent/](../src/simple_steps_core/agent/) | `suggested_tool_call: ToolCall` | emit a grid `Operation` (tool + modifier stack) |
| [api/decorators.py](../src/simple_steps_core/api/decorators.py), [public.py](../src/simple_steps_core/api/public.py) | re-export engine names | export grid names; drop engine-only symbols |
| [loader.py](../src/simple_steps_core/loader.py) | runs `@register_tool` onto `REGISTRY` | run grid `@tool` onto the unified store |
| examples: [api_server](../examples/api_server/), [simple_server](../examples/simple_server/), [simple_steps_backend](../examples/simple_steps_backend/) | all engine | rewrite against grid; `types.ts` re-modelled (contradictions.md C11) |
| notebooks: [tutorial_notebook](../tutorial_notebook/), [walkthrough](../examples/simple_steps_core_walkthrough.ipynb) | engine (walkthrough already errors) | rewrite |
| docs | half engine, half grid | flip every engine doc to grid; retire config-isolation.md |

### Tests
`tests/unit/test_grid.py` (214) stays. The rest of the suite (~194) is engine
behavior: `test_orchestrations`, `test_step_spec`, `test_operation_modes`,
`test_tabular`, `test_references`, `test_reference_types`, `test_resolver`,
`test_session_io`, `test_session_manager`, `test_resource_binding`, `test_ui`,
`test_validation`, `test_media`, `test_collections`, `test_guardrails`,
`test_registry`, `test_runtime_contract`, `integration/test_engine_execute`,
`integration/test_workflow`. Each is **rewrite-against-grid or delete** — budget
for this explicitly; it is where the behavior guarantees get re-pinned.

---

## 5. Decisions to make *before* writing code

1. **Registry direction (§2a).** Does grid `@tool` absorb `ToolDefinition`
   (recommended), or does grid keep reading `REGISTRY`? Everything downstream
   depends on this answer.
2. **Payload store backend (§3.2).** Interface for `StoreBackend` — in-memory
   now, disk/Redis later. Reuse session_io's `StoreBackend` or define fresh?
3. **Guardrail enforcement.** Engine enforces only `arguments` bounds; the rest
   is declarative. Keep that contract on grid or tighten it?
4. **Multi-input scope (§3.8).** Confirm it is explicitly *out* of the migration
   so it can't expand the critical path.
5. **Stages.** The engine's `stage`/`Stage`/`stage_config` has no grid analog —
   decide if stages become a modifier, a `meta` tag, or are dropped.

---

## 6. Suggested sequence (critical path)

```
P0  recursive ToolCall …………………………………  unblocks everything (§3.1)
P1  Output.ref + payload store ……………………  unblocks refs, snapshots, cache (§3.2, §2e)
P2  unify the registry …………………………………  guardrails/ui/schema/resources onto @tool (§2a, §3.5)
P3  resources + media + collections ……………  as grid sources with injection (§3.3, §3.4)
P4  async + timeout/concurrency/cache/gate …  real execution modifiers (§3.6)
P5  session_io codecs + SessionManager ………  persistence + multi-user on grid (§3.7)
P6  re-point App/Server/agent/api/loader ……  + rewrite examples/notebooks/docs/tests (§4)
P7  DELETE engine orchestration + dual exports  (§1, §2b-2d) and drop build/ copy
P8  multi-input verbs (stack/zip/join) …………  additive, after the engine is gone (§3.8)
```

P0-P5 grow the core; the engine keeps running untouched the whole time (grid is
standalone, so the two coexist with zero risk until P6). **P6 is the only
irreversible step** — everything before it is purely additive, which is what
makes this migration safe to do incrementally rather than as one big cut.

### The one-line summary
Delete **orchestration-as-a-tool** (§1); merge the **two registries, two
`Workflow`s, two ref systems, two validators** into one each (§2); and build the
**payload store, resource injection, media, async, and persistence** that the
grid core still lacks (§3) — *then* the engine can be removed and every
application surface re-pointed (§4).
