# Status — the grid model

**As of 2026-09-30.** The consolidated view: where `grid.py` stands, what landed
recently, and every open issue with its size and what it is blocked on.

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

## 3. Open — small, and fits the existing design

Each is one `MODIFIERS` entry plus a `ROWS_RULE` and `DEFAULT_PAYLOAD` line.
Nothing here needs a decision first.

| issue | note |
|---|---|
| **`slice` / `head` / `limit`** | the sharpest gap of the three. **Row position is unreachable today** — a tool cannot see its index, even with `**row`, so positional selection is not expressible at all, only verbose. Workaround: `df.reset_index(names="row_no")` then `filter` |
| **`rename`** | matching a column to a differently-named parameter currently takes map-then-select: two plumbing steps. `widen` covers the records case but not renaming an existing column |
| **`sort`, `distinct`** | proposed, no blocker |
| **`cache`, `gate`, `concurrency`** | documented as part of the model in shape-algebra §1.1 and present in neither model |
| **Enforce the declaration contract** | [writing-tools.md §2.2](writing-tools.md) specifies four rules that currently fail *silently*: positional-only parameters (every row fails), `*args` (**the tool is called with no arguments and returns a plausible wrong answer**), non-identifier ids (`<lambda>`), mutable defaults (a step stops being re-runnable). All four are safe to enforce — verified that no tool in this repo or any builtin violates them. ~20 lines |
| **Duplicate tool ids** | silently overwrite. Recommended as a **warning**, not an error: re-declaration is legitimate in notebooks and in tests (this suite re-declares `again` five times), so a hard refusal would make the model painful where tools are actually written |

---

## 4. Open — needs a decision before it can be built

| issue | the decision |
|---|---|
| **Multi-upstream / `join`** | a step reads **exactly one** upstream; two `over`s are two shape verbs and are refused. The blocker is not plumbing but semantics: do two grids align on index, on a shared key, or as a cross product? And what becomes of the ledger's unit, and how does binding say which step a column came from? |
| **Source schemas** | nothing declares a `source` step's column types, so they are the only dtypes no annotation governs — and they propagate into every downstream step that carries columns forward. Worth doing for its own sake rather than as a serialization fix: it would validate a source whose **data is replaced**, which is a supported flow (`wf["raw"] = <different data>` after an import) that nothing currently checks |
| **Namespacing / `Workflow.adopt`** | composing two workflows forces a rename, which invalidates literal ids. Mechanical on the export — rename the ids, rewrite every `over` — and prototyped working in ~25 lines, but not in the library. **Mostly obviated** by the recommended pattern: a reusable pipeline is a Python function taking a ref and returning a ref, with the prefix as a parameter. That needs no library change and keeps provenance intact |
| **`colmap` / column-as-unit** | blocked on shape-algebra §5: a column-wise verb needs a ledger indexed by column, a different index *space* from the row-indexed grid. `axis="columns"` raises today rather than transposing and producing NaN |
| **`Output.ref`** | no payload store; payloads sit inline on each Step, so two steps reading one grid each hold it and storage cannot move to disk or Redis |

---

## 5. Accepted limits

Not bugs — consequences of decisions, recorded so they are not rediscovered as
surprises.

**Validation**

- **A string ref is unchecked.** `over="raw"` carries no workflow, so the
  provenance guard cannot see it. That is the same property that makes it a
  reusable template, so it cannot be both.
- **Modifier parameter names are not validated.** Unlike a bound literal, a typo
  in a verb's own parameter passes declaration and surfaces at run time:
  `mod.map(nmae="f")` → `TypeError: map_() got an unexpected keyword argument`.
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

**Staging**

- `collapse(by=…)` stages as `1 cell` regardless of how many groups the data has.
- `sweep` stages as `one cell per upstream row`, which is wrong wording for a verb
  with no upstream. Both are correct once run.

**Reserved names**

- `column` as a *grid column* hijacks the builtins' payload resolver.
- `sweep` reserves `name`, `retries` and `over`, so a swept parameter cannot use
  those names; the collision currently surfaces as `TypeError: unhashable type`.

**Other**

- `timeout` records intent only; real enforcement needs the async engine.
- `RangeIndex` returns from a session round trip as a plain `Index`. Values are
  identical so alignment is unaffected; only `DataFrame.equals` strict-fails.
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

## 7. If I were picking the next three

1. **Enforce the declaration contract** (§3). The `*args` case returns a wrong
   answer with no error, which is the worst failure mode in the system, and the
   fix is ~20 lines with zero breakage.
2. **`slice`** (§3). The only gap where something is *impossible* rather than
   verbose, and it fits the verb table exactly.
3. **Source schemas** (§4). The last place types are undeclared, and it closes
   the unchecked "replace the source's data" flow rather than just tidying.

`join` is the largest open question but should wait for a concrete pipeline that
needs it, so the alignment semantics are chosen against a real case rather than
guessed.
