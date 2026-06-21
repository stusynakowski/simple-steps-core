"""End-to-end tests for the Workflow execution object."""

import pytest

from simple_steps_core.execution.engine import CoreEngine
from simple_steps_core.execution.workflow import Workflow
from simple_steps_core.domain.models import StepStatus
from simple_steps_core.operations.registry import OperationRegistry


def _engine():
    registry = OperationRegistry()

    def make_list(n: int):
        return list(range(n))

    def total(data: list):
        return sum(data)

    registry.register("make_list", make_list)
    registry.register("total", total)
    return CoreEngine(registry), registry


def test_workflow_runs_steps_in_order_with_references():
    engine, registry = _engine()
    make_list = registry.get_operation("make_list")
    total = registry.get_operation("total")

    wf = Workflow(engine, session_id="s")
    # Deferred operation calls produce ToolCalls assigned to step ids.
    wf["step1"] = make_list(n=4)
    wf["step2"] = total(data="step1")     # references step1's output

    wf.run()

    assert wf["step1"].status is StepStatus.COMPLETED
    assert wf["step1"].output.value == [0, 1, 2, 3]
    assert wf["step2"].status is StepStatus.COMPLETED
    assert wf["step2"].output.value == 6


def test_workflow_accepts_formula_strings():
    engine, _ = _engine()
    wf = Workflow(engine, session_id="s")
    wf["step1"] = "=make_list(n=3)"
    wf.run()
    assert wf["step1"].output.value == [0, 1, 2]


def test_failed_step_records_error_and_raises():
    engine, registry = _engine()

    def boom():
        raise RuntimeError("kaboom")

    registry.register("boom", boom)

    wf = Workflow(engine, session_id="s")
    wf["step1"] = "=boom()"
    with pytest.raises(RuntimeError):
        wf.run()

    assert wf["step1"].status is StepStatus.FAILED
    assert "kaboom" in (wf["step1"].error or "")


def test_workflow_json_roundtrip_preserves_steps():
    engine, _ = _engine()
    wf = Workflow(engine, session_id="s")
    wf["step1"] = "=make_list(n=2)"

    data = wf.to_json()
    restored = Workflow.from_json(data, engine, session_id="s")

    assert "step1" in restored
    assert restored["step1"].formula == wf["step1"].formula
