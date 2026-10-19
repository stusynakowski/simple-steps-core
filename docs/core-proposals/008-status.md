# 008 status — reply to the app's 008-core-changes

> **For the app team.** 2026-10-19. Answers the app's `008-core-changes.md`
> (filed in core as [008-core-changes.md](008-core-changes.md)), measured from
> the app's current pin, `a799d0e`. The design notes for each change are in
> [008-dev-plan.md](008-dev-plan.md). Progress is
> `python scripts/core_asks.py`: the app's probes, plus core probes for the
> C/N/O items.

## In short

- **34 of 38 probes pass** (3 at `a799d0e`). Every **priority 1** item is done,
  and so is every priority 2 item except C8 and parts of C5/C9. Phase 5 (the
  boundary: C3, K12, M, P, N, C12) is done too.
- **The saved format is now version 2.** Version 1 files still load. The
  app's own reader of saved JSON needs to learn the new tags (see
  [Saved format v2](#saved-format-v2)).
- **One owner decision overrides C10:** a failure the step doesn't catch now
  **stops `run_all`**. The new `mod.try_except(...)` lets a step's failures
  through (see [Failures](#failures-stop-the-run-unless-caught)).
- **Before bumping the pin,** read [Changes that can break the
  app](#changes-that-can-break-the-app). Eighteen behaviours differ from
  `a799d0e`.
- 545 tests pass. Each finished ask has a test written from its "Done when"
  line, in `tests/unit/test_008_asks.py`.

## Status by ask

| ID | Status | Notes |
|---|---|---|
| **K1** | done | An unrun source's columns are "not known yet", not empty. Column checks wait and are re-run when it runs |
| **K2** | done | Same verb before and after a run. An accumulator is recognized by name (`acc`, `accumulator`, `memo`, `carry`) |
| **K3** | done | An operation as an input raises *"an operation can't be an input yet; make it its own step…"* |
| **K4** | done | `over=` plus a call input raises *"Give the input once"* |
| **N2** | done, **as a warning** | An explicit argument wins over a same-named column, and the step warns: *"city='NYC' overrides the 'city' column of 'readings' for every row…"* |
| **C10** | done, **changed by owner** | Failure as state, root `cause`, blocked rows, forward refs. `run_all` now stops on an uncaught failure; see below |
| **C11** | done | Python literals saved exactly; non-literals refused at declaration |
| **C13** | done, **narrowed** | An explicit `name=` that already exists is refused unless `replace=True`. The default `value` overwriting `value` is a warning |
| **C14** | done | Missing is `None`; nullable int columns stay ints; `None`-worded type problems |
| **C1** | done | References in settings, positional args after the input, conversion by type |
| **C7** (+K9) | done | `rows`/`cols` selection, `select(rows=, columns=)`, string column names, reserved names |
| **C5** | **partly** | A source declares its columns via `-> Annotated[pd.DataFrame, TypedDict]`, and a payload's type comes from the tool's return. **Not yet:** record returns spread by `widen` |
| **C8** | open | The planned grid with known values and typed placeholder cells |
| **C9** | **partly** | `Step.plan` (certainty, because, resolve) and `mod.expect(...)`. **Not yet:** tuple-length and join bounds, marker rows |
| **C2** | done | Tools in `sort`/`group`/`collapse`/`distinct`/`select`/`rename` settings, saved as `{"$tool": id}` |
| **C6** | done | `grid.wf` |
| **C3** | done | `builtin_tools()`, `declared_tools()`, `shape_verbs()`, `resource_types()`, `payload_column()`, `check_modifier()`, `Operation.check()`, `freeze()`, `@tool(tags=…)` |
| **O** | done | A missing required setting is a declaration problem. `grid.check(op)` needs no workflow |
| **K12** | done | `mod.table()`: the tool gets the whole grid; its DataFrame is the step's grid. Inferred for a first parameter typed `DataFrame` |
| **N1** | done | `dict \| None` settings accept their members (also fixes `int \| None` bound literals) |
| **C12** | done | `**kwargs` tools warn, are `open`/untyped in the catalog, refused in strict mode; a keyword landing in them warns on the step |
| **N** | done | `mod.auto()`: saved as `auto`, resolved at run; the step reports the verb and why |
| **P** | done | `Operation.to_source()`; `eval(to_source(op), formula_names()) == op` is tested |
| **M** | done | `infer_verb` accepts `DB.lookup`, `(DB, "lookup")` or a handle |
| C15, C16 | open | Priority 3 |
| **K13** | done | `takes_tool`, `default_tool` in `modifier_catalog()` |
| **K5** | done | `mod.map(over="x")` raises; use `wf["x"]` |
| **K8** | done | `mod.select(...)(wf["r"])` works for verbs with a default tool |
| R3/R4 secrets, R5 | open | Priority 3 |
| K14, K15, K16, C4 | open | Priority 3 |
| **K11** | done | `over=[a, b]` raises, pointing at `join`/`stack`/`zip_` |
| **K17** | done | `version: 2`; v1 loads; a newer file is refused with a message |
| K18, R7, R9 | open | Later |
| **R8** | done | Failed rows keep an int column int (`Int64`) |

---

## Changes that can break the app

Each of these differs from `a799d0e`. They are ordered by how likely the app
is to hit them.

1. **`run_all` raises `grid.StepFailed`** on a failed cell its step didn't
   catch. Steps after it don't run. Add `mod.try_except(...)` where failure is
   expected.
2. **The saved JSON is version 2,** with new tags inside arguments and
   settings.
3. **The ledger has two new columns,** `cause` and `caught` (7 in all:
   `status, error, attempts, seconds, unit, cause, caught`).
4. **A one-column `$ref` argument to an untyped parameter is a list,** not a
   DataFrame. A cell is still its value, and a typed parameter gets its type's
   form.
5. **`wf["nope"]` no longer raises `KeyError`.** The step that reads it is
   invalid instead.
6. **`mod.<verb>(over="name")` raises.** Use `wf["name"]` (the workflow's own,
   or `grid.wf`). JSON keeps string ids.
7. **A non-literal argument** (a `date`, `Decimal`, `bytes`, an object or a
   function) is a declaration problem.
8. **An explicit argument wins over a same-named column,** with a warning.
   Before, the column won silently.
9. **A clashing explicit `name=`** on `map`/`group`/`expand` is refused
   unless `replace=True`.
10. **`retry()` without `times=` and `timeout()` without `seconds=`** are
    declaration problems.
11. **Integer column names become strings** (`2023` → `"2023"`). Names that
    collide once converted fail.
12. **A missing value is `None`.** A source column like `[1, None, 3]` is
    `Int64`, and a tool typed `n: int` over it is refused (*"r.n can be None,
    but inc() takes n: int…"*).
13. **A second positional argument binds** instead of raising: `scale(wf["r"],
    wf["w"])` means `weight=wf["w"]`.
14. **Type checks happen before a run** when the input declares its types: a
    tool's return annotation, a source's schema, or `mod.expect`. Mismatches
    that used to appear only after the run now appear at declaration.
15. **A variable named `rows` or `cols`** in the scope that declares a step
    makes `wf[...] = ...` raise *"Rename your variable"*. `rows`, `cols`, `wf`,
    `res`, `mod`, `op`, `join`, `stack` and `zip_` can't be tool, bound tool
    or resource type names.
16. **Running a step marks every step that already read it `stale`,** and
    `stale` now ranks above `failed` in `Step.status`.
17. **A source tool that raises** is a failed step, not an exception from
    `run`.
18. **A step downstream of an unrun tool-backed source** is valid at
    declaration and re-checked when the source runs, instead of being
    invalid.

## Failures stop the run unless caught

The owner's rule (2026-10-19) is that a failure stops the workflow unless the
step says it may fail. This replaces C10's "run_all runs everything else".

```python
wf["a"] = risky[mod.map()](wf["r"])
wf.run_all()
# StepFailed: step 'a' failed at a[1]: ValueError: boom. The run stopped.
#   Not run: b, other. Add mod.try_except(…) to the step to let this failure through.
```

`StepFailed` carries `step_id`, `cell`, `error` and `not_run`. Steps that
already ran keep their results. `wf.run("a")` on one step records the failure
without raising.

| Written | A failed row becomes | The run |
|---|---|---|
| (nothing) | failed | **stops** |
| `mod.try_except(default=0)` | completed with `0`; ledger `error` keeps `"caught ValueError: boom; used the default"`, `caught: true` | continues |
| `mod.try_except()` | failed, `caught: true` | continues; rows that read it are blocked (C10) |
| `mod.try_except(default=0, on=[ValueError])` | only `ValueError` is caught | other errors stop it |

`default=None` is a value, not "no default". `on=` takes classes and saves
names: `{"kind": "try_except", "params": {"default": 0, "on": ["ValueError"]}}`.
Order is semantics: `[mod.try_except(...), mod.retry(times=2)]` retries
first. A blocked row never stops the run by itself.

**Failure as state (C10), for steps that let failures through:**

| Ledger field | A cell whose tool raised | A row blocked by an upstream failure |
|---|---|---|
| `status` | `failed` | `failed` |
| `error` | `ValueError: boom` | `upstream cell a[1] failed` |
| `attempts` | ≥ 1 | `0` (the tool was never called) |
| `cause` | `null` | `a[1]: ValueError: boom` (the root) |

- `filter`, `select`, `sort` and the other rearranging verbs carry a failed
  row through, still failed.
- `collapse` over one gives a failed cell, without calling the reducer.
- A `$ref` argument that reads a step with any failed cell blocks every row.

At declaration, a step reading an invalid step says *"input 'a', which is
invalid (root cause: a: input 'nope', which is not an earlier step)"*.
`wf.root_cause(step_id)` returns `(step, problem)`. A reference to a step
declared later says *"'w' comes after 'a'; a step can only read earlier
steps"*.

**Kept, to confirm:** a step with a declaration problem has status
`invalid`, not `failed` as C10's text suggests. `invalid` means it can't run;
`failed` means it ran and cells failed.

## Phase 5: what the app can drop

| App shim | Replace with |
|---|---|
| reads of `grid.TOOLS`, `BUILTIN_TOOLS`, `SHAPE_VERBS`, `RESOURCE_TYPES`, `PAYLOAD` | `declared_tools()`, `builtin_tools()`, `shape_verbs()`, `resource_types()`, `payload_column(step)` |
| `check_modifier` (private) / `SHIM(core §O)` | `grid.check_modifier(kind, params)` or `operation.check()` |
| `REGISTRY.freeze` | `grid.freeze()` |
| tool "types" kept beside core | `@tool(tags=[…])`, read back as `catalog()[id]["tags"]` |
| `SHIM(core §K)`, `SHIM(core §A6)` (the legacy dataframe orchestrator) | `tool[mod.table()](wf["r"])` |
| `SHIM(core §M)`, `core_bridge.inferable_method` | `grid.infer_verb(DB.lookup, …)` |
| `SHIM(core §N)`: `AUTO`, its catalog wrapper, `resolve_auto` | `mod.auto()`; the chosen verb is `step.output.meta["auto"]` |
| `operation_formula.format_parts` | `operation.to_source()` (canonical: double-quoted strings, keyword arguments, modifiers in written order) |

**Two behaviour changes in phase 5:** a `**kwargs` tool now warns at
registration (and strict mode refuses it), and `table`/`auto` are new shape
verbs in `modifier_catalog()`.

## Saved format v2

`to_dict` writes `"version": 2`. `from_dict` reads 1 and 2, and refuses newer:
*"this workflow was saved in format version 3; this core reads versions 1 to
2"*.

**Values in `arguments` and in `modifiers[].params`:**

| Python | Saved |
|---|---|
| `wf["x"]` | `{"$ref": "x"}` |
| `wf["p"][1:5][cols["a":"c"]]` | `{"$ref": "p", "rows": {"start": 1, "stop": 5}, "columns": {"from": "a", "to": "c"}}` |
| `res["llm"]` | `{"$res": "llm"}` |
| a registered tool in a setting | `{"$tool": "first_letter"}` |
| `(1, 2)` | `{"$tuple": [1, 2]}` |
| `{1, 2}` | `{"$set": [1, 2]}` |
| `{1: "one"}`, or a dict with a `$` key | `{"$dict": [[1, "one"]]}` |
| `int`, `float`, `str`, `bool`, `None`, `list`, `dict` with `str` keys | plain JSON |

Settings may now hold `$ref` and `$tool`, not just literals. A selection's
`columns` always names its kind: `{"names": [...]}`, `{"from": ..., "to":
...}`, `{"positions": [...]}` or `{"positions": {"start": ..., "stop":
...}}`. Rows are an int, a list of ints, or `{"start": ..., "stop": ...}`.
Every spelling of a selection saves the same.

## New and changed API

| Name | What |
|---|---|
| `grid.wf` | `wf["x"]` = a step in whichever workflow the formula is assigned into (C6) |
| `grid.rows`, `grid.cols` | Selection indexers (C7). `grid.rows(df)` still works as the old coercion |
| `grid.Rows`, `grid.Cols`, `grid.SelectionError` | Selection parts, and the error a bad selection raises |
| `grid.RESERVED_NAMES` | Names no tool, bound tool or resource type may take |
| `grid.ToolRef` | A `{"$tool": id}` setting, decoded |
| `grid.FORMAT_VERSION` | `2` |
| `grid.StepFailed` | Raised by `run_all` on an uncaught failure |
| `grid.columns_unknown(output)` | True while a staged output's columns may grow (K1) |
| `mod.try_except(default=, on=)` | Let a step's failures through |
| `mod.expect(rows=, min_rows=, max_rows=, columns=, more_columns=)` | State what a step will produce. Used by staging, refused when it contradicts what core knows, checked at run |
| `mod.select(rows=, columns=)` | Every selection form (K9). `columns=` also takes a tool predicate |
| `mod.map/group/expand(replace=True)` | Allow an output to replace an input column (C13) |
| `mod.<verb>(...)(wf["r"])` | Tool-less verbs callable on a reference (K8) |
| `Step.plan` | `{"rows", "columns", "types"}`, each with `certainty` (`exact`/`stated`/`bounded`/`unknown`) and `because`/`resolve` when not exact |
| `Workflow.root_cause(step_id)` | Where an invalid step's problem starts |
| `modifier_catalog()[k]` | Gains `takes_tool` and `default_tool`. Settings that take a tool show `… \| tool` |
| `grid.check(operation)` | Reports missing required settings with no workflow (O) |

## What an unrun source shows

```python
class Readings(TypedDict):
    city: str
    n: int

@tool
def load(path: str) -> Annotated[pd.DataFrame, Readings]: ...

wf["all"]  = load[mod.source()](path="r.csv")
wf["some"] = load_raw[mod.source(), mod.expect(columns={"city": str}, more_columns=True)](path="r.csv")
wf["none"] = load_raw[mod.source()](path="r.csv")
```

```
all   source load · columns city (str), n (int) · rows unknown until it runs
some  source load_raw · columns city (str) + maybe more (stated) · rows unknown until it runs
none  source load_raw · columns unknown until it runs · rows unknown until it runs
```

`wf.step("none").plan["columns"]` is `{"certainty": "unknown", "names": [],
"more": true, "because": "load_raw returns a DataFrame with no declared
columns", "resolve": ["run load_raw", "annotate the return: -> Annotated[...]",
"state them on the step: mod.expect(columns=[…], more_columns=True)"]}`.
Declared columns and types flow downstream, and are checked before anything
runs. A source whose output breaks its schema, and a step that breaks its
`expect`, fail at run (*"expected 12 rows, got 2"*).

Under `from __future__ import annotations`, the schema class must live at
module level, or it can't be resolved and the source plans as `unknown`.

## Decisions for the app to confirm

1. **Stop on uncaught failure** (owner decision), replacing C10's "run
   everything else".
2. **N2 is a warning,** not a refusal: an explicit argument wins.
3. **C13 refuses only an explicit `name=`.** The default payload clash is a
   warning.
4. **`invalid` stays `invalid`,** not renamed `failed`.
5. **Whole-number float source columns with gaps become `Int64`**, by pandas'
   `convert_dtypes` rule.
6. **K2 recognizes accumulators by name** before the input runs.
7. **A selection as a tool's input stays refused.** Open question: allow a
   *row-only* selection there (`scale[mod.map()](wf["p"][1:5])`), since rows
   keep their ids?
8. **`resource_catalog()` stays separate from `catalog()`** (from 007).

## Still open

- **Priority 2:** C8 (planned grid), and the rest of C5 (`widen` of record
  returns) and C9 (tuple/join bounds, marker rows).
- **Priority 3:** C15, C16, R3/R4 secrets, R5, K14, K15, K16, C4.
- **Later:** K18, R7, R9.
- **Not carried through by combine verbs:** `join`/`stack`/`zip_` don't
  propagate failed cells yet.
- **Light export gap (from 007):** `to_json` doesn't carry a literal source's
  data or columns, so after a light reload a column check downstream of it
  can be refused when it would pass after a session reload. Use
  `to_session_json` until the light export saves column names.
