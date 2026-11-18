# Moving the app to core 1.0.3

> For the Simple Steps app, written 2026-11-17. **Core 1.0.3 is tagged
> `v1.0.3`** (branch `core-handover`, after 1.0.2 `dbaf4c7`); every property
> test passed at 2,000 examples on its code. Every change was run in core, with
> tests; what the app sees is also kept, row by row, in
> [plan.md §5](plan.md#5-changes-the-app-will-see). The app's own plan for the
> move is in its `docs/dev_plan/` (its number is the app's to give).

## 1. In one paragraph

Two silent wrong answers and two silent stale states are fixed, so some
results and states the app shows will change, rightly. Sessions can be saved
as a folder, one sub-folder per step with its table and its files, exactly,
with or without results, and reopened with nothing to re-run: that replaces
the app's C32 shim. Running brings steps up to date instead of redoing them.
Stages group consecutive steps and run as one. Bulky cells (images, arrays,
figures) can be kept on disk with a handle in the cell, opt-in. `k.view` no
longer crashes on arrays, so the C37 shim goes. pyarrow is a dependency.

## 2. Pin

```toml
"simple-steps-core @ git+https://github.com/stusynakowski/simple-steps-core.git@v1.0.3",
```

(or the tag's commit hash, as the app pins today), and the submodule to the
same commit. **pyarrow comes with it** (`pyarrow>=14`, a dependency of core
now): the app's environment doesn't have it today (checked 2026-11-17), so
reinstall after moving the pin, and `scripts/smoke_install.py` should see it.

## 3. What changes for what the app already does

Check each; the app's tests that assert the old behaviour should be updated
to the new one, as at 1.0.1.

| | Change | Where the app meets it | What to do |
|---|---|---|---|
| A | **Run brings steps up to date.** `k.run(x)` and `k.run_all()` leave a step that is current (completed, or failed, nothing it was made from changed) as it is; `force=True` runs it again. A source tool (no input) runs again whenever it is run by name: a reload. A standing failure nothing handles still stops `run_all`, without re-running | `kernels.py:502` (*Run step*) calls `s.k.run(name)`: a completed step clicked again no longer recomputes, and a failed one isn't retried | offer **Run again** / **Retry** as `s.k.run(name, force=True)`; the plain button stays `run(name)`. `ran = [n … if version changed or n == name]` still holds |
| B | **A column argument under `collapse` gets each group's values** (it got the whole column): `mean[mod.collapse(by="ward")](wf["v"], temp=wf["v"]["am"])`. A column from rows that aren't the input's is refused, `bad_pairing`, writing the join; a parameter typed as one value is refused, *declare temp: list* | any example or user workflow written that way | its results change: they were wrong. Show the refusals |
| C | **A step whose binding core wrote by type** (`slow=wf["a"]["a"]`) **now goes stale** when that column changes; it stayed `completed` | the grid's out-of-date marks | more steps show stale, rightly |
| D | **Change detection reads objects by content** (images, arrays): a change inside a big array is seen; an image's and a figure's **data version is its content** (mode, size, pixels, info; a figure's canonical JSON), and bytes have a token | image and figure columns | readers of image or figure columns may show `stale` once after the update, then stay right |
| E | **Every load checks restored results as they are now**: a tool whose code changed shows `stale`, *tool changed*. Also through the internal session export the C32 shim calls, where it showed `completed` | `restore_with_outputs` | right after the update a reopened workflow may show stale steps whose tool changed; they were showing old results as current |
| F | **A step given a DataFrame, loaded from a light `to_json`, is `invalid`** (code `data_missing`), saying the data isn't in the file; `run_all` no longer raises for it. A data step's spec carries `"data": {"in": …}` | `file_manager.py` if it saves `k.to_json()` without data | save sessions with `k.save` (§4); show `data_missing` |
| G | **`k.view` and `k.cell` don't crash on arrays** (C37): an array stays an array | `core_bridge._patch_plain` | **delete the C37 shim** |
| H | `describe()` shows `map`'s `name=` defaulting to the step's name (fixed in 1.0.2) | `core_bridge` C36 | **delete the C36 shim** |
| I | `Workflow` has two new attributes, `stages` and `spill` | only if the app reads `vars(k.workflow)` | nothing |

## 4. Saving a session: replaces the C32 shim

```python
report = k.save(folder, outputs=True)       # results too: reopens with nothing to run
k = Kernel.load(folder, catalog)            # runs no code
report["exact"]                             # True, or report["steps"][name] says what wasn't
```

```
<folder>/
  workflow.json          the workflow; each step names its folder
  report.json            what the last save couldn't keep exactly
  data/<step>/
    table.parquet        its table: the data given to it, or its results
    states.parquet       with outputs: a state per cell
    meta.json            with outputs: its record
    files/<hash>.<ext>   the arrays (.npy), images (.png/.tiff), figures (.json) it holds
```

- **Exact or reported:** every column reads back exactly (checked by data
  version) or is listed in the report; an image keeps its pixels, format and
  info; nothing is pickled.
- **On load:** a step whose data file is missing or changed is `invalid`
  (`data_missing`), saying so; a result whose file is missing or changed, or
  whose tool changed, needs a run (`staged` or `stale`); nothing raises.
- **Saving again** into the same folder replaces it; core removes only its own
  files that nothing names any more.

**In the app:** `core_bridge.save_with_outputs` / `restore_with_outputs`
become `k.save(folder, outputs=True)` / `Kernel.load(folder, catalog)`, with a
folder per workflow (next to its `.simple-steps-workflow`, or as it). Show the
report when it isn't exact. **Delete the C32 shim.**

## 5. New, to adopt when ready

| | What | How |
|---|---|---|
| Stages | a named group of consecutive steps, run and shown as one | `k.stage("prep", first="load", last="tidy")`, `k.stages`, `k.stage_of(step)`, `k.run_stage("prep", force=False)`, `k.unstage`, `k.rename_stage`; **`k.stage_status("prep")`** → `{"state", "steps", "needs_run", "output"}`: the stage as one step, its table its last step's. Saved in the workflow; in no id; kept valid through insert, move, rename, delete. A stage edit sends no `on_change` yet: read `k.stages` after an edit |
| Bulky cells on disk (opt-in) | images and arrays kept on disk, a handle in the cell | `Kernel(catalog, spill_over=1_000_000, store=folder)`: each array, image or figure of that many bytes or more goes to `folder/data/<step>/files/` when its step runs; its cell holds a **`MediaHandle`** (`.summary` "RGB image 256×256", `.kind`, `.value_type`, `.load()`). Tools get values; versions and states don't change. **`k.value(step, row, column)`** loads one. Point `store` at the workflow's session folder and `k.save` copies nothing. `Kernel.load(folder, catalog, spill_over=n)` keeps a session's files on disk |
| Run again | recompute or retry | `k.run(name, force=True)`, `k.run_all(force=True)` |

**To turn on bulky cells**, `cell_types.py` renders a `MediaHandle` from its
`.summary` and `.kind` (a placeholder, no pixels), and `/api/cell` loads the
value with `k.value(step, row, column)` when a cell is opened. Until then,
leave `spill_over` unset: nothing changes.

## 6. Shims after this

| Shim | After 1.0.3 |
|---|---|
| C32 save with outputs | **delete**: `k.save(folder, outputs=True)` |
| C36 `name=` default | **delete** |
| C37 `_plain` on arrays | **delete** |
| C18 description is the first line | still needed (P1) |
| C33 `inspect.signature(tool)` | still needed (P1) |
| C34 `check_modifier`, `shape_verbs` internal | still needed (P1) |
| C45 `SelectionError` not `FormulaError` | still needed (P1) |

## 7. Gates

As at 1.0.1: `pytest` at baseline, `examples/runme.py`, `npx vitest run`,
`scripts/preflight.py --fix`, `scripts/smoke_install.py`, and the UI end to
end: declare, run, edit (stale), **save, close, reopen with nothing to run**,
run again.
