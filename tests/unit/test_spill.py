"""Bulky cells on disk, a ledger in memory (owner, 2026-11-17; plan P7d, S-D6).

With ``Kernel(catalog, spill_over=n)``, a step's array, image or figure of
``n`` bytes or more is written once to the kernel's store (by content, as a
saved session's media) when the step runs, and its cell holds a
:class:`MediaHandle`: a small entry naming the file, a summary and the
value's data version. A tool reading the column gets the value itself, loaded
then; the view shows the summary without loading it. Versions, run keys and
staleness are the same as with the values in memory.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest
from PIL import Image

from simple_steps_core import Catalog, Kernel, MediaHandle, cols, mod, tool, wf
from simple_steps_core.output import _data_version

SEEN: list = []


@tool
def load_image(n: int) -> object:
    return Image.fromarray(np.full((64, 64, 3), n, dtype=np.uint8))


@tool
def channel(load_image: object) -> np.ndarray:
    SEEN.append(type(load_image).__name__)
    return np.asarray(load_image)[..., 0]


@tool
def brightness(channel: np.ndarray) -> float:
    SEEN.append(type(channel).__name__)
    return float(channel.mean())


@tool
def chart(n: int) -> object:
    return go.Figure(go.Scatter(y=np.arange(5000, dtype=float) * n))


@tool
def grid_size(df: pd.DataFrame) -> pd.DataFrame:
    SEEN.append(type(df["load_image"].iloc[0]).__name__)
    return pd.DataFrame({"pixels": [sum(im.size[0] * im.size[1] for im in df["load_image"])]})


@tool
def width(im: object) -> int:
    SEEN.append(type(im).__name__)
    return im.size[0]


CAT = Catalog(tools=[load_image, channel, brightness, chart, grid_size, width])


def _build(spill_over=None, store=None):
    SEEN.clear()
    k = Kernel(CAT, spill_over=spill_over, store=store)
    k["s"] = pd.DataFrame({"n": [10, 200]})
    k["load_image"] = load_image[mod.map()](wf["s"])
    k["channel"] = channel[mod.map()](wf["load_image"])
    k["brightness"] = brightness[mod.map()](wf["channel"])
    k["chart"] = chart[mod.map()](wf["s"])
    k.run_all()
    return k


def test_bulky_cells_are_kept_on_disk_and_tools_get_the_values(tmp_path):
    k = _build(spill_over=1000, store=tmp_path / "store")
    image = k.step("load_image").output.data["load_image"].iloc[0]
    assert isinstance(image, MediaHandle)
    assert "RGB image 64×64" in image.summary
    assert isinstance(k.step("channel").output.data["channel"].iloc[0], MediaHandle)
    assert isinstance(k.step("chart").output.data["chart"].iloc[0], MediaHandle)
    assert SEEN == ["Image", "Image", "ndarray", "ndarray"]   # tools never see a handle
    assert k.step("brightness").output.data["brightness"].tolist() == [10.0, 200.0]
    assert len(list((tmp_path / "store").iterdir())) == 6     # 2 images, 2 arrays, 2 figures


def test_small_values_stay_in_memory(tmp_path):
    k = _build(spill_over=10 ** 9, store=tmp_path / "store")
    assert isinstance(k.step("load_image").output.data["load_image"].iloc[0], Image.Image)


def test_versions_run_keys_and_states_are_the_same_on_disk_or_not(tmp_path):
    on_disk, in_memory = _build(spill_over=1000, store=tmp_path / "store"), _build()
    for name in ("load_image", "channel", "brightness", "chart"):
        assert on_disk.step(name).output.meta["version"] == in_memory.step(name).output.meta["version"]
        assert on_disk.workflow.run_key(name) == in_memory.workflow.run_key(name)
        assert on_disk.step(name).state == in_memory.step(name).state == "completed"
        assert _data_version(on_disk.step(name).output.data) == \
            _data_version(in_memory.step(name).output.data)


def test_the_view_shows_a_summary_without_loading(tmp_path, monkeypatch):
    k = _build(spill_over=1000, store=tmp_path / "store")
    monkeypatch.setattr(MediaHandle, "load", lambda self: pytest.fail("the view loaded a value"))
    cell = k.view("load_image")["rows"][0]["cells"]["load_image"]
    assert cell["state"] == "known"
    assert "RGB image 64×64" in str(cell["value"])


def test_k_value_gives_the_value_itself(tmp_path):
    k = _build(spill_over=1000, store=tmp_path / "store")
    image = k.value("load_image", 1, "load_image")
    assert isinstance(image, Image.Image) and image.getpixel((0, 0)) == (200, 200, 200)


def test_a_table_tool_and_a_picked_cell_get_values(tmp_path):
    k = _build(spill_over=1000, store=tmp_path / "store")
    k["g"] = grid_size[mod.table()](wf["load_image"])
    k["w"] = width[mod.map()](wf["s"], im=wf["load_image"][0][cols["load_image"]])
    SEEN.clear()
    k.run_all()
    assert k.step("g").output.data["pixels"].tolist() == [64 * 64 * 2]
    assert k.step("w").output.data["w"].tolist() == [64, 64]
    assert set(SEEN) == {"Image"}


def test_an_edit_makes_only_its_rows_stale_on_disk_too(tmp_path):
    k = _build(spill_over=1000, store=tmp_path / "store")
    k["s"] = pd.DataFrame({"n": [10, 99]})
    k.run("load_image")
    assert k.step("channel").state == "stale"
    assert k.step("channel").output.meta.get("stale_rows") == [1]


def test_a_saved_session_copies_the_files_and_loads_them_lazily(tmp_path):
    k = _build(spill_over=1000, store=tmp_path / "store")
    report = k.save(tmp_path / "session", outputs=True)
    assert report["exact"] is True
    lazy = Kernel.load(tmp_path / "session", CAT, spill_over=1000)
    cell = lazy.step("load_image").output.data["load_image"].iloc[0]
    assert isinstance(cell, MediaHandle)                      # not loaded
    assert lazy.needs_run() == {}
    assert np.array_equal(np.asarray(lazy.value("load_image", 1, "load_image")),
                          np.asarray(k.value("load_image", 1, "load_image")))
    eager = Kernel.load(tmp_path / "session", CAT)
    assert isinstance(eager.step("load_image").output.data["load_image"].iloc[0], Image.Image)


def test_the_view_of_arrays_in_memory_no_longer_crashes():
    # P1 C37: _plain called .item() on anything with a dtype
    k = Kernel(Catalog(tools=[]))
    k["a"] = pd.DataFrame({"x": [np.zeros((2, 2)), np.ones(3)]})
    cell = k.view("a")["rows"][0]["cells"]["x"]
    assert cell["state"] == "known"


def test_a_change_in_the_middle_of_a_big_array_is_seen_row_by_row():
    # repr shortens a big array to its edges, so row fingerprints missed it
    from simple_steps_core.step import _row_fps
    a = np.zeros(5000)
    b = a.copy()
    b[2500] = 1
    fps = _row_fps(pd.DataFrame({"x": [a, b]}, dtype=object), ["x"])
    assert fps.iloc[0] != fps.iloc[1]


def test_handles_inside_containers_and_their_identity(tmp_path):
    from simple_steps_core.handles import Spill, values_of
    spill = Spill(tmp_path / "store", over=10)
    array = np.arange(100, dtype=np.int64)
    handle = spill.handle(array)
    assert isinstance(handle, MediaHandle) and handle.kind == "array"
    assert handle == spill.handle(array.copy()) and len({handle, spill.handle(array)}) == 1
    assert "int64 array 100" in repr(handle)
    nested = values_of({"a": [handle, (handle,)], "s": pd.Series([handle], dtype=object)})
    assert np.array_equal(nested["a"][0], array) and np.array_equal(nested["a"][1][0], array)
    assert np.array_equal(nested["s"].iloc[0], array)
    assert spill.handle(5) == 5 and spill.handle(np.arange(2)) is not None


def test_a_kernels_own_store_goes_with_it():
    import gc
    import pathlib
    k = Kernel(CAT, spill_over=1000)
    k["s"] = pd.DataFrame({"n": [1]})
    k["load_image"] = load_image[mod.map()](wf["s"])
    k.run_all()
    store = pathlib.Path(k._spill.folder)
    assert any(store.iterdir())
    del k
    gc.collect()
    assert not store.exists()
