# 004 — Grid adoption: what the app needs from core

**Status: proposal.** What `simple-steps-core`'s **grid model** must provide for
the app to run on it. Supersedes most of `003-app-adoption.md`, which targeted
the engine core is retiring ([migration-plan.md](../migration-plan.md)); items
that carry over are noted inline.

Every gap below is backed by a probe against the current `grid.py`. Run them with
the dev venv active:

```bash
python - <<'PY'
import json
from typing import Literal, Optional
import pandas as pd
from simple_steps_core import grid
from simple_steps_core.grid import tool, mod
...
PY
```

Priority tiers: **§A blocking** (the app cannot run without them), **§B soon**
(needed shortly after the switch), **§C not blocking**, **§D not needed**.

---

## A. Blocking — before the app can run on the grid model

### A1. The tool palette needs complete parameter info for forms
*New; replaces item A in `003`.* **✅ Built (2026-10-05).** `catalog()` params now
carry `type` (the inner type of an `Optional`), `choices` (a `Literal`'s
options), `nullable`, and `description` (the `Args:` text); string annotations
are resolved.

`catalog()` collapses `Literal[...]` to `"Literal"` and `Optional[int]` to
`"Optional"`, so the choices and the inner type are lost; it also drops the
per-parameter `Args:` text and keeps only the summary.

```python
@tool
def pick(region: Literal["EMEA","AMER"], limit: Optional[int] = None) -> list:
    """Pick rows.

    Args:
        region: which region to load.
        limit: cap the row count.
    """
    ...
grid.catalog()["pick"]["params"]
# [{"name":"region","required":true,"default":null,"type":"Literal"},   ← choices lost
#  {"name":"limit", "required":false,"default":null,"type":"Optional"}]  ← inner type lost
```

**Ask:** add `choices` and `description` to each parameter, keep the inner type
of `Optional`, and add `nullable`. Without this the app's dropdowns and
parameter help regress.

### A2. The list of verbs and their settings should come from core as JSON
*New.* **✅ Built (2026-10-05).** `grid.modifier_catalog()` returns, per verb, its
`class`, `row_rule`, and typed `settings` (`over`, `name`, `columns`, `by`,
`initial`, … with required/default) — plain JSON for `GET /modifiers`.

`grid.MODIFIERS` holds `ModifierKind` objects that contain functions, so they
can't be served; and nothing lists a verb's settings.

```python
json.dumps(grid.MODIFIERS)
# TypeError: Object of type ModifierKind is not JSON serializable
grid.PARAM_TYPES_BY_VERB.get("map")
# None
```

**Ask:** a `modifier_catalog()` giving, per verb, its class, its row rule, and its
settings (`over`, `name`, `columns`, `by`, `initial`, … with type, required,
default). [react-api.md](../react-api.md) already proposes this as
`GET /modifiers`. With it the UI builds verb forms from core instead of
hard-coding them.

### A3. A source step should be able to come from a tool, like `load_csv(path)`
*New.* **✅ Built (2026-10-05).** `load.bind(path=…)[mod.source()]` now validates,
stages, and on `run` calls the no-input tool — a returned DataFrame becomes the
step's grid, so loading is a saved, re-runnable step that round-trips.

```python
wf["raw"] = load.bind(path="x.csv")[mod.source()]
wf.step("raw").problems
# ('source applies no tool; use map to compute',)
```

Without this, loading data happens outside the workflow: it isn't in the saved
workflow, can't be re-run, and a reload fails with "source step has no data".

**Ask:** a source verb that calls a no-input tool and treats a returned DataFrame
as the step's grid.

### A4. Steps need to be deletable and renamable
*New.* **✅ Built (2026-10-05).** `del wf[sid]` / `wf.remove(sid)` delete a step,
refusing (and naming the readers) when a later step reads it; `wf.rename(old,
new)` rewrites every `over=` that pointed at it, keeps outputs, and preserves
order.

```python
hasattr(grid.Workflow, "__delitem__"), hasattr(grid.Workflow, "remove"), \
hasattr(grid.Workflow, "rename")
# (False, False, False)
```

**Ask:** `__delitem__`/`remove` and a `rename`. Deleting should refuse, or report
the broken steps, when later steps read the one being deleted.

### A5. Downstream steps should go stale when an upstream step changes
*Already on core's list as future work ([react-api.md](../react-api.md) §11, [status.md](../status.md) §5).* **✅ Built (2026-10-05).** Reassigning an upstream
marks its completed transitive dependents `stale` (data kept, nothing
recomputed); `Step.status` reads `stale` until the step is re-run.

```python
w["s"] = sc(w["r"]); w.run_all()
w["r"] = pd.DataFrame({"n":[9,9]})       # reassign the upstream
w.step("s").status, w.step("s").output.values
# ('completed', [10, 20, 30])            ← stale data shown as current
```

**Ask:** mark dependents `stale` without recomputing them. Without it the UI
shows wrong results as if current.

---

## B. Needed soon after the switch

### B6. A step needs to read more than one other step
*Already on core's list ([status.md](../status.md) D1; P5 for single values).*

```python
w2["j"] = sc[mod.map(over=[w2["a"], w2["b"]])]
w2.step("j").problems
# ("map over '[<a>, <b>]', which is not an earlier step",)
```

**Ask:** P5 (using a value from another step as a parameter) covers most of how
the formula bar uses references like `step1.col`, so it comes first. `join`
replaces `merge_steps`.

### B7. Progress updates while a step runs
*New.*

```python
inspect.signature(grid.Workflow.run)
# (self, step_id, tools=None) -> Step        ← no callback
w.step("s").output.progress()
# '3/3'                                        ← only readable after it finishes
```

**Ask:** a callback, e.g. `on_unit(step_id, unit, record)`, so the app can stream
per-row progress.

### B8. Re-run only the failed rows
*Already on core's list ([react-api.md](../react-api.md) §11).*

`.failed` correctly gives the failed rows, but nothing re-runs only those
(`hasattr(grid.Workflow, "redrive") == False`).

**Ask:** `wf.redrive(step_id)` that keeps the rows that succeeded.

### B9. A pluggable results store
*Already on core's list ([status.md](../status.md) D5).*

Results sit inline on each step, and `to_session_json()` raises `PayloadError`
for anything that isn't plain data. The app keeps its own per-session store, so
this is less urgent — what it needs is an **interface** to plug that store into.

---

## C. Not blocking

### C10. Make the workflow JSON format stable before P0 lands
Core's planned **P0** (a tool call that can contain another call,
[migration-plan.md](../migration-plan.md)) will change the operation JSON.

**Ask:** bump the existing `version` field and accept version 1 for at least one
release, so saved workflows keep loading.

### C11. Real `timeout`, async and cancellation
*Already on core's list ([status.md](../status.md) §4 B5).* `timeout` currently
records the value and does nothing.

---

## D. Not needed from core

Already working on the grid model, or the app doesn't need them:

- **Duplicate tool ids** — now warn when one replaces another (`003` item H resolved).
- **`DataFrame` parameters** — show as type `DataFrame` in the palette (`003` item J resolved).
- **`validate()`, `from_dict`/`from_json`, full-session round-trip** — all working.
- **Resource injection** — the app only uses `ResourceSpec` to group its built-in
  tools by name, which needs no core feature.

---

## Summary table

| # | tier | ask | core status |
|---|---|---|---|
| A1 | blocking | richer `catalog()` params (`choices`, `description`, `nullable`, inner `Optional`) | **✅ built** |
| A2 | blocking | `modifier_catalog()` → JSON verb/settings (`GET /modifiers`) | **✅ built** |
| A3 | blocking | source step from a no-input tool returning a DataFrame | **✅ built** |
| A4 | blocking | `Workflow` delete / remove / rename with dependency checks | **✅ built** |
| A5 | blocking | mark dependents `stale` on upstream change (no recompute) | **✅ built** |
| B6 | soon | multi-input (P5 value refs first, then `join`) | planned D1/P5 |
| B7 | soon | per-unit progress callback on `run` | new |
| B8 | soon | `redrive(step_id)` for failed rows only | planned §11 |
| B9 | soon | pluggable results-store interface | planned D5 |
| C10 | not blocking | stable workflow JSON `version` across P0 | new |
| C11 | not blocking | real `timeout` / async / cancellation | planned B5 |
