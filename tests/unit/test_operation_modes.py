"""Tests for the dual-mode Operation wrapper and decorator."""

from simple_steps_core.domain.models import ToolCall
from simple_steps_core.operations.registry import OperationRegistry, register_operation


def test_register_returns_dual_mode_operation():
    registry = OperationRegistry()

    def add(a: int, b: int = 1):
        return a + b

    op = registry.register("add", add)

    # Deferred mode: calling builds a ToolCall, nothing runs.
    call = op(a=2, b=3)
    assert isinstance(call, ToolCall)
    assert call.operation_id == "add"
    assert call.arguments == {"a": 2, "b": 3}

    # Immediate mode: .run executes the underlying function.
    assert op.run(a=2, b=3) == 5


def test_decorator_returns_operation_wrapper():
    @register_operation(operation_id="greet")
    def greet(name: str):
        return f"hi {name}"

    call = greet(name="sam")
    assert isinstance(call, ToolCall)
    assert call.arguments == {"name": "sam"}
    assert greet.run(name="sam") == "hi sam"
