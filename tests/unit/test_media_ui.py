"""Rendering: each value type gets the component it deserves.

Like ``test_components``, these run the real components against a fake ``st``.
The point is the dispatch — an image must reach ``st.image`` and a clip
``st.video``, rather than everything funnelling into one table of reprs.
"""

from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from simple_steps_core import (
    Collection,
    ItemOutcome,
    ListCollection,
    MapResult,
    MediaAsset,
    MediaStore,
    StepOutput,
    StepStatus,
    set_media_store,
)
from simple_steps_core.streamlit import components as C

Image = pytest.importorskip("PIL.Image")
pd = pytest.importorskip("pandas")


class FakeSt:
    """Records every call, including calls made inside columns and tabs."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self.children: list["FakeSt"] = []

    def _log(self, kind, payload=None):
        self.calls.append((kind, payload))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def caption(self, body, **kw): self._log("caption", body)
    def warning(self, body, **kw): self._log("warning", body)
    def write(self, *a, **kw): self._log("write", a[0] if a else None)
    def image(self, src, **kw): self._log("image", (src, kw.get("caption")))
    def video(self, src, **kw): self._log("video", src)

    def dataframe(self, df, **kw):
        self._log("dataframe", df.data if hasattr(df, "data") else df)

    def columns(self, n, **kw):
        made = [FakeSt() for _ in range(n if isinstance(n, int) else len(n))]
        self.children.extend(made)
        return made

    def tabs(self, labels, **kw):
        self._log("tabs", list(labels))
        made = [FakeSt() for _ in labels]
        self.children.extend(made)
        return made

    @contextmanager
    def expander(self, label, **kw):
        self._log("expander", label)
        yield self

    # ── queries ──────────────────────────────────────────────────────────
    def kinds(self, *, deep: bool = False) -> list[str]:
        found = [kind for kind, _ in self.calls]
        if deep:
            for child in self.children:
                found.extend(child.kinds(deep=True))
        return found

    def payloads(self, kind: str, *, deep: bool = False) -> list:
        found = [p for k, p in self.calls if k == kind]
        if deep:
            for child in self.children:
                found.extend(child.payloads(kind, deep=True))
        return found


@pytest.fixture
def store(tmp_path):
    return set_media_store(MediaStore(tmp_path / "media"))


def _asset(color="red", size=(20, 10), name=""):
    return MediaAsset.from_image(Image.new("RGB", size, color), name=name or color)


# ── single values ────────────────────────────────────────────────────────
def test_an_image_is_shown_as_an_image(store):
    st = FakeSt()
    asset = _asset(name="red")

    C.render_value(st, asset, key="k")

    (src, caption), = st.payloads("image")
    assert src == asset.path
    assert "red" in caption and "20×10" in caption


def test_a_video_is_played_not_tabulated(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"pretend")
    st = FakeSt()

    C.render_value(st, MediaAsset.from_path(clip), key="k")

    assert st.payloads("video") == [str(clip)]
    assert "dataframe" not in st.kinds()


def test_a_handle_whose_file_is_gone_says_so(tmp_path):
    st = FakeSt()
    C.render_value(st, MediaAsset.from_path(tmp_path / "missing.png"), key="k")

    assert "warning" in st.kinds()
    assert "not found" in st.payloads("warning")[0]


def test_a_dataframe_still_renders_as_a_table():
    st = FakeSt()
    C.render_value(st, pd.DataFrame({"a": [1, 2]}), key="k", shaded=False)

    frame, = st.payloads("dataframe")
    assert list(frame["a"]) == [1, 2]


def test_a_scalar_still_renders_as_a_one_cell_table():
    st = FakeSt()
    C.render_value(st, 42, key="k", shaded=False)

    frame, = st.payloads("dataframe")
    assert list(frame["value"]) == [42]


def test_no_output_says_so():
    st = FakeSt()
    C.render_value(st, None, key="k")
    assert st.payloads("caption") == ["no output"]


# ── many values ──────────────────────────────────────────────────────────
def test_a_list_of_images_becomes_a_contact_sheet(store):
    st = FakeSt()
    assets = [_asset(c, name=c) for c in ("red", "green", "blue")]

    C.render_value(st, assets, key="k")

    assert len(st.payloads("image", deep=True)) == 3
    assert "dataframe" not in st.kinds(deep=True)


def test_a_fan_out_over_images_shows_the_pictures(store):
    st = FakeSt()
    result = MapResult(outcomes=[
        ItemOutcome(index=i, status=StepStatus.COMPLETED, value=_asset(c, name=c))
        for i, c in enumerate(("red", "green"))
    ])

    C.render_value(st, result, key="k")

    assert len(st.payloads("image", deep=True)) == 2


def test_a_fan_out_still_reports_failures_under_the_contact_sheet(store):
    st = FakeSt()
    result = MapResult(outcomes=[
        ItemOutcome(index=0, status=StepStatus.COMPLETED, value=_asset(name="ok")),
        ItemOutcome(index=1, status=StepStatus.FAILED, error="boom"),
    ])

    C.render_value(st, result, key="k")

    assert len(st.payloads("image", deep=True)) == 1
    assert any("1 item(s) failed" in c for c in st.payloads("caption"))
    frame, = st.payloads("dataframe")
    assert list(frame["error"]) == ["boom"]


def test_a_fan_out_over_plain_values_is_unchanged():
    st = FakeSt()
    result = MapResult(outcomes=[
        ItemOutcome(index=i, status=StepStatus.COMPLETED, value=i * 2)
        for i in range(3)
    ])

    C.render_value(st, result, key="k")

    frame, = st.payloads("dataframe")
    assert list(frame["value"]) == [0, 2, 4]
    assert "image" not in st.kinds(deep=True)


def test_a_big_contact_sheet_is_capped_and_says_how_many_are_hidden(store):
    st = FakeSt()
    one = _asset(name="one")
    C.render_media_grid(st, [one] * 60, key="k", limit=8)

    assert len(st.payloads("image", deep=True)) == 8
    assert any("52 more" in c for c in st.payloads("caption"))


# ── grouped and lazy values ──────────────────────────────────────────────
def test_a_group_result_gets_one_tab_per_bucket():
    st = FakeSt()
    groups = {
        "east": pd.DataFrame({"a": [1, 3]}),
        "west": pd.DataFrame({"a": [2]}),
    }

    C.render_value(st, groups, key="k", shaded=False)

    assert st.payloads("tabs") == [["east (2)", "west (1)"]]
    assert len(st.payloads("dataframe", deep=True)) == 2


def test_a_collection_previews_a_window_and_names_its_version():
    st = FakeSt()
    C.render_value(st, ListCollection(items=[1, 2, 3], version="v1"),
                   key="k", shaded=False)

    frame, = st.payloads("dataframe")
    assert list(frame["value"]) == [1, 2, 3]
    caption, = st.payloads("caption")
    assert "ListCollection" in caption and "3 item(s)" in caption and "v1" in caption


def test_a_collection_of_images_previews_as_a_contact_sheet(store):
    st = FakeSt()
    assets = [_asset(c, name=c) for c in ("red", "green")]

    C.render_value(st, ListCollection(items=assets, version="v1"), key="k")

    assert len(st.payloads("image", deep=True)) == 2


def test_an_unsized_collection_does_not_claim_an_exact_count():
    @dataclass
    class Unsized(Collection):
        version: str = "v9"

        def __iter__(self):
            return iter(range(500))

    st = FakeSt()
    C.render_value(st, Unsized(), key="k", shaded=False)

    caption, = st.payloads("caption")
    assert "+ item(s)" in caption


# ── through the public entry points ──────────────────────────────────────
def test_render_output_dispatches_the_same_way(store):
    st = FakeSt()
    C.render_output(st, StepOutput(value=_asset(name="red")), key="k")
    assert len(st.payloads("image")) == 1


def test_the_dispatch_table_knows_media_and_collections(store):
    st = FakeSt()
    C.render(st, _asset(name="red"), key="k")
    assert len(st.payloads("image")) == 1

    st = FakeSt()
    C.render(st, ListCollection(items=[1], version="v"), key="k")
    assert "dataframe" in st.kinds()


# ── the staged preview (before a step runs) ──────────────────────────────
def _staged(name, mode, registry):
    from simple_steps_core import Operation, OrchestrationConfig
    from simple_steps_core.streamlit.components import staged_frame

    spec = Operation(step_id="s", name=name,
                     orchestration=OrchestrationConfig(mode=mode, over="step1"))
    return staged_frame(spec, registry.get_definition(name)).iloc[0]


@pytest.fixture
def staging_registry():
    from simple_steps_core import ToolRegistry, register_orchestrators

    registry = ToolRegistry()
    register_orchestrators(registry)

    def thumb(image: MediaAsset) -> MediaAsset: ...
    def is_big(row: dict) -> bool: ...
    def stats(acc, row: dict) -> dict: ...

    for fn in (thumb, is_big, stats):
        registry.register(fn.__name__, fn)
    return registry


def test_a_media_return_is_named_not_called_a_dict(staging_registry):
    assert _staged("thumb", "map", staging_registry)["type"] == "MapResult[MediaAsset]"


def test_a_plain_dict_return_is_still_a_dict(staging_registry):
    """Pydantic titles the wrapper field "Result"; that must not leak into the UI."""
    assert _staged("stats", "collapse", staging_registry)["type"] == "dict"


def test_group_announces_buckets_rather_than_one_cell(staging_registry):
    row = _staged("thumb", "group", staging_registry)
    assert row["shape"] == "one bucket per distinct key of step1"
    assert row["type"] == "Groups[MediaAsset]"


def test_filter_announces_that_it_keeps_the_input_shape(staging_registry):
    assert _staged("is_big", "filter", staging_registry)["type"] == "same as step1"


def test_a_groups_result_renders_as_tabs_not_as_a_lazy_source():
    """Groups is a Collection, but strata must reach the tab renderer first."""
    from simple_steps_core import Group, Groups

    st = FakeSt()
    groups = Groups(groups=[
        Group(key="east", rows=pd.DataFrame({"a": [1, 3]})),
        Group(key="west", rows=pd.DataFrame({"a": [2]})),
    ])

    C.render_value(st, groups, key="k", shaded=False)

    assert st.payloads("tabs") == [["east (2)", "west (1)"]]
    assert len(st.payloads("dataframe", deep=True)) == 2
