"""The dashboard's panels and editing model, tested without a browser.

``DraftWorkflow`` is pure Python, so the step-management rules that used to live
in Streamlit callbacks are now directly testable.
"""

import pytest

from simple_steps_core import (
    CoreEngine,
    Operation,
    OrchestrationConfig,
    StepExecutionConfig,
    ToolRegistry,
    Workflow,
    register_orchestrators,
)
from simple_steps_core.streamlit.panels import DraftStep, DraftWorkflow

from test_components import FakeSt


def _registry():
    registry = ToolRegistry()
    register_orchestrators(registry)

    def mk(n: int) -> list[int]:
        return list(range(n))

    def scale(x: int) -> int:
        return x * 2

    registry.register("mk", mk, "Make a list.")
    registry.register("scale", scale, "Double it.")
    return registry


# ── DraftStep ────────────────────────────────────────────────────────────
def test_draft_step_compiles_to_operation():
    draft = DraftStep(id="step1", op="mk", arguments={"n": 3})
    spec = draft.to_operation()
    assert isinstance(spec, Operation)
    assert spec.name == "mk" and spec.arguments == {"n": 3}


def test_draft_step_without_a_tool_cannot_compile():
    with pytest.raises(ValueError, match="no tool selected"):
        DraftStep(id="step1").to_operation()


def test_references_layer_over_literals():
    draft = DraftStep(id="step2", op="scale", arguments={"x": 1}, sources={"x": "step1"})
    assert draft.to_operation().arguments == {"x": "step1"}


def test_is_fanned_out_follows_orchestration_mode():
    assert not DraftStep(id="s", op="mk").is_fanned_out
    assert DraftStep(id="s", op="mk",
                     orchestration=OrchestrationConfig(mode="map", over="step1")).is_fanned_out


# ── DraftWorkflow mutation ───────────────────────────────────────────────
def test_add_uses_step_prefixed_ids():
    """Ids must stay `step*` — the reference grammar resolves nothing else."""
    drafts = DraftWorkflow()
    assert [drafts.add().id for _ in range(3)] == ["step1", "step2", "step3"]


def test_remove_and_clear():
    drafts = DraftWorkflow()
    for _ in range(3):
        drafts.add()
    drafts.remove(["step2"])
    assert drafts.ids() == ["step1", "step3"]
    drafts.clear()
    assert len(drafts) == 0 and drafts.step_seq == 0


def test_swap_exchanges_positions():
    drafts = DraftWorkflow()
    for _ in range(3):
        drafts.add()
    drafts.swap("step1", "step3")
    assert drafts.ids() == ["step3", "step2", "step1"]


def test_group_needs_at_least_two_steps():
    drafts = DraftWorkflow()
    a, b = drafts.add(), drafts.add()
    assert drafts.group([a.id]) is None
    stage = drafts.group([a.id, b.id])
    assert a.stage == stage == b.stage
    drafts.ungroup([a.id])
    assert a.stage is None and b.stage == stage


def test_prior_to_only_lists_earlier_authored_steps():
    drafts = DraftWorkflow()
    first, _untooled, third = drafts.add(), drafts.add(), drafts.add()
    first.op, third.op = "mk", "scale"        # the middle row has no tool yet
    assert drafts.prior_to(third.id) == ["step1"]
    assert drafts.prior_to(first.id) == []


# ── authoring into a workflow ────────────────────────────────────────────
def test_author_into_syncs_and_reports_incomplete_rows():
    registry = _registry()
    wf = Workflow(CoreEngine(registry), session_id="t")
    drafts = DraftWorkflow()

    first = drafts.add()
    first.op, first.arguments = "mk", {"n": 3}
    second = drafts.add()
    second.op = "scale"
    # map chosen before `over` — normal while editing, rejected by the library
    second.orchestration = OrchestrationConfig(mode="map")

    problems = drafts.author_into(wf)
    assert "step1" in wf
    assert "step2" not in wf
    assert "over" in problems["step2"]


def test_author_into_removes_deleted_steps():
    registry = _registry()
    wf = Workflow(CoreEngine(registry), session_id="t")
    drafts = DraftWorkflow()
    draft = drafts.add()
    draft.op, draft.arguments = "mk", {"n": 1}
    drafts.author_into(wf)
    assert "step1" in wf

    drafts.remove(["step1"])
    drafts.author_into(wf)
    assert "step1" not in wf


def test_round_trip_through_a_workflow():
    registry = _registry()
    wf = Workflow(CoreEngine(registry), session_id="t")
    wf["step1"] = Operation(step_id="step1", name="mk", arguments={"n": 3}, stage="load")
    wf["step2"] = Operation(
        step_id="step2", name="scale", arguments={"x": "step1"},
        orchestration=OrchestrationConfig(mode="map", over="step1"),
        execution=StepExecutionConfig(concurrency=4),
    )

    drafts = DraftWorkflow.from_workflow(wf)
    assert drafts.ids() == ["step1", "step2"]
    second = drafts.get("step2")
    assert second.sources == {"x": "step1"}          # reference recognised
    assert second.execution.concurrency == 4
    assert second.orchestration.mode == "map"

    rebuilt = Workflow(CoreEngine(registry), session_id="t2")
    assert drafts.author_into(rebuilt) == {}
    assert rebuilt["step2"].spec == wf["step2"].spec


# ── panels render ────────────────────────────────────────────────────────
def test_step_card_renders_and_returns_the_draft():
    from simple_steps_core.streamlit.panels import render_step_card

    registry = _registry()
    draft = DraftStep(id="step1", op="mk", arguments={"n": 3})
    st = FakeSt()
    out = render_step_card(st, draft, key="c", registry=registry,
                           tool_ids=["mk", "scale"], prior=[], step=None)
    assert out is draft
    assert st.payloads("dataframe")[0].iloc[0]["type"] == "list[int]"


def test_step_card_run_action_is_caller_supplied():
    from simple_steps_core.streamlit.panels import render_step_card

    registry = _registry()
    draft = DraftStep(id="step1", op="mk", arguments={"n": 3})
    ran = []
    st = FakeSt(clicks={"run_step1"})
    render_step_card(st, draft, key="c", registry=registry,
                     tool_ids=["mk"], prior=[], step=None, on_run=ran.append)
    assert [d.id for d in ran] == ["step1"]


def test_problems_panel_surfaces_library_messages():
    from simple_steps_core.streamlit.panels import render_problems

    st = FakeSt()
    render_problems(st, {"step2": "orchestration.over is required"})
    assert "step2" in st.text_blob() and "over" in st.text_blob()
