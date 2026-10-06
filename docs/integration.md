# Integration guide — the grid model

> **Status: the grid model is the integration surface.** This guide is how an
> application embeds `simple-steps-core` today. The older engine runtime
> (`CoreEngine`, `SessionManager`, `Server`) is **legacy** and being retired
> onto this model ([migration-plan.md](migration-plan.md)); do not build new
> integrations against it.

How to embed the grid core into a backend where end users author and run their
own workflows — e.g. behind a React API ([react-api.md](react-api.md) is the
proposed HTTP shape). The runnable reference is
[examples/all_orchestrations/](../examples/all_orchestrations/).

---

## 1. Install

```bash
python -m pip install simple-steps-core      # runtime deps: pandas, pydantic
```

```python
from simple_steps_core import grid
from simple_steps_core.grid import tool, op, mod
```

Import the **module** — `grid.Workflow`/`Operation`/`Step` disambiguate from the
legacy engine's same-named classes.

---

## 2. Mental model

The backend owns the only Python callables. The frontend never executes
anything — it **authors a workflow as JSON** (a list of operations) and reads
back staged shapes and, after a run, the output grids.

```
React UI  ──(JSON: steps as operations)──▶  Backend
   ▲                                          │
   │                                          ├─ grid.catalog()        → the tool palette
   └──(staged shapes, then data+ledger)───────┤─ Workflow.from_json()  → build + validate (declare)
                                              ├─ wf.run_all()          → execute
                                              └─ wf.to_session_json()  → persist the run
```

The one idea the client must absorb: **declaring a step is not running it.**
A declared step already knows its shape and cell count and carries any
`problems`, having computed nothing — so a 40-step workflow can be laid out and
validated before any expensive call runs.

Three roles:

| concept | role |
|---|---|
| **tool** | a Python function the backend registers with `@tool` |
| **operation** | a tool + a modifier stack + bound literals — the JSON a client authors |
| **workflow** | ordered steps, run against the data a source step carries |

---

## 3. Expose the tool palette

A *tools file* is a plain module that `@tool`-decorates functions; importing it
registers them into `grid.TOOLS`.

```python
# tools.py
from simple_steps_core.grid import tool

@tool
def scale(n, weight=1) -> int:
    return n * 10 * weight
```

```python
import tools                      # running the module registers its tools
palette = grid.catalog()          # {tool_id: {description, params, returns, origin, ...}}
```

Serve `palette` as your `GET /tools`. `origin` separates `"declared"` tools from
`"builtin"` ones (`count`, `gather`, …), so a UI can group or hide the builtins.

---

## 4. The workflow JSON contract

An operation serializes to exactly this (`Operation.to_dict()`):

```json
{
  "tool_id": "scale",
  "arguments": {"weight": 2},
  "modifiers": [{"kind": "map", "params": {"over": "readings", "name": "score"}}]
}
```

A workflow is `{"version": 1, "steps": [{"step_id": "...", "operation": {...}}]}`.
References between steps are the plain **step id** in a modifier's `over`
param. The vocabulary of `kind` values is the 14 shape verbs plus `retry` /
`timeout` ([api-reference.md](api-reference.md)); a client builds the modifier
UI from them.

A **source step** carries data rather than an operation — assign a frame, list
or value, and it is born completed.

---

## 5. Build and validate (declare)

```python
wf = grid.Workflow.from_json(workflow_json, grid.TOOLS)   # structure only; stages every step
problems = wf.validate()                                   # {step_id: problems}, empty = valid
```

Every step goes through the same `check` + staging the incremental path uses, so
loading cannot smuggle in a step that declaring would reject. For the UI:

- an **invalid** step is still a step (carrying `problems`) — render it, do not
  reject the request; it is a `200`, not a `422`.
- a **staged** step already knows its shape: `wf.step(sid).describe()` →
  `"map scale · 4 cells"`, and `wf.step(sid).status` is `"staged"`.

---

## 6. Run

```python
wf.run_all()                 # every valid step, each after the steps it reads
# or one at a time, which the client drives:
wf.run("scored")             # refuses if an input has not run
```

Running is **explicit** — nothing recomputes on its own. `run_all` only saves
you from ordering the calls by hand.

---

## 7. Read results

```python
out = wf.step("scored").output
out.view()        # data + ledger, the one table to render
out.data          # the payload grid (what downstream consumes)
out.ledger        # status, error, attempts, seconds, unit — per unit of work
out.failed        # the re-drive set: rows that failed, with their errors
```

A tool that fails on some rows does not raise — every unit is recorded, and
`out.failed` is exactly the set a UI can re-drive. The ledger columns are fixed
(`LEDGER_COLUMNS`), so progress and error views always render.

---

## 8. Persist and restore

| call | carries | when |
|---|---|---|
| `wf.to_json()` | structure only (light) | store the recipe; cheap, no payloads |
| `wf.to_session_json()` | structure **+ every payload** (full) | persist a completed run |
| `grid.Workflow.from_json(data, grid.TOOLS)` | rebuilds either | restore; pass the registry so functions re-attach |

A light reload lands at "shapes known, counts not" — counts came from the data,
which the light export does not carry. A full reload reproduces the exact
outputs:

```python
original = wf.to_session_json()
restored = grid.Workflow.from_json(original, grid.TOOLS)   # same data + ledgers
```

(`roundtrip()` in the example asserts this.)

---

## 9. What you supply yourself

The grid core is the authoring + execution + serialization engine. Until the
migration lands them ([migration-plan.md](migration-plan.md)), the backend owns:

| concern | today |
|---|---|
| **transport** (HTTP, auth, routing) | yours — the core is in-process Python |
| **multi-user sessions / isolation** | yours — one `Workflow` per user area |
| **resources** (db/LLM clients, config) | not injectable into grid tools yet; pass values as data or close over them |
| **media, lazy sources** | not in the grid core yet |
| **guardrails / UI schema** | not on grid tools yet |
| **async / concurrency / caching** | sync only; `timeout` records intent but does not enforce |

A minimal backend is therefore: import a tools module, serve `catalog()`, accept
workflow JSON, `from_json` → `validate` → `run_all`, return `to_session_json()`
or per-step `view()`. See [react-api.md](react-api.md) for the proposed endpoint
shapes and [examples/all_orchestrations/](../examples/all_orchestrations/) for
the whole flow in Python.
