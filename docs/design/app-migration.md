# Moving Simple Steps onto the new core

> Step G of [phase4-plan.md](phase4-plan.md), brought forward: what the app
> repo (`Simple_Steps`) changes to run on this core, in what order, and what
> it adopts later. Derived 2026-10-27 at core `fdd3b62`, from the app at
> `1139779` (pin `86170a3`, 69 core commits behind). The app's own maps of
> the same work are its `docs/cleanup-map.md` (round 4, stages A–D) and
> `docs/system_design/12-core-and-app.md`; this page says which of their
> rows core now makes possible.
>
> **Amended 2026-11-02.** The app now moves **after the expression cleanup**
> (phase4-plan S0–S11), not before it (decisions.md N1, D51): the syntax the
> app writes expressions in changes, so it moves once, onto the new syntax.
> What each cleanup step changes for the app is §3.8, kept current as each
> step lands. The word is now *expression* (CA-F); core's `step.formula`
> keeps its name until it is renamed.

## 1. Can the app move now?

**Not yet (2026-11-02).** It waits for phase4-plan's S5, S4, S3 and S11:
they change how rows are picked, how columns bind and are named, and what an
expression saves, so moving before them would mean migrating twice (N1).
Steps D, E and F still don't block it, as below.

*As written 2026-10-27:* **Yes.** Nothing left in phase 4 blocks it. Steps D, E and F add features
the app either does without today or does for itself, and none of them
renames or removes anything the app will use. So the move is one breaking
pass now, then small additive passes as each core step lands (§5).

| Left in core | What the app does meanwhile | Blocks the move? |
|---|---|---|
| D: K22 outputs by data version | keeps `DATA_STORE` / `RAW_STORE` | no |
| D: K23, K14 progress and `cancel()` | keeps `progress.py`; only the legacy orchestrators call it | no |
| D: K15 re-run failed rows; R9 stages; autorun | not used yet | no |
| E: C32, K16 output store; R7 media | saves the spec; a reloaded workflow re-runs, as today | no |
| F: G18 the workflow as a table | its own UI | no |
| C-D2 the seed recommendation | — | no |

The one thing that would be worse later: every core commit from here on is
written against an app that isn't on it. Moving now means the app's tests
check core's changes as they land.

## 2. Before the pin moves (on the old pin)

Shrink what has to move. These are the app's own decided cleanups
(cleanup-map.md round 4), none of which needs the new core, and each removes
code the move would otherwise have to port:

1. **Stage A:** eval mode (L1), the engine switch (L2), the unused routes.
2. **Stage D, under "the best code is no code"**: `pack_loader.py` (L3),
   the old-syntax formulas and orchestrators (L4), `safe_formula.py` and the
   console (L7), `step_proxy.py` and `helpers.py` (L8), duplicate tools
   (L9). About 3,200 lines; the old engine's last users go with them.
3. **Stage B:** split `grid_runner.py` into what the kernel needs and the
   legacy per-step path; `models.StepConfig` and `example_check.py` onto
   `operation_formula`; `@simple_step_tool` stops wrapping in `StepProxy`.

Checks after each, as the app has them: `pytest`, `scripts/preflight.py`,
`examples/runme.py`.

## 3. Moving the pin

One branch in the app, in this order. Each item ends with the app's tests
passing, except where it says otherwise.

### 3.1 Pin and imports

Move `pyproject.toml`'s pin and `external/simple-steps-core` together. Then
**import from the package; `simple_steps_core.grid` is gone**:

```python
from simple_steps_core import (Catalog, Kernel, tool, resource, bound_tool, Secret,
    mod, wf, res, rows, cols, join, stack, zip_, Operation, Step, Output, Problem)
```

Anything else comes from its module and may still change:

| The app uses | Now |
|---|---|
| `grid.Workflow` (61 uses) | `Kernel` for everything the app hosts; `simple_steps_core.workflow.Workflow` only inside core |
| `grid.Operation`, `grid.op`, `grid.Output` | `Operation`, `op`, `Output` |
| `grid.mod`, `wf`, `res`, `cols`, `zip_`, `join`, `stack`, `tool`, `resource`, `bound_tool` | the same names, from the package |
| `grid.ResourceNotLoaded` | `ResourceNotLoaded` (also `StepFailed`, `SelectionError`, `PayloadError`) |
| `grid.catalog`, `tool_entry`, `resource_entry`, `modifier_catalog`, `builtin_tools`, `shape_verbs`, `MODIFIERS`, `BUILTIN_TOOLS` | `cat.describe()` (`tools`, `modifiers`, `combines`, `resource_types`) |
| `grid.TOOLS`, `grid.RESOURCE_TYPES`, `REGISTRY`, `register_tool` | gone: a `Catalog` |
| `grid.ToolHandle` | `Tool` |
| `grid.payload_column(output)` | `output.value_column` |
| `grid.grid(value)` (`example_check.as_table`) | `k["x"] = value` then `k.step("x").data`; or `simple_steps_core.verbs.grid` |
| `grid.infer_verb` (the editor's `/api/infer_verb`) | `k.infer_verb(tool, input, arguments, bound_to=…)` → `(verb, why)`, declaring nothing |
| `grid.formula_names` | `cat.formula_names()` |
| `grid.check_modifier`, `predicted_columns`, `check` | `k.check(name, op)` and `step.plan` |

The pin-drift symptom in the app's `CLAUDE.md` and `docs/context.md`
becomes *`cannot import name 'grid' from 'simple_steps_core'`*.

### 3.2 One catalog

`application.App` builds the catalog; nothing registers itself.

- `@simple_step_tool` = core's `@tool` plus `extras={"simple_steps.ui": {name,
  category, widgets}}`; its description goes in the docstring.
- `core_bridge.register_with_core` and `main.py:139` stop using `REGISTRY`;
  `OPERATION_REGISTRY` becomes `Catalog(tools=[…], resources=[…])` or
  `Catalog.from_modules(app_tools)`. `agent/scope.py` reads the catalog.
- The palette is `cat.describe()`; restricting is `cat.without(…)`.
- `core_bridge.py`'s built-in tool groups (the old `ResourceSpec`) become
  plain tools in the catalog, with a tag for the group.

Dead afterwards: `OPERATION_REGISTRY` (56 references), `DEFINITIONS_LIST`,
`core_bridge.py`'s shims (C17, C18, G).

### 3.3 Host core's kernel

`kernels.Kernel` keeps what hosting needs (key, lock, last-used) and holds a
core `Kernel`. The rest it reads from core:

| The app computes | Core gives |
|---|---|
| `Kernel.formulas`, `operations`, `reads`, `uses`, `problems`, `loaded`, `ids` | `k.steps`, `step.formula`, `step.operation.reads`, `step.problems` (each a `Problem` with `code`), `k.resources.loaded`, `step.id` |
| `kernels.summary()` | `repr(k)`, `k.needs_run()` |
| a step's status | `step.state` (`staged`, `completed`, `stale`, `failed`, `invalid`), `step.output.stale_reason` |
| change notifications | `k.on_change(callback)` |
| data for the grid view | `k.view(step, …)` (pages of 50, `window`), `k.cell(step, row id)`, `step.plan` (`size`, types, `inverse`) |
| checking a proposal | `k.check(name, op)` |

`agent/proposals.check_step` calls `k.check`.

### 3.4 Formulas

The parser stays in the app (`operation_formula.py`) and builds
`Operation.from_spec(spec, catalog)`; core prints with `step.formula`.
`formula_parser.py`'s canonical half goes; the UI's `/api/parse_formula`
keeps its response shape.

### 3.5 Saving and loading

`file_manager.py` saves `k.to_json()` and loads `Kernel.from_json(text,
catalog)`. Core reads format 4 only and refuses others with a message, so
**re-save** the mock projects and examples. Under the app's own rule (no
converters without a named user) older workspace files get that message;
a converter is the owner's call (K17, §6).

Secrets: a resource setting typed `Secret[str]` is never saved, so a loaded
kernel asks for it (`k.define(…)` again, or `k.resources.attach`).

### 3.6 What reads differently

Renames from phase 3:

| Was | Now |
|---|---|
| `ToolHandle`, `BoundToolHandle`, `ResourceDecl` | `Tool`, `BoundTool`, `Resource` |
| `op.tool_id`, `step.step_id` | `op.tool`, `step.name` |
| `modifier.params` | `modifier.settings` |
| `step.status` (a string) | `step.state`; `step.status` is a `StepStatus` |
| `PAYLOAD`, `payload_column()`, `meta["payload"]` | `VALUE_COLUMN`, `value_column()`, `output.value_column` |
| preview `["status"]` | `["state"]` |
| JSON `step_id`, `tool_id`, `params` | `name`, `tool`, `settings` (format 4) |
| `name=` on a step | `mod.name(…)` |

Behaviour from phase 4, which the UI and its tests will see:

| Change | Rule ([rules.md](rules.md)) |
|---|---|
| a step's `.data` has its row id `#` as the index, and starts with the `#` columns that say where each row came from (`#v`, …); tools never see them | 2, 3 |
| `k.view` rows carry the row id under `#`, the screen position under `position`; `k.cell` takes a row id. **Superseded by S5 (§3.8)**: `#` becomes the row number | 2 |
| selections and column arguments go by row id, not position. **Superseded by S1 and S5 (§3.8)** | 2, 6 |
| `zip_` and column arguments between unrelated steps are refused; `zip_(…, match_ids=True)`. **Tightened by S1 and S5 (§3.8)** | 6 |
| `collapse`, `distinct`, `join`, `stack` add `#` columns; `gather[collapse()]` gives one list per column; a reducer gets lists | 3, 10 |
| `expand` of a bare string or `None` fails the row; a dict expands to key/value rows | 9 |
| a cell state `absent`; ints stay ints when rows fail | 9 |
| `k["x"] = None` is the empty step | 9 |
| a `-> Record` return spreads into one column per field; `mod.name` takes a list, mapping or pattern; `Kernel(cat, naming=…)` | — |
| `timeout` is enforced; failures say `where`; defaults used warn; a stale read warns | — |
| `plan` has `size` and observed types, or `unknown` with the reason | 7 |
| `k.id`, `k.run_id`, `step.id`, `k.diff(other)`; tool hashes in the catalog spec; a resource's `data_version()` | — |
| a resource passed by position binds as the tool's argument; a plain call with `res[…]` is refused | — |

The `ref_id` the frontend uses (12 references) keeps its name; its value
becomes the step's data version (`step.output.version`), as cleanup-map.md
recommends.

### 3.7 Probes and the handover folder

Regenerate the app's `scripts/core_probes/` and `scripts/core_asks.py`
against the package API (they import `grid`), then rebuild
`core-handover/` with `scripts/core_handover.py`.

### 3.8 What the expression cleanup changes for the app

One row per change, by phase4-plan step, **added as each step lands**
(phase4-plan §3, "After S4, and S11"). The design is core's
[core-asks/model.md](core-asks/model.md); its decisions are decisions.md §0
and §4. Core's copy of `core-asks/` leads (N4): the app's `docs/core-asks/`
is copied from it, not the other way round.

**Landed**

| Step | Change | What the app does |
|---|---|---|
| S1 | `total` over mixed columns fails only the cells it can't add, naming `numeric_only=True`; `op("total")[mod.collapse()](…, numeric_only=True)` leaves those columns out | nothing, or offer `numeric_only` in the palette |
| S1 | a failed cell can carry its own error: the view's cell `error` comes from the row's note `cells` when present | show a cell's own error |
| S1 | `mod.widen("info")` names the column it spreads (printed that way); with no name, the one column holding dicts; none or several fail the step | the parser accepts `mod.widen("info")` |
| S1 | `mod.expand(columns=[…], keep=…)`: a dict column gives a row per key (`key`, then the values); `keep=False` drops the other columns | the parser and palette know `keep=` |
| S1 | a `#` column as a tool argument is refused, problem code `id_argument` | show the code |
| S1 | `stack` of an input holding only row ids is refused (`bad_combine`) | — |
| S1 | under `map` / `filter` / `expand` a column argument passes **each row's cell, whatever the parameter's type** (CA-D1); a column whose rows would leave a row without a value is refused, code `bad_pairing`, the message writing the join. A list parameter no longer gets a whole column: gather it into one cell (`op("gather")[mod.collapse()]`), which goes to every row | rewrite formulas that relied on a list parameter getting the whole column; show `bad_pairing` |
| S1 | a one-cell argument holding a list passes that list, not wrapped in another | — |
| S1 | a `zip_` of one origin whose row ids differ is refused once both inputs have run (`bad_combine`), instead of failing the run | — |
| S1 | an object's data version is its own `data_version()`, else its fields, else its pickle: readers of an object column no longer look stale after every run | — |
| S1 | a step is stale when a column its output carries changes, not only a bound one | more steps show `stale`, correctly |
| S1 | an int column stays int across a `join` gap | — |
| S5a, S5b | the view's `#` is the row number `0…n-1`; the `id` field goes; `k.cell(step, row)` takes a row number (and refuses anything else, saying so); a cell's `inputs` give each input row as `row` (its number), not `id`; lineage is listed apart: `view["lineage"]` names the columns, each row's `lineage` holds them (the ancestor's current row number, a list after a collapse, `None` for a gap), and every step carries its ancestors' (`#r`, `#r.idx`, `#r.2`). `step.output.data` keeps core's ids, for code | show `#` as is; collapse lineage under "from r"; read `row`, not `id`, in a cell's inputs |
| S5c | conditions choose rows: `wf["r"][cols["n"] > 15]`, `wf["e"][row["r"] == 3]`, `row["r"].idx == 1`, `.isin([…])`, joined by `&`, `\|`, `~` (each test in brackets); also `mod.select(rows=…)`. Saved as data (`rows: {"where": …}`), printed back as written; a list cell matches by membership, `<` / `>` on one is refused; an empty cell fails every test. Matching nothing gives zero rows and a `run_warning`. `row` is exported and reserved (`from simple_steps_core import row`) | the parser builds conditions with core's `cols` and `row` (never evaluating Python); show the warning |
| S5c | `tool(fn, id="x")` names the tool `x` (the id was ignored unless used as a decorator) | — |
| S5d | an integer in a pick is a **row number** (`[0]`, `[-1]`, `[[0, 2]]`), everywhere. Once the picked step has run, staging saves it as the row's lineage: `wf["s"][rows[row["r"] == 2]]`, `rows[(row["r"] == 1) & (row["r"].idx == 0)]` after an expand, `rows[cols["ward"] == "B"]` for a group; into a source it stays a number; a range stays a range. `rows[condition]` names rows that must exist (gone: the step fails, naming the row); a plain `[condition]` filters. Text row ids (`rows["A"]`) are refused; a list naming a row twice is refused | a click writes a row number; show the saved form; the parser accepts `rows[condition]` |
| S5e | **strict alignment (CA-11)**: a column argument and `zip_` pair rows only between aligned steps (the same rows in the same order: one-to-one steps, a `zip_` of them, `collapse(by="#s")` beside `s`); anything else is refused (`bad_pairing`, `bad_combine`) and the message writes the join, `on="#s"` for the nearest shared ancestor. A child with its parent, or a sorted copy with its source, now meet in that join | rewrite those pairings as joins on lineage |
| S5e | `run_all` runs each step after every step it depends on that is still to run (it could run a reader before an input about to change) | — |
| S5e | `join(child, parent, on="#r")` matches each child row with its parent row (by row number); `how="left"` gives every parent row back, the child's columns `absent` where it dropped one. A column both sides carry unchanged from the shared ancestor appears once; one that differs keeps its `_left` / `_right` suffixes. A side with no lineage `#r`, or lists there (a collapse), fails the step saying so | offer "join back to parent" |
| S5e | lineage is read-only: `mod.copy(columns={"#r": "parent"})` copies it into a data column (the row numbers as shown); `mod.rename` of a `#` column copies too and is saved as `mod.copy` (mixing data and lineage in one rename is refused); picking a `#` column (`cols["#"]`, `select(columns=["#…"])`) is refused, pointing to `mod.copy` | rewrite picks of `#` columns as `mod.copy` |
| S5d | `collapse(by="#s")` runs after `s` and goes stale when `s` changes (it waited only for its input) | — |
| S2 | a numeric or empty column name becomes `var<n>` (`0`, `"0"` → `var0`, `2023` → `var2023`); a clash is refused naming both | expressions that named `"0"` name `var0` |

**Coming** (planned; this list becomes "landed" row by row)

| Step | Change | What the app will do |
|---|---|---|
| S4 | one output column is named after its step (not `value`); a dict result gives a column per key; step names are identifiers, no `.` | rewrite `"value"` references |
| S3 | plain strings choose columns (`wf["p"]["temp"]`); a pick can be a tool's input; binding decided at staging and **saved explicitly** (`n=wf["d"]["d"]`); `mod.cast`; an inferred verb is written, never `filter`; nothing added unseen | the parser accepts the new forms; show what staging decided as core's |
| S11 | a reader whose column disappeared is `invalid` at once; stale steps say why; a rename rewrites what core wrote; `k.remove(name, force=True)` | show the reasons |

## 4. Done means

1. The app's tests pass, with the tests of removed code removed with it, and
   no test of behaviour that stays edited to pass.
2. `scripts/preflight.py` and `examples/runme.py` run.
3. The acceptance session in the app's doc 12: every *update* line passes.
4. `grep -r "simple_steps_core.grid\|REGISTRY\|OPERATION_REGISTRY"` finds nothing.
5. The UI runs a workflow end to end: declare, run, edit (stale), save, load.

## 5. Later, as each core step lands

Additive, each a small pass in the app (cleanup-map.md stage C rows):

| Core step | The app then | Removes |
|---|---|---|
| D: K22 outputs by data version | `/api/data`, `/api/cell`, `/api/data-meta` read from the kernel | `DATA_STORE`, `RAW_STORE`, the leak |
| D: K23, K14 progress, `cancel()` | `progress.py` and `/api/progress/{step_id}` relay core's callback | its own progress bookkeeping |
| D: K15, R9, autorun | a "re-run failed rows" action; stages shown as one block | — |
| E: the output store | `file_manager.py` passes a store; a reloaded workspace opens with its data | — |
| E: R7 media handles | `cell_types.py` reads handles | — |
| F: G18 | the table view from core's step blocks | its own row alignment |

## 6. Decisions

| | Decision | Recommended |
|---|---|---|
| G-D1 | move the app now, before steps D–F | **superseded 2026-11-02 by N1**: after S0–S11, before D–F |
| G-D2 | older saved workspaces (K17) | refuse with core's message, as the app's own rule says; a converter only if a named user has files to keep |
| G-D3 | the app's stage A, B, D deletions before the move | yes: less to port, and none of them needs the new core |

## 7. To do in core

What `simple-steps-core` does for this move, then after it. Each item is
one piece, confirmed before it lands; ✓ when done.

### Before the app moves

| | To do | Why |
|---|---|---|
| T1 ✓ | **Tag a release** (`0.2.0`, from `0.1.0`) at the commit the app pins, and bump `__version__` | the app pins a commit today; a tag says which core the migration was checked against |
| T2 ✓ | **Export what the app needs publicly**: `ResourceNotLoaded` (and the other errors), `op`; or say which module each comes from in `docs/integrating.md` | §3.1 sends the app to internal modules for these; an internal name may change |
| T3 ✓ | **A public way to infer a verb and list formula names** (`k.infer_verb`, `cat.formula_names()`): the UI calls `/api/infer_verb` and the parser needs `formula_names` (today `checks.infer_verb`, `catalog.formula_names`, both internal) | the app shouldn't reach into `checks` |
| T4 ✓ | `cat.describe()` gives each tool's **`hash`** beside its tags and extras | the palette and the workflow file show `k.id`; a changed tool should be visible there too |
| T5 ✓ | **Update kernel-session.md and its example** (`examples/kernel_session.py`) with step C: ids, `diff`, `Secret`, `data_version()` | the working guide is what the app's developer reads first (phase-4 *done means*, 4) |
| T6 | **Run the app's acceptance session against core alone** (its doc 12, and the regenerated probes), and fix what fails here, not in the app | "if the app works out a fact about a workflow, that fact belongs in core" |

### Decisions waiting on the owner

| | Decision | Recommended |
|---|---|---|
| C-D2 | the seed recommendation | a tool with a `seed` parameter its step doesn't give warns |
| R-D1 | a resource whose type has bound tools: also passable to a free tool as an argument, or only through its bound tools? | both allowed (today's behaviour), unless you mean to refuse |
| G-D1–3 | §6 | as recommended there |

### Leftovers from step A

| | To do |
|---|---|
| T7 ✓ | `where: expect` on a failure note from an `expect` modifier, like `where: timeout` |
| T8 ✓ | a source tool returning a record gives one row, a list of records a row per record, a column per field; an item that doesn't fit fails the step, `where: declared`. An undeclared `list[dict]` stays one cell |

### Before the move: the expression cleanup

phase4-plan S0–S11 (S0, S1, S2 done 2026-11-02; S5 next). Each adds its rows
to §3.8 as it lands.

### After the move: the rest of phase 4

In order, each as its step in [phase4-plan.md](phase4-plan.md), and each
followed by its small pass in the app (§5):

| | Step | Needs first |
|---|---|---|
| T9 | **D. Sessions**: K22 outputs by data version, K23/K14 progress and `cancel()`, K15 re-run failed rows, R9 stages, the autorun modifier | D-D1 (autorun design), D-D2 (progress callback) |
| T10 | **E. Storage**: C32/K16 the output store, R7 media handles | E-D1 (the store's interface) |
| T11 | **F. The workflow as a table** (G18) | nothing new |
| T12 | `scripts/core_asks.py` at 39 of 39 (K14, K15, K16 close with D and E) | T9, T10 |
| T13 | **Phase 5, the final docs** (cleanup-plan.md §6): README, writing-tools, resources (secrets, data versions), modifiers, integrating (for the app), problems | phase 4 done |
