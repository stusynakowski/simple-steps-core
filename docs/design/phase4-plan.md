# The plan

> **The dev plan for what's left of phase 4**: the goals, the order of work,
> and what each step needs. Reorganised 2026-10-31 at `8f8de1e`. Three pages
> go together:
>
> | Page | Holds |
> |---|---|
> | **this one** | the goals and the order of work |
> | [decisions.md](decisions.md) | every decision, grouped by the step that needs it |
> | [syntax-review.md](syntax-review.md) | the design of the expression cleanup: the model, the rules, the bugs, the tests |
>
> Done work keeps its own record: [reshaping-plan.md](reshaping-plan.md), and
> §4 below. The overall phases are in [cleanup-plan.md](cleanup-plan.md#4-order-of-work).

## 1. The goals

**For a user.** A workflow reads like Python and feels like a spreadsheet:

1. **A step is a list of rows, and a row is a dict.** You iterate through the
   list; the keys are what you call the things in each row.
2. **A formula says what each tool receives, and how many times it runs.**
   The types decide (broadcasting); core never guesses a key, never passes a
   name or a row number unless asked, and nothing happens that the formula
   doesn't show.
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

| | Step | What it does | Size | Status |
|---|---|---|---|---|
| A | Outputs | records spread into columns; naming; warnings; `timeout` | — | ✓ |
| B | Seeing the data | sizes, pages, observed types, stale reads | — | ✓ |
| C | Identity | tool hashes, ids, `diff`, `data_version()`, `Secret` | — | ✓ (seed: S9) |
| — | Conditions | `mod.map(where=…)`, `first_present` | — | ✓ |
| **S0** | **The tests** | the laws E1–E27 (syntax-review.md §8), each expected-to-fail until its step | small | **next** |
| **S1** | **Bugs** | B1–B10 (syntax-review.md §4): `widen`, `expand` of dicts, the `#` leak, `stack`, string keys, a column replacing a default, `#` counted in a shape, objects' versions | small | needs D3, D27–D29, D31, D32, D57 |
| **S2** | **Values and keys** | tools get plain Python values; keys are identifiers | small | needs D3, D17 |
| **S3** | **The core change** | string = key, integer = row; a selection can be an input; tools receive by type (§3 of syntax-review); binding by name only on request | **large** | needs D1, D2, D5–D8, D10, D13–D16, D18, D19 |
| **S4** | **Broadcasting and naming** | `auto` as broadcasting, resolved when written; nothing unseen; one key named after its step; sources and literals | medium | needs D9, D11, D12, D20b, D21 |
| **G** | **The app moves** | [app-migration.md](app-migration.md), onto the new syntax; core's to-dos T6, T9–T13 | medium (in the app) | needs D50–D53 |
| **S5** | **Row numbers** | `0…n-1` per step; links in `#` columns; core's hidden key for lineage and staleness; the reshaping laws re-run | **the largest** | needs D4, D30, D35, D47. *May be deferred*: nothing before it depends on it |
| **D** | **Sessions** | outputs kept by version (K22), progress and `cancel()` (K23, K14), re-run failed or stale rows (K15, D42), stages (R9), autorun | medium–large | needs D-D1, D-D2, D42; after S5, since re-running rows needs row identity |
| **E** | **Storage** | the output store (C32, K16); media handles (R7) | medium | needs E-D1 |
| **F** | **The workflow as a table** | step blocks side by side, rows lined up (G18) | medium | nothing new |
| **S6** | **Modifiers** | `initial=`, `sweep`'s values and `over=` move into the call | small | needs D22–D25, D56 |
| **S7** | **Reshaping** | `melt`, `pivot`, `collapse(keep=…)`, the cheat sheet | medium | needs D33, D34, D36 |
| **S8** | **States** | the `empty` state; marks on `completed` | small | needs D37–D40 |
| **S9** | **Staleness and time** | the exact cells an argument reads; volatility (pure, seeded, versioned, volatile); *as of*; the seed | medium | needs D41, D43–D46 |
| **S10** | **Docs and UI** | rules.md opens with the model; `k.data(…)`; the output UI written into the app's dev plan | small | needs D48, D49 |
| — | **Phase 5** | the final docs set (cleanup-plan.md §6) | medium | after all of the above |

**Why this order.**
- S0–S4 change what a formula means, so they go before the app moves (G),
  and the app's formulas change once.
- S5 is the largest and riskiest. It comes after the app moves, and before
  D, which needs row identity for re-running rows. It can be deferred
  without blocking anything earlier.
- D, E and F add features and break nothing, so after S5 they can go in any
  order. S6–S10 are small and mostly additive.

**The cheaper path.** S0–S4, then G, and S5 deferred: most of goal 1 and
all of goal 2, for well under half the remaining effort.

## 3. Done means

Phase 4 is done when:

1. every law in syntax-review.md §8, and in reshaping.md §10, passes, with
   nothing expected-to-fail;
2. the property tests at `STRESS=1` pass, generating formulas in the new
   syntax;
3. `scripts/core_asks.py` says **39 of 39** (K14, K15, K16 close with D and E);
4. every feature in features.md is done, or moved to "Later, by decision";
5. rules.md opens with the model, kernel-session.md shows what was built,
   and its example runs as a test;
6. the app runs on this core (app-migration.md §4).

Then phase 5, the final docs, starts.

## 4. Done so far in phase 4

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
