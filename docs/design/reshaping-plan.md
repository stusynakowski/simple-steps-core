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

**15 of the 40 law tests hold:** L2, L7–L11, L14, L17, L18, L28–L30, L34,
L35, L41. The other 25 are marked with the step that fixes them. L39 and L40
are not tests yet: steps 3 and 10 build them.

## 3. The path

### Step 3. The invariant check (L39)

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

### Step 4. Same samples (guarantee 3)

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

### Step 5. Provenance for every verb (guarantee 2)

`#` columns for the verbs that don't write them yet: `collapse` (`#v`, a list
per group), `distinct` (`#v`, the rows each kept row stands for), `join`
(`#a`, `#b`) and `stack` (`#a`, `#b`). Today `join` and `stack` leave their
inputs' `#` columns out, and `collapse` keeps its groups in a note (per-group
staleness, D3, already works from it: L41). Lineage says when a trace was
dropped.

- **Decide:** R-D12 (reductions); R-D9b (`distinct`).
- **Fixes:** M2, M3, M4.
- **Laws:** L15, L19, L31, L32.
- **Changes for users:** `collapse`, `distinct`, `join` and `stack` outputs
  gain `#` columns, and a click on their cells shows the exact input rows.

### Step 6. Round trips (guarantee 5)

Built-in reducers reduce each variable separately (R-D1). An `expand` of a
list `gather` made gives back the packed ids (R-D3). `collapse(by="#s")`
follows `#` columns back to any earlier step (R-D5), with a row for every
row of `s` (J-D5).

- **Decide:** R-D1, R-D5, J-D5. R-D3 is decided.
- **Fixes:** R1, R4, R9, J3.
- **Laws:** L1, L4, L6, L12, L13, L22, L33.
- **Changes for users:** `gather[collapse()]` on several columns gives one
  list per column, not a list of dicts.

### Step 7. The missing moves

`mod.pack(columns=…)` packs a row's variables into a dict (R-D2), and
`widen` drops the dict it spread (G10). `mod.expand(columns=[…])` unpacks
several lists together and carries the other columns (R-D4).

- **Decide:** R-D2 (and its name), R-D4.
- **Fixes:** R2, R3, R5, G10.
- **Laws:** L3, L5.

### Step 8. Uneven data

The `absent` cell state (J-D1); `widen` takes every key seen (J-D2);
`expand` never tidies (J-D3), with the built-in `as_list`; `expand` of a dict
gives `key`, `value` rows (J-D4).

- **Decide:** J-D1, J-D2, J-D3, J-D4.
- **Fixes:** J1, J2, J4, J5.
- **Laws:** L23, L24, L25, L26, L27.
- **Changes for users:** `expand` of a bare string or `None` no longer gives
  one row; it fails that row, or gives none.

### Step 9. The plan says how to go back

Each plan carries `inverse: rebuild | trace | opaque`, and for `rebuild` the
inverse step's formula (R-D8).

- **Decide:** R-D8.
- **Laws:** L21.

### Step 10. The property test (L40)

Generated grids that meet V1–V9 (reshaping.md §10), and generated chains of
verbs over them, each checked with `check_invariants` and the round-trip
laws. Hand-picked examples can't show closure; this can.

- **Decide:** add `hypothesis` as a dev dependency (recommended), or use a
  seeded generator with no new dependency.
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

Each one, with what core does today, what it does once decided, the
alternatives and a recommendation, is in
[reshaping-decisions.md](reshaping-decisions.md).

| | Decision | Status | Step |
|---|---|---|---|
| R-D1 | built-in reducers reduce each variable separately, under its own name; the `by` key is never in what they reduce | to confirm: changes `gather` on several columns | 6 |
| R-D2 | `mod.pack(columns=…)`; `widen` is its inverse and drops the dict column | to confirm; the name is open | 7 |
| R-D3 | an `expand` of a list core packed gives back its ids and origin | **decided** 2026-10-27 | 6 |
| R-D4 | `expand(columns=[…])` unpacks several lists together and, as a reshape, carries the other columns | to confirm: refines the 2026-10-20 decision for the tool-less form | 7 |
| R-D5 | `collapse(by="#s")` groups by the row of any earlier step | to confirm | 6 |
| R-D6 | core never parses ids | **built** (step 2) | 2 |
| R-D7 | rows line up only when core recorded how they match, so every row has exactly one partner: one origin, a child and its one parent, or `zip_(…, match_ids=True)`; otherwise `join` first. Checked when declared. A shared index name is not a match; missing rows block a column argument and refuse a `zip_` (as K19) | **decided** 2026-10-27 | 4 |
| R-D8 | the plan says `inverse: rebuild \| trace \| opaque` | to confirm | 9 |
| R-D9 | `table` is always its own origin | **decided** 2026-10-27: follows from R-D7 (a tool's index is no known match) | 4 |
| R-D9b | `distinct` records the rows it stands for | to confirm | 5 |
| R-D10 | `#` columns are grid columns, under the five guarantees | **decided** 2026-10-27; built for `expand` (step 2) | 2, 5 |
| R-D11 | `#` is the row id; the row number has no name | **decided and built** (step 2) | 2 |
| R-D12 | reductions: `#v` lists the group; empty values over no rows; a failed row blocks its group | to confirm (empty values built in step 1) | 5 |
| J-D1 | a cell state `absent` | to confirm | 8 |
| J-D2 | `widen` takes every key seen; missing is `absent`; types kept | to confirm | 8 |
| J-D3 | `expand` never tidies; `as_list` does it as a step | to confirm: changes `expand` of a bare string or `None` | 8 |
| J-D4 | `expand` of a dict gives `key`, `value` rows; `gather_dict` (name open) packs them back | to confirm | 8 |
| J-D5 | `collapse(by="#s")` gives a row for every row of `s` | to confirm | 6 |

## 6. Findings

Found by running core, 2026-10-27. Wrong answers given silently are in bold.

| # | What | Status |
|---|---|---|
| M1 | `expand` → `collapse` didn't round-trip per parent | fixed for a direct parent (step 2, L7); further back in step 6 |
| M2 | `collapse(by=…)`'s groups are kept in a note, not a `#` column (per-group staleness works from the note: L41) | step 5 |
| M3 | `distinct` traces a kept row only to itself | step 5 |
| M4 | `join` and `stack` trace to whole steps | step 5 |
| **M5** | **`zip_(v, select(join(w, v)))` puts Ben beside Dr X: counted ids pair by accident** | step 4 |
| M6 | `table` keeps the tool's index, so its rows claim to be its input's rows | step 4 |
| M7 | `k.cell` took a position | fixed (step 1) |
| **M8** | **lineage parsed id strings: a source with ids `a`, `a.1` traced an `expand`'s rows to the wrong parent** | fixed (step 2) |
| **M9** | **`zip_` parsed id strings: `zip_(v, expand(gather(v)))` put every row beside `v`'s row 0** | fixed (step 2): refused; pairs correctly after step 6 |
| **M10** | **a column argument pairs rows by equal ids across unrelated steps: `label(name, head=wf["jw"][cols["head"]])` gives Ben/Dr X** | step 4 |
| **M11** | **ids are matched as text: an int id `1` and a string id `"1"` pair as one row** | step 4 |
| M12 | a column argument from a parent into its child fails (*"'v' has no row '0.0'"*), though `zip_` makes the same match | step 4 |
| M13 | two `expand`s of one step are refused only for a column-name clash; renamed, they would pair item *j* with item *j* | step 4 |
| R1 | unpacking a gathered list gives new ids, not the packed ones | step 6 |
| R2 | no way to pack a row whatever its width | step 7 |
| R3 | `identity` under `map` packs a row into a dict only when it has 2 or more columns | step 7 |
| R4 | `gather` on several columns packs both axes in one step | step 6 |
| R5 | `expand` unpacks one list only | step 7 |
| **R6** | **every reducer gave `None` over no rows, `count` included** | fixed (step 1) |
| R7 | `collapse(by=…)` with a missing column | not a bug: refused when the columns are known |
| R8 | `cols["#"]` stored row numbers as data | fixed (step 2) |
| R9 | under `collapse(by=…)`, built-in reducers get the key in each row: `total` by ward fails | step 6 |
| J1 | `expand` wraps a bare string | step 8 |
| J2 | `expand` of `None` gives one `None` row | step 8 |
| J3 | `expand` of `[]` loses its parent for the way back | step 6 |
| J4 | `widen(columns=…)` fails rows missing a key; ints become floats; `null` and missing look alike | step 8 |
| J5 | `expand` of a dict gives one row holding the dict | step 8 |

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
