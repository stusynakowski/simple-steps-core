"""
Tool-contract components
========================

Components for the objects that describe *what a tool is*: :class:`Tool`,
:class:`ToolDefinition`, :class:`ToolParam`, :class:`Guardrails` and
:class:`ArgGuardrail`.

Every widget choice here is derived from the tool contract — the JSON-Schema
type picks the widget, the guardrail constrains it, and ``kind`` decides whether
a param is asked for at all. Nothing is hard-coded per tool.
"""

from __future__ import annotations


from simple_steps_core import ArgGuardrail, Guardrails, Tool, ToolDefinition, ToolParam

from .base import summary

__all__ = [
    "render_tool",
    "render_tool_definition",
    "render_param",
    "render_guardrails",
    "render_arg_guardrail",
    "render_resource_params",
]


def render_tool(st, tool: Tool, *, key: str, on_select=None) -> None:
    """One tool as a palette entry: id, call style, description, contract."""
    definition = tool.definition
    st.markdown(f"**`{tool.tool_id}`**")
    st.caption(
        f"{'async' if tool.is_async else 'sync'}"
        + (f" · {definition.category}" if definition.category else "")
        + (f" · {definition.description}" if definition.description else "")
    )
    if on_select is not None and st.button("Use this tool", key=f"{key}_select"):
        on_select(tool)
    render_tool_definition(st, definition, key=f"{key}_def")


def render_tool_definition(st, definition: ToolDefinition, *, key: str) -> None:
    """A tool's public contract — straight from ``definition.info()``."""
    summary(st, definition.info(), key=f"{key}_contract", title=False)
    if definition.guardrails is not None:
        render_guardrails(st, definition.guardrails, key=f"{key}_guard")


def render_param(st, param: ToolParam, *, key: str) -> None:
    """One parameter's contract line (no widget — see forms.edit_argument)."""
    bits = [f"`{param.type_name}`", "required" if param.required else "optional"]
    if param.kind == "resource":
        bits.append("injected")
    elif param.default is not None:
        bits.append(f"default `{param.default}`")
    st.caption(f"**{param.name}** — " + " · ".join(bits))


def render_resource_params(st, params: list[ToolParam]) -> None:
    """Show a tool's injected resources — supplied by the runtime, not the user."""
    names = [p.name for p in params if p.kind == "resource"]
    if names:
        st.caption(
            ":material/database: injected resource"
            f"{'s' if len(names) > 1 else ''}: " + ", ".join(f"`{n}`" for n in names)
        )


def render_guardrails(st, guardrails: Guardrails, *, key: str) -> None:
    """Policy a tool declares. Flags are advisory — the runtime enforces only
    ``arguments`` (see docs/api-reference.md), so say so rather than imply a gate.
    """
    flags = [name for name, on in (
        ("read only", guardrails.read_only),
        ("destructive", guardrails.destructive),
        ("needs confirmation", guardrails.requires_confirmation),
    ) if on]

    if flags:
        st.warning(
            f":material/warning: {' · '.join(flags)}"
            + (f" — {guardrails.usage}" if guardrails.usage else "")
        )
    elif guardrails.usage:
        st.caption(guardrails.usage)

    for rule in guardrails.rules:
        st.caption(f"• {rule}")

    for name, rule in guardrails.arguments.items():
        render_arg_guardrail(st, rule, name=name, key=f"{key}_{name}")


def render_arg_guardrail(st, rule: ArgGuardrail, *, name: str, key: str) -> None:
    """One argument's enforced constraints, as a single dim line."""
    text = describe_arg_guardrail(rule)
    if text:
        st.caption(f"`{name}` — {text}")


def describe_arg_guardrail(rule: ArgGuardrail | None) -> str:
    """The human phrasing of an ``ArgGuardrail``; shared with the form builder."""
    if rule is None:
        return ""
    parts: list[str] = []
    if rule.enum is not None:
        parts.append("one of " + ", ".join(f"`{v}`" for v in rule.enum))
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
    return " · ".join(parts)


def render_registry(st, definitions: list[ToolDefinition], *, key: str,
                    on_select=None) -> None:
    """The whole palette: one expander per registered tool."""
    if not definitions:
        st.caption("No tools registered.")
        return
    for definition in definitions:
        with st.expander(f"`{definition.operation_id}`", expanded=False):
            if definition.description:
                st.caption(definition.description)
            render_tool_definition(st, definition, key=f"{key}_{definition.operation_id}")
            if on_select is not None and st.button(
                "Use", key=f"{key}_{definition.operation_id}_use"
            ):
                on_select(definition.operation_id)
