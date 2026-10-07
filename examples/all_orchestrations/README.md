# All orchestrations — the one example

The single canonical example for `simple-steps-core`. It defines **one registry
of tools** and one tiny tabular dataset, then wires a workflow that exercises
**every grid-model orchestration** in one place.

Everything here uses the **grid model** (`from simple_steps_core import grid`) —
the authoring surface being designed. See [docs/grid-model.md](../../docs/grid-model.md)
and [docs/shape-algebra.md](../../docs/shape-algebra.md).

## Three ways to use it, one source of truth

| form | file | run with |
|---|---|---|
| **script** | [pipeline.py](pipeline.py) | `python examples/all_orchestrations/pipeline.py` |
| **tests** | [../../tests/integration/test_all_orchestrations.py](../../tests/integration/test_all_orchestrations.py) | `pytest tests/integration/test_all_orchestrations.py` |
| **notebook** | [walkthrough.ipynb](walkthrough.ipynb) | open in Jupyter |

The script and notebook both import the builders from `pipeline.py`; the test
asserts their outputs. There is one registry and one workflow — the other two
forms are just different views of it.

## The registry (`pipeline.py`)

One tool per role the verbs need:

| tool | role | used by |
|---|---|---|
| `scale(n, weight=1)` | a value per row | `map` |
| `is_big(n)` | a predicate | `filter` |
| `label_city(city)` | a key function | `group` |
| `add_n(acc, n)` | a two-arg reducer | `collapse` |
| `fan_out(n)` | a row → a list | `expand` |
| `make_coords(n)` | a row → records | `expand` → `widen` |
| `grid_cell(model, window)` | a cell per combination | `sweep` |
| `risky(n)` | fails on some rows | failure handling |

Builtin reducers (`count`, `gather`, `total`, `first`, `last`) and `identity`
need no registration — the no-tool reshapers (`select`, `drop`, `rename`,
`widen`, `slice`, `sort`, `distinct`, `source`) apply `identity`.

## What it covers

- **All 14 shape verbs**: `source`, `map`, `filter`, `select`, `drop`, `rename`,
  `widen`, `slice`, `sort`, `distinct`, `group`, `expand`, `collapse`, `sweep`.
- **Both fan-out chains**: `group` → `collapse` (stratified summary) and
  `expand` → `widen` (longer then wider).
- **Execution modifiers**: `retry`, `timeout` (shape-preserving; order is
  semantics).
- **Verb inference**: passing a reference (`scale(wf["readings"])`) picks the
  verb — `map` / `filter` / `collapse` / `expand`.
- **Standard-type sources**: a `list` / `dict` / scalar / tuple is **one cell**,
  reshaped by a verb (`expand` a list, `widen` a dict or tuple → `c0, c1`);
  only a DataFrame carries its own structure.
- **Builtin reducers**: `gather`, `total`, `first`, `last`, `count`.
- **Chained fan-out**: `map` over a `map`.
- **Serialization**: full-session `to_json` / `from_json` round-trip.
- **Staging & validation**: `describe()`, `validate()`, positional access
  (`wf[0]` / `wf[-1]`), and `catalog()` before anything runs.
- **Resources**: a dummy DB and LLM with bound (`@bound_tool`) and unbound
  (`@tool` + `res["…"]`) tools, declared with `wf.define`, run with
  `resources=`, saved as declarations.
- **Failure**: a tool that fails on some rows → the ledger keeps every unit and
  `.failed` is the re-drive set.

## Resources (`build_resources()`)

A second workflow that uses a dummy database and a dummy LLM, for the resource
model in [docs/core-proposals/007](../../docs/core-proposals/007-mvp-resources.md).
Both dummies are deterministic and count their calls.

**The notation:**

| mark | on | meaning | written in a step |
|---|---|---|---|
| `@resource` | a class | a resource type, built from literal settings | `wf.define("db", FakeDB)` |
| `@bound_tool` | a method | **bound** tool: runs on one named instance; stays an ordinary method | `res["db"].lookup[mod.map()](wf["keys"])` |
| `@tool` | a free function with a resource-typed parameter | **unbound** tool: needs a resource, doesn't belong to one | `enrich[mod.map()](wf["readings"], db=res["db"])` |
| (none) | a method | never a tool; tool code may still call it | — |

| name | kind |
|---|---|
| `FakeDB.lookup(key)` | bound |
| `FakeLLM.complete(prompt)` | bound |
| `enrich(city, db: FakeDB)` | unbound |
| `summarize(text, llm: FakeLLM)` | unbound |
| `lookup_fresh(city, db: FakeDB)` | unbound, calls the unmarked `reset()` |
| `FakeDB.reset()` | not a tool |

The workflow declares resources, never objects. The caller passes the live
objects to `run`:

```python
wf = build_resources()                    # wf.define("llm", FakeLLM, model="fake-1"), ...
wf.run_all(resources=live_resources())    # {"db": FakeDB(), "llm": FakeLLM(), ...}
```

`resource_problems()` shows each refusal at declaration: wrong type, unknown
name, unmarked method, and a resource left unbound. `resource_roundtrip()`
saves and reloads it; the save holds `{"$res": "llm"}` and a `resources`
section, never an object.

## The data

Four observations of two variables — a `city` and a reading `n`:

```
city   n
 SF    1
NYC    2
 SF    3
 LA    2
```

Tiny on purpose: every count in the test is checkable by hand.
