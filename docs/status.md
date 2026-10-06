# Status — the grid model

**As of 2026-10-05.** The consolidated view: where `grid.py` stands, what landed
recently, and every open issue with its size and what it is blocked on.

**If you only read one section: §3 is what to fix, §7 is the order.**

This is the roll-up. Two other places track gaps at a different scope and are not
duplicated here — [grid-model.md §7](grid-model.md) for `grid.py`'s internals,
[api-reference.md](api-reference.md) *Not yet in this surface* for the public
names. When they disagree with this file, this one is newer.

Tests: **370 passing** (176 of them `tests/unit/test_grid.py`), up from 326.

---

## 1. Where it stands

`grid.py` is a working prototype of [shape-algebra.md](shape-algebra.md),
**standalone**: it imports nothing from the engine and nothing imports it. Both
models therefore define `Workflow`, `Operation` and `Step`, which is why the
convention is to import the module (`from simple_steps_core import grid`).

What works end to end: declaring steps, staging them before they run, ten shape
verbs, two execution modifiers, per-unit ledgers, declaration-time validation,
verb inference, and both export modes.

---

## 2. What landed recently

| | what | where |
|---|---|---|
| **Canonical grammar** | the input goes in the call position — `score[mod.map(name="pts")](wf["raw"])` — with `over=` documented as the same step stored the other way round | [defining-operations.md](defining-operations.md) |
| **Declaration contract** | the requirements a tool must meet, tiered into enforced / worth enforcing / unenforceable-but-load-bearing | [writing-tools.md §2](writing-tools.md) |
| **Strict typing** | `grid.STRICT_TYPES` / `@tool(strict=True)` require a full annotation; `check` compares annotations to bound literals and to the upstream's real dtypes; `catalog()` publishes `type`, `returns`, `typed` | `grid.py`, [§10](defining-operations.md) |
| **Reference provenance** | a `StepRef` stays a ref in `Modifier.params` (flattened only in `to_dict`), so `check` refuses one borrowed from another `Workflow` instead of silently resolving it against a same-named local step | `grid.py`, [§11](defining-operations.md) |
| **`widen` verb** | `expand`'s column-axis twin (`unnest_wider` to its `unnest_longer`): a record's fields become columns. Requires `columns=` so staging stays exact — unknown columns would make every downstream step unvalidatable until it ran. Applies no tool but keeps a per-unit ledger, so a non-mapping cell or a missing field is an inspectable failure | `grid.py`, [§3](defining-operations.md), [§12.5](defining-operations.md) |
| **`expand` guard** | a returned `DataFrame` is refused per unit instead of being iterated into its *column names* — a silent wrong answer | `grid.py` `expand_` |
| **Empty results** | a verb producing zero rows now reports `completed`, not `staged`, and keeps its columns **and their dtypes**. `expand` to `[]` used to yield a column-less frame, so a downstream step reported "it has no columns" rather than "it is empty" — and `filter` already disagreed with it | `grid.py` `expand_`, `Step.status` |
| **Raw-value conventions** | what a returned value becomes per verb, what `rows()` makes of an assigned value, and the index/column rule for all nine verbs — all verified against the implementation | [§12](defining-operations.md) |
| **Dtype fidelity** | frame payloads record their dtypes; JSON cannot express them, so a float column of whole numbers used to reload as `int64` — which could flip a type check's verdict | `grid.py` `_encode`/`_decode` |

A regression from the provenance change was also caught and fixed: with a
`StepRef` living in `params`, reprs and problem messages had started printing
`over=<raw>` instead of `over='raw'`. `Modifier.__repr__` now flattens for the
same reason `__eq__` does — how a step was named is not part of what the modifier
says. Two tests pin it.

Three stale claims were corrected while doing this: *one shape verb per step is
undecided* (it is enforced), *column types are not checked* (they are, for
annotated tools), and `grid.__all__` was missing `STRICT_TYPES` and
`annotation_problems`.

---

## 3. Fixed — F1–F9, all nine

Every one reproduced first, then fixed, then pinned by a test.

| # | was | now |
|---|---|---|
| F1 | `bind(x=wf["step"])` stored the id **string** and yielded `[None, None, None]` | `TypeError` at the line that wrote it, naming `over=` as where a reference belongs |
| F2 | the declaration contract was unenforced | `@tool` refuses positional-only parameters, `*args`, non-identifier ids and mutable defaults, reporting every problem at once. `declaration_problems(fn, id)` is the same check, callable |
| F3 | a duplicate tool id overwrote in silence | `UserWarning`; re-registering the **same** function stays silent, so a notebook re-run says nothing |
| F4 | a modifier's own parameter names were unchecked | `map takes no parameter 'nmae'; it accepts axis, name, over, retries`. Derived from each verb's signature, so it cannot drift; `sweep` still accepts anything, because its parameters are the data |
| F5 | a swept parameter called `name` crashed inside pandas with `unhashable type: 'list'` | `sweep's name= must be str, got list. A swept parameter cannot be called 'name' — it collides with the verb's own`. Generalised into `PARAM_TYPES`, so every modifier parameter is type-checked at declaration |
| F6 | `collapse(by=)` staged as `1 cell` regardless of group count | `one cell per group, from 3 rows` — a new `per_group` rows rule |
| F7 | `sweep` staged as `one cell per upstream row` | `6 cells` — the count is computed from its own parameter lists, so its addresses are known before it runs |
| F8 | a `RangeIndex` reloaded as a plain `Index` | recorded alongside the dtypes; a labelled index is still left alone |
| F9 | `score[mod.map()](ref, weight=2)` was a `TypeError` | works, and equals `score.bind(weight=2)[mod.map()](ref)`. `source` is positional-only so a tool may still have a parameter called `source` |

One more found while doing it: a bare `mod.sweep(...)` was refused with *"it is
an execution modifier"*, which it is not. The message now distinguishes a shape
verb with no default tool from an execution modifier from a non-modifier.

---

## 4. Built — four new verbs, plus positional step access

| # | what | notes |
|---|---|---|
| B1 | **`slice`** | rows by position — `mod.slice(stop=2)`, `mod.slice(start=1, stop=3)`, `mod.slice(at=[0, 3])`. The one selection no tool can make, since a tool never sees its row index. `at=` and `start`/`stop` are exclusive. Applies no tool; `at_most` rows |
| B2 | **`wf[0]` / `wf[-1]`** | positional step access. **Resolves to the id immediately** — positions shift when a step is inserted, so a stored position would silently rewire the graph. `int` is a position, `str` a name, so a step called `"0"` stays reachable |
| B3 | **`rename`** | `mod.rename(columns={"n": "count"})`. Strict about an absent name, and **refuses to overwrite** an existing column rather than losing it |
| B4 | **`sort` / `distinct`** | `sort` takes one column or several and `ascending=`; **the index travels with its row**, so cells keep their addresses. `distinct` keeps the first of each group and its index |

Not built — **B5 `cache`, `gate`, `concurrency`**. These are documented in
shape-algebra §1.1 but none is implementable yet: `cache` needs a payload store
(§4c D5) and nothing is cached today, while `gate` and `concurrency` need the
async engine that `timeout` is also still waiting on. Adding them now would mean
three more placeholders like `timeout`, which is dead API rather than progress.

The vocabulary is now **14 shape verbs**, 2 execution modifiers, and
`grid.__all__` exports 59 names. Suite: **408 passing**, up from 326.

---

## 4b. Decided this round — no longer open

Recorded so they stop being re-litigated.

| decision | the reasoning |
|---|---|
| **Selection is an operation, not a reference.** A reference stays a bare step id; `select` / `drop` / `filter` / `widen` do the projecting | Binding already hands a tool only the columns it declares, so "reference a column as an argument" is not a real need — `select`'s job is narrowing what flows *downstream*. One mechanism, each selection visible in the graph with a cell address and a ledger, and no grammar means no parser and no resolvers to keep in agreement |
| **No selector subscripts on a reference** (`step1.cols[…]`, `step1[["a","b"]]`, `step1[0:5]`) | A prototype worked and validated cleanly, but it is a second way to project the same data — and the thing it was really solving was multi-input (D1), which it would smuggle in through subscripts rather than address |
| **Positional row sets are the brittle option** | `.rows[[0,2,4]]` style selection breaks the moment upstream data changes. `filter` with a predicate is the robust form and carries a ledger saying which rows it kept |
| **A scattered set of cells is not representable** | it has no rectangular shape, so it is neither a frame, a column, nor a scalar, and nothing downstream could bind to it. Pass several `cell` values as separate arguments instead |

---

## 4c. Needs a decision before it can be built

| # | issue | the decision |
|---|---|---|
| D1 | **Multi-input** | **The real gap, and the one the reference-grammar idea was masking.** A step reads exactly one upstream. Spelled out in §4d below |
| D2 | **Source schemas** | nothing declares a `source` step's column types, so they are the only dtypes no annotation governs — and they propagate into every step that carries columns forward. Worth doing for its own sake: it would validate a source whose **data is replaced**, a supported flow (`wf["raw"] = <different data>` after an import) that nothing currently checks |
| D3 | **Namespacing / `Workflow.adopt`** | composing two workflows forces a rename. Mechanical on the export and prototyped in ~25 lines, but **mostly obviated** by the recommended pattern: a reusable pipeline is a Python function taking a ref and returning a ref, with the prefix a parameter. No library change, provenance intact |
| D4 | **`colmap` / column-as-unit** | blocked on shape-algebra §5: a column-wise verb needs a ledger indexed by column, a different index *space*. `axis="columns"` raises today rather than transposing and producing NaN |
| D5 | **`Output.ref`** | no payload store; payloads sit inline on each Step, so two steps reading one grid each hold it and storage cannot move to disk or Redis |

---

## 4d. Multi-input — the exact problems, and the operations they imply

> **Update (2026-10):** the *single-value* half of D1 is **solved** — a bound
> argument may now be a `StepRef`, resolved at run (value references, K10), so
> `bind(threshold=wf["cutoff"])` works. P5 below is therefore settled. What
> remains is true **multi-grid** combine (`stack`/`zip`/`join`), now specified in
> [core-proposals/005](core-proposals/005-reshaping-merging-and-status-grids.md).

D1 in one sentence: **a step reads exactly one upstream.** The single-value case
(*"use one value from another step"*) is handled by value references; the
remaining wall is combining two whole **grids**:

```python
wf["j"] = over_threshold[mod.map(over=wf["a"]), mod.map(over=wf["b"])]
# "2 shape verbs in one step (map, map); at most one is allowed"

over_threshold.bind(threshold=wf["cutoff"])   # now OK — a value reference (K10)
```

Before choosing a syntax, these are the five things that actually have to be
decided. They are what makes this bigger than adding a verb.

### P1 — Where does a second input live?

`_input_for` walks the modifiers, returns the first `over` it finds, and stops.
One step therefore has one input by construction, and check rule 5 enforces one
shape verb per step — so there is nowhere to put a second reference today.

A merge verb needs either two named parameters (`left=`, `right=`) or a list
(`over=[a, b]`). The second reads better but makes `over` polymorphic, which
every resolver and the cycle check would have to follow.

### P2 — What is a unit, once there are two inputs?

The ledger has one row per unit, and today a unit is an input row. With two
inputs of different lengths that breaks down:

- for a **join**, is a unit one output row, or one left row?
- a unit that fails — which input do you re-drive, and from which position?
- `expand` already solved a version of this by recording the originating row in
  the ledger's `unit` column. A merge needs the same idea, but with **two**
  origins per output row.

This is the one that decides whether the ledger stays a flat table.

### P3 — Which input does a column come from?

Binding is by name, and the rule is "a column wins a bound literal." With two
inputs, if both have a `score` column, nothing says which one a tool's `score`
parameter means. Options: require disjoint column names, prefix them
(`left.score`), or make the merge verb rename on collision like pandas'
`suffixes=`. Each changes what downstream tools must declare.

### P4 — Alignment: three operations, not one

This is the part that cannot be papered over — **these are different operations
with different row rules, and no single verb covers them.**

| operation | aligns on | rows out | `ROWS_RULE` |
|---|---|---|---|
| **`join`** / `merge` | a shared key (`on=`) | depends on cardinality: 1:1, 1:many, many:many | `unknown` — like `expand`, not knowable without the data |
| **`stack`** / `concat` | nothing — appends rows | the **sum** of both | `sum`, knowable at declaration |
| **`zip`** | position / index, row *i* with row *i* | the same as either side; requires equal length | `same`, knowable |
| **`broadcast`** | one side is a single row or scalar | the **larger** side | `same` as the big side |

Each is the right answer to a different question, so the realistic outcome is
**three verbs, not one** — plus a decision on whether `broadcast` is a verb at
all or belongs with `bind` (see P5).

`join` is the only one whose row count is unknowable in advance, which puts it
in `expand`'s category for staging: it can promise a shape but not a count.

### P5 — Is a scalar from another step really a merge?  **— settled (K10)**

The commonest real case is not a join at all: *"use this one value as a constant
for every row."* **This is now built:** a bound argument may be a `StepRef`,
resolved at run (one-cell → the cell, else the whole grid), and it lands in
`reads` so it is ordered and guarded like any input. `broadcast` needs no verb,
and this removed most of the demand for a general `join` — leaving only true
multi-grid combine, specified in
[core-proposals/005](core-proposals/005-reshaping-merging-and-status-grids.md).

### Suggested operations, if these are settled

| verb | signature sketch | rows | tool |
|---|---|---|---|
| `stack` | `mod.stack(over=[a, b])` | sum | none — pure structure |
| `zip` | `mod.zip(over=[a, b])` | same (refuse unequal) | none |
| `join` | `mod.join(left=a, right=b, on="k", how="inner")` | unknown | none |
| *broadcast* | probably not a verb — see P5 | — | — |

All three would apply **no tool**, like `select` and `drop`: they rearrange
without computing, so nothing can fail per unit. That keeps them inside the
existing design rather than requiring a new kind of ledger — which is the
strongest argument for doing merge as its own step, and leaving `map` to compute
over the result.

**Recommended order:** settle P5 first (cheapest, most common), then `stack` and
`zip` (both have knowable row rules and need no key semantics), and leave `join`
last, chosen against a real pipeline so `how=` and the collision rule are
decided by a case rather than guessed.

---

## 5. Accepted limits

Not bugs — consequences of decisions, recorded so they are not rediscovered as
surprises. Anything listed in §3 is a defect to fix and is **not** here.

**Validation**

- **A string ref is unchecked.** `over="raw"` carries no workflow, so the
  provenance guard cannot see it. That is the same property that makes it a
  reusable template, so it cannot be both.
- **The column and dtype checks need the upstream to have run.** A staged Output
  holds placeholder rows, so checking one would invent errors. Declaring a whole
  workflow before running therefore catches less than declaring incrementally.
- **Type checking reports only *certain* mismatches.** `object`, unions,
  protocols and all-null columns are undecidable and pass; `int` into `float` is
  widening, not an error; a `collapse` accumulator is never checked. A reported
  mismatch is real, but silence is not proof every value fits.
- **`**kwargs` opts out** of both the column check and the type check.
- **A failing `filter` yields an empty grid, not an error.** A row whose
  predicate raised is not kept, so a wholly broken filter looks merely selective.
  `status` and the ledger are where it shows.

**Reserved names**

- `column` as a *grid column* hijacks the builtins' payload resolver. A tool
  *parameter* called `column` is fine; only the grid column is reserved.
- `sweep` reserves `name`, `retries` and `over`, so a swept parameter cannot use
  those names. (The cryptic error it currently gives is F5.)

**Other**

- `timeout` records intent only; real enforcement needs the async engine.
- No fingerprints and no `stale`: nothing is cached and nothing recomputes on its
  own.

---

## 6. The strategic one

**Two parallel models.** This is the item that should not outlive the migration.
`grid.py` implements the target design standalone while the engine still has
`orchestration-map` as a *tool* that takes your function as a string argument —
the inversion the grid model exists to fix. The refactor that lands it also
deletes `ORCHESTRATORS`, `orchestrator_id`, `Tool.is_orchestrator` and the
engine's higher-order branches. Sequence in shape-algebra §10; the load-bearing
first step is making `ToolCall` recursive, because nothing else can land before
it.

Secondary: `grid.__all__` exports 51 names flat, about a quarter of them verb
implementations a user never calls. Tiering the surface is cheap and would make
it teach itself.

---

## 7. What is left

Everything in §3 and §4 is done. What remains, in the order I would take it —
now specified in [core-proposals/005](core-proposals/005-reshaping-merging-and-status-grids.md)
and [006](core-proposals/006-tool-contracts-and-resources.md):

1. **Baseline fixes** — ✅ P5 settled (value references); ✅ a required verb
   setting (`select`/`drop`/`sort`/`rename`) is now caught at declaration, not at
   run (005 A2).
2. **The warning/severity tier** (005 C) — turn the silent column-expectation
   optimism into 🟡/🟠/🔴 warnings; cheap, the predicted columns already exist.
3. **The cell-shaped status grid** (005 D) — parallel typed status grids; the
   per-row ledger and `Step.status` become rollups over it.
4. **`stack` / `zip` / `join`** (005 B) — combine verbs as operation
   constructors; `join` last, chosen against a real pipeline.
5. **D2 source schemas** — the last place types are undeclared.
6. **Resources** (006) — port the engine's Resource system onto the grid.
7. **D5 `Output.ref`** — a payload store; also what `cache` (B5) is waiting on.
8. **The strategic one** (§6) — the engine still has not moved onto this model.

`colmap` (D4) stays blocked on shape-algebra §5, and B5's three execution
modifiers stay blocked on the async engine.

---

## 8. Tests

`tests/unit/test_grid.py` — **408 passing**, up from 326 at the start of this
round. Every defect in §3 has a test that fails without its fix, and every verb
in §4 is covered for its happy path, its refusals, its staged prediction, and a
session round trip.
