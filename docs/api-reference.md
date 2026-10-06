# API reference — the grid model

> **Status: the grid model is the integration surface.** This is what an
> application embeds today. The older engine runtime (`CoreEngine`,
> `OrchestrationConfig`, `MapResult`, `ToolCall`) is **legacy** and being
> retired onto this model — see [migration-plan.md](migration-plan.md). Do not
> build new integrations against it.

Everything here is imported as one module, so every call site says which model
it means:

```python
from simple_steps_core import grid
from simple_steps_core.grid import tool, op, mod      # the three you name directly

wf = grid.Workflow()
```

> Import the **module** for `grid.Workflow` / `grid.Operation` / `grid.Step` —
> those three names also exist in the legacy engine and mean different things
> there ([grid-model.md §0](grid-model.md)). `tool`, `op` and `mod` are
> unambiguous, so importing them by name is fine.

The runnable, asserted version of everything below is
[examples/all_orchestrations/](../examples/all_orchestrations/).

---

## Tier 1 — writing tools

A tool is a plain function that declares the **values** it needs by name.
Supplying rows is the modifier's job, so a tool never mentions a row or a grid.

| name | what it is |
|---|---|
| `tool` | decorator — registers a function into the shared `TOOLS` registry |
| `TOOLS` | the process-wide registry `@tool` writes into |
| `BUILTIN_TOOLS` | `identity`, `gather`, `count`, `total`, `first`, `last` — always available, no registration |
| `STRICT_TYPES` / `@tool(strict=True)` | require a full type annotation on every parameter and the return |

```python
from simple_steps_core.grid import tool

@tool
def scale(n, weight=1):          # declares the columns it wants: n, weight
    return n * 10 * weight
```

- **Annotate for a richer palette.** Annotations are optional, but `catalog()`
  publishes them and `check` compares them to the upstream's real dtypes, so a
  frontend can say what a step consumes and produces before it runs.
- **A tool may take the whole row** with `**row`; then `check` cannot verify its
  inputs (it receives every column), and `catalog` flags it `takes_whole_row`.
- The decorated object is still callable as an ordinary function (`scale(3)`),
  and gains `.fn` (the raw function) and the bracket grammar below.

---

## Tier 2 — authoring a workflow

A step is an assignment into a `Workflow`. The grammar is three decisions:

```python
wf["scored"] = scale[ mod.map(over=wf["readings"], name="score") ]
#              └tool┘ └──────────── shape verb ───────────────┘
```

| piece | decides | form |
|---|---|---|
| `scale` | **what** runs on one unit | a tool (or `op("id")` for a builtin) |
| `[mod.<verb>(...)]` | **how** it iterates — the shape change | brackets *decorate*, returning data |
| `over=wf["readings"]` | **which step** it reads | a reference to an earlier step |

| name | what it is |
|---|---|
| `op("tool_id", **args)` | start an `Operation` from a tool id (e.g. a builtin: `op("count")`) |
| `mod.<verb>(...)` | a `Modifier` descriptor — `mod.map`, `mod.filter`, … `mod.retry`, `mod.timeout` |
| `Operation` | one tool + an ordered, JSON-safe modifier stack + bound literals |
| `Modifier` | one stack entry: `kind` + `params` (data, never a closure) |
| `.bind(**literals)` | fix arguments without running (`scale.bind(weight=2)[mod.map(...)]`) |
| `grid(value)` | lift a raw value into an `Output` so a chain can start from it |

**The 14 shape verbs** (full semantics in [shape-algebra.md §3](shape-algebra.md)):

| run a tool | apply no tool (pure reshape) |
|---|---|
| `map` `filter` `group` `expand` `collapse` `sweep` | `source` `select` `drop` `rename` `widen` `slice` `sort` `distinct` |

**Execution modifiers** (shape-preserving): `retry(times=)`, `timeout(seconds=)`.
Order is semantics — `retry(map(f))` retries the whole fan-out, `map(retry(f))`
retries each item. `cache`/`gate`/`concurrency` are planned, not built.

A **bare shape verb** is a complete step for the no-tool reshapers:

```python
wf["cities"] = mod.distinct(over=wf["scored"], columns=["city"])   # applies identity
wf["readings"] = some_dataframe                                    # a source step
```

Introspection on the vocabulary, all derived from one table so they cannot
drift: `MODIFIERS`, `SHAPE_VERBS`, `is_shape(kind)`, `DECORATORS`,
`ModifierKind`, `ROWS_RULE`, `DEFAULT_PAYLOAD`, `CARRIES_COLUMNS`, `PAYLOAD`
(`"value"`).

---

## Tier 3 — running and reading

```python
wf.run_all()                      # run every valid step, each after the ones it reads
wf.run("scored")                  # or one step (refuses if an input has not run)

del wf["scored"]                  # or wf.remove("scored") — refused if a later step reads it
wf.rename("raw", "readings")      # rewrites every over= that pointed at it; outputs kept
```

`run`/`run_all` are **explicit** — nothing recomputes on its own. Reassigning an
upstream step marks its completed dependents `stale` (data kept) until re-run.

### `Output` — what a step produced

`Output` is a payload grid plus a row-aligned ledger that share an index.

| member | is |
|---|---|
| `.data` | the payload `DataFrame` — what downstream steps consume |
| `.ledger` | per-unit execution state — columns `status, error, attempts, seconds, unit` (`LEDGER_COLUMNS`) |
| `.view()` | `data` joined with `ledger` — the one table to render |
| `.values` | the payload column as a plain list |
| `.item()` | the single payload of a one-row grid (`collapse`) |
| `.ok` | rows that completed |
| `.failed` | ledger rows that failed — the re-drive set, with errors |
| `.shape` / `.form` | `(rows, cols)` / `"scalar" \| "column" \| "grid"` |
| `.progress()` | `"3/4"` |

### `Step` — a node of the workflow

| member | is |
|---|---|
| `.operation` / `.output` | what to run / what it produced (always both, from declaration) |
| `.status` | a **rollup** of the ledger: `staged \| running \| completed \| failed \| invalid`, plus `stale` when an upstream changed |
| `.describe()` | what the step is, in words — a staged step reports its *predicted* cell count |
| `.problems` / `.valid` | declaration-time problems (empty = valid) |

### Validation — before anything runs

```python
wf.validate()                     # {step_id: problems} — every step, empty tuples for the good ones
grid.check(operation, wf, step_id)   # the same check, for one operation
```

`check` catches unknown tools and verbs, bad modifier params, unknown/forward
references, cycles, and (for annotated tools) dtype mismatches.

---

## Tier 4 — the wire contract (serialization)

This is the JSON an application sends and stores.

### The tool palette — `catalog()`

```python
grid.catalog()        # {tool_id: entry} for every builtin + declared tool
```

Each entry:

```json
{
  "tool_id": "pick",
  "description": "Pick rows.",
  "origin": "declared",                      // or "builtin"
  "params": [
    {"name": "region", "required": true, "default": null,
     "type": "str", "choices": ["EMEA", "AMER"], "nullable": false,
     "description": "which region to load."},
    {"name": "limit", "required": false, "default": null,
     "type": "int", "choices": null, "nullable": true,
     "description": "cap the row count."}
  ],
  "returns": "list",
  "typed": true,
  "takes_whole_row": false
}
```

Per parameter: `type` is the **inner** type (`Optional[int]` → `"int"`),
`choices` are a `Literal`'s options (`null` otherwise), `nullable` marks an
`Optional`, and `description` is the parameter's `Args:` docstring text. String
annotations (`from __future__ import annotations`) are resolved, so these work
regardless of how the tool is written.

### The verb palette — `modifier_catalog()`

```python
grid.modifier_catalog()       # {verb: {class, row_rule, settings}} — JSON, GET /modifiers
```

Each verb entry carries its `class` (`"shape"` | `"execution"`), its `row_rule`
(`same` / `at_most` / `one` / `unknown` / `generated`, `null` for execution
modifiers), and a `settings` list — each `{name, type, required, default}` — so a
client builds the verb's form from core instead of hard-coding it. A verb's data
input is **not** a setting (it is the step's `input`, below); `sweep`'s
`<swept>` setting marks that extra named parameters are the data.

### An operation — `Operation.to_dict()`

```json
{
  "tool_id": "scale",
  "input": {"$ref": "readings"},
  "arguments": {"weight": 2},
  "modifiers": [{"kind": "map", "params": {"name": "score"}}]
}
```

`input` is the step whose grid this reads — the data, taken from the call
position (or `over=`). `arguments` are bound literals; a value that is itself a
reference to another step appears as `{"$ref": id}` too. Modifiers are
**literal-only** — they say how to orchestrate, never what data. A `StepRef`
serializes to `{"$ref": id}` everywhere; that is the only envelope a reference
takes.

### A workflow — two export modes

| method | carries | use |
|---|---|---|
| `wf.to_json()` / `to_dict()` | **light**: `{"version": 1, "steps": [{step_id, operation}]}` — structure only | store the recipe; a light reload knows shapes but not counts |
| `wf.to_session_json()` / `to_session_dict()` | **full**: the light export **plus** `{"outputs": {step_id: {data, ledger, meta}}}` | persist a run with its payloads |
| `Workflow.from_json(data, tools)` | rebuild either export through the same `check` + staging | pass `grid.TOOLS` (or a tool dict) so functions re-attach |

A persisted output is `{"data": …, "ledger": …, "meta": …}` — the two frames
encoded with their dtypes, never pickled.

---

## The whole surface (`grid.__all__`)

```
Output grid rows                          lift & inspect a value
map_ filter_ group_ collapse_ expand_ sweep_ source_
select_ drop_ widen_ slice_ rename_ sort_ distinct_   the verb functions
identity gather count total first last    builtin tools / reducers
tool ToolHandle TOOLS BUILTIN_TOOLS catalog tool_entry modifier_catalog   the registry
op Operation Modifier mod                 authoring
Step Workflow StepRef                     the workflow (Workflow.validate() is a method)
check stage                               declaration-time checks
compile_operation                          Operation -> callable
MODIFIERS ModifierKind SHAPE_VERBS is_shape DECORATORS   the vocabulary
ROWS_RULE DEFAULT_PAYLOAD CARRIES_COLUMNS PAYLOAD LEDGER_COLUMNS
STRICT_TYPES annotation_problems declaration_problems predicted_columns infer_verb
```

---

## Not in the grid core yet

Honest scope — an application needs to supply these itself until the migration
lands them ([migration-plan.md](migration-plan.md)):

| capability | status |
|---|---|
| resources / dependency injection (`Resource()`) | engine-only; not on grid tools |
| media assets, lazy `Collection` sources | engine-only |
| guardrails · prefab/React UI · JSON Schema | engine-only |
| async + real `timeout`/`concurrency`/`cache` | sync only; `timeout` records intent but does not enforce |
| an HTTP server, multi-user sessions | **none in the grid core** — you own the transport |

For the proposed HTTP shape over this model, see [react-api.md](react-api.md);
for embedding it in a backend, [integration.md](integration.md).
