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
- **Status:** open

```
test_L40_reshaping_is_closed(
frame=   k     n  tags rec
0  A  <NA>  None  {},
chain=[(428, 0, 0, 0)],
)
```
