"""Tests for tool guardrails: metadata + argument enforcement."""

import pytest

from simple_steps_core import (
    ArgGuardrail,
    Guardrails,
    OperationRegistry,
    ToolCall,
    ValidationError,
    validate_tool_call,
)


def _registry():
    registry = OperationRegistry()

    def grade(score: int, kind: str = "A") -> str:
        return f"{kind}:{score}"

    registry.register(
        "grade",
        grade,
        guardrails=Guardrails(
            usage="Only for scores 0-100.",
            destructive=True,
            arguments={
                "score": ArgGuardrail(minimum=0, maximum=100),
                "kind": ArgGuardrail(enum=["A", "B", "C"]),
            },
        ),
    )
    return registry


def test_guardrails_stored_on_definition():
    d = _registry().get_definition("grade")
    assert d.guardrails is not None
    assert d.guardrails.usage == "Only for scores 0-100."
    assert d.guardrails.destructive is True
    assert d.guardrails.arguments["score"].maximum == 100


def test_guardrail_blocks_out_of_range():
    registry = _registry()
    with pytest.raises(ValidationError):
        validate_tool_call(ToolCall(operation_id="grade", arguments={"score": 150}), registry)
    with pytest.raises(ValidationError):
        validate_tool_call(ToolCall(operation_id="grade", arguments={"score": -1}), registry)


def test_guardrail_blocks_disallowed_enum():
    registry = _registry()
    with pytest.raises(ValidationError):
        validate_tool_call(
            ToolCall(operation_id="grade", arguments={"score": 10, "kind": "Z"}), registry
        )


def test_guardrail_allows_valid_values():
    registry = _registry()
    validate_tool_call(
        ToolCall(operation_id="grade", arguments={"score": 80, "kind": "B"}), registry
    )


def test_guardrail_skips_reference_tokens():
    registry = _registry()
    # A reference stands in for the value; it is checked at run time, not here.
    validate_tool_call(ToolCall(operation_id="grade", arguments={"score": "step1"}), registry)


def test_no_guardrails_is_a_noop():
    registry = OperationRegistry()

    def add(a: int, b: int) -> int:
        return a + b

    registry.register("add", add)
    validate_tool_call(ToolCall(operation_id="add", arguments={"a": 1, "b": 2}), registry)


def test_guardrail_enforced_on_resolved_reference_at_runtime():
    """A reference skips validation but its resolved value is guarded at run time."""
    from simple_steps_core import CoreEngine, StepSpec, Workflow

    registry = OperationRegistry()

    def make_list(n: int) -> list[int]:
        return list(range(n))

    def total(data: list[int]) -> int:
        return sum(data)

    registry.register("make_list", make_list)
    registry.register("total", total, guardrails=Guardrails(
        arguments={"data": ArgGuardrail(max_length=3)}
    ))

    wf = Workflow(CoreEngine(registry), session_id="rt")
    wf.add(StepSpec(step_id="step_nums", name="make_list", arguments={"n": 5}))   # length 5
    wf.add(StepSpec(step_id="step_sum", name="total", arguments={"data": "step_nums"}))

    with pytest.raises(Exception):   # the resolved list violates max_length=3
        wf.run()
    assert wf["step_sum"].status.value == "failed"

