"""Images, frames and lazy sources through the real dashboard.

Drives the actual Streamlit app with ``AppTest`` against the
``media_and_dataframes`` example. The component tests prove the dispatch is
right; this proves the dashboard boots with these types registered and runs a
pipeline over them without raising — the wiring the fakes cannot see.
"""

import os

import pytest

pytest.importorskip("streamlit", reason="dashboard extra not installed")
pytest.importorskip("PIL", reason="Pillow not installed")
pytest.importorskip("pandas")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "src", "simple_steps_core", "streamlit", "dashboard.py")
TOOLS = os.path.join(ROOT, "streamlit_example", "media_and_dataframes.py")


def _widget(app, key):
    for group in (app.selectbox, app.number_input, app.slider,
                  app.text_input, app.text_area):
        for widget in group:
            if widget.key == key:
                return widget
    raise KeyError(f"no widget {key!r}")


def _assert_clean(app, tag):
    assert not app.exception, f"{tag}: {[e.value for e in app.exception]}"


def _wire(app, step_id, tool, *, param=None, source=None, mode=None):
    next(b for b in app.button if "Add" in b.label).click().run()
    _widget(app, f"op_{step_id}").set_value(tool).run()
    if source is not None:
        _widget(app, f"src_{step_id}_{param}").set_value(source).run()
    if mode is not None:
        _widget(app, f"orch_{step_id}_mode").set_value(mode).run()


@pytest.fixture
def app():
    os.environ["SIMPLE_STEPS_TOOLS"] = TOOLS
    at = AppTest.from_file(SCRIPT, default_timeout=300)
    at.run()
    _assert_clean(at, "boot")
    return at


def _run_all(app):
    next(b for b in app.button if "Run all" in b.label).click().run()
    return app


def _statuses(app):
    return {s.step_id: s.status.value for s in app.session_state["wf"].steps}


def test_the_dashboard_boots_with_media_and_frame_tools(app):
    """A resource spec in RESOURCES and media tools must not break startup."""
    options = _first_tool_options(app)
    assert "photos-load" in options
    assert "photos-thumbnail" in options
    assert "load_sales" in options


def _first_tool_options(app):
    next(b for b in app.button if "Add" in b.label).click().run()
    return list(_widget(app, "op_step1").options)


def test_a_media_pipeline_runs_and_renders(app):
    """load images -> thumbnail each: the grid must render without raising."""
    _wire(app, "step1", "photos-load")
    _wire(app, "step2", "photos-thumbnail", param="image", source="step1", mode="map")
    _assert_clean(app, "media pipeline built")

    _run_all(app)
    _assert_clean(app, "media pipeline run")

    assert set(_statuses(app).values()) == {"completed"}
    thumbnails = app.session_state["wf"]["step2"].output.value.ok
    assert len(thumbnails) == 3
    assert all(a.is_image and a.exists() for a in thumbnails)


def test_a_dataframe_pipeline_runs_and_renders(app):
    """load a frame -> filter it -> group it: frames all the way through."""
    _wire(app, "step1", "load_sales")
    _wire(app, "step2", "big_sale", param="row", source="step1", mode="filter")
    _wire(app, "step3", "region_of", param="row", source="step1", mode="group")
    _assert_clean(app, "frame pipeline built")

    _run_all(app)
    _assert_clean(app, "frame pipeline run")

    workflow = app.session_state["wf"]
    assert set(_statuses(app).values()) == {"completed"}

    from simple_steps_core import is_frame

    filtered = workflow["step2"].output.value
    grouped = workflow["step3"].output.value
    assert is_frame(filtered) and len(filtered) == 4      # amounts over 25
    assert set(grouped.keys()) == {"east", "west", "north"}
    assert all(is_frame(bucket) for bucket in grouped.values())


def test_the_media_store_is_durable_for_the_example():
    """The example points at its own directory, not a temp one the OS may clear."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("_media_example", TOOLS)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    from simple_steps_core import get_media_store

    assert "media_store" in str(get_media_store().root)
    assert module.PHOTOS.exists()
    assert len(list(module.PHOTOS.glob("*.png"))) == 3
