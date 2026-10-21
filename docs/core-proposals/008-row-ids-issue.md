# Open issue: linking a step's results back to its input rows

> **Superseded (2026-10-21) by [009-step-output-model.md](009-step-output-model.md),**
> which folds this issue into the full step output model and recommends an
> answer for each open question here.

> **Status: open — to sort out 2026-10-21.** Written 2026-10-20. Covers a
> problem created by two owner decisions that day, and a first fix that is
> **uncommitted** in the working tree on top of `d0507c2`.

## 1. The problem in one paragraph

On 2026-10-20 we decided that a step that computes outputs **only its
results**: `map`, `group` and `expand` no longer carry their input's columns.
To see an input row and its result together, you now combine the two steps.
That works for `map` and `group`, whose output keeps each input row's id
(the DataFrame index). It does **not** work for `expand`. One input row
becomes several output rows, `expand` renumbered them `0, 1, 2…`, and so
nothing linked an item back to the row it came from. Only the ledger's
`unit` column said which parent produced it. **We need a reliable way to
get from any result row back to the input row(s) it came from.**

> **Note (owner, 2026-10-20): we can reference the inputs with the index of
> the grid.** Every grid has an index, so a result row never needs to carry
> its input's columns. Its index is the reference back to the input row it
> came from. A step that computes outputs only its results, and the input is
> reached through the index, not copied. Whatever we decide below should keep
> that rule: **the index is the link from a result to its inputs**, for every
> verb, including `expand`, whose items point to their parent row.

## 2. Why it matters

| Situation | Before 2026-10-20 | After the decision, before the fix |
|---|---|---|
| `map`, then read `city` | `city` was carried in the map's output | must `zip_(wf["in"], wf["map"])`: works, the ids line up |
| `group` → `collapse(by=…)` | the key sat beside every column | `zip_(rows, keys)`, then collapse: works |
| `expand`, then read the parent's `city` | `city` was carried on every item | **impossible.** The item rows have new ids and different counts |
| `zip_` of a **sorted or filtered** step with its source | paired **by position**: silently wrong rows | same bug (zip ignored ids) |

The last row was a silent wrong answer before any of today's changes.

## 3. The idea: every row's id says where it came from

The index is always there, so make it carry the lineage:

- **`map`, `group`, `filter`, `sort`, `select`, `slice`, `distinct`** keep
  the input row's id. (They already did.)
- **`expand`** gives the *k*-th item of row `1` the id `"1.k"`: `1.0`, `1.1`,
  …. Expanding again goes one level deeper (`1.0.0`). This is the app's
  **C16** rule for `expand`.
- **`zip_`** pairs rows **by id**: the same id, or a derived row (`1.0`) with
  its parent (`1`). This gives every item its parent's columns, and fixes
  the sort/filter misalignment.

## 4. What is built (uncommitted)

All in `src/simple_steps_core/grid.py`. **544 tests pass**, but **no new
tests were written for this yet** (see §6).

| Change | Where |
|---|---|
| `expand_` assigns ids `f"{parent}.{k}"`. A failed or blocked parent gets one placeholder row, `"{parent}.0"` | `expand_`, `_child_id` |
| `_ancestors("1.0.2")` → `["1.0", "1"]` | new helper |
| `zip_` (`_combine_zip`) pairs by id. The result takes the rows and ids of the **deepest** grid (the one with derived ids), or the first grid when depths are equal | `_combine_zip`, `_align`, `_row_lookup` |
| `zip_` falls back to **position** when the grids share no ids at all and have the same length | `_combine_zip` |
| A saved session keeps ids as written: `read_json(..., convert_axes=False)` | `_decode` |

Checked by hand (2026-10-20):

```
items ids: ['0.0', '1.0', '1.1', '2.0']          # expand over rows 0, 1, 2

zip_(items, readings):
     value city  n
0.0     10   SF  1
1.0     20  NYC  2
1.1     21  NYC  2      # both items of row 1 get row 1's columns
2.0     10   LA  1

zip_(readings, map over a sorted step): paired by id → correct rows
ids after save + reload: ['0.0', '1.0', '1.1', '2.0']   # unchanged
```

## 5. Known problems with the fix as it stands

1. **Silent data loss: a partial overlap now drops rows.** Two grids with
   ids `0, 1` and `0, 1, 2` used to be refused ("zip needs grids of equal
   length"). Now the second is aligned to the first, and its row `2` is
   dropped **without a message**. This must be decided before committing.
   Options: (a) refuse unless every row of every grid is matched, (b) keep
   the finest grid's rows but refuse if another grid has rows nothing points
   to, or (c) a `how=` setting like `join`.
2. **Which grid sets the rows is implicit.** "Deepest, else first" means
   `zip_(a, b)` and `zip_(b, a)` can have different row counts. It may be
   clearer to always use the first grid, or to require the finer grid first.
3. **Mixed id types.** Most steps have integer ids (`0, 1, 2`), while expand
   outputs have strings (`"1.0"`). Matching compares `str(id)`, so it works,
   but a user reading `.loc[1]` on an expand output gets a `KeyError`
   (it's `.loc["1.0"]`).
4. **Ids that already contain dots.** A source whose own index has values
   like `"a.b"` looks like a child of `"a"`. Rare, but wrong if it happens.
   A tuple / MultiIndex id would avoid it, but is harder to save as JSON.
5. **Staging doesn't know expand ids** until the step runs, so a planned
   `zip_` after an `expand` can't predict its row count. That's consistent
   with expand's "unknown count" today.
6. **Only part of C16.** C16's table also asks for `collapse` (one new id),
   `group` keys as ids, `join` (derived from both parents) and `stack`
   (prefixed on collision). None of those are done.
7. **Combine verbs still drop failures.** `zip_`/`join`/`stack` build a
   fresh ledger, so a failed cell upstream is not carried through them (the
   C10 gap already listed in [008-status.md](008-status.md)).
8. **`convert_axes=False` changes how every saved frame reloads.** Integer
   ids still load as integers in the cases checked, but we haven't tested
   frames with date-like or other unusual indexes.

## 6. Not done yet

- No tests for: expand ids, nested expand, `zip_` by id (same id, parent id,
  position fallback, refusal), sort/filter then zip, save and reload of
  string ids, blocked/failed expand rows.
- `scripts/core_asks.py` has no C16 probe.
- [008-status.md](008-status.md) and [008-dev-plan.md](008-dev-plan.md)
  don't mention any of this yet. They describe expand's lost link as an open
  gap, and `zip_` as positional.
- The example (`examples/all_orchestrations/pipeline.py`) still has
  `zipped = zip_(ns, scores_only)`. Both keep the readings' ids, so it still
  works, but nothing shows the expand-then-zip pattern.

## 7. Decisions to make tomorrow

1. **Keep the approach?** Derived string ids plus `zip_` by id (§3), versus
   an alternative:
   - a separate lineage column (for example `_parent`) that expand writes
     and `join` can use; or
   - a MultiIndex `(parent, k)` instead of `"parent.k"` strings.
2. **Partial overlap in `zip_`** (§5.1): refuse, keep the finest grid's rows,
   or add `how=`.
3. **Which grid sets the rows** (§5.2).
4. **Do the rest of C16 now** (collapse, group, join, stack ids), or only
   expand?
5. **Commit as is, or revert first?** If tomorrow's answer is different, the
   fix is small to revert. It touches `expand_`, `_combine_zip` and
   `_decode`, plus three small helpers.

## 8. Where things stand

- Last commit: `d0507c2` (staging and error handling).
- Uncommitted:
  - phase 5 (C3, K12, M, P, N, C12) and the "only its results" decisions for
    map/group/expand, both documented in [008-dev-plan.md](008-dev-plan.md)
    and [008-status.md](008-status.md);
  - this row-id fix, **documented only here**.
- Tests: 544 passing. Probes: 34 of 38 (K14, K15, K16, K18 open).
