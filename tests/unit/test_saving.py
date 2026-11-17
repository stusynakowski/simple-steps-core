"""Saving a session as a folder, and loading it back (plan P1c; saving.md).

Layer 1: the workflow and the data entered into its steps. A DataFrame
assigned to a step was dropped by ``to_json``, and ``run_all`` then raised
(found 2026-11-16). Now it is saved as ``data/<step>.parquet``, each column
written the plainest way that reads back exactly, checked by data version;
what can't be saved is reported, and loads as an ``invalid`` step, never a
raise.
"""

import datetime as dt
import decimal
import json

import numpy as np
import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, tool, wf
from simple_steps_core.output import _data_version


@tool
def dbl(n: int) -> int:
    return 2 * n


CAT = Catalog(tools=[dbl])


def _roundtrip(tmp_path, frame, name="s"):
    k = Kernel(CAT)
    k[name] = frame
    report = k.save(tmp_path / "session")
    loaded = Kernel.load(tmp_path / "session", CAT)
    return k, loaded, report


def test_a_dataframe_step_is_saved_and_loads_back_the_same(tmp_path):
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2, 3], "name": ["Ada", "Ben", "Cy"]})
    k["t"] = dbl[mod.map()](wf["s"])
    k.run_all()
    report = k.save(tmp_path / "session")
    assert report["exact"] is True
    assert (tmp_path / "session" / "workflow.json").exists()
    assert (tmp_path / "session" / "data" / "s" / "table.parquet").exists()

    loaded = Kernel.load(tmp_path / "session", CAT)
    assert loaded.step("s").state == "completed"
    assert _data_version(loaded.step("s").output.data) == _data_version(k.step("s").output.data)
    loaded.run_all()
    assert loaded.step("t").output.data["t"].tolist() == [2, 4, 6]


@pytest.mark.parametrize("column", [
    pytest.param([1, None, 3], id="ints with a gap"),
    pytest.param([1.0, None, float("nan")], id="None apart from NaN"),
    pytest.param([[0, 2], [1], []], id="lists"),
    pytest.param([(1, "a"), (2, "b"), (3, "c")], id="tuples"),
    pytest.param([{"a": 1}, {"b": "x"}, {}], id="dicts with different keys"),
    pytest.param([1, "a", 2.5], id="mixed types"),
    pytest.param([2 ** 70, 1, -2 ** 65], id="ints past 64 bits"),
    pytest.param([True, 1, 0], id="bool apart from int"),
    pytest.param([dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), None, None], id="datetimes"),
    pytest.param([decimal.Decimal("1.10"), None, None], id="decimals"),
    pytest.param([b"\x00\xff", b"", None], id="bytes"),
    pytest.param([np.float32(1.5), np.int8(3), None], id="numpy scalars"),
    pytest.param([{1: "int key"}, {(1, 2): "tuple key"}, None], id="non-string keys"),
    pytest.param([{"$dict": "looks like a tag"}, None, None], id="a dict that looks like a tag"),
])
def test_every_kind_of_column_reads_back_exactly(tmp_path, column):
    frame = pd.DataFrame({"c": pd.Series(column, dtype=object), "n": [1, 2, 3]})
    k, loaded, report = _roundtrip(tmp_path, frame)
    assert report["exact"] is True
    before, after = k.step("s").output.data, loaded.step("s").output.data
    assert _data_version(after) == _data_version(before)
    assert [type(v) for v in after["c"]] == [type(v) for v in before["c"]]


def test_dtypes_column_names_and_the_index_are_kept(tmp_path):
    frame = pd.DataFrame({0: [1, 2], "2023": [1.5, 2.5], "flag": [True, False],
                          "when": pd.to_datetime(["2026-01-01", "2026-02-01"])},
                         index=pd.Index(["a", "b"], name="id"))
    k, loaded, report = _roundtrip(tmp_path, frame)
    assert report["exact"] is True
    before, after = k.step("s").output.data, loaded.step("s").output.data
    assert list(after.columns) == list(before.columns)
    assert list(after.dtypes.astype(str)) == list(before.dtypes.astype(str))
    assert list(after.index) == list(before.index)
    assert _data_version(after) == _data_version(before)


def test_a_typed_column_opens_without_core(tmp_path):
    frame = pd.DataFrame({"n": [1, 2, 3], "name": ["Ada", "Ben", "Cy"]})
    _roundtrip(tmp_path, frame)
    plain = pd.read_parquet(tmp_path / "session" / "data" / "s" / "table.parquet")
    assert plain["n"].tolist() == [1, 2, 3]
    assert plain["name"].tolist() == ["Ada", "Ben", "Cy"]


def test_a_value_that_cant_be_saved_is_reported_and_loads_invalid(tmp_path):
    class Model:
        pass

    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"m": [Model(), Model()], "n": [1, 2]})
    k["u"] = [1, 2, 3]
    report = k.save(tmp_path / "session")
    assert report["exact"] is False
    assert "m" in report["steps"]["s"]["not_saved"]
    assert "Model" in report["steps"]["s"]["not_saved"]["m"]
    assert json.loads((tmp_path / "session" / "report.json").read_text())["exact"] is False

    loaded = Kernel.load(tmp_path / "session", CAT)
    assert loaded.step("s").state == "invalid"
    assert any("m" in p.message and "Model" in p.message for p in loaded.step("s").problems)
    assert loaded.step("u").state == "completed"
    loaded.run_all()                                  # never raises


def test_a_missing_data_file_loads_invalid_and_runs_the_rest(tmp_path):
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2]})
    k["t"] = dbl[mod.map()](wf["s"])
    k["u"] = [1, 2]
    k.save(tmp_path / "session")
    (tmp_path / "session" / "data" / "s" / "table.parquet").unlink()

    loaded = Kernel.load(tmp_path / "session", CAT)
    assert loaded.step("s").state == "invalid"
    assert any("data/s/table.parquet" in p.message for p in loaded.step("s").problems)
    assert loaded.step("t").state == "invalid"
    loaded.run_all()
    assert loaded.step("u").state == "completed"


def test_a_changed_data_file_loads_invalid_naming_it(tmp_path):
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2]})
    k.save(tmp_path / "session")
    other = Kernel(CAT)
    other["s"] = pd.DataFrame({"n": [5, 6]})
    other.save(tmp_path / "other")
    (tmp_path / "other" / "data" / "s" / "table.parquet").replace(tmp_path / "session" / "data" / "s" / "table.parquet")

    loaded = Kernel.load(tmp_path / "session", CAT)
    assert loaded.step("s").state == "invalid"
    assert any("changed since it was saved" in p.message for p in loaded.step("s").problems)


def test_the_light_export_says_the_data_isnt_in_it_and_never_raises():
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2]})
    k["t"] = dbl[mod.map()](wf["s"])
    loaded = Kernel.from_json(k.to_json(), CAT)
    assert loaded.step("s").state == "invalid"
    assert any("k.save" in p.message for p in loaded.step("s").problems)
    loaded.run_all()                                  # raised ValueError before


def test_a_json_literal_stays_in_the_workflow_file(tmp_path):
    k = Kernel(CAT)
    k["lim"] = 38
    k["xs"] = [3, 1, 2]
    k.save(tmp_path / "session")
    assert not (tmp_path / "session" / "data").exists() or \
        not any((tmp_path / "session" / "data").iterdir())
    loaded = Kernel.load(tmp_path / "session", CAT)
    for name in ("lim", "xs"):           # a list literal is one value (D11)
        assert loaded.step(name).output.data[name].tolist() == \
            k.step(name).output.data[name].tolist()


def test_a_step_name_that_isnt_a_safe_file_name_is_escaped(tmp_path):
    k = Kernel(CAT)
    k["a/b c"] = pd.DataFrame({"n": [1, 2]})
    k.save(tmp_path / "session")
    files = [p.name for p in (tmp_path / "session" / "data").iterdir()]
    assert files and all("/" not in f and " " not in f for f in files)
    loaded = Kernel.load(tmp_path / "session", CAT)
    assert loaded.step("a/b c").output.data["n"].tolist() == [1, 2]


def test_saving_again_replaces_the_data(tmp_path):
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2]})
    k.save(tmp_path / "session")
    k["s"] = pd.DataFrame({"n": [7, 8, 9]})
    k.save(tmp_path / "session")
    loaded = Kernel.load(tmp_path / "session", CAT)
    assert loaded.step("s").output.data["n"].tolist() == [7, 8, 9]


def test_a_data_steps_spec_round_trips_without_its_data():
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2]})
    k["t"] = dbl[mod.map()](wf["s"])
    assert Kernel.from_spec(k.spec, CAT).spec == k.spec


def test_resaving_a_session_whose_data_didnt_load_says_so(tmp_path):
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2]})
    k.save(tmp_path / "a")
    (tmp_path / "a" / "data" / "s" / "table.parquet").unlink()
    loaded = Kernel.load(tmp_path / "a", CAT)
    assert loaded.step("s").formula == "<data not loaded>"
    report = loaded.save(tmp_path / "b")
    assert report["exact"] is False
    assert "wasn't loaded" in report["steps"]["s"]["not_saved"]["*"]
    assert Kernel.load(tmp_path / "b", CAT).step("s").state == "invalid"


# ── the tagged form, value by value ──────────────────────────────────────
from simple_steps_core.saving import NotSaved, tag, untag  # noqa: E402


@pytest.mark.parametrize("value", [
    pd.NA, pd.NaT, np.datetime64("2026-01-01T10:00", "m"), np.timedelta64(5, "s"),
    np.bool_(True), np.float16(0.5), bytearray(b"ab"), complex(1, -2), float("inf"),
    pd.Timestamp("2026-03-01 12:00:00.000000001", tz="Europe/London"),
    pd.Timedelta(90, unit="s"), dt.date(2026, 1, 2), dt.time(10, 30, 5),
    dt.timedelta(days=1, seconds=3, microseconds=7),
    dt.datetime(2026, 1, 1, 9, tzinfo=__import__("zoneinfo").ZoneInfo("Europe/Paris")),
    {1, 2}, frozenset({"a"}), {"k": [(1, None), {2.5}]},
])
def test_tag_gives_every_kind_of_value_back(value):
    back = untag(json.loads(json.dumps(tag(value))))
    assert type(back) is type(value)
    assert json.dumps(tag(back), sort_keys=True) == json.dumps(tag(value), sort_keys=True)


@pytest.mark.parametrize("value", [object(), np.array([1])[0:1].astype(object)[0:1][0:1],
                                   np.str_("x"), __import__("collections").OrderedDict(a=1)])
def test_tag_refuses_what_it_cant_hold(value):
    if isinstance(value, np.ndarray):
        value = np.array([object()], dtype=object)[0]
    with pytest.raises(NotSaved):
        tag(value)


def test_a_value_that_isnt_a_table_is_kept_in_the_workflow_file(tmp_path):
    k = Kernel(CAT)
    k["when"] = dt.datetime(2026, 1, 1, 9, 30)
    k["arr"] = np.array([1, 2, 3])
    report = k.save(tmp_path / "session")
    assert report["steps"]["when"]["file"] == "workflow.json"
    assert report["exact"] is True                                  # the array is media
    loaded = Kernel.load(tmp_path / "session", CAT)
    assert loaded.step("when").output.data.iloc[0, 0] == dt.datetime(2026, 1, 1, 9, 30)
    assert np.array_equal(loaded.step("arr").literal, np.array([1, 2, 3]))


@pytest.mark.parametrize("frame, why", [
    (pd.DataFrame([[1, 2]], columns=pd.MultiIndex.from_tuples([("a", "x"), ("a", "y")])),
     "several header"),
    # repeated column names: core can't assign such a table yet (plan P1, R-cols)
])
def test_a_table_core_cant_save_is_reported(tmp_path, frame, why):
    k = Kernel(CAT)
    k["s"] = frame
    report = k.save(tmp_path / "session")
    assert why in report["steps"]["s"]["not_saved"]["*"]
    assert Kernel.load(tmp_path / "session", CAT).step("s").state == "invalid"


def test_reserved_and_case_colliding_names_get_files_of_their_own(tmp_path):
    k = Kernel(CAT)
    for name, n in [("con", 1), ("S", 2), ("s", 3)]:
        k[name] = pd.DataFrame({"n": [n]})
    report = k.save(tmp_path / "session")
    files = {report["steps"][n]["file"] for n in ("con", "S", "s")}
    assert len(files) == 3 and "data/con/table.parquet" not in files
    loaded = Kernel.load(tmp_path / "session", CAT)
    assert [loaded.step(n).output.data["n"].iloc[0] for n in ("con", "S", "s")] == [1, 2, 3]


def test_a_removed_steps_data_file_goes_on_the_next_save(tmp_path):
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1]})
    k["t"] = pd.DataFrame({"n": [2]})
    k.save(tmp_path / "session")
    k.remove("t")
    k.save(tmp_path / "session")
    assert sorted(p.name for p in (tmp_path / "session" / "data").iterdir()) == ["s"]


def test_a_broken_workflow_file_isnt_a_reason_not_to_save(tmp_path):
    (tmp_path / "session").mkdir()
    (tmp_path / "session" / "workflow.json").write_text("{not json")
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1]})
    assert k.save(tmp_path / "session")["exact"] is True


# ── layer 2: outputs, so a reopened session shows its results unrun ──────
CALLS: list = []


@tool(id="split")
def split_two(name: str) -> list:
    CALLS.append(name)
    return list(name[:2])


@tool(id="split")
def split_three(name: str) -> list:                  # the same tool, its code changed
    return list(name[:3])


@tool
def mean(n: list) -> float:
    return sum(n) / len(n)


@tool
def risky(n: int) -> int:
    if n == 2:
        raise ValueError("two")
    return n


def _session(split=split_two):
    cat = Catalog(tools=[dbl, split, mean, risky])
    k = Kernel(cat)
    k["v"] = pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "ward": ["A", "B", "A"], "n": [1, 2, 3]})
    k["d"] = dbl[mod.map()](wf["v"])
    k["e"] = split[mod.expand()](wf["v"])
    k["c"] = mean[mod.collapse(by="ward")](wf["v"])
    k["r"] = risky[mod.map(), mod.try_except()](wf["v"])
    k.run_all()
    return k, cat


def _views(k):
    return {name: k.view(name) for name in k.workflow.steps}


def test_outputs_load_completed_and_shown_as_they_were(tmp_path):
    k, cat = _session()
    report = k.save(tmp_path / "session", outputs=True)
    assert report["exact"] is True
    assert (tmp_path / "session" / "data" / "e" / "table.parquet").exists()
    CALLS.clear()
    loaded = Kernel.load(tmp_path / "session", cat)
    assert {n: loaded.step(n).state for n in loaded.workflow.steps} == \
        {n: k.step(n).state for n in k.workflow.steps}
    assert _views(loaded) == _views(k)                # values, lineage, row numbers, states
    for name in ("d", "e", "c", "r"):
        assert _data_version(loaded.step(name).output.data) == _data_version(k.step(name).output.data)
    assert CALLS == []                                # loading ran nothing
    assert loaded.needs_run() == {}                   # and nothing needs a run
    assert loaded.cell("e", 1)["inputs"] == k.cell("e", 1)["inputs"]


def test_failed_cells_and_their_errors_come_back(tmp_path):
    k, cat = _session()
    k.save(tmp_path / "session", outputs=True)
    loaded = Kernel.load(tmp_path / "session", cat)
    assert loaded.step("r").state == k.step("r").state
    assert loaded.cell("r", 1)["state"] == "failed" == k.cell("r", 1)["state"]
    assert loaded.step("r").output.notes == k.step("r").output.notes


def test_a_changed_tool_makes_its_steps_stale_on_load(tmp_path):
    k, _ = _session()
    k.save(tmp_path / "session", outputs=True)
    loaded = Kernel.load(tmp_path / "session", Catalog(tools=[dbl, split_three, mean, risky]))
    assert loaded.step("e").state == "stale"
    assert loaded.step("e").output.meta.get("stale_reason") == "tool changed"
    assert loaded.step("d").state == "completed"


def test_the_session_export_marks_a_changed_tool_stale_too():
    from simple_steps_core.workflow import Workflow
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2]})
    k["t"] = dbl[mod.map()](wf["s"])
    k.run_all()

    @tool(id="dbl")
    def tripled(n: int) -> int:
        return 3 * n
    back = Workflow.from_json(k.workflow.to_session_json(), catalog=Catalog(tools=[tripled]))
    assert back.step("t").state == "stale"           # was "completed": an old result shown as current


def test_an_output_that_cant_be_saved_is_reported_and_runs_again(tmp_path):
    class Model:
        pass

    @tool
    def model(n: int) -> object:
        return Model()

    cat = Catalog(tools=[dbl, model])
    k = Kernel(cat)
    k["s"] = pd.DataFrame({"n": [1, 2]})
    k["m"] = model[mod.map()](wf["s"])
    k["d"] = dbl[mod.map()](wf["s"])
    k.run_all()
    report = k.save(tmp_path / "session", outputs=True)
    assert report["exact"] is False
    assert "Model" in report["steps"]["m"]["output"]["not_saved"]["m"]
    loaded = Kernel.load(tmp_path / "session", cat)
    assert loaded.step("m").state == "staged"         # needs a run; nothing wrong shown
    assert loaded.step("d").state == "completed"
    loaded.run_all()
    assert loaded.step("m").state == "completed"


def test_a_missing_or_changed_output_file_means_a_rerun_not_a_crash(tmp_path):
    k, cat = _session()
    k.save(tmp_path / "session", outputs=True)
    (tmp_path / "session" / "data" / "d" / "table.parquet").unlink()
    (tmp_path / "session" / "data" / "c" / "table.parquet").replace(
        tmp_path / "session" / "data" / "e" / "table.parquet")
    loaded = Kernel.load(tmp_path / "session", cat)
    assert loaded.step("d").state == "staged"
    assert loaded.step("e").state == "staged"
    loaded.run_all()
    assert loaded.step("d").output.data["d"].tolist() == [2, 4, 6]


def test_without_outputs_nothing_is_written_and_old_outputs_go(tmp_path):
    k, cat = _session()
    k.save(tmp_path / "session", outputs=True)
    k.save(tmp_path / "session")
    assert not (tmp_path / "session" / "data" / "d").exists()   # its output's files went
    assert Kernel.load(tmp_path / "session", cat).step("d").state == "staged"


def test_a_data_steps_row_ids_survive_so_its_readers_outputs_still_match(tmp_path):
    k, cat = _session()
    k["v"] = pd.DataFrame({"name": ["Zed", "Ada", "Ben", "Cy"], "ward": ["C", "A", "B", "A"],
                           "n": [9, 1, 2, 3]})      # a row inserted above: ids follow (D-picks)
    k.run_all()
    k.save(tmp_path / "session", outputs=True)
    loaded = Kernel.load(tmp_path / "session", cat)
    assert list(loaded.step("v").output.data.index) == list(k.step("v").output.data.index)
    assert _views(loaded) == _views(k)
    assert {n: loaded.step(n).state for n in loaded.workflow.steps} == \
        {n: k.step(n).state for n in k.workflow.steps}


# ── media: arrays, images and figures, exactly ───────────────────────────
from PIL import Image  # noqa: E402
import plotly.graph_objects as go  # noqa: E402


def _image(mode):
    base = Image.fromarray(np.arange(48, dtype=np.uint8).reshape(4, 4, 3))
    return base.convert(mode) if mode != "I;16" else \
        Image.fromarray(np.arange(16, dtype=np.uint16).reshape(4, 4))


@pytest.mark.parametrize("array", [
    np.arange(48, dtype=np.uint8).reshape(4, 4, 3), np.array([1.5, np.nan], dtype=np.float32),
    np.array([0.1], dtype=np.float16), np.array([True, False]), np.array([1 + 2j]),
    np.array(["2026-01-01"], dtype="datetime64[D]"), np.asfortranarray(np.arange(6).reshape(2, 3)),
    np.array(5), np.array([1, 2], dtype=">i4"),
    np.array([(1, 2.0)], dtype=[("a", "i4"), ("b", "f8")]),
], ids=lambda a: f"{a.dtype}{a.shape}")
def test_arrays_are_saved_exactly(tmp_path, array):
    k, loaded, report = _roundtrip(tmp_path, pd.DataFrame({"a": [array, array], "n": [1, 2]}))
    assert report["exact"] is True
    back = loaded.step("s").output.data["a"].iloc[0]
    assert back.dtype == array.dtype and back.shape == array.shape
    assert back.flags.f_contiguous == array.flags.f_contiguous
    assert np.array_equal(back, array, equal_nan=array.dtype.kind in "fc")
    assert len([f for f in (tmp_path / "session" / "data").rglob("*") if f.parent.name == "files"]) == 1  # once


@pytest.mark.parametrize("mode", ["1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I", "F", "CMYK"])
def test_images_are_saved_exactly_in_every_mode(tmp_path, mode):
    image = _image(mode)
    k, loaded, report = _roundtrip(tmp_path, pd.DataFrame({"img": [image]}))
    assert report["exact"] is True
    back = loaded.step("s").output.data["img"].iloc[0]
    assert (back.mode, back.size, back.tobytes()) == (image.mode, image.size, image.tobytes())
    ext = "png" if mode in ("1", "L", "LA", "P", "RGB", "RGBA", "I;16") else "tiff"
    assert [p.suffix for p in (tmp_path / "session" / "data" / "s" / "files").iterdir()] == [f".{ext}"]


def test_an_image_opened_from_a_jpeg_keeps_its_pixels_format_and_info(tmp_path):
    import io
    buffer = io.BytesIO()
    _image("RGB").save(buffer, format="JPEG", quality=80)
    jpeg = Image.open(io.BytesIO(buffer.getvalue()))
    jpeg.load()
    k, loaded, report = _roundtrip(tmp_path, pd.DataFrame({"img": [jpeg]}))
    assert report["exact"] is True
    back = loaded.step("s").output.data["img"].iloc[0]
    assert back.tobytes() == jpeg.tobytes()
    assert back.format == "JPEG" and back.info == jpeg.info


def test_a_figure_is_saved_exactly_with_its_arrays_as_arrays(tmp_path):
    x = np.array([1.5, 2.5], dtype=np.float32)
    figure = go.Figure(go.Scatter(x=x, y=x * 2), layout={"title": "temps"})
    k, loaded, report = _roundtrip(tmp_path, pd.DataFrame({"fig": [figure]}))
    assert report["exact"] is True
    back = loaded.step("s").output.data["fig"].iloc[0]
    assert isinstance(back, go.Figure)
    assert isinstance(back.data[0].x, np.ndarray) and back.data[0].x.dtype == np.float32
    assert back.to_json() == figure.to_json() or \
        json.loads(back.to_json()) == json.loads(figure.to_json())


def test_tool_outputs_of_arrays_images_and_figures_reload_unrun(tmp_path):
    @tool
    def load_image(n: int) -> object:
        return Image.fromarray(np.full((2, 2, 3), n, dtype=np.uint8))

    @tool
    def channels(n: int) -> np.ndarray:
        return np.full((2, 2), n, dtype=np.uint8)

    @tool
    def chart(n: int) -> object:
        return go.Figure(go.Bar(y=[n, n * 2]))

    cat = Catalog(tools=[load_image, channels, chart])
    k = Kernel(cat)
    k["s"] = pd.DataFrame({"n": [1, 2]})
    k["img"] = load_image[mod.map()](wf["s"])
    k["arr"] = channels[mod.map()](wf["s"])
    k["fig"] = chart[mod.map()](wf["s"])
    k.run_all()
    report = k.save(tmp_path / "session", outputs=True)
    assert report["exact"] is True
    loaded = Kernel.load(tmp_path / "session", cat)
    assert {n: loaded.step(n).state for n in ("img", "arr", "fig")} == \
        {"img": "completed", "arr": "completed", "fig": "completed"}
    assert loaded.needs_run() == {}
    for name in ("img", "arr", "fig"):
        assert _data_version(loaded.step(name).output.data) == _data_version(k.step(name).output.data)


def test_an_array_of_objects_is_reported_not_saved(tmp_path):
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"a": [np.array([object()], dtype=object)], "n": [1]})
    report = k.save(tmp_path / "session")
    assert "objects" in report["steps"]["s"]["not_saved"]["a"]


def test_media_no_value_names_any_more_is_removed(tmp_path):
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"a": [np.zeros(3)]})
    k.save(tmp_path / "session")
    k["s"] = pd.DataFrame({"a": [np.ones(3)]})
    k.save(tmp_path / "session")
    assert len(list((tmp_path / "session" / "data" / "s" / "files").iterdir())) == 1
    loaded = Kernel.load(tmp_path / "session", CAT)
    assert np.array_equal(loaded.step("s").output.data["a"].iloc[0], np.ones(3))


def test_a_missing_media_file_loads_invalid_naming_it(tmp_path):
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"a": [np.zeros(3)]})
    k.save(tmp_path / "session")
    for f in (tmp_path / "session" / "data" / "s" / "files").iterdir():
        f.unlink()
    loaded = Kernel.load(tmp_path / "session", CAT)
    assert loaded.step("s").state == "invalid"
    assert any("missing" in p.message for p in loaded.step("s").problems)
