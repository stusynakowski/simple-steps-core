# The plan

> **The dev plan for what's left of phase 4**: the goals, the order of work,
> and what each step needs. Reorganised 2026-10-31 at `8f8de1e`; **reordered
> 2026-11-02** for the core asks ([core-asks/](core-asks/): the target model,
> changes L1–L52 and their probe), with the owner's answers in
> [decisions.md §4](decisions.md#4-core-asks-reconciled-2026-11-02). Pages
> that go together:
>
> | Page | Holds |
> |---|---|
> | **this one** | the goals, the order of work, and the changes in detail |
> | [decisions.md](decisions.md) | every decision, grouped by the step that needs it |
> | [syntax-review.md](syntax-review.md) | the design of the expression cleanup: the model, the rules, the bugs, the tests |
| [core-asks/model.md](core-asks/model.md), [core-asks/plan.md](core-asks/plan.md) | the target for references, selection, lineage and binding; where it and syntax-review differ, core-asks wins (binding: CA-A replaces syntax-review §3.1 rule 7) |
>
> Done work keeps its own record: [reshaping-plan.md](reshaping-plan.md), and
> §4 below. The overall phases are in [cleanup-plan.md](cleanup-plan.md#4-order-of-work).

## 1. The goals

**For a user.** A workflow reads like Python and feels like a spreadsheet:

1. **A step is a list of rows, and a row is a dict.** You iterate through the
   list; the keys are what you call the things in each row.
2. **An expression says what each tool receives, and how many times it runs.**
   The verb decides how much an argument passes; staging decides which column
   reaches which parameter (what you wrote, then a matching name, then the one
   fitting type) and writes it into the expression. Core never guesses
   between two columns, never passes a name or a row number, and nothing
   happens that the saved expression doesn't show.
3. **Reshaping is quick,** and never loses information silently.
4. **What you see is true:** sizes, types, states, what is stale and why.
5. **A workflow is reproducible:** the same recipe, tools and data give the
   same result, and core can say when they don't.

**For the code.** The grid model is the only model. It is **airtight**:
every rule has a law that tests it, the property tests generate workflows
that break none of them, and every refusal names its fix.

**For the app.** Simple Steps moves onto this core once, after the syntax it
writes formulas in is settled.

## 2. The order of work

One list, in order. A step starts when its decisions (decisions.md, by the
same letter) are made, and ends when its laws pass, the suite and the
property tests (`STRESS=1`) are green, and it is committed. Each behaviour
change is confirmed before it lands.

| | Step | What it does | core-asks | Size | Status |
|---|---|---|---|---|---|
| A | Outputs | records spread into columns; naming; warnings; `timeout` | — | — | ✓ |
| B | Seeing the data | sizes, pages, observed types, stale reads | — | — | ✓ |
| C | Identity | tool hashes, ids, `diff`, `data_version()`, `Secret` | — | — | ✓ (seed: S9) |
| — | Conditions | `mod.map(where=…)`, `first_present` | — | — | ✓ |
| **S0** | **The tests** | the laws E1–E27, expected-to-fail until their step; core-asks `probe.py` (L1–L52) turned into tests the same way | all | small | **next** |
| **S1** | **Bugs, and no wrong answers** | B1–B11; a column argument from an unaligned step refused, the message writing the join; `zip_` of unaligned steps refused; `total` over mixed columns | M0 (L1–L5) | small | needs D27, D29, D31, D32, D57 (recommended) |
| **S2** | **Values and keys** | tools get plain Python values; numeric names become `var<n>`; other names kept (CA-E) | L21 | small | needs D17 (recommended) |
| **S5** | **Row numbers and lineage** (moved up) | `#<step>` = `0…n-1`; every row form by row number; row ids hidden; every step carries its ancestors' lineage; `.idx`; `#r.2`; lineage apart from data; joins on lineage; `mod.copy` | M1, M2 (L6–L19, L44, L45) | **the largest** | N1 decided |
| **S4** | **Naming** | one output named after its step; a dict's keys as columns; `var<n>`; ints stay ints; step names identifiers; sources and literals (D12) | M3 (L20–L24, L46, L47) | medium | needs D12 (recommended) |
| **S3** | **Grammar and binding** | strings choose columns, integers rows, conditions (`cols`, `row`); pickers before the verb; a pick as an input; **binding at staging, saved explicitly** (CA-A); `mod.cast`; verbs inferred and written (`auto` resolved, D20); nothing unseen (D21) | M4, M5 (L25–L39, L48–L51) | **large** | N2, N3 decided; D8, D18, D19, D21 (recommended) |
| **S11** | **Live editing** | readers re-checked at once; "reference moved"; stale reasons; renames rewrite what core wrote; delete anyway | M6 (L40–L43, L52) | small–medium | — |
| **G** | **The app moves** | [app-migration.md](app-migration.md), onto the new syntax; core's to-dos T6, T9–T13 | — | medium (in the app) | needs D50, D52, D53 |
| **D** | **Sessions** | outputs kept by version (K22), progress and `cancel()` (K23, K14), re-run failed or stale rows (K15, D42), stages (R9), autorun | — | medium–large | needs D-D1, D-D2, D42 |
| **E** | **Storage** | the output store (C32, K16); media handles (R7) | — | medium | needs E-D1 |
| **F** | **The workflow as a table** | step blocks side by side, rows lined up (G18) | — | medium | nothing new |
| **S6** | **Modifiers** | `initial=`, `sweep`'s values and `over=` move into the call | — | small | needs D22–D25, D56 |
| **S7** | **Reshaping** | `melt`, `pivot`, `collapse(keep=…)`, the cheat sheet | — | medium | needs D33, D34, D36 |
| **S8** | **States** | the `empty` state; marks on `completed`; `running` (CA-10) | — | small | needs D37–D40 |
| **S9** | **Staleness and time** | the exact cells an argument reads; volatility (pure, seeded, versioned, volatile); *as of*; the seed | — | medium | needs D41, D43–D46 |
| **S10** | **Docs and UI** | rules.md opens with the model; `k.data(…)`; the output UI written into the app's dev plan (lineage expander, CA-B2) | — | small | needs D48, D49 |
| — | **Phase 5** | the final docs set (cleanup-plan.md §6) | — | medium | after all of the above |

The steps keep their letters, so decisions.md's groups still point at them;
the order is the table's.

**Why this order.**
- S1 first: it stops wrong answers under any syntax (core-asks M0).
- Everything up to S11 changes what an expression means, so it goes before
  the app moves (G), and the app's expressions change once.
- S5 (row numbers) now comes **before** the grammar: an integer in a pick is
  a row number (CA-B1), and lineage is what joins, conditions and "reference
  moved" are built on. This follows core-asks' milestone order (N1, decided
  2026-11-02: settled before more app development).
- D, E and F add features and break nothing, so after G they can go in any
  order. S6–S10 are small and mostly additive.

**The cheaper path is gone** (N1): deferring S5 past G would mean the app
migrating twice.

## 3. The changes, in detail (S0–S4)

What I propose to change, step by step: what you'd see before and after,
where in the code, and the test that shows it. Later steps (S5–S10, D, E, F)
are written at this level when they come up. Nothing below lands without
your yes on its decisions ([decisions.md](decisions.md)).

### S0. The tests (no behaviour changes)

| Change | Where |
|---|---|
| The laws E1–E27 of syntax-review.md §8, one test each, marked expected-to-fail with the step that will make it pass | new `tests/unit/test_expressions.py` |
| A regression test per bug B1–B10, expected-to-fail until S1 | the same file |
| The property test learns the new references (`wf["p"]["temp"]`, `wf["p"][1]`), switched on step by step | `tests/unit/test_reshape_properties.py` |

Running it shows exactly what fails today: the starting line.

### S1. Bugs

| | Today | After | Where | Needs |
|---|---|---|---|---|
| B1 | `widen(columns=["age", "bed"])` on `name, info` gives `None`s, silently | `mod.widen("info")` spreads that column; with other columns and none named: refused, *"widen which column? p has name, info"* | `verbs.widen_`, `checks` (widen's column) | D31 |
| B2 | `expand(columns=["info"])` refuses a dict | key/value rows, the other columns kept (so a melt keeps `ward`) | `verbs.expand_` / `_unpack` | D32 |
| B3 | `value=wf["p"][cols["#"]]` hands ids to a tool | refused: *"row ids aren't data; rename them into a variable first"* | `checks` (arguments), `workflow._resolve_arguments` | D27 |
| — | `rename(columns={"#": "row"})` refused | copies the row id into a variable `row`; the row keeps its `#` | `verbs` (rename), `checks` | D28 |
| B4 | `stack` of an ids-only step gives empty rows | refused: nothing to stack | `combines.stack` | D29 |
| B6 | `DataFrame([[1, 2]])` gets keys `"0"`, `"1"` | refused: *"columns must be named: mod.name(["a", "b"])"* | `verbs.grid` and the source path | D3 |
| B7 | a `scale` column silently replaces `scale=1.8` | a warning: *"scale comes from p's column, not its default 1.8"* (S3 then removes binding by name) | `modifiers._d_apply`, `checks` | — |
| B9 | a one-key list counts as a "block" (its `#` counted) | `#` columns never count towards a shape | `values._shape_kind` | — |
| B11 | **an edit to a source isn't seen downstream** in one property-test chain: a `rec` cell edited from `{}` to `{'a': None}`, then `key_pp[mod.group(), mod.name("g")](wf["s0"])` keeps `{}` after a re-run. `test_reshape_properties.py::test_L40c` fails at `11a7ca0`, before today's changes. The two data versions differ, so the cause is in staleness or in the re-run, not in the hash | the re-run gives what a fresh run gives | `output`, `workflow` (staleness), to find | — |
| B10 | an object without a `repr` gets a new data version every run | its own `data_version()`, else its fields, else pickle; else the plan says it has no stable version | `output._data_version` | D57 |

(B5, `auto` stored, is S4. B8 is S3.)

### S2. Values and keys

| Today | After | Where | Needs |
|---|---|---|---|
| a row dict holds `np.float64(38.2)`, missing floats as `NaN` | `38.2`, `None`: plain Python, unless the parameter asks for `pd.Series` / `DataFrame` | `verbs._units` (the one place rows are made for tools) | D17 |
| any string is a column name | an identifier (`temp_f`); others refused with a suggested name, when a step writes them | `checks` (names written: sources, `mod.name`, `rename`, records) | D3 |

### S3. The core change

| Today | After | Where | Needs |
|---|---|---|---|
| `wf["p"]["temp"]` refused (*"Columns use cols"*) | a string in brackets is a key; an integer a row; `wf["p"][1]["temp"]` = `wf["p"]["temp"][1]` | `references.StepRef.__getitem__` | D2, D10 |
| a selection can't be an input (*"make it its own step"*) | `to_f(wf["p"]["temp"])` is the normal form | `operation._wire`, `run`, staging | D6 |
| `wf[0]` is the first step | step names only | `references` (`wf[…]`) | D5 |
| `cols[…]` / `rows[…]` needed | kept for ranges of keys; printed in the plain form | `references`, `operation.to_source` | D7 |
| `.header` | `.keys` | `references` | D8 |
| parameters bind to columns **by name**, at run; a missing name is `invalid` | **at staging**, the first that decides: what the user wrote; a column with the parameter's name (only without a default: B7); the one column whose type fits; otherwise `invalid` naming the candidates or suggesting `mod.cast`. The result is **written into the saved expression** (`n=wf["d"]["d"]`) | `modifiers._d_apply`, `checks` (binding, `_paired_arguments`), `workflow._columns_bound`, `operation.to_source` | CA-A (replaces D13, D15) |
| what an argument column passes depends on the parameter's type | on the verb: a row's cell under `map`/`filter`/`expand`, the whole column under one call, the group's values under `collapse` | `modifiers`, `checks` | CA-D1 |
| — | `mod.cast(column="type")`; `int` → `float` automatic | `modifiers`, `checks` | CA-A |
| a reference to a step whose shape isn't known yet | a warning when declared, decided at run, re-checked after | `checks`, staging | D18 |
| `collapse(by="ward")` reads `ward` from the input | the same, also when the input is one key of a step | `verbs.collapse_` | D19 |

Binding by name stays (step 2 of CA-A), so most of the ~200 existing call
sites keep working; what changes is that the binding is saved explicitly,
which changes their saved specs and printed expressions. The full list of
changes and tests for S5, S4, S3 and S11 is core-asks/plan.md §5–§11; this
section keeps only what core-asks doesn't cover (`wf[0]`, `.keys`, D18,
D19, D12, D20, D21).

### S4. Broadcasting and naming

| Today | After | Where | Needs |
|---|---|---|---|
| `is_hot(wf["p"])` saves `mod.auto()`, decides at run (B5) | `auto` resolves when written, by §3.1's rules, and saves and prints what it chose (`map`, or one call) | `run._resolve_auto`, `operation._wire` | D20 |
| `auto` turns a `bool` tool into a `filter` | it doesn't: `filter` is written | `checks.infer_verb` | D20b |
| `auto` adds `breaker(after=5)` unseen | shown in the formula, or not added | `run` (defaults), `operation.to_source` | D21 |
| an unnamed single key is `value` | the step's name (`k["temp_f"] = …` → `temp_f`); `mod.name` still wins | `workflow.default_name_rule` | D9 |
| a source's `list[int]` is one value | its declared type decides: `list[T]` is rows; `list` or none is one value | the source path in `workflow` | D12 |
| a literal is one value | the same (confirmed) | — | D11 |

### After S4

G (the app moves) uses app-migration.md, updated with S1–S4's changes. S5
onwards is written at this level when its turn comes.

## 4. Done means

Phase 4 is done when:

1. every law in syntax-review.md §8, and in reshaping.md §10, passes, with
   nothing expected-to-fail;
2. the property tests at `STRESS=1` pass, generating formulas in the new
   syntax;
3. `scripts/core_asks.py` says **39 of 39** (K14, K15, K16 close with D and E;
   K19 is re-probed for CA-C), and `docs/design/core-asks/probe.py` passes
   every test (today 18 of 82);
4. every feature in features.md is done, or moved to "Later, by decision";
5. rules.md opens with the model, kernel-session.md shows what was built,
   and its example runs as a test;
6. the app runs on this core (app-migration.md §4).

Then phase 5, the final docs, starts.

## 5. Done so far in phase 4

| | |
|---|---|
| **reshaping, closed** | row ids and `#` columns, matching rows, round trips, reductions as lists, uneven data (`absent`), the empty step, plans that say how to go back, the invariant check on every test, the property tests ([reshaping-plan.md](reshaping-plan.md)) |
| K19, K28 | selections, column arguments and `zip_` by row id; each cell's lineage |
| G1, G2, G4, G10, G12, G13, G17, R8 | `group` labels rows; missing is `None`; formulas print as written; `widen` replaces its column; `mod.name`; readers re-checked; the empty step; ints stay ints |
| **Step A**, 2026-10-27 | G5 (a fold's start), G8 (records spread), G9, G12 (every form, kernel naming), G6, G7 (warnings, *where*), K18 (`timeout`). `tests/unit/test_outputs.py` |
| **Step B**, 2026-10-27 | K1, K26 (sizes, pages of 50), K27 (observed types), K29 (stale reads). `tests/unit/test_seeing.py` |
| **Step C**, 2026-10-27 | K20 (tool hashes, `k.id`, `run_id`, step ids, `diff`, *tool changed*), K25 (`data_version()`), R3 (`Secret[str]`). `tests/unit/test_identity.py` |
| **For the app**, 2026-10-27 | exports, `k.infer_verb`, `cat.formula_names()`, hashes in `describe()`, `where: expect`, record sources, `v0.2.0` |
| **Conditions**, 2026-10-31 | `mod.map(where=test)`, `first_present`; a single cell broadcasts like a literal. `tests/unit/test_where.py` |

`scripts/core_asks.py`: 36 of 39. Open: K14 (progress), K15 (re-run failed
rows), K16 (results store).
