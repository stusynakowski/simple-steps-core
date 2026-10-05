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

## 3. Fix now — verified defects

Each was reproduced by running it. None needs a design decision; the first two
are the ones that return **wrong answers with no error**, which is the worst
failure mode the system has.

| # | defect | symptom | size |
|---|---|---|---|
| F1 | **`bind()` dereferences a `StepRef`** | `over_threshold.bind(threshold=wf["cutoff"])` stores the id **string** `'cutoff'`, reports no problem, and yields `[None, None, None]` at run time. A bind literal is a constant and can never be a step reference, so the deref is wrong in every case — it should raise where it is written | ~3 lines |
| F2 | **The declaration contract is unenforced** | [writing-tools.md §2.2](writing-tools.md) specifies four rules that fail silently today: positional-only parameters (every row fails, `problems` empty), **`*args` (the tool is called with no arguments and returns a plausible number)**, non-identifier ids (`<lambda>`), mutable defaults (a step stops being re-runnable). Verified that no tool in this repo and no builtin violates any of them | ~20 lines, zero breakage |
| F3 | **Duplicate tool ids overwrite silently** | the second `@tool def dup` replaces the first with no complaint. Recommended as a **warning**, not an error — re-declaration is legitimate in notebooks and in tests (this suite re-declares `again` five times) | ~5 lines |
| F4 | **Modifier parameter names are unvalidated** | unlike a bound literal, a typo in a verb's own parameter passes declaration and surfaces at run time: `mod.map(nmae="f")` → `TypeError: map_() got an unexpected keyword argument` | small |
| F5 | **`sweep` reserved-name collision is cryptic** | a swept parameter called `name`, `retries` or `over` collides with the verb's own, surfacing as `TypeError: unhashable type: 'list'` | small |
| F6 | **`collapse(by=)` stages as `1 cell`** | regardless of how many groups the data has, because `ROWS_RULE` is per-verb and cannot see the data. Correct once run | small |
| F7 | **`sweep` describes itself wrongly when staged** | reports `one cell per upstream row`, which is wrong wording for a verb with no upstream; its count is knowable from its own parameter lists. Correct once run | small |
| F8 | **`RangeIndex` reloads as a plain `Index`** | values are identical so alignment is unaffected; only `DataFrame.equals` strict-fails | small |
| F9 | **The two `__call__`s disagree about literals** | `score(ref, weight=2.0)` works — kwargs in the call position are routed to `bind`. `score[mod.map()](ref, weight=2.0)` is a `TypeError`, because `ToolHandle.__call__` takes `**kwargs` and `Operation.__call__` takes only `source`. No principle behind it, so the two forms should be equivalent. Note the signature must be `(self, source, /, **literals)` — without the `/`, a tool with a parameter genuinely named `source` raises *multiple values for argument* | ~5 lines |

---

## 4. Build next — missing capability, no decision needed

| # | what | why it is needed |
|---|---|---|
| B1 | **`slice` verb** | the sharpest gap in the vocabulary. **Row position is unreachable today** — a tool cannot see its index, even with `**row`, so positional row selection is not expressible *at all*, not merely verbose. Workaround is `df.reset_index(names="row_no")` then `filter`. One `MODIFIERS` entry plus a `ROWS_RULE` line |
| B2 | **`wf[0]` positional step access** | `wf[0]` / `wf[-1]` as sugar for a step id. Prototyped. The one condition: it must **resolve to the id immediately**, because positions shift when a step is inserted — storing a position would silently rewire the graph. `int` → position, `str` → name, so a step named `"0"` stays reachable |
| B3 | **`rename` verb** | matching a column to a differently-named parameter takes map-then-select: two plumbing steps. `widen` covers the records case but not renaming an existing column |
| B4 | **`sort`, `distinct`** | proposed, no blocker |
| B5 | **`cache`, `gate`, `concurrency`** | documented as part of the model in shape-algebra §1.1 and present in neither model |

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
| D1 | **Multi-input** | **The real gap, and the one the reference-grammar idea was masking.** A step reads exactly one upstream: two `over`s are refused, and there is no way to use a value from another step (F1 is what happens when you try). Three options, each with different semantics: align on index, align on a shared key (a `join`), or broadcast a scalar. Also unsettled: what the ledger's unit becomes, and how binding says which step a column came from |
| D2 | **Source schemas** | nothing declares a `source` step's column types, so they are the only dtypes no annotation governs — and they propagate into every step that carries columns forward. Worth doing for its own sake: it would validate a source whose **data is replaced**, a supported flow (`wf["raw"] = <different data>` after an import) that nothing currently checks |
| D3 | **Namespacing / `Workflow.adopt`** | composing two workflows forces a rename. Mechanical on the export and prototyped in ~25 lines, but **mostly obviated** by the recommended pattern: a reusable pipeline is a Python function taking a ref and returning a ref, with the prefix a parameter. No library change, provenance intact |
| D4 | **`colmap` / column-as-unit** | blocked on shape-algebra §5: a column-wise verb needs a ledger indexed by column, a different index *space*. `axis="columns"` raises today rather than transposing and producing NaN |
| D5 | **`Output.ref`** | no payload store; payloads sit inline on each Step, so two steps reading one grid each hold it and storage cannot move to disk or Redis |

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

## 7. The order I would do them in

**First — the two silent-wrong-answer bugs.** Both are small and neither needs a
decision.

1. **F1** — `bind()` refusing a `StepRef`. Three lines, and it converts a
   `[None, None, None]` result into an error at the line that caused it.
2. **F2** — enforce the declaration contract. ~20 lines, verified zero breakage,
   and `*args` is the worst failure mode in the system.

**Then — the one thing that is impossible rather than awkward.**

3. **B1** — `slice`. Positional rows cannot be expressed at all today, and it
   fits the verb table exactly.

**Then, cheap and obvious.**

4. **F9** — make the two `__call__`s agree about literals. Five lines, and it
   removes the main reason `bind` feels like ceremony: the form most people
   reach for first (`score[mod.map()](ref, weight=2.0)`) starts working.
5. **B2** — `wf[0]`, prototyped and verified.
6. **F3–F8** — the remaining small defects, in any order.

**And the one real design question.**

7. **D1 — multi-input.** Everything else on this list is additive; this one
   changes what a step *is*. It is also what the app's formula bar needs:
   a formula like `=score(url=step1["url"], n=step2["k"][0])` references two
   steps in one expression, which the grid model cannot express at all. That
   incompatibility — not subscript syntax — is the thing to settle before the
   app targets the grid model.

I would pick D1's semantics against a concrete pipeline that needs it rather
than choose in the abstract.
