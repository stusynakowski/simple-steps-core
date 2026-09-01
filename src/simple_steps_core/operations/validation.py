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

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, create_model

from ..domain.models import ToolCall
from ..domain.references import is_reference, split_reference
from .registry import OperationRegistry


class ValidationError(Exception):
    """Raised when a ToolCall does not satisfy its operation's contract."""


def build_arg_model(registry: OperationRegistry, operation_id: str) -> type[BaseModel]:
    """
    Build a Pydantic model describing the arguments of one operation.

    Every field is declared **optional** here on purpose: a required argument
    may legitimately arrive as a reference token (e.g. ``data="step1"``), which
    is stripped before this model runs because its real value is only known at
    execution time. Required-*presence* is therefore enforced separately in
    :func:`validate_tool_call`; this model only type-checks the literal values
    that are actually supplied. ``extra="forbid"`` still flags unknown names.
    """
    definition = registry.get_definition(operation_id)
    fields: dict[str, tuple[Any, Any]] = {}
    for param in definition.params:
        if param.kind == "resource":
            continue  # resources are injected at run time, never caller-supplied
        # We keep field types permissive (Any) because reference tokens may
        # stand in for any declared type; real coercion happens post-resolve.
        # Defaulting required params to None keeps a missing literal (it was a
        # reference) from being mis-reported as an absent required argument.
        fields[param.name] = (Any, param.default if not param.required else None)

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
    known = {p.name for p in definition.params if p.kind != "resource"}

    # Reject unexpected argument names early for a clear message.
    unexpected = set(call.arguments) - known
    if unexpected:
        raise ValidationError(
            f"Unexpected argument(s) for {call.operation_id!r}: "
            f"{', '.join(sorted(unexpected))}"
        )

    # Required data params must be present (a reference token counts as present).
    for param in definition.params:
        if param.kind == "resource":
            continue  # injected by the engine, not part of the tool call
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

    # Enforce guardrail argument constraints on literal values.
    enforce_arg_guardrails(call.operation_id, literal_args, definition.guardrails)


def enforce_arg_guardrails(operation_id: str, arguments: dict[str, Any], guardrails) -> None:
    """Check *arguments* against per-argument guardrails; raise on violation.

    Pass **literal** args at validation time, or **resolved** args (with former
    reference tokens replaced by their real values) at run time — the latter is
    how a reference's actual value is guarded.
    """
    if guardrails is None:
        return
    for name, value in arguments.items():
        rule = guardrails.arguments.get(name)
        if rule is None:
            continue
        if rule.enum is not None and value not in rule.enum:
            raise ValidationError(f"{name}={value!r} not in allowed values {rule.enum} for {operation_id!r}")
        if rule.minimum is not None and _lt(value, rule.minimum):
            raise ValidationError(f"{name}={value!r} is below minimum {rule.minimum} for {operation_id!r}")
        if rule.maximum is not None and _gt(value, rule.maximum):
            raise ValidationError(f"{name}={value!r} is above maximum {rule.maximum} for {operation_id!r}")
        if rule.min_length is not None and _len_or_none(value) is not None and len(value) < rule.min_length:
            raise ValidationError(f"{name} shorter than min_length {rule.min_length} for {operation_id!r}")
        if rule.max_length is not None and _len_or_none(value) is not None and len(value) > rule.max_length:
            raise ValidationError(f"{name} longer than max_length {rule.max_length} for {operation_id!r}")
        if rule.pattern is not None and not re.fullmatch(rule.pattern, str(value)):
            raise ValidationError(f"{name}={value!r} fails pattern {rule.pattern!r} for {operation_id!r}")


def _lt(value: Any, bound: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value < bound


def _gt(value: Any, bound: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > bound


def _len_or_none(value: Any) -> int | None:
    try:
        return len(value)
    except TypeError:
        return None


# ─────────────────────────────────────────────────────────────────────────
# Static reference type checking (best-effort, workflow-level)
# ─────────────────────────────────────────────────────────────────────────
_PY_JSON_TYPE = {
    str: "string", bool: "boolean", int: "integer",
    float: "number", list: "array", dict: "object", type(None): "null",
}


def _schema_types(schema: Any) -> set[str]:
    """The set of JSON-Schema ``type`` names a schema allows (best-effort)."""
    if not isinstance(schema, dict):
        return set()
    declared = schema.get("type")
    if declared is not None:
        return set(declared) if isinstance(declared, list) else {declared}
    types: set[str] = set()
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in schema.get(key, []):
            types |= _schema_types(sub)
    if not types and "enum" in schema:
        for value in schema["enum"]:
            name = _PY_JSON_TYPE.get(type(value))
            if name:
                types.add(name)
    return types


def _types_compatible(producer: dict, expected: dict) -> bool:
    """True if a value of *producer* type could satisfy an *expected* slot."""
    p = _schema_types(producer)
    e = _schema_types(expected)
    if not p or not e:
        return True  # unknown on either side -> don't flag
    if "integer" in p:
        p = p | {"number"}
    if "integer" in e:
        e = e | {"number"}
    pn, en = p - {"null"}, e - {"null"}
    if pn & en:
        return True
    return not pn and "null" in e  # producer is null-only into a nullable slot


def _referenced_output_schema(output_schema: dict | None, field: str | None) -> dict | None:
    """The schema of the value a reference points at, or None if indeterminate.

    Output schemas wrap the return type under ``result``; a dotted field only
    resolves statically when the return type is a model with that property.
    """
    if not output_schema:
        return None
    result = output_schema.get("properties", {}).get("result")
    if result is None:
        return None
    if field is None:
        return result
    props = result.get("properties")
    if isinstance(props, dict) and field in props:
        return props[field]
    return None


def check_reference_types(workflow, registry: OperationRegistry) -> list[dict]:
    """Best-effort static check of a workflow's step-output references.

    Returns a list of issues ``{step_id, argument, reason}``; empty means no
    detectable problems. Flags references to unknown steps, references to steps
    that do not run earlier, and definite output/input type mismatches. Cases
    that can't be typed statically (dotted fields on dicts, computed properties
    like ``.ok``) are skipped rather than falsely flagged.
    """
    steps = list(workflow.steps)
    order = {step.step_id: index for index, step in enumerate(steps)}
    issues: list[dict] = []
    for index, step in enumerate(steps):
        has_consumer = registry.has(step.call.operation_id)
        consumer = registry.get_definition(step.call.operation_id) if has_consumer else None
        for arg, value in step.call.arguments.items():
            if not is_reference(value):
                continue
            source, field = split_reference(value)
            if source not in order:
                issues.append({"step_id": step.step_id, "argument": arg,
                               "reason": f"references unknown step {source!r}"})
                continue
            if order[source] >= index:
                issues.append({"step_id": step.step_id, "argument": arg,
                               "reason": f"references {source!r} which does not run before it"})
                continue
            if consumer is None:
                continue
            producer_id = steps[order[source]].call.operation_id
            if not registry.has(producer_id):
                continue
            producer_type = _referenced_output_schema(
                registry.get_definition(producer_id).output_schema, field
            )
            expected = (consumer.input_schema.get("properties") or {}).get(arg)
            if producer_type is None or expected is None:
                continue
            if not _types_compatible(producer_type, expected):
                issues.append({
                    "step_id": step.step_id, "argument": arg,
                    "reason": (
                        f"type mismatch: {value} is "
                        f"{sorted(_schema_types(producer_type)) or ['unknown']} but "
                        f"{arg!r} expects {sorted(_schema_types(expected)) or ['unknown']}"
                    ),
                })
    return issues
