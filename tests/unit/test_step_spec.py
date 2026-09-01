"""Tests for the structured StepSpec (inline orchestration) and its compilation."""

import pytest

from simple_steps_core import (
    CoreEngine,
    ExecutionConfig,
    MapResult,
    OperationRegistry,
    OrchestrationConfig,
    StepSpec,
    StepStatus,
    ToolCall,
    Workflow,
    register_orchestrators,
)


def _engine():
    registry = OperationRegistry()

    def make_list(n: int) -> list[int]:
        return list(range(n))

    def double(x: int) -> int:
        return x * 2

    def add(acc: int, item: int) -> int:
        return acc + item

    registry.register("make_list", make_list)
    registry.register("double", double)
    registry.register("add", add)
    register_orchestrators(registry)
    return CoreEngine(registry)


def test_single_spec_compiles_to_direct_call():
    spec = StepSpec(step_id="s1", name="make_list", arguments={"n": 3})
    assert spec.to_tool_call() == ToolCall(operation_id="make_list", arguments={"n": 3})


def test_map_spec_compiles_to_orchestrator_call():
    spec = StepSpec(
        step_id="s2",
        name="double",
        orchestration=OrchestrationConfig(mode="map", over="s1", concurrency=4),
    )
    call = spec.to_tool_call()
    assert call.operation_id == "map"
    assert call.arguments == {
        "over": "s1",
        "op": "double",
        "concurrency": 4,
        "on_error": "collect",
        "retries": 0,
    }


def test_collapse_spec_passes_initial_only():
    spec = StepSpec(
        step_id="s3",
        name="add",
        orchestration=OrchestrationConfig(mode="collapse", over="s2", initial=0),
    )
    call = spec.to_tool_call()
    assert call.operation_id == "collapse"
    assert call.arguments == {"over": "s2", "op": "add", "initial": 0}


def test_over_required_for_orchestrated_modes():
    with pytest.raises(ValueError):
        StepSpec(step_id="s", name="double", orchestration=OrchestrationConfig(mode="map")).to_tool_call()


def test_over_forbidden_for_single_mode():
    with pytest.raises(ValueError):
        StepSpec(step_id="s", name="double", orchestration=OrchestrationConfig(over="s1")).to_tool_call()


def test_shared_args_compile_into_orchestrator_call():
    spec = StepSpec(
        step_id="s",
        name="scale",
        arguments={"factor": 2},
        orchestration=OrchestrationConfig(mode="map", over="s1"),
    )
    call = spec.to_tool_call()
    assert call.operation_id == "map"
    assert call.arguments["op"] == "scale"
    assert call.arguments["args"] == {"factor": 2}   # shared constants passed through


def test_workflow_runs_step_specs_with_inline_map():
    engine = _engine()
    wf = Workflow(engine, session_id="spec")

    wf.add(StepSpec(step_id="step_nums", name="make_list", arguments={"n": 4}))
    wf.add(
        StepSpec(
            step_id="step_doubled",
            name="double",
            orchestration=OrchestrationConfig(mode="map", over="step_nums"),
        )
    )
    wf.run()

    result = wf["step_doubled"].output.value
    assert isinstance(result, MapResult)
    assert result.ok == [0, 2, 4, 6]
    # The structured intent is retained on the step for tracing.
    assert wf["step_doubled"].spec.orchestration.mode == "map"


def test_execution_config_defaults_to_manual():
    spec = StepSpec(step_id="s", name="double")
    assert spec.execution == ExecutionConfig(mode="sync", run="manual")


def test_run_stage_runs_only_that_stage():
    engine = _engine()
    wf = Workflow(engine, session_id="stages")
    wf.add(StepSpec(step_id="step_a", name="make_list", arguments={"n": 3}, stage=0))
    wf.add(StepSpec(step_id="step_b", name="double",
                    orchestration=OrchestrationConfig(mode="map", over="step_a"), stage=0))
    wf.add(StepSpec(step_id="step_c", name="make_list", arguments={"n": 2}, stage=1))

    assert wf.stages() == [0, 1]
    assert [s.step_id for s in wf.steps_in_stage(0)] == ["step_a", "step_b"]

    wf.run_stage(0)
    assert wf["step_a"].status is StepStatus.COMPLETED
    assert wf["step_b"].status is StepStatus.COMPLETED
    assert wf["step_c"].status is StepStatus.PENDING   # stage 1 untouched

    wf.run_stage(1)
    assert wf["step_c"].output.value == [0, 1]


def test_run_by_stages_runs_everything_in_stage_order():
    engine = _engine()
    wf = Workflow(engine, session_id="stages2")
    wf.add(StepSpec(step_id="step_a", name="make_list", arguments={"n": 4}, stage=0))
    wf.add(StepSpec(step_id="step_b", name="double",
                    orchestration=OrchestrationConfig(mode="map", over="step_a"), stage=1))
    wf.run_by_stages()
    assert wf["step_b"].output.value.ok == [0, 2, 4, 6]


def test_map_shared_args_flow_to_each_item():
    registry = OperationRegistry()

    def make_list(n: int) -> list[int]:
        return list(range(n))

    def scale(x: int, factor: int) -> int:
        return x * factor

    registry.register("make_list", make_list)
    registry.register("scale", scale)
    register_orchestrators(registry)

    wf = Workflow(CoreEngine(registry), session_id="shared")
    wf.add(StepSpec(step_id="step_nums", name="make_list", arguments={"n": 4}))
    wf.add(StepSpec(step_id="step_scaled", name="scale",
                    orchestration=OrchestrationConfig(mode="map", over="step_nums"),
                    arguments={"factor": 10}))
    wf.run()
    assert wf["step_scaled"].output.value.ok == [0, 10, 20, 30]


