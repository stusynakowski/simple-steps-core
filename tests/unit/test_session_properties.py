"""Property tests for sessions: saving, the disk store, running, stages.

The laws, over generated workflows (test_reshape_properties' grids and chains:
every move, gaps, lists, dicts, odd indexes) and generated values:

- S1  a workflow saved with its outputs and loaded shows the same: every
      step's state, data version and view; and needs nothing run;
- S2  a workflow whose source is data (a DataFrame) saves it exactly;
- S3  a second run_all runs nothing: every output is the very same object;
- S4  every value the tagged form takes comes back exactly, type and all;
- S5  every generated table is written and read back exactly;
- S6  bulky values on disk or in memory give the same versions, states and
      values, at any threshold, saved and loaded too;
- S7  stages stay consecutive, in order, apart and naming real steps, through
      any sequence of inserts, moves, renames and deletes.

``STRESS=1`` runs 500 examples, ``STRESS=<n>`` n, as test_reshape_properties.
"""

import datetime as dt
import decimal
import math
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from test_reshape_properties import (  # noqa: E402  (a sibling: same generators)
    EXAMPLES, _build, _catalog, _run, _timed, chains, grids,
)

from simple_steps_core import Catalog, Kernel, MediaHandle, mod, tool, wf
from simple_steps_core.output import _data_version
from simple_steps_core.saving import read_frame, tag, untag, write_frame

SETTINGS = settings(max_examples=EXAMPLES, deadline=None,
                    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large,
                                           HealthCheck.function_scoped_fixture])


def _session(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def _shown(k: Kernel, name: str):
    """What a step shows, comparable: its state, data version and view."""
    step = k.workflow.steps[name]
    view = k.view(name) if step.state != "invalid" else None
    return step.state, step.output.meta.get("version"), _plainview(view)


def _plainview(view):
    if view is None:
        return None
    return {key: value for key, value in view.items() if key not in ("summary",)}


# ── S1, S2: saved and loaded, the same ──────────────────────────────────────
@pytest.mark.no_invariants
@SETTINGS
@given(grids(), chains())
# a column of {} typed as an Arrow struct of no fields, which Parquet can't
# write: the save raised (found 2026-11-17 at 100 examples)
@example(frame=pd.DataFrame({"k": ["A"], "n": pd.array([pd.NA], dtype="Int64"),
                             "tags": [None], "rec": [{}]}), chain=[(0, 0, 0, 0)])
@_timed
def test_S1_a_saved_session_loads_showing_the_same(frame, chain):
    catalog = _catalog(frame)
    k, names = _build(catalog, chain)
    _run(k)
    folder = _session("s1-")
    k.save(folder, outputs=True)
    back = Kernel.load(folder, catalog)
    for name in names:
        if name in k.workflow.steps:
            assert _shown(back, name) == _shown(k, name), (name, k.workflow.steps[name].formula)
    assert back.needs_run() == k.needs_run()


@pytest.mark.no_invariants
@SETTINGS
@given(grids(), chains())
@_timed
def test_S2_a_data_source_saves_exactly_and_its_readers_follow(frame, chain):
    catalog = _catalog(frame)
    k, names = _build(catalog, chain)
    k["s0"] = frame.copy()                         # the source as data, not a tool
    _run(k)
    folder = _session("s2-")
    report = k.save(folder, outputs=True)
    assert report["steps"]["s0"].get("not_saved") is None, report["steps"]["s0"]
    back = Kernel.load(folder, catalog)
    assert _data_version(back.step("s0").literal) == _data_version(frame)
    for name in names:
        if name in k.workflow.steps:
            assert _shown(back, name) == _shown(k, name), (name, k.workflow.steps[name].formula)


# ── S3: running what's needed ───────────────────────────────────────────────
@pytest.mark.no_invariants
@SETTINGS
@given(grids(), chains())
@_timed
def test_S3_a_second_run_all_runs_nothing(frame, chain):
    k, names = _build(_catalog(frame), chain)
    _run(k)
    before = {n: k.workflow.steps[n].output for n in k.workflow.steps}
    needs = k.needs_run()
    _run(k)
    for name, output in before.items():
        if name not in needs:                      # current: left as it was
            assert k.workflow.steps[name].output is output, (name, k.workflow.steps[name].formula)


# ── S4, S5: values and tables, exactly ──────────────────────────────────────
def _canon(value):
    """A value as plain data that differs whenever the value or a type in it
    does: independent of the tagged form it checks."""
    kind = type(value).__name__
    if isinstance(value, float):
        return [kind, "nan" if math.isnan(value) else repr(value)]
    if isinstance(value, (list, tuple)):
        return [kind, [_canon(v) for v in value]]
    if isinstance(value, (set, frozenset)):
        return [kind, sorted((_canon(v) for v in value), key=repr)]
    if isinstance(value, dict):
        return [kind, [[_canon(k), _canon(v)] for k, v in value.items()]]
    if isinstance(value, np.generic):
        return [kind, str(value.dtype), _canon(value.item())]
    if isinstance(value, (bytes, bytearray)):
        return [kind, value.hex()]
    return [kind, repr(value)]


scalars = st.one_of(
    st.none(), st.booleans(), st.integers(), st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=8), st.binary(max_size=8),
    st.decimals(allow_nan=False, allow_infinity=False, places=3),
    st.datetimes(timezones=st.sampled_from([None, dt.timezone.utc])), st.dates(),
    st.timedeltas(), st.complex_numbers(allow_nan=False, allow_infinity=False),
    st.integers(-128, 127).map(np.int8), st.floats(width=32, allow_nan=False).map(np.float32),
)
hashables = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=5),
                      st.tuples(st.integers(), st.text(max_size=3)))
values = st.recursive(scalars, lambda inner: st.one_of(
    st.lists(inner, max_size=4), st.tuples(inner, inner),
    st.dictionaries(hashables, inner, max_size=4),
    st.frozensets(hashables, max_size=3)), max_leaves=12)


@SETTINGS
@given(values)
# isoformat drops fold, the second of a repeated hour (found 2026-11-17)
@example(value=dt.datetime(2000, 1, 1, fold=1))
@example(value=dt.time(1, 30, fold=1))
def test_S4_every_value_comes_back_exactly(value):
    import json
    assert _canon(untag(json.loads(json.dumps(tag(value))))) == _canon(value)


@st.composite
def tables(draw):
    n = draw(st.integers(0, 6))
    columns = {}
    for c in range(draw(st.integers(1, 4))):
        kind = draw(st.sampled_from(["int", "Int64", "float", "str", "bool", "object", "when"]))
        if kind == "int":
            col = pd.Series(draw(st.lists(st.integers(-10**12, 10**12), min_size=n, max_size=n)),
                            dtype="int64")
        elif kind == "Int64":
            col = pd.array(draw(st.lists(st.one_of(st.none(), st.integers(-9, 9)),
                                         min_size=n, max_size=n)), dtype="Int64")
        elif kind == "float":
            col = pd.Series(draw(st.lists(st.floats(allow_nan=True), min_size=n, max_size=n)),
                            dtype="float64")
        elif kind == "str":
            col = pd.Series(draw(st.lists(st.text(max_size=6), min_size=n, max_size=n)))
        elif kind == "bool":
            col = pd.Series(draw(st.lists(st.booleans(), min_size=n, max_size=n)), dtype=bool)
        elif kind == "when":
            col = pd.Series(pd.to_datetime(draw(st.lists(
                st.datetimes(min_value=dt.datetime(1900, 1, 1), max_value=dt.datetime(2200, 1, 1)),
                min_size=n, max_size=n))))
        else:
            col = pd.Series(draw(st.lists(values, min_size=n, max_size=n)), dtype=object)
        name = draw(st.one_of(st.text(min_size=1, max_size=5), st.integers(0, 99)))
        columns[name] = col
    frame = pd.DataFrame(columns)
    if n and draw(st.booleans()):
        frame.index = draw(st.lists(st.one_of(st.integers(-99, 99), st.text(max_size=4)),
                                    min_size=n, max_size=n, unique=True))
    return frame


@SETTINGS
@given(tables())
@example(frame=pd.DataFrame({0: pd.Series([dt.datetime(2000, 1, 1, fold=1)], dtype=object)}))
# bytes that aren't text beside a bool: the data version itself raised
# (UnicodeDecodeError), so any step holding such bytes would (found 2026-11-17)
@example(frame=pd.DataFrame({0: pd.Series([False, b"\x80"], dtype=object)}))
def test_S5_every_table_is_written_and_read_back_exactly(frame):
    path = _session("s5-") / "t.parquet"
    manifest = write_frame(frame, path)
    if "not_saved" in manifest:                     # only what can't be: said, never silent
        assert manifest["not_saved"]
        return
    back = read_frame(path, manifest)
    assert list(map(str, back.dtypes)) == list(map(str, frame.dtypes))
    assert _data_version(back) == _data_version(frame)
    for position in range(frame.shape[1]):
        assert [_canon(v) for v in back.iloc[:, position]] == \
            [_canon(v) for v in frame.iloc[:, position]], frame.columns[position]
    assert [_canon(v) for v in back.index] == [_canon(v) for v in frame.index]


# ── S6: bulky values, on disk or in memory, the same ────────────────────────
@tool
def picture(n: int) -> object:
    from PIL import Image
    side = 4 + abs(n) % 13
    return Image.fromarray(np.full((side, side, 3), abs(n) % 256, dtype=np.uint8))


@tool
def matrix(picture: object) -> np.ndarray:
    return np.asarray(picture).astype(np.float32) / 255


@tool
def level(matrix: np.ndarray) -> float:
    return round(float(matrix.mean()), 6)


@tool
def bright(level: float) -> bool:
    return level > 0.4


@tool
def figure(n: int) -> object:
    import plotly.graph_objects as go
    return go.Figure(go.Bar(y=np.arange(abs(n) % 9 + 1, dtype=float)))


MEDIA = Catalog(tools=[picture, matrix, level, bright, figure])


def _media_workflow(numbers, spill_over, store=None):
    k = Kernel(MEDIA, spill_over=spill_over, store=store)
    k["s"] = pd.DataFrame({"n": numbers})
    k["picture"] = picture[mod.map()](wf["s"])
    k["matrix"] = matrix[mod.map()](wf["picture"])
    k["level"] = level[mod.map()](wf["matrix"])
    k["kept"] = bright[mod.filter()](wf["level"])
    k["fig"] = figure[mod.map()](wf["s"])
    k.run_all()
    return k


@pytest.mark.no_invariants
@SETTINGS
@given(st.lists(st.integers(-300, 300), min_size=0, max_size=6),
       st.integers(0, 3000), st.booleans())
# loaded with its arrays on disk, a reader's type check saw a MediaHandle,
# not an ndarray, and the step was invalid (found 2026-11-17)
@example(numbers=[0], spill_over=0, through_a_save=True)
@_timed
def test_S6_on_disk_or_in_memory_the_same(numbers, spill_over, through_a_save):
    in_memory = _media_workflow(numbers, None)
    on_disk = _media_workflow(numbers, spill_over, _session("s6-store-"))
    if through_a_save:
        folder = _session("s6-")
        on_disk.save(folder, outputs=True)
        on_disk = Kernel.load(folder, MEDIA, spill_over=spill_over)
        assert on_disk.needs_run() == {}
    for name in in_memory.workflow.steps:
        a, b = in_memory.workflow.steps[name], on_disk.workflow.steps[name]
        assert (a.state, a.output.meta.get("version")) == (b.state, b.output.meta.get("version")), name
        assert _data_version(a.output.data) == _data_version(b.output.data), name
        for column in a.output.data.columns:
            for row in range(len(a.output.data)):
                x, y = in_memory.value(name, row, column), on_disk.value(name, row, column)
                assert not isinstance(y, MediaHandle)
                assert _data_version(pd.DataFrame({"c": [x]})) == _data_version(pd.DataFrame({"c": [y]}))
    # an edit, on both: the same rows go stale, and a run brings both back level
    if numbers:
        changed = list(numbers)
        changed[-1] += 1
        for k in (in_memory, on_disk):
            k["s"] = pd.DataFrame({"n": changed})
            k.run_all()
        for name in in_memory.workflow.steps:
            assert in_memory.workflow.steps[name].output.meta.get("version") == \
                on_disk.workflow.steps[name].output.meta.get("version"), name


# ── S7: stages through any edits ────────────────────────────────────────────
@tool
def plus(n: int) -> int:
    return n + 1


EDITS = st.lists(st.tuples(st.sampled_from(["insert", "move", "rename", "remove", "stage",
                                            "unstage", "append"]),
                           st.integers(0, 50), st.integers(0, 50)), max_size=12)


def _check_stages(k: Kernel) -> None:
    order = list(k.workflow.steps)
    seen = set()
    for name, steps in k.stages.items():
        assert steps, name
        assert all(s in k.workflow.steps for s in steps), (name, steps)
        positions = [order.index(s) for s in steps]
        assert positions == list(range(positions[0], positions[0] + len(steps))), (name, steps, order)
        assert not seen & set(steps), (name, steps)
        seen |= set(steps)


@pytest.mark.no_invariants
@SETTINGS
@given(st.integers(2, 6), EDITS)
def test_S7_stages_stay_consecutive_and_apart_through_any_edits(length, edits):
    k = Kernel(Catalog(tools=[plus]))
    for i in range(length):
        k[f"v{i}"] = pd.DataFrame({"n": [i]})       # independent: any order is valid
    count = length
    for what, a, b in edits:
        names = list(k.workflow.steps)
        if not names:
            break
        try:
            if what == "insert":
                k.insert(a % (len(names) + 1), f"v{count}", pd.DataFrame({"n": [count]}))
                count += 1
            elif what == "append":
                k[f"v{count}"] = pd.DataFrame({"n": [count]})
                count += 1
            elif what == "move":
                k.move(names[a % len(names)], b % len(names))
            elif what == "rename":
                k.rename(names[a % len(names)], f"r{count}")
                count += 1
            elif what == "remove":
                k.remove(names[a % len(names)], force=True)
            elif what == "stage":
                first, last = sorted((a % len(names), b % len(names)))
                k.stage(f"g{a % 3}", first=names[first], last=names[last])
            elif what == "unstage" and k.stages:
                k.unstage(list(k.stages)[a % len(k.stages)])
        except ValueError:
            pass                                     # an overlap refused: allowed
        _check_stages(k)
    back = Kernel.from_json(k.to_json(), k.catalog)
    assert back.stages == k.stages


# ── S8: a page is the full view, cut (the app's 014 C50) ────────────────────
@pytest.mark.no_invariants
@SETTINGS
@given(grids(), chains(), st.integers(-8, 8), st.integers(-2, 10), st.integers(-6, 6))
# a collapse group with no rows: its cell's recipe wrote an empty row pick,
# which raised (found 2026-11-20 at 500 examples, with run_cell)
@example(frame=pd.DataFrame({"k": ["A"] * 3, "n": pd.array([pd.NA] * 3, dtype="Int64"),
                             "tags": [None] * 3, "rec": [{}] * 3}),
         chain=[(0, 0, 0, 0), (1, 0, 0, 0), (272, 2, 0, 0)], start=0, size=0, row=0)
@_timed
def test_S8_a_page_and_a_cell_are_the_full_view_cut(frame, chain, start, size, row):
    k, names = _build(_catalog(frame), chain)
    _run(k)
    for name in names:
        if name not in k.workflow.steps:
            continue
        full = k.view(name, None)
        page = k.view(name, (start, start + size))
        assert page["rows"] == full["rows"][start:start + size], (name, start, size)
        if full["state"] == "invalid" or not full["columns"]:
            continue
        column = full["columns"][0]["name"]
        cell = k.cell(name, row, column)
        if -len(full["rows"]) <= row < len(full["rows"]):
            entry = full["rows"][row]
            expected = entry["cells"].get(column, {"state": entry["state"]})
            assert {key: cell[key] for key in expected} == expected, (name, row)
            assert cell["lineage"] == entry["lineage"], (name, row)
