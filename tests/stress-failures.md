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
- **Status:** fixed in `3e01a8e` (D-picks): a source keeps its row ids across an edit, by design; the law compares what is shown (values, lineage as row numbers), not ids (decisions W5)

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
- **Status:** fixed in `3e01a8e` (D-picks): a source keeps its row ids across an edit, by design; the law compares what is shown (values, lineage as row numbers), not ids (decisions W5)

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
- **Status:** fixed in `3e01a8e` (D-picks): a source keeps its row ids across an edit, by design; the law compares what is shown (values, lineage as row numbers), not ids (decisions W5)

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
- **Status:** fixed in `3e01a8e` (D-picks): a source remembers every row it has seen, so a row given back gets its id back and a gone pick follows it again (W4)

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
- **Status:** fixed in `3e01a8e` (D-picks): a source keeps its row ids across an edit, by design; the law compares what is shown (values, lineage as row numbers), not ids (decisions W5)

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
- **Status:** fixed in `3e01a8e` (D-picks): a source remembers every row it has seen, so a row given back gets its id back and a gone pick follows it again (W4)

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
- **Status:** fixed in `3e01a8e` (D-picks): a source keeps its row ids across an edit, by design; the law compares what is shown (values, lineage as row numbers), not ids (decisions W5)

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
- **Status:** fixed in `3e01a8e` (D-picks): a pick written before a data change follows its row, after it is read on the new data; the two orders hold different workflows, which the law doesn't compare (W5)

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
- **Status:** fixed in `3e01a8e` (D-picks): `#` columns hold ids; the law compares them as lineage, row numbers (W5)

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

## 2026-11-04 · `test_L40d_undo_is_free` · at `a9c7c54`

- **Broke:** see the test output
- **Status:** fixed (D-picks, follow-up): a source put back by its tool came back from the store, and a pick the edit had rewritten stayed rewritten. Picks now follow a source's rows however they change (data assigned, its tool run again, a result from the store); the example is pinned in L40d

```
no example printed
```

## 2026-11-04 · `test_L40d_undo_is_free` · at `a9c7c54`

- **Broke:** see the test output
- **Status:** fixed (D-picks, follow-up): a source put back by its tool came back from the store, and a pick the edit had rewritten stayed rewritten. Picks now follow a source's rows however they change (data assigned, its tool run again, a result from the store); the example is pinned in L40d

```
no example printed
```

## 2026-11-04 · `test_L40d_undo_is_free` · at `a9c7c54`

- **Broke:** AssertionError: ('source put back', 's3', 'completed', 'invalid')
- **Status:** fixed (D-picks): picks now follow a source's rows when its result comes back from the store; pinned in L40d

```
test_L40d_undo_is_free(
frame=   k     n       tags                     rec
0  A  <NA>       None  {'a': None, 'b': None}
1  A  <NA>       None     {'a': None, 'b': 4}
2  A  <NA>       None     {'b': 5, 'a': None}
3  C  <NA>       None                      {}
4  A  <NA>  [2, 3, 0]                {'a': 6},
changed=   k     n    tags          rec
0  C  <NA>    None           {}
1  C  <NA>  [0, 4]     {'a': 8}
2  A  <NA>    None  {'a': None}
3  B    -1     [3]  {'a': None}
4  B     0    None  {'b': None},
chain=[(187, 77, 160, 20),
(938, 248, 373, 250),
(307, 413, 500, 644),
(121, 565, 323, 665),
(416, 99, 843, 352),
(275, 238, 98, 281)],
which=126,
other=86,
)
```

## 2026-11-04 · `test_L40d_undo_is_free` · at `a9c7c54` · STRESS=1

- **Broke:** AssertionError: ('source put back', 's1', 'completed', 'invalid')
- **Status:** fixed (D-picks): a condition someone wrote on row numbers tests positions, and isn't rewritten as a pick; pinned in L40d (W2)

```
test_L40d_undo_is_free(
# The test always failed when commented parts were varied together.
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
changed=   k     n  tags rec
0  A  <NA>  None  {},
chain=[(309, 0, 0, 0)],
which=0,  # or any other generated value
other=0,  # or any other generated value
)
```

## 2026-11-04 · `test_L40d_undo_is_free` · at `a9c7c54`

- **Broke:** AssertionError: ('source put back', 's1', 'completed', 'invalid')
- **Status:** fixed (D-picks): new data with an index of its own, put back by its tool: core's ids and the user's labels can't be compared, so picks stay as written (W3); pinned in L40d

```
test_L40d_undo_is_free(
# The test always failed when commented parts were varied together.
frame=   k     n  tags rec
0  A  <NA>  None  {},
changed=   k     n  tags rec
a  A  <NA>  None  {},
chain=[(649, 0, 0, 0)],
which=0,  # or any other generated value
other=0,  # or any other generated value
)
```

## 2026-11-04 · `test_L40d_undo_is_free` · at `a9c7c54` · STRESS=1

- **Broke:** AssertionError: ('source put back', 's1', 'completed', 'invalid')
- **Status:** fixed (D-picks): new data with an index of its own, put back by its tool: core's ids and the user's labels can't be compared, so picks stay as written (W3); pinned in L40d

```
test_L40d_undo_is_free(
frame=   k     n  tags rec
0  A  <NA>  None  {},
changed=   k     n  tags rec
a  A  <NA>  None  {},
chain=[(649, 0, 0, 0)],
which=0,
other=0,
)
```

## 2026-11-04 · `test_L40d_undo_is_free` · at `c4d6c7e`

- **Broke:** RecursionError: maximum recursion depth exceeded
- **Status:** fixed (D9): a step re-declared to read itself was planned for its name before its problems were seen, planning itself forever; a step with problems is planned as invalid first. Pinned in L40d

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
(5, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0)],
which=0,
other=2,
)
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `c4d6c7e`

- **Broke:** see the test output
- **Status:** found in the same run as the RecursionError above, during D9; passes since that fix, and at 500 examples

```
no example printed
```

## 2026-11-04 · `test_L40d_undo_is_free` · at `c4d6c7e`

- **Broke:** RecursionError: maximum recursion depth exceeded
- **Status:** fixed (D9): a step re-declared to read itself was planned for its name before its problems were seen, planning itself forever; a step with problems is planned as invalid first. Pinned in L40d

```
test_L40d_undo_is_free(
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
changed=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
chain=[(0, 0, 0, 0),
(5, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0)],
which=0,
other=2,
)
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `c4d6c7e`

- **Broke:** see the test output
- **Status:** found in the same run as the RecursionError above, during D9; passes since that fix, and at 500 examples

```
no example printed
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `a99c748`

- **Broke:** AssertionError: ('order', 's1', 's2', 'invalid', 'completed')
- **Status:** fixed (D-picks): a step whose picks a source's change touched is checked again directly, since it may no longer read the source; pinned in L40e

```
test_L40e_the_order_of_edits_doesnt_matter(
frame=   k     n  tags rec
0  A  <NA>  None  {}
1  A  <NA>  None  {},
changed=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],
chain=[(0, 0, 0, 0), (257, 1, 0, 0)],
which=1,
other=0,
)
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `a99c748` · STRESS=1

- **Broke:** AssertionError: ('order', 's1_r', 's1_r', 'stale', 'invalid')
- **Status:** fixed (S3): a binding core writes is an unbound reference, as `wf[…]` is, not one pinned to the workflow it was written in; pinned in L40e

```
test_L40e_the_order_of_edits_doesnt_matter(
# The test always failed when commented parts were varied together.
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],  # or any other generated value
changed=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],  # or any other generated value
chain=[(186, 0, 0, 0), (164, 0, 0, 0), (155, 1, 0, 0)],
which=16,
other=48,
)
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `6b23bf4`

- **Broke:** ValueError: cannot order ['s3_p', 's3_r', 's3']: something reads a step that never runs
- **Status:** fixed: an intermediate state of the run_all change, which kept invalid steps waiting forever; steps still invalid when nothing else can run are now left reporting their problems

```
no example printed
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `6b23bf4`

- **Broke:** ValueError: cannot order ['s3_p', 's3_r', 's3']: something reads a step that never runs
- **Status:** fixed: an intermediate state of the run_all change, which kept invalid steps waiting forever; steps still invalid when nothing else can run are now left reporting their problems

```
no example printed
```

## 2026-11-04 · `test_L40c_an_edit_then_a_rerun_matches_a_fresh_run` · at `004eb32` · STRESS=2000

- **Broke:** AssertionError: ('edited', 's3', 'lineage'), and s3's `rec` differed (found by the final 2,000-example run, in a clean copy of HEAD)
- **Status:** fixed: `run_all` chose its steps from those valid when it started, so a step invalid then (its input still showing its old rows) never ran after that input re-ran; now each step is asked when it's reached, and steps still invalid when nothing else can run are left reporting their problems. Pinned in L40c

```
test_L40c_an_edit_then_a_rerun_matches_a_fresh_run(
frame=   k     n  tags rec
0  A  <NA>  None  {},
changed=   k     n  tags rec
a  A  <NA>  None  {},
chain=[(0, 0, 0, 0), (698, 1, 0, 0), (0, 32, 0, 0)],
)
```

## 2026-11-04 · `test_L40e_the_order_of_edits_doesnt_matter` · at `6b23bf4` · STRESS=1

- **Broke:** RecursionError: maximum recursion depth exceeded
- **Status:** fixed: run_all now asks every step, and pending() went round a step that reads itself forever; it skips a step it has visited. Pinned in L40e

```
test_L40e_the_order_of_edits_doesnt_matter(
# The test always failed when commented parts were varied together.
frame=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],  # or any other generated value
changed=Empty DataFrame
Columns: [k, n, tags, rec]
Index: [],  # or any other generated value
chain=[(262, 0, 0, 0),
(0, 1, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(0, 0, 0, 0),
(0, 220, 0, 0)],
which=3,
other=7,
)
```

## 2026-11-04 · `test_L40f_run_makes_a_step_current` · at `2c8944d` · STRESS=1

- **Broke:** AssertionError: run(s3): s3 op("gather")[mod.collapse()](wf["s1"]) are different
- **Status:** fixed: a widen's per-row stamps listed the columns it carries, not the dict column it spreads, so a cell gaining a key left it completed (a silent wrong answer, older than tonight); a pack had the same gap. Both now count the columns they consume. Pinned in L40f

```
test_L40f_run_makes_a_step_current(
frame=   k     n  tags rec
0  A  <NA>  None  {}
1  A  <NA>  None  {}
2  A  <NA>  None  {}
3  A  <NA>  None  {},
changed=   k     n  tags          rec
0  A  <NA>  None           {}
1  A  <NA>  None           {}
2  A  <NA>  None           {}
3  A  <NA>  None  {'a': None},
chain=[(519, 0, 0, 0), (0, 0, 0, 0), (561, 2, 0, 0)],
which=124,
)
```

## 2026-11-09 · `test_L40d_undo_is_free` · at `a1ad7f5` · STRESS=1

- **Broke:** AssertionError: ('source put back', 's4', 'completed', 'invalid')
- **Status:** open

```
test_L40d_undo_is_free(
# The test always failed when commented parts were varied together.
frame=   k     n  tags rec
0  B  <NA>  None  {}
1  A  <NA>  None  {},
changed=   k     n  tags rec
0  A  <NA>  None  {},
chain=[(0, 0, 0, 0), (2, 0, 0, 0), (42, 224, 0, 0), (993, 3, 0, 0)],
which=0,  # or any other generated value
other=0,  # or any other generated value
)
```

## 2026-11-09 · `test_L40d_undo_is_free` · at `a1ad7f5` + the EX6 piece · STRESS=1

- **Broke:** AssertionError: ('source put back', 's4', 'completed', 'invalid')
- **Status:** open, **W9**; older than the day's work (the same on `78c35ef`, `01f6279`, `a1ad7f5`). `s4 = wf["s3"][[0, -1]]` on a join of `s2` (a pick of `s0`) and `s0` is saved as lineage on both parents. An edit that drops `s0`'s row 0 rewrites `row["s0"]`'s numbers but not `row["s2"]`'s (a derived step's, W9), so both picked rows end up naming `s0` row 0; putting the source back can't tell them apart, and `s4` stays `invalid`. Needs each step's row map (PL2, L6). Not pinned: pinning an open bug fails the suite.

```
test_L40d_undo_is_free(
frame=   k     n  tags rec
0  B  <NA>  None  {}
1  A  <NA>  None  {},
changed=   k     n  tags rec
0  A  <NA>  None  {},
chain=[(0, 0, 0, 0), (2, 0, 0, 0), (42, 224, 0, 0), (993, 3, 0, 0)],
which=0,
other=0,
)
```

## Hangs: where they are recorded (2026-11-09)

- **Seen:** `sweep.py --stress` ran 361 CPU minutes (2026-11-04, under coverage),
  and three runs on 2026-11-09 went past 10 CPU minutes (a full test run at
  `a1ad7f5` + the EX6 piece, and two `STRESS=1` property runs, one of them while
  hypothesis shrank the W9 failure above). Each was killed before its stacks
  could be read: the 2026-11-09 ones had their output piped into
  `grep`/`head`/`tail`, the sweep held its output in memory.
- **Not reproduced:** five `STRESS=1` runs writing to files (2026-11-09, at
  `0c49e18`) passed in 130–167 s, with no test past 200 s.
- **Now recorded:** `faulthandler_timeout = 600` (pyproject.toml) makes any test
  past 10 minutes dump every thread's stack, without stopping it; `sweep.py`
  writes each suite's output to `.sweep/<suite>.log` as it runs. A hang's
  location is in that log (or the file a run is redirected to): add it here,
  with the commit, before killing the run. Don't pipe a long run into `head`.
