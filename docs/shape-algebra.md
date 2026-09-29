# Shape algebra — the target model

**Status: agreed design, not yet built.** [object-model.md](object-model.md)
describes what exists today; this describes what we are moving to and why.
Where they disagree, this document is the intent and that one is the present.

The goal in one sentence: **a spreadsheet for expensive, impure, failable
Python functions.** Excel can recompute on every keystroke because its
functions are instant, pure and cannot fail. Transcription, LLM calls and model
inference are none of those, and every difference below follows from that.

---

## 1. Vocabulary

Two words were doing double duty and caused most of our confusion. The tidy
meanings win; the workflow concepts get new names.

| term | means |
|---|---|
| **tool** | a plain Python function the user wrote |
| **step** | a node in the workflow: a tool plus how to run it, plus what it produced |
| **grid** | the rows × columns output of an **orchestrated** step |
| **row** | one unit of work — an observation |
| **column** | one variable about that unit |
| **cell** | one (row, column) intersection; holds any Python object |
| **index** | a row's stable address, preserved across steps |
| **payload column** | the column holding the produced object (conventionally `value`) |
| **ledger** | the per-row execution record, row-aligned with the grid |
| **shape** | a grid's rows × columns — what a verb changes, step to step (§3) |
| **alignment** | how `data` and `ledger` line up inside one Output — always row-for-row (§5) |

Deliberately retired: calling a step "a column" (it clashes with a variable),
and calling a step's output box "a cell" (it clashes with a datum).

### 1.1 Tool, Operation, Step, Output

These four were already defined in [object-model.md](object-model.md) §7–§9 and
[how-it-works.md](how-it-works.md). **Nothing here changes their meaning** —
this spec only changes what *Output* contains. Restated so we are aligned:

| term | is | lifetime |
|---|---|---|
| **Tool** | the registered capability — a plain Python function plus its `ToolDefinition` contract | declared once, at import |
| **Operation** | **one Tool + an ordered stack of modifiers** (higher-order functions), plus arguments | created when you wire a step |
| **ToolCall** | an Operation *compiled* to the executable form the engine runs | derived, `operation.to_tool_call()` |
| **Step** | one node of the workflow: **Operation + Output** | lives in the workflow |
| **Output** | what the Step produced — grid + ledger + meta | filled by running |

The pipeline, unchanged from the existing docs:

```
Tool  ──wrap it in HOFs──►  Operation  ──compile──►  ToolCall  ──run──►  Output
(a function)                (one tool +             (what the           (grid +
                             modifier stack          engine executes)    ledger)
                             + args)
```

> You *author* Operations; the engine *runs* ToolCalls; a Step *holds* the
> Operation and its Output.

#### An Operation is one tool wrapped by many modifiers

Not "a tool plus two config blobs" — **a tool with an ordered stack of
higher-order functions applied to it**, declared when you wire the step:

```python
wf.add(map_over(retry(timeout("score", 30), times=3),
                "step2", over="step1", concurrency=8))
```

**Order is semantics, not style.** These are different runs:

| composition | means |
|---|---|
| `map(retry(f))` | retry **each item** — 100 items, each may retry |
| `retry(map(f))` | retry **the whole fan-out** — one retry of all 100 |
| `map(timeout(f, 60))` | 60s **per item** |
| `timeout(map(f), 60)` | 60s for **the entire step** |

Today's flat `StepExecutionConfig` cannot express the second of each pair. Its
own docstring concedes it: *"`retries` means 'retry the unit' … the whole call
when `single`, one item when fanned out"* — the mode decides for you, and
"retry the whole fan-out" is simply unsayable. A stack makes it explicit.

#### Two classes of modifier

| class | modifiers | effect on shape |
|---|---|---|
| **shape verbs** | `map` `filter` `expand` `collapse` `group` `sweep` | change rows/columns (§3) |
| **execution modifiers** | `retry` `timeout` `cache` `gate` `concurrency` | shape-preserving |

Staged shape is the **fold of the shape verbs in stack order** — still pure
structure, still computable before anything runs.

**At most one shape verb per step.** Nothing in the algebra forbids
`filter(map(f))`, but a step is the unit the user sees, addresses and re-drives.
Two shape changes inside one step means an intermediate grid that has no cell
address and cannot be inspected or re-run. Keep every shape change visible as
its own column.

#### Modifiers are data

The stack is stored as an ordered list of descriptors, never as closures:

```python
Operation(
  tool="score",
  arguments={...},
  modifiers=[
    Modifier(kind="timeout", params={"seconds": 30}),
    Modifier(kind="retry",   params={"times": 3}),
    Modifier(kind="map",     params={"over": "step1", "concurrency": 8}),
  ],
)
```

**Stored innermost-first — plain nested-call evaluation order.** These are
ordinary nested function calls made when you wire the step, *not* decorators on
the tool: `map_over(retry("score", times=2), over="step1")` evaluates `retry`
first, which returns an `Operation`, and `map_over` then appends to its stack.

So the list `[retry, map]` means `retry` sits closest to the tool and runs
**per item**; `[map, retry]` would wrap the whole fan-out. Nothing attaches to
the function declaration — that is the point, since the same tool must be
usable `once` in one step and `map` in another.

Keeping the stack as descriptors rather than closures is what keeps staging,
serialization and UI construction alive (§6). And it is what
`OrchestrationConfig` and `StepExecutionConfig` dissolve into: the former
becomes the single shape verb in the stack, the latter becomes execution
modifiers.

**Output is the only thing this spec redefines.** Today the second half of a
Step is called `Data` and holds `StepStatus` + `StepOutput` + `StepError`.
Those three collapse into one `Output` object (§5), because per-row state needs
somewhere to live.

| today | becomes |
|---|---|
| `Data` (the concept) | **`Output`** — the object, not just a concept |
| `StepOutput` (`ref`, `value`, `kind`) | `Output.ref`, `Output.data`, `Output.meta` |
| `StepStatus` (one per step) | `Output.status` — now a **rollup** of the ledger |
| `StepError` (one per step) | a column in `Output.ledger`, one per row |

### 1.2 A naming wart to fix while we are here

`ToolCall.operation_id` and `ToolDefinition.operation_id` **name a Tool, not an
Operation** — the existing docs already concede this ("also readable as
`.tool_id`"). Since these are the exact four words we are clarifying, the field
should be renamed `tool_id`, with `operation_id` kept as a deprecated alias.
Leaving it guarantees this conversation happens again.

---

## 2. The invariant

> **Equip a tool with any orchestration → its output is a grid.
> No orchestration → a single value.**

No exceptions, including `collapse`, which returns a one-row grid. A bare
`int` from an unorchestrated step stays a bare `int` — an integer should not
cost a DataFrame.

This is what makes the UI simple: **shape comes from the step's mode, never
from the payload.** A user-uploaded table is always *one cell*, however many
rows it has; it becomes many rows only when a verb explicitly fans out over it.
No component ever has to ask "is this one cell or many?" — it reads the mode,
which is written on the step before anything runs.

---

## 3. The shape algebra

*Shape* here means the **step-to-step** relationship: how one step's grid
becomes the next one's. The separate question of how `data` lines up with
`ledger` **inside** a single Output is *alignment*, covered in §5.

Every orchestration first coerces its input to **n rows**:

| input | n rows are |
|---|---|
| an upstream grid | its rows |
| a table | the table's rows |
| a list / `Collection` | its elements |
| a single object | 1 row |

Then the verb transforms. Output **columns are a function of input columns** —
that is the "shape of the output depends on the shape of the input" part:

| verb | rows | columns | tidy name |
|---|---|---|---|
| `map` | n → n | input columns **+ payload** | `mutate` |
| `filter` | n → k ≤ n | input columns unchanged | `filter` |
| `expand` | n → m | input columns repeated per produced row **+ payload** | `unnest` |
| `collapse` | n → 1 (or k with `by=`) | payload + group keys | `summarise` |
| `group` | n → n | input columns **+ key column** | `group_by` |
| `sweep` | 1 → n×m | one column **per swept parameter** + payload | `expand_grid` |

Naming note: `expand` is tidyr's `unnest` and `sweep` is `crossing`. Only
`map`, `filter` and `group` match dplyr's names directly. We keep our names.

### Two consequences worth stating plainly

**`map` stops discarding the table.** Today `map` over a 3-row table returns a
`MapResult` of three values and the table is gone. Under `mutate` semantics it
returns the table plus a column:

```
   n  g  score
0  1  a     10
1  2  b     20
2  3  a     30
```

**`group` stops nesting.** It marks rows with a key column and keeps n rows;
reduction happens in `collapse(by=...)`. The "column of columns" problem
disappears rather than being solved:

```
group(over=step1, op=topic_of)        → step1's rows + a `topic` column   (n rows)
collapse(over=step2, by="topic", …)   → one row per topic                 (k rows)
```

---

## 4. The objects

### 4.0 The hierarchy, revised

Same notation as [object-model.md](object-model.md). **Bold** = new or changed.

```
App                         unchanged
├─ ToolRegistry             unchanged — tools, aliases, resource binding
│   └─ Tool                 a plain function + its ToolDefinition contract
├─ ResourceSpec*            unchanged — a resource and the tools bound to it
└─ Session
    └─ Workflow*
        ├─ graph()          **DERIVED, not stored** — edges from reference tokens
        └─ Step*            ordered steps
            ├─ Operation                 what to run — stays DATA
            │   ├─ tool                  ONE tool (by id)
            │   ├─ arguments             literals / references to earlier steps
            │   └─ **modifiers[]**       an ORDERED stack of higher-order fns
            │       ├─ shape verb        at most one: map | filter | expand
            │       │                    | collapse | group | **sweep**
            │       └─ execution mods    retry | timeout | cache | gate | concurrency
            │                            (order matters: retry(map(f)) ≠ map(retry(f)))
            └─ **Output**                what it produced
                ├─ **data**       DataFrame — the payload grid (immutable)
                │   ├─ index              stable cell address
                │   ├─ input columns      carried through
                │   ├─ payload column     the produced object (any type)
                │   └─ key / param cols   group keys, swept parameters
                ├─ **ledger**     DataFrame — per-row execution state (mutable)
                │   ├─ **status**         staged | running | completed | failed | **stale**
                │   ├─ error              per-row failure message
                │   ├─ attempts           retries used
                │   ├─ started_at/ended_at
                │   └─ **fingerprint**    what makes staleness computable
                └─ meta           dict — shape, tool id, run id
```

`*` = repeatable. `Output.view()` joins `data` and `ledger` on the index; that
join is the only thing the user sees.

Retired from the old hierarchy: `MapResult`, `Group`, `Groups`. `ItemOutcome`
survives only as an in-flight record during a run, materialized into `ledger`.

### 4.1 Unchanged

These are settled and stay as they are.

| object | role |
|---|---|
| tool (plain function) | the unit of work the user writes |
| `ToolDefinition` / `ToolParam` / `Guardrails` | a tool's public contract |
| `ToolRegistry` | tools by id, with aliases and resource binding |
| `ResourceSpec` / `ResourceContainer` / `Resource()` | injected runtime dependencies |
| `Collection` / `ListCollection` | lazy, versioned sources |
| `MediaAsset` / `MediaStore` | images and video held by handle |
| `ToolCall` | a durable, serialized invocation |
| `Workflow` / `SessionContext` / `CoreEngine` | ordered steps, payload store, execution |
| `Operation` | stays, and stays **data** — but now holds a modifier stack (§1.1) |

### 4.2 Changed

| object | change | why |
|---|---|---|
| `Step` | `Operation + Data` → **`Operation + Output`** | the ledger has to live somewhere |
| `StepOutput` | **absorbed into `Output`** — `ref` stays, `kind`/timings move to `Output.meta` | one object, not three |
| `StepStatus` | `PENDING` → `STAGED`; add `STALE` | the state already meant "staged"; staleness is new |
| `map` | returns a grid, not a `MapResult` | mutate semantics |
| `group` | adds a key column, no nesting | tidy semantics |
| `collapse` | gains `by=` | reduce within strata |
| `OrchestrationConfig` | dissolves into **the one shape verb** in `Operation.modifiers` | order-sensitive composition |
| `StepExecutionConfig` | dissolves into **execution modifiers** in the same stack | `retry(map(f))` vs `map(retry(f))` |

### 4.3 New

| object | role |
|---|---|
| **`Output`** | `data` + `ledger` + `meta`, with one merged `view()` — replaces `Data`/`StepOutput`/`StepError` |
| **`sweep`** | the cross-product verb: parameters in, a grid of cells out |
| **`Modifier`** | one entry in an Operation's stack: `kind` + `params`, ordered |
| **fingerprint** | a ledger column: what makes staleness computable |
| **graph derivation** | a *function*, not a stored object (§7) |
| **HOF constructors** | `once(...)`, `map_over(...)`, `sweep_over(...)` — build `Operation`s |

### 4.4 Retired

| object | replaced by |
|---|---|
| `MapResult` | the grid (values) + the ledger (status/error) |
| `Group` / `Groups` | a key column produced by `group` |
| `ItemOutcome` | demoted to an **in-flight record** during a run, materialized into the ledger |

---

## 5. Output: one grid, two frames

The output is **one** dataframe. The ledger sits beside it on the Step — the
same way `Step.status` already sits beside `Step.output`.

```python
class Output:
    ref:    str | None     # key into the session store, where `data` actually lives
    data:   DataFrame      # payload grid — immutable, referenced by downstream steps
    ledger: DataFrame      # execution state — mutable, index-aligned, never referenced as data
    meta:   dict           # shape, tool id, run id, timings
    def view(self): return self.data.join(self.ledger)
```

### The alignment invariant

Two different relationships are easy to conflate, so they get different words:

| word | relates | changes? |
|---|---|---|
| **shape** (§3) | one step's grid to the **next step's** grid | yes — that is what a verb does |
| **alignment** (§5) | `data` to `ledger` **inside one Output** | no — always row-for-row |

This section is only about the second.

> **`data` and `ledger` are row-aligned: one ledger row per grid row, sharing
> one index.**

They differ only in *columns* — that is the whole point of the split. The index
is what joins them, and `view()` is always a clean 1:1 join.

This holds exactly for the verbs that are 1:1 — `map`, `group`, `sweep`. For
the three that are not, "one row per **unit of work**" and "one row per
**output row**" come apart:

| verb | units attempted | output rows | aligned? |
|---|---|---|---|
| `map` / `group` / `sweep` | n | n | **yes** |
| `filter` | n | k ≤ n | no — n−k units produced no row |
| `expand` | n | m | no — one unit may yield many rows |
| `collapse` | n | 1 | no |

**Resolution: the ledger has one row per *unit of work*, indexed by the
input's index.** That gives three tiers rather than a binary choice:

| verb | alignment |
|---|---|
| `map` / `group` / `sweep` | indexes **coincide** — the invariant holds exactly |
| `filter` | ledger **⊇** data, same index space — `join` still finds every data row |
| `expand` / `collapse` | different spaces — data carries a **`source`** column naming its unit |

`filter` is the case that decides it. Four predicates run, two rows survive;
a unit-of-work ledger still answers *what happened to the other two*:

```
      status   kept             error
1  completed  False               NaN      ← predicate said no
3     failed  False  predicate raised      ← predicate crashed
```

Mirroring output rows instead would buy strict 1:1 everywhere at the cost of
that record — for the one verb whose job is dropping things. `source` is the
general link; for the 1:1 verbs it *is* the index, so it costs nothing there.

`Output` replaces `Data` and `StepOutput`, and absorbs `StepError`. The two-layer indirection survives unchanged:
`ref` points into `SessionContext.outputs`, and `data` is the inline copy —
exactly as `StepOutput.ref` / `.value` work today. An unorchestrated step has
`data` holding a single value and no `ledger`.

### Why not one frame

1. **Collisions.** Real tables already have columns named `value` and `status`.
   No prefix convention survives contact with scientific data.
2. **Mutability.** Status changes *while the step runs*; the payload must not.
   A downstream step referencing a payload that is being rewritten row by row
   is reading a moving target.
3. **Arrow.** The ledger is all scalar columns, so progress and error views
   always render natively. Only the payload column carries objects.

### What goes where

Rule of thumb: *would you ever group or filter your analysis by it?* → data.
*Does it describe how the run went?* → ledger.

| data (grid) | ledger |
|---|---|
| input columns carried through | `status` |
| the produced object | `error` |
| swept parameters | `attempts` |
| group keys | `started_at` / `ended_at` |
| | `fingerprint` |

### Referencing

| reference | resolves to |
|---|---|
| `step2` | the payload grid |
| `step2.ok` | grid rows whose ledger says completed |
| `step2.failed` | ledger rows that failed — the re-drive set |
| `step2.ledger` | the full execution record |
| `step2[0]` / `step2['q1']` / `step2['east']['q1']` | accessor paths (already implemented) |

---

## 6. Authoring: functions outside, data inside

Tools are plain functions; **orchestration is declared when the step is wired,
never on the function.** The same tool must be usable `once` in one step and
`map` in another.

Nested constructor calls give the functional call site — nothing attached to
the function:

```python
wf.add(map_over(retry("score", times=2), "step2", over="step1", concurrency=8))
```

Each constructor takes a tool id **or an Operation** and returns an `Operation`
with one more `Modifier` appended — so they compose, and the stack records the
order you wrote. They return **data, not closures**. This is not negotiable, because three things die with closures:

| | config as data | closure |
|---|---|---|
| reactive staging | reads `mode` → "one cell per item of step1" | opaque until it runs |
| `to_json()` / `from_json` | serializes | cannot serialize |
| dashboard building steps from dropdowns | constructs the data | cannot construct |
| fingerprinting | hashes resolved args | nothing stable to hash |

Reactive staging is the feature we care most about, and it is the one that
requires the orchestration to be readable before anything executes.

### 6.1 Three surfaces, one Operation

Nested calls are not the only readable spelling, and the prototype
(`simple_steps_core/grid.py`) offers three. **All three build the identical
`Operation` data** — they differ only in how the stack reads on the page:

```python
score.retry(2).map(over=step1)                       # chained — execution order
score[mod.map(over=step1), mod.retry(times=2)]       # bracket — decorator order
stack(mod.map(over=step1), mod.retry(times=2), score)  # vertical — one per line
```

All three are `map(retry(score))`: **retry runs per item**, and the stored
stack is `[retry, map]`, innermost-first as §1.1 requires.

The bracket form subscripts the tool with its modifier list, so it reads
exactly like the stacked `@` lines it mimics — outermost at the top, applied
bottom-up — and it stays a one-liner at the call site:

```python
wf["scored"] = score[mod.map(over=videos, concurrency=8), mod.retry(times=2)]
```

### 6.2 Brackets are decoration at run time

The right way to read `score[mod.map(...), mod.retry(...)]` is as a **runtime
decoration of the tool**: it changes what `score` does, before any data is
handed to it. That is genuinely a decorator — the objection in §6 is to **`@`
at definition time**, not to decorator-shaped syntax:

| | `@map(...)` above the `def` | `score[mod.map(...)]` |
|---|---|---|
| when it happens | import, once, forever | wiring, per step |
| the same tool `once` here and `map` there | ✗ pinned | ✓ |
| readable before anything runs | ✗ a closure | ✓ `Modifier` data |

So the two halves separate cleanly, and the second is where data arrives:

```python
decorated = score(threshold=5)[mod.map(over=videos), mod.retry(times=2)]
decorated                      # an Operation — data, serializable, stageable
decorated(videos_grid)         # now run it
```

Bound literals (`threshold=5`) are the **innermost** decoration, inside every
modifier — so a `retry` re-runs the same call and a `map` passes them to every
item. The row is the single positional unit of work and the literals arrive as
keywords, which is the same split the engine's `_run_item` already makes
between the item and its `shared` constants.

#### Three orders, one of them reversed

Order is semantics (§1.1), so it is worth being exact about which order is
which. For `score[mod.map(), mod.retry(times=1)]` over two rows:

| | order | why |
|---|---|---|
| **written** in the brackets | `map, retry` | outermost first, like stacked `@` lines |
| **stored** in `Operation.modifiers` | `retry, map` | innermost-first, per §1.1 |
| **wrapped** — when decoration happens | `retry, map` | the inside must be built before the outside |
| **entered** — when data arrives | `map, retry, retry` | outermost runs first; `retry` once per row |

So **written order = nesting order = run-time entry order**. That is the one
that carries meaning, and it is the one you type. The reversal is mechanical
and leaks into exactly one place: the stored list.

Because it leaks, both orders are named. `Operation.modifiers` is the stored,
innermost-first list the engine folds over; `Operation.layers` is the written,
outermost-first list. Anything showing a user their own stack — a repr, the
list editor, a diff of two steps — reads `layers`, so what is displayed matches
what was typed.

#### The one place the decorator idiom must change

The usual bracket-decorator recipe applies the decorators immediately and
hands back a wrapped function. Doing that here would cost all four rows of the
closure table above. Instead `__getitem__` returns an `Operation` — the stack
is only *appended as descriptors*, and application is deferred to
`compile_operation`, which builds exactly the object graph `@` would have.

Deferral is what makes this decoration *at run time* rather than at definition
time, and it is the whole reason the same syntax is safe here.

A layer that is not a `Modifier` is rejected at the bracket with a `TypeError`
saying so, precisely so a plain decorator cannot slip in and silently
un-serialize a step.

---

## 7. Lifecycle and reactivity

### A step is born staged

Defining a step **is** staging. There is no staging phase to add: a fresh step
has a spec (the template) and an empty output (the slot). Staging is a pure
read of structure — zero I/O — which is exactly why it can be reactive.

```
staged ──► running ──► completed
                   └─► failed
completed ──► stale        (an upstream input changed)
stale ──► running ──► …
```

`stale` is distinct from `staged` because there *is* an old value: the user can
look at last run's answer while knowing it is out of date.

### Staging sharpens in three levels

| known | when | the preview can say |
|---|---|---|
| shape | always, from the mode | "one cell per item of step1" |
| cardinality | once upstream has a value | "4 cells" |
| addresses | once upstream has an index | cells `[0, 1, 2, 3]` |

At level three the **staged ledger can be materialized before the run** — rows
with `status="staged"`. Running flips statuses in place. The UI renders one
structure through all three phases, and progress is
`(ledger.status == "completed").sum() / len(ledger)`. No separate progress
mechanism exists or is needed.

### The graph is derived, never stored

Dependencies are already implicit in the reference tokens sitting in
`step.call.arguments` and `orchestration.over`. Extracting them is ~10 lines and
costs **1.4 ms for 2,000 steps** — measured. Storing the graph would mean
keeping it in sync; deriving it cannot go stale.

### Staleness is a fingerprint comparison

One more ledger column:

```
fingerprint = hash(tool_id, tool_version, resolved_args_for_this_cell,
                   fingerprints of the upstream cells consumed)
```

A cell is stale iff its recomputed fingerprint differs from the stored one.
The payoff is incremental recomputation:

> **Append 50 rows upstream → only 50 new cells stage downstream.** Existing
> cells' fingerprints are unchanged, so their values stay valid.

This only works because rows have stable identity — the index, preserved
through `filter` and `group` by `.iloc` selection.

### Push vs pull

Staleness propagates **automatically**; recomputation happens **only when the
user runs**. Auto-recalculation is wrong here: the functions are expensive.

---

## 8. Known hard parts

Stated up front so they are designed for, not discovered.

1. **Tool code changes.** A Python function's behaviour cannot be reliably
   hashed (closures, globals, imports). `inspect.getsource` catches most edits;
   a manual `version=` on the tool is the honest escape hatch. Pick one.
2. **Resource changes.** Swap the transcription model and every fingerprint
   should change though no argument did. Resources must contribute a version.
3. **Side effects.** A tool that writes to a database must not be skipped as
   "unchanged". Needs `always_run`, opt-out rather than opt-in.
4. **Fingerprinting large arguments.** Hash the *reference plus version stamp*,
   never the payload.
5. **Never write the ledger row by row.** Mutating a DataFrame per completed
   item is **69x slower** than accumulating plain records and building the
   frame once at the end (measured at 5,000 rows: 65 ms vs 0.9 ms), and it
   degrades worse than linearly. Live progress comes from a counter, not from
   frame writes.
6. **Pause.** Orchestrators currently dispatch all items to `asyncio.gather`
   at once. Pausing means halting new acquisition while in-flight items finish,
   plus recording the resume point in the ledger. Must be designed into
   `_gather_outcomes`, not bolted on.
7. **`collapse` returns a 1-row grid.** The price of the invariant. Give grids
   an `.item()` for the 1×1 case.
8. **Object columns are not Arrow-serializable.** `to_parquet` hard-fails;
   Streamlit degrades to `repr` strings. Object payloads persist only when they
   are *handles* (`MediaAsset`, `Collection`) or have a `to_json` (plotly).

---

## 9. The pandas decision

**pandas becomes a core dependency.** Today it arrives only via the `dashboard`
extra, so a headless server pays ~30 MB it may not use. Taken deliberately:

- The **index** gives free, stable cell identity — the thing per-cell re-drive
  and incremental staleness both require.
- The **verbs** already exist and are correct.
- **Object dtype** holds plots, tables and media handles.

Writing our own `Frame` class means reimplementing `groupby`, `join` and
`explode` badly. Keeping the duck-typed `is_frame` check keeps the branching we
are trying to remove.

Be clear-eyed about what we are *not* buying: the payload column is `object`
dtype, so there is no vectorization over the values. We are using pandas as a
**ledger with typed metadata columns**, not as a numeric engine.

---

## 10. Sequence

Not a big-bang refactor. Each step leaves the system working.

1. **This document.** Cheapest place to disagree.
2. **`sweep`, tidy-native.** It is new, so nothing breaks, and it exercises the
   entire stack: grid output, params as columns, an object payload column, the
   renderer, the codec. The honest test of whether this holds up.
3. **`map` → mutate**, with `MapResult` coexisting during migration.
4. **`group` / `collapse`** to key-column semantics.
5. **Ledger + fingerprints + `stale`**, once the graph derivation lands.
6. **Retire** `MapResult`, `Group`, `Groups` when nothing depends on them.

If step 2 feels wrong in practice, we learned it cheaply and nothing is broken.

---

## 11. Open questions

- ~~The `Block` noun.~~ **Settled:** it is `Output`, the name the existing docs
  already gave that slot. No new noun.
- ~~Modifier application order in the stored list.~~ **Settled:**
  innermost-first, which is just nested-call evaluation order.
- ~~Ledger rows: units of work, or output rows?~~ **Settled:** one row per
  unit of work, indexed by the input's index; `expand`/`collapse` link back
  through a `source` column (§5).
- Does `Step.status` remain a field, or become a **rollup computed from the
  ledger**? A step where 3 of 100 rows failed is neither "completed" nor
  "failed" — the rollup rule needs stating.
- Tool versioning: source hash or manual `version=`?
- Does `sweep` take parameter lists directly, or a reference to a grid of
  parameter rows? The second composes better; the first reads better.
- Nested fan-out (a set of tables, then each table's rows): one flat grid with
  a source column, or a genuinely 2-D grid? §3 implies flat; unconfirmed.
