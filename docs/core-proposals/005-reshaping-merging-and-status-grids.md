# 005 — Reshaping, merging, and the status grid

**Status: proposal — decisions made, to implement.** Extends the grid model with
multi-input combine verbs, a warning/severity tier, and a cell-shaped status
grid. Builds on [004](004-grid-adoption.md) (A1–A5 shipped) and settles the
open questions in [status.md §4d](../status.md) (D1 multi-input).

Every claim below was probed against the current `grid.py` with the dev venv
active. The design is deliberately conservative: it *completes* existing
invariants rather than bending them.

---

## 0. What already holds — the baseline (do not rebuild)

Verified this cycle:

- **Declaration is lazy.** `wf[id] = expr` stages and validates; it runs nothing.
- **Value references (K10).** A bound argument may be a `StepRef`, resolved at
  run (one-cell → the cell, else the whole grid).
- **`operation.reads` is generic.** It is the input plus every `StepRef`
  argument; `run()`/`run_all()` order and guard off it. The guard already
  covers argument references:
  `ValueError: step 'flag' reads 'cutoff', which has not run.`
- **Structural `#REF!` already hard-fails.** A dangling / circular /
  cross-workflow reference is a declaration-time problem.
- **Every output payload is a `DataFrame`.** A scalar is a 1×1 grid, an empty
  result is a 0-row grid with typed columns, a source coerces.
- **P5 (scalar broadcast) is solved** by value references — so status.md §4d P5
  and §7 item 1 are stale and are corrected as step 1 of the plan.

---

## 1. The invariants this proposal preserves

The contract every change below is held to:

1. **Grids are flat with a known column set.** Rows may be unknown
   (`expand`, `join`); columns are strict — known or declared.
2. **Strict on the graph, optimistic on the data.** Structural facts are checked
   at declaration; data-shape facts are deferred to run ("if it breaks, it
   breaks"), surfaced as warnings, never silently assumed.
3. **References live in inputs or arguments, never in modifiers.** Modifiers are
   literal-only, because they are shape-determining and must be knowable at
   staging.
4. **Declaration is lazy, and every grid a verb consumes appears in `reads`.**
   Run-ordering and the run guard follow from this alone.
5. **Every output is a `DataFrame`.**

---

## 2. Decision A — formalize referencing-before-run (+ one fix)

**A1. Write invariants 4 and 2 into the model contract.** They already hold for
the single-input case; stating them is what lets the multi-input verbs inherit
lazy declaration, ordering, and the run guard for free.

**A2. Fix: a shape verb missing a required literal must fail at *declaration*,
not run.** Today `mod.select()` / `mod.drop()` with no `columns=` passes `check`
and raises `ValueError` only at run. Decision: `check` rejects a shape verb whose
required params are absent, as a declaration-time problem — consistent with
every other declaration check.

**A3. Correct the baseline docs.** Mark P5 resolved (value references), remove
the stale `F1`/`TypeError` example from status.md §4d, and re-order §7 so the
multi-input verbs are next.

---

## 3. Decision B — multi-input combine verbs

The real feature gap (D1). Three verbs, and the design questions from
[status.md §4d](../status.md) are settled as follows.

### B1. A combine verb is its own operation, not a modifier (settles P1)

A combine verb reads more than one grid and decorates no tool, so it is **not a
modifier** — it is a standalone **operation constructor** that takes its input
grids positionally and its config as keywords.

**Recommended — a combine is an operation:**

```python
wf["j"] = join(wf["left"], wf["right"], on="k", how="inner")
wf["s"] = stack(wf["a"], wf["b"], wf["c"])
wf["z"] = zip(wf["a"], wf["b"])
```

**Not recommended — a combine as a modifier.** Expressible for consistency with
the bare-verb forms, but it reads wrong and is discouraged, because a binary grid
combine is not an iteration pattern decorating a tool:

```python
wf["j"] = op[mod.join(on="k", how="inner")](wf["left"], wf["right"])   # avoid
```

**Why a constructor, not a modifier.** `map`/`filter`/`select` *decorate* — they
say how one tool iterates one grid, so the `mod.` / decorator surface fits. A
combine has no tool to decorate and more than one grid to read, so it reads as a
*function of its grids* (`join(left, right, …)`), exactly like `pd.merge`. The
dividing line is arity: **single-input verbs stay modifiers; multi-input combines
are constructors.**

Under the hood it is still the one serializable `Operation` — the constructor is
sugar over the canonical data, not a new model:

- A combine stores an ordered **`Operation.inputs: tuple[StepRef, ...]`** (the
  grids, in order). `Operation.input` (singular) stays as `inputs[0]` for
  back-compat; single-input verbs have `inputs == (input,)`.
- Its verb is the `tool_id` — a **builtin, no user tool** (like `identity` /
  `gather`); its literal config lives in `arguments` (the verb's own parameters,
  `on` / `how`); and the modifier stack is empty:

  ```json
  {"tool_id": "join",
   "inputs": [{"$ref": "left"}, {"$ref": "right"}],
   "arguments": {"on": "k", "how": "inner"},
   "modifiers": []}
  ```

- `reads` becomes `[str(i) for i in inputs] + [value-ref args]` — ordering, the
  run guard, cycle detection and `_dependents` extend with no new rule.
- **References live only in `inputs`** (the grids) **and `arguments`** (value
  references) — never in modifiers (there are none here). The config (`on`,
  `how`) is literal. This is why the secondary grid is a first-class *input*, not
  a value-reference argument: value-ref args are shape-neutral by rule, and a
  combine partner is shape-bearing.

### B2. Combine verbs apply no tool (settles P2 — the ledger stays flat)

**Decision: `stack`, `zip`, `join` apply no tool**, exactly like `select`/`drop`.
They rearrange, they do not compute, so nothing fails per unit and the ledger
needs no two-origin unit. Computation stays a separate `map` over the result.
A `join` output row records *both* origins in the ledger's `unit` (a pair);
`stack`/`zip` keep a single origin.

### B3. Row rules and column rules

| verb | aligns on | columns out | `ROWS_RULE` | staging |
|---|---|---|---|---|
| `stack` / concat-rows | nothing — appends | union (declared `join="outer"\|"inner"`) | **sum** | known when inputs ran |
| `zip` | position / index | union | **same** (refuse unequal length — a problem) | known |
| `join` / merge | a key (`on=[…]`) | left ∪ right, keys merged | **unknown** (like `expand`) | columns known, count not |

- **Column collision (settles P3): pandas-style `suffixes=("_left","_right")`**
  by default, overridable; `stack`/`zip` require matching names or union with
  `NaN`. A later strict mode may require disjoint names.
- **Columns are predicted from both input schemas** when the inputs have run —
  same timing rule as the existing column check. Before that, the consuming
  step's column expectations are warnings (§4), not silent.

### B4. Order to build

`stack` → `zip` → `join`. `join` last, chosen against a real pipeline so `how=`
and the collision rule are decided by a case, not guessed.

### B5. Parked idea — a pure-structure `reshape` container (later)

The "one shape verb per step" rule exists so a unit that *fails* at an
intermediate shape still has a cell address. But the no-tool verbs
(`select` / `drop` / `slice` / `sort` / `distinct` / `rename`) **never** fail —
they apply no tool — so several of them could safely compose in a single
`reshape(...)` step without the addressable-unit problem. That would give
single-step block selection (the K9 literal-block case) cleanly. Scope would be
strict: a step may hold more than one shape verb **only if all of them apply no
tool**; anything that computes (`map`/`filter`/`expand`/`collapse`/`group`/
`sweep`/`widen`) still gets exactly one. Deferred — captured so it isn't
rediscovered.

---

## 4. Decision C — the warning / severity tier

Turn the model's silent optimism into visible, Excel-style expectations.

### C1. A severity ladder, not a binary

| tier | meaning | blocks `run()`? |
|---|---|---|
| 🟢 confirmed | upstream ran, column present | no |
| 🟡 expected | upstream staged, column **predicted present** | no |
| 🟠 likely-missing | upstream staged, column **predicted absent** | no |
| 🔴 `#REF!` | reference unresolvable, or upstream ran and column truly absent | yes |

### C2. `warnings` alongside `problems`

**Decision:** add `Step.warnings: tuple[str, ...]`, distinct from `problems`.
Problems are errors and block `run()`; warnings inform and do not. `Step.status`
gains the 🟡/🟠 states as a rollup. `check()` still never raises.

### C3. Column expectations at staging

The predicted column set already exists on a staged output. **Decision:** diff a
tool's required columns against the upstream's *predicted* columns and emit:
predicted-present-but-not-run → 🟡 "expects `city` from `narrow`, unconfirmed";
predicted-absent → 🟠 "expects `city`, but `narrow` is predicted to produce
`[n]`". Predicted-absent is a **warning, not an error** — honoring optimism; it
becomes 🔴 only once the upstream has run and the column is truly gone.

### C4. Unassign vs remove

**Decision:** clearing a *source's data* (the Excel "unassign") is allowed, keeps
the workflow, and lights dependents 🟠/🔴 "expecting data that isn't here".
Removing a *step* stays strict (refused while readers exist). This mirrors
Excel's own split between deleting a cell's value and deleting the cell.

---

## 5. Decision D — parallel typed status grids (cell-shaped status)

The target status representation, which subsumes the row ledger, the schema
status, and `#REF!` into one surface.

### D1. Struct-of-arrays, not dicts-in-cells

**Decision:** cell-level status is stored as **parallel typed grids the same
shape as the data** — a `status` grid, an `error` grid, … — not a dict per cell.
Struct-of-arrays keeps each attribute typed and vector-queryable
(`status_grid == "failed"`); a dict per cell would be opaque `object` cells, the
same nesting trap a frame-in-a-cell is. Stored **sparsely** (only cells that are
not plain `carried`/`ok`).

### D2. Cell states

`carried` · `computed-ok` · `failed` · `expected` · `likely-missing` · `#REF!` ·
`stale`.

### D3. It unifies the two axes

Run status lands per cell; a broken or missing column shows as **every cell in
that column flagged** — exactly how Excel fills a dependent column with `#REF!`.
So §4's column warnings and the run ledger become one structure.

### D4. Rollups preserve today's surface

`Step.status` and the current per-row `ledger` become **rollup views** over the
cell grid (back-compat kept). **Re-drive grain stays per-row** — a tool call
produces a row, so a row is the retry unit; per-cell status is honest finer only
for cell-wise verbs like `widen`, where today's ledger is lossy and this fixes
it. The `axis="columns"` `NotImplementedError` ("ledger indexed by column,
designed but unbuilt") is this.

---

## 6. Test strategy

**Extend the consolidated example, do not add new ones.** New verbs and status
behavior are covered by appending operations to
[`examples/all_orchestrations/pipeline.py`](../../examples/all_orchestrations/)
so one pipeline exercises the widest range: a `stack`/`zip`/`join` of existing
steps, a step whose column expectation is 🟡/🟠 before its upstream runs, a
cleared source producing `#REF!` dependents, and a `widen` whose per-field
status the cell grid now records. Unit tests in `tests/unit/test_grid.py` assert
the staging/run/serialization/rollup facts per verb; the example is the
integration surface.

---

## 7. Sequencing

1. **Baseline** — correct status.md (P5 done; log the bare-`select` gap) and land
   fix A2.
2. **Contract** — write invariants 1–5 and the B/C/D decisions into the model
   docs (object-model.md, step-expressions.md).
3. **Warning tier (C)** — cheap; the predicted columns already exist. Ships the
   🟡/🟠/🔴 ladder and column expectations on today's per-row ledger + a per-column
   schema status.
4. **Status grid (D)** — the larger build; folds the row ledger and schema status
   into the cell grid, with rollups for back-compat.
5. **Combine verbs (B)** — `stack` → `zip` → `join`, each extended into the
   example.
