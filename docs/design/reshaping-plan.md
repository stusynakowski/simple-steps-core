# Reshaping: the plan to a closed system

> The one place for the reshaping work: what is done, what is left, in what
> order, and what "done" means. The rules and laws it builds are in
> [reshaping.md](reshaping.md). Updated 2026-10-27 at `464e423`. Part of
> phase 4 of [cleanup-plan.md](cleanup-plan.md#4-order-of-work).

## 1. How to read it

Each step below is one piece of work. For each: the decisions it needs from
the owner, what it fixes, which laws start to hold, and what changes for
someone using core. A step starts when its decisions are confirmed and ends
when its laws pass, the whole suite is green, and it is committed.

The laws are the tests in
[tests/unit/test_reshape_closure.py](../../tests/unit/test_reshape_closure.py).
A law that doesn't hold yet is marked `xfail(strict=True)` with the step
that fixes it, so it fails loudly the day it starts to hold, and the mark
comes off.

## 2. Where we are

| Step | What | Commit |
|---|---|---|
| 1 ✓ | reducers give their empty value over no rows (R6); `k.cell` takes a row id (M7) | `8d622ed` |
| 2 ✓ | `#` is the row id (R-D11, R8); `expand` writes `#v` and steps that keep ids carry it (R-D10); rows are followed back through `#` columns, never by parsing ids (R-D6, M8, M9) | `b2ac908`, `45b547a`, `464e423` |
| 3 ✓ | the invariant check runs on every step of every test (`tests/conftest.py`, `Workflow.check_invariants`); it found and fixed P1–P3 and S1–S6 (§6) | `e2761d9` |
| 4 ✓ | rows meet only through a recorded match, checked when declared (R-D7): `zip_` and column arguments; `zip_(…, match_ids=True)`; ids match exactly; a parent's value reaches each child; A5 is enforced in every test | `daca7e2` |
| 5 ✓ | every verb records where its rows came from: `collapse` and `distinct` write `#v` lists, `join` and `stack` write `#a`, `#b`; a click on their cells shows the exact input rows; a dropped trace is named | `cc5a801` |
| 6 ✓ | reducers take lists, and grouping is a pack then a map (R-D1, R-D13); `expand(columns=…)` in lockstep (R-D4); unpacking what core packed gives back its rows (R-D3); `by="#s"` back to any earlier step, every row of it (R-D5, J-D5) | `42e49a4`, `51a9580`, `444f797` |
| 7 ✓ | `mod.pack`: a row's variables into one dict (R-D2); `widen` drops the column it spreads (G10) and, without `columns=`, takes the union of the keys (J-D2's union) | this commit |

**43 of the 49 law tests hold:** L1–L20, L22, L28–L39, L41–L49. The other 6
are marked with the step that fixes them: L23–L27 (step 8), L21 (step 9).
L40 (the property test) is built in step 10.

## 3. The path

### Step 3. The invariant check (L39) ✓

*Done 2026-10-27.* `Workflow.check_invariants(step, plan)` checks A1, A3–A6;
`tests/conftest.py` runs it after every step of every test, against the plan
the step had before it ran. A5 is reported but not yet enforced: four tests
zip or pair unrelated steps today (`test_009_zip_of_loaded_tables_pairs_by_id…`,
`test_C7_a_selection_as_an_argument_converts_by_type`, and
`test_a_column_pairs_with_the_rows_that_share_its_ids` twice). Step 4 refuses
those pairings, and they get `match_ids=True` or a `join`.

What was planned:

A function, `check_invariants(kernel)`, run after every test that runs a
kernel (through the test fixtures), asserting A1–A7 of
[reshaping.md §2.1](reshaping.md#21-airtight-precisely) on every step:
unique typed ids, no `#` column given to a tool, every `#v` value a row of
`v`, ids kept where a step keeps them, pairing only through a trace or
`match_ids`, the run matching an exact plan, and every loss a visible step.
A8 (inverses) is the round-trip laws.

And an audit of the 58 places that read a grid's columns directly
(`.columns` in `verbs`, `checks`, `combines`, `workflow`, `references`): each
becomes `variables(…)`, or says why it means every column.

- **Decide:** nothing. It changes no behaviour.
- **Why first:** it turns the edge cases still hiding in the existing 590
  tests into failures now, before the next steps build on them. Each one it
  finds becomes a finding in §6.

### Step 4. Same samples (guarantee 3) ✓

*Done 2026-10-27.* Six existing tests paired unrelated steps by equal ids
(K19's earlier behaviour). They now show the rule: the unrelated pairing is
refused when declared, with the hint, and a matched version still pairs.

What was planned:

One check, built on `Workflow.trace` and made when a step is declared:
*does every row have exactly one partner, through a link core recorded?*
(reshaping.md §6). Used by `zip_`, column arguments and the table view. Ids
keep their type: `1` is not `"1"`. Column arguments learn the parent→child
match `zip_` already has.

- **Decided** (2026-10-27): R-D7, with the `match_ids=True` opt-in; R-D9,
  `table` is its own origin. Nothing left to confirm.
- **Fixes:** M5, M6, M10, M11, M12, M13.
- **Laws:** L16, L16b, L20, L36, L37, L38, L42, L43, L44, L45.
- **Changes for users:** a `zip_` or column argument between unrelated
  steps whose ids happen to match is refused when declared. If the ids do
  mean the same samples, add `match_ids=True`; otherwise, `join`.

### Step 5. Provenance for every verb (guarantee 2) ✓

*Done 2026-10-27.* A `join`'s rows now trace to both inputs, so
`zip_(v, select(join(w, v)))` is a recorded match and pairs correctly: Ben
beside Dr Y. A list of rows (a group's, or the rows a `distinct` row stands
for) is never one partner, so `trace` doesn't pass through it, wherever the
column is carried. Eight tests that listed a `collapse`, `join`, `stack` or
`distinct` output's columns now include its `#` columns.

What was planned:

`#` columns for the verbs that don't write them yet: `collapse` (`#v`, a list
per group), `distinct` (`#v`, the rows each kept row stands for), `join`
(`#a`, `#b`) and `stack` (`#a`, `#b`). Today `join` and `stack` leave their
inputs' `#` columns out, and `collapse` keeps its groups in a note (per-group
staleness, D3, already works from it: L41). Lineage says when a trace was
dropped.

- **Decided** (2026-10-27): R-D12, R-D9b. Nothing left to confirm.
- **Fixes:** M2, M3, M4.
- **Laws:** L15, L19, L31, L32.
- **Changes for users:** `collapse`, `distinct`, `join` and `stack` outputs
  gain `#` columns, and a click on their cells shows the exact input rows.

### Step 6. Round trips (guarantee 5) ✓

*Done 2026-10-27*, in three pieces: reducers and group functions (6a);
`expand(columns=…)` and packed ids coming back (6b; R-D4 moved here from
step 7, because 6b needs it); `by="#s"` (6c). A `drop` of `#v` now stops a
trace for every step after it, not only that one: tracing back past it
skips the column it dropped. L4 and L5 need `mod.pack`, in step 7.

What was planned:

**The approach (owner, 2026-10-27): grouping is a new index, and a reduction
is a composition.** `f[collapse(by=k)]` is `gather[collapse(by=k)]` (re-index
by the key and pack each column into a list) followed by `f[map()]` over the
lists. So a group function (R-D13) needs no machinery of its own: it is a
`map` over a packed grid, and its lineage, plan and types follow. Law L49
checks the two give the same grid.

Built-in reducers reduce each variable separately (R-D1). An `expand` of a
list `gather` made gives back the packed ids (R-D3). `collapse(by="#s")`
follows `#` columns back to any earlier step (R-D5), with a row for every
row of `s` (J-D5).

- **Decided** (2026-10-27): R-D1, R-D3, R-D5, R-D13, J-D5. Nothing left to confirm.
- **Fixes:** R1, R4, R9, J3.
- **Laws:** L1, L4, L6, L12, L13, L22, L33, L49.
- **Changes for users:** `gather[collapse()]` on several columns gives one
  list per column, not a list of dicts.

### Step 7. The missing moves (now only `pack`; R-D4 is built in step 6) ✓

*Done 2026-10-27.* `widen()` with no `columns=` takes the union of the keys
seen, because `pack` ↔ `widen` needs it: that half of J-D2 is built here;
`absent` for a missing key is still step 8. A `widen` of a dict `pack` made
counts as carrying its columns unchanged, so unpacking after a round trip
still gives back the packed ids (L5). Six tests that expected `widen` to keep
the column it spread now don't.

What was planned:

`mod.pack(columns=…)` packs a row's variables into a dict (R-D2), and
`widen` drops the dict it spread (G10). `mod.expand(columns=[…])` unpacks
several lists together and carries the other columns (R-D4).

- **Decided** (2026-10-27): R-D2, named `pack`; R-D4. Nothing left to confirm.
- **Fixes:** R2, R3, R5, G10.
- **Laws:** L3, L5.

### Step 8. Uneven data

The `absent` cell state (J-D1); `widen` takes every key seen (J-D2);
`expand` never tidies (J-D3), with the built-in `as_list`; `expand` of a dict
gives `key`, `value` rows (J-D4).

- **Decided** (2026-10-27): J-D1 (widened to `stack` and `join` gaps), J-D2,
  J-D3 (with `as_list`), J-D4 (named `gather_dict`), J-D6 (`k.declare`).
  Nothing left to confirm.
- **Fixes:** J1, J2, J4, J5.
- **Laws:** L23, L24, L25, L26, L27.
- **Changes for users:** `expand` of a bare string or `None` no longer gives
  one row; it fails that row, or gives none.

### Step 9. The plan says how to go back

Each plan carries `inverse: rebuild | trace | opaque`, and for `rebuild` the
inverse step's formula (R-D8).

- **Decided** (2026-10-27): R-D8.
- **Laws:** L21.

### Step 10. The property test (L40)

Generated grids that meet V1–V9 (reshaping.md §10), and generated chains of
verbs over them, each checked with `check_invariants` and the round-trip
laws. Hand-picked examples can't show closure; this can.

- **Decided** (2026-10-27): `hypothesis`, as a dev dependency only.
- **Laws:** L40.

## 4. Done means

The reshaping system is closed, given valid variables, when all of these
hold:

1. `test_reshape_closure.py` has no `xfail` left: every law passes. That is
   A8, and the laws for A1–A7, of reshaping.md §2.1.
2. `check_invariants` runs after every test that runs a kernel, and passes.
3. The property test passes.
4. The 58 raw column reads are audited.
5. The docs say so: reshaping.md's laws all hold; the words *`#` column*,
   *trace*, *origin*, *pack*, *absent* are in object-model.md §1; the app's
   changes (§7) are handed over.

What still can't be done after that is in
[reshaping.md §11](reshaping.md#11-what-you-cant-do-even-when-its-closed):
those are limits of the design, not missing work.

## 5. Decisions

**Every decision is made** (2026-10-27): nothing in steps 3–10 waits on the
owner. Each one, with what core does today, what it does once decided, the
alternatives and a recommendation, is in
[reshaping-decisions.md](reshaping-decisions.md).

| | Decision | Status | Step |
|---|---|---|---|
| R-D1 | a reducer takes each column it names as a list (sometimes the group's rows as a list of dicts; the types say which). Built-in reducers do this per variable; the `by` key is never in what they reduce | **direction decided** 2026-10-27; details in R-D13 | 6 |
| R-D13 | how a group function gets its arguments: a column parameter → a list; `list[dict]` → the group's rows; the `by` key → its value; the `acc` form kept | **decided** 2026-10-27: a–e as recommended | 6 |
| R-D2 | `mod.pack(columns=…)`; `widen` is its inverse and drops the dict column | **decided** 2026-10-27: named `pack` | 7 |
| R-D3 | an `expand` of a list core packed gives back its ids and origin | **decided** 2026-10-27 | 6 |
| R-D4 | `expand(columns=[…])` unpacks several lists together and, as a reshape, carries the other columns | **decided** 2026-10-27: keeps the other columns of the grid it's given, so the reference decides which | 7 |
| R-D5 | `collapse(by="#s")` groups by the row of any earlier step | **decided** 2026-10-27 | 6 |
| R-D6 | core never parses ids | **built** (step 2) | 2 |
| R-D7 | rows line up only when core recorded how they match, so every row has exactly one partner: one origin, a child and its one parent, or `zip_(…, match_ids=True)`; otherwise `join` first. Checked when declared. A shared index name is not a match; missing rows block a column argument and refuse a `zip_` (as K19) | **decided** 2026-10-27 | 4 |
| R-D8 | the plan says `inverse: rebuild \| trace \| opaque` | **decided** 2026-10-27 | 9 |
| R-D9 | `table` is always its own origin | **decided** 2026-10-27: follows from R-D7 (a tool's index is no known match) | 4 |
| R-D9b | `distinct` records the rows it stands for | **decided** 2026-10-27 | 5 |
| R-D10 | `#` columns are grid columns, under the five guarantees | **decided** 2026-10-27; built for `expand` (step 2) | 2, 5 |
| R-D11 | `#` is the row id; the row number has no name | **decided and built** (step 2) | 2 |
| R-D12 | reductions: `#v` lists the group; empty values over no rows; a failed row blocks its group | **decided** 2026-10-27 (empty values built in step 1) | 5 |
| J-D1 | a cell state `absent`, for every cell whose source had no value: a key a record lacks, a column one input of a `stack` doesn't have, the unmatched side of an outer or left `join` (widened by the owner, 2026-10-27); the column keeps its type | **decided** 2026-10-27 | 8 |
| J-D6 | the empty step: `k.declare("x")` gives a step with no formula, a 1×1 grid holding `"empty"` (the project rule), never confused with `None` or `absent` | **decided** 2026-10-27 | 8 |
| J-D2 | `widen` takes every key seen; missing is `absent`; types kept | **decided** 2026-10-27 | 8 |
| J-D3 | `expand` never tidies; `as_list` does it as a step | **decided** 2026-10-27, with `as_list` | 8 |
| J-D4 | `expand` of a dict gives `key`, `value` rows; `gather_dict` (name open) packs them back | **decided** 2026-10-27, named `gather_dict` | 8 |
| J-D5 | `collapse(by="#s")` gives a row for every row of `s` | **decided** 2026-10-27 | 6 |

## 6. Findings

Found by running core, 2026-10-27. Wrong answers given silently are in bold.

| # | What | Status |
|---|---|---|
| M1 | `expand` → `collapse` didn't round-trip per parent | fixed (step 6): `by="#s"` reaches any earlier step |
| M2 | `collapse(by=…)`'s groups are kept in a note, not a `#` column (per-group staleness works from the note: L41) | fixed (step 5): `#v`, a list per group |
| M3 | `distinct` traces a kept row only to itself | fixed (step 5) |
| M4 | `join` and `stack` trace to whole steps | fixed (step 5): `#a`, `#b` |
| **M5** | **`zip_(v, select(join(w, v)))` puts Ben beside Dr X: counted ids pair by accident** | fixed (step 4) |
| M6 | `table` keeps the tool's index, so its rows claim to be its input's rows | fixed (step 4) |
| M7 | `k.cell` took a position | fixed (step 1) |
| **M8** | **lineage parsed id strings: a source with ids `a`, `a.1` traced an `expand`'s rows to the wrong parent** | fixed (step 2) |
| **M9** | **`zip_` parsed id strings: `zip_(v, expand(gather(v)))` put every row beside `v`'s row 0** | fixed (step 2): refused; pairs correctly after step 6 |
| **M10** | **a column argument pairs rows by equal ids across unrelated steps: `label(name, head=wf["jw"][cols["head"]])` gives Ben/Dr X** | fixed (step 4) |
| **M11** | **ids are matched as text: an int id `1` and a string id `"1"` pair as one row** | fixed (step 4) |
| M12 | a column argument from a parent into its child fails (*"'v' has no row '0.0'"*), though `zip_` makes the same match | fixed (step 4) |
| M13 | two `expand`s of one step are refused only for a column-name clash; renamed, they would pair item *j* with item *j* | fixed (step 4) |
| P1 | a row selection's plan claimed its input's row count, exactly (`wf["srt"][0:2]` planned 3 rows, got 2) | fixed (step 3) |
| P2 | `widen()` with no `columns=` planned exactly `['value']` | fixed (step 3): its columns are planned as unknown until it runs |
| P3 | `collapse(by=a_tool)` planned exactly 1 row and `['value']` | fixed (step 3): one row per group, columns unknown until it runs |
| S1 | `wf["p"].header` listed `#` columns as if they were variables, and carried `#v` onto rows that are column names | fixed (step 3) |
| S2 | `select(columns=a_tool)` and `rename(columns=a_tool)` called the tool on `#` column names, so it could rename `#v` | fixed (step 3) |
| **S3** | **a source or `table` tool could return a `#v` column and forge provenance; only an exact `#` was refused** | fixed (step 3): any `#` name is refused |
| **S4** | **`mod.name("#v")` and `rename(columns={"x": "#v"})` could forge an id column** | fixed (step 3): refused when declared |
| S5 | a source tool returning a `#` column raised out of `run_all` instead of failing its step | fixed (step 3) |
| S6 | which steps keep ids was listed twice (checks and workflow) | fixed (step 3): one `keeps_ids` rule |
| S7 | `distinct` with no `columns=` compared whole rows, `#` columns included, so equal rows from different parents stayed apart | fixed (step 5): it compares variables only |
| P4 | a built-in reducer's plan claimed exact columns while its input's columns weren't known, so a `select` after it was refused | fixed (step 6) |
| S8 | a `drop` of `#v` stopped the trace only at that step: tracing back past it reached `#v` again | fixed (step 6): the trace remembers what was dropped on the way back |
| R1 | unpacking a gathered list gives new ids, not the packed ones | fixed (step 6) |
| R2 | no way to pack a row whatever its width | fixed (step 7) |
| R3 | `identity` under `map` packs a row into a dict only when it has 2 or more columns | fixed (step 7): `pack` packs a row whatever its width |
| R4 | `gather` on several columns packs both axes in one step | fixed (step 6) |
| R5 | `expand` unpacks one list only | fixed (step 6) |
| **R6** | **every reducer gave `None` over no rows, `count` included** | fixed (step 1) |
| R7 | `collapse(by=…)` with a missing column | not a bug: refused when the columns are known |
| R8 | `cols["#"]` stored row numbers as data | fixed (step 2) |
| R9 | under `collapse(by=…)`, built-in reducers get the key in each row: `total` by ward fails | fixed (step 6) |
| J1 | `expand` wraps a bare string | step 8 |
| J2 | `expand` of `None` gives one `None` row | step 8 |
| J3 | `expand` of `[]` loses its parent for the way back | fixed (step 6) |
| J4 | `widen(columns=…)` fails rows missing a key; ints become floats; `null` and missing look alike | step 8 |
| J5 | `expand` of a dict gives one row holding the dict | step 8 |
| J6 | a `stack` of grids with different columns, and the unmatched side of an outer or left `join`, give `NaN`, turn ints into floats, and say `known` (G2) | step 8: `absent`, types kept |
| J7 | the empty step of the project rules isn't built: core can't declare a step with no formula (`k["x"] = None` makes a value step holding `None`) | step 8: `k.declare` |

## 7. For the app

What changes for the app repo (`Simple_Steps`), to hand over through
`core-handover/`:

| Change | Since |
|---|---|
| a step's `.data` includes its `#` columns (`#v`, …) before its variables | step 2 |
| `k.view` rows give the row id under `#`, and the screen position under `position` | step 2 |
| `k.cell(step, row)` takes a row id; `Workflow.cell` still takes a position | step 1 |
| `zip_` and column arguments between unrelated steps are refused; `match_ids=True` | step 4 |
| `collapse`, `distinct`, `join`, `stack` outputs gain `#` columns | step 5 |
| `gather[collapse()]` on several columns gives one list per column | step 6 |
| `expand` of a bare string or `None` fails the row, or gives none | step 8 |
| a new cell state, `absent` | step 8 |
