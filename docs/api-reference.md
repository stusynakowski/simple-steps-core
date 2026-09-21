# Simple Steps — Public API Reference

The programmer-facing surface: what you may import, what each name is for, and
which names are load-bearing versus incidental.

**The import rule.** Everything public comes from the top-level package:

```python
from simple_steps_core import register_tool, Resource, Workflow, Operation
```

`simple_steps_core.__all__` and `api/public.py`'s `__all__` are identical
(58 names) and are the contract. Internal modules may move as long as these
names keep their behavior, so never reach into sub-packages
(`simple_steps_core.execution.workflow`) in your own code.

**Two names break that rule** — the surfaces you actually launch:

```python
from simple_steps_core.serving import Server        # FastAPI    — needs [api]
from simple_steps_core.streamlit import Dashboard   # Streamlit  — needs [dashboard]
```

Both are deliberately outside the top level so that importing the package never
requires the optional extras. See [Change 2](#2-server-and-dashboard-are-invisible)
— this is the single most common thing new users fail to find.

---

## Tier 1 — Writing a tools file

The 90% surface. Most users never import anything else.

| Name | What it is |
|---|---|
| `register_tool` | Decorator. Turns a function into a Tool; the signature *is* the schema. |
| `Resource` | Parameter default marking an injected dependency (db, client, config). |
| `Guardrails` | Per-tool policy: `usage`, `rules`, `read_only`, `destructive`, `requires_confirmation`, `arguments`. |
| `ArgGuardrail` | Per-argument constraint: `enum`, `minimum`, `maximum`, `min_length`, `max_length`, `pattern`, `note`. |
| `REGISTRY` | The process-wide default registry `@register_tool` writes into. |

```python
from simple_steps_core import ArgGuardrail, Guardrails, Resource, register_tool

@register_tool("charge", description="Charge an amount.", guardrails=Guardrails(
    destructive=True,
    arguments={"amount": ArgGuardrail(minimum=1, maximum=1000)},
))
def charge(amount: int, billing=Resource()) -> str:
    return billing.charge(amount)
```

Rules that bite:

- **Annotate every parameter and the return type.** An unannotated param degrades
  to `Any`; an unannotated return yields `output_schema=None`, which silently
  disables reference type-checking *and* leaves the dashboard unable to say what
  a staged step will produce.
- **Tools are keyword-only at call time.** The `Tool` wrapper accepts `**kwargs`
  only.
- `@register_tool` returns a **dual-mode `Tool`**, not your function:
  `charge(amount=5)` builds a deferred `ToolCall`; `charge.run(amount=5)` executes
  immediately. A tool therefore cannot call another tool by name — wire them with
  references instead.
- `async def` is detected automatically; sync tools run off-loop via
  `asyncio.to_thread`.

### Optional per-tool UI

| Name | What it is |
|---|---|
| `ToolUI` | A tool's `{target: view}` map (`operation.ui`). |
| `ToolUIView` | One target's lifecycle views: `input`, `result`, or exclusive `full`. |
| `build_default_ui` | Auto-builds a prefab declaration from the input schema. |

```python
ui={"streamlit": {"input": render_form, "result": render_result}}
```

- `input(st, *, key, defaults) -> dict` — draw widgets, return arguments.
- `result(st, *, key, result) -> None` — `result` is the `StepOutput`
  (`result.value` plus timing fields).
- A composed view **must** define `input`; a result-only view raises `ValueError`.
  See [Change 5](#5-result-only-ui-views-are-rejected).

---

## Tier 2 — Building and running workflows

| Name | What it is |
|---|---|
| `Workflow` | Ordered steps with a dict-like API, run against one session. |
| `Operation` | A Tool *equipped* with arguments + orchestration + execution config. |
| `OrchestrationConfig` | Breadth: `mode`, `over`, `item_arg`, `concurrency`, `on_error`, `retries`, `initial`. |
| `Step` | `Operation + Data` — the spec plus its status/output. |
| `StepStatus` | `PENDING` / `RUNNING` / `COMPLETED` / `FAILED`. |
| `StepOutput` | `value`, `kind`, `ref`, `started_at`, `ended_at`, `duration`. |
| `StepError`, `StepResult` | Error record; engine-level step result. |
| `MapResult`, `ItemOutcome` | Partial-failure-aware fan-out result: `.ok`, `.failed`, `.outcomes`. |
| `Stage` | A computed groupby view over steps sharing a `stage` tag. |
| `CoreEngine` | Executes a `ToolCall` against a `SessionContext`. |
| `App`, `AppConfig`, `Session` | The facade: App → Session → Workflow. |
| `SummaryTable` | What every `info()` returns — HTML in notebooks, aligned text in logs. |

```python
wf = session.workflow("demo")
wf.add(Operation(step_id="step1", name="make_list", stage="load", arguments={"n": 5}))
wf.add(Operation(
    step_id="step2", name="scale", stage="transform",
    orchestration=OrchestrationConfig(mode="map", over="step1", concurrency=4),
))
wf.validate()     # preflight -> SummaryTable
wf.run()          # or: await wf.arun()
wf.info(); wf.preview("step2")
```

### `Workflow` surface

| Group | Methods |
|---|---|
| Author | `add`, `__setitem__`, `__getitem__`, `__delitem__`, `__contains__`, `__len__`, `steps` |
| Run (sync) | `run`, `run_step`, `run_stage`, `run_by_stages` |
| Run (async) | `arun`, `arun_step`, `arun_stage`, `arun_by_stages` |
| Inspect | `info`, `preview`, `validate`, `missing_resources` |
| Stages | `stage`, `stages`, `stage_views`, `steps_in_stage` |
| Persist | `to_json` / `from_json`, `export_session*` / `import_session*` |

**Sync vs async is not a preference.** `CoreEngine.execute()` refuses to nest
inside a running event loop, so any async or orchestrated step raises under
FastAPI, Streamlit, or a notebook kernel. Use `arun`/`aexecute` there, `run` in
plain scripts.

### Execution configs

| Name | Scope |
|---|---|
| `StepExecutionConfig` | `run`, `timeout`, `retries`, `cache` |
| `StageExecutionConfig` | `steps`, `concurrency`, `on_step_error`, `run` |
| `WorkflowExecutionConfig` | `stages`, `on_stage_error`, `run` |

They are orthogonal and isolated — no inheritance, no overriding.
**They are also inert:** nothing in the runtime reads them. See
[Change 1](#1-execution-configs-are-declared-but-never-honored).

---

## Tier 3 — Hosting and embedding

For building your own surface rather than using `Server` / `Dashboard`.

| Group | Names |
|---|---|
| Registry | `ToolRegistry`, `Tool`, `ToolDefinition`, `ToolParam`, `RegistryFrozenError`, `register_orchestrators` |
| Calls | `ToolCall`, `ExecutionHandle` |
| Validation | `ValidationError`, `validate_tool_call`, `check_reference_types` |
| References | `is_reference`, `split_reference`, `ReferenceResolver` |
| Sessions | `SessionManager`, `make_session_id`, `SessionContext` |
| Payload store | `DataStore`, `DataEntry`, `Cell`, `Shape` |
| Resources | `ResourceContainer`, `ResourceMissingError`, `ResourceCheck` |

Multi-user serving: give every logical run its own `SessionContext` via
`SessionManager.get_or_create(make_session_id(user, workflow, run))`, and hold
`manager.lock(session_id)` around mutations.

### Snapshot / persistence

`SessionSnapshot`, `CodecRegistry`, `DEFAULT_CODECS`, `SnapshotError`,
`PayloadEnvelope`, `StoreBackend`, `InMemoryStore`.

Resources are **never** serialized; on load they are rebuilt from their factories.

---

## The two surfaces

Both read the **same tools file**: a script that registers tools plus optional
module-level `CONFIG` and `RESOURCES` dicts. The bottom line picks the surface.

```python
CONFIG = {"title": "My Tools", "port": 8000}
RESOURCES = {"db": connect}       # callable -> factory, else an instance

if __name__ == "__main__":
    Server().run()                # or Dashboard().run()
```

| | `Server` (FastAPI) | `Dashboard` (Streamlit) |
|---|---|---|
| Extra | `pip install -e ".[api]"` | `pip install -e ".[dashboard]"` |
| Routes / UI | `GET /tools`, `POST /call`, `POST /run` | Step Manager: palette, forms, orchestration, JSON load/save |
| State | **Stateless** — references resolve only within one `/run` body | One `Workflow` per browser session |
| Registry | `freeze=True` by default | not frozen |

---

# What to change

Ranked by how much damage each does. Every item below was reproduced against
the current tree.

## 1. Execution configs are declared but never honored

`StepExecutionConfig`, `StageExecutionConfig` and `WorkflowExecutionConfig` are
exported, documented, serialized, and surfaced in the dashboard's "Runtime
settings" tab — and no runner reads them.

```python
wf["step1"] = Operation(step_id="step1", name="slow", arguments={"x": 1},
                        execution=StepExecutionConfig(retries=3, timeout=0.001))
wf.run()
# attempts made: 1   (retries=3 implies 4; timeout never applied)
```

A user who sets `retries=3` has every reason to believe retries happen. This is
the worst kind of API defect: it fails silently and looks like a feature.

**Options** — (a) implement them in `run_step`/`arun_step`, (b) rename to
`*AuthoringIntent` and document that hosts must enforce, or (c) drop them from
`__all__` until implemented. Anything but the current state.

## 2. `Server` and `Dashboard` are invisible

The two things every user ultimately needs are the two things not in
`__all__`. `from simple_steps_core import Dashboard` fails, and nothing in the
top-level namespace hints at where to look.

The lazy-import constraint is real, but solvable with a module-level
`__getattr__` (PEP 562) that imports on first attribute access and raises a
helpful error naming the missing extra:

```python
def __getattr__(name):
    if name == "Dashboard":
        from .streamlit import Dashboard
        return Dashboard
    raise AttributeError(name)
```

## 3. Non-`step*` ids silently corrupt data

A reference token must match `^step[\w-]*(?:\.\w+|\[...\])*$`. Anything else is
treated as a literal — so a step named `load_csv` can never be referenced, and
the downstream tool receives the **string** `"load_csv"` instead of the data:

```python
wf["load_csv"] = Operation(step_id="load_csv", name="mk", arguments={})
wf["step2"]    = Operation(step_id="step2", name="take", arguments={"rows": "load_csv"})
wf.run()
wf["step2"].output.value   # 'load_csv'  — the string, not [1, 2, 3]
```

**And `validate()` reports `✓ ok` on exactly this workflow.** The preflight only
checks tokens that already *look* like references, so the one case that needs
catching is the one it misses. The mirror bug: a legitimate string value like
`"stepfather"` *is* read as a reference (`is_reference("stepfather") is True`).

**Options** — make the reference an explicit type (`Ref("load_csv")`) instead of
inferring from string shape, which removes both failure modes at once; or, as a
cheap stopgap, have `validate()` warn when an argument string exactly matches a
known step id but isn't step-shaped.

## 4. `Workflow.run()` aborts the whole run on one failure

`run_step` records the failure on the step **and re-raises**, so `run()` stops at
the first bad step. The comment says it captures the error "rather than raising
blindly" — it does both, which makes the intent unclear.

`WorkflowExecutionConfig.on_stage_error` exists to express exactly this choice
but is inert (see Change 1). Decide which is authoritative.

## 5. Result-only UI views are rejected

`ToolUIView.__post_init__` requires a composed view to define `input`, so a tool
that wants the auto-generated form *plus* a custom result view cannot say so —
it must hand-write an input view it didn't want, which also costs it the
dashboard's reference-binding picker.

The constraint is deliberate ([test_ui.py:146](../tests/unit/test_ui.py#L146)),
and the `full`-vs-composed exclusion it sits next to is sound. But the
`input`-required half has no such justification: the host already falls back to
the auto-form when `input` is absent.

## 6. The `type=` annotation contradicts the model

`ToolDefinition.type` accepts seven values (`source | map | filter | dataframe |
expand | raw_output | orchestrator`), but `ToolRegistry.register` and
`register_tool` annotate the parameter as only three:

```python
type: Literal["source", "dataframe", "raw_output"] = "raw_output"
```

`Literal` isn't enforced at runtime, so `register("x", fn, type="map")` is
accepted and yields `definition.type == "map"`. The cost is entirely static: a
type checker or editor flags four legitimate values as errors, so the annotation
actively misleads about what the API supports.

Widen the decorator's `Literal` to match the model (or narrow the model if four
of those states are genuinely internal).

## 7. Two serialization pairs with no stated rule

`to_json` / `from_json` (structure only) sit beside `export_session_json` /
`import_session_json` (structure + payloads). The names don't say which drops
your data. Suggest `export_structure_json` vs `export_session_json`, or one
method with a `payloads: bool` flag.

## 8. Four exports nothing uses

`InMemoryStore`, `PayloadEnvelope`, `StoreBackend`, `ResourceCheck` appear zero
times outside `src/` — no doc, test, example, or notebook. `StoreBackend` and
`InMemoryStore` are a real extension point worth keeping and documenting;
`PayloadEnvelope` and `ResourceCheck` are return/detail types that leak
internals. Decide per name rather than exporting all four by default.

## 9. Declarative guardrails bind nothing

`usage`, `rules`, `read_only`, `destructive` and `requires_confirmation` are
never read by the runtime — only `arguments` is enforced. A tool marked
`requires_confirmation=True` runs without confirmation unless the host
implements the gate. Worth stating in the class docstring, since the field names
read like promises.

---

## Cross-cutting

Changes 1, 4 and 9 are one theme: **the model layer declares intent the
execution layer ignores.** Changes 2 and 8 are one theme: **`__all__` is not
tiered** — 57 names arrive flat, with the four dead ones present and the two
essential ones absent. Fixing the tiering is cheap and would make the surface
teach itself.
