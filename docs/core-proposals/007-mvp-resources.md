# 007 — What the MVP needs from simple-steps-core

> **Received from the app** as its proposal 006 (2026-10-07); filed here as
> core's 007. It builds on core's [006 §2 (Resources)](006-tool-contracts-and-resources.md).
> Every "Today" line was produced by running core at `66afce2`.
>
> The work breakdown, with two examples per request and what runs today, is in
> [007-breakdown.md](007-breakdown.md). The dummies (`FakeDB`, `FakeLLM`) and
> their usage on today's core are appended to
> [examples/all_orchestrations/pipeline.py](../../examples/all_orchestrations/pipeline.py).
>
> References to "005" below mean the **app's** `005-core-changes.md` (asks
> K1–K17), not core's [005](005-reshaping-merging-and-status-grids.md).

This is the short list for the app's MVP (`docs/dev_plan/122-skeleton-complete.md`
in the app). It adds the resource requests (R1–R5) and points at the existing
asks in the app's `005-core-changes.md` that the MVP can't ship without (R6).
Everything else in that 005 stays as it is, after the MVP.

## Summary

| ID | Request | Blocks the MVP? |
|---|---|---|
| **R1** | A resource reference in an operation, `{"$res": "claude"}`, resolved at run from a container the caller supplies | **yes** |
| **R2** | Tools bound to a resource, written `res["db"].query(…)` | **yes** |
| **R3** | Resource types: built from literal settings only, published in the catalog with their bound tools | **yes** |
| **R4** | Every resource a workflow uses is saved with it (defined, loaded, and loaded with changes), with secrets saved only as pointers | **yes** |
| **R5** | Sections core doesn't know about survive a save and reload | **yes** |
| **R6** | The wrong-result asks already in 005: **K1, K3** (and K2) | **yes** |
| R7 | A standard handle for images and other media in saved outputs | after the MVP |
| R8 | Small fixes: failed rows turn integer columns to float; `over=[a, b]` crashes | after the MVP |
| R9 | Stages: a group of steps that runs as one | after the MVP |
| **Q1** | Decision: does core own sessions for the grid, or does the caller? | answer needed before R1 |

---

## Build order and tests

Build the core pieces first, in three slices, each tested on its own before the
app adopts it. **Slice 1 uses a dummy database and a dummy LLM handed to
ordinary tools as objects.** It proves the reference, the type check and saving,
without bound methods yet.

| slice | requests | what it proves |
|---|---|---|
| **1** | R1, plus the parts of R3/R4 that R1 needs (a declared type per resource) | a tool can take a resource object; the type is checked; the workflow saves without it |
| **2** | R2, rest of R3 | a resource's **marked** methods are tools: `res["db"].lookup[mod.map()](…)`; unmarked ones are refused |
| **3** | rest of R4, R5 | loaded resources with overrides, secrets as pointers, unknown sections kept |

R6 (the wrong-result fixes) is independent and can go in alongside any slice.
Slice 1 assumes Q1's recommended answer: the caller owns the live objects and
passes them to `run`.

### The dummies

Both are deterministic, so tests can assert exact output, and both count
their calls, so tests can check that one instance serves every row.

```python
class FakeDB:
    """An in-memory table: city -> region."""
    def __init__(self, table: dict | None = None):
        self.table = dict(table or {"SF": "west", "NYC": "east", "LA": "west"})
        self.reads = 0

    @tool                                   # marked: a bound tool (slice 2)
    def lookup(self, key: str) -> str | None:
        self.reads += 1
        return self.table.get(key)

    def reset(self) -> None:                # not marked: never a tool
        self.reads = 0


class FakeLLM:
    """Answers deterministically: the model name, then the prompt upper-cased."""
    def __init__(self, model: str = "fake-1"):
        self.model = model
        self.calls = 0

    @tool                                   # marked: a bound tool (slice 2)
    def complete(self, prompt: str) -> str:
        self.calls += 1
        return f"[{self.model}] {prompt.upper()}"


@tool
def enrich(city: str, db: FakeDB) -> str:
    """The region for a city, read from the database."""
    return db.lookup(city) or "unknown"


@tool
def summarize(text: str, llm: FakeLLM) -> str:
    """One line from the model."""
    return llm.complete(text)
```

`enrich` and `summarize` are **unbound**: they need a resource of the right
type but don't belong to one. That's what slice 1 tests. Slice 2 calls the
**marked** methods `FakeDB.lookup` and `FakeLLM.complete` directly, as bound
tools, and checks that the unmarked `FakeDB.reset` can't be used as one.
(`@tool` on a method is a placeholder spelling; how core marks a method is
its call. The app writes `@simple_step_tool`.)

**Until slice 2 lands, write the dummies without the marks.** With today's
core, `@tool` on a method breaks the method (see R2), so `enrich`'s call to
`db.lookup(...)` would fail in slice 1's tests.

### Slice 1: a tool takes a resource object

The tests write a reference exactly as the app's formulas do, `res["db"]`,
which serializes as `{"$res": "db"}`. In Python that's one small object whose
`[]` returns a reference, the way `wf["x"]` returns a `StepRef`. A bound tool is
then `res["db"].lookup(…)`, the same text in Python and in a formula. Declaring
a resource is written `wf.define(name, Type, **settings)`; that spelling is
core's call. Core only needs keyword arguments.
The app turns its positional form, `summarize[…](wf["notes"], res["llm"])`,
into `llm=` by matching the parameter's type before it sends the operation.

Setup shared by the tests:

```python
wf = grid.Workflow()
wf["readings"] = pd.DataFrame({"city": ["SF", "NYC", "SF", "LA"]})
wf["notes"]    = pd.DataFrame({"text": ["a", "b"]})
wf.define("db",  FakeDB)
wf.define("llm", FakeLLM, model="fake-1")
live = {"db": FakeDB(), "llm": FakeLLM(model="fake-1")}     # what the caller owns
```

| test | does | expects |
|---|---|---|
| **T1.1** runs | `wf["regions"] = enrich[mod.map()](wf["readings"], db=res["db"])`, then `wf.run("regions", resources=live)` | values `["west", "east", "west", "west"]`; `live["db"].reads == 4`: one instance served every row |
| **T1.2** runs with an LLM | `wf["s"] = summarize[mod.map()](wf["notes"], llm=res["llm"])`, run | values `["[fake-1] A", "[fake-1] B"]`; `live["llm"].calls == 2` |
| **T1.3** not a column | declare `wf["s"]` as in T1.2 before anything runs | `problems == ()`: `llm` is not looked up as a column of `notes`; staging predicts columns `text, value` |
| **T1.4** declares without the object | declare T1.2's step; never pass `resources` | `problems == ()`: declaring needs only the declared type |
| **T1.5** not loaded | `wf.run("s")` with no `resources`, or with `live` missing `llm` | a run-time problem naming the resource: *"resource 'llm' is not loaded"*; the tool never runs |
| **T1.6** wrong type | `wf["bad"] = summarize[mod.map()](wf["notes"], llm=res["db"])` | a declaration problem naming the parameter, its type and the resource's: `llm: FakeLLM` vs `db` (`FakeDB`) |
| **T1.7** subclass fits | `class TinyLLM(FakeLLM)`, `wf.define("tiny", TinyLLM)`, `summarize(…, llm=res["tiny"])` | `problems == ()` |
| **T1.8** unknown name | `summarize(…, llm=res["nope"])` | a declaration problem: *no resource named 'nope'* |
| **T1.9** saves without the object | `blob = wf.to_dict()` | the argument is `{"$res": "llm"}`; `blob["resources"]["llm"] == {"source": "defined", "type": "FakeLLM", "settings": {"model": "fake-1"}}`; no object anywhere; `json.dumps(blob)` succeeds |
| **T1.10** reloads and runs | `Workflow.from_dict(blob, tools, resource_types={"FakeLLM": FakeLLM, "FakeDB": FakeDB})`, run with `live` | same values as T1.2. `resource_types` mirrors the existing `tools` argument |
| **T1.11** redefining marks readers stale | `wf.define("llm", FakeLLM, model="fake-2")` after T1.2 ran | `s` is stale, as when a `$ref` it reads changes |

### Slice 2: marked methods are tools

| test | does | expects |
|---|---|---|
| **T2.1** bound map | `res["db"].lookup[mod.map()](wf["readings"])` (binding `key` from the `city` column via rename, as today) | same values as T1.1, read through the bound method |
| **T2.2** bound source | `res["llm"].complete[mod.source()](prompt="hi")` | one cell, `"[fake-1] HI"` |
| **T2.3** catalog | `catalog()` | lists `FakeDB` with setting `table` and tool `lookup` (**not** `reset`), and `FakeLLM` with setting `model` and tool `complete`, with their docstrings |
| **T2.5** unmarked is refused | `res["db"].reset[mod.source()]()` | a declaration problem: *"reset is not a tool of FakeDB; its tools are: lookup"* |
| **T2.6** tool code may call anything | an unbound tool whose body calls `db.reset()` | runs: marking controls what can go in a step, not what Python can call |
| **T2.4** saves | `to_dict()` of T2.1 | the operation names the type's tool and binds `{"$res": "db"}`; reloads and runs |

### Slice 3: loaded resources, secrets, other sections

| test | does | expects |
|---|---|---|
| **T3.1** override | a loaded `llm` (`model="fake-1"`) with the workflow overriding `model="fake-2"` | built as `fake-2`; saved as `{"source": "loaded", "as_loaded": {"model": "fake-1"}, "overrides": {"model": "fake-2"}}` |
| **T3.2** secret is a pointer | a type with `api_key: Secret`; define it with `api_key="sk-123"` | refused at declaration; `api_key="env:FAKE_KEY"` accepted, saved as the pointer |
| **T3.3** unknown sections | add `"stages"` and `"extensions"` to a blob, `from_dict(...).to_dict()` | both come back unchanged (R5 option a), or core documents option b |

## The model these requests implement

A **resource** is an object a workflow uses that is not data, such as an LLM
client, a database or a file system. Three rules:

1. **It is created from literal settings only:** `Claude(model="claude-opus-5-5")`.
   It never takes a table or a step, so it can always be rebuilt from how it
   was declared.
2. **It is visible and chosen per step.** A formula names the resource it
   uses. This differs from core 006 §2.1–2.2, where resources are injected by
   parameter name and never shown. The app needs users to see which resource
   a step uses, and its agent needs to be able to propose one.
3. **It is either defined or loaded.** *Defined*: declared in the workflow.
   *Loaded*: configured by the deployment, referenced by name, and adjustable
   by the user. **Either way, the workflow records it** (R4). Credentials
   live only in loaded resources and in environment variables.

How it reads in a formula (the app compiles these; core sees the JSON):

```
res["claude"] = Claude(model="claude-opus-5-5")            # define
=summarize[mod.map()](wf["notes"], res["claude"])          # a tool that needs a resource
=res["db"].query(sql="select * from visits")               # a tool bound to one
```

Like core's grid rules for references: **`wf["…"]` is a table, `res["…"]` is
a resource, and everything else is a literal.**

---

## R1. A resource reference in an operation

**Today:**
- A resource parameter is treated as a column:
  `summarize(text: str, llm: LLM)` over a grid with only `text` gives
  `("summarize() needs 'llm', which 'notes' does not have (it has text)",)`.
- Passing the object as an argument runs (`['A', 'B']`), but then the workflow
  can't be saved: `to_json -> TypeError: Object of type LLM is not JSON serializable`.

**Ask:**
- An argument may be `{"$res": "<name>"}`, next to literals and
  `{"$ref": "<step>"}`. In Python, a `ResRef("claude")`, mirroring `StepRef`.
- A parameter bound to a resource is excluded from the column bind and from
  staging. Like a `$ref`, it's resolved when the step runs.
- `Workflow.run(step_id, tools, resources=container)`: the caller passes the
  live objects, a mapping of name to object. Core resolves `$res` from it.
  A name missing from it is a **run-time** problem with a clear message
  (*"resource 'db' is not loaded"*), not a declaration error. A workflow is
  portable; its resources are environment.
- `to_json` writes `{"$res": "claude"}`, never the object.

**Type matching comes almost for free.** Today, `check` already compares
a bound object with the parameter's annotation:
`llm=DB()` where `llm: LLM` gives `("summarize() declares llm: LLM, but it is bound to <…DB object…> (DB)",)`.
For a `$res`, compare the parameter's annotation with the resource's
**declared type** (R4), so the check works before the resource is loaded.
Subclasses match (`Claude(LLM)` fits `llm: LLM`).

**Done when:** a workflow that uses `res["claude"]` declares cleanly, runs
with a container, reports a clear problem without one, refuses a resource of
the wrong type at declaration, and round-trips through `to_json`/`from_json`.

## R2. Tools bound to a resource

**Today:** the grid has no bound tools. Core's engine does (`ResourceSpec.tool`
registers `kv-get_key`), but it binds by name and lives outside the grid.
Putting the grid's `@tool` on a method is accepted but **breaks the
method**:
- `FakeDB().lookup("SF")` raises `TypeError: FakeDB.lookup() missing 1
  required positional argument: 'key'`, because the method is replaced by a
  `ToolHandle` that doesn't receive `self`;
- it registers a global tool named `lookup` with parameters `['self', 'key']`.

**Ask:**
- **Only methods the developer marks as tools are tools** (the app marks them
  with `@simple_step_tool`; core chooses its own spelling). Unmarked methods
  (`close`, `connect`, helpers) are never exposed: not in the catalog, and refused
  in an operation with the list of the type's real tools. Tool code can still
  call any method.
- **Marking a method must leave it an ordinary method.** `FakeDB().lookup("SF")`
  still works, and nothing is registered as a global tool. The mark only
  records that the type offers `lookup` as a bound tool.
- A marked method is a tool that acts on one named instance:
  `res["db"].query(sql=…)`, `res["db"].lookup[mod.map()](wf["ids"])`.
- In operation JSON, the instance is part of the operation, for example
  `{"tool_id": "ClinicalDB.query", "bound_to": {"$res": "db"}, …}`. The exact
  spelling is core's call. What matters is that the instance is a `$res`,
  resolved at run as in R1, and that the tool id names the type, so the
  catalog lists the tools once per type.
- Modifiers work the same as for any other tool.

**Done when:** `res["db"].query[mod.source()](sql=…)` and
`res["db"].lookup[mod.map()](wf["ids"])` declare, stage, run against the
container's `db` and round-trip.

## R3. Resource types

**Ask:**
- A way to declare a resource type in the grid, porting `ResourceSpec` where it
  fits: the class, its settings (the constructor's parameters, which must
  be literals), an optional health check, and its bound tools (the
  **marked** methods only, with contracts from their signatures and
  docstrings, as for `@tool`).
- Settings follow the existing literal rules. Declaring a setting as a secret
  (for example, annotated `Secret`) means it accepts only a pointer such as
  `"env:ANTHROPIC_API_KEY"` or the name of a loaded resource, never a value.
- `catalog()` lists resource types: settings, bound tools, and base types (so
  the app can show which resources fit an `llm: LLM` parameter).

**Done when:** the catalog lists a resource type with its settings and bound
tools, and a type whose constructor takes a non-literal is refused at
declaration.

## R4. Every resource a workflow uses is saved with it

**Ask:** `to_dict` / `from_dict` carry a `resources` section listing every
resource the workflow uses, whether defined in it or loaded by the deployment:

```jsonc
"resources": {
  "claude": {"source": "defined", "type": "Claude",
             "settings": {"model": "claude-opus-5-5"},
             "secrets":  {"api_key": "env:ANTHROPIC_API_KEY"}},
  "db":     {"source": "loaded", "type": "ClinicalDB",
             "as_loaded": {"url": "postgres://study"},   // non-secret settings, when saved
             "overrides": {"timeout": 30}}               // what the user changed
}
```

- A secret is never written as a value. Secret settings can't be overridden.
- A loaded resource is built from the deployment's settings plus the saved
  `overrides`, so the deployment's credentials always apply underneath.
- `check` resolves a `$res`'s declared type from this section, which is what
  R1's type check needs. It works with nothing loaded.
- Building the live objects from these declarations can be core's or the
  caller's. Either works for the app, as long as the declarations round-trip.

**Done when:** a workflow with one defined resource and one loaded resource
with an override round-trips unchanged, and loading it with neither available still declares
every step (problems appear only at run).

## R5. Unknown sections survive a save and reload

**Today:** extra top-level sections are dropped. A blob with `resources` and
`extensions` added comes back from `from_dict(...).to_dict()` as
`['version', 'steps']`.

**Ask:** either one works:
- **(a)** `from_dict` keeps top-level keys it doesn't recognize and `to_dict`
  writes them back unchanged; or
- **(b)** core states that its blob is one section of a larger file, and the
  app owns the file around it.

The app will add sections over time (`stages`, `ui`, `description`, step
`notes`, `extensions`). What matters is that a core upgrade never silently
drops one. This goes together with **K17** in 005: a version bump policy, so
older files keep loading.

## R6. The wrong-result asks from 005

Still **OPEN** at `66afce2` (`python scripts/core_asks.py` in the app):

- **K1**: a step reading a tool-backed source that hasn't run is declared
  invalid, and after `run_all` returns `{'value': [None]}`.
- **K3**: an operation used as an input is accepted, runs as a source, and
  reports *completed* with `{'value': [None]}`.
- **K2**: the inferred verb changes depending on whether the source has run
  (`collapse` with data, `map` before).

These block the MVP because the result looks successful. A user can't tell,
and the app's agent will propose exactly these shapes. Details and probes are
in 005.

## R7. A standard handle for media (after the MVP)

**Today:** core refuses, clearly, to save an output holding an arbitrary object:
*"cannot export column 'value': it holds a Image … Object payloads persist only
as handles or as something with a to_json (§8.8)"*.

**Ask:** port the engine's `MediaAsset` / `MediaStore` as the grid's standard
handle, so an image output saves as a content-hashed reference and loads back.
Until then the app stores media itself.

## R8. Small fixes (after the MVP)

- **Failed rows turn integer columns to float.** Core's own example: `risky`
  over `n = [1, 2, 3, 2]` gives `out: float64` (`100.0, NaN, 300.0, NaN`),
  because a failed row writes `NaN` into an `int64` column. Use a nullable
  integer type (`Int64`) or `object` for a payload column with failures.
- **`over=[wf["a"], wf["b"]]` crashes** with `TypeError: __str__ returned
  non-string (type list)` (005 K11). Combining steps now works through
  `join` / `stack` / `zip_`, so the request itself is done. What remains is
  refusing this form with a message that points at them. (The app's
  `core_asks.py` probe for K11 still tests this form, so it reports OPEN.)

## R9. Stages (after the MVP)

A named group of consecutive steps that runs as one unit and saves as a
section of the workflow. The engine has `Stage`. The grid needs
`run_stage(name)` and the section in R4/R5's format.

## Q1. Who owns sessions for the grid?

Core 006 §2.4 asks the same question. The app's preference: **core stays
at `Workflow`** and takes the resource container as an argument (R1). The app
already has sessions, per-user storage and identity, and owns them in its
`App` object (122 §1). If core would rather lift `App` / `Session` /
`ResourceContainer` free of the engine for the grid, the app can adopt those
instead. It needs to know which before R1 is built.
