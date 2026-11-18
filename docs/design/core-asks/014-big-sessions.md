# 014 — The app's asks of core at `adfaf87` (v1.0.3): big sessions

> **Core's answers, 2026-11-17** (the asks follow, as the app sent them):
>
> | # | Status |
> |---|---|
> | **C50** | **done, for 1.0.4.** A page reads only its rows (`_preview_rows` slices data, states and notes to the window first; row states are computed with numpy, for the window); `k.cell` reads a one-row page; a step's plan is worked out once per result, and its lineage kept while it and its ancestors hold the same results. On a 1M-row step: `k.view("d", (0, 50))` 13.56 s → **37 ms** (2 ms again), a string column 13.01 s → 25 ms, `k.cell("d", 5)` 13.61 s → 37 ms. Every page equals the full view cut, and every cell its row: `tests/unit/test_paging.py` (first, middle, last, negative and empty windows; a stale step, failed rows, a step not run, lineage, lists of lineage) and the property test S8 |
> | **C52** | **mostly done with C50.** A step's state comes from its rows' distinct state codes, not a state per row as text: 1M rows, `step.state` 0.3 s → 2 ms, `needs_run()` 0.89 s → 17 ms, `run("d")` when current 0.59 s → 10 ms. P2 (states only from the store) finishes it |
> | C49 | open: plan P7d, with layer 3 (a save that skips a step whose data version matches the folder's) |
> | C51 | open: a typed Parquet column needs no untagging (only tagged columns do); with C49 |
> | C48 | open: `async def` tools, plan P1 |
> | Housekeeping 1 | **done**: `main` fast-forwarded to `v1.0.3` (`adfaf87`), so `origin/main` gives 1.0.3 |
> | Housekeeping 2 | done before this arrived: the release commit's guide pins `@v1.0.3` |
> | Housekeeping 3 | done: the guide no longer names the app's plan by number |
> | Housekeeping 4 | noted: the paging fix reads columns, not cells, so it doesn't meet `ArrowStringArray`'s slow `.at` |

> **For simple-steps-core.** From the Simple Steps app, 2026-11-17, while
> planning the move to 1.0.3 for working with large files. (Core's plan
> keeps 013 for its own list of the app's shims, P-D5.) Every number below
> was produced by running core alone, at the v1.0.3 tag (`adfaf87`,
> code identical to `5dcdac2`), Python 3.13, pandas 3.1.1, pyarrow 26.0.1:
>
> ```bash
> python scripts/core_probes/probe_big_session.py 300000 1000000
> ```
>
> The workflow: `src`, a DataFrame of `n` floats; `d = double[mod.map()](wf["src"])`;
> `small`, three rows; `pics = img[mod.map()](wf["small"])`, a 256×256×3 array
> per row. Durable entries are in the app's 008 under the same IDs.

**1.0.3 itself is fine to pin.** The app's 283 backend tests pass against it
unchanged; saving with outputs reads back exactly and reopens with nothing to
run; spilled cells (`MediaHandle`, `k.value`) work. The asks below are about
what happens when a step is big.

## Summary

| # | Ask | Kind | Priority |
|---|---|---|---|
| **C50** | A page view costs the page, not the step | 13.5 s for 50 rows of a 1M-row step | **1, as 1.0.4** |
| C49 | A save writes only what changed | every table rewritten on every save | 2 |
| C51 | A load converts columns, not cells | 3 s per million rows, one Python call per cell | 3 |
| C52 | Run-state reads after an edit don't scan rows | ~0.9 s per million rows, after every edit | 3 |
| C48 | `async def` tools | a silent wrong answer, still | 2 |
| — | Housekeeping: the tag, the guide | — | now |

## C50. A page view costs the page, not the step

| Rows in `d` | `k.view("d", (0, 50))` | `k.view("src", (0, 50))` | `k.cell("d", 5)` |
|---|---|---|---|
| 300,000 | 4.01 s | 3.84 s | 4.02 s |
| 1,000,000 | **13.56 s** | 13.01 s | 13.61 s |

No store and no save are involved: the kernel is in memory. On 1.0.2 the same
300k view took 2.64 s, so it was linear in the step's size then too; it's
~50% slower now because pyarrow makes pandas back every string column with
`ArrowStringArray`, and single-cell `.at` reads on it are slower.

**Why:** `Workflow._preview_rows` loops over `out.data.index` (every row) and
reads each cell with `out.states.at[...]` and `out.data.at[...]`, then the
window is cut afterwards. A profile of one 50-row page on 300k rows: 600,000
`DataFrame._get_value` calls, 1.2 M `ArrowExtensionArray.__getitem__`.

**Why it matters to the app:** the app holds the workflow's lock while it
calls `k.view` (`kernels.py:430`), so every scroll or cell click on a big step
blocks that workflow for the whole time (app plan 138 P1/N1).

**Ask:** slice `data`, `states`, the stale rows and the notes to the requested
window **before** the loop, so `k.view` and `k.cell` cost what they return.

**Test:** `k.view` of a 1M-row step returns in under 50 ms, and returns
exactly what it returns today for the same window (first, middle and last
pages; a stale step; a step with failed rows).

## C49. A save writes only what changed

`k.save(folder, outputs=True)`, then again with nothing changed: 300k rows
0.77 s and 0.73 s, 1M rows 2.40 s and 2.37 s; 10 of 13 files rewritten. **Ask:**
a save into an existing session folder skips a step whose data version matches
what's recorded there. Can come with P7d.

## C51. A load converts columns, not cells

`Kernel.load(folder, catalog)`: 0.83 s at 300k rows, 2.97 s at 1M; at 1M,
`saving.untag` called 3,000,047 times. **Ask:** a column Parquet read back
exactly needs no per-cell untagging; untag only the tagged-JSON columns.

## C52. Run-state reads after an edit don't scan rows

1M rows: `needs_run()` 0.89 s; the states of four steps 0.59 s; `run("d")` when
`d` is current 0.59 s. The app reads these after every edit. **Ask:** a step's
state and whether it needs a run come from its recorded versions, not a pass
over its rows; a speed test on a 1M-row step would pin it.

## C48. `async def` tools

`async def slow(x: float) -> float` under `map`: the step is `completed`, its
cell holds a `coroutine`. The app will refuse such tools until core does.

## Housekeeping

1. The v1.0.3 tag is only on `core-handover`, not `main`: please merge.
2. `docs/design/app-update-1.0.3.md` §2 pins `5dcdac2`: the app will pin the tag.
3. The app's plan for this move will be renumbered (`137` is taken).
4. For information: with pyarrow, pandas 3 stores string columns as
   `ArrowStringArray`; cell-at-a-time `.at` loops got slower in 1.0.3.
