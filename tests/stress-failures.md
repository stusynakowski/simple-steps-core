# Property-test failures

Every failure of the property tests (`tests/unit/test_reshape_properties.py`),
appended by `tests/conftest.py` as it happens: what broke and the shrunk
example that shows it. An example already here isn't added twice. When one is
fixed, set its status to the commit that fixed it and pin the example
(`@example(...)`) so it's checked on every run.

## 2026-11-02 · `test_L40_reshaping_is_closed` · at `ea946d2` · STRESS=1

- **Broke:** A6 s6: planned columns ['#s0', '#s0_1', '#s0_2', 'k', 'value', 'n3'], got ['#s0', 'k', 'value', '#s0_1', '#s0_2', 'n3']: a sort of a `zip_` planned its `#` columns in front, the run kept them in place
- **Status:** fixed in `03ab207`, example pinned

```
test_L40_reshaping_is_closed(
    frame=Empty DataFrame
    Columns: [k, n, tags, rec]
    Index: [],
    chain=[(93, 0, 0, 0),
     (121, 0, 0, 0),
     (824, 38, 1, 0),
     (921, 0, 0, 0),
     (0, 0, 0, 0),
     (0, 65, 0, 0)],
)
```

## 2026-11-02 · `test_L40c_an_edit_then_a_rerun_matches_a_fresh_run` · at `03ab207` · STRESS=1

- **Broke:** edited: s2 op("count")[mod.collapse(by="#s1")](wf["s0"]) shape mismatch, (1, 3) vs (2, 3): after a source edit, a pick invalid for want of rows stayed invalid, and a collapse grouped by it completed anyway
- **Status:** fixed in `baec929`; covered by `test_an_edit_rechecks_everything_downstream_at_once` (tests/unit/test_grid.py)

```
test_L40c_an_edit_then_a_rerun_matches_a_fresh_run(
    frame=Empty DataFrame
    Columns: [k, n, tags, rec]
    Index: [],
    changed=   k     n  tags rec
    0  A  <NA>  None  {}
    1  A  <NA>  None  {},
    chain=[(993, 0, 0, 0), (811, 0, 0, 1)],
)
```

## 2026-11-03 · `test_L40_reshaping_is_closed` · at `718943b` · STRESS=1

- **Broke:** AttributeError: 'DataFrame' object has no attribute 'dtype': a self-join on lineage of a step that already had `n_left`/`n_right` columns merged `n_left_left`/`n_left_right` back into `n_left`, beside the `n_left` made from `n`; two columns with one name crashed the run
- **Status:** fixed (combines.py `_merge_shared` keeps a pair suffixed when the plain name is taken), example pinned

```
test_L40_reshaping_is_closed(
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],  # or any other generated value
chain=[(42, 0, 0, 0),
(139, 1, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(44, 2, 0, 2)],
)
```

## 2026-11-03 · `test_L40_reshaping_is_closed` · at `1a9f58e`

- **Broke:** TypeError: Workflow._first_param() takes 1 positional argument but 2 were given
- **Status:** my own mistake while removing `where=` (a `@staticmethod` cut with `_where_tests`), fixed before `aa84967` was committed; no core bug

```
test_L40_reshaping_is_closed(
frame=   k     n  tags rec
0  A  <NA>  None  {},
chain=[(428, 0, 0, 0)],
)
```

## 2026-11-03 · the ST8 laws, `test_L40d`–`test_L40f` · at `9113e89` · rewritten

The entries the conftest logged for these runs were lost (I reset this file
to fix an unrelated edit) and are rewritten here from the test output, one
per distinct failure. The four real bugs are pinned as examples on their
tests.

- **`test_L40d`, a pick turned invalid at run.** `s2 = wf["s1"][0]` on an
  empty source is refused when `s1` runs; `s4 = count[collapse(by="#s2")]`
  stayed `completed`, and was `invalid` only after an undo. Re-checks after
  a run followed only direct inputs. **Status:** fixed with ST8 (they
  follow `_depends_on`), example pinned:
  `chain=[(0, 0, 0, 0), (600, 1, 0, 0), (997, 0, 0, 0), (860, 0, 0, 552)]`, empty frames.
- **`test_L40d`, a pick re-checked against a blank plan.** After an undo,
  `s2`'s pick was re-checked before `s1`'s stored result came back, so it
  showed `staged`, not `invalid`. **Status:** fixed with ST8 (a restored
  result has its readers re-checked), example pinned:
  `chain=[(0, 0, 0, 0), (600, 1, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)]`, `which=0, other=1`, empty frames.
- **`test_L40d` at STRESS=1, planned types not compared.** A filter's type
  check on a collapse's planned types waited for an unrelated undo: the
  re-check after a run compared columns and row counts, not types.
  **Status:** fixed with ST8, example pinned:
  `chain=[(413, 0, 0, 0), (367, 1, 0, 0), (1, 3, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (73, 0, 0, 0)]`,
  a two-row frame, `changed` empty.
- **`test_L40e` at STRESS=1, stale or staged by order.** A step given a new
  expression showed its last result, stale, when the source changed first,
  and a blank plan when it changed second. **Status:** fixed with ST8 (no
  result for its key but earlier ones: the newest, stale), example pinned:
  `chain=[(0, 0, 0, 0), (257, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)]`, `which=1, other=142`.
- **The laws' own mistakes, fixed in the laws, no core change:** `test_L40d`
  compared the result object of a step that never held one
  (`chain=[(600, 0, 0, 0)]`); `test_L40f` ran an empty step
  (`chain=[(832, 0, 0, 0), (0, 0, 0, 0)]`) and saved its fresh kernel after
  the source became a DataFrame, which isn't saved; `test_L40e` copied a
  value step's expression, which is only "a source".
- **`test_L40_reshaping_is_closed` at `1a9f58e`:** `TypeError:
  Workflow._first_param() takes 1 positional argument but 2 were given`, my
  own mistake while removing `where=` (a `@staticmethod` cut with
  `_where_tests`), fixed before `aa84967` was committed. **Status:** no core bug.

## 2026-11-04 · `test_L40d_undo_is_free` · at `9113e89` · STRESS=1

- **Broke:** AssertionError: ('expression put back', 's5', 's5', 'completed', 'stale')
- **Status:** fixed with ST8: a run stamped the step a `collapse(by="#s")` groups by, but `run_key()` left it out, so the key a result was filed under was never found again; both are made of `_run_reads` now; example pinned

```
test_L40d_undo_is_free(
# The test always failed when commented parts were varied together.
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],  # or any other generated value
changed=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],  # or any other generated value
chain=[(0, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(419, 0, 0, 1),
(0, 0, 0, 0)],
which=600,
other=0,
)
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `9113e89` · STRESS=1

- **Broke:** RuntimeError: re-checking after 's1' doesn't settle: s3_r keep changing
- **Status:** fixed with ST8: re-checks after a run went both ways, so a step naming a later step (given another step's expression) and that later step re-checked each other forever; the run hung for 8 hours. They go forwards only now, and more rounds than steps raises, naming them, instead of hanging; example pinned

```
test_L40e_the_order_of_edits_doesnt_matter(
# The test always failed when commented parts were varied together.
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],  # or any other generated value
changed=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],  # or any other generated value
chain=[(0, 0, 0, 0), (0, 0, 0, 0), (186, 1, 0, 0), (0, 0, 0, 0)],
which=94,
other=495,
)
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `9113e89`

- **Broke:** RuntimeError: re-checking after 's1' doesn't settle: s3_r keep changing
- **Status:** fixed with ST8: re-checks after a run went both ways, so a step naming a later step (given another step's expression) and that later step re-checked each other forever; the run hung for 8 hours. They go forwards only now, and more rounds than steps raises, naming them, instead of hanging; example pinned

```
test_L40e_the_order_of_edits_doesnt_matter(
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
changed=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
chain=[(0, 0, 0, 0), (0, 0, 0, 0), (186, 1, 0, 0), (0, 0, 0, 0)],
which=94,
other=495,
)
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `9113e89` · STRESS=1

- **Broke:** AssertionError: ('order', 's2_p', 's2', 'invalid', 'staged')
- **Status:** fixed with ST8: assigning a value re-checked readers only where their problems changed, so a reader not yet run kept an old plan (columns unknown) and what read it wasn't re-decided; a value assigned now re-plans readers, as a run does (`_restage_after`); example pinned

```
test_L40e_the_order_of_edits_doesnt_matter(
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
changed=   k     n  tags rec
0  A  <NA>  None  {}
1  A  <NA>    []  {},
chain=[(2, 0, 0, 0), (556, 1, 0, 0), (212, 0, 0, 0), (0, 0, 0, 0)],
which=452,
other=166,
)
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `9113e89` · STRESS=1

- **Broke:** AssertionError: ('order', 's1', 's3', 'invalid', 'staged')
- **Status:** fixed with ST8: a step showing its newest earlier result (a new expression not run) didn't have its readers re-checked against what it shows, so one order checked them against it and the other against a blank plan; it does now, as a restored result does; example pinned

```
test_L40e_the_order_of_edits_doesnt_matter(
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
changed=   k     n  tags rec
0  A  <NA>  None  {},
chain=[(5, 0, 0, 0), (0, 0, 0, 0), (0, 1, 0, 0), (208, 0, 0, 0)],
which=1,
other=254,
)
```

## 2026-11-04 · `test_L40f_run_makes_a_step_current` · at `fdb0c53`

- **Broke:** AssertionError: ('s3', 's3_p', 'stale')
- **Status:** fixed in `090efdd`. With staleness no longer passed down, `run(x)` chose what to run before
  starting, so a step that turned stale once the step before it re-ran was missed; it now asks each
  step in turn

```
test_L40f_run_makes_a_step_current(
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
changed=   k     n  tags rec
0  A  <NA>  None  {},
chain=[(115, 0, 0, 0),
(0, 0, 0, 0),
(997, 1, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0)],
which=5,
)
```

## 2026-11-04 · `test_L40c_an_edit_then_a_rerun_matches_a_fresh_run` · at `af0348e`

- **Broke:** AssertionError: edited: s1 mod.sort(by="k")(wf["s0"]).index are different
- **Status:** open

```
test_L40c_an_edit_then_a_rerun_matches_a_fresh_run(
frame=   k     n  tags rec
0  A  <NA>  None  {},
changed=   k     n tags rec
0  A  <NA>   []  {},
chain=[(0, 0, 0, 0)],
)
```

## 2026-11-04 · `test_L40f_run_makes_a_step_current` · at `af0348e`

- **Broke:** AssertionError: run(s0) <DataFrame 1×4>.index are different
- **Status:** open

```
test_L40f_run_makes_a_step_current(
# The test sometimes passed when commented parts were varied together.
frame=   k     n  tags rec
0  A  <NA>  None  {},
changed=   k     n tags rec
0  A  <NA>   []  {},
chain=[(0, 0, 0, 0)],  # or any other generated value
which=0,  # or any other generated value
)
```

## 2026-11-04 · `test_L40c_an_edit_then_a_rerun_matches_a_fresh_run` · at `af0348e`

- **Broke:** AssertionError: edited: s1 mod.sort(by="k")(wf["s0"]).index are different
- **Status:** open

```
test_L40c_an_edit_then_a_rerun_matches_a_fresh_run(
frame=   k     n  tags rec
0  A  <NA>  None  {},
changed=   k     n  tags rec
0  A  <NA>    []  {}
1  A  <NA>  None  {},
chain=[(0, 0, 0, 0)],
)
```

## 2026-11-04 · `test_L40d_undo_is_free` · at `af0348e`

- **Broke:** AssertionError: ('source put back', 's1', 'completed', 'invalid')
- **Status:** open

```
test_L40d_undo_is_free(
# The test always failed when commented parts were varied together.
frame=   k     n  tags rec
0  A  <NA>  None  {},
changed=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
chain=[(162, 0, 0, 0)],
which=0,  # or any other generated value
other=0,  # or any other generated value
)
```

## 2026-11-04 · `test_L40f_run_makes_a_step_current` · at `af0348e`

- **Broke:** AssertionError: run(s0) <DataFrame 2×4>.index are different
- **Status:** open

```
test_L40f_run_makes_a_step_current(
# The test sometimes passed when commented parts were varied together.
frame=   k     n  tags          rec
0  A  <NA>  None  {'a': None},
changed=   k     n  tags rec
0  A  <NA>  None  {}
1  A  <NA>  None  {},
chain=[(0, 0, 0, 0)],  # or any other generated value
which=0,  # or any other generated value
)
```

## 2026-11-04 · `test_L40d_undo_is_free` · at `af0348e`

- **Broke:** AssertionError: ('source put back', 's1', 'completed', 'invalid')
- **Status:** open

```
test_L40d_undo_is_free(
frame=   k     n  tags rec
0  A  <NA>  None  {},
changed=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
chain=[(162, 0, 0, 0)],
which=0,
other=0,
)
```

## 2026-11-04 · `test_L40f_run_makes_a_step_current` · at `af0348e`

- **Broke:** AssertionError: run(s0) <DataFrame 2×4>.index are different
- **Status:** open

```
test_L40f_run_makes_a_step_current(
frame=   k     n  tags          rec
0  A  <NA>  None  {'a': None},
changed=   k     n  tags rec
0  A  <NA>  None  {}
1  A  <NA>  None  {},
chain=[(0, 0, 0, 0)],
which=0,
)
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `af0348e`

- **Broke:** AssertionError: ('order', 's1_p', 's1_p', 'stale', 'invalid')
- **Status:** open

```
test_L40e_the_order_of_edits_doesnt_matter(
frame=   k     n  tags          rec
0  A  <NA>  None  {'a': None},
changed=   k     n  tags rec
0  A  <NA>  None  {}
1  A  <NA>  None  {},
chain=[(164, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(61, 0, 0, 0),
(0, 0, 0, 0)],
which=1,
other=47,
)
```

## 2026-11-04 · `test_L40c_an_edit_then_a_rerun_matches_a_fresh_run` · at `af0348e`

- **Broke:** AssertionError: edited: s1 mod.distinct(columns=["k"])(wf["s0"]).iloc[:, 0] (column name="#s0") are different
- **Status:** open

```
test_L40c_an_edit_then_a_rerun_matches_a_fresh_run(
frame=   k     n  tags rec
0  A  <NA>  None  {},
changed=   k     n  tags          rec
0  A  <NA>  None  {'a': None}
1  A  <NA>  None           {},
chain=[(205, 0, 0, 0)],
)
```
