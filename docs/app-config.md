# App configuration

> **Status: settled design, not yet built.** The grid model's target
> configuration for running this library as a backend. See
> [shape-algebra.md](shape-algebra.md) for the model,
> [react-api.md](react-api.md) for what the server exposes, and
> [config-isolation.md](config-isolation.md) for the rule §2 below preserves.

---

## 1. The boundary that decides everything

The existing model has **four** config objects and one hard-won rule: they are
isolated, nothing cascades, and there is no `resolved_config()`
([config-isolation.md](config-isolation.md)). Three of them —
`StepExecutionConfig`, `StageExecutionConfig`, `WorkflowExecutionConfig` —
dissolve into the modifier stack, where behaviour is per-step and local.

An app config is the one that survives, and the danger is obvious: it is a
tempting place to put `default_retries`. Doing so would rebuild the cascade the
model just deleted, and reintroduce the question *"where did this step's retry
count come from?"* which is exactly what a modifier stack answers by inspection.

> **`AppConfig` holds process-level facts. It never holds step behaviour.**

The distinction that makes this workable is **default versus ceiling**:

| | | allowed? |
|---|---|---|
| **default** | "steps retry twice unless they say otherwise" | ✗ — a cascade; the stack is the only source |
| **ceiling** | "no step may exceed 32 concurrent items" | ✓ — a limit, not a value |

A ceiling *clamps* a modifier, it does not supply one. `mod.map(concurrency=64)`
under `max_concurrency = 32` runs 32 at a time and **says so in the ledger** —
it is never silently rewritten, and the step's stored data still reads 64,
because that is what the author asked for. Clamping is the server protecting
itself; the Operation stays the author's intent.

---

## 2. What it holds

```python
class AppConfig(BaseModel):
    """Process-level settings, read once at startup."""

    # ── identity ──────────────────────────────────────────────────────
    title: str = "Simple Steps"

    # ── serving ───────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = []          # e.g. ["http://localhost:5173"]
    root_path: str = ""                   # when mounted behind a proxy

    # ── tools ─────────────────────────────────────────────────────────
    tool_modules: list[str] = []          # imported at startup; @tool registers
    freeze: bool = True                   # lock the registry once loaded

    # ── resources ─────────────────────────────────────────────────────
    resources: dict[str, str] = {}        # name -> "module:factory"

    # ── state ─────────────────────────────────────────────────────────
    storage: str = "memory"               # "memory" | a StoreBackend import path
    session_ttl_seconds: int | None = None

    # ── ceilings (never defaults — see §1) ────────────────────────────
    max_concurrency: int = 32
    max_cells_per_step: int | None = 100_000
    max_payload_bytes: int | None = 50_000_000
    request_timeout_seconds: float | None = 300
```

### Why each earns its place

**`tool_modules`** is the one that matters most. A workflow arrives as tool
*ids*, so something has to turn `"to_fahrenheit"` back into a function.
Importing a module registers its `@tool`s, and nothing else needs to happen —
which is why this is a list of import paths rather than a registry to populate
by hand. See [writing-tools.md](writing-tools.md).

**`freeze`** defaults to `True` for a server and `False` for a notebook. A
frozen registry cannot gain tools after startup, which is what stops a request
from mutating the palette other sessions are reading.

**`resources`** maps a name to a `"module:factory"` string rather than a live
object, because configuration must be serializable and resources must not be:
they are rebuilt from their factories on load, never snapshotted
([api-reference.md](api-reference.md)).

**`storage`** decides where payloads live. This is the setting that pairs with
`Output.ref` — the indirection that keeps grids off the model. With
`"memory"` a restart loses everything, which is correct for development and
wrong for anything else.

**The ceilings** exist because a grid model makes it easy to ask for far too
much by accident: a `sweep` over four parameter lists is a cross product, and
one careless list turns 100 cells into 100,000. `max_cells_per_step` is checked
**at declaration**, so an over-large step is `invalid` before it runs rather
than after it has exhausted memory — the same reactive path as every other
problem a step can have.

---

## 3. Where values come from

Precedence, lowest to highest:

```
class defaults  <  config file  <  environment  <  explicit constructor argument
```

Environment variables are prefixed and upper-cased: `SSC_PORT`,
`SSC_MAX_CONCURRENCY`, `SSC_CORS_ORIGINS`. A parent repo embedding this as a
submodule sets the environment and touches nothing else — which is the point of
the ordering, since the file may be vendored and the environment is per
deployment.

```python
from simple_steps_core import AppConfig, Server

config = AppConfig.load("app.toml")          # file, then env, then:
Server(config, port=9000).run()              # explicit wins
```

`AppConfig.info()` renders the resolved values as a table, so what is actually
in effect is always inspectable — not reconstructed by reading three sources.

---

## 4. What it deliberately does not hold

| not here | where it lives | why |
|---|---|---|
| retries, timeout, cache | the step's modifier stack | per-step, order-sensitive; a default would cascade |
| the shape verb | the step's modifier stack | it *is* the step's definition |
| a step's input data | the step itself — a source step's data is its output | a Workflow is only steps |
| the dependency graph | derived from `over` tokens | storing it means keeping it in sync |
| staging / cell counts | derived from structure | it is a pure function of the steps |
| secrets | the environment or a secret store | config is serializable and gets logged |

Every row is the same principle: **configuration holds what cannot be derived.**
Anything computable from the workflow is computed, so it cannot go stale.

---

## 5. Multi-tenant shape

One `AppConfig` per process; one `SessionContext` per logical run.

```python
session_id = make_session_id(user, workflow_id, run_id)
context = manager.get_or_create(session_id)
async with manager.lock(session_id):
    ...
```

The config is read-only after startup and shared; everything mutable lives in a
session. `session_ttl_seconds` is what stops an idle dashboard from pinning
payloads in memory forever — with `storage="memory"` it is the only thing that
does.

---

## 6. Open

- **Per-tool ceilings.** A `transcribe` tool may warrant a lower concurrency
  than everything else. That is arguably a property of the *resource* it uses
  (one API key, one rate limit) rather than of the app — which suggests it
  belongs on `ResourceSpec`, not here. Unsettled.
- **Clamp reporting.** A clamped step should record that it was clamped. The
  ledger is the obvious home, but that adds a column every other verb leaves
  empty.
