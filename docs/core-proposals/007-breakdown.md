# 007 — Breakdown: two examples per request

Work breakdown for [007-mvp-resources.md](007-mvp-resources.md). For each
request: where it lands in `grid.py`, the tasks, and **two examples**. Each
"Today" line is core at `66afce2`, re-checked 2026-10-07.

**Status (2026-10-07): slices 1 and 2 are built** (R1, R2, and R3/R4 for
*defined* resources). The dummies with their marks, and a workflow that uses
them, are in [pipeline.py](../../examples/all_orchestrations/pipeline.py)
(`build_resources()`). They are asserted as T1.1–T1.11 and T2.1–T2.6 in
[test_all_orchestrations.py](../../tests/integration/test_all_orchestrations.py).
Spellings core chose: `wf.define(name, Type, **settings)`, `res["name"]`
(`ResRef`), `@bound_tool` on methods, `@resource` on classes (optional; `define`
registers too), `run(..., resources=)` / `run_all(..., resources=)`,
`from_dict(..., resource_types=)`, `resource_catalog()`, and
`ResourceNotLoaded`. In JSON a bound tool is
`{"tool_id": "FakeDB.lookup", "bound_to": {"$res": "db"}}`.

**Still open:** slice 3 (loaded resources, `override`, `Secret`, R5 unknown
sections), R6, R7–R9, and the light-export gap below.

Shared setup for the target examples:

```python
wf = grid.Workflow()
wf["readings"] = pd.DataFrame({"city": ["SF", "NYC", "SF", "LA"]})
wf["notes"]    = pd.DataFrame({"text": ["a", "b"]})
wf.define("db",  FakeDB)
wf.define("llm", FakeLLM, model="fake-1")
live = {"db": FakeDB(), "llm": FakeLLM(model="fake-1")}
```

Q1 (who owns sessions) blocks R1. The breakdown assumes the recommended answer:
**the caller owns the live objects** and passes them to `run`.

| slice | requests | tests | depends on |
|---|---|---|---|
| 1 | R1, `define` + declared type (R3/R4 part) | T1.1–T1.11 | Q1 |
| 2 | R2, rest of R3 | T2.1–T2.6 | slice 1 |
| 3 | rest of R4, R5 | T3.1–T3.3 | slice 1 |
| any | R6 | the app's K1/K2/K3 probes | none |

---

## R1. A resource reference in an operation (slice 1)

**Touches:** `StepRef` / `_encode_ref` / `_decode_ref` / `_deref` (add `ResRef`
and `{"$res": …}` beside `$ref`), `_missing_columns` and `stage` (skip
parameters bound to a `ResRef`), `_type_mismatches` (compare against the
declared type), `Workflow.run` / `run_all` (new `resources=` argument),
`Workflow._resolve_arguments` (resolve `$res` from the container).

**Tasks**
0. **Done.** **Found while writing the example:** the existing type check skipped string
   annotations. Under `from __future__ import annotations` (as in pipeline.py),
   `llm: FakeLLM` is the string `"FakeLLM"`, `_value_fits` returns `None`, and
   `summarize.bind(llm=FakeDB())` validates clean. Resolve annotations with
   `typing.get_type_hints(fn)` (or `inspect.signature(fn, eval_str=True)`) in
   `_type_mismatches`, `_missing_columns` and `tool_entry`. R1's check depends on this.
   Pinned by `test_gap_type_check_skips_string_annotations`.
1. `ResRef(name)` plus a module-level `res` whose `[]` returns one. It has to
   be JSON-encodable as `{"$res": name}`.
2. `Workflow.define(name, Type, **settings)`: records the declaration (type and
   literal settings) in a new `wf.resources`. It does not build the object.
3. `check`: a `ResRef`-bound parameter is not a column. Resolve its declared type
   from `wf.resources`, use `issubclass` against the annotation, and report an
   unknown name.
4. `run(step_id, tools, resources=None)`: resolve each `ResRef` from the mapping
   before the tool runs. A missing name fails the step with *"resource 'llm' is
   not loaded"*, before any row runs.
5. Staleness: redefining a resource marks every step that reads it as stale.

### Example 1a: an unbound tool takes the database (T1.1, T1.9)

```python
wf["regions"] = enrich[mod.map()](wf["readings"], db=res["db"])
wf.run("regions", resources=live)

wf.step("regions").output.values   # ['west', 'east', 'west', 'west']
live["db"].reads                   # 4: one instance served every row
wf.to_dict()["steps"]["regions"]["operation"]["arguments"]
                                   # {'db': {'$res': 'db'}}
```

**Today:** there is no `res`. The nearest form binds the live object:
`enrich.bind(db=FakeDB())[mod.map(over=wf["readings"])]`. It runs and gives the
same values (see `resources_today()` in pipeline.py), but `wf.to_json()` raises
`TypeError: Object of type FakeDB is not JSON serializable`.

### Example 1b: declared but not loaded, and the wrong type (T1.4, T1.5, T1.6)

```python
wf["s"]   = summarize[mod.map()](wf["notes"], llm=res["llm"])
wf["bad"] = summarize[mod.map()](wf["notes"], llm=res["db"])

wf.validate()["s"]     # ()  (declaring needs only the declared type)
wf.validate()["bad"]   # ("summarize() declares llm: FakeLLM, but it is bound to resource 'db' (FakeDB)",)
wf.run("s")            # run-time problem: "resource 'llm' is not loaded"; summarize never runs
```

**Today:** leaving `llm` unbound gives
`("summarize() needs 'llm', which 'notes' does not have (it has text)",)`, so the
resource is read as a column. The type check already exists for a bound
object: `summarize.bind(llm=FakeDB())` gives
`summarize() declares llm: FakeLLM, but it is bound to <…FakeDB object…> (FakeDB)`.
R1 points that same check at the declared type.

---

## R2. Tools bound to a resource (slice 2)

**Touches:** `tool` (a method form that leaves the function alone and only
records a mark), `ToolHandle` (a bound variant that carries `bound_to: ResRef`),
`Operation.to_dict` / `from_dict` (write `bound_to`), `ResRef.__getattr__`
(returns the bound handle, or refuses an unmarked name).

**Tasks**
1. A method mark (spelling to be decided; the app uses `@simple_step_tool`). It
   must **not** replace the function or register into `TOOLS`. It only sets
   an attribute the type scan reads.
2. `res["db"].lookup` returns a handle with tool id `FakeDB.lookup` and
   `bound_to={"$res": "db"}`. `[]`, `.bind` and verb inference work as on any
   `ToolHandle`.
3. At run, resolve `bound_to` from the container (R1) and call the method on
   that instance.
4. An unmarked name is refused at declaration, with the type's real tools listed.

### Example 2a: a bound map and a bound source (T2.1, T2.2)

```python
wf["keys"]    = mod.rename(over=wf["readings"], columns={"city": "key"})
wf["regions"] = res["db"].lookup[mod.map()](wf["keys"])
wf["hello"]   = res["llm"].complete[mod.source()](prompt="hi")
wf.run_all(resources=live)

wf.step("regions").output.values   # ['west', 'east', 'west', 'west']
wf.step("hello").output.values     # ['[fake-1] HI']
wf.to_dict()["steps"]["regions"]["operation"]
    # {"tool_id": "FakeDB.lookup", "bound_to": {"$res": "db"}, "modifiers": [...]}
```

**Today:** `@tool` on the method breaks it (`FakeDB().lookup("SF")` →
`missing 1 required positional argument: 'key'`) and registers a global
`lookup(self, key)`. The stand-in in pipeline.py wraps one live instance's
method without registering it: `grid.ToolHandle(db.lookup, "db_lookup")`. It
runs, but the instance is captured in the operation, so it does not save.

### Example 2b: unmarked methods are refused, but tool code may call them (T2.5, T2.6)

```python
wf["oops"] = res["db"].reset[mod.source()]()
wf.validate()["oops"]   # ("reset is not a tool of FakeDB; its tools are: lookup",)

@tool
def lookup_fresh(city: str, db: FakeDB) -> str:
    db.reset()                       # any method is callable from tool code
    return db.lookup(city) or "unknown"

wf["fresh"] = lookup_fresh[mod.map()](wf["readings"], db=res["db"])
wf.run("fresh", resources=live)       # runs; live["db"].reads == 1 at the end (each row resets, then reads)
```

**Today:** nothing stops `ToolHandle(db.reset, "db_reset")` from becoming a
step. There is no type-level list of what is a tool.

---

## R3. Resource types (slices 1 and 2)

**Touches:** a new `resource_entry(Type)` beside `tool_entry`, `catalog()`
(a `resources` section or a `kind` per entry), and `define` (validate settings
against the constructor).

**Tasks**
1. Scan a type: its settings from `__init__`'s parameters (names, types,
   defaults, `Args:` docs), its bound tools from the marked methods (each a
   `tool_entry` minus `self`), its bases (the MRO, for "what fits `llm: LLM`"),
   and an optional `health()` method.
2. Refuse, at `define` or registration, a constructor parameter whose
   annotation is not a literal type (a `DataFrame`, a step, another resource).
3. A `Secret` annotation: the setting accepts only `"env:NAME"` or the name of a
   loaded resource (feeds T3.2).

### Example 3a: the catalog lists types (T2.3)

```python
grid.catalog()["FakeDB"]
# {"kind": "resource", "description": "An in-memory table: city -> region.",
#  "settings": [{"name": "table", "type": "dict | None", "default": None}],
#  "tools":    [{"tool_id": "FakeDB.lookup", "params": [{"name": "key", "type": "str"}],
#                "returns": "str | None"}],          # no "reset"
#  "bases":    ["FakeDB", "object"]}
```

**Today:** `catalog()` lists tools only. A wrapped bound method shows up as an
ordinary tool (`db_lookup`, params `key`), with no link to `FakeDB`.

### Example 3b: settings must be literals; secrets must be pointers (T3.2)

```python
class Warehouse:
    def __init__(self, seed: pd.DataFrame): ...
wf.define("wh", Warehouse, seed=df)
# refused: "Warehouse's setting 'seed' is a DataFrame; a resource is built from literals only"

class KeyedLLM(FakeLLM):
    def __init__(self, model: str = "fake-1", api_key: Secret = None): ...
wf.define("k", KeyedLLM, api_key="sk-123")        # refused: a secret takes a pointer
wf.define("k", KeyedLLM, api_key="env:FAKE_KEY")  # accepted; saved as the pointer
```

**Today:** there is no `define`, and nothing distinguishes a setting from any
other argument.

---

## R4. Every resource is saved with the workflow (slices 1 and 3)

**Touches:** `Workflow.to_dict` / `from_dict` (a `resources` section), and
`from_dict(…, resource_types=…)`, which mirrors `tools`.

**Tasks**
1. Slice 1: write `{"source": "defined", "type", "settings"}` for each
   `define`; read it back given `resource_types`. `check` uses it with nothing
   loaded.
2. Slice 3: `wf.load(name, Type, **as_loaded)` (or the caller supplies the
   deployment's settings) and `wf.override(name, **changes)`. These save as
   `{"source": "loaded", "as_loaded", "overrides"}`. A secret is never a value
   and is never overridable.
3. A loaded blob with an unknown type name still declares. The steps that use
   it report the problem at run.

### Example 4a: a defined resource round-trips (T1.9, T1.10)

```python
wf["s"] = summarize[mod.map()](wf["notes"], llm=res["llm"])
blob = wf.to_dict()
blob["resources"]["llm"]  # {"source": "defined", "type": "FakeLLM", "settings": {"model": "fake-1"}}
json.dumps(blob)          # succeeds; no object anywhere

again = grid.Workflow.from_dict(blob, grid.TOOLS,
                                resource_types={"FakeLLM": FakeLLM, "FakeDB": FakeDB})
again.run("s", resources=live).output.values   # ['[fake-1] A', '[fake-1] B']
```

**Today:** `to_dict()` has only `version` and `steps`, and the bound object
makes it unserializable.

### Example 4b: a loaded resource with an override (T3.1)

```python
wf.load("llm", FakeLLM, model="fake-1")      # what the deployment configured
wf.override("llm", model="fake-2")           # what the user changed
wf.to_dict()["resources"]["llm"]
# {"source": "loaded", "type": "FakeLLM",
#  "as_loaded": {"model": "fake-1"}, "overrides": {"model": "fake-2"}}
# built as FakeLLM(model="fake-2"); the s step now reads "[fake-2] A"
```

**Today:** there is no concept of a loaded resource.

---

### Found while building: a light reload loses source columns

Not a resource issue, but the resource example hit it. `to_json` (the light
export) carries no source payloads, so a reloaded workflow can't predict a
source's columns. Any column check downstream then fails:

```python
w["r"] = readings(); w["s"] = scale[mod.map(over=w["r"])]
w["t"] = mod.select(over=w["s"], columns=["city"])
Workflow.from_json(w.to_json(), TOOLS).validate()["t"]
# ("select names 'city', which the input does not have (it has value)",)
```

The example reloads through `to_session_json` instead. A fix is to save each
source's column names (not its data) in the light export.

A related bug in the **session** reload is fixed: `from_dict` checked every step
before restoring any saved output, so the same `select` was refused after a
full round-trip too. It now restores each step's output before checking the
steps after it, as declaring does.

---

## R5. Unknown sections survive (slice 3)

**Touches:** `Workflow.from_dict` / `to_dict` (keep an `extra` dict of
unrecognised top-level keys), and the version policy (the app's K17).

**Tasks**
1. Option (a): store unknown top-level keys verbatim and write them back.
   Recommended, because it is three lines and stops silent loss for good.
2. Document the rule in `docs/integration.md`: core never drops a section it
   does not own, and a version bump says what changed.

### Example 5a: the app's sections come back (T3.3)

```python
blob = pipeline.build().to_dict()
blob["stages"] = {"prep": ["readings", "scored"]}
blob["extensions"] = {"app": {"layout": "grid"}}
out = grid.Workflow.from_dict(blob, grid.TOOLS).to_dict()
out["stages"] == blob["stages"] and out["extensions"] == blob["extensions"]   # True
```

**Today:** `list(out)` is `['version', 'steps']`. Both sections are dropped
silently. (Re-checked against `build()`.)

### Example 5b: core's own new section doesn't collide

```python
blob = wf.to_dict()                      # has "resources" after slice 1
blob["ui"] = {"collapsed": ["notes"]}
grid.Workflow.from_dict(blob, grid.TOOLS, resource_types=...).to_dict()["ui"]
# {"collapsed": ["notes"]}; "resources" is parsed by core and not kept as unknown
```

**Today:** `ui` is dropped. Once slice 1 lands, `resources` would also be
dropped by an older core, which is the K17 case: an older core reading a
newer file should refuse it by version, not strip it.

---

## R6. The wrong-result asks (any slice)

**Touches:** `infer_verb`, `stage` for tool-backed sources, and `Operation` used
in `over=`.

**Tasks**
1. K2: make `infer_verb` depend only on the declaration (the tool's signature
   and the upstream's *declared* columns), never on whether the upstream has run.
2. K1: stage a tool-backed source from its return annotation, so a reader
   declares the same before and after the run, and never yields `{'value': [None]}`.
3. K3: refuse an `Operation` passed where a `StepRef` is expected, with a message
   that says to assign it to a step first.

### Example 6a: K2, the verb depends on run state (reproduced)

```python
@tool
def make_frame() -> pd.DataFrame:
    return pd.DataFrame({"n": [1, 2, 3]})

w = grid.Workflow()
w["src"] = make_frame[mod.source()]
w["s"] = add_n(w["src"])        # inferred: map
w.run("src")
w["s2"] = add_n(w["src"])       # inferred: collapse; same text, different step
```

**Target:** both infer the same verb (`collapse`, from `add_n`'s `(acc, n)`
signature) whether or not `src` has run.

### Example 6b: K1 and K3 (probe shapes needed)

The shapes behind K1 and K3 are in the app's `005-core-changes.md` and
`scripts/core_asks.py`. My probes on 2026-10-07 did **not** reproduce them:

- a `map` over a tool-backed `source` (`make_frame` above) validated cleanly and
  returned `{'n': [1, 2, 3], 'value': [10, 20, 30]}`;
- `scale[mod.map(over=scale[mod.map(over=w["a"])])]` raised
  `__str__ returned non-string (type Operation)` instead of running.

**Next step:** copy the two exact probes from the app's `core_asks.py` into
`tests/unit/test_capability_gaps.py`, marked `xfail(strict=True)`, so they turn
green when fixed.

---

## R7. A handle for media (after the MVP)

### Example 7a: today's refusal

```python
@tool
def pic(n): return Image()
w["i"] = pic[mod.map(over=w["readings"])]; w.run_all(); w.to_session_json()
# PayloadError: cannot export column 'value': it holds a Image, which to_json
# would silently write as {} and read back as an empty dict. Object payloads
# persist only as handles ...
```

### Example 7b: target

```python
@tool
def pic(n: int) -> MediaAsset:
    return store.put(png_bytes(n), mime="image/png")   # content-hashed
blob = w.to_session_json()      # the cell is {"$media": "sha256:…", "mime": "image/png"}
grid.Workflow.from_json(blob, grid.TOOLS, media=store).step("i").output.values[0].read()
```

---

## R8. Small fixes (after the MVP)

### Example 8a: failed rows keep integers

```python
pipeline.failure().step("out").output.data["out"]
# today:  float64  [100.0, NaN, 300.0, NaN]
# target: Int64    [100, <NA>, 300, <NA>]
```

### Example 8b: `over=[a, b]` is refused with a pointer

```python
w["c"] = scale[mod.map(over=[w["a"], w["b"]])]
# today:  TypeError: __str__ returned non-string (type list)
# target: a declaration problem: "over= takes one step; to read several, use
#         join(...), stack(...) or zip_(...)"
```

---

## R9. Stages (after the MVP)

### Example 9a: declare and run a stage

```python
wf.stage("prep", ["readings", "keys", "regions"])
wf.run_stage("prep", resources=live)     # runs the three in order, as one unit
wf.to_dict()["stages"]                   # {"prep": ["readings", "keys", "regions"]}
```

### Example 9b: a stage fails as one unit

```python
wf.stage("llm", ["s", "hello"])
wf.run_stage("llm")                      # no resources: the stage stops at "s"
                                         # with "resource 'llm' is not loaded";
                                         # "hello" stays pending, not half-run
```

**Today:** neither `stage` nor `run_stage` exists on the grid `Workflow`. Before
R5 lands, a hand-added `stages` section is dropped on reload.
