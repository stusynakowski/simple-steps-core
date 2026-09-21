"""The example pipeline built through the real dashboard UI.

Drives the actual Streamlit app with ``AppTest`` — no browser — choosing tools,
setting orchestration, and running. This is the test that catches wiring bugs
the component-level tests cannot see.
"""

import os

import pytest

pytest.importorskip("streamlit", reason="dashboard extra not installed")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "src", "simple_steps_core", "streamlit", "dashboard.py")
TOOLS = os.path.join(ROOT, "streamlit_example", "example_tools_and_resources.py")


def _widget(app, key):
    """Any input widget by key."""
    for group in (app.selectbox, app.number_input, app.slider,
                  app.text_input, app.text_area):
        for widget in group:
            if widget.key == key:
                return widget
    raise KeyError(f"no widget {key!r}")


def _add_step(app):
    next(b for b in app.button if "Add" in b.label).click().run()


def _assert_clean(app, tag):
    assert not app.exception, f"{tag}: {[e.value for e in app.exception]}"


@pytest.fixture
def app():
    os.environ["SIMPLE_STEPS_TOOLS"] = TOOLS
    at = AppTest.from_file(SCRIPT, default_timeout=180)
    at.run()
    _assert_clean(at, "boot")
    return at


def _wire(app, step_id, tool, *, param=None, source=None, mode=None):
    """Choose a tool and which step it reads. Orchestration is inferred."""
    _add_step(app)
    _widget(app, f"op_{step_id}").set_value(tool).run()
    if source is not None:
        _widget(app, f"src_{step_id}_{param}").set_value(source).run()
    if mode is not None:
        _widget(app, f"orch_{step_id}_mode").set_value(mode).run()


@pytest.fixture
def pipeline(app):
    """load -> expand -> filter -> summarize, configured by type inference.

    Only `step2` names a mode: `identity` declares ``value: Any``, so nothing can
    be inferred from its types. Every other mode below is worked out.
    """
    _wire(app, "step1", "load_batches")
    _wire(app, "step2", "identity", param="value", source="step1", mode="expand")
    _wire(app, "step3", "above_cutoff", param="value", source="step2")
    _wire(app, "step4", "summarize", param="rows", source="step3")
    _assert_clean(app, "pipeline built")
    return app


def test_choosing_a_tool_shows_that_tool_s_arguments_immediately(app):
    """The form must not lag a selection behind."""
    _add_step(app)
    _widget(app, "op_step1").set_value("above_cutoff").run()
    assert _widget(app, "form_step1_cutoff") is not None

    _widget(app, "op_step1").set_value("summarize").run()
    assert _widget(app, "form_step1_rows") is not None
    with pytest.raises(KeyError):
        _widget(app, "form_step1_cutoff")


def test_orchestration_is_inferred_from_the_declared_types(pipeline):
    """Picking a tool and a source is enough; the modes follow from the types."""
    drafts = pipeline.session_state["drafts"]
    assert drafts.get("step3").orchestration.mode == "filter"   # bool per element
    assert drafts.get("step3").orchestration.over == "step2"
    assert drafts.get("step4").orchestration.mode == "single"   # wants the column
    assert drafts.get("step4").sources == {"rows": "step3"}


def test_a_predicate_infers_filter_and_a_transform_infers_map(app):
    """Both read one element; the return type separates them."""
    _wire(app, "step1", "load_batches")
    _wire(app, "step2", "identity", param="value", source="step1", mode="expand")

    _wire(app, "step3", "above_cutoff", param="value", source="step2")   # -> bool
    assert app.session_state["drafts"].get("step3").orchestration.mode == "filter"


def test_collecting_a_fan_out_reads_through_ok(app):
    """A MapResult is not a list, so a column-taking tool needs `.ok`."""
    _wire(app, "step1", "load_batches")
    _wire(app, "step2", "identity", param="value", source="step1", mode="map")
    _wire(app, "step3", "summarize", param="rows", source="step2")

    draft = app.session_state["drafts"].get("step3")
    assert draft.orchestration.mode == "single"
    assert draft.sources == {"rows": "step2.ok"}


def test_a_hand_picked_mode_is_not_overwritten(app):
    """`auto` infers; anything else sticks."""
    _wire(app, "step1", "load_batches")
    _wire(app, "step2", "above_cutoff", param="value", source="step1", mode="map")

    draft = app.session_state["drafts"].get("step2")
    assert draft.mode_locked is True
    assert draft.orchestration.mode == "map"        # not the inferred 'filter'


def test_defaulted_arguments_are_not_on_the_card(pipeline):
    """`cutoff` has a default, so it lives in the Tool settings popover."""
    on_card = {w.key for group in (pipeline.selectbox, pipeline.number_input)
               for w in group if w.key and w.key.startswith("src_step3")}
    assert on_card == {"src_step3_value"}          # only the positional input
    assert _widget(pipeline, "form_step3_cutoff").value == 20.0   # in the popover


def test_staged_cells_announce_type_and_shape(pipeline):
    staged = [df.value.to_dict("records")[0] for df in pipeline.dataframe
              if df.value.to_dict("records")
              and df.value.to_dict("records")[0].get("state") == "staged"]
    by_step = {row["output"]: row for row in staged}

    assert by_step["step1"]["type"] == "list[list[float]]"
    assert by_step["step2"]["shape"] == "one cell per item produced from step1"
    assert by_step["step3"]["shape"] == "the items of step2 that pass"
    assert by_step["step4"]["type"] == "dict"


def test_running_the_pipeline_produces_each_stage(pipeline):
    next(b for b in pipeline.button if "Run all" in b.label).click().run()
    _assert_clean(pipeline, "run all")

    workflow = pipeline.session_state["wf"]
    statuses = {s.step_id: s.status.value for s in workflow.steps}
    assert set(statuses.values()) == {"completed"}

    batches = workflow["step1"].output.value
    readings = workflow["step2"].output.value
    kept = workflow["step3"].output.value
    stats = workflow["step4"].output.value

    assert len(readings) == sum(len(b) for b in batches)   # expand flattened
    assert set(kept) <= set(readings)                      # filter kept a subset
    assert stats["count"] == len(kept)                     # summarize saw them all
    assert stats["total"] == pytest.approx(sum(kept))


def test_loading_the_sample_keeps_every_step_completed(app):
    """Re-authoring a loaded workflow must not reset steps that already ran."""
    next(b for b in app.button if "sample" in b.label.lower()).click().run()
    _assert_clean(app, "load sample")

    workflow = app.session_state["wf"]
    statuses = {s.step_id: s.status.value for s in workflow.steps}
    assert statuses == {f"step{i}": "completed" for i in range(1, 5)}
    assert workflow["step4"].output.value["count"] == len(workflow["step3"].output.value)


def _run_step(app, step_id):
    next(b for b in app.button if b.key == f"run_{step_id}").click().run()


def test_per_step_run_button_actually_runs_the_step(app):
    """The card is a fragment, so its run request must survive the rerun.

    A queue held in a local list would be discarded before the executing pass
    ever saw it, and the button would silently do nothing.
    """
    _add_step(app)
    _widget(app, "op_step1").set_value("load_batches").run()
    _run_step(app, "step1")
    _assert_clean(app, "run step1")

    step = app.session_state["wf"]["step1"]
    assert step.status.value == "completed"
    assert step.output.value


def test_custom_input_view_arguments_reach_the_run(app):
    """load_batches draws its own sliders; their values must be what runs."""
    _add_step(app)
    _widget(app, "op_step1").set_value("load_batches").run()
    _widget(app, "form_step1_batches").set_value(2).run()
    _widget(app, "form_step1_per").set_value(3).run()
    _run_step(app, "step1")

    batches = app.session_state["wf"]["step1"].output.value
    assert len(batches) == 2
    assert all(len(b) == 3 for b in batches)


def test_each_stage_can_be_run_on_its_own(pipeline):
    """Running steps one at a time must give the same result as Run all."""
    for step_id in ("step1", "step2", "step3", "step4"):
        _run_step(pipeline, step_id)
        _assert_clean(pipeline, f"run {step_id}")

    workflow = pipeline.session_state["wf"]
    assert {s.status.value for s in workflow.steps} == {"completed"}
    assert workflow["step4"].output.value["count"] == len(workflow["step3"].output.value)


def test_sources_are_shown_as_shell_style_references(app):
    """A step reference is a variable, so it reads as ${step1}."""
    _wire(app, "step1", "load_batches")
    _wire(app, "step2", "above_cutoff")

    picker = _widget(app, "src_step2_value")
    assert picker.options == ["(a value)", "${step1}"]


def test_the_three_settings_popovers_are_all_present(pipeline):
    """Tool settings, orchestration and execution sit together beside the inputs."""
    assert _widget(pipeline, "form_step3_cutoff") is not None   # tool settings
    assert _widget(pipeline, "orch_step3_mode") is not None     # orchestration
    assert _widget(pipeline, "exec_step3_run") is not None      # execution
