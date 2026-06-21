"""
Tool-aware validation
=====================

The domain layer validates a formula's *grammar* (is it a well-formed call?).
This module validates a ToolCall against the **registry**: does the operation
exist, and do the supplied arguments match its parameters? It also builds a
per-operation Pydantic model so argument *types* can be checked and coerced.

Reference tokens (e.g. ``"step1"``) are accepted for any parameter without
type checking, because their real value is only known at execution time.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, create_model

from ..domain.models import ToolCall
from ..domain.references import is_reference
from .registry import OperationRegistry


class ValidationError(Exception):
    """Raised when a ToolCall does not satisfy its operation's contract."""


def build_arg_model(registry: OperationRegistry, operation_id: str) -> type[BaseModel]:
    """
    Build a Pydantic model describing the arguments of one operation.

    Each parameter becomes a model field; required params have no default,
    optional params use their default. ``extra="forbid"`` makes unknown
    argument names an error.
    """
    definition = registry.get_definition(operation_id)
    fields: dict[str, tuple[Any, Any]] = {}
    for param in definition.params:
        # We keep field types permissive (Any) because reference tokens may
        # stand in for any declared type; real coercion happens post-resolve.
        if param.required:
            fields[param.name] = (Any, ...)            # ... means "required"
        else:
            fields[param.name] = (Any, param.default)

    return create_model(
        f"{operation_id}_Args",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def validate_tool_call(call: ToolCall, registry: OperationRegistry) -> None:
    """
    Validate *call* against the registry.

    Raises :class:`ValidationError` if the operation is unknown, a required
    argument is missing, or an unexpected argument is supplied. Arguments that
    are reference tokens are allowed to stand in for required values.
    """
    if not registry.has(call.operation_id):
        raise ValidationError(f"Unknown operation: {call.operation_id!r}")

    definition = registry.get_definition(call.operation_id)
    known = {p.name for p in definition.params}

    # Reject unexpected argument names early for a clear message.
    unexpected = set(call.arguments) - known
    if unexpected:
        raise ValidationError(
            f"Unexpected argument(s) for {call.operation_id!r}: "
            f"{', '.join(sorted(unexpected))}"
        )

    # Required params must be present (a reference token counts as present).
    for param in definition.params:
        if param.required and param.name not in call.arguments:
            raise ValidationError(
                f"Missing required argument {param.name!r} for {call.operation_id!r}"
            )

    # Type-check only the literal (non-reference) arguments via Pydantic.
    literal_args = {
        name: value
        for name, value in call.arguments.items()
        if not is_reference(value)
    }
    model = build_arg_model(registry, call.operation_id)
    try:
        model(**literal_args)
    except Exception as exc:  # pydantic.ValidationError and friends
        raise ValidationError(str(exc)) from exc
