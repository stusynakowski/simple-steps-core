# The dev plan

> **Draft, 2026-11-15; updated 2026-11-15 for the app's plan 136, and
> 2026-11-16 for the owner's notes: the grid and its picks need no new
> objects, and core needs saving methods.** Phase 4 is done: core 1.0.0–1.0.2
> shipped the grid model, and the app runs on 1.0.2. Phase 4's plan and the
> app's migration guide are in [docs/old/](../old/)
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
> | [saving.md](saving.md) | saving and loading a session: what is kept, value by value, and when something can be lost |
> | [core-asks/](core-asks/) | the app's requirements of core, and the probe that tests them |

## 1. Where core is (run 2026-11-15/16, at `dbaf4c7`)

| Check | Result |
|---|---|
| `pytest` | 946 passed, 5 xfailed (W9, W18, S6 D23, S7 D33, an S3 CA-D1 case) |
| `docs/design/core-asks/probe.py` | 85 pass, 0 fail, 0 skip |
| `scripts/core_asks.py` | 36 of 39 (open: K14 progress, K15 re-run failed rows, K16 output store) |
| `tutorial/tutorial.py` | 118 lessons: 117 ✓, 1 ? (C11, an inline expression as a combine's input; refused by EX5) |
| `tutorial/handover.py` | 59 checks: 53 ✓, 4 ✗ (K23, K28b, R7, R9), 2 ? |
| Size | `src/` 14,599 lines; `workflow.py` 3,665 (139 methods), `checks.py` 2,313 |
| Speed (50 `map` steps in a chain, 1,000 rows) | `formula(text)` + `k.check` of a new step: **1.4 ms**; an edit at the top re-checking all 50: **107 ms** |
| Picks | every pick is a grid: a cell `wf["s"][1]["n"]` 1×1, a row `wf["s"][1]` 1×2, a column `wf["s"]["n"]` 3×1, a block 2×2, the step `wf["s"]` 3×2, each a DataFrame that prints back as its pick |
| Saving | `k.to_json()` / `Kernel.from_json(text, catalog)` save expressions and literals (`k["lim"] = 38`), **not data assigned to a step**: a DataFrame in `k["s"]` is gone after a load, and `run_all()` then **raises** `ValueError: source step 's' has no data`. Outputs are saved only by the internal `Workflow.to_session_dict()`, which the app reaches through its C32 shim. Nothing is saved as a run goes |
| The app | pins `dbaf4c7`; reads formulas with core's `formula()`; `core_bridge.py` holds seven shims against core (P1) |

**What's strong:** one model, lineage on every row, refusals that write the
fix, per-cell failures, and the test net (the invariant check after every
step of every test, the property tests, the probe). **What's weak:**
consolidation that was decided and never done (observations F4, L2), states
still partly kept as flags, app-side workarounds core doesn't know about
(observations L3), and **saving**, which loses entered data silently.

## 2. The goals of this phase

1. **Robust.** No crash, hang or raw Python error on any input the app can
   send; every app shim gone.
2. **Nothing a user made is lost.** A saved workflow holds everything needed
   to show and re-run it: expressions, the data typed or uploaded into steps,
   and, when asked, the outputs. Long runs keep what they have done.
3. **Consolidated.** One answer to each question in one place: how two steps'
   rows relate, what state a step is in, which row a pick means. `workflow.py`
   split along those lines.
4. **Room to grow.** Features arrive as small additive pieces on a smaller
   core, each settled from a short list of principles (P6) instead of a ruling
   of its own. The first features are the ones the app's plan 136 needs (§3.4).
5. **Fast enough to feel live.** The app answers meaning in about 100–200 ms
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
| **P1b** | **The grid and its picks, written down** (136-A, 136-P0) | no new objects: a cell, a row, a column and a block are picks, and every pick is a grid. One section of model.md (and a line in rules.md) says what a grid holds and how header, row number, lineage and data differ, for the UI, formula text, the agent and a terminal (§3.4, P-D6). Runs alongside P1–P3 | docs | small | P-D6 | to do |
| **P1c** | **Saving a session as a folder** | a session saves as one folder: the workflow in `workflow.json`, and each step's grid in its own Parquet file, checked to read back exactly. First the loss (data assigned to a step is saved, and a step whose data is missing is `invalid`, never a raise); then outputs, closing the C32 shim (§3.5) | behaviour | medium | P-D12, P-D13, P-D15, P-D16; [saving.md](saving.md) S-D1–S-D5 | **✓ 2026-11-16**: layers 1 and 2, and media: `k.save(folder, outputs=True)` / `Kernel.load(folder, catalog)`, data steps and outputs as Parquet, arrays, images and Plotly figures as files by content, all checked. Next: big steps on disk (P7d) |
| **P2** | **States only from the store** | the old flags (`edited`, `stale`, `stale_reason`, `read_stale`) go; `stale` is read off the store like every other state (SM, ST5). The first piece of keeping results (136-P4) | restructure | medium | — (SM decided) | to do |
| **P3** | **One row relation, and a smaller `workflow.py`** | each verb declares its row map in its plan (PL2); one function answers how two steps' rows relate (WR1); then `workflow.py` and `checks.py` split by concern; a speed test pins goal 5 (§3.2). Row maps are what incremental runs (136-P4) are built on | restructure | large | — (WR1, PL2 decided) | to do |
| **P4** | **Picks kept by row identity** | a saved pick holds its row's identity and works out its row number each time. Fixes W18 and W9 | behaviour | medium | P3; P-D3 | to do |
| **P5** | **Grammar leftovers** | D18, D19; PK7 at staging; EX11's per-cell type checks at run | behaviour | small | D18, D19 | to do |
| **P6** | **Principles, the public API, the round trip** | the principles list (H5); what is public and what versioning promises (P-D4); a property test that `formula(print(x)) == x` over generated expressions (EX7) | docs + test | small | P-D2, P-D4 | to do |
| **P7** | **What the app's plan 136 needs** | in this order: **P7r** a cell's recipe; **P7a** stages (✓ 2026-11-17); **P7b** the workflow as a script; **P7c** formula spans and the shared corpus; **P7d** keeping results, with saving as a run goes (§3.4, §3.5) | additive | medium–large | P-D7–P-D10, P-D14 | after P1; see §3.4 |
| **P8** | **The other features** | §3.3, in the order the app needs them | additive | — | each its own | after P7 |
| **P9** | **The final docs** | README, writing tools, resources, modifiers, integrating, problems (the old T13) | docs | medium | after P7 | — |

**Why this order.** P1 first: the app ships on core today, and two of its
shims are live bugs. P1c next to it: saving loses entered data silently, which
breaks "nothing is lost silently", and the app's data entry (136-B) would make
that loss common. P1b is docs and runs alongside. P2 and P3 come before P7d
because they are its foundation: incremental runs need states read off the
store (P2) and row maps (P3), so consolidation is on the way to the feature,
not a detour. P7's small items (stages, the script) touch neither and may go
earlier if the app is waiting on them (P-D1).

### 3.1 P1: the app's shims (read 2026-11-15 from the app's `core_bridge.py`)

| Shim | What the app works around | Core's fix | Checked |
|---|---|---|---|
| **B-collapse-arg** | **A silent wrong answer** (found 2026-11-16). Under `collapse(by=…)`, a column argument written explicitly passes the **whole column** to every group, not the group's rows: `mean[mod.collapse(by="ward")](wf["v"], temp=wf["v"]["am"])` gives ward A 38.23 (all three patients), where A's two average 37.6; a pivot with `value=wf["long"]["pk"]` gives every name the last values. Bound by name, both are right | an explicit column argument under `collapse` passes the group's values, as binding by name does; one from rows that aren't the input's is refused, writing the join; a one-value parameter is refused, *declare temp: list* | **✓ done 2026-11-16** (`checks._paired_arguments` pairs a column under `collapse`; `tests/unit/test_collapse_arguments.py`, 8 tests) |
| **C37** | `k.view` / `k.cell` crash on a cell holding an array (an image): `_plain` calls `.item()` on anything with a dtype | unwrap numpy scalars only | **✓ 2026-11-17**: `_plain` unwraps numpy scalars only; an array stays an array |
| **C45** | `formula('wf["s"][1][2]')` raises `SelectionError`, not `FormulaError` | every refusal from `formula()` is a `FormulaError` | **reproduced** |
| C33 | `inspect.signature(tool)` is `(*args, **kwargs)`, not the function's | a tool carries its function's signature | to run |
| C34 | the app's parser checks a modifier's settings as you type through core internals (`check_modifier`, `shape_verbs`) | a public check, `cat.check_modifier(name, settings)`, or the same through `describe()` | to run |
| C18 | a tool's description is its docstring's first line, not its first paragraph | the first paragraph | to run |
| C36 | `describe()` lists a retired `name=` default | **already fixed in core** (`default_is: "the step's name"`): the app can drop this shim | run |
| C32 | a kernel can't be saved with its outputs; the app calls the internal `to_session_dict()` | public `k.save(folder, outputs=True)` (P1c) | **✓ 2026-11-16**: the app can drop the shim |
| **S-plan** | (not a shim: found 2026-11-16) after a step has run, assigning it a new expression leaves `step.plan` showing the **old** result's columns as `exact` (a NamedTuple `r, g, b` re-assigned to a tuple tool still plans `r, g, b`, the step `stale`). Readers are checked right (against the new expression, PL), so only what is shown is wrong | `step.plan` is the plan of the step's expression as it is now; the last result's shape stays with that result | **reproduced** |
| **R-cols** | (not a shim: found 2026-11-16, writing P1c's tests) assigning a DataFrame whose column names repeat, `k["s"] = pd.DataFrame([[1, 2]], columns=["a", "a"])`, raises a raw pandas error, *The truth value of a Series is ambiguous* | refused, naming the repeated names (column names are unique, model.md §6) | **reproduced** |
| **K-cell** | (not a shim: found 2026-11-16) `k.cell` on a `map` with a column argument (`add[mod.map()](wf["srt"], a=wf["srt"][cols["n"]])`) reports the argument's **whole column** (rows 0, 1, 2) as the cell's input, where the call used one cell; after a `collapse` it lists the input rows with empty `values` | the one cell used, and a group's values | **reproduced** |
| **W-arr** | (not a shim: found 2026-11-16) `mod.widen("img")` on a column of numpy arrays **completes with zero columns**: the arrays are gone, with no warning; `expand` of one stops the run (*not a list: ndarray*) | `widen` and `expand` refuse an array cell (the row fails, naming it, and the run goes on), writing the fix: *an array is unpacked by a tool* (decisions.md AR) | **reproduced** |

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
   and states, running, editing, saving. `Workflow` stays the object; the split
   is internal. Then `checks.py`, by what is checked.
4. **A speed test** (goal 5): on a 50-step chain of 1,000 rows, checking a new
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
| E·R7 | **Media handles**: images and files filed by content hash, loaded when read; saved once however many steps hold them | images; plots (136-I9) | E-D1; the content store of P7d |
| S9 | **Time and volatility**: pure, seeded, versioned, volatile tools; *as of* for tools that read the outside world (ST3); the seed (C-D2) | LLM and web tools, which today re-run every time | D41, D43–D46 |
| L4 | `k.trace(step, rows, to=ancestor)`: the pick of the rows behind them. 136-I6's "which input row did this come from" is already `k.cell(...)["inputs"]`, one step back; this goes back further | the app's lineage gutter | P3 |
| L7 | a plan whose columns are exact refuses a missing tool parameter at once | users | — |
| L3 | a join that drops rows warns, with the count | users | — |
| S7 | `melt`, `pivot`, `collapse(keep=…)`, built from pack and unpack (H3), not as new primitives | users | D33, D34, D36 |
| S6 | `initial=`, `sweep`'s values and `over=` in the call | users | D22–D25, D56 |
| S8 | the `empty` state; marks on `completed` | the app | D37–D40 |
| S10 | `k.data(pick)`: a pick's grid as plain data, without core's columns, for a user to write out with pandas | the app, users | D48, D49 |
| F | the workflow as a table: step blocks side by side, rows lined up (G18) | the app | P3 |
| L1 | sharing settings for tools and resources | hosting | D50 |
| L2 | one join for several tables | users | when asked |
| L8 | the steps that need a re-run, for the app's toolbar (`needs_run()` gives it) | the app | — |

### 3.4 What the app's plan 136 asks of core

Plan 136 (app, 2026-11-15) organizes the owner's list I1–I10 into five tracks.
Each row below is checked against core 1.0.2, with what core builds. Tracks
and items that are the app's alone are in §4.

| 136 | Asks core for | Core today (run) | Core's piece |
|---|---|---|---|
| **A** (I3, I4), 136-P0 | Grid, Column, Row, Cell and Selection as real objects | **Owner, 2026-11-16: likely not needed.** A cell, row, column and block are picks of a grid, and every pick is a grid (run: §1, *Picks*); a whole step is the pick of everything, `wf["s"]` | **P1b**: written down, no new types (P-D6). What 136-A wanted from the objects is answered in words: *a grid* holds data columns, each row's number `#` and lineage `#<step>`, a state per cell, and before it runs, its plan; *a header* names a column and is never data; *the row number* is a row's place, never data; *lineage* is read-only, copied into data with `mod.copy`; *a pick* is the one way to point at any part, and prints as formula text. `k.view` and `k.cell` stay the shown form, their keys documented. **Two levels** (owner, 2026-11-16): *a step maps grids to a grid*, its output; *a tool receives values*, the part of a pick its verb hands each call (P-D6) |
| **C·I5**, 136-P4 | **Keeping results**: an output store keyed by data version (K22, C32); **incremental runs by row state** (owner: decided): keep each row's result as it completes, and on a re-run compute only rows not `known` or whose inputs changed; progress and cancel (K23) | one output per step on screen, `KEEP = 4` in the store; no resume (`run(x, fresh=False)` means "on what the inputs show", not "continue"); per-row states exist | **P7d**, after P2 and P3: (1) rows filed as they complete, and saved as a run goes (§3.5, layer 3); (2) re-run by row state (K15, D42, PL3, PL4: the old L6); (3) progress and `cancel()` as a callback (K23, K14). Each its own piece |
| **C·I6**, 136-P1 | which input row a value came from | **already there**: `k.cell("t", 1)["inputs"]` → `[{step: "s", row: 1, values: {"n": 2}, …}]`; lineage on every view row | nothing new; further back is L4 (§3.3) |
| **D·I7**, 136-P5 | **Stages**: a named group of consecutive steps, to organize the workflow; adds no inputs, outputs or computation; shown folded; a section in exported code (owner: decided) | none (R9; model.md §3 *planned*) | **P7a**: a stage in the workflow spec, kept valid by core through insert, move, rename and delete, and saved with it (P-D7) |
| **D·I10**, 136-P6 | the workflow as code, for a script, then a notebook, then other frameworks | each step prints (`step.formula`); no whole-workflow script | **P7b**: `k.to_python()`, a script that rebuilds the kernel in plain Python, its stages as sections, checked by a round trip (P-D8). Notebooks and other frameworks are the app's, over it |
| across tracks, 136-P0b | **the browser may predict; core decides**: a shared conformance corpus of formulas, run by the frontend against its reader and by the backend against core | `formula()` gives an operation and its printed form; no spans of the text | **P7c**: core's tests run the corpus too (kept in [core-asks/](core-asks/), like `probe.py`); `formula()` reports each part's span in the text, so spans are checked against core (P-D9) |
| **B** (I1, I2), 136-P2–P3 | a typed table typed into one step, `table[mod.source()](data={…})` (135 §4); uploading a table | `table` is already a verb (`mod.table`); **a DataFrame assigned to a step isn't saved** (§1) | the name clashes (P-D10); the literal table is a small built-in tool once named, saved in the spec like any literal. An upload too large to sit in the spec is data filed beside it (P1c, P-D12) |
| **B** (I1) | "defining a function in a cell" | a kernel's catalog is fixed when it's made; a bare function is refused (EX9); formula text never runs code (EX13) | nothing in core: the app makes the function a tool and builds the kernel again with the new catalog (`Kernel.from_json(text, catalog)`), which works today (P-D11) |
| **E** (I8), 136-P8 | a step agent scoped to one step | `k.check(name, op)`; refusals that write the fix | WR2, `Problem.fix` (§3.3), when the app wants it |

**P7r, a cell's recipe** (owner, 2026-11-16: "click on a cell and say this cell was produced using this tool, these literal args and these previous cells"): `k.cell(step, row, column)` gives the call that made the cell: the tool and its code hash, the verb, and each argument with its value and its source (an earlier cell as a pick, `wf["v"][1]["n"]`; a literal written in the expression; a parameter's default; a resource), plus the wrappers that ran. Since every input is a pick, the recipe can be re-run as a one-row step; a test calls the tool again from the recipe and compares. It says when a cell can't be reproduced: the tool's code changed (its hash), the tool is volatile (S9), or the step is a `table` (its recipe is the whole input). It is what the app's 136-P1 (row lineage on screen, the cell's formula line) shows; it fixes K-cell with it. Small, needs neither P2 nor P3, so it goes first. Drawn in the page *The step table*, figure 3.

**P7's order:** **P7a** stages and **P7b** the script are small, need neither
P2 nor P3, and may go right after P1 if the app is waiting on them. **P7c**
spans and the corpus whenever the app's corpus exists. **P7d** keeping results
after P3.

### 3.5 Saving (owner, 2026-11-16: "we need saving methods")

**A session is a folder** (owner, 2026-11-16: "parquet files for each step,
or some way that is organized"): `workflow.json`, a Parquet file per step,
and arrays, images and Plotly figures as media files by content hash. **What
it holds, when you can save, and exactly when something can be lost is
[saving.md](saving.md)**, with every claim run: each value is saved exactly or
listed in the save's report, every save is checked by reading it back, and
loading runs no code.

Four layers, each its own piece. Today only the first half of layer 1 exists.

| Layer | What is saved | Today (run 2026-11-16) | After | Piece |
|---|---|---|---|---|
| **1. The workflow** | expressions, literals, resources' settings (never a `Secret`), stages, extras; **and the data typed, pasted or uploaded into a step**, since without it the workflow can't re-run | `to_json()` keeps expressions and literals; data assigned to a step is dropped, and a load then raises at `run_all()` | data assigned to a step is saved with it, in `data/<step>.parquet` (a small literal stays inline in `workflow.json`, P-D12). A load whose data is missing makes that step `invalid`, naming what to supply, never a raise. Its data version is its hash, so a load of the same data is the same workflow | **P1c**, first |
| **2. The workflow with its outputs** | layer 1, plus each step's current output, filed by run key | only the internal `Workflow.to_session_dict()`; the app's C32 shim calls it | public `k.save(folder, outputs=True)` / `Kernel.load(folder, catalog)`, writing `outputs/<step>/` as above. A loaded step is `completed` only when its run key still matches (same tool code, same inputs); otherwise `stale`, saying why. One file format, versioned; older ones refused with core's message (D52) | **P1c**, second; closes C32 |
| **3. Saving as a run goes** | each row's output as it completes, so a stopped run (a crash, a cancel, a closed laptop) keeps what it did and resumes where it stopped | nothing: a run's output exists only when the step finishes | the store writes rows as they complete, through a store interface with two backends in core, memory and the session folder (finished rows appended as Parquet parts under `outputs/<step>/`); the app may plug in others. A resume computes only rows not `known` (IR) | **P7d** (with incremental runs) |
| **4. Data out** | a pick's grid as a file a person or another tool opens (CSV, Parquet, Excel); the workflow as code | `k.step(x).output.data` is a DataFrame, with core's `#` columns; no whole-workflow script | `k.data(pick)` gives plain data (S10), and pandas writes the format; `k.to_python()` writes the workflow as code (P7b). File formats are not core's (§4) | P8 (S10), P7b |

## 4. What core won't build

Core is the grid model and what it needs to run. These belong elsewhere, and a
request for one is answered by pointing there.

| Not in core | Where it belongs | Why |
|---|---|---|
| Grid, Column, Row, Cell or Selection types | nowhere, unless a need shows that a pick can't meet (P-D6) | every part of a grid is a pick, and every pick is a grid |
| hosting many kernels, locks, eviction, memory budgets | the app | core gives the store and its `KEEP`; how much to hold is hosting |
| a `running` state | the app (SS6) | it's a fact about a process, not a workflow |
| users, auth, workspaces, file paths, multi-user deployment | the app (its plan 200, M1) | — |
| where and when files are saved: autosave timers, the workspace folder, recent files, cloud storage | the app, calling `k.save` (§3.5) | core says what a save holds and reads it back; the app decides where it goes |
| data file formats (CSV, Parquet, Excel) | pandas, after `k.data(pick)` | core gives plain data; formats are many and not about the model |
| UI: palette categories, widgets, notes, colours, cell editing | `extras["simple_steps.…"]`, never read or hashed | removing it can't change an output |
| editing gestures: typing into cells, paste, upload, the fill handle, locks, "Make values" (136-B) | the app (its 134, 135): each gesture writes an expression core checks | core sees only the expression |
| prefab components and plots for tools, resources and cells (136-I9) | the app, named in `extras["simple_steps.ui"]` | a UI never changes an output |
| the browser's formula reader, for tokens, colours, spans and autocomplete (136 tier 1) | the app, behind the shared corpus | it predicts; core decides meaning |
| notebook and other-framework exporters (136-I10) | the app, over `k.to_python()` | core gives one exact script; formats are adapters |
| the agent, its sub-agents and their permissions (136-E) | the app | core gives `k.check`, and `Problem.fix` (WR2) |
| a blob store backend beyond memory and a folder (a bucket, a database) | the app plugs one in | core defines the interface (§3.5, layer 3) |
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
| 1.0.3 | P1 B-collapse-arg | a column argument written out under `collapse(by=…)` (`temp=wf["v"]["am"]`) gets **each group's values**, as binding by name does; it got the whole column. A column from rows that aren't the input's is refused (`bad_pairing`), writing the join; a parameter typed as one value is refused, *declare temp: list* | results of such steps change (they were wrong); show the refusals |
| 1.0.3 | P1c layer 1 | **`k.save(folder)` and `Kernel.load(folder, catalog)`**: a session as a folder, `workflow.json` and `data/<step>.parquet` for each step declared with a DataFrame, every column checked to read back exactly; `k.save` returns a report (also `report.json`). A data step whose data is missing, changed or wasn't saved loads **`invalid`** (code `data_missing`), saying why; `run_all()` after a light `to_json` load no longer raises. A data step's spec carries `"data": {"in": …}`. **pyarrow is a dependency** | save sessions with `k.save`; show the report; drop the C32 shim once layer 2 lands |
| 1.0.3 | P1c layer 2 | **`k.save(folder, outputs=True)`** also writes each step's output, `outputs/<step>/` (`data.parquet` with lineage and row ids, `states.parquet`, `meta.json`), checked; a reopened session shows its results with nothing to run (`needs_run()` empty). An output that can't be saved exactly (an object; arrays until the media piece) is reported and loads `staged`; a missing or changed file the same. **Every load now checks restored outputs as they are now**: a tool whose code changed shows `stale` (*tool changed*), also through the internal session export, where it showed `completed` | replace the C32 shim with `k.save(folder, outputs=True)` and `Kernel.load` |
| 1.0.3 | P1c media | **arrays, Pillow images and Plotly figures are saved exactly**, each once in `media/<hash>.<ext>` (arrays `.npy`, never pickled; images PNG, or TIFF for `I`, `F`, `CMYK`; figures Plotly's JSON), wherever they sit: a cell, a list, a step's value. An image keeps its `format` and `info`; a figure's arrays load as numpy arrays. **An image's and a figure's data version is now its content** (mode, size, pixels, palette, info; a figure's canonical JSON), so readers of image or figure columns may show `stale` once after the update, and then stay right | nothing; images and figures now save with the session |
| 1.0.3 | running (owner, 2026-11-16) | **`k.run_all()` and `k.run(x)` bring steps up to date**: they run only what has never run or is stale, and leave a completed or failed step whose inputs, tool and expression haven't changed as it is; `force=True` runs again (a retry). A tool with no input (a source, a sweep) runs again whenever it is run by name (a reload), not on `run_all`. A failure nothing handles still stops `run_all`, without re-running it. **And a staleness bug fixed**: a step whose column binding core wrote by type (`slow=wf["a"]["a"]`) stayed `completed` when that column changed | "Run all" no longer redoes slow steps; offer "Run again" (`force=True`) and "Reload" for a source; more steps show `stale` where they should |
| 1.0.3 | P7a stages | **stages**: `k.stage(name, first=…, last=…)`, `k.stages`, `k.stage_of(step)`, `k.run_stage(name, force=False)`, `k.unstage(name)`, `k.rename_stage(old, new)`, and **`k.stage_status(name)`: the stage as one big step** (one state, what needs a run, the step it ends with). Saved (`"stages"` in the workflow file), in no id; kept valid through insert, move, rename and delete; a step is in one stage | show a stage folded as one block; *Run stage*; read `k.stages` after each edit (a stage edit sends no `on_change` yet) |
| 1.0.3 | P7d, bulky cells on disk | **opt-in**: `Kernel(catalog, spill_over=n, store=folder)` keeps each array, image or figure of `n` bytes or more on disk when its step runs (content-named files, as a session's `media/`); its cell holds a **`MediaHandle`** (`.summary`, `.kind`, `.load()`). Tools always get values; the view and `k.cell` show the handle unloaded; **`k.value(step, row, column)`** loads one. Versions, run keys and staleness are unchanged. `Kernel.load(folder, catalog, spill_over=n)` keeps a saved session's media on disk, as handles. Also: `k.view` no longer crashes on arrays (C37); row fingerprints read objects by content, so a change inside a big array or image is seen | to turn it on: render a `MediaHandle` cell from `.summary`, and fetch its value with `k.value` (or `.load()`) when a cell is opened; drop the C37 shim |

## 6. Where phase 4's open items went

| Phase 4 | Open item | Now |
|---|---|---|
| S3 | D18, D19 | P5 |
| S4 | `var<n>` | built (S2, L21); the plan row was out of date |
| S11 | the old flags removed | P2 |
| S5f / D-picks | W9, W18 | P4 |
| D | K22, K23/K14, K15/D42 | P7d (keeping results) |
| D | R9 stages | P7a |
| E | C32/K16 the output store | P1c (saving with outputs) and P7d (the store interface); R7 media handles, P8 |
| F, S6–S10 | as listed | P8 |
| L1–L8 | later, by decision | L5 (stages) P7a; L6 (lazy rows) P7d; the rest P8 |
| T6 | run the app's acceptance session against core alone | P1: the app's shims are what it found |
| T12 | `core_asks.py` at 39 of 39 | closes with P1c and P7d |
| T13, phase 5 | the final docs | P9 |
| observations H2, H3, H5 | one relation; fewer primitives; principles | P3; S7 and the "won't build" rule; P6 |

## 7. Decisions this plan needs

**Taken by the owner, recorded in [decisions.md §0](decisions.md#0-needed-from-you-now):**
from the app's plan 136 (2026-11-15), a stage is a grouping of consecutive
steps that adds no computation (SG), and incremental runs go by row state
(IR). On 2026-11-16 the owner reconsidered 136's grid objects (GO): every
part of a grid is a pick, and every pick is a grid, so new objects may not be
needed (P-D6); and core needs saving methods (§3.5).

| | Decision | Recommended |
|---|---|---|
| **P-D1** | **Consolidation before features**: P1–P4 before P7d and P8 | **yes**: keeping results needs P2 and P3 anyway. P1b, P1c, P7a and P7b are independent and small, and go as soon as they're wanted |
| **P-D2** | **The principles** (H5). A new case is settled by them, or the list changes. Draft: (1) core never guesses: two readings, refuse and write the fix; (2) what is saved is what runs: anything inferred is written into the expression; (3) rows meet only through an identity core recorded; (4) nothing is lost silently; (5) one way to write each thing; (6) states are derived from the workflow and the store, never remembered; (7) check when written, fail at run only on data, cell by cell; (8) core owns the facts about a workflow, the app owns text, people and pixels; (9) every part of a grid is a pick, and every pick is a grid; a step maps grids to a grid, and a tool receives only values | adopt, edited as you like, as a new first section of model.md |
| **P-D3** | **A pick saves its row's identity** (P4), and its row number is worked out each time. Saved files keep writing the row number, with the identity beside it | yes: the only fix for W18 that doesn't add a rule |
| **P-D4** | **The public API** is `simple_steps_core.__all__` plus the methods of `Kernel`, `Catalog`, `Step`, `Output` and `Problem`; anything else may change in a patch. A breaking change to the public API is a minor version before 2.0, with a §5 row | yes |
| **P-D5** | **Who writes P1's asks.** The app files core asks (012 was the app's). For shims, core opens the ask itself (013), from the app's `core_bridge.py`, and tells the app each release | core writes 013 |
| **P-D6** | **No new objects for the grid's parts** (amends GO). A cell, a row, a column and a block are picks, and every pick is a grid (run 2026-11-16). **Two levels:** a step maps grids to a grid (its output, with row numbers, lineage and cell states); a tool receives values, the part of a pick its verb hands each call (a row's cells under `map`, `filter`, `expand`; a group's columns as lists under `collapse`; the whole grid's values under `table`), plain Python, never `#` columns, states or row ids. P1b writes that down in core's words: *pick*, not *selection* (retired); a row shows its row number and lineage, never core's row id (CA-B1), where 136 has "row id (the index)"; a cell's states are core's seven, and `stale` is a mark the view shows over `known` | **yes**: one object, one rule. Types only if a need shows that a pick can't meet |
| **P-D7** | **Where a stage lives.** A stage changes no output, so it is outside every spec id. It is still core's, not `extras`, because keeping it valid is a fact about the workflow: an insert inside a stage joins it; a move out of it leaves; a rename follows; deleting its last step deletes it; two stages never overlap. `k.stage("clean", first="load", last="tidy")`; `k.run(stage="clean")` runs its steps | yes. **Built 2026-11-17** (owner: "a method to group steps with the same functionality") |
| **P-D8** | **The workflow as a script in core.** `k.to_python()` writes the catalog's imports, the resources and one `k["s"] = …` line per step, stages as comment sections; a test runs it and gets the same spec ids. The app's 132 `export_script()` becomes a call to it | yes: "a workflow the app saved runs the same in plain Python" (model.md §11) is then tested, not assumed |
| **P-D9** | **Spans from `formula()`.** Each part it reads (the tool, each modifier, the input, each argument, each pick) carries its place in the text, from the syntax tree it already reads. The shared corpus then checks the browser's spans against core, not against itself | yes |
| **P-D10** | **The name of the literal table tool** (135 §4: `table[mod.source()](data={…})`). `table` is already a verb, `mod.table` (one call with the whole input), so one word would mean two things (model.md §2) | a core built-in under another name. The owner names it |
| **P-D11** | **A function defined in a cell** (136-I1) | no core change: the app turns it into a tool and builds the kernel again with the larger catalog. A catalog that grows inside a kernel is a later decision, only if rebuilding proves too slow |
| **P-D12** | **Data assigned to a step is part of the workflow, and is saved with it**, as `data/<step>.parquet`; a literal small enough to read stays inline in `workflow.json`. The workflow records its data version, so a load checks it got the same data. A load whose file is missing or different makes the step `invalid`, naming the file, never a raise | yes: today it's lost silently (principle 4). **Taken as recommended 2026-11-16 for P1c** (owner: "start the dev plan"; to confirm) |
| **P-D13** | **A session is a folder** (§3.5). `k.save(folder, outputs=False)` writes layer 1; `outputs=True` adds layer 2, a folder per step. `Kernel.load(folder, catalog)` reads either. `to_json()` / `from_json()` stay as the in-memory spec text. A loaded output is `completed` only when its run key still matches. This replaces model.md §3's *saving writes specs, never output data*: specs are still never data, and data now has a file of its own | yes. **Taken as recommended 2026-11-16 for P1c** (owner: "start the dev plan"; to confirm) |
| **P-D14** | **Saving as a run goes** (layer 3) comes with incremental runs (P7d): finished rows appended as Parquet parts in the session folder | yes |
| **P-D15** | **pyarrow becomes a dependency of core** (today: pandas only; pyarrow 25.0.1 is in the dev environment). One way to save, so no second code path for when it's missing | yes. The other way is an extra, `simple-steps-core[save]`, with saving refused without it, naming the extra. **Taken as recommended 2026-11-16 for P1c** (owner: "start the dev plan"; to confirm) |
| **P-D16** | **How a column is written**: plain Parquet when it reads back exactly; tagged JSON for lists, dicts, tuples and mixed columns; media files for large values; a class's own `to_saved()`; else not saved, the step loading `stale` and saying why. **Never pickle.** Every save checked by reading back and comparing data versions (§3.5) | yes: nothing lost silently, nothing run on load. **Taken as recommended 2026-11-16 for P1c** (owner: "start the dev plan"; to confirm) |
| **P-D17** | **Step names in file names.** A step's name becomes its file's name, so a name that isn't a safe file name (`/`, `:`, a reserved name on Windows) is either refused when declared, as `.` is (W7), or written with an escape. The workflow.json maps names to files either way | escape in the file name, keep the name as written: no step name changes because of saving. **Taken as recommended 2026-11-16 for P1c** (owner: "start the dev plan"; to confirm) |

## 8. Done means

This phase is done when:

1. the app's `core_bridge.py` holds no shim;
2. a saved workflow, loaded with the same catalog, shows and re-runs what was
   saved, entered data included; with outputs, it opens without a re-run; a
   stopped run resumes where it stopped;
3. no state in core is kept as a flag; `relation()` is the one answer to how
   two steps' rows relate; `workflow.py` is under half its 2026-11-15 size;
4. W9 and W18 pass, and nothing is expected to fail but P8's pinned features;
5. the principles are written, and every decision after them cites one;
6. `formula(print(x)) == x` holds over generated expressions, and the app's
   corpus passes against core;
7. 136's core asks are built: stages, `k.to_python()`, spans, and keeping
   results with incremental runs;
8. the speed test holds (goal 5), and the property tests pass at
   `STRESS=2000`.
