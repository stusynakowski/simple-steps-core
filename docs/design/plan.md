# The plan

> **The one plan**: the goals, the order of work, and what each step needs.
> Reorganised 2026-10-31; reordered 2026-11-02 for the core asks; brought up
> to date 2026-11-03 (it was phase4-plan.md). Pages that go together:
>
> | Page | Holds |
> |---|---|
> | **this one** | the goals, the order of work, and the changes in detail |
> | [model.md](model.md) | what core is: each rule marked built or planned |
> | [decisions.md](decisions.md) | every decision, the open ones first |
> | [core-asks/model.md](core-asks/model.md), [core-asks/plan.md](core-asks/plan.md) | the app's requirements: references, selection, lineage, binding, and the probe that tests them |
>
> Done work keeps its own record in §4 below, and in [history/](history/)
> (the reshaping and cleanup plans).

## 1. The goals

**For a user.** A workflow reads like Python and feels like a spreadsheet:

1. **A step is a list of rows, and a row is a dict.** You iterate through the
   list; the keys are what you call the things in each row.
2. **An expression says what each tool receives, and how many times it runs.**
   The verb decides how much an argument passes; staging decides which column
   reaches which parameter (what you wrote, then a matching name, then the one
   fitting type) and writes it into the expression. Core never guesses
   between two columns, never passes a name or a row number, and nothing
   happens that the saved expression doesn't show.
3. **Reshaping is quick,** and never loses information silently.
4. **What you see is true:** sizes, types, states, what is stale and why.
5. **A workflow is reproducible:** the same recipe, tools and data give the
   same result, and core can say when they don't.

**For the code.** The grid model is the only model. It is **airtight**:
every rule has a law that tests it, the property tests generate workflows
that break none of them, and every refusal names its fix.

**For the app.** Simple Steps moves onto this core once, after the syntax it
writes formulas in is settled.

## 2. The order of work

One list, in order. A step starts when its decisions (decisions.md, by the
same letter) are made, and ends when its laws pass, the suite and the
property tests (`STRESS=1`) are green, and it is committed. Each behaviour
change is confirmed before it lands.

| | Step | What it does | core-asks | Size | Status |
|---|---|---|---|---|---|
| A | Outputs | records spread into columns; naming; warnings; `timeout` | — | — | ✓ |
| B | Seeing the data | sizes, pages, observed types, stale reads | — | — | ✓ |
| C | Identity | tool hashes, ids, `diff`, `data_version()`, `Secret` | — | — | ✓ (seed: S9) |
| — | Conditions | `mod.map(where=…)`, `first_present` | — | — | ✓ |
| **S0** | **The tests** | the laws E1–E27, expected-to-fail until their step; core-asks `probe.py` (L1–L52) turned into tests the same way | all | small | ✓ 2026-11-02 |
| **S1** | **Bugs, and no wrong answers** | B1–B11; a column argument from an unaligned step refused, the message writing the join; `zip_` of unaligned steps refused; `total` over mixed columns | M0 (L1–L5) | small | ✓ 2026-11-02 |
| **S2** | **Values and keys** | tools get plain Python values (already held on every path; now tested); numeric names become `var<n>`; other names kept (CA-E) | L21 | small | ✓ 2026-11-02 |
| **S5** | **Row numbers and lineage** (moved up) | **a change of surface** (CA-B1, amended): rows shown and typed as `0…n-1`, picks saved as lineage; core's lineage-based row ids stay its identity. Every step carries its ancestors' lineage; `.idx`; `#r.2`; lineage apart from data; conditions (`cols`, `row`, from S3); joins on lineage; `mod.copy`; strict alignment (CA-11). Five pieces, §3 | M1, M2, conditions (L6–L19, L29–L31, L35, L36, L41, L44, L45, L48) | medium (was the largest) | ✓ 2026-11-02 |
| **S5f** | **Freeze** (2026-11-03) | pairing by identity: aligned means the same rows in any order (CA-11, amended); the A5 check traces every join on lineage back by id; a group never joins on lineage (unpack it first); an edit re-checks everything downstream, and a step reading an `invalid` one is `invalid`; three crashes found at `STRESS=1` fixed; every property-test failure listed ([tests/stress-failures.md](../../tests/stress-failures.md)); the docs consolidated into model.md | M2, M6 L40 | — | ✓ 2026-11-03 |
| **S4** | **Naming** | one output named after its step; a dict's keys as columns; `var<n>`; ints stay ints; step names identifiers; sources and literals (D12) | M3 (L20–L24, L46, L47) | medium | D12 decided 2026-11-04: ready |
| **S3** | **Grammar and binding** | strings choose columns; pickers before the verb; a pick as an input; **binding at staging, saved explicitly** (CA-A); `mod.cast`; verbs inferred and written (`auto` resolved, D20); nothing unseen (D21) | M4, M5 (L25–L39, L48–L51) | **large** | N2, N3, D8 (no), D18, D19, D21, EX5 decided (2026-11-04): ready |
| **S11** | **Live editing** (**recommended next**) | the session model (SM, [model.md §8.1](model.md#81-the-proposed-session-model-sm)): a result store filed by run key (K22, from step D), stored as **ST** (row maps, columns and media filed once by content hash), every state derived from it, never flagged; `needs_run()` and `running` (SS5, SS6); stale reasons among the warnings, delete anyway (SS7); picks into a source follow their rows when its data changes (D-picks); readers re-checked at once ✓ (`baec929`); renames rewrite what core wrote ✓ | M6 (L41–L43, L52) | medium | needs SM, SS5–SS7, D-picks ([decisions.md §0](decisions.md#0-needed-from-you-now)) |
| **G** | **The app moves** | [app-migration.md](app-migration.md), onto the new syntax; core's to-dos T6, T9–T13 | — | medium (in the app) | D50, D52, D53 decided 2026-11-04 |
| **D** | **Sessions** | outputs kept by version (K22), progress and `cancel()` (K23, K14), re-run failed or stale rows (K15, D42), stages (R9), autorun | — | medium–large | needs D-D1, D-D2, D42 |
| **E** | **Storage** | the output store (C32, K16); media handles (R7) | — | medium | needs E-D1 |
| **F** | **The workflow as a table** | step blocks side by side, rows lined up (G18) | — | medium | nothing new |
| **S6** | **Modifiers** | `initial=`, `sweep`'s values and `over=` move into the call | — | small | needs D22–D25, D56 |
| **S7** | **Reshaping** | `melt`, `pivot`, `collapse(keep=…)`, the cheat sheet | — | medium | needs D33, D34, D36 |
| **S8** | **States** | the `empty` state; marks on `completed`; `running` (CA-10) | — | small | needs D37–D40 |
| **S9** | **Staleness and time** | the exact cells an argument reads; volatility (pure, seeded, versioned, volatile); *as of*; the seed | — | medium | needs D41, D43–D46 |
| **S10** | **Docs and UI** | rules.md opens with the model; `k.data(…)`; the output UI written into the app's dev plan (lineage expander, CA-B2) | — | small | needs D48, D49 |
| — | **Phase 5** | the final docs set (cleanup-plan.md §6) | — | medium | after all of the above |

The steps keep their letters, so decisions.md's groups still point at them;
the order is the table's.

**Why this order.**
- S1 first: it stops wrong answers under any syntax (core-asks M0).
- Everything up to S11 changes what an expression means, so it goes before
  the app moves (G), and the app's expressions change once.
- S5 (row numbers) now comes **before** the grammar: an integer in a pick is
  a row number (CA-B1), and lineage is what joins, conditions and "reference
  moved" are built on. This follows core-asks' milestone order (N1, decided
  2026-11-02: settled before more app development).
- D, E and F add features and break nothing, so after G they can go in any
  order. S6–S10 are small and mostly additive.

**The cheaper path is gone** (N1): deferring S5 past G would mean the app
migrating twice.

### After the app moves: later, by decision (owner, 2026-11-04)

Wanted, not before the move. Each lands as its own piece, confirmed first;
none changes what an existing expression means.

| | What | From |
|---|---|---|
| L1 | **Sharing settings for tools and resources**: a kernel or catalog setting that allows or prevents passing a resource to free tools, and sharing tools between resources (today both are allowed, D50) | D50 |
| L2 | **One join for several tables**, `join(a, b, c, on=[…])`, as one step | WR4 |
| L3 | **A join that drops rows warns**, with the count | WR5 |
| L4 | **Better tracing**: `k.trace(step, rows, to=ancestor)` gives the pick of the rows behind them | PK3 |
| L5 | **Steps grouped into stages** | R9 (step D) |
| L6 | **Lazy row execution**: each verb's row map in its plan (PL2), stale rows that follow the row maps (PL3), and a partial re-run of only the stale rows, an outside-world tool kept until asked to refresh (PL4) | PL2–PL4, K15, D42 |
| L7 | **Refusing on an exact plan**: a tool parameter missing from a plan whose columns are exact is a problem at once, not a *likely missing* warning | PL |

## 3. The changes, in detail (S0–S5)

What I propose to change, step by step: what you'd see before and after,
where in the code, and the test that shows it. Later steps (S11, S6–S10, D,
E, F) are written at this level when they come up. Nothing below lands without
your yes on its decisions ([decisions.md](decisions.md)).

### S0. The tests (no behaviour changes)

| Change | Where |
|---|---|
| The laws E1–E27 of syntax-review.md §8, one test each, marked expected-to-fail with the step that will make it pass | new `tests/unit/test_expressions.py` |
| A regression test per bug B1–B10, expected-to-fail until S1 | the same file |
| The property test learns the new references (`wf["p"]["temp"]`, `wf["p"][1]`), switched on step by step | `tests/unit/test_reshape_properties.py` |

Running it shows exactly what fails today: the starting line.

**Done 2026-11-02.** `tests/unit/test_core_asks.py` runs every core-asks
test from `probe.py` (18 hold, 63 wait, 1 skip); `tests/unit/test_expressions.py`
has the laws and bugs the probe doesn't cover (3 hold, 15 wait). Each waiting
test is `xfail(strict=True)` naming its step. Found while writing them:

- **E15 already holds** for a tool's parameters (plain `float`, `None`); D17
  is left for row dicts, which CA-A no longer passes (E10 superseded).
- **B9 as written didn't reproduce** (*"'list' is a block"*); what remains is
  `#xs` listed among a step's columns in a refusal. The test checks that.
- **B11** (new): a step stays `completed` when a column it passes through
  changes. The property test `test_L40c` found it; it's marked `xfail`, not
  strict, as the generator doesn't find it every run.
- Laws not written as tests: E10, E11, E16 (superseded by CA-A, CA-E); E1–E5,
  E12, E13, E17, E21 (covered by core-asks tests or `test_where.py`); E22
  (per-row staleness: core has none to test yet, written when S5 is detailed).
  The property test learns the new references step by step, from S5.

Suite: 720 passed, 1 skipped, 79 xfailed; `STRESS=1` property tests green.

### S1. Bugs

| | Today | After | Where | Needs |
|---|---|---|---|---|
| B1 | `widen(columns=["age", "bed"])` on `name, info` gives `None`s, silently | `mod.widen("info")` spreads that column; with other columns and none named: refused, *"widen which column? p has name, info"* | `verbs.widen_`, `checks` (widen's column) | D31 |
| B2 | `expand(columns=["info"])` refuses a dict | key/value rows, the other columns kept (so a melt keeps `ward`) | `verbs.expand_` / `_unpack` | D32 |
| B3 | `value=wf["p"][cols["#"]]` hands ids to a tool | refused: *"row ids aren't data; rename them into a variable first"* | `checks` (arguments), `workflow._resolve_arguments` | D27 |
| — | `rename(columns={"#": "row"})` refused | copies the row id into a variable `row`; the row keeps its `#` | `verbs` (rename), `checks` | D28 |
| B4 | `stack` of an ids-only step gives empty rows | refused: nothing to stack | `combines.stack` | D29 |
| B6 | `DataFrame([[1, 2]])` gets keys `"0"`, `"1"` | refused: *"columns must be named: mod.name(["a", "b"])"* | `verbs.grid` and the source path | D3 |
| B7 | a `scale` column silently replaces `scale=1.8` | a warning: *"scale comes from p's column, not its default 1.8"* (S3 then removes binding by name) | `modifiers._d_apply`, `checks` | — |
| B9 | a one-key list counts as a "block" (its `#` counted) | `#` columns never count towards a shape | `values._shape_kind` | — |
| B11 | **a step stays `completed` when a column it passes through changes.** Staleness looks only at the columns a tool binds: `key_pp[mod.group()](wf["s0"])` binds `k`, so editing `s0`'s `n` leaves it `completed` while its output still holds the old `n`. Found by `test_reshape_properties.py::test_L40c` (a `rec` cell `{}` → `{'a': None}`), failing at `11a7ca0` | stale when any column the output carries changed, not only the bound ones | `checks` / `workflow` (column-level staleness) | — |
| B10 | an object without a `repr` gets a new data version every run | its own `data_version()`, else its fields, else pickle; else the plan says it has no stable version | `output._data_version` | D57 |

(B5, `auto` stored, is S4. B8 is S3.)

**Done 2026-11-02**, with the owner's answers (decisions.md §4, "S1,
answered"). As built, where it differs from the table: `total(…,
numeric_only=True)` (L5); `mod.widen("info")`, or the one dict column (B1);
`expand(columns=…, keep=)` (B2); B6 became `var<n>` names (S2, L21); D28 became
`mod.copy` (S5); B7 became binding at staging (S3). Also built: L1–L3 (a
column argument pairs by verb, refused where a row would get no value; a
`zip_` whose ids differ refused once both ran), and A3 allowing a gap carried
through `zip_`.

### S2. Values and keys

| Today | After | Where | Needs |
|---|---|---|---|
| a row dict holds `np.float64(38.2)`, missing floats as `NaN` | `38.2`, `None`: plain Python, unless the parameter asks for `pd.Series` / `DataFrame` | `verbs._units` (the one place rows are made for tools) | D17 |
| any string is a column name | an identifier (`temp_f`); others refused with a suggested name, when a step writes them | `checks` (names written: sources, `mod.name`, `rename`, records) | D3 |

**Done 2026-11-02.** D17 already held on every path (parameters, `**row`,
gathered lists, the view); a test keeps it. D3 became CA-E: names are kept as
written, and numeric or empty ones become `var<n>` (L21).

### S5. Row numbers and lineage: a change of surface

Written 2026-11-02 at `65865bb`, every *today* run. CA-B1 (amended) is the
design: core's row ids stay its identity, because they already are lineage;
what a user sees and writes becomes row numbers and lineage.

**Today** (run on the core-asks fixture):

| | Row id (the view's `#`) | Lineage stored |
|---|---|---|
| a source | `0, 1, 2, 3` | none |
| `filter`, `sort`, `slice` | the parent's ids: `1, 2, 3`; `3, 2, 1, 0` | none: the id *is* the parent's |
| `expand` | `0.0, 0.1, 1.0, …` | `#r`: the parent's ids |
| `collapse(by=…)` | the key: `A, B, C` | `#r`: lists of the parent's ids |
| `join`, `stack` | `0 … n-1` | `#r`, `#other`: each side's ids, `None` for a gap |

The view already returns each row's `position` (0…n-1) beside `#`; lineage
columns sit among the data columns; an expand of `filtered` writes
`#filtered` = `1, 1, 2, 2` (filtered's ids, which are r's), not filtered's
row numbers `0, 0, 1, 1`.

**The changes**, in five pieces, each its own commit:

| | Piece | Today | After | Where | Tests |
|---|---|---|---|---|---|
| S5a | **What you see** | `#` is the row id; lineage columns among the data, holding ids | `#` (and `#<step>`) is the row number, `0…n-1`; lineage listed apart (`view["lineage"]`), each cell the parent's **current** row number (a list after a collapse, empty where there is none). `k.cell(step, row)` takes a row number | `workflow` (view, `_preview_rows`, `cell`), a translation through `trace` | L6, L10, L11a, L12b, L14a, L16a |
| S5b | **Lineage is carried, and named** | only combines and expands write lineage, one hop | every step that isn't one-to-one adds `#<parent>` and carries its input's; one-to-one steps carry. Computed from the ids by `trace` for the steps that keep ids, so nothing new is stored. An expand adds `#<parent>.idx` (from the id's last part); the same parent twice is `#r`, `#r.2` (today `#r_1`, `#r_2`) | `workflow` (lineage of a step), `combines` (names) | L12, L13, L14b, L15, L44 |
| S5c | **Conditions** (moved from S3, S5-D1) | `cols["n"] > 15` is a `TypeError` | `cols["x"]`, `row["s"]`, `row["s"].idx`, comparisons, `.isin`, `&`, `\|`, `~`, in a pick's row slot and in `mod.select(rows=…)`; list cells by CA-L3; matching nothing is zero rows and a warning; `row`, `rows`, `cols` reserved | `references` (a condition object, parsed, never run), `verbs.select`, `checks` | L29a, L29b, L30a, L30b, L31, L35, L36, L48a, L48b |
| S5d | **Picks are row numbers, saved as lineage** | `wf["sorted_"][1]` is row id 1 (`n` 20); `[-1]` refused; `rows["A"]` works | `[i]`, `[[i, k]]`, `[-1]` are row numbers as typed; staging writes the rows' lineage: `row["r"] == 2`; `(row["r"] == 1) & (row["r"].idx == 0)` through an expand; `cols["ward"] == "A"` through a collapse; both sides through a join; into a source, sweep or table it stays a row number. A range stays a range (S5-D2). A pick follows its row; one whose row is gone fails, naming it. `rows["A"]` refused with the row number to use | `references`, `checks` (resolve at staging), `operation.to_source` | L7a–L7f, L8, L41a, L41b |
| S5e | **Joins on lineage, copy, strict alignment** | `join(…, on="#r")` refused; no `mod.copy`; `rename` of `#r` replaces it; pairing by id after a sort or between child and parent | `join(child, parent, on="#r")`, `how="left"` gives every parent row back, `absent` where dropped; a column passed through from the shared ancestor appears once (CA-C). `mod.copy(columns={"#r": "parent"})`, and `rename` of a `#` column saved as it (CA-D). Column arguments and `zip_` only between aligned steps (CA-11); the refusal writes the join | `combines.join`, `verbs` (copy), `checks` (`_covers` → `aligned`) | L17, L18a, L18b, L45a, L45b, L37b |

**Decisions** (all decided as recommended, owner 2026-11-02):

| | Decision | Recommended |
|---|---|---|
| S5-D1 | Conditions move from S3 into S5 | yes: a pick saved as lineage is written as a condition, so the grammar has to exist first |
| S5-D2 | What a typed range saves | a range stays a range: `[0:10]` means the first ten rows, whatever they are (like `head`); a single row and a list of rows are saved as lineage |
| S5-D3 | A pick into a step that hasn't run | resolved when that step has run, and written in then, saying so (as D18) |
| S5-D4 | A lineage cell's number | the parent row's **current** row number (the model said "as when the step ran"); empty where the parent row is gone |
| S5-D5 | The Python API | `step.output.data` keeps core's ids as its index, for code; the view, `k.cell`, picks and `k.data()` (D48) use row numbers |
| S5-D6 | A join row's lineage pick, with an empty side | both sides' lineage, an empty side written `row["other"] == None` |

**Progress.** S5a and S5b done 2026-11-02: `Workflow.lineage(step)` works the
lineage out from core's ids; the view lists it apart and shows row numbers;
cell inputs give row numbers. 14 core-asks tests now hold (L6, L10–L16a, L52).
S5c done 2026-11-02: conditions (`references.Condition`, saved as
`{"where": …}`, evaluated against the data and the picked step's lineage, never
run as Python); 10 more hold (L29–L31, L35, L36, L48); the property test
generates conditions. Found on the way: `tool(fn, id=…)` ignored its id.
S5d done 2026-11-02: integers are row numbers; staging saves a pick as its
row's lineage (`rows[condition]`, which names rows that must exist: my reading
of CA-B1's "fails if gone" beside CA-5's "zero rows"); 10 more hold (L7a–L8,
L37b, L41a/b). The property test picks rows, and compares an edited run with a
fresh run of the *saved* workflow. Found on the way: `collapse(by="#s")` could
run before `s`, and didn't go stale with it.
S5e done 2026-11-02: `mod.copy`, `rename` of `#` saved as copy, `#` picks
refused; joins on lineage (a collapse's list meets each of its rows; shared
columns merge); alignment (CA-11), "aligned" widened to a `zip_` of
aligned steps, `collapse(by="#s")` and a restoring expand, so the reshaping
laws hold as they were; the tests that paired a child with its parent became
joins. Amended the same day (owner): aligned is the same rows **in any order**,
paired by identity, never by position, so a sort is aligned; the join on
lineage looks an aligned side's rows up by id (it read their positions, and
paired rows given back in group order with the wrong rows). Found on the way: `run_all` could run a reader before an input that was
about to change. **S5 is done**: every M1/M2 core-asks test holds.

**Existing tests that change** (counted at `65865bb`): the view's `#` (12
uses), `k.cell` by id (31; most read a source, where the id is the row
number), integer picks (8), text row ids (4), and the `zip_` and
column-argument tests that pair a child with its parent or after a sort (some
of 34 `zip_` uses), which become joins on lineage in S5e. Tests that read
`step.output.data.index` (47) keep core's ids (S5-D5) and don't change. The
property test learns typed row numbers and conditions in S5c and S5d.

### S3. The core change

| Today | After | Where | Needs |
|---|---|---|---|
| `wf["p"]["temp"]` refused (*"Columns use cols"*) | a string in brackets is a key; an integer a row; `wf["p"][1]["temp"]` = `wf["p"]["temp"][1]` | `references.StepRef.__getitem__` | D2, D10 |
| a selection can't be an input (*"make it its own step"*) | `to_f(wf["p"]["temp"])` is the normal form | `operation._wire`, `run`, staging | D6 |
| `wf[0]` is the first step | step names only | `references` (`wf[…]`) | D5 |
| `cols[…]` / `rows[…]` needed | kept for ranges of keys; printed in the plain form | `references`, `operation.to_source` | D7 |
| `.header` | `.keys` | `references` | D8 |
| parameters bind to columns **by name**, at run; a missing name is `invalid` | **at staging**, the first that decides: what the user wrote; a column with the parameter's name (only without a default: B7); the one column whose type fits; otherwise `invalid` naming the candidates or suggesting `mod.cast`. The result is **written into the saved expression** (`n=wf["d"]["d"]`) | `modifiers._d_apply`, `checks` (binding, `_paired_arguments`), `workflow._columns_bound`, `operation.to_source` | CA-A (replaces D13, D15) |
| what an argument column passes depends on the parameter's type | on the verb: a row's cell under `map`/`filter`/`expand`, the whole column under one call, the group's values under `collapse` | `modifiers`, `checks` | CA-D1 |
| — | `mod.cast(column="type")`; `int` → `float` automatic | `modifiers`, `checks` | CA-A |
| a reference to a step whose shape isn't known yet | a warning when declared, decided at run, re-checked after | `checks`, staging | D18 |
| `collapse(by="ward")` reads `ward` from the input | the same, also when the input is one key of a step | `verbs.collapse_` | D19 |

Binding by name stays (step 2 of CA-A), so most of the ~200 existing call
sites keep working; what changes is that the binding is saved explicitly,
which changes their saved specs and printed expressions. The full list of
changes and tests for S5, S4, S3 and S11 is core-asks/plan.md §5–§11; this
section keeps only what core-asks doesn't cover (`wf[0]`, `.keys`, D18,
D19, D12, D20, D21).

### S4. Broadcasting and naming

| Today | After | Where | Needs |
|---|---|---|---|
| `is_hot(wf["p"])` saves `mod.auto()`, decides at run (B5) | `auto` resolves when written, by §3.1's rules, and saves and prints what it chose (`map`, or one call) | `run._resolve_auto`, `operation._wire` | D20 |
| `auto` turns a `bool` tool into a `filter` | it doesn't: `filter` is written | `checks.infer_verb` | D20b |
| `auto` adds `breaker(after=5)` unseen | shown in the formula, or not added | `run` (defaults), `operation.to_source` | D21 |
| an unnamed single key is `value` | the step's name (`k["temp_f"] = …` → `temp_f`); `mod.name` still wins | `workflow.default_name_rule` | D9 |
| a source's `list[int]` is one value | its declared type decides: `list[T]` is rows; `list` or none is one value | the source path in `workflow` | D12 |
| a literal is one value | the same (confirmed) | — | D11 |

### After S4, and S11

G (the app moves) uses [app-migration.md](app-migration.md). **Each step, as
it lands, adds what the app changes to app-migration.md §3.8** (owner,
2026-11-02), so the migration guide is current when G starts.

## 4. Done means

Phase 4 is done when:

1. every law in syntax-review.md §8, and in reshaping.md §10, passes, with
   nothing expected-to-fail;
2. the property tests at `STRESS=1` pass, generating formulas in the new
   syntax;
3. `scripts/core_asks.py` says **39 of 39** (K14, K15, K16 close with D and E;
   K19 is re-probed for CA-C), and `docs/design/core-asks/probe.py` passes
   every test (today 24 of 85);
4. every feature in features.md is done, or moved to "Later, by decision";
5. rules.md opens with the model, kernel-session.md shows what was built,
   and its example runs as a test; app-migration.md §3.8 lists every change
   the app makes, step by step;
6. the app runs on this core (app-migration.md §4).

Then phase 5, the final docs, starts.

## 5. Done so far in phase 4

| | |
|---|---|
| **reshaping, closed** | row ids and `#` columns, matching rows, round trips, reductions as lists, uneven data (`absent`), the empty step, plans that say how to go back, the invariant check on every test, the property tests ([reshaping-plan.md](history/reshaping-plan.md)) |
| K19, K28 | selections, column arguments and `zip_` by row id; each cell's lineage |
| G1, G2, G4, G10, G12, G13, G17, R8 | `group` labels rows; missing is `None`; formulas print as written; `widen` replaces its column; `mod.name`; readers re-checked; the empty step; ints stay ints |
| **Step A**, 2026-10-27 | G5 (a fold's start), G8 (records spread), G9, G12 (every form, kernel naming), G6, G7 (warnings, *where*), K18 (`timeout`). `tests/unit/test_outputs.py` |
| **Step B**, 2026-10-27 | K1, K26 (sizes, pages of 50), K27 (observed types), K29 (stale reads). `tests/unit/test_seeing.py` |
| **Step C**, 2026-10-27 | K20 (tool hashes, `k.id`, `run_id`, step ids, `diff`, *tool changed*), K25 (`data_version()`), R3 (`Secret[str]`). `tests/unit/test_identity.py` |
| **For the app**, 2026-10-27 | exports, `k.infer_verb`, `cat.formula_names()`, hashes in `describe()`, `where: expect`, record sources, `v0.2.0` |
| **Conditions**, 2026-10-31 | `mod.map(where=test)`, `first_present`; a single cell broadcasts like a literal. `tests/unit/test_where.py` |

`scripts/core_asks.py`: 36 of 39. Open: K14 (progress), K15 (re-run failed
rows), K16 (results store).
