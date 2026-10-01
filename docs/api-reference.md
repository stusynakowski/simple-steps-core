# Simple Steps — Public API Reference

> **Status: describes the engine as it is today.** The object model is converging
> on a single modifier stack — see [object-model.md](object-model.md) for what is
> changing and [shape-algebra.md](shape-algebra.md) for why. The engine has not
> moved yet, so everything here remains accurate.

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

**One name breaks that rule** — the surface you actually launch:

```python
from simple_steps_core.serving import Server        # FastAPI — needs [api]
```

It is deliberately outside the top level so that importing the package never
requires the optional extras.

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
  disables reference type-checking *and* leaves a frontend unable to say what
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
ui={"react": {"input": render_form, "result": render_result}}
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
| `OrchestrationConfig` | **Shape only**: `mode`, `over`, `item_arg`, `initial`. |
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
FastAPI or a notebook kernel. Use `arun`/`aexecute` there, `run` in
plain scripts.

### Execution configs

| Name | Scope |
|---|---|
| `StepExecutionConfig` | `run`, `timeout`, `retries`, `cache`, `concurrency`, `on_item_error` |
| `StageExecutionConfig` | `steps`, `concurrency`, `on_step_error`, `run` |
| `WorkflowExecutionConfig` | `stages`, `on_stage_error`, `run` |

They are isolated on both axes: **by scope** (no inheritance, no overriding) and
**by concern** — `OrchestrationConfig` holds shape, `StepExecutionConfig` holds
conduct, and they share zero fields. All four set `extra="forbid"`, so a field
passed to the wrong config raises. Full map:
[config-isolation.md](config-isolation.md).

`concurrency`, `on_item_error` and `retries` are honored for fan-out modes.
`retries` on a `single` step, plus `run`, `timeout` and `cache`, are still
inert — see [Change 1](#1-execution-configs-are-declared-but-never-honored).

---

## Tier 3 — Hosting and embedding

For building your own surface rather than using `Server`.

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

## The surface

`Server` reads a **tools file**: a script that registers tools plus optional
module-level `CONFIG` and `RESOURCES` dicts.

```python
CONFIG = {"title": "My Tools", "port": 8000}
RESOURCES = {"db": connect}       # callable -> factory, else an instance

if __name__ == "__main__":
    Server().run()
```

| | `Server` (FastAPI) |
|---|---|
| Extra | `pip install -e ".[api]"` |
| Routes | `GET /tools`, `POST /call`, `POST /run` |
| State | **Stateless** — references resolve only within one `/run` body |
| Registry | `freeze=True` by default |

This library is backend-only: it ships no UI. A frontend consumes the tool
contract over HTTP — see [react-api.md](react-api.md).

---

## Tier 4 — the grid model (`simple_steps_core.grid`)

> **Separate surface, separate import.** Three names shadow the engine's —
> `Workflow`, `Operation`, `Step` — so import the module, never the names:
> `from simple_steps_core import grid`. Design in
> [shape-algebra.md](shape-algebra.md), how it is arranged in
> [grid-model.md](grid-model.md), how to write tools for it in
> [writing-tools.md](writing-tools.md), and the grammar for declaring a step in
> [defining-operations.md](defining-operations.md).

### Authoring

| Name | Is |
|---|---|
| `tool` | the decorator; registers into `TOOLS`. `tool(id=…, strict=…)` |
| `STRICT_TYPES` | module flag: require a full annotation on every tool. Default `False` |
| `annotation_problems(fn)` | what is unannotated about a function; `[]` when fully typed |
| `op(tool_id, **literals)` | an Operation naming a tool by id |
| `mod` | modifier constructors — `mod.map(over=…)`, `mod.retry(times=…)` |
| `Workflow` | ordered `Step`s and nothing else |
| `Step` | an `Operation` **and** an `Output`, both from declaration |
| `StepRef` | what `wf["id"]` returns; wiring a reference builds the step |

Two calling rules, and no third: **brackets decorate, parens apply.** Applying
to data runs; applying to a `StepRef` wires. `bind(**literals)` fixes constants.

The canonical form puts the verb in brackets and the data in the call position —
`score[mod.map(name="pts")](wf["raw"])`. `over=` is the same step written the
other way round and is what gets stored; the two are equal and export identically.

### The tool registries

| Name | Is |
|---|---|
| `BUILTIN_TOOLS` | `identity gather count total first last` — system, **protected** |
| `TOOLS` | whatever `@tool` declared |
| `DEFAULT_TOOL` | verb → the builtin a bare modifier resolves to |
| `catalog()` / `tool_entry()` | palette entries: `tool_id`, `description`, `origin`, `params` (each with `name`, `required`, `default`, **`type`**), **`returns`**, **`typed`**, `takes_whole_row` |

`@tool` **refuses** a name that collides with a builtin: the shape verbs resolve
`identity` and `gather` by name, so shadowing one would quietly change what
`select`, `drop` or a bare `collapse` does.

A bare shape verb is a complete step — `wf["all"] = mod.collapse(over=ref)`
applies `gather`. A bare *execution* modifier is refused.

### The modifier vocabulary

| Name | Is |
|---|---|
| `MODIFIERS` | **the one table** — every kind, its class, its applier |
| `ModifierKind` | one entry: `name`, `cls` (`shape` / `execution`), `apply` |
| `SHAPE_VERBS`, `DECORATORS`, `is_shape` | derived from it; never written twice |
| `ROWS_RULE` | §3's rows column as data — what staging folds |
| `DEFAULT_PAYLOAD`, `CARRIES_COLUMNS` | which column a verb writes; whose it keeps |

Current verbs: `source map filter select drop widen group expand collapse sweep`
(shape) · `retry timeout` (execution).

### Declaring, staging, running

| Name | Is |
|---|---|
| `check(operation, workflow, step_id)` | every problem knowable without running; **never raises** |
| ↳ what it refuses | unknown tool/modifier · a ref read from **another `Workflow`** · `over` dangling, self-referential or circular · more than one shape verb · a tool on `source`/`select`/`drop` · `select`/`drop` naming absent columns · a bound literal the signature rejects · a required value the upstream lacks · **a declared type the literal or upstream dtype contradicts** |
| `stage(...)` | the `Output` a step has before it runs |
| `infer_verb(fn, upstream, literals)` | which verb a tool wants, and why |
| `predicted_columns(output)` | the columns a step will have, **in order** |
| `Workflow.pending / run / run_all` | what must run first; run one; run the chain |
| `compile_operation(operation, tools)` | **the boundary** — data becomes behaviour |

### Output and payloads

| Name | Is |
|---|---|
| `Output` | `data` + `ledger` + `meta`; `view()`, `ok`, `failed`, `values`, `item()` |
| `Output.shape` / `.form` | `(rows, cols)` — pandas' meaning / the cardinality class |
| `PAYLOAD`, `LEDGER_COLUMNS` | `"value"`; `status error attempts seconds unit` |
| `to_json` / `to_session_json` / `from_json` | light export (structure) / full (plus payloads). Frame payloads carry their **dtypes**, which JSON itself cannot express |
| `PayloadError` | raised rather than writing a payload that cannot load back |

### The implementation layer

Public, but not what you reach for when wiring a workflow. `MODIFIERS` wires
these up; `mod.map(over=…)` is the authoring form.

| Name | Is |
|---|---|
| `map_ filter_ select_ drop_ widen_ group_ collapse_ expand_ sweep_ source_` | the verbs themselves — callable directly on a frame, with no Workflow, which is how they are unit-tested |
| `grid(value)` / `rows(value)` | lift a value into an `Output` / coerce one into a frame of rows |
| `Modifier` | one stack entry: `kind` + `params`, with `cls` and `is_shape` read from `MODIFIERS`. `params` may hold a `StepRef`, which knows its `Workflow`; it flattens to a bare id in `Operation.to_dict()`. `__eq__` compares params flattened, so naming a step either way is the same modifier |
| `ToolHandle` | what `@tool` returns — the function, an id, `bind`, and `__getitem__` |
| `is_identity(fn)` | recognizes `identity` through the argument adapter; how `source`/`select`/`drop` enforce "no tool" |

Fifty-two exported names is a lot for a submodule to absorb, and roughly a
quarter of them are this layer. Worth trimming once the authoring surface stops
moving.

### Not yet in this surface

Public names only. [status.md](status.md) is the consolidated review, with the
blocker and rough size for each.

| | status |
|---|---|
| `rename`, `sort`, `distinct` | proposed verbs, not built |
| `slice` / `head` / `limit` | proposed. **Row position is unreachable today** — a tool cannot see its index, even with `**row`, so positional selection is not expressible at all. Workaround: `df.reset_index(names="row_no")`, then `filter` |
| `cache`, `gate`, `concurrency` | **promised in §1.1, missing from `MODIFIERS`** |
| `join` | needs multi-upstream references first. A step reads **exactly one** upstream: two `over`s are two shape verbs and are refused |
| source schemas | nothing declares a `source` step's column types, so they are the only dtypes no annotation governs — and the ones a replaced source could silently change |
| `Workflow.adopt` / namespacing | composing two workflows forces a rename. Mechanical on the export (rename ids, rewrite `over`), but not in the library |
| `colmap` and the column-as-unit family | blocked on §5 — `axis="columns"` raises |
| literal steps via `ast.literal_eval` | decided (one cell), not built |
| `AppConfig` | specified in [app-config.md](app-config.md), not built |
| `Output.ref` | no payload store yet; payloads sit inline on the Step |

---

# What to change

Ranked by how much damage each does. Every item below was reproduced against
the current tree.

## 1. Execution configs are only partly honored

*Partly fixed.* `concurrency`, `on_item_error` and `retries` now live on
`StepExecutionConfig` and are honored whenever a step fans out — the
orchestrator implements them. What remains inert:

| Field | Status |
|---|---|
| `retries` | works fanned out; **ignored when `mode="single"`** |
| `timeout` | ignored everywhere |
| `cache` | ignored everywhere |
| `run` | ignored everywhere |
| `StageExecutionConfig.*`, `WorkflowExecutionConfig.*` | ignored everywhere |

```python
wf["step1"] = Operation(step_id="step1", name="slow", arguments={"x": 1},
                        execution=StepExecutionConfig(retries=3, timeout=0.001))
wf.run()
# attempts made: 1   (single step: no retry loop in run_step)
```

The stated rule is "`retries` retries the unit of work, and `mode` defines the
unit." That holds for fan-out modes only until `run_step`/`arun_step` grow a
retry loop. `timeout` is harder than it looks: sync tools run via
`asyncio.to_thread`, and a thread cannot be cancelled — `wait_for` would return
control while the work continued, which is worse than not implementing it.

## 2. `Server` is invisible

The thing most users ultimately need is not in `__all__`.
`from simple_steps_core import Server` fails, and nothing in the top-level
namespace hints at where to look.

The lazy-import constraint is real, but solvable with a module-level
`__getattr__` (PEP 562) that imports on first attribute access and raises a
helpful error naming the missing extra:

```python
def __getattr__(name):
    if name == "Server":
        from .serving import Server
        return Server
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

## 10. The grid model is a second, parallel model

`simple_steps_core.grid` implements [shape-algebra.md](shape-algebra.md)
standalone — it imports nothing from the engine and nothing imports it — so
`Workflow`, `Operation` and `Step` each mean two things depending on which
module you took them from. That is survivable during migration and must not
outlive it. The sequence is in shape-algebra §10; the load-bearing first step is
making `ToolCall` recursive, because nothing else can land before it.

Three execution modifiers are documented as part of the model and exist in
neither place: `cache`, `gate`, `concurrency`.

`grid.__all__` also exports 52 names, about a quarter of which are the verb
implementations a user never calls directly (Tier 4, *implementation layer*).
Same problem as §8 above, in the newer half of the codebase.

---

## Cross-cutting

Changes 1, 4 and 9 are one theme: **the model layer declares intent the
execution layer ignores.** Changes 2 and 8 are one theme: **`__all__` is not
tiered** — 57 names arrive flat, with the four dead ones present and the two
essential ones absent. Fixing the tiering is cheap and would make the surface
teach itself.
