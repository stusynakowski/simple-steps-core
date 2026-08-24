"""
JSON Schema generation
======================

Turns a registered function's signature and type annotations into a JSON
Schema for its **data** parameters (the contract exposed to MCP, LLM
function-calling, and the UI). Resource parameters are excluded; the real
value of a reference token is only known at run time, so references simply
satisfy any data slot.

Pydantic does the heavy lifting (``create_model(...).model_json_schema()``),
covering scalars, collections, unions, ``Literal``/enums, and nested models.
Because some MCP clients do not resolve ``$ref``, generated schemas are
dereferenced (``$defs`` inlined) before being returned.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, get_type_hints

from pydantic import ConfigDict, create_model

from .dependencies import ResourceMarker


def _resolved_hints(fn: Callable) -> dict[str, Any]:
    """Best-effort resolution of a function's annotations to real types.

    Modules using ``from __future__ import annotations`` expose string
    annotations; ``get_type_hints`` evaluates them in the function's globals.
    """
    try:
        return get_type_hints(fn)
    except Exception:
        return {}


def classify_params(fn: Callable, *, skip: int = 0) -> tuple[list[str], list[str]]:
    """Return ``(data_param_names, resource_param_names)`` for *fn*.

    ``skip`` drops leading positional parameters (e.g. an orchestrator handle).
    """
    signature = inspect.signature(fn)
    data: list[str] = []
    resource: list[str] = []
    for index, (name, parameter) in enumerate(signature.parameters.items()):
        if index < skip:
            continue
        if isinstance(parameter.default, ResourceMarker):
            resource.append(name)
        else:
            data.append(name)
    return data, resource


def dereference(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline ``$defs``/``definitions`` ``$ref`` entries for client compatibility.

    Self-referential models are left as-is at the point of recursion to avoid
    infinite expansion; this is rare for tool arguments.
    """
    defs = {**schema.get("$defs", {}), **schema.get("definitions", {})}

    def resolve(node: Any, seen: frozenset[str]) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith(("#/$defs/", "#/definitions/")):
                name = ref.rsplit("/", 1)[-1]
                if name in seen or name not in defs:
                    return {k: v for k, v in node.items() if k != "$ref"}
                return resolve(defs[name], seen | {name})
            return {
                key: resolve(value, seen)
                for key, value in node.items()
                if key not in ("$defs", "definitions")
            }
        if isinstance(node, list):
            return [resolve(item, seen) for item in node]
        return node

    resolved = resolve(schema, frozenset())
    return resolved if isinstance(resolved, dict) else schema


def build_input_schema(fn: Callable, *, skip: int = 0) -> dict[str, Any]:
    """Build a dereferenced JSON Schema for *fn*'s data parameters.

    Falls back to a permissive object schema if a parameter's type cannot be
    schematized (e.g. an opaque or unresolved annotation).
    """
    signature = inspect.signature(fn)
    hints = _resolved_hints(fn)
    fields: dict[str, tuple[Any, Any]] = {}
    considered: list[tuple[str, inspect.Parameter]] = []
    for index, (name, parameter) in enumerate(signature.parameters.items()):
        if index < skip:
            continue
        if isinstance(parameter.default, ResourceMarker):
            continue  # resources are injected, never part of the schema
        considered.append((name, parameter))
        annotation = hints.get(name)
        if annotation is None:
            annotation = parameter.annotation if parameter.annotation is not inspect._empty else Any
        if isinstance(annotation, str):  # unresolved forward reference
            annotation = Any
        default = ... if parameter.default is inspect._empty else parameter.default
        fields[name] = (annotation, default)

    try:
        model = create_model(
            f"{fn.__name__}_Input",
            __config__=ConfigDict(extra="forbid"),
            **fields,
        )
        return dereference(model.model_json_schema())
    except Exception:
        return _fallback_schema(considered)


def _fallback_schema(params: list[tuple[str, inspect.Parameter]]) -> dict[str, Any]:
    """A permissive object schema built from parameter names only."""
    properties = {name: {} for name, _ in params}
    required = [name for name, p in params if p.default is inspect._empty]
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def build_output_schema(fn: Callable) -> dict[str, Any] | None:
    """Build a JSON Schema for *fn*'s return type, or ``None`` if unannotated.

    Primitives and collections are wrapped under a ``result`` key so the root
    is always an object, matching the MCP structured-output convention.
    """
    hints = _resolved_hints(fn)
    return_annotation = hints.get("return", inspect.signature(fn).return_annotation)
    if return_annotation is inspect.Signature.empty or return_annotation is None:
        return None
    if isinstance(return_annotation, str):
        return None
    try:
        model = create_model(f"{fn.__name__}_Output", result=(return_annotation, ...))
        return dereference(model.model_json_schema())
    except Exception:
        # Non-schematizable return types (e.g. opaque objects) are acceptable.
        return None
