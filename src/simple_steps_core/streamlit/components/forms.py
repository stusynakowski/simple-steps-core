"""
Argument form components
========================

The generic form builder: widgets derived entirely from a tool's contract —
JSON-Schema type picks the widget, ``guardrails.arguments`` constrains it, and
``ToolParam.kind`` decides whether a param is asked for at all.

A tool may override the whole form with its own ``ui={"streamlit": ...}`` input
view; :func:`render_tool_form` honors that first and falls back to the built
form. Nothing here is specific to any tool.
"""

from __future__ import annotations

import json
import re
from typing import Any

from simple_steps_core import Tool

from .tools import render_resource_params

__all__ = [
    "render_arg_combo",
    "tool_settings_popover",
    "render_tool_form",
    "render_literal_arg",
    "coerce_value",
    "check_rule",
    "build_help",
]


def coerce_value(value: Any, jtype: str | None):
    """Convert selectbox/custom input to the schema's expected type."""

    if value is None:
        return None

    if jtype == "integer":
        return int(value)

    if jtype == "number":
        return float(value)

    if jtype == "boolean":
        if isinstance(value, bool):
            return value

        lookup = {
            "true": True,
            "false": False,
        }

        key = str(value).strip().lower()

        if key not in lookup:
            raise ValueError("Must be true or false.")

        return lookup[key]

    if jtype in ("array", "object"):
        if isinstance(value, (list, dict)):
            return value
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError as exc:
            raise ValueError(f"must be valid JSON ({exc.msg})") from exc
        expected = list if jtype == "array" else dict
        if not isinstance(parsed, expected):
            raise ValueError(f"must be a JSON {'array' if jtype == 'array' else 'object'}")
        return parsed

    # string or unspecified type
    return str(value)


def build_help(param, prop: dict, rule=None) -> str | None:
    """One-line help string for a param, assembled from the tool contract."""
    parts: list[str] = []

    type_name = prop.get("type") or (param.type_name if param.type_name != "Any" else None)
    if type_name:
        parts.append(f"`{type_name}`")
    parts.append("required" if param.required else "optional")

    if rule is not None:
        if rule.minimum is not None:
            parts.append(f"min {rule.minimum:g}")
        if rule.maximum is not None:
            parts.append(f"max {rule.maximum:g}")
        if rule.min_length is not None:
            parts.append(f"min length {rule.min_length}")
        if rule.max_length is not None:
            parts.append(f"max length {rule.max_length}")
        if rule.pattern:
            parts.append(f"pattern `{rule.pattern}`")
        if rule.note:
            parts.append(rule.note)

    return " · ".join(parts) if parts else None


def check_rule(value: Any, rule) -> None:
    """Raise ValueError when *value* violates an ArgGuardrail. Mirrors core validation."""
    if rule is None or value is None:
        return

    if rule.enum is not None and value not in rule.enum:
        raise ValueError(f"must be one of {rule.enum}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if rule.minimum is not None and value < rule.minimum:
            raise ValueError(f"must be ≥ {rule.minimum:g}")
        if rule.maximum is not None and value > rule.maximum:
            raise ValueError(f"must be ≤ {rule.maximum:g}")

    if isinstance(value, str):
        if rule.min_length is not None and len(value) < rule.min_length:
            raise ValueError(f"must be at least {rule.min_length} characters")
        if rule.max_length is not None and len(value) > rule.max_length:
            raise ValueError(f"must be at most {rule.max_length} characters")
        if rule.pattern and re.search(rule.pattern, value) is None:
            raise ValueError(f"must match pattern {rule.pattern}")


def render_literal_arg(st, definition, param, *, key: str, default: Any = None) -> Any:
    """Render one widget for a data param, driven entirely by the tool contract.

    Widget choice comes from the param's JSON-Schema type; bounds, enums and
    lengths come from the tool's ``guardrails.arguments`` entry. Returns the
    coerced value, or ``None`` when the field is left empty / is invalid.
    """
    props = definition.input_schema.get("properties", {})
    rules = getattr(definition.guardrails, "arguments", {}) or {}
    prop = props.get(param.name, {})
    rule = rules.get(param.name)

    jtype = prop.get("type")
    enum = prop.get("enum") or (rule.enum if rule is not None and rule.enum else None)
    help_text = build_help(param, prop, rule)
    label = param.name
    wkey = f"{key}_{param.name}"

    # Seed: the step's cached value, then the signature default, then the schema default.
    seed = default
    if seed is None:
        seed = param.default
    if seed is None:
        seed = prop.get("default")

    if enum is not None:
        options = list(enum)
        return st.selectbox(
            label, options,
            index=options.index(seed) if seed in options else None,
            key=wkey, help=help_text, placeholder="choose a value…",
        )

    if jtype == "boolean":
        return st.checkbox(label, value=bool(seed), key=wkey, help=help_text)

    if jtype in ("integer", "number"):
        is_int = jtype == "integer"
        cast = int if is_int else float
        bounds: dict[str, Any] = {}
        if rule is not None and rule.minimum is not None:
            bounds["min_value"] = cast(rule.minimum)
        if rule is not None and rule.maximum is not None:
            bounds["max_value"] = cast(rule.maximum)
        if isinstance(seed, (int, float)) and not isinstance(seed, bool):
            base = cast(seed)
        else:
            base = bounds.get("min_value", cast(0))
        value = st.number_input(
            label, value=base, step=cast(1) if is_int else 0.1,
            key=wkey, help=help_text, **bounds,
        )
        return cast(value)

    if jtype in ("array", "object"):
        placeholder = "[1, 2, 3]" if jtype == "array" else '{"key": "value"}'
        text = st.text_area(
            label,
            value="" if seed is None else json.dumps(seed),
            key=wkey, height=68, placeholder=placeholder,
            help=f"{help_text} · JSON" if help_text else "JSON",
        )
        if not text.strip():
            return None
        try:
            value = coerce_value(text, jtype)
            check_rule(value, rule)
            return value
        except ValueError as exc:
            st.error(f"**{label}**: {exc}")
            return None

    # string, or an unannotated param
    text = st.text_input(
        label, value="" if seed is None else str(seed), key=wkey, help=help_text,
        max_chars=rule.max_length if rule is not None and rule.max_length else None,
    )
    if text == "":
        return None
    try:
        value = coerce_value(text, jtype)
        check_rule(value, rule)
        return value
    except ValueError as exc:
        st.error(f"**{label}**: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────
# Form rendering — the generic default renderer (takes `st` so it is testable)
# ─────────────────────────────────────────────────────────────────────────
def render_tool_form(
    st,
    operation: Tool,
    *,
    key: str,
    defaults: dict[str, Any] | None = None,
    available_steps: list[str] | None = None,
) -> dict[str, Any]:
    """Render a tool's argument form and return the collected arguments.

    Uses the tool's own ``ui.input("streamlit")`` view when present; otherwise
    builds a default form from the tool contract. Each data argument also offers
    a "use the output of an earlier step" reference picker.
    """
    defaults = defaults or {}
    available_steps = available_steps or []

    renderer = operation.ui.input("streamlit")
    if renderer is not None:
        return renderer(st, key=key, defaults=defaults) or {}

    definition = operation.definition
    render_resource_params(st, definition.params)
    args: dict[str, Any] = {}

    for param in definition.params:
        if param.kind != "data":
            continue  # resources are injected, never user-supplied

        # Reference vs literal: pick "(value)" or an earlier step's output.
        if available_steps:
            source = st.selectbox(
                f"{param.name} — source",
                ["(value)", *available_steps],
                key=f"{key}_{param.name}_src",
            )
            if source != "(value)":
                args[param.name] = source  # a step-id reference
                continue

        value = render_literal_arg(
            st, definition, param, key=key, default=defaults.get(param.name),
        )
        # Leaving an optional field empty means "use the tool's own default",
        # so don't pass None and override it.
        if value is None and not param.required:
            continue
        args[param.name] = value

    return args


def render_arg_combo(st, definition, param, *, key: str, default: Any = None,
                     prior_steps: list[str] | None = None,
                     bound: str | None = None) -> tuple[Any, str | None]:
    """One control per argument: type a value, or pick an earlier step.

    Returns ``(literal, source)`` — exactly one is set. Collapsing the old
    "source" picker and value widget into a single combo removes the ``(value)``
    indirection, at the cost of the typed widget's own affordances (a number's
    spinner, a bound slider). The type and its constraints move into the help
    text and are enforced on entry instead, so a bad value still cannot reach the
    workflow.
    """
    prior_steps = prior_steps or []
    props = definition.input_schema.get("properties", {})
    rules = getattr(definition.guardrails, "arguments", {}) or {}
    prop = props.get(param.name, {})
    rule = rules.get(param.name)

    jtype = prop.get("type")
    enum = prop.get("enum") or (rule.enum if rule is not None and rule.enum else None)

    # Seed: the bound step, then the typed literal, then the signature default.
    seed = bound if bound in prior_steps else default
    if seed is None:
        seed = param.default
    if seed is None:
        seed = prop.get("default")

    if enum is not None:
        choices = [*enum, *prior_steps]
        accept_new = False
    elif jtype == "boolean":
        choices = [True, False, *prior_steps]
        accept_new = False
    else:
        choices = ([seed] if seed is not None and seed not in prior_steps else [])
        choices = [*choices, *prior_steps]
        accept_new = True

    help_text = build_help(param, prop, rule)
    if prior_steps:
        help_text = f"{help_text} · or pick an earlier step" if help_text else \
            "Type a value, or pick an earlier step"

    chosen = st.selectbox(
        param.name, choices,
        index=choices.index(seed) if seed in choices else None,
        key=f"{key}_{param.name}", help=help_text,
        placeholder="type a value…" if accept_new else "choose…",
        accept_new_options=accept_new,
    )

    if chosen is None:
        return None, None
    if isinstance(chosen, str) and chosen in prior_steps:
        return None, chosen                      # bound to a step

    try:
        value = coerce_value(chosen, jtype)
        check_rule(value, rule)
        return value, None
    except (ValueError, TypeError) as exc:
        st.error(f"**{param.name}**: {exc}")
        return None, None


def tool_settings_popover(st, definition, params, *, key: str,
                          current: dict[str, Any] | None = None) -> dict[str, Any]:
    """The parameters that have defaults, folded into one popover.

    A parameter with a default is a knob, not an input: the tool already works
    without it. Keeping them off the card leaves only the step's real inputs
    visible, and each widget opens seeded with the signature's own default.
    """
    current = current or {}
    collected: dict[str, Any] = {}
    with st.popover(":material/tune:", help="Tool settings"):
        st.caption(f"`{definition.operation_id}` settings")
        for param in params:
            value = render_literal_arg(st, definition, param, key=key,
                                       default=current.get(param.name))
            # Leaving one empty means "use the tool's own default".
            if value is not None:
                collected[param.name] = value
    return collected
