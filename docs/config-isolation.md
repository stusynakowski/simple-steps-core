# Orchestration vs Execution — the isolation rule

> **Status: implemented, and being superseded — but the rule survives.**
> The *split* between shape and conduct is right and is kept. What changes is
> that it stops being **two config objects** and becomes **two classes of
> modifier in one ordered stack** on the Operation. Read
> [§0](#0-what-this-becomes) first if you are working on the new model;
> everything after it describes the engine as it is today and remains accurate.

**Status: implemented.** `OrchestrationConfig` is shape-only and
`StepExecutionConfig` owns conduct. The two share **zero fields**, enforced by a
test (`test_orchestration_and_execution_share_no_fields`).

---

## 0. What this becomes

Both configs dissolve into `Operation.modifiers`, an ordered list, each entry
tagged with which class it belongs to:

```python
score[mod.map(over="step1", concurrency=8), mod.retry(times=2)]
#      └─ cls="shape" ─────────────────────┘  └─ cls="execution" ─┘
```

| this document's term | becomes |
|---|---|
| `OrchestrationConfig` | the **one shape verb** in the stack |
| `StepExecutionConfig` | the **execution modifiers** in the same stack |
| `mode="single"` | no shape verb at all |
| `mode="map"`, `over=` | `mod.map(over=...)` |
| `retries=`, `concurrency=` | `mod.retry(times=...)`, a param on the shape verb |
| `extra="forbid"` catching a misplaced field | `mod.<kind>` rejecting an unknown kind at the call site |

### What survives, and why it has to

**The disjointness.** Shape and conduct still share zero fields — the class is
now a field (`cls`) on the modifier rather than a choice of object. It is
load-bearing, not bookkeeping:

| class | does to the signature it wraps | staging |
|---|---|---|
| `shape` | **lifts** it: `(row → b)` becomes `(source → Output)` | must fold it |
| `execution` | **preserves** it: `(row → b)` stays `(row → b)` | ignores it |

Because execution modifiers cannot change shape, a step's shape is computable
from its stack before anything runs. That is what makes staging reactive.

**No cascade, no precedence, no `resolved_config()`.** Unchanged. A modifier is
local to its step, exactly as a config was.

**The unit-of-work rule**, restated: the unit is what the enclosing shape verb
makes it. `retry` inside `map` retries an item; `retry` outside `map` retries
the fan-out.

### What does *not* survive

**"The mode decides the unit for you."** Today's rule — *`retries` means "retry
the unit", the whole call when `single`, one item when fanned out* — reads as a
convenience but is really a limitation. It means you cannot say "retry the whole
fan-out": `retries` is an argument *of* the orchestrator call, so it is
structurally inside it, and an argument cannot sit outside its own function.

| composition | today |
|---|---|
| `map(retry(f))` — retry each item | the only thing sayable |
| `retry(map(f))` — retry the fan-out | **unsayable** |
| `map(timeout(f, 60))` — 60s per item | sayable |
| `timeout(map(f), 60)` — 60s for the step | **unsayable** |

An ordered stack makes the choice explicit instead of implied. The cost is that
**order becomes significant**, which is a real thing to learn — but it is
significant either way; today one of the two orders is simply unavailable.

**`test_orchestration_and_execution_share_no_fields` needs a successor.** The
invariant it protects is worth keeping; the thing it inspects will not exist.
The replacement asserts that every entry in the modifier vocabulary declares
exactly one `cls`, and that no shape verb and execution modifier share a
parameter name.

---

| Config | Owns | In one sentence |
|---|---|---|
| `OrchestrationConfig` | **shape** | how input data is fanned out and how output data comes back |
| `StepExecutionConfig` | **conduct** | how that operation is carried out — errors, retries, timing |
| `StageExecutionConfig` | conduct, stage scope | how a stage's steps run together |
| `WorkflowExecutionConfig` | conduct, workflow scope | how a workflow's stages run |

```python
Operation(
    step_id="step2", name="scale",
    orchestration=OrchestrationConfig(mode="map", over="step1"),   # shape
    execution=StepExecutionConfig(concurrency=8, retries=2,        # conduct
                                  on_item_error="fail_fast"),
)
```

**The unifying rule:** `mode` defines the *unit of work* — the whole call when
`single`, one item when fanned out — and every conduct field acts on that unit.
So `retries=2` means "retry the unit twice" in both cases, with no second
meaning to learn.

All four configs now set `extra="forbid"`. Passing a field to the wrong config
raises instead of being silently dropped:

```python
OrchestrationConfig(mode="map", over="s1", concurrency=4)
# ValidationError: concurrency — Extra inputs are not permitted
```

---

## 1. The field map

| Field | Lives on | Concern | Honored at runtime? |
|---|---|---|---|
| `mode`, `over`, `item_arg`, `initial` | Orchestration | shape | yes |
| `concurrency` | StepExecution | conduct | yes — fan-out modes |
| `on_item_error` | StepExecution | conduct | yes — fan-out modes |
| `retries` | StepExecution | conduct | yes — fan-out modes; **inert for `single`** |
| `run`, `timeout`, `cache` | StepExecution | conduct | **inert** |
| *sync/async* | derived from `Tool.is_async` | conduct | n/a |
| *progress* | **nowhere yet** | conduct | — |

### What moved

`concurrency`, `on_error` → `on_item_error`, and `retries` moved from
`OrchestrationConfig` to `StepExecutionConfig`. `Operation.to_tool_call()` now
reads both configs when compiling an orchestrator call — shape from one, conduct
from the other. That is the single point where they meet.

### Still to do

`retries` is live when a step fans out (the orchestrator implements it) but
**inert when `mode="single"`**, because `Workflow.run_step` does not implement a
retry loop. Same for `timeout` and `cache`. Until that lands, the "retry the
unit" rule holds for mapped steps only — see
[api-reference.md § 1](api-reference.md#1-execution-configs-are-declared-but-never-honored).

### Why `retries` had to move (historical)

Two fields, same name, opposite fates:

```python
wf["step2"] = Operation(step_id="step2", name="flaky_item",
                        orchestration=OC(mode="map", over="step1", retries=3))
wf["step3"] = Operation(step_id="step3", name="flaky_step",
                        execution=SEC(retries=3))
wf.run()
# OrchestrationConfig.retries=3 -> 4 attempts  (honored)
# StepExecutionConfig.retries=3 -> 1 attempt   (ignored)
```

Two fields shared one name with opposite fates: the honored one lived on the
config that should not have owned it. There is now exactly one `retries`.

---

## 2. Why the drift happened (history)

Worth recording, because the cause was structural rather than sloppiness.

`Operation.to_tool_call()` compiles orchestration into the **arguments of the
orchestrator tool**:

```python
call_args["concurrency"] = orch.concurrency
call_args["on_error"]    = orch.on_error or _ORCH_DEFAULT_ON_ERROR[orch.mode]
call_args["retries"]     = orch.retries
return ToolCall(operation_id=orch.mode, arguments=call_args)
```

Since `map`/`filter`/`expand` are themselves ordinary registered tools, anything
they need must arrive as an argument. Execution config is never consulted by
`to_tool_call()` at all — verified by compiling every mode:

```
mode=single    -> op=t         args=['k']
mode=map       -> op=map       args=['args','concurrency','on_error','op','over','retries']
mode=filter    -> op=filter    args=['args','concurrency','on_error','op','over','retries']
mode=collapse  -> op=collapse  args=['args','initial','op','over']
```

**Orchestration config was a live wire into the runtime; execution config was a
dead end.** Conduct fields migrated to orchestration because that was the only
channel that reached anything.

`to_tool_call()` now reads *both* configs, so the channel is no longer the
constraint and the fields could go home. Note that `collapse` still takes no
`concurrency`/`on_item_error`/`retries` (it is a sequential reduce), and
`single` compiles to a direct call — so per-item conduct is meaningful for
`map`/`filter`/`expand` only.

---

## 3. Naming

Scope is now in the name everywhere, so the three error policies read as one
family — item, step, stage:

| Config | Field | Scope |
|---|---|---|
| StepExecution | `on_item_error` | per item |
| StageExecution | `on_step_error` | per step |
| WorkflowExecution | `on_stage_error` | per stage |

`concurrency` still appears on two configs, but they are unambiguous now that
both sit in the conduct column: `StepExecutionConfig.concurrency` bounds *items
within one step*, `StageExecutionConfig.concurrency` bounds *steps within one
stage*. Each is the concurrency of that scope's unit.

---

## 4. Migration

There is no compatibility shim — by design. `extra="forbid"` means old call
sites raise instead of silently losing settings:

```python
# before
OrchestrationConfig(mode="map", over="step1", concurrency=8, retries=2)
# after
OrchestrationConfig(mode="map", over="step1")
StepExecutionConfig(concurrency=8, retries=2)
```

**Saved workflow JSON from before this change will not load** — an old
snapshot carries `concurrency`/`on_error`/`retries` inside its orchestration
object, which now fails validation. That is the intended loud failure. If a
snapshot must be recovered, strip those three keys from each step's
`orchestration` object and move them under `execution`.

---

## 5. The progress gap

You named progress as an execution concern; nothing in any of the four configs
carries it, and no runtime hook reports it. It belongs on
`StepExecutionConfig` (per your definition: it is about how the work is carried
out and observed, not how data is shaped).

Worth deciding at the same time as the move above, because progress for a mapped
step is per-item and needs the same channel into the orchestrator that
`concurrency` uses — so it is cheap to add while `to_tool_call()` is already
being changed, and awkward to bolt on afterwards.

---

## 6. Fixed while mapping this

The dashboard offered a sync/async **mode** selectbox under Runtime settings.
`StepExecutionConfig` has no `mode` field — the model states sync/async is
derived from the tool — so the value was collected and dropped. Worse, reloading
any saved workflow seeded the draft from `model_dump()`, which has no `"mode"`
key, so every load crashed:

```
KeyError: 'mode'   at dashboard.py, Runtime settings tab
```

The phantom control is gone; the tab now displays the derived call style from
`Tool.is_async`. Loading the sample workflow works.
