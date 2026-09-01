"""
Default UI builder (prefab-ui)
==============================

Turns a tool's ``input_schema`` into a **prefab-ui protocol** document — the
native ``{"view": <component tree>, "state": {...}}`` shape rendered by the
bundled prefab React renderer (https://prefab.prefect.io). Each data parameter
becomes an input component inside a ``Card`` form; ``state`` seeds defaults.

Users can override this entirely by passing their own ``ui=`` protocol dict to
``register_tool``; this builder only supplies the default.
"""

from __future__ import annotations

from typing import Any


def _title(name: str) -> str:
    return name.replace("_", " ").strip().title()


def _labeled(label: str, component: dict[str, Any]) -> dict[str, Any]:
    """Stack a text label above an input that has no built-in ``label`` prop."""
    return {
        "type": "Column",
        "cssClass": "gap-1",
        "children": [{"type": "Text", "content": label}, component],
    }


def _field_component(name: str, prop: dict[str, Any], *, required: bool, rule: Any = None) -> dict[str, Any]:
    """Map one JSON-Schema property (plus optional guardrail) to a prefab-ui input."""
    label = prop.get("title") or _title(name)
    enum = prop.get("enum")
    if enum is None and rule is not None and getattr(rule, "enum", None):
        enum = rule.enum                      # a guardrail enum also drives the widget
    jtype = prop.get("type")
    help_text = prop.get("description") or (getattr(rule, "note", "") if rule else "")

    if enum is not None:
        combobox = {
            "type": "Combobox",
            "name": name,
            "placeholder": f"Select {label}...",
            "required": required,
            "children": [
                {"type": "ComboboxOption", "value": opt, "label": str(opt)}
                for opt in enum
            ],
        }
        if help_text:
            combobox["help"] = help_text
        return _labeled(label, combobox)
    if jtype == "boolean":
        switch = {"type": "Switch", "name": name, "label": label, "required": required}
        if help_text:
            switch["help"] = help_text
        return switch
    if jtype in ("integer", "number"):
        inp = {"type": "Input", "name": name, "inputType": "number",
               "placeholder": label, "required": required}
        if rule is not None:
            if getattr(rule, "minimum", None) is not None:
                inp["min"] = rule.minimum
            if getattr(rule, "maximum", None) is not None:
                inp["max"] = rule.maximum
        if help_text:
            inp["help"] = help_text
        return _labeled(label, inp)
    # string / array / object / unknown -> text input (JSON hint for containers)
    placeholder = label if jtype in (None, "string") else f"{label} (JSON)"
    inp = {"type": "Input", "name": name, "inputType": "text",
           "placeholder": placeholder, "required": required}
    if rule is not None:
        if getattr(rule, "min_length", None) is not None:
            inp["minLength"] = rule.min_length
        if getattr(rule, "max_length", None) is not None:
            inp["maxLength"] = rule.max_length
        if getattr(rule, "pattern", None) is not None:
            inp["pattern"] = rule.pattern
    if help_text:
        inp["help"] = help_text
    return _labeled(label, inp)


def build_default_ui(
    operation_id: str,
    input_schema: dict[str, Any],
    *,
    description: str = "",
    guardrails: Any = None,
) -> dict[str, Any]:
    """Build a prefab-ui protocol form (``{"view", "state"}``) for a tool.

    When ``guardrails`` is given, its per-argument constraints shape the widgets
    (an enum becomes a dropdown, numeric bounds/lengths/patterns become input
    attributes, and the note becomes help text).
    """
    props: dict[str, Any] = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    arg_rules = getattr(guardrails, "arguments", {}) if guardrails is not None else {}

    fields = [
        _field_component(name, prop, required=name in required, rule=arg_rules.get(name))
        for name, prop in props.items()
    ]
    state = {name: prop["default"] for name, prop in props.items() if "default" in prop}

    header_children: list[dict[str, Any]] = [
        {"type": "CardTitle", "content": _title(operation_id)}
    ]
    if description:
        header_children.append({"type": "CardDescription", "content": description})

    view = {
        "type": "Card",
        "children": [
            {"type": "CardHeader", "children": header_children},
            {
                "type": "CardContent",
                "children": [{"type": "Column", "cssClass": "gap-3", "children": fields}],
            },
        ],
    }
    return {"view": view, "state": state}
