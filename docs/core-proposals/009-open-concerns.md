# 009 — Open concerns to come back to

> **Status: parked, 2026-10-21.** The owner's concerns from the step-output and
> UI design session, with what's built so far and what's still undecided.
> Design: [009-step-output-model.md](009-step-output-model.md). Visualization:
> https://claude.ai/artifact/JNCsXgmxi1E8YpFuyYjzfr (private).
>
> **Uncommitted** in core when this was written: the data/states/meta output,
> `wf.preview` / `wf.cell`, edited steps keeping their output, short stale
> reasons, input values in `wf.cell`, `ran_with` / `wf.arg_changes`, and saved
> format version 3. 582 tests pass.

## 1. Seeing inputs without it becoming a distraction

**Concern.** The goal is simple: see the inputs a result came from. Showing
references everywhere is overwhelming, but they're useful sometimes. They
must never take away from the experience.

**Where it stands.** On demand only. The grid shows just the output and its
states. Selecting a cell adds one quiet line under the grid,
`from r[2] · city LA · n −1`. "Show inputs" puts input columns beside the
grid, lighter and labelled. `wf.cell()` returns each input row's id, state
and first 6 values (`+N more`).

**Open.** Is one line on selection the right amount? Should "Show inputs"
exist at all, or only the line? Hover or click? How should it work for
steps with several inputs (a zip), or wide rows?

## 2. Don't store inputs for every cell

**Concern.** Saving every input for every cell would be too much.

**Where it stands.** Nothing is stored per cell. A cell's inputs are looked
up from its row id when it's clicked (`expand` items derive their parent's
id: `1.0` → `1`). Per step, core stores only `read` (one version stamp per
step it read) and `ran_with` (its formula and arguments as text).

**Update (010 C25).** Per-cell staleness is built: a row-aligned step now
stores one short hash per input row, over only the columns it reads, so
editing one input row makes only its cells stale. That's the only per-row
record, and it's a hash, not the inputs.

## 3. Mistaking inputs or old values for the output

**Concern.** If arguments or inputs are shown near a result, people may take
them for the output. Clicking a stale cell must make clear its value was
**not** computed with the arguments now shown.

**Where it stands.** Inputs are set apart: lighter, labelled `input r`, and
behind a toggle. A stale output from an edited argument says so in the
caption, *values below were computed with weight=1.5, the default (now
2.0)*, and in the cell detail, *stale output · computed with weight=1.5, the
default (now 2.0)*. From `wf.arg_changes()`.

**Open.** Is that wording clear enough at a glance? Should the old argument
also be marked in the formula itself (e.g. the changed value underlined)?

## 4. Visual language: subtle, greys for scale

**Concern.** Orange is too loud. Greys should carry state and scale. Cell
details should be subtle, and stale labels short (`stale output (updated
args)`).

**Where it stands.** The visualization is greyscale: tone and a glyph per
state (`✕` failed, hatched blocked, `‹float›` planned, faded stale, dashed
maybe). Stale reasons are short: `updated args`, `input r changed`,
`resource llm changed`, `r is stale`.

**Open.** Whether failure needs any colour at all. A greys / muted-colour
toggle on the visualization was offered, to compare.

## 5. Do we need a "re-run"?

**Concern.** Unsure a re-run is needed at all.

**Where it stands.** Core only recomputes when asked. That's why "stale"
exists: the old output is kept until a run. Proposed, **not decided**:

| Step | On an edit |
|---|---|
| cheap and deterministic | recomputes automatically, like a spreadsheet; no "stale" shown |
| expensive or non-deterministic (LLM, web, slow) | shows stale, waits for the user to run it |
| marked `mod.lazy()` | when it runs, computes only what changed |

How a step is classified could come from the tool (a `deterministic` /
"expensive" flag, the app's C15), with a per-step override. A `wf.refresh()`
(or the app) would recompute the automatic ones after each edit, with auto's
breaker as the guard.

**Open.** Automatic for cheap steps, or everything manual? Who classifies
steps: the tool, the step, or the app?

## 6. Lazy compute

**Concern.** "Lazy compute": only compute when arguments changed, and only
when asked for, as a modifier on the step.

**Where it stands.** **Not built.** Intended shape: `mod.lazy()`. On a
run, if neither the arguments nor the input changed, nothing is recomputed.
If only some input rows changed, only those rows run; failed rows run again.
For `map` and `group` first (1:1 rows). It needs a short per-row hash of the
input, stored only for lazy steps.

**Open.** Should failed rows re-run under lazy? Which verbs besides `map` and
`group`? Does lazy imply automatic recompute (§5)?

## 7. Smaller items noticed along the way

- `join` and `stack` don't carry cell states yet (`zip_` does).
- Row ids for `collapse`, `join` and `stack` (009 recommendation 11).
- The walkthrough notebook and the app's `008-status.md` still describe the
  ledger. `009-status.md` is current.
- Selection *steps* over rows that may not exist yet; `step.references()`
  (009 steps 5–6).
