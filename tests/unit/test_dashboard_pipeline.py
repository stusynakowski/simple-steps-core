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


def _wire(app, step_id, tool, *, source=None, verb=None):
    """Choose a tool, then say where its data comes from and how to apply it."""
    _add_step(app)
    _widget(app, f"op_{step_id}").set_value(tool).run()
    if source is not None:
        _widget(app, f"data_{step_id}_source").set_value(source).run()
    if verb is not None:
        _widget(app, f"data_{step_id}_verb").set_value(verb).run()


@pytest.fixture
def pipeline(app):
    """The full chain: load -> expand -> filter -> reduce."""
    _wire(app, "step1", "load_batches")
    _wire(app, "step2", "unpack_batch", source="step1", verb="expand")
    _wire(app, "step3", "above_cutoff", source="step2", verb="filter")
    _wire(app, "step4", "accumulate_stats", source="step3", verb="reduce")
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


def test_verbs_are_single_words(app):
    """The card is ~260px wide; a verb has to fit in a selectbox that narrow."""
    _wire(app, "step1", "load_batches")
    _wire(app, "step2", "unpack_batch", source="step1")
    assert _widget(app, "data_step2_verb").options == [
        "once", "map", "filter", "expand", "reduce"
    ]


def test_a_source_step_shows_no_routing_controls(app):
    """Nothing to read from and nothing to iterate, so neither field appears."""
    _wire(app, "step1", "load_batches")
    for absent in ("data_step1_source", "data_step1_verb"):
        with pytest.raises(KeyError):
            _widget(app, absent)


def test_only_unrouted_arguments_get_a_widget(app):
    """The parameter carrying the data is never also asked for as an argument."""
    _wire(app, "step1", "load_batches")
    _wire(app, "step2", "above_cutoff", source="step1", verb="filter")

    form_keys = {w.key for group in (app.selectbox, app.number_input, app.text_input)
                 for w in group if w.key and w.key.startswith("form_step2")}
    assert form_keys == {"form_step2_cutoff"}      # `value` is supplied per item
    assert _widget(app, "form_step2_cutoff").value == 20.0   # a real number input


def test_routing_is_one_pair_of_controls_in_every_mode(app):
    """The same two fields answer 'which step feeds this', whatever the mode."""
    _wire(app, "step1", "load_batches")
    _wire(app, "step2", "above_cutoff", source="step1")        # 'once'

    draft = app.session_state["drafts"].get("step2")
    assert draft.orchestration.mode == "single"
    assert draft.sources == {"value": "step1"}
    assert draft.orchestration.over is None

    _widget(app, "data_step2_verb").set_value("filter").run()
    draft = app.session_state["drafts"].get("step2")
    assert draft.orchestration.mode == "filter"
    assert draft.orchestration.over == "step1"     # recorded as `over` now
    assert draft.sources == {}                     # orchestrator supplies it
    assert _widget(app, "data_step2_source").value == "step1"   # field did not move


def test_staged_cells_announce_type_and_shape(pipeline):
    staged = [df.value.to_dict("records")[0] for df in pipeline.dataframe
              if df.value.to_dict("records")
              and df.value.to_dict("records")[0].get("state") == "staged"]
    by_step = {row["output"]: row for row in staged}

    assert by_step["step1"]["type"] == "list[list[float]]"
    assert by_step["step2"]["type"] == "list[float]"
    assert by_step["step2"]["shape"] == "one cell per item produced from step1"
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
    assert stats["count"] == len(kept)                     # collapse reduced them
    assert stats["minimum"] == min(kept)
    assert stats["maximum"] == max(kept)


def test_details_live_behind_popovers(pipeline):
    """Item binding and conduct are one click away, not on the card."""
    # they exist (inside popovers) but no source-picker indirection remains
    assert _widget(pipeline, "orch_step3_item").value == "(auto)"
    assert _widget(pipeline, "exec_step3_conc").value == 1
    for gone in ("src_step3_value", "src_step3_cutoff", "src_step2_batch"):
        with pytest.raises(KeyError):
            _widget(pipeline, gone)


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
