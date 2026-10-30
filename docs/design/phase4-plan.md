# Phase 4: the plan for what's left

> The one place for the rest of phase 4 (behaviour) of
> [cleanup-plan.md](cleanup-plan.md#4-order-of-work): what is done, what is
> left, in what order, what each step needs from the owner, and what "done"
> means. Updated 2026-10-27 at `39835bc`. The reshaping part of phase 4 is
> finished and has its own record, [reshaping-plan.md](reshaping-plan.md).
> The feature list this plan orders is [features.md](features.md).

## 1. How to read it

Each step is one piece of work: the features it builds (their ids), where
each is designed, what it needs from the owner, and what changes for someone
using core. A step starts when its decisions are confirmed and ends when its
probes pass (`scripts/core_asks.py`), the suite and the property tests are
green, and it is committed. *Today* lines were run at `39835bc`.

## 2. Where we are

| Done in phase 4 | |
|---|---|
| **reshaping, closed** | row ids and `#` columns, matching rows, round trips, reductions as lists, uneven data, the empty step, plans that say how to go back, the invariant check on every test, the property tests ([reshaping-plan.md](reshaping-plan.md)) |
| K19 | selections, column arguments and `zip_` by row id |
| K28 | each cell's lineage, through `#` columns |
| G1, G4, G10, G13, G17 | `group` labels rows; formulas print as written; `widen` replaces the column it spreads; a reader is re-checked when its input's columns change; the empty step |
| G2, R8 | missing is `None`, gaps are `absent`, ints stay ints |
| G12 (a single name) | `mod.name("temp_f")`, and `name=` retired |

`scripts/core_asks.py`: **35 of 39 asks done.** Open: K14 (progress), K15
(re-run only failed rows), K16 (results store), K18 (timeout).

## 3. The path

### Step A. Outputs, finished ✓

*Done 2026-10-27*: G5, G8, G9, G12 (every form, and kernel-wide naming), G6,
G7, K18. Tests in `tests/unit/test_outputs.py`. `scripts/core_asks.py`: 36 of
39.

| Feature | Designed in | Today |
|---|---|---|
| **G5** a fold with no `initial=` ✓ | grid-model.md §8 | built: starts from its accumulator type's empty value |
| **G8** a declared record type (`-> LoHi`) spreads into one column per field ✓ | outputs-and-reshaping.md §3 (decided 2026-10-26) | built, under `map`, `expand` (`-> list[LoHi]`), `collapse`, `sweep`, `auto`; each row held to it (§5); one name keeps it in one cell |
| **G9** `widen` reads declared record types, so its plan is exact ✓ | outputs-and-reshaping.md §6 | built |
| **G12** `mod.name` as a list, a mapping or a pattern; kernel-wide naming conventions ✓ | outputs-and-reshaping.md §4, §10 (decided 2026-10-26) | built: `Kernel(cat, naming=Naming(pattern=…, case=…))`, saved with the kernel |
| **G6, G7** a `try_except` default that doesn't fit the return type warns; a step that used defaults warns; a failure note says *where* it failed ✓ | grid-model.md §5.1, §5.2 (decided 2026-10-26) | built; also, a modifier written before the verb warns that it covers the whole step |
| **K18** `timeout` is enforced ✓ | grid-model.md §6 | built: a worker thread with a deadline (A-D2); a late call fails, `where: timeout` |

- **Decide:** G5 (A-D1) and K18 (A-D2), §5. The rest is decided.
- **Changes for users:** a `-> LoHi` tool's step gets columns `lo`, `hi`
  instead of one cell; a slow call under `timeout` fails.

### Step B. Seeing the data truthfully ✓

*Done 2026-10-27.* K1 was already built (a declared source plans its
columns). K26: a plan has `size`, rows and estimated bytes once run, else
`unknown` with the reason; `k.view` shows a page of 50 rows by default
(B-D1), and `window` says which and how many in all. K27: a type is declared,
else `unknown` until it runs, then observed, and a mix is the union
(`int | str`). K29: a step that read a stale step warns, naming it and its
version. Tests in `tests/unit/test_seeing.py`.

| Feature | Designed in |
|---|---|
| **K26** row count and estimated size per output, or `unknown` with the reason; pages of rows | kernel-session.md, interactive-sessions.md |
| **K27** column types: declared, else `unknown`, then observed, or the union | grid-model.md §2 |
| **K1** an unrun source's planned columns from its declared type (the rest of C5: a `TypedDict` return planning a `widen`) | features.md |
| **K29** reading an older version of a step warns, naming the step and version | features.md |

- **Decide:** nothing new (B-D1, page size, has a default).

### Step C. Identity and reproducibility (all but the seed ✓)

*Done 2026-10-27*: K20, K25, R3. Tests in `tests/unit/test_identity.py`.
`tool.hash`, in the catalog spec; `k.id`, `k.run_id`, `k.step(…).id`,
`k.diff(other)`; a step remembers the tool hash it ran with, and is `stale:
tool changed` when the catalog's differs (seen once outputs outlive a catalog:
step E's store, or a catalog swap). A resource type may define
`data_version()` (C-D1). `Secret[str]` settings are never saved, hashed or
shown. Left: the seed recommendation (C-D2).

| Feature | Designed in |
|---|---|
| **K20** tool hashes; `k.id`, `k.run_id`, `k.step(…).id`; `k.diff(other)`; a changed tool marks its steps stale | object-model.md §4.1, kernel-session.md |
| **K25** a resource reports a data version, which marks its users stale | object-model.md §4.2 |
| **R3** secret resource settings, left out of saves and hashes | kernel-session.md (`Secret[str]`) |
| a `seed` literal recommended for tools that aren't deterministic | features.md |

- **Decide:** K25 (C-D1), decided; the seed (C-D2).
- **Why now:** step D's sessions need versions and ids to say what is stale.

### Step D. Sessions

| Feature | Designed in |
|---|---|
| **K22** outputs kept by data version while a stale reader shows them | interactive-sessions.md |
| **K23, K14** progress per cell to a host callback, and `cancel()`: observing modifiers, saved, not hashed | grid-model.md §6 (decided 2026-10-26) |
| **K15** re-run only the failed rows | features.md |
| **R9** stages: consecutive steps run, checked and shown as one | object-model.md §4.11 |
| the autorun modifier | interactive-sessions.md §6.2: **still to be designed** |

- **Decide:** the autorun modifier's design (D-D1); the progress callback's
  shape (D-D2).

### Step E. Storage

| Feature | Designed in |
|---|---|
| **C32, K16** a pluggable output store: outputs saved beside the spec, so a reloaded kernel opens with its data | object-model.md §4.10, extensions.md |
| **R7** media handles: images and other objects saved as content-hashed references | features.md |

- **Decide:** the store's interface (E-D1).

### Step F. The workflow as a table

| Feature | Designed in |
|---|---|
| **G18** the workflow as a table of step blocks; a step's rows labelled with their reference; rows lined up across steps | features.md (decided 2026-10-27, to add later) |

- **Now unblocked:** rows line up through `#` columns, by the matching rule
  of reshaping.md §6.
- **Decide:** nothing new; the draft of 2026-10-27 is the starting point.

### Step G. Hand over to the app

Everything that changed for the app: reshaping-plan.md §7, plus what steps
A–F change. The app repo writes `core-handover/`. **Derived 2026-10-27 in
[app-migration.md](app-migration.md)**, which recommends moving the app now,
before D–F (G-D1): none of them blocks it, and each lands later as a small
additive pass.

## 4. Done means

Phase 4 is done when:

1. `scripts/core_asks.py` says **39 of 39**;
2. every feature in features.md is done, or moved to "Later, by decision";
3. the suite, and the property tests at `STRESS=1`, pass;
4. kernel-session.md, the working guide, shows what was built, and its
   example still runs as a test;
5. the app's changes are listed for the handover.

Then phase 5 (the final docs set) starts.

## 5. Decisions

| | Decision | Recommended | Step |
|---|---|---|---|
| A-D1 | **G5:** a fold with no `initial=` — **decided and built** 2026-10-27: it starts from `initial=` if given (a value or a reference), else a built-in's empty value, else its accumulator's type's (`acc: float` → `0.0`, `list` → `[]`); untyped or `X \| None` starts at `None`, and a failure there says to give `initial=`; a type with no empty value is refused when declared. Was: | start from the reducer's empty value when it has one (as R6 did for built-ins); otherwise refuse when declared: *"add(acc, n) has no starting value: give initial="*. Only when none is given: `initial=0`, or a reference (`initial=wf["s"][0][cols["value"]]`, even before `s` has run; it is read when the step runs) counts as given | A |
| A-D2 | **K18:** how `timeout` is enforced — **decided and built** 2026-10-27, as recommended. Was: | each call in a worker thread with a deadline; a call past it fails, `where: timeout`. A thread can't be stopped, so the call may finish in the background, and its result is dropped | A |
| B-D1 | K26's page size — **decided and built**, as recommended. Was: | 50 rows, as interactive-sessions.md suggests; the host can ask for another | B |
| C-D1 | **K25:** a resource reports its data version — **decided** 2026-10-27, as recommended: an optional method, for the few types that need it. Was: | a method, `data_version()`, called before a run; a setting can't change while the resource lives | C |
| C-D2 | **the seed recommendation:** how core knows a tool isn't deterministic, and what it says | a tool with a parameter named `seed` whose step doesn't give it warns: *"to_f takes seed: give seed= so a re-run gives the same values"*. Nothing else is guessed | C |
| D-D1 | **the autorun modifier** | design it before step D starts: triggers, chains, cost guards, pacing (interactive-sessions.md §6.2) | D |
| D-D2 | the progress callback | `k.run(…, observe=[progress(cb)])`, one call per cell: step, row id, state, as grid-model.md §6 has it | D |
| E-D1 | the output store's interface | `save(version, output)`, `load(version)`, `keep(versions)`: content-addressed by data version, so a store is a folder or a bucket | E |

Already decided and only to build: G8, G9, G12, G6, G7, K20, K22, K23, R9,
G18 (see the step tables).

Choices the owner wants to reconsider later (`auto`, modifiers that take data,
how references are passed, expand's ids, `#` in modifiers) are listed, with
what core does today, in [to-revisit.md](to-revisit.md).
