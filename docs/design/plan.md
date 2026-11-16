# The dev plan

> **Draft, 2026-11-15; updated the same day for the app's plan 136.** Phase 4
> is done: core 1.0.0–1.0.2 shipped the grid model, and the app runs on 1.0.2.
> Phase 4's plan and the app's migration guide are in [docs/old/](../old/)
> ([plan-phase4.md](../old/plan-phase4.md),
> [app-migration.md](../old/app-migration.md)). This page orders what comes
> next. Nothing here lands without the owner's yes; the choices it needs are §7.
>
> The app's own plan is its `docs/dev_plan/136-consolidation-plan.md`
> (*Consolidation: core ↔ app, features, polish*). It has its own phases P0–P8;
> this page writes those as **136-P0** … **136-P8**, and its tracks as
> **136-A** … **136-E**. What it asks of core is §3.4.
>
> | Page | Holds |
> |---|---|
> | **this one** | where core is, the order of work, what core won't build, the changes the app will see |
> | [model.md](model.md) | what core is, each rule marked built or not |
> | [decisions.md](decisions.md) | every decision; the ids below (WR1, PL2, D43, …) are its rows |
> | [observations.md](observations.md) | what working on core has shown, and why this plan leads with consolidation |
> | [core-asks/](core-asks/) | the app's requirements of core, and the probe that tests them |

## 1. Where core is (run 2026-11-15, at `dbaf4c7`)

| Check | Result |
|---|---|
| `pytest` | 946 passed, 5 xfailed (W9, W18, S6 D23, S7 D33, an S3 CA-D1 case) |
| `docs/design/core-asks/probe.py` | 85 pass, 0 fail, 0 skip |
| `scripts/core_asks.py` | 36 of 39 (open: K14 progress, K15 re-run failed rows, K16 output store) |
| `tutorial/tutorial.py` | 118 lessons: 117 ✓, 1 ? (C11, an inline expression as a combine's input; refused by EX5) |
| `tutorial/handover.py` | 59 checks: 53 ✓, 4 ✗ (K23, K28b, R7, R9), 2 ? |
| Size | `src/` 14,599 lines; `workflow.py` 3,665 (139 methods), `checks.py` 2,313 |
| Speed (50 `map` steps in a chain, 1,000 rows) | `formula(text)` + `k.check` of a new step: **1.4 ms**; an edit at the top re-checking all 50: **107 ms** |
| The app | pins `dbaf4c7`; reads formulas with core's `formula()`; `core_bridge.py` holds seven shims against core (P1) |

**What's strong:** one model, lineage on every row, refusals that write the
fix, per-cell failures, and the test net (the invariant check after every
step of every test, the property tests, the probe). **What's weak:**
consolidation that was decided and never done (observations F4, L2), states
still partly kept as flags, and app-side workarounds core doesn't know about
(observations L3).

## 2. The goals of this phase

1. **Robust.** No crash, hang or raw Python error on any input the app can
   send; every app shim gone.
2. **Consolidated.** One answer to each question in one place: how two steps'
   rows relate, what state a step is in, which row a pick means. `workflow.py`
   split along those lines.
3. **Room to grow.** Features arrive as small additive pieces on a smaller
   core, each settled from a short list of principles (P6) instead of a ruling
   of its own. The first features are the ones the app's plan 136 needs (§3.4).
4. **Fast enough to feel live.** The app answers meaning in about 100–200 ms
   (136's tier 2). Core keeps checking an expression and re-checking after an
   edit inside that, and a test pins it.

The user's goals stand as phase 4 set them: a step is a list of rows and a row
is a dict; an expression says what each tool receives and how many times it
runs; reshaping never loses information silently; what you see is true; a
workflow is reproducible.

## 3. The order of work

One list, in order. A piece ends when its test passes, `scripts/sweep.py` is
green, the docs it touches are updated (rules.md for any behaviour change), and
it is committed and pushed. **Restructures** (no behaviour change) keep every
test green as they are. **Behaviour changes** are confirmed first and run the
500-example stress test before they are pushed.

| | Piece | What it does | Kind | Size | Needs | Status |
|---|---|---|---|---|---|---|
| **P0** | **Docs refreshed** | old pages to [docs/old/](../old/); out-of-date claims fixed; this plan | docs | small | — | ✓ 2026-11-15 |
| **P1** | **Close the app's shims** | each shim in the app's `core_bridge.py` fixed in core, as a patch release the app can pin (§3.1) | fixes | small | P-D5 | to do |
| **P1b** | **The grid objects, specified** (136-A, 136-P0) | core reviews the app's spec of Grid, Column, Row, Cell and pick against model.md, so it is written in core's words (P-D6), and adds what each object is to model.md. Docs only; runs alongside P1–P3 | docs | small | P-D6 | to do |
| **P2** | **States only from the store** | the old flags (`edited`, `stale`, `stale_reason`, `read_stale`) go; `stale` is read off the store like every other state (SM, ST5). The first piece of keeping results (136-P4) | restructure | medium | — (SM decided) | to do |
| **P3** | **One row relation, and a smaller `workflow.py`** | each verb declares its row map in its plan (PL2); one function answers how two steps' rows relate (WR1); then `workflow.py` and `checks.py` split by concern; a speed test pins goal 4 (§3.2). Row maps are what incremental runs (136-P4) are built on | restructure | large | — (WR1, PL2 decided) | to do |
| **P4** | **Picks kept by row identity** | a saved pick holds its row's identity and works out its row number each time. Fixes W18 and W9 | behaviour | medium | P3; P-D3 | to do |
| **P5** | **Grammar leftovers** | D18, D19; PK7 at staging; EX11's per-cell type checks at run | behaviour | small | D18, D19 | to do |
| **P6** | **Principles, the public API, the round trip** | the principles list (H5); what is public and what versioning promises (P-D4); a property test that `formula(print(x)) == x` over generated expressions (EX7) | docs + test | small | P-D2, P-D4 | to do |
| **P7** | **What the app's plan 136 needs** | in this order: stages; the workflow as a script; the grid objects as types; formula parts and the shared corpus; keeping results (§3.4) | additive | medium–large | P-D7–P-D11 | after P1; see §3.4 |
| **P8** | **The other features** | §3.3, in the order the app needs them | additive | — | each its own | after P7 |
| **P9** | **The final docs** | README, writing tools, resources, modifiers, integrating, problems (the old T13) | docs | medium | after P7 | — |

**Why this order.** P1 first: the app ships on core today, and two of its
shims are live bugs. P1b is docs and unblocks the app's 136-P0, so it runs
alongside. P2 and P3 come before P7's largest item because they are its
foundation: incremental runs (136-I5) need states read off the store (P2) and
row maps (P3), so consolidation is on the way to the feature, not a detour.
P7's small items (stages, the script) touch neither and may go earlier if the
app is waiting on them (P-D1).

### 3.1 P1: the app's shims (read 2026-11-15 from the app's `core_bridge.py`)

| Shim | What the app works around | Core's fix | Checked |
|---|---|---|---|
| **C37** | `k.view` / `k.cell` crash on a cell holding an array (an image): `_plain` calls `.item()` on anything with a dtype | unwrap numpy scalars only | **reproduced**: `ValueError: can only convert an array of size 1 to a Python scalar` |
| **C45** | `formula('wf["s"][1][2]')` raises `SelectionError`, not `FormulaError` | every refusal from `formula()` is a `FormulaError` | **reproduced** |
| C33 | `inspect.signature(tool)` is `(*args, **kwargs)`, not the function's | a tool carries its function's signature | to run |
| C34 | the app's parser checks a modifier's settings as you type through core internals (`check_modifier`, `shape_verbs`) | a public check, `cat.check_modifier(name, settings)`, or the same through `describe()` | to run |
| C18 | a tool's description is its docstring's first line, not its first paragraph | the first paragraph | to run |
| C36 | `describe()` lists a retired `name=` default | **already fixed in core** (`default_is: "the step's name"`): the app can drop this shim | run |
| C32 | a kernel can't be saved with its outputs | the output store, P7 (keeping results) | waits |

Each is one piece and one patch release (`1.0.3`, …), with a test that fails
without it, and a row in §5.

### 3.2 P3 in pieces

Each piece keeps every test green, unchanged.

1. **Row maps in the plan (PL2).** Each verb's plan says, for each output row,
   its input rows: kept, reordered, chosen, more, fewer, new. Built beside the
   helpers; a test checks the two agree on every property-test workflow.
2. **One relation function (WR1).** `relation(a, b)` → same rows / subset /
   child / group / unrelated, the nearest shared ancestor and the join that
   meets them. Every refusal, plan and view calls it; `_same_ids`,
   `_aligned_root`, `_matched`, `_reaches` and the pairing half of `trace` go.
3. **Split `workflow.py`** into modules by concern: rows and lineage, the store
   and states, running, editing. `Workflow` stays the object; the split is
   internal. Then `checks.py`, by what is checked.
4. **A speed test** (goal 4): on a 50-step chain of 1,000 rows, checking a new
   step stays under 20 ms and an edit at the top re-checks in under 200 ms
   (1.4 ms and 107 ms on 2026-11-15). Run outside coverage, so it measures the
   code and not the tracer.
5. **Measure:** `workflow.py` and the number of places a verb's identity rules
   live, recorded in observations.md.

### 3.3 P8: the other features, each its own piece

Grouped by what they serve; the owner picks the order. Ids are decisions.md's
and phase 4's.

| | Feature | Serves | Needs |
|---|---|---|---|
| WR2 | **A refusal carries its fix** as an operation, `Problem.fix`; `k.fix(name)` applies it. Never applied unasked. The app's step agent (136-E) proposes with it | the app, the agent | decided (yes) |
| WR3 | `join(a, b)` with no `on=` on related steps joins on the nearest shared ancestor, writing `on="#v"` | users | P3; decided (yes) |
| E·R7 | **Media handles**: images and files filed by content hash, loaded when read | images; plots (136-I9) | E-D1 |
| S9 | **Time and volatility**: pure, seeded, versioned, volatile tools; *as of* for tools that read the outside world (ST3); the seed (C-D2) | LLM and web tools, which today re-run every time | D41, D43–D46 |
| L4 | `k.trace(step, rows, to=ancestor)`: the pick of the rows behind them. 136-I6's "which input row did this come from" is already `k.cell(...)["inputs"]`, one step back; this goes back further | the app's lineage gutter | P3 |
| L7 | a plan whose columns are exact refuses a missing tool parameter at once | users | — |
| L3 | a join that drops rows warns, with the count | users | — |
| S7 | `melt`, `pivot`, `collapse(keep=…)`, built from pack and unpack (H3), not as new primitives | users | D33, D34, D36 |
| S6 | `initial=`, `sweep`'s values and `over=` in the call | users | D22–D25, D56 |
| S8 | the `empty` state; marks on `completed` | the app | D37–D40 |
| S10 | `k.data(…)`; the app's lineage expander (CA-B2) | the app | D48, D49 |
| F | the workflow as a table: step blocks side by side, rows lined up (G18) | the app | P3 |
| L1 | sharing settings for tools and resources | hosting | D50 |
| L2 | one join for several tables | users | when asked |
| L8 | the steps that need a re-run, for the app's toolbar (`needs_run()` gives it) | the app | — |

### 3.4 What the app's plan 136 asks of core

Plan 136 (app, 2026-11-15) organizes the owner's list I1–I10 into five tracks.
Each row below is checked against core 1.0.2 on 2026-11-15, with what core
builds. Tracks and items that are the app's alone are in §4.

| 136 | Asks core for | Core today (run) | Core's piece |
|---|---|---|---|
| **A** (I3, I4), 136-P0 | **Grid, Column, Row, Cell and a pick as real objects**, defined clearly, with how each is used by the UI, formula text, the agent and a terminal (owner: decided) | no such objects: `k.view` and `k.cell` return dicts; `wf["s"]` and `wf["s"][0][cols["n"]]` are both `StepRef` | P1b (the spec, in core's words, P-D6), then **P7c**: the types, returned by `k.view` / `k.cell`, each with `.to_dict()` giving today's dict exactly (P-D8); a pick its own type beside the step reference |
| **C·I5**, 136-P4 | **Keeping results**: an output store keyed by data version (K22, C32); **incremental runs by row state** (owner: decided): keep each row's result as it completes, and on a re-run compute only rows not `known` or whose inputs changed; progress and cancel (K23) | one output per step on screen, `KEEP = 4` in the store; no resume (`run(x, fresh=False)` means "on what the inputs show", not "continue"); per-row states exist | **P7e**, after P2 and P3: (1) rows filed as they complete (K22); (2) re-run by row state (K15, D42, PL3, PL4: the old L6); (3) progress and `cancel()` as a callback (K23, K14); (4) the output store's interface, so a kernel is saved with its outputs (C32, K16; closes the C32 shim). Each its own piece |
| **C·I6**, 136-P1 | which input row a value came from | **already there**: `k.cell("t", 1)["inputs"]` → `[{step: "s", row: 1, values: {"n": 2}, …}]`; lineage on every view row | nothing new; further back is L4 (§3.3) |
| **D·I7**, 136-P5 | **Stages**: a named group of consecutive steps, to organize the workflow; adds no inputs, outputs or computation; shown folded; a section in exported code (owner: decided) | none (R9; model.md §3 *planned*) | **P7a**: a stage in the workflow spec, kept valid by core through insert, move, rename and delete (P-D7) |
| **D·I10**, 136-P6 | the workflow as code, for a script, then a notebook, then other frameworks | each step prints (`step.formula`); no whole-workflow script | **P7b**: `k.to_python()`, a script that rebuilds the kernel in plain Python, its stages as sections, checked by a round trip (P-D9). Notebooks and other frameworks are the app's, over it |
| across tracks, 136-P0b | **the browser may predict; core decides**: a shared conformance corpus of formulas, run by the frontend against its reader and by the backend against core | `formula()` gives an operation and its printed form; no spans of the text | **P7d**: core's tests run the corpus too (kept in [core-asks/](core-asks/), like `probe.py`); `formula()` reports each part's span in the text, so spans are checked against core (P-D10) |
| **B** (I1, I2), 136-P2–P3 | a typed table typed into one step, `table[mod.source()](data={…})` (135 §4) | `table` is already a verb (`mod.table`) | the name clashes (P-D11); the literal table itself is a small built-in tool once named |
| **B** (I1) | "defining a function in a cell" | a kernel's catalog is fixed when it's made; a bare function is refused (EX9); formula text never runs code (EX13) | nothing in core: the app makes the function a tool and builds the kernel again with the new catalog (`Kernel.from_json(text, catalog)`), which works today (P-D12) |
| **E** (I8), 136-P8 | a step agent scoped to one step | `k.check(name, op)`; refusals that write the fix | WR2, `Problem.fix` (§3.3), when the app wants it |

**P7's order:** **P7a** stages and **P7b** the script are small, need neither
P2 nor P3, and may go right after P1 if the app is waiting on them. **P7c** the
types after P2, so a Cell's state comes from the store. **P7d** spans and the
corpus whenever the app's corpus exists. **P7e** keeping results after P3.

## 4. What core won't build

Core is the grid model and what it needs to run. These belong elsewhere, and a
request for one is answered by pointing there.

| Not in core | Where it belongs | Why |
|---|---|---|
| hosting many kernels, locks, eviction, memory budgets | the app | core gives the store and its `KEEP`; how much to hold is hosting |
| a `running` state | the app (SS6) | it's a fact about a process, not a workflow |
| users, auth, workspaces, file paths, multi-user deployment | the app (its plan 200, M1) | — |
| UI: palette categories, widgets, notes, colours, cell editing | `extras["simple_steps.…"]`, never read or hashed | removing it can't change an output |
| editing gestures: typing into cells, paste, upload, the fill handle, locks, "Make values" (136-B) | the app (its 134, 135): each gesture writes an expression core checks | core sees only the expression |
| prefab components and plots for tools, resources and cells (136-I9) | the app, named in `extras["simple_steps.ui"]` | a UI never changes an output |
| the browser's formula reader, for tokens, colours, spans and autocomplete (136 tier 1) | the app, behind the shared corpus | it predicts; core decides meaning |
| notebook and other-framework exporters (136-I10) | the app, over `k.to_python()` | core gives one exact script; formats are adapters |
| the agent, its sub-agents and their permissions (136-E) | the app | core gives `k.check`, and `Problem.fix` (WR2) |
| a blob store backend (a folder, a bucket) | the app plugs one in | core defines the interface (P7e) |
| a scheduler or autorun machinery | at most a policy over the store (SM) | autorun is "run what's stale and cheap", not new machinery |
| converters for old saved files | nowhere (D52) | no saved workspaces to keep |
| lineage across kernels or files | nowhere (model.md §12) | lineage lives inside one workflow |
| code in formula text, or a catalog that changes inside a kernel | nowhere (EX9, EX13, model.md §2) | a step runs only catalog tools, each hashed |
| a second spelling of anything, or a setting that does nothing | nowhere (EX1, C10) | one way to write each thing |
| a new verb that pack, unpack, choose, reorder or match can build | nowhere (H3) | each verb is ~6 properties to get right |
| `widen(sep=)`, a join of several tables, a declared source key | later, when a user needs one (PK8, L2, model.md §10) | today's refusals lose nothing meanwhile |

**And the other way:** a fact the app works out about a workflow (why a step is
stale, where a cell came from, whether an expression is valid) belongs in core.
When the app adds a shim or a computation of its own, it becomes a P1 row.

## 5. Changes the app will see

One row per piece that changes what the app sees, **added as it lands**, with
the release that carries it. (Phase 4's list is
[app-migration.md §3.8](../old/app-migration.md#38-what-the-expression-cleanup-changes-for-the-app).)

| Release | Piece | Change | What the app does |
|---|---|---|---|
| — | — | none yet | — |

## 6. Where phase 4's open items went

| Phase 4 | Open item | Now |
|---|---|---|
| S3 | D18, D19 | P5 |
| S4 | `var<n>` | built (S2, L21); the plan row was out of date |
| S11 | the old flags removed | P2 |
| S5f / D-picks | W9, W18 | P4 |
| D | K22, K23/K14, K15/D42 | P7e (keeping results) |
| D | R9 stages | P7a |
| E | C32/K16 the output store | P7e; R7 media handles, P8 |
| F, S6–S10 | as listed | P8 |
| L1–L8 | later, by decision | L5 (stages) P7a; L6 (lazy rows) P7e; the rest P8 |
| T6 | run the app's acceptance session against core alone | P1: the app's shims are what it found |
| T12 | `core_asks.py` at 39 of 39 | closes with P7e |
| T13, phase 5 | the final docs | P9 |
| observations H2, H3, H5 | one relation; fewer primitives; principles | P3; S7 and the "won't build" rule; P6 |

## 7. Decisions this plan needs

**Taken from the app's plan 136 (owner, 2026-11-15), recorded in
[decisions.md §0](decisions.md#0-needed-from-you-now):** core makes Grid,
Column, Row, Cell and a pick real objects, defined clearly with how each is
used; a stage is a grouping of consecutive steps that adds no computation;
incremental runs go by row state.

| | Decision | Recommended |
|---|---|---|
| **P-D1** | **Consolidation before features**: P1–P4 before P7e and P8 | **yes**: keeping results needs P2 and P3 anyway. P1b, P7a and P7b are independent and small, and go as soon as the app is waiting on them |
| **P-D2** | **The principles** (H5). A new case is settled by them, or the list changes. Draft: (1) core never guesses: two readings, refuse and write the fix; (2) what is saved is what runs: anything inferred is written into the expression; (3) rows meet only through an identity core recorded; (4) nothing is lost silently; (5) one way to write each thing; (6) states are derived from the workflow and the store, never remembered; (7) check when written, fail at run only on data, cell by cell; (8) core owns the facts about a workflow, the app owns text, people and pixels | adopt, edited as you like, as a new first section of model.md |
| **P-D3** | **A pick saves its row's identity** (P4), and its row number is worked out each time. Saved files keep writing the row number, with the identity beside it | yes: the only fix for W18 that doesn't add a rule |
| **P-D4** | **The public API** is `simple_steps_core.__all__` plus the methods of `Kernel`, `Catalog`, `Step`, `Output` and `Problem` (and P7c's types when they land); anything else may change in a patch. A breaking change to the public API is a minor version before 2.0, with a §5 row | yes |
| **P-D5** | **Who writes P1's asks.** The app files core asks (012 was the app's). For shims, core opens the ask itself (013), from the app's `core_bridge.py`, and tells the app each release | core writes 013 |
| **P-D6** | **The grid objects in core's words.** 136-A's table differs from model.md §2 in three places: (1) *selection* is a retired word; it is a **pick**; (2) a Row shows its **row number** (`#`) and lineage; the row id is core's and never shown or written (CA-B1), where 136 has "row id (the index)"; (3) a Cell's states are core's seven (`absent`, `known`, `maybe`, `pending`, `blocked`, `failed`, `invalid`), with `stale` a mark the view shows over `known` (`checks._worst`), not a state of its own; model.md doesn't list that mark yet, and should | the spec takes core's words in all three, and model.md adds the `stale` mark |
| **P-D7** | **Where a stage lives.** A stage changes no output, so it is outside every spec id. It is still core's, not `extras`, because keeping it valid is a fact about the workflow: an insert inside a stage joins it; a move out of it leaves; a rename follows; deleting its last step deletes it; two stages never overlap. `k.stage("clean", first="load", last="tidy")`; `k.run(stage="clean")` runs its steps | yes |
| **P-D8** | **Typed objects keep the dict form.** `k.view(…)` returns a `Grid` and `k.cell(…)` a `Cell`; `.to_dict()` is today's dict, key for key, so the app's API and its tests move when they choose | yes |
| **P-D9** | **The workflow as a script in core.** `k.to_python()` writes the catalog's imports, the resources and one `k["s"] = …` line per step, stages as comment sections; a test runs it and gets the same spec ids. The app's 132 `export_script()` becomes a call to it | yes: "a workflow the app saved runs the same in plain Python" (model.md §11) is then tested, not assumed |
| **P-D10** | **Spans from `formula()`.** Each part it reads (the tool, each modifier, the input, each argument, each pick) carries its place in the text, from the syntax tree it already reads. The shared corpus then checks the browser's spans against core, not against itself | yes |
| **P-D11** | **The name of the literal table tool** (135 §4: `table[mod.source()](data={…})`). `table` is already a verb, `mod.table` (one call with the whole input), so one word would mean two things (model.md §2) | a core built-in under another name. The owner names it |
| **P-D12** | **A function defined in a cell** (136-I1) | no core change: the app turns it into a tool and builds the kernel again with the larger catalog. A catalog that grows inside a kernel is a later decision, only if rebuilding proves too slow |

## 8. Done means

This phase is done when:

1. the app's `core_bridge.py` holds no shim;
2. no state in core is kept as a flag; `relation()` is the one answer to how two
   steps' rows relate; `workflow.py` is under half its 2026-11-15 size;
3. W9 and W18 pass, and nothing is expected to fail but P8's pinned features;
4. the principles are written, and every decision after them cites one;
5. `formula(print(x)) == x` holds over generated expressions, and the app's
   corpus passes against core;
6. 136's core asks are built: stages, `k.to_python()`, the grid types, spans,
   and keeping results with incremental runs;
7. the speed test holds (goal 4), and the property tests pass at
   `STRESS=2000`.
