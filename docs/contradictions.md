# Contradictions audit — streamlining usage

**Audited 2026-10-05. The audit itself changed no code; follow-up doc fixes have
since begun — see the Progress note below and the per-item ✓/◑/○ markers.**

Scope: the whole repo (`src/`, `docs/`, `specs/`, `examples/`, `tests/`, the
`.claude` skill). Focus areas requested: **do the shape modifiers work**,
**is the model closed** (both the algebra and general consistency), and **what
syntax is outdated**.

Headline: the shape modifiers *do* work — `tests/unit/test_grid.py` is
**214 passing**, the full suite is **408 passing**. The problem is not broken
code; it is that **two complete models of the same three nouns live in the
package at once**, and the documentation, skill, specs and examples each pin to
a *different one of the two* without saying so. A reader following one doc
writes code the neighbouring doc calls wrong.

Each item below is **C#** (contradiction) or **L#** (loose end), with file and
line evidence and a one-line streamlining recommendation.

> **Progress (2026-10-05).** Doc reconciliation has started on the shape
> algebra. `shape-algebra.md` was brought level with the 14 shipped verbs:
> §1.1 is now a three-tier modifier table (run-a-tool / no-tool / execution),
> a new **§2.1 "Tidy intent"** documents how a Python return becomes a tidy
> grid (the one-cell rule + the return-type→verb map), and **§3** is split into
> the two shape-verb classes with an added **index (row-identity)** column.
> Items annotated **✓ fixed** / **◑ partial** / **○ open** below.

---

## 0. The one root cause

There are two implementations of orchestration in the package, and **both define
`Workflow`, `Operation` and `Step`**:

| | engine model | grid model |
|---|---|---|
| lives in | [domain/models.py](../src/simple_steps_core/domain/models.py), [execution/](../src/simple_steps_core/execution/), [operations/](../src/simple_steps_core/operations/) | [grid.py](../src/simple_steps_core/grid.py) (one standalone 2786-line module) |
| how you fan out | `OrchestrationConfig(mode="map", over=...)` + `StepExecutionConfig(...)` | a modifier stack: `score[mod.map(over=...), mod.retry(times=2)]` |
| what `map` returns | `MapResult` (values + per-item outcomes) | a grid (input columns **+ payload**) + a per-unit `ledger` |
| `group` returns | `Groups` of `Group` records | the rows **+ a key column** (no nesting) |
| output object | `Data` = `StepStatus` + `StepOutput` + `StepError` | `Output` = `data` + `ledger` + `meta` |
| exported as | `Operation`, `Workflow`, `Step` (top level) | `grid.Operation`, `grid.Workflow`, `grid.Step` |

[grid-model.md §0](grid-model.md) and [status.md §1](status.md) acknowledge this
and prescribe the coping convention (`from simple_steps_core import grid`; import
the *module*, never the bare names). The convention is sound, but **almost every
other document ignores it**, which is where the contradictions below come from.

> **Streamline:** decide the single answer to "how do I fan a tool out over
> data?" and make every user-facing doc give *that* answer. Until the engine
> adopts the grid model, the honest framing is: *grid.py is the authoring
> surface being designed; the engine is what executes today.* Right now four
> docs present the grid surface as the real one and four present the engine
> surface as the real one, with no signpost between them.

---

## 1. Shape modifiers & algebraic closure

### C1 — "Closed algebra" is true in `grid.py`, false in the engine
[shape-algebra.md §3](shape-algebra.md) states `source` is "the verb a chain
starts with… what **closes the algebra**: every step is then (verb, tool,
arguments)," and `identity`/`gather` are the default tools that close the mapping
and reducing verbs ([§6.3](shape-algebra.md)).

- `grid.py` **is** closed: `Operation × Modifier → Operation` is tested
  (`test_grid.py` `test_every_modifier_application_returns_an_operation`), and
  `source`/`identity`/`gather` all exist ([grid.py](../src/simple_steps_core/grid.py)
  `source_`, `DEFAULT_TOOL`).
- The engine is **not** closed. Its mode enum is
  `Literal["single", "map", "filter", "expand", "collapse", "group"]`
  ([domain/models.py:247](../src/simple_steps_core/domain/models.py#L247)) — there
  is no `source` verb, so a source step is a *special case* (a plain tool call),
  which is exactly the non-closure shape-algebra says `source` removes.

> **Streamline:** state plainly that closure is a property of the grid model
> only. The sentence "every step is (verb, tool, arguments)" is false for the
> engine and should not be read as describing today's `ToolCall`.

### C2 — The shape-verb vocabulary has three different sizes  ◑ partial
> **Update (2026-10-05).** `shape-algebra.md` now carries **all 14** shipped
> verbs (§1.1 three-tier table, new §2.1, §3's two tables + index column), so the
> design doc no longer lags the implementation. **Remaining drift:**
> `object-model.md §converging` still lists 7, and the engine enum still 6 — the
> engine gap is inherent to the two-model split and only closes at migration.

Three authorities, three verb lists:

| source | verbs | count |
|---|---|---|
| [domain/models.py:247](../src/simple_steps_core/domain/models.py#L247) (engine) | single, map, filter, expand, collapse, group | 6 (5 shape) |
| [shape-algebra.md §3](shape-algebra.md) (design) | map, filter, expand, collapse, group, sweep, source, select, drop | 9 |
| [object-model.md §converging](object-model.md) | map, filter, expand, collapse, group, sweep, source | 7 |
| [status.md §4](status.md) / `grid.py` (built) | the above **+ widen, slice, rename, sort, distinct** | **14** |

The *implementation* (`grid.py`, 14 verbs) is now **ahead of its own design
doc** (`shape-algebra.md`, 9 verbs): `widen`, `slice`, `rename`, `sort`,
`distinct` are built and tested but never appear in the algebra spec. The design
doc reads as the future while being behind the present.

> **Streamline:** fold the 14 shipped verbs back into
> [shape-algebra.md §3](shape-algebra.md)'s table, or add a one-line "built
> beyond this table: …" note. One canonical verb list, referenced everywhere.

### C3 — "At most one shape verb per step" — undecided vs enforced  ○ open
> **Update (2026-10-05): still open.** One stale line remains —
> [shape-algebra.md:136](shape-algebra.md) (§1.1) still reads "proposed, not
> settled (§11)", even though [defining-operations.md:742](defining-operations.md)
> and `test_grid.py` (`at most one is allowed`) both treat it as enforced. Flip
> that line and §11.

[shape-algebra.md §1.1 / §11](shape-algebra.md) says this rule is "**proposed,
not settled**." [status.md §2](status.md) explicitly lists it as a *corrected
stale claim*: "one shape verb per step is undecided (**it is enforced**)," and
`test_grid.py` `test_two_shape_verbs_in_one_step_is_refused` pins the
enforcement. shape-algebra.md was never updated.

> **Streamline:** change §11's "proposed, not settled" to "enforced" (or delete
> the open question). It is decided and tested.

### C4 — Execution modifiers `cache` / `gate` / `concurrency` are documented but not built  ○ open
> **Update (2026-10-05): still open.** `shape-algebra.md §1.1`'s execution-modifier
> row still lists `cache`/`gate`/`concurrency` with no "planned" marker; only
> `retry` and `timeout` are built (and `timeout` is inert — L1).

[object-model.md §converging](object-model.md) and
[shape-algebra.md §1.1](shape-algebra.md) list execution modifiers as
`retry | timeout | cache` (+ `gate`, `concurrency`). [status.md §4 B5](status.md)
states these three are **not built** and that `grid.py` ships only `retry` and
`timeout`. So the modifier tables in the two design docs over-claim the execution
half of the stack.

> **Streamline:** mark `cache`/`gate`/`concurrency` as "planned" in the modifier
> tables, matching status.md, so nobody writes `mod.cache(...)` expecting it.

### L1 — `timeout` is present but inert
`grid.py` exposes `mod.timeout(...)` yet status.md §4 notes it is still waiting on
the async engine ("dead API rather than progress"). It validates and serializes
but does not enforce a timeout. Worth a docstring/`info()` note so it is not
mistaken for a working guard.

---

## 2. Documentation tense & authority contradictions

The docs are deliberately split by "tense" ([object-model.md header](object-model.md)),
but the split is not maintained consistently, so two docs give opposite answers
to the same beginner question.

### C5 — "How do I define a step?" has two incompatible answers
- [defining-operations.md](defining-operations.md), [writing-tools.md](writing-tools.md),
  [grid-model.md](grid-model.md), [react-api.md](react-api.md): the **grid**
  grammar — `wf["with_f"] = to_fahrenheit[mod.map(name="fahrenheit")](wf["readings"])`.
- [api-reference.md §OrchestrationConfig](api-reference.md),
  [config-isolation.md](config-isolation.md),
  [how-it-works.md](how-it-works.md), the [skill](../.claude/skills/simple-steps-core/SKILL.md §3),
  [integration.md](integration.md): the **engine** grammar —
  `Operation(step_id=..., orchestration=OrchestrationConfig(mode="map", over=...), execution=StepExecutionConfig(...))`.

Neither set says "the other spelling exists and is the other model." A user who
starts in `defining-operations.md` and then opens the skill finds the brackets
have vanished and been replaced by config objects.

> **Streamline:** put a single banner at the top of every orchestration-related
> doc: *"This page describes the {grid | engine} model. See §0 of
> contradictions.md / grid-model.md §0 for which one runs today."* Then pick one
> as the recommended authoring surface and label the other "execution internals."

### C6 — The skill contradicts the grid docs on `map`/`group` results
The [skill](../.claude/skills/simple-steps-core/SKILL.md) (§"DataFrames",
§"Groups") teaches `map → MapResult`, `group → Groups` of `Group` records, and
`step.ok`/`step.failed`. [shape-algebra.md §4.4](shape-algebra.md) explicitly
**retires** `MapResult`, `Group`, `Groups` ("map returns a grid, not a
`MapResult`"), and [defining-operations.md §group](defining-operations.md) teaches
`group` as "mark each row with a key column — nothing nests." So the skill
teaches the engine semantics while the prose docs teach the grid semantics. Both
are "current" depending on which model you mean.

> **Streamline:** the skill is the highest-traffic entry point. Make it state up
> front which model its examples run against (it is the engine model — its
> `OrchestrationConfig`/`MapResult`/`Groups` examples execute today), and add one
> pointer to the grid surface.

### C7 — `config-isolation.md` is simultaneously "implemented" and "superseded"
[config-isolation.md](config-isolation.md) says **"Status: implemented"** (the
shape/conduct split is real in the engine). [object-model.md header](object-model.md)
lists it as **"present, being superseded"** and the whole premise of
[shape-algebra.md §1.1](shape-algebra.md) is that `OrchestrationConfig` and
`StepExecutionConfig` **"dissolve into"** the modifier stack. So the two-config
design is at once the shipped truth and the thing being removed.

> **Streamline:** keep the "implemented" status, but add "superseded by the
> modifier stack in shape-algebra.md §1.1 (not yet in the engine)" so the reader
> knows it is a current-but-transitional design, not the end state.

---

## 3. Outdated syntax — the incomplete Option-A rename

The Option-A rename (`Operation*`→`Tool*`) landed in `src/`, `tests/` and the
`.py` examples but **not** in docs, specs, notebooks, or the TypeScript client
([repo memory confirms this](../src/simple_steps_core/api/public.py) exports
`ToolRegistry`/`ToolDefinition`/`ToolParam`/`register_tool`, not the old names).
The following still reference removed names and **break if executed**:

### C8 — `examples/simple_steps_core_walkthrough.ipynb` imports a name that no longer exists
`from simple_steps_core import CoreEngine, OperationRegistry, …`
([walkthrough notebook](../examples/simple_steps_core_walkthrough.ipynb)) — but
`OperationRegistry` is no longer exported (it is `ToolRegistry`). The notebook
also narrates "`OperationRegistry` turns Python functions into operations."
**This import fails today.**

### C9 — `specs/core_contract_for_frontrnd .md` imports four removed names
[specs/core_contract_for_frontrnd .md:65-66](../specs/core_contract_for_frontrnd%20.md)
imports `OperationRegistry, register_operation, OperationDefinition,
OperationParam`. All four are renamed. (The filename also has a stray space
before `.md`.)

### C10 — `examples/simple_server/README.md` tells users to use `@register_operation`
[examples/simple_server/README.md:10](../examples/simple_server/README.md) — the
decorator is `@register_tool`.

### C11 — `examples/simple_steps_backend/types.ts` mirrors the old Python names
[types.ts](../examples/simple_steps_backend/types.ts) declares `OperationParam`,
`OperationDefinition`, and (lines 63-93) `StepSpec` / `OrchestrationConfig` /
**`ExecutionConfig`**. The Python class is `StepExecutionConfig`, not
`ExecutionConfig` — so even against the *engine* model the TS name is stale. The
file's own header says "Keep them in sync with the Python models," which it no
longer is.

### C12 — `specs/011-…md` uses `ExecutionConfig` and `StepSpec` as the authoring type
[specs/011-tool-orchestration-and-agent-workflows.md:33,97,109](../specs/011-tool-orchestration-and-agent-workflows.md)
specifies `ExecutionConfig` (now `StepExecutionConfig`) and `StepSpec` (now
`Operation`). The agent-planner contract is defined over `list[StepSpec]`, a type
that no longer exists under that name.

> **Streamline (C8-C12):** one mechanical pass renaming
> `OperationRegistry→ToolRegistry`, `register_operation→register_tool`,
> `OperationDefinition→ToolDefinition`, `OperationParam→ToolParam`,
> `ExecutionConfig→StepExecutionConfig`, `StepSpec→Operation` across
> `docs/`, `specs/`, `examples/`, and the two notebooks. The walkthrough notebook
> (C8) is the urgent one — it is the advertised "getting started" artifact and it
> errors on the first import.

### C13 — `operation_id` vs `tool_id` is half-renamed
[shape-algebra.md §1.2](shape-algebra.md) calls `ToolCall.operation_id` /
`ToolDefinition.operation_id` a "naming wart" that "**should be renamed
`tool_id`, with `operation_id` kept as a deprecated alias.**" The code did the
**reverse**: the stored field is still `operation_id`, and `tool_id` is the
read-only *alias* property
([domain/models.py:99,137](../src/simple_steps_core/domain/models.py#L99)).
Meanwhile `ToolDefinition` already surfaces `tool_id` (tests read `d.tool_id`)
but `types.ts` and the JSON wire format still emit `operation_id`. So the field
is canonical one way in Python-attribute land and the other way in design-doc
land.

> **Streamline:** pick the canonical name and make the serialized field match the
> design intent (or amend §1.2 to say the alias direction was intentionally
> inverted). Right now the doc and the code disagree on which name is "preferred."

---

## 4. Internal contradictions within a single doc

### C14 — `status.md` disagrees with itself (and with reality) on test counts
[status.md §1](status.md) header: "**370 passing** (176 of them
`tests/unit/test_grid.py`)." [status.md §4](status.md): "Suite: **408 passing**."
Measured today: **408 total**, **214** in `test_grid.py`. §1 is stale on both
numbers; §4 matches the suite total but its `test_grid.py` figure is also behind.

> **Streamline:** make the count appear once (or derive it), so the file cannot
> contradict itself. Both §1 and §4 restate the suite size independently.

### L2 — `status.md` cross-references for its own authority
[status.md §top](status.md) says "When they disagree with this file, this one is
newer," yet also defers gap-tracking to grid-model.md §7 and api-reference.md.
Three places track overlapping gap lists ("not duplicated here" is asserted but
the verb list, test counts and modifier status do in fact overlap). This is the
general-consistency sense of "closure": the gap inventory is not single-sourced.

---

## 5. General closure / consistency loose ends

### L3 — `Operation` is an overloaded name across the public surface
The top-level package exports the engine's `Operation`
([api/public.py:43](../src/simple_steps_core/api/public.py#L43)); `grid.Operation`
is a *different class* with the same name. [grid-model.md §0](grid-model.md) and
[defining-operations.md §intro](defining-operations.md) both warn about it, which
is good — but it is a standing trap: `from simple_steps_core import Operation`
silently gives the engine one. The same is true for `Workflow` and `Step`.

> **Streamline:** this is the single biggest usability cliff. Until the models
> merge, consider *not* exporting a bare `Operation`/`Workflow`/`Step` and
> forcing `engine.Operation` vs `grid.Operation`, so neither can be grabbed by
> accident.

### L4 — `build/lib/simple_steps_core/` is a stale duplicate of `src/`
A full second copy of the package sits under
[build/lib/simple_steps_core/](../build/lib/simple_steps_core/). It lacks the
`streamlit/` package and may lag `src/` in other ways (build artifacts are not
regenerated on edit). It is importable noise and a source of "which copy am I
editing?" confusion.

> **Streamline:** add `build/` to `.gitignore` / delete the checked-in artifact.

### C15 — `defining-operations.md` says `MapResult` is gone; `how-it-works.md` relies on it
[defining-operations.md](defining-operations.md) / [shape-algebra.md §4.4](shape-algebra.md)
retire `MapResult`. [how-it-works.md:474,705](how-it-works.md) and
[api-reference.md:102](api-reference.md) document `MapResult.ok` /
`ItemOutcome` as live reference-resolution features (they are — in the engine).
Same object, "retired" in one doc and "how references work" in another.

### L5 — `docs/react-api.md` describes a contract no backend implements end-to-end
`react-api.md` and `types.ts` describe the HTTP/React surface over the **grid**
model, while the runnable backend under
[examples/api_server/](../examples/api_server/) and
[examples/simple_steps_backend/](../examples/simple_steps_backend/) serve the
**engine** model (`REGISTRY.list_definitions()`, `StepSpec`, `MapResult` JSON).
So the TypeScript types and the only working server are modelling different
backends.

---

## 6. Priority order to streamline usage

Ranked by "how likely is a user to hit it," not by effort.

| # | fix | status | why first |
|---|---|---|---|
| 1 | **C8** — repair the walkthrough notebook import (`OperationRegistry`→`ToolRegistry`) | ○ open | the advertised quick-start errors on line 1 |
| 2 | **C5 / C6** — one banner per orchestration doc naming its model (grid vs engine) | ○ open | removes the "which spelling is real?" confusion at the source |
| 3 | **L3** — stop silently handing out the engine `Operation` under a bare import | ○ open | the name collision is the sharpest runtime trap |
| 4 | **C9-C12** — mechanical Option-A rename pass over docs/specs/examples/notebooks/types.ts | ○ open | large but purely find-replace; kills a whole class of stale names |
| 5 | **C2 / C3 / C4** — reconcile shape-algebra.md with the 14 verbs, the one-verb rule, the unbuilt exec modifiers | ◑ C2 done; C3/C4 open | makes the design doc describe the implementation instead of lagging it |
| 6 | **C14 / L2** — single-source the test counts and gap lists | ○ open | stops the status docs contradicting themselves |
| 7 | **C13** — settle `operation_id` vs `tool_id` direction | ○ open | low-traffic but it is the exact wart the docs keep re-opening |
| 8 | **L4** — drop the `build/` duplicate | ○ open | removes an editable shadow copy |

### What we still need to fix (the short list, updated 2026-10-05)

**Cheap, do-now doc fixes (minutes each):**
- **C3** — flip "proposed, not settled (§11)" at [shape-algebra.md:136](shape-algebra.md) to "enforced"; update §11 to match.
- **C4** — mark `cache`/`gate`/`concurrency` as "planned" in [shape-algebra.md §1.1](shape-algebra.md)'s execution row (and L1: note `timeout` is inert).
- **C2 leftover** — bring [object-model.md §converging](object-model.md)'s 7-verb list up to the 14 (or link it to shape-algebra.md §3 as the one source).
- **C14** — correct the stale test counts in [status.md §1](status.md) (408 total / 214 grid).

**Higher-impact, decide-then-do:**
- **C8** — fix the walkthrough notebook's first-line import (the only *runtime* break in the docs).
- **C5 / C6 / L3** — the model-signposting problem: one banner per orchestration doc, and stop exporting a bare `Operation`/`Workflow`/`Step`. This is the real usability cliff and is the same decision the migration-plan hinges on.
- **C9-C12** — the Option-A rename sweep across specs/examples/notebooks/`types.ts`.

**Structural (tracked in [migration-plan.md](migration-plan.md), not quick doc edits):**
- The two-model split itself (root cause §0) — C1, C7, C15, L5 all dissolve once the engine is retired onto the grid model.

### What is *not* broken
- The shape modifiers themselves: `test_grid.py` is 214/214, full suite 408/408.
- The grid algebra's closure: `Operation × Modifier → Operation` holds and is
  tested; `source`/`identity`/`gather` close the mapping/reducing verbs.
- The engine's execution path: `OrchestrationConfig`/`StepExecutionConfig`,
  references, snapshots and resources all pass.

The work is **alignment, not repair**: pick one model as the authoring surface,
label the other as internals, and sweep the renamed vocabulary through the prose.
