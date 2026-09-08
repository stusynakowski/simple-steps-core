"""
Tool UI lifecycle and default builder
=====================================

``ToolUIView`` lets each renderer provide a recommended pair of ``input`` and
``result`` views, or an advanced ``full`` view that owns the complete visual
experience. ``ToolUI`` stores those declarations by renderer target.

The default builder turns a tool's ``input_schema`` into a **prefab-ui
protocol** input document. Legacy single-view declarations remain input views.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolUIView:
    """Views for one renderer target across a tool's execution lifecycle.

    Most tools should provide separate ``input`` and ``result`` views. Advanced
    tools may instead provide one ``full`` view that owns the whole experience.
    A full view is exclusive because mixing both ownership models leaves the
    host unable to determine which view controls execution and result layout.
    """

    input: Any = None
    result: Any = None
    full: Any = None

    def __post_init__(self) -> None:
        composed = self.input is not None or self.result is not None
        if self.full is not None and composed:
            raise ValueError("define either 'full' or 'input'/'result' views, not both")
        if self.full is None and self.input is None:
            raise ValueError("a composed tool UI must define an 'input' view")

    @property
    def is_full(self) -> bool:
        return self.full is not None

    def primary(self) -> Any:
        """Return the legacy view: composed input, or the full view."""
        return self.full if self.is_full else self.input

    def as_definition(self) -> Any:
        """Return a serializable declaration, retaining legacy input-only shape."""
        if self.result is None and not self.is_full:
            return self.input
        if self.is_full:
            return {"full": self.full}
        return {"input": self.input, "result": self.result}


def _coerce_target_view(view: Any) -> ToolUIView:
    if isinstance(view, ToolUIView):
        return view
    if isinstance(view, dict) and "view" not in view and any(
        phase in view for phase in ("input", "result", "full")
    ):
        unknown = set(view) - {"input", "result", "full"}
        if unknown:
            raise ValueError(f"unknown tool UI phase(s): {', '.join(sorted(unknown))}")
        return ToolUIView(**view)
    return ToolUIView(input=view)


class ToolUI:
    """A tool's lifecycle views, keyed by renderer target.

    Existing target values are treated as input views, so ``get(target)`` and
    ``prefab`` remain backward compatible. New integrations should use
    :meth:`input`, :meth:`result`, and :meth:`full` explicitly.
    """

    def __init__(self, views: dict[str, Any] | None = None):
        self._views = {
            target: _coerce_target_view(view)
            for target, view in (views or {}).items()
        }

    def get(self, target: str) -> Any:
        """The legacy primary view for *target*, or ``None`` when absent."""
        view = self._views.get(target)
        return view.primary() if view is not None else None

    def for_target(self, target: str) -> ToolUIView | None:
        """The lifecycle-aware declaration for *target*."""
        return self._views.get(target)

    def set(self, target: str, view: Any) -> None:
        self._views[target] = _coerce_target_view(view)

    def input(self, target: str) -> Any:
        """The pre-execution argument view for *target*, when composed."""
        view = self._views.get(target)
        return view.input if view is not None else None

    def result(self, target: str) -> Any:
        """The post-execution interactive result view for *target*."""
        view = self._views.get(target)
        return view.result if view is not None else None

    def full(self, target: str) -> Any:
        """The view that owns the complete tool experience for *target*."""
        view = self._views.get(target)
        return view.full if view is not None else None

    def definition_for(self, target: str) -> Any:
        """Return the serializable UI declaration for a renderer target."""
        view = self._views.get(target)
        return view.as_definition() if view is not None else None

    @property
    def prefab(self) -> dict[str, Any] | None:
        """The legacy primary prefab-ui protocol document."""
        return self.get("prefab")

    def targets(self) -> list[str]:
        return list(self._views)

    def __contains__(self, target: str) -> bool:
        return target in self._views


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
