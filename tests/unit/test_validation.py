"""Tests for tool-aware validation (operations layer)."""

import pytest

from simple_steps_core.domain.models import ToolCall
from simple_steps_core.operations.registry import OperationRegistry
from simple_steps_core.operations.validation import ValidationError, validate_tool_call


def _registry():
    registry = OperationRegistry()

    def load_csv(filepath: str, limit: int = 100):
        return [filepath, limit]

    registry.register("load_csv", load_csv)
    return registry


def test_valid_call_passes():
    registry = _registry()
    validate_tool_call(
        ToolCall(operation_id="load_csv", arguments={"filepath": "a.csv"}),
        registry,
    )


def test_unknown_operation_raises():
    registry = _registry()
    with pytest.raises(ValidationError):
        validate_tool_call(ToolCall(operation_id="missing"), registry)


def test_missing_required_argument_raises():
    registry = _registry()
    with pytest.raises(ValidationError):
        validate_tool_call(ToolCall(operation_id="load_csv", arguments={}), registry)


def test_unexpected_argument_raises():
    registry = _registry()
    with pytest.raises(ValidationError):
        validate_tool_call(
            ToolCall(operation_id="load_csv", arguments={"filepath": "a", "nope": 1}),
            registry,
        )


def test_reference_token_satisfies_required_argument():
    registry = _registry()
    # A reference stands in for a required value; validation must allow it.
    validate_tool_call(
        ToolCall(operation_id="load_csv", arguments={"filepath": "step1"}),
        registry,
    )
