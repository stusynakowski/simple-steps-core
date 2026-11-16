# The dev plan

> **Draft, 2026-11-15.** Phase 4 is done: core 1.0.0–1.0.2 shipped the grid
> model, and the app runs on 1.0.2. Phase 4's plan and the app's migration guide
> are in [docs/old/](../old/) ([plan-phase4.md](../old/plan-phase4.md),
> [app-migration.md](../old/app-migration.md)). This page orders what comes
> next. Nothing here lands without the owner's yes; the choices it needs are §7.
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
   of its own.

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
| **P0** | **Docs refreshed** | old pages to [docs/old/](../old/); out-of-date claims fixed (model.md §6 and §8.1, rules.md, observations.md); this plan | docs | small | — | ✓ 2026-11-15 |
| **P1** | **Close the app's shims** | each shim in the app's `core_bridge.py` fixed in core, as a patch release the app can pin (§3.1) | fixes | small | P-D5 | to do |
| **P2** | **States only from the store** | the old flags (`edited`, `stale`, `stale_reason`, `read_stale`) go; `stale` is read off the store like every other state (SM, ST5) | restructure | medium | — (SM decided) | to do |
| **P3** | **One row relation, and a smaller `workflow.py`** | each verb declares its row map in its plan (PL2); one function answers how two steps' rows relate (WR1), replacing `_same_ids`, `_aligned_root`, `_matched`, `_reaches` and the pairing half of `trace`; then `workflow.py` and `checks.py` split by concern (§3.2) | restructure | large | — (WR1, PL2 decided) | to do |
| **P4** | **Picks kept by row identity** | a saved pick holds its row's identity and works out its row number each time, instead of a number rewritten in place. Fixes W18 (two picks rewritten to one number) and W9 (a condition on a derived step's rows not following a source edit) | behaviour | medium | P3; P-D3 | to do |
| **P5** | **Grammar leftovers** | D18 (a reference to a step whose shape isn't known yet: warn when declared, decide at run); D19 (`collapse(by=)` reading one key of a step); PK7 (a declared `list` refused by `widen` when written, not at run); EX11's per-cell type checks at run | behaviour | small | D18, D19 (recommended in decisions.md) | to do |
| **P6** | **Principles, the public API, the round trip** | the principles list (H5); which names are public and what semantic versioning promises for them; a property test that generates expressions and checks `formula(print(x)) == x` (EX7) | docs + test | small | P-D2, P-D4 | to do |
| **P7** | **Features** | in the order the app needs them; §3.3 | additive | — | each its own | after P1–P4 |
| **P8** | **The final docs** | README, writing tools, resources, modifiers, integrating, problems (the old T13) | docs | medium | after P7's first wave | — |

**Why this order.** P1 first: the app is shipping on core today, and two of its
shims are live bugs. P2 and P3 before features: every feature in P7 either
reads a step's state (D, S9) or how rows relate (L6, WR3, F), so building them
on today's structure would add a sixth helper and more flags. P4 needs P3's row
maps. P5 and P6 are small and can slot in between pieces.

### 3.1 P1: the app's shims (read 2026-11-15 from the app's `core_bridge.py`)

| Shim | What the app works around | Core's fix | Checked |
|---|---|---|---|
| **C37** | `k.view` / `k.cell` crash on a cell holding an array (an image): `_plain` calls `.item()` on anything with a dtype | unwrap numpy scalars only | **reproduced**: `ValueError: can only convert an array of size 1 to a Python scalar` |
| **C45** | `formula('wf["s"][1][2]')` raises `SelectionError`, not `FormulaError` | every refusal from `formula()` is a `FormulaError` | **reproduced** |
| C33 | `inspect.signature(tool)` is `(*args, **kwargs)`, not the function's | a tool carries its function's signature (`functools.wraps` / `__signature__`) | to run |
| C34 | the app's parser checks a modifier's settings as you type through core internals (`check_modifier`, `shape_verbs`) | a public check: `cat.check_modifier(name, settings)`, or the same through `describe()` | to run |
| C18 | a tool's description is its docstring's first line, not its first paragraph | the first paragraph | to run |
| C36 | `describe()` lists a retired `name=` default | **already fixed in core** (`default_is: "the step's name"`): the app can drop this shim | run |
| C32 | a kernel can't be saved with its outputs | the output store, P7 (E) | waits |

Each is one piece and one patch release (`1.0.3`, …), with a test that fails
without it, and a row in §5.

### 3.2 P3 in pieces

Each piece keeps every test green, unchanged.

1. **Row maps in the plan (PL2).** Each verb's plan says, for each output row,
   its input rows: kept, reordered, chosen, more, fewer, new. Built beside the
   helpers; a test checks the two agree on every property-test workflow.
2. **One relation function (WR1).** `relation(a, b)` → same rows / subset /
   child / group / unrelated, the nearest shared ancestor and the join that
   meets them. Every refusal, plan and view calls it; the five helpers go.
3. **Split `workflow.py`** into modules by concern: rows and lineage (the
   relation, `trace`), the store and states, running, editing. `Workflow` stays
   the object; the split is internal. Then `checks.py`, by what is checked.
4. **Measure:** `workflow.py` and the number of places a verb's identity rules
   live, recorded in observations.md.

### 3.3 P7: features, each its own piece

Grouped by what they serve; the owner picks the order. Ids are decisions.md's
and phase 4's.

| | Feature | Serves | Needs |
|---|---|---|---|
| WR2 | **A refusal carries its fix** as an operation, `Problem.fix`; `k.fix(name)` applies it (a button in the app; a move for the agent). Never applied unasked | the app, the agent | decided (yes) |
| WR3 | `join(a, b)` with no `on=` on related steps joins on the nearest shared ancestor, writing `on="#v"` | users | P3; decided (yes) |
| D | **Sessions**: outputs kept per step while read (K22), progress and `cancel()` as a callback (K23, K14), re-run failed rows (K15, D42), stages (R9) | the app drops `progress.py` and its own stores | D-D1, D-D2, D42 |
| E | **Storage**: the output store's interface (C32, K16), media handles (R7) | images; the app's C32 shim | E-D1 |
| S9 | **Time and volatility**: pure, seeded, versioned, volatile tools; *as of* for tools that read the outside world (ST3); the seed (C-D2) | LLM and web tools, which today re-run every time | D41, D43–D46 |
| L6 | **Lazy row execution**: stale rows follow the row maps (PL3); only they re-run (PL4) | big data, slow tools | P3 |
| L4 | `k.trace(step, rows, to=ancestor)`: the pick of the rows behind them | the app's lineage view | P3 |
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

## 4. What core won't build

Core is the grid model and what it needs to run. These belong elsewhere, and a
request for one is answered by pointing there.

| Not in core | Where it belongs | Why |
|---|---|---|
| hosting many kernels, locks, eviction, memory budgets | the app | core gives the store and its `KEEP`; how much to hold is hosting |
| a `running` state | the app (SS6) | it's a fact about a process, not a workflow |
| users, auth, workspaces, file paths, multi-user deployment | the app (its plan 200, M1) | — |
| UI: palette categories, widgets, notes, colours, cell editing | `extras["simple_steps.…"]`, never read or hashed | removing it can't change an output |
| the agent, its permissions, model calls | the app | core gives `k.check`, and `Problem.fix` (WR2) |
| a blob store backend (a folder, a bucket) | the app plugs one in | core defines the interface (E) |
| a scheduler or autorun machinery | at most a policy over the store (SM) | autorun is "run what's stale and cheap", not new machinery |
| converters for old saved files | nowhere (D52) | no saved workspaces to keep |
| lineage across kernels or files | nowhere (model.md §12) | lineage lives inside one workflow |
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
| S6, S7, S8, S9, S10 | as listed | P7 |
| D, E, F | sessions, storage, the table | P7 |
| L1–L8 | later, by decision | P7 (L5 is R9, in D; L6 after P3) |
| T6 | run the app's acceptance session against core alone | P1: the app's shims are what it found |
| T12 | `core_asks.py` at 39 of 39 | closes with D and E (P7) |
| T13, phase 5 | the final docs | P8 |
| observations H2, H3, H5 | one relation; fewer primitives; principles | P3; S7 and the "won't build" rule; P6 |

## 7. Decisions this plan needs

| | Decision | Recommended |
|---|---|---|
| **P-D1** | **Consolidation before features**: P1–P4 before anything in P7 | **yes**: every P7 feature reads states or row relations; building them first adds to what P2 and P3 must undo. Exception: a P7 item the app is blocked on goes first, as its own piece |
| **P-D2** | **The principles** (H5). A new case is settled by them, or the list changes. Draft: (1) core never guesses: two readings, refuse and write the fix; (2) what is saved is what runs: anything inferred is written into the expression; (3) rows meet only through an identity core recorded; (4) nothing is lost silently; (5) one way to write each thing; (6) states are derived from the workflow and the store, never remembered; (7) check when written, fail at run only on data, cell by cell; (8) core owns the facts about a workflow, the app owns text, people and pixels | adopt, edited as you like, as a new first section of model.md |
| **P-D3** | **A pick saves its row's identity** (P4), and its row number is worked out each time. Saved files keep writing the row number (so they read the same), with the identity beside it | yes: the only fix for W18 that doesn't add a rule |
| **P-D4** | **The public API** is `simple_steps_core.__all__` plus the methods of `Kernel`, `Catalog`, `Step`, `Output` and `Problem`; anything else may change in a patch. A breaking change to the public API is a minor version before 2.0, with a §5 row | yes |
| **P-D5** | **Who writes P1's asks.** The app files core asks (012 was the app's). For shims, core opens the ask itself (013), from the app's `core_bridge.py`, and tells the app each release | core writes 013 |

## 8. Done means

This phase is done when:

1. the app's `core_bridge.py` holds no shim but C32's, and C32 has a date in P7;
2. no state in core is kept as a flag; `relation()` is the one answer to how two
   steps' rows relate; `workflow.py` is under half its 2026-11-15 size;
3. W9 and W18 pass, and nothing is expected to fail but P7's pinned features;
4. the principles are written, and every decision after them cites one;
5. `formula(print(x)) == x` holds over generated expressions;
6. the property tests pass at `STRESS=2000`.
