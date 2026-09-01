"""Tests for static reference type checking (check_reference_types)."""

from simple_steps_core import (
    CoreEngine,
    OperationRegistry,
    StepSpec,
    Workflow,
    check_reference_types,
    register_orchestrators,
)


def _wf():
    registry = OperationRegistry()

    def make_list(n: int) -> list[int]:
        return list(range(n))

    def total(data: list[int]) -> int:
        return sum(data)

    def label(text: str) -> str:
        return text

    registry.register("make_list", make_list)
    registry.register("total", total)
    registry.register("label", label)
    register_orchestrators(registry)
    return Workflow(CoreEngine(registry), session_id="s"), registry


def test_valid_references_have_no_issues():
    wf, registry = _wf()
    wf.add(StepSpec(step_id="step_nums", name="make_list", arguments={"n": 5}))
    wf.add(StepSpec(step_id="step_sum", name="total", arguments={"data": "step_nums"}))
    assert check_reference_types(wf, registry) == []


def test_unknown_step_is_flagged():
    wf, registry = _wf()
    wf.add(StepSpec(step_id="step_sum", name="total", arguments={"data": "step_missing"}))
    issues = check_reference_types(wf, registry)
    assert len(issues) == 1
    assert issues[0]["step_id"] == "step_sum"
    assert "unknown step" in issues[0]["reason"]


def test_forward_reference_is_flagged():
    wf, registry = _wf()
    # step_sum references step_nums which is defined *after* it.
    wf.add(StepSpec(step_id="step_sum", name="total", arguments={"data": "step_nums"}))
    wf.add(StepSpec(step_id="step_nums", name="make_list", arguments={"n": 3}))
    issues = check_reference_types(wf, registry)
    assert any("does not run before it" in i["reason"] for i in issues)


def test_type_mismatch_is_flagged():
    wf, registry = _wf()
    wf.add(StepSpec(step_id="step_nums", name="make_list", arguments={"n": 5}))
    # `label` expects a str, but step_nums produces a list.
    wf.add(StepSpec(step_id="step_lbl", name="label", arguments={"text": "step_nums"}))
    issues = check_reference_types(wf, registry)
    assert any(i["step_id"] == "step_lbl" and "type mismatch" in i["reason"] for i in issues)


def test_map_over_reference_is_compatible():
    wf, registry = _wf()
    wf.add(StepSpec(step_id="step_nums", name="make_list", arguments={"n": 4}))
    wf.add(StepSpec(step_id="step_sum", name="total", orchestration={"mode": "collapse", "over": "step_nums", "initial": 0}))
    # `over` is a list reference into an orchestrator; no false mismatch.
    assert all(i["step_id"] != "step_sum" or "type mismatch" not in i["reason"]
               for i in check_reference_types(wf, registry))
