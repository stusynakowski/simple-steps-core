# 009 — The step output model: results, status, and references by index

> **Status: seven decisions made (§8), four recommended.** Written 2026-10-21 from the owner's
> notes on the interactive UI and step sessions. Supersedes the open
> questions in [008-row-ids-issue.md](008-row-ids-issue.md), and builds on
> 008's C7 (selection), C8/C9 (plans), C10 (failure) and C16 (row ids).
> Every "Today" line was produced by running core on 2026-10-21.

## Where the code is

- **Committed:** `9a86a0d` ("updated phase 5"). The accidental commit is the
  phase 5 work (C3, K12, M, P, N, C12), complete and tested. The app is
  already pinned to it. Nothing half-done went in.
- **Uncommitted:** "a step that computes is only its results" (`map`,
  `group`, `expand`), expand's derived row ids, and `zip_` by id. Whether to
  keep these is decided by this doc.

---

## 1. The model, in one sentence

> **A step's output is a grid of its own results, indexed by row ids it
> shares with, or derives from, its inputs, with a status record for every
> cell. Inputs are never copied into it; they are referenced by index.**

Everything below is how that sentence answers the owner's six points:

| # | Owner's point | Section |
|---|---|---|
| 1 | Reference arbitrary rows, columns and cells of a step's output as steps | §3 |
| 2 | Click any cell, run or not, and see its contents or what is expected there | §4 |
| 3 | Don't store input data with the output; store the minimum, including the status of each reference | §2, §5 |
| 4 | Share the index from one step to the next | §2 |
| 5 | Edit an earlier step: later outputs are shown stale but stay readable | §6 |
| 6 | Mapping: fail the whole step when some cells work? Prefer cheap failures | §7 |

---

## 2. What a step stores

```
step "score" = score[mod.map()](wf["readings"])

data (results only)          status (one record per row unit)
 id │ value                   id │ status    error            attempts  cause  read
────┼───────                 ────┼──────────────────────────────────────────────────
  0 │ 10.5                     0 │ completed                      1             r@3
  1 │ ‹fail›                   1 │ failed    ValueError: boom     1             r@3
  2 │ 31.5                     2 │ completed                      1             r@3
```

- **`data` holds only the step's results** (owner, 2026-10-20). A `map` is
  "append a column" conceptually, but the step *stores* only the column.
  The appended view is `zip_(wf["readings"], wf["score"])`, made when it's
  wanted, never saved twice.
- **The index is shared.** `map`, `group`, `filter`, `sort`, `select`, `slice`
  and `distinct` keep the input row's id; `expand` derives `1.0`, `1.1`
  from parent `1`. So any result cell points back to the input row(s) it
  came from by its id alone.
- **Status is per row unit,** as today: `status`, `error`, `attempts`,
  `seconds`, `unit`, `cause` (where a failure started) and `caught`.
- **New and minimal: what the row read.** `read` records the *version* of
  each step the row read when it ran (`r@3` = version 3 of `readings`).
  That one stamp is enough to tell, later, whether the row is stale (§6),
  without copying any input data. See §5 for how it's kept small.

**Today:** results-only data and expand's derived ids exist, uncommitted.
`read` doesn't exist.

### Row-id rules (C16, settled here)

| Verb | Output row ids |
|---|---|
| `map`, `group`, `filter`, `sort`, `select`, `slice`, `distinct`, `drop`, `rename`, `widen` | the input's (kept) |
| `expand` | derived from the parent: `"1.0"`, `"1.1"`, nested `"1.0.0"` |
| `collapse` | one new id per group (the key, or `0` with no `by=`) |
| `source`, `sweep`, `table` | new ids, `0…n-1` |
| `join` | derived from both parents, e.g. `"2+5"` (to settle) |
| `stack` | kept; prefixed with the input's step id where two would collide |
| `zip_` | the finest input's (see §2.1) |

### 2.1 `zip_` by id (the open issue from 008-row-ids-issue)

`zip_` pairs rows by id: the same id, or a derived row with its parent.
**Recommendation:** be strict, because a silent drop is the worst outcome.
Every row of every input must be paired, or the step fails, naming the
unmatched rows and pointing at `join` for partial matches. Positional
pairing is kept only for two grids with unrelated ids and equal length.
That fixes problem §5.1 of the issue doc, the silent drop. The result
takes the rows of the input whose ids are deepest (derived from the others);
when none is deeper, the first.

---

## 3. Selections of rows, columns and cells as steps

**Today (C7, committed):** `wf["block"] = wf["p"][1:5][cols["name":"price"]]`
is a `select` step. A single cell is `wf["p"][2][cols["price"]]`. Selecting
from a step that hasn't run declares fine and is checked when it runs.

**What's missing for the UI:**

- **Selecting what isn't there yet.** Over an unrun step whose row count is
  unknown (an unrun source), `wf["p"][2]` should stage as "row 2, *if it
  exists*". It plans with the step's known columns and types, and is
  checked at run (*"row 2 of 'p', which has 2 rows"*). The plan already
  carries columns and types (C5/C9); the row part needs a `bounded` /
  "if present" state.
- **Selecting by row id, not only position.** Positions are what a user
  clicks. Ids are what stays stable when an upstream step re-runs and
  reorders. **Proposal:** a click is saved as a position (as C7 says), and
  the UI shows the id beside it. `rows[id("1.0")]` (or `rows.ids["1.0"]`)
  selects by id when the user wants it pinned.
- **A cell is a selection.** No separate concept: a cell step is a
  one-row, one-column `select`, and an argument cell is a `$ref` with
  `rows` and `columns` (C7's saved form).

## 4. Clicking a cell: what the UI is shown

The UI needs one call that answers "what is in this cell?" for any step, run
or not.

**Proposal: `wf.cell(step_id, row, column)` and `wf.cells(step_id, rows=,
columns=)`** (a window, for paging large grids). Each cell comes back as:

```json
{"step": "score", "row": 1, "id": 1, "column": "value",
 "state": "failed",                // known | pending | maybe | unknown | failed | blocked | stale
 "value": null,                     // present when the state carries one (known, stale)
 "type": "float",                   // from the data, else the plan (C5/C8)
 "error": "ValueError: boom",       // failed
 "cause": "score[1]: ValueError: boom",   // failed or blocked: where it started
 "inputs": [{"step": "readings", "id": 1, "state": "known"}],   // §5
 "because": null, "resolve": null}  // why it isn't known yet, and how to settle it (C9)
```

| State | Meaning | Value shown |
|---|---|---|
| `known` | ran, completed, inputs unchanged | the value |
| `stale` | ran, but an input changed since (§6) | the **old value**, marked stale |
| `failed` | its tool raised | none; `error` |
| `blocked` | an input cell failed, so the tool wasn't called | none; `cause` |
| `pending` | not run; the row is known to exist | the planned `type` |
| `maybe` | not run; the row may not survive (`filter`) | the planned `type` |
| `unknown` | not run; whether the row exists isn't known (unrun source, `expand`) | the planned `type`, plus `because`/`resolve` |

For a column copied straight from an input (inside a `zip_` or `select`), a
`pending` cell can show its **value already**, because it's known (C8's
"known cells show their values").

**Today:** none of this exists. The pieces it reads from do: the ledger,
`Step.plan` (types, certainty, because/resolve) and `cause`.

---

## 5. The status of each reference in an expression

A step's formula names its references: the input (`wf["readings"]`),
argument references (`weight=wf["w"]`, `prices=wf["p"][cols["price"]]`),
setting references (`select(columns=wf["cols"])`) and resources
(`res["llm"]`). The UI should show, for each one, whether it's fine.

**Proposal: `step.references()`**, computed from the workflow plus the
`read` stamps, never stored as data:

```json
[{"name": "input",  "step": "readings", "selection": null, "state": "ok",    "version": 3, "read": 3},
 {"name": "weight", "step": "w",        "selection": null, "state": "stale", "version": 2, "read": 1},
 {"name": "llm",    "resource": "llm",                    "state": "not loaded"}]
```

| Reference state | Meaning |
|---|---|
| `ok` | exists, valid, and the version this step read is current |
| `stale` | changed since this step ran (`read` < `version`) |
| `has failures` | the referenced cells include failed or blocked ones |
| `staged` | hasn't run yet |
| `invalid` / `missing` | the step is invalid, or doesn't exist (C10's "not an earlier step") |
| `not loaded` | a resource the caller hasn't passed to `run` |

**The minimum stored, per step:** `read = {step_id: version}` for every step
it references, recorded at run. A **version** is a counter on each step,
bumped whenever its output changes (a run, or a source reassigned).
Everything else is derived. Row-level detail (§6) adds one small column,
and only when it's wanted.

---

## 6. Editing an earlier step: stale, but still readable

**Today:** editing a step marks every step that already read it `stale`
(the whole step), and their data stays readable. Running a step marks its
readers stale too (C10.5).

**Proposal, in two levels:**

1. **Step level (now):** the `read` versions (§5). A step is stale when any
   `read[x]` is behind `x`'s current version. That's more precise than
   today: re-running `x` with identical output need not mark anything stale
   (the version only bumps when the output actually changed, compared by a
   hash of the data).
2. **Cell level (with K15/C15):** a per-row fingerprint (a short hash of the
   row's values) on each step's status, and `read` per row holding the
   fingerprint of the input row it used. A row is stale only when *its*
   input row changed. Editing one input row then makes one output cell
   stale, not the whole column, and a re-run can redo just those rows.
   That is K15's "re-run only what's needed" and C15's "reuse results",
   from the same data.

Either way: **stale data is never deleted.** The UI shows the old value,
marked stale, until the step re-runs.

---

## 7. Failure policy for row-wise steps

The question: when some cells of a `map` fail and others work, does the
step fail as a whole?

**Today:**
- Each cell runs on its own. A failed cell is recorded; its siblings
  still run and keep their values.
- Cells that read a failed cell are **blocked**, at no cost: the tool isn't
  called.
- Then `run_all` **stops** (owner, 2026-10-19), unless the step has
  `mod.try_except(…)`.

**Recommendation: keep cells independent, and decide only what happens
*after* the step.**

| Choice | Cost of a failure | Keeps good cells? | Recommended |
|---|---|---|---|
| **A. Cells independent; the run stops after the step** (today) | one cell's work; nothing downstream runs | yes | **yes, as the default** |
| B. Cells independent; the run continues, downstream cells blocked | one cell's work; blocked cells are free | yes | as an opt-in: `mod.try_except()` (today), or `run_all(on_failure="continue")` |
| C. Fail fast: stop the step at the first failed cell | cheapest compute | **no**: later cells never run, and earlier ones are thrown away or left half-done | only as an opt-in, `mod.fail_fast()`, for expensive tools (LLM calls) where one failure means the rest will fail too |

Why A by default: the work already done is never thrown away; the run
doesn't spend money downstream of a known failure; and fixing the failed
cell and re-running redoes **one cell** (with §6's cell level), not the
column. That's the cheap failure.

Also cheap, and already built: everything checkable at declaration is
refused there (types, missing columns, shapes, selections), so most failures
never reach a run.

---

## 8. Decisions

### Decided (owner, 2026-10-21)

| # | Decision | Outcome |
|---|---|---|
| 1 | Store only a step's results, row ids shared across steps (§2) | **Yes.** The UI draws input columns beside results by id; nothing is saved twice. Keep the uncommitted results-only and derived-id work |
| 2 | `zip_` when rows don't all match by id (§2.1) | **Refuse**, naming the unmatched rows and pointing at `join`. Never drop rows silently. Positional pairing only for unrelated ids of equal length |
| 3 | How a step knows it's stale (§5, §6) | **A version per step, from a hash of its output data.** Each step records the versions of the steps it read. Stale only when an input's data really changed: re-running with identical output leaves readers fresh. Per-reference status in the formula bar comes from the same stamps |
| 4 | Failures in row-wise steps (§7) | **Cells independent, plus a circuit breaker that auto adds by default and the user can undo** (decision 5) |

**The circuit breaker** is one of auto's defaults (decision 5):
`mod.breaker(after=5)`. If `after` units **in a row** fail with the same kind
of error, the step stops. The rest are marked *"not run: stopped after 5
failures in a row (ValueError: …)"*, with `attempts: 0`, and work already
done is kept. One bad row never trips it; a bad API key costs 5 calls, not
one per row. Undo it per step by removing it, or with `mod.breaker(after=None)`
("never stop early", saved).

| # | Decision | Outcome |
|---|---|---|
| 5 | What "auto" is | **Auto is the set of defaults core applies when a call wouldn't run on the data as it's structured:** it picks the orchestration (`map`, `filter`, `collapse`, `expand`, `table`) and adds the default modifiers (the breaker). It applies implicitly (no modifier written) or explicitly (`mod.auto()`), and the UI always shows what it chose. A step whose orchestration the user wrote (`score[mod.map()](…)`) gets **no** hidden defaults |
| 6 | What an implicit auto saves | **`mod.auto()`**, written into the step, re-decided from the data at each run, and shown as *"auto → map, breaker(5)"*. Because auto is stated in the saved step, saved workflows keep running if implicit auto is later turned off |
| 7 | A direct call on raw data, `score(df)` | **Auto applies when the data doesn't fit as-is.** If `df` doesn't fit the first parameter's type (`n: int`) but its columns supply the tool's parameters, it runs over the rows and returns the result grid. If it fits as written (`df: pd.DataFrame`), or the tool is untyped, it's called plainly |

### Auto: the design

- **What auto decides:** the orchestration, from the tool's signature and
  the data (`infer_verb`: `-> bool` filter, `-> list` expand, an accumulator
  collapse, a `DataFrame` parameter table, otherwise map); and the default
  modifiers for that orchestration (row-wise: `breaker(after=5)`).
- **Implicit:** `score(wf["r"])` saves `score[mod.auto()](wf["r"])`. That's a
  change from today, which saves the concrete verb picked at writing time.
- **Explicit:** `score[mod.auto()](wf["r"])`, the same thing written out.
  Required when implicit auto is off.
- **Shown:** staging shows the provisional choice (already built for N:
  `meta["auto"]`, *"(auto, for now: …)"*). After a run, the actual choice and
  why (*"(auto, from the data: …)"*), plus the defaults it added.
- **Undo:** write the orchestration yourself (`score[mod.map()](…)`, no
  defaults), or keep auto and override one default
  (`score[mod.auto(), mod.breaker(after=None)](…)`: an explicit modifier
  beats auto's default of the same kind).
- **Direct calls:** `score(df)` follows decision 7. "Parens run" still holds:
  it runs, over rows when the frame doesn't fit as a single argument.
- **The setting (later):** a switch in the environment settings, e.g.
  `grid.settings.implicit_auto` (or an env var), default **on**. Off: a step
  with no orchestration is refused with *"score needs an orchestration: write
  score[mod.map()](…) or score[mod.auto()](…)"*, and `score(df)` on a frame
  that doesn't fit raises the same. Explicit `mod.auto()` always works.

### Recommended, not yet confirmed

| # | Decision | Recommendation |
|---|---|---|
| 8 | Selections by position or by id (§3) | Position by default (C7, spreadsheet-like), the existing warning when the order isn't fixed, and an explicit "pin this record" by id |
| 9 | `wf.cell` / `wf.cells` and the seven cell states (§4) | Build after 1–3; a pure read over saved data, easy to revise |
| 10 | Cell-level staleness (§6.2) | Step level now (with decision 3), cell level together with K15; old sessions fall back to step level |
| 11 | Row ids for `collapse`, `join`, `stack` (§2 table) | `collapse`: the group key; `join`: derived from both parents; `stack`: kept, prefixed on collision |

## 9. Build order and progress

| Step | What | Status |
|---|---|---|
| 1 | Strict `zip_`; results-only steps and expand's derived ids, with tests | **done** (2026-10-21), uncommitted |
| 2 | Hash versions and `read` stamps | **done** (2026-10-21), uncommitted |
| 3 | Auto: breaker, implicit `mod.auto()`, direct calls, the setting | **done** (2026-10-21), uncommitted |
| 4–7 | `wf.cell`, "if present" selections, `step.references()`, cell-level fingerprints | next |

**Step 1, as built:**
- `zip_` pairs by id and never drops a row. An unmatched row of the finest
  grid fails the step, and so does an unused row of a same-level grid, both
  pointing to `join`. Only a parent grid may have rows nothing points to (a
  row that expanded to nothing).
- Grids with unrelated ids pair by position when their lengths agree, and
  are refused when they don't.
- A combine that can't be made (`zip_`, `join`) now **fails the step** with
  its message instead of raising from `run`, so `run_all` stops with
  `StepFailed`.
- Tests: `tests/unit/test_008_asks.py`, the `test_009_*` group. Probe: `C16`
  (expand ids only).

**Step 2, as built:**
- `wf.version(step_id)` is a 12-character hash of the step's data (row ids,
  columns and values), saved in `output.meta["version"]`. Literal sources get
  one when assigned; other steps when they run.
- When a step runs it records `output.meta["read"]`: the version of every step
  it read (input, argument and setting references), and `"res:<name>"` for
  each resource (a hash of its declaration).
- A step is **stale** when a step it read has a different version now, or is
  stale itself (transitively). Re-running with an identical result, or
  changing a source and then changing it back, leaves readers fresh. Stale
  data is kept and readable.
- Outputs saved before stamps existed (no `read`) keep the old rule: any
  change upstream marks them stale.
- One test changed meaning: re-running a failed root with the same result no
  longer marks what it blocked stale; fixing it does.
- Tests: `test_009_*` (7 more). Stamps and staleness survive a saved session.

**Step 3, as built:**
- **`mod.breaker(after=5)`** is an execution modifier. After `after`
  failures in a row of the same kind, the rest of the step's units are
  recorded as *"not run: stopped after 5 failures in a row (ValueError: …)"*
  with `attempts: 0`; no call is made. `after=None` never stops early.
  `try_except` re-raises a breaker stop rather than turning it into its
  default.
- **Auto adds it.** When auto resolves to a row-wise verb (`map`, `filter`,
  `group`, `expand`) it adds `breaker(after=5)` just inside the verb, unless
  the step already states a `breaker`. The reason reads *"…; adds
  breaker(after=5)"* in `meta["auto"]` and in `describe()`. A step whose verb
  is written gets nothing added.
- **Implicit steps save `mod.auto()`.** `score(wf["r"])` is
  `score[mod.auto()](wf["r"])`. Staging shows the verb it would pick now; a
  run records the one it picked (`output.meta["auto"]`).
- **Direct calls:** `score(df)` returns an `Output` over `df`'s rows when the
  tool's first parameter is typed, a frame doesn't fit it, and `df`'s columns
  supply every required parameter. Otherwise the tool gets `df` as-is.
- **`grid.settings.implicit_auto`** (env `SIMPLE_STEPS_IMPLICIT_AUTO=0` to turn
  it off). When off, a step with no orchestration raises *"score needs an
  orchestration: write score[mod.map()](…) or score[mod.auto()](…)"*, and a
  direct call passes the frame as-is. A written `mod.auto()` always works.
- Tests: `test_009_*` (6 more). The inference tests now check the verb auto
  picks (`output.meta["auto"]["verb"]`) rather than a saved concrete verb. The
  example prints auto's choices and reasons.

**What changes for users of core (steps 1–3):**
- `score(wf["r"])` saves `mod.auto()`, not `mod.map()`; auto adds a breaker
  to row-wise steps.
- `score(df)` on a typed tool runs over rows instead of passing the frame.
- A `zip_` that can't pair every row fails the step instead of returning
  fewer rows. A failed combine no longer raises from `run`.
- Re-running a step with an identical result no longer makes later steps
  stale.

### The plan, in order



1. Make `zip_` strict and commit the results-only/row-id work, with its tests.
2. Step versions from data hashes, and `read` stamps; `stale` from versions
   (§5, §6.1).
3. Auto (decisions 5–7): `mod.breaker(after=…)`; implicit steps save
   `mod.auto()`; auto adds its defaults; an explicit modifier overrides a
   default of the same kind; `score(df)` runs over rows when the frame
   doesn't fit; the `implicit_auto` setting.
4. `wf.cell` / `wf.cells` and the cell states (§4; recommendation 9), reading the ledger and
   plans.
5. "If present" row selections over unknown row counts (§3).
6. `step.references()` (§5).
7. Cell-level fingerprints, with K15 (§6.2).
