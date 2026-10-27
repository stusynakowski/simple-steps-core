<!-- from docs/core-proposals/008-core-changes.md -->

## Priority 4 — later

### K11. Refuse `over=[a, b]` clearly

**Today:** adding the step raises `TypeError: __str__ returned non-string
(type list)` (`Operation._add` wraps any `over` in `StepRef`). Combining steps
already works through `join`/`stack`/`zip_`; the app's compiler never
produces this form.

**Ask:** in `_add`, accept only a `StepRef` or a string; otherwise raise *"one
step reads one input; to combine steps use join, stack or zip_"*.

### K17. Keep JSON v1 loadable across P0

**Today:** `to_json` writes `version: 1`. C1 and C2 change the JSON too.

**Ask:** when the operation JSON changes, bump `version` and keep loading
version 1 for at least one release.

### K18. Enforce `timeout`

**Today:** 4 units × 0.3 s with `timeout=0.05` take 1.2 s and all complete.

**Ask:** fail a unit that runs past its timeout, with a timeout error in the
ledger. Needs core's async engine (B5).

### K19. A column argument pairs per row, by type

**Decided by the owner (2026-10-25):** modifiers make a tool run per cell, so a
column passed as an argument should be paired row by row. The orchestration is
inferred from type matching, not written by the user.

**Today** (run on the current pin, `make` = `n: [3, 1, 2]`, `w: [10, 20, 30]`):

- `scale(n, weight=1)` untyped, `weight=wf["r"][cols["w"]]`, under `mod.map()`:
  every row gets the whole list → `[[10, 20, 30]×3, [10, 20, 30], [10, 20, 30]×2]`.
- `scale(n: int, weight: int = 1) -> int`, same call, under `mod.map()` or
  `mod.auto()`: problem *"weight: int, but 'r' is a column; to pair its rows with
  the input's, join first"*, output `[None]`.
- The working route today: `wf["z"] = zip_(wf["r"], wf["w"])`, then
  `scale[mod.map()](wf["z"])` → `[30, 20, 60]`.

**Ask:** in a row-wise verb (`map`, `filter`, `expand`, `auto` resolving to one
of them), decide a column argument by the parameter's type:

| Parameter type | Column argument |
|---|---|
| scalar (`int`, `str`, …) or untyped | one value per row, row *i* with row *i* |
| `list`, `Series`, `DataFrame` | the whole column, as today |

A row-count mismatch is a problem on the step, naming both counts. Under a
whole-grid verb (`table`, `collapse`) the column stays whole.

**Row id (decided by the owner, 2026-10-25):** pairing by position breaks when
an earlier step re-sorts or filters one side but not the other, and cell
selections (C1) have the same problem: after a sort, `wf["srt"][0]` picked a
different row. Both use the **row id** instead, and the row id is the frame's
index: the default index unless a tool sets its own. So:

- a column argument pairs with the input's rows by index, not by position;
- a selection such as `wf["r"][0]` or `wf["r"][0:2]` picks rows by index label,
  so it follows the row through a sort;
- verbs that keep rows (`map`, `filter`, `sort`) keep each row's index;
- an index label missing on the other side is a problem on that row, not a
  silent `NaN`.

Still to settle in core: what id the new rows get from verbs that make rows
(`expand`, `stack`, `join`, a source).

The owner is making this core update.

**Not yet confirmed as a core change.** This is the requirement; the edit to core
is confirmed separately before it lands.

### K20. Kernel and run identifiers, by hashing specs

**Decided by the owner (2026-10-26):** users should be able to tell they are
running exactly the same workflow, and whether a tool changed under the data.

**Today** (run on the current pin): core hashes a step's **output data**
(`wf.version("f")` → `'1ea84a71beb3'`, SHA-1 of row ids, columns and values),
the versions a step **read** (`read: {'p': 'f3868e7634d7'}`) and a
**resource's** type and settings. It stores the formula a step ran with as
text. Tool code and the kernel as a whole are not hashed.

A tool's source hashes cheaply: `inspect.getsource(handle.fn)` → SHA-256 took
0.11 ms, and works on library functions too (`pandas.read_csv`).

**Ask:**

```
tool hash     = sha256(name, source of handle.fn, library name + version)
resource hash = sha256(type, settings without secret ones)
step hash     = sha256(name, operation spec, hashes of its tools,
                       hashes of the steps and resources it reads)
kernel id     = sha256(step hashes in order, catalog hash)
run id        = kernel id + the data versions of the source steps
```

- **Step names count** (owner): a name is part of the spec, so a rename changes
  the hash.
- **Tool hashes are computed once**, when the catalog is built, not per run.
  The source hash changes on any edit, comments included; that's acceptable.
  It doesn't see changes inside packages a tool imports; the library version
  is the line.
- **A changed tool marks its steps stale**: put the tool hash in `ran_with`,
  so "the tool changed under this data" shows the same way a changed formula
  does.
- **Secrets:** resources need secret settings for now (API keys). A resource
  type marks which settings are secret, and they're left out of the hash.
  Today's resource hash includes every setting.
- **Tools that aren't deterministic** (an LLM call, random sampling): the same
  id can't promise the same output. For now, recommend developers give such
  tools a `seed` literal parameter, so the seed is part of the spec and the
  hash. Nothing more is enforced yet.
- **Canonical form:** JSON with sorted keys, never `repr`. Full SHA-256 stored,
  shown short (`ss:4be0c19a…`).
- **Terminal:** `k.id`, `k.run_id`, `k.step("f").id`, and `k.diff(other)`
  giving the first step whose hash differs and why (formula, tool code, input).

### K21. Room in each spec for the app's additions

**Decided by the owner (2026-10-26):** this repo augments core's specs (a
tool's, a resource's, a step's) with its own information, and developers will
want custom UI components for their tools, such as a date picker for one
argument.

**Ask:** each spec carries an open `extras` mapping, keyed by namespace
(`"simple_steps.ui"`), that core stores, saves and loads but never reads.

- **Not part of the hash.** A changed input widget doesn't change what a step
  computes.
- **Declared with the tool:** `@tool(extras={"simple_steps.ui": {"date": "date-picker"}})`,
  or added to a catalog entry. The app maps names to components; core never
  knows about UI.

### K22. Keep earlier outputs while something still reads them

**Decided by the owner (2026-10-26):** when a step re-runs, its new output
becomes current, but a later step that read the old output and hasn't re-run
keeps showing what it was computed from.

**Today:** core keeps only each step's latest output. This repo's
`DATA_STORE` keeps every run's output, per session, keyed by a ref id, and
never frees any (the leak in [how-simple-steps-works.md §5 item 6](../how-simple-steps-works.md)).

**Ask:** store outputs by their data version, which core already computes.

- An output is immutable once written; equal data is stored once.
- A step points at the version it produced; a reader records the version it
  read (core's `read` stamps already do).
- A reader that hasn't re-run is `stale` and still shows the version it read.
- A version no step points at or reads is freed. That ends the leak.
- Where versions are kept (memory now, disk or a database later) is the
  pluggable store of C32.

### K23. Progress and cancellation as modifiers

**Decided by the owner (2026-10-26):** progress is defined with modifiers, and
can be defined for any cell output.

**Ask:** execution modifiers (beside `retry` and `breaker`) that report each
cell as it moves through its states (pending → running → known / failed), to
a callback the host passes in, plus `cancel()` on a running step. The host
(terminal or app) decides how to show it; core only reports.

### K24. No state shared between workflows

**Decided by the owner (2026-10-26):** users and workflows must never share
anything that could mix them up, across users and across live kernels. Core
assumes one workflow per interactive session; this repo isolates sessions.

**Today:** `grid.TOOLS` is one process-wide dict, so a tool defined for one
workflow is usable by all of them in the process.

**Ask:** no mutable state at module level in core. Everything a workflow uses
(catalog, resources, outputs, caches) hangs off its kernel, so two kernels in
one Python process can't see each other.

### K25. Resource defaults are literals

**Decided by the owner (2026-10-26):** a resource's settings for a context are
hardcoded defaults, always literals. Two kernels connected to exactly the same
database should behave the same.

**Open:** a tool that queries a resource (a database in a `map`) reads data
that isn't a step, so its data version isn't in the run id (K20). The same run
id can then give different results if the database changed. Possible answer:
a resource may report a version (a snapshot id, a last-modified time) that goes
into the run id.

**Decided (owner, 2026-10-26):** do that. A resource type may report a data
version; it goes into the run id (K20) and into the `read` stamps of the steps
that use it, so a changed database marks them stale like a changed input step.

### K26. Size estimates, and output in pages

**Decided by the owner (2026-10-26):** memory limits are Python's own for now.
The UI shows 50–100 rows at a time and loads the next page at the bottom. The
user must still see the scale of the data. UI limits go on the *estimated
size* of the data being processed; scaled solutions are a later layer.

**Ask:** every output reports its row count and estimated size in bytes, in
`meta`, before and after it runs (staged steps estimate). `wf.preview(step,
rows=(start, stop))` already pages; keep it the one way to read a page.

**Unknown is an answer (owner, 2026-10-26).** For reshaping and dynamic
operations (`expand`, `filter`, `join`, `group`) the size often can't be known
before running. Report that as `unknown` with the reason, so the user sees it,
rather than leaving it blank. Core already has the wording in its plan:
*"expand: how many items … returns per row is only known by running"*.

### K27. Return types: unknown until it runs, then what it returned

**Decided by the owner (2026-10-26):** `Annotated` parameters are fine for
extras (K21). When a tool's return type isn't declared, its type is
**unknown**. Once it has run without error, the type observed is used when
staging later steps; if rows returned different types, the union of them.

**Ask:** `meta["type"]` per output column: declared, else `unknown`, else after
a run the observed type or union. Check first, by running, that core's type
checks look through `Annotated`.

### K28. Cell-to-cell lineage stored in each output

**Decided by the owner (2026-10-26):** each step's output metadata includes
the exact cells that led to each of its cells: which cell maps to which.

**Today** (run on the current pin): `wf.cell(step, row, column)` works this
out on request: `wf.cell("e", 1, "value")` → id `'0.1'`, inputs
`[{'step': 'p', 'id': 0, 'columns': ['n'], 'argument': 'n', ...}]`. Rows made
by `expand` already get child ids (`0.0`, `0.1`, `1.0`, `1.1`) that point at
their parent. The lineage isn't stored with the output.

**Ask:**

- every output stores, per cell, the input cells (step, row id, column) and the
  argument each fed;
- a row from `expand` maps to the same source row as its siblings (as the
  child ids already do);
- when a step re-runs with changed arguments, the cells that are new or
  changed are marked, and the steps downstream show which of their cells came
  from them.

- a tool can return several outputs for one row (a dict or tuple), spread
  into several cells (columns, as `widen` does). Each of those cells maps to
  the same input cells (owner, 2026-10-26).

This is also what K19's row ids and K22's kept versions are built on.

### K29. Renames: references follow, and reading old data warns

**Today** (run on the current pin): `wf.rename("p", "q")` rewrites later
references: `d`'s formula becomes `dbl[mod.map()](wf["q"])` and `d` stays
`completed`.

**Decided by the owner (2026-10-26):** a step that reads data older than its
reference's current output warns the user that it is reading old data (a
stale reference), with the step it read and the version.

### R7. A standard handle for media

**Today:** saving an output that holds an image is refused, clearly.

**Ask:** port the engine's `MediaAsset` / `MediaStore` as the grid's handle,
saved as a content-hashed reference.

### R8. Failed rows turn integer columns into floats

**Today:** `risky` over `n = [1, 2, 3, 2]` gives `out: float64`
(`100.0, NaN, 300.0, NaN`).

**Ask:** use nullable `Int64` (or `object`) for a payload column with failures.

### R9. Stages

**Ask:** a named group of consecutive steps that runs as one, with
`run_stage(name)` and a section in R5's format.

---

## How each ask is verified

Every ask's **Done when** is written as a check that can be run against core.

- **`scripts/core_asks.py`** runs one probe per K-item today. Each C-item's
  "Done when" should become a probe there, so `python scripts/core_asks.py`
  reports the whole list as OPEN/DONE.
- **Core's own tests** should carry the same checks, so a fix can't regress
  after the app adopts it.
- **End-to-end examples** (`examples/all_orchestrations`, and the planned
  example repos) run real formulas through the app against a pinned core.
  They are the regression suite for adoption: bump the pin, run them, and
  any change in behaviour shows up there first.
