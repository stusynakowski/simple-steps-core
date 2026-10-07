# 007 status — reply to the app's proposal 006

> **For the app team.** 2026-10-07. Answers the app's `006` (filed in core as
> [007-mvp-resources.md](007-mvp-resources.md)). The full breakdown, with two
> examples per request, is in [007-breakdown.md](007-breakdown.md).

## In short

- **Slices 1 and 2 are built:** R1, R2, and R3/R4 for *defined* resources. A
  tool can take a resource, a resource's marked methods are tools, the type is
  checked at declaration, and the workflow saves without the object.
- **Q1:** built on the app's preferred answer. Core stays at `Workflow`; the
  caller owns the live objects and passes them to `run`.
- **Not built yet:** slice 3 (loaded resources, overrides, secrets, R5), R6,
  and R7–R9.
- Tests T1.1–T1.11 and T2.1–T2.6 from the proposal all pass, written against a
  real workflow in `examples/all_orchestrations/pipeline.py`
  (`build_resources()`).

## Status by request

| ID | Status | Notes |
|---|---|---|
| R1 resource reference | **done** | `res["llm"]` → `{"$res": "llm"}` |
| R2 bound tools | **done** | `@bound_tool` on a method; `res["db"].lookup[...]` |
| R3 resource types | **partly** | literal-only settings, catalog, bases. **Not yet:** `Secret`, health check |
| R4 saved with the workflow | **partly** | `"source": "defined"` round-trips. **Not yet:** `loaded`, `as_loaded`, `overrides`, `secrets` |
| R5 unknown sections | open | still dropped; option (a) is planned for slice 3 |
| R6 K1 / K2 / K3 | open | K2 reproduces. K1 and K3 did not reproduce with our probes; **please send the exact probes from `core_asks.py`** |
| R7 media, R8 fixes, R9 stages | open | after the MVP, as agreed |
| Q1 sessions | **answered** | the caller owns them; see above |

## The spellings core chose

The proposal left these to core:

| What | Spelling |
|---|---|
| Declare a resource | `wf.define("llm", FakeLLM, model="fake-1")`, which returns `res["llm"]` |
| Reference one | `res["llm"]` (module-level `grid.res`; a `ResRef`) |
| Register a type | `@resource` on the class. Optional: `define` registers the type too |
| Mark a bound tool | `@bound_tool` on the method (the app's `@simple_step_tool`) |
| An unbound tool | an ordinary `@tool` function with a parameter typed as the resource |
| Run | `wf.run(step_id, resources={...})`, `wf.run_all(resources={...})` |
| Load | `Workflow.from_dict(blob, tools, resource_types={"FakeLLM": FakeLLM})` |
| Catalog | `grid.resource_catalog()`, separate from `catalog()` (see below) |
| Missing at run | raises `grid.ResourceNotLoaded` |

```python
from simple_steps_core.grid import bound_tool, mod, res, resource, tool

@resource
class FakeDB:
    def __init__(self, table: dict | None = None): ...
    @bound_tool
    def lookup(self, key: str) -> str | None: ...   # a tool; still an ordinary method
    def reset(self) -> None: ...                    # not a tool

@tool
def summarize(text: str, llm: FakeLLM) -> str: ...  # unbound: needs a FakeLLM

wf.define("db", FakeDB)
wf.define("llm", FakeLLM, model="fake-1")
wf["summaries"] = summarize[mod.map()](wf["notes"], llm=res["llm"])
wf["regions"]   = res["db"].lookup[mod.map()](wf["keys"])
wf["hello"]     = res["llm"].complete[mod.source()](prompt="hi")
wf.run_all(resources={"db": FakeDB(), "llm": FakeLLM(model="fake-1")})
```

## What the JSON looks like

This is what the app's formulas compile to:

```jsonc
"resources": {
  "llm": {"source": "defined", "type": "FakeLLM", "settings": {"model": "fake-1"}}
},
"steps": [
  {"step_id": "summaries", "operation": {
     "tool_id": "summarize", "input": {"$ref": "notes"},
     "arguments": {"llm": {"$res": "llm"}},
     "modifiers": [{"kind": "map", "params": {}}]}},
  {"step_id": "regions", "operation": {
     "tool_id": "FakeDB.lookup", "bound_to": {"$res": "db"},
     "input": {"$ref": "keys"}, "arguments": {},
     "modifiers": [{"kind": "map", "params": {}}]}}
]
```

- The `resources` section is written only when the workflow has resources, so
  blobs without them are unchanged. `version` stays `1`.
- A bound tool's id is `<DeclaredType>.<method>`, so the catalog lists each
  tool once per type. The instance is always `bound_to: {"$res": …}`.
- The app's positional form, `summarize[…](wf["notes"], res["llm"])`, still has
  to become `llm=` on the app's side, as the proposal planned. Core takes
  keywords only.

## Messages the app will see

All of these are declaration problems (in `step.problems` / `wf.validate()`),
unless marked otherwise:

| Case | Message |
|---|---|
| wrong type | `summarize() declares llm: FakeLLM, but it is bound to resource 'db' (FakeDB)` |
| unknown name | `no resource named 'nope' (declared: 'db', 'llm'). Declare it first: wf.define('nope', <Type>, ...)` |
| unmarked method | `reset is not a tool of FakeDB; its tools are: lookup` |
| resource left unbound | `summarize() needs 'llm', which 'notes' does not have (it has text). 'llm' is a resource (FakeLLM), not a column: bind it with llm=res["<name>"]` |
| not loaded (**run**) | `ResourceNotLoaded: resource 'llm' is not loaded. Pass it to run: wf.run(..., resources={'llm': <FakeLLM>})` |
| wrong live object (**run**) | `TypeError: resource 'llm' is declared FakeLLM, but the object passed for it is FakeDB` |
| bad setting (**define**) | `TypeError`: unknown setting, non-literal value, or a constructor parameter that isn't a literal type |

A subclass fits its base: a `TinyLLM(FakeLLM)` resource is accepted for
`llm: FakeLLM`.

## Behaviour to plan around

- **Define resources before the steps that use them.** A step declared first is
  invalid ("no resource named …"). `define` re-checks that step and fixes it,
  but any step *downstream* of it keeps its "input … which is invalid" problem
  until it is re-declared. (Re-declaring never re-checks dependents in core
  today.)
- **Redefining a resource** marks the steps that use it and have run as
  `stale`, the same as a changed `$ref` (T1.11).
- **Catalog:** resource types are in `grid.resource_catalog()`, not mixed into
  `catalog()`. Each entry has `settings`, `tools` (marked methods only, each in
  the usual `tool_entry` shape) and `bases`. If the app would rather have one
  call, say so; folding them into `catalog()` is easy.
- **Saved types are looked up by class name** in `resource_types=` and then in
  types registered with `@resource`/`define`. A blob naming a type the
  process doesn't have still loads. Unbound steps still declare (their type
  check is skipped); bound steps report that the type isn't available.

## Fixed along the way

These change behaviour the app may already rely on:

1. **The type check now sees through `from __future__ import annotations`.**
   Before, string annotations were skipped, so a wrong-typed bound object passed
   silently. Tools in modules that use that import may now report type problems
   they always had.
2. **`@tool` on a method is refused**, with a pointer to `@bound_tool`. It used
   to break the method and register a global `lookup(self, key)`.
3. **A full session reload (`to_session_json` → `from_json`) no longer marks
   valid steps invalid.** `from_dict` checked every step before restoring any
   saved output, so a `select` after a `map` was refused after a round-trip.
4. **Calling a source operation with keywords only binds them:**
   `tool[mod.source()](prompt="hi")` is the same as `tool.bind(prompt="hi")[mod.source()]`.

## Known gap, not fixed

**The light export (`to_json`) still loses source columns.** It carries no
source data, so after reloading, a column check downstream of a source fails
(`select names 'city', which the input does not have`). Use the session export
until it is fixed (by saving each source's column names, not its data).

## What we need from the app

1. **The exact K1 and K3 probes** from `scripts/core_asks.py`. Our versions
   didn't reproduce them.
2. **Confirm the spellings** above, especially `resource_catalog()` as a
   separate call.
3. **Slice 3 priorities:** whether loaded resources with overrides, or secrets
   as pointers, come first for the MVP.
