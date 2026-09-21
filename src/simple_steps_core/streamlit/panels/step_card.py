"""
Step card panel
===============

One step's card: controls, the Operation panel (tool + input + runtime), and
the Result panel. Built entirely from :mod:`..components`, and driven by a
:class:`~.draft.DraftStep` plus caller-supplied callbacks — it owns no state
and never reaches into ``st.session_state``.
"""

from __future__ import annotations

from typing import Any

from simple_steps_core import StepStatus, Tool

from ..components import (
    execution_popover,
    format_reference,
    orchestration_popover,
    render_guardrails,
    render_literal_arg,
    render_output,
    render_output_status,
    render_resource_params,
    reference_options,
    render_staged_output,
    tool_settings_popover,
)
from ..components.configs import NO_SOURCE
from .draft import DraftStep
from .inference import describe, infer_binding

__all__ = ["render_step_card", "render_operation_panel", "render_result_panel",
           "render_staged", "render_inputs",
           "render_step_controls", "STEP_VIEWS"]

#: The view toggles a card offers, in display order.
STEP_VIEWS = [":material/step:", ":material/function:", ":material/dataset:"]


def render_step_card(st, draft: DraftStep, *, key: str, registry,
                     tool_ids: list[str], prior: list[str],
                     step=None, views: list[str] | None = None,
                     drafts=None, on_run=None, on_reset=None) -> DraftStep:
    """Draw one step's whole card and return the (mutated) draft row.

    The tool is resolved **after** the selectbox, from the registry — resolving
    it before would render the previously selected tool's arguments, since the
    selectbox only updates ``draft.op`` as it is drawn.

    *step* is the workflow's own ``Step`` when it exists, so the Result panel can
    show real output; ``None`` means the step has not been authored into the
    workflow yet.
    """
    views = views if views is not None else STEP_VIEWS
    tool = _resolve(registry, draft.op)

    with st.container(key=f"step_{draft.id}_card", gap="xxsmall"):
        #run_step_col,operation_selection_col = st.columns(2)
        # bottom alignment puts the unlabelled buttons on the selectbox's input
        # line rather than level with its label.
        #st.write(views)
        with st.container(horizontal=True, horizontal_alignment="left",
                          vertical_alignment="bottom", gap="xxsmall",
                          key=f"step_{draft.id}_controls_and_tool"):
            if ":material/step:" in views:
                #with run_step_col:
                render_step_controls(st, draft, key=key, on_run=on_run, on_reset=on_reset,
                                        can_reset=step is not None)
                #with operation_selection_col:
            if ":material/function:" in views:
                draft.op = st.selectbox(
                    ":material/construction: Tool Selection", tool_ids,
                    index=tool_ids.index(draft.op) if draft.op in tool_ids else None,
                    placeholder="choose an operation…", key=f"op_{draft.id}",
                )

        if ":material/function:" in views:
            with st.expander(":material/input: :material/function:  Inputs", type="compact",expanded=True):

                tool = _resolve(registry, draft.op)
                if draft.op:
                    render_operation_panel(st, draft, key=key, tool=tool,
                                           prior=prior, drafts=drafts,
                                           registry=registry)
                else:
                    st.caption("Choose a tool first.")
        else:
            tool = _resolve(registry, draft.op)

        if ":material/dataset:" in views:
            render_result_panel(st, draft, key=key, tool=tool, step=step,
                                show_status=":material/analytics:" in views)

    return draft


def _resolve(registry, op: str | None) -> Tool | None:
    """The registered Tool for *op*, or None while nothing is chosen."""
    if not op or not registry.has(op):
        return None
    return registry.get_operation(op)


def render_step_controls(st, draft: DraftStep, *, key: str, on_run=None,
                         on_reset=None, can_reset: bool = False) -> None:
    """Run / clear controls. Behavior is entirely caller-supplied."""
    #with st.expander(":material/step: Step Controls", expanded=True, type="compact"):
    # width="content" matters: st.container defaults to "stretch", which would
    # fill the row and push whatever sits beside it to the far edge.
    with st.container(horizontal=True, gap="xxsmall", width="content",
                      key=f"step_{draft.id}_controller"):
        if on_run is not None and st.button(
            ":material/play_arrow:", key=f"run_{draft.id}",
            help="Run this step", type="primary",
        ):
            on_run(draft)
        if on_reset is not None:
            st.button(":material/refresh:", key=f"reset_{draft.id}",
                        help="Clear this step's output", disabled=not can_reset,
                        type="secondary", on_click=on_reset, args=(draft,))


def render_operation_panel(st, draft: DraftStep, *, key: str, tool: Tool | None,
                           prior: list[str], drafts=None, registry=None) -> None:
    """The Operation pane.

    Positional parameters — the ones with no default — are the step's real
    inputs, so they are asked for directly. Everything with a default is a knob,
    and knobs live in the Tool settings popover already filled in.

    Choosing an earlier step for the first positional parameter also *configures
    the orchestration*: the declared types decide whether the column is passed
    whole or the tool is applied across it (see :mod:`.inference`).
    """
    if tool is None:
        st.caption("Unknown tool.")
        return

    definition = tool.definition
    data_params = [p for p in definition.params if p.kind == "data"]
    positional = [p for p in data_params if p.required]
    settings = [p for p in data_params if not p.required]

    if definition.guardrails is not None:
        render_guardrails(st, definition.guardrails, key=f"guard_{draft.id}")
    render_resource_params(st, definition.params)

    custom = tool.ui.input("streamlit")

    # Inputs on the left, the settings popovers on the right.
    inputs_col, settings_col = st.columns([3, 1], vertical_alignment="top")

    with inputs_col:
        if custom is not None:
            # A tool that draws its own form still needs somewhere to say which
            # step it reads, or a fan-out could never be given its collection.
            if positional or draft.is_fanned_out:
                route_primary(st, draft, key=key, definition=definition,
                              param=positional[0] if positional else None,
                              prior=prior, drafts=drafts, registry=registry,
                              literal=False)
            draft.arguments = custom(st, key=f"form_{draft.id}",
                                     defaults=dict(draft.arguments)) or {}
        else:
            render_inputs(st, draft, key=key, definition=definition,
                          positional=positional, prior=prior, drafts=drafts,
                          registry=registry)

    with settings_col:
        if settings and custom is None:
            chosen = tool_settings_popover(st, definition, settings,
                                           key=f"form_{draft.id}",
                                           current=draft.arguments)
            draft.arguments = {**draft.arguments, **chosen}
        draft.orchestration, draft.mode_locked = orchestration_popover(
            st, draft.orchestration, key=f"orch_{draft.id}",
            param_names=[p.name for p in data_params],
            inferred=draft.primary_param(data_params),
            locked=draft.mode_locked,
        )
        draft.execution = execution_popover(
            st, draft.execution, key=f"exec_{draft.id}",
            fanned_out=draft.is_fanned_out,
        )

    # The popover is drawn after the inputs, so a mode chosen there arrives too
    # late for the routing above. Re-route the same source now that the mode is
    # final, or the step would be briefly invalid (a fan-out with no `over`).
    primary = draft.primary_param(data_params)
    if primary:
        reference = draft.sources.get(primary) or draft.orchestration.over
        if reference:
            draft.set_data_source(reference, data_params)


def render_inputs(st, draft: DraftStep, *, key: str, definition, positional,
                  prior: list[str], drafts=None, registry=None) -> None:
    """The positional parameters: an earlier step, or a value typed in.

    The **first** positional parameter carries the step's data, so binding it to
    an earlier step also sets the orchestration. Any further positional
    parameters are plain references or literals — a fan-out has only one
    collection to iterate.
    """
    if not positional:
        return

    literals: dict[str, Any] = {}
    sources: dict[str, str] = {}

    for index, param in enumerate(positional):
        if index == 0:
            bound, value = route_primary(
                st, draft, key=key, definition=definition, param=param,
                prior=prior, drafts=drafts, registry=registry,
            )
            if bound is not None:
                sources[param.name] = bound
            elif value is not None:
                literals[param.name] = value
            continue

        name = param.name
        options = reference_options(prior, sentinel=NO_SOURCE)
        current = draft.sources.get(name)
        chosen = st.selectbox(
            name, options,
            index=options.index(current) if current in options else 0,
            key=f"src_{draft.id}_{name}", format_func=format_reference,
            help="Read an earlier step, or choose a value to type one in.",
        )
        if chosen == NO_SOURCE:
            value = render_literal_arg(st, definition, param, key=f"form_{draft.id}",
                                       default=draft.arguments.get(name))
            if value is not None:
                literals[name] = value
        else:
            sources[name] = chosen

    draft.arguments = {**{k: v for k, v in draft.arguments.items()
                          if k not in {p.name for p in positional}}, **literals}
    draft.sources = sources


def route_primary(st, draft: DraftStep, *, key: str, definition, param,
                  prior: list[str], drafts=None, registry=None,
                  literal: bool = True) -> tuple[str | None, Any]:
    """Ask which step feeds this one, and configure orchestration from the answer.

    Returns ``(reference, literal_value)`` — at most one is set. Comparing the
    upstream's declared output with *param*'s declared type is what decides
    between passing a column whole and applying the tool across it.
    """
    name = param.name if param is not None else "data"
    options = reference_options(prior, sentinel=NO_SOURCE)
    current = (draft.sources.get(name)
               or (draft.orchestration.over or "").split(".", 1)[0] or None)
    chosen = st.selectbox(
        name, options,
        index=options.index(current) if current in options else 0,
        key=f"src_{draft.id}_{name}", format_func=format_reference,
        help="Read an earlier step, or choose a value to type one in.",
    )

    if chosen == NO_SOURCE:
        if not draft.mode_locked:
            draft.orchestration = draft.orchestration.model_copy(
                update={"mode": "single", "over": None})
        if literal and param is not None:
            return None, render_literal_arg(st, definition, param,
                                            key=f"form_{draft.id}",
                                            default=draft.arguments.get(name))
        return None, None

    props = definition.input_schema.get("properties", {})
    binding = infer_binding(chosen, _upstream(drafts, chosen), props.get(name, {}),
                            registry, drafts,
                            target_definition=definition) if registry else None
    reference = binding.reference if binding else chosen
    mode = draft.orchestration.mode if draft.mode_locked else (
        binding.mode if binding else "single")

    if mode == "single":
        draft.orchestration = draft.orchestration.model_copy(
            update={"mode": "single", "over": None})
        if binding is not None and not draft.mode_locked:
            st.caption(f":material/auto_awesome: {describe(binding)}")
        return reference, None

    draft.orchestration = draft.orchestration.model_copy(
        update={"mode": mode, "over": reference})
    if binding is not None and not draft.mode_locked:
        st.caption(f":material/auto_awesome: {describe(binding)}")
    return None, None


def _upstream(drafts, step_id: str):
    """The draft a reference points at, ignoring any accessor suffix."""
    if drafts is None:
        return None
    return drafts.get(step_id.split(".", 1)[0])


def render_result_panel(st, draft: DraftStep, *, key: str, tool: Tool | None,
                        step=None, show_status: bool = False) -> None:
    """A step's output.

    Value only by default — no "done" banner, no duration. Turn on the Status
    view (or give the tool its own result view) to see anything more.
    """
    definition = tool.definition if tool is not None else None

    with st.expander(":material/output: Result", expanded=True, type="compact"):
        if show_status:
            value_tab, status_tab = st.tabs(
                [":material/dataset: Value", ":material/analytics: Status"]
            )
        else:
            value_tab, status_tab = st.container(), None

        with value_tab:
            if step is None or step.status is StepStatus.PENDING:
                render_staged(st, draft, definition, key=key)
            elif step.status is StepStatus.RUNNING:
                st.info("running…")
            elif step.status is StepStatus.COMPLETED:
                render_output(st, step.output, key=f"result_{draft.id}", operation=tool)
            elif step.status is StepStatus.FAILED:
                st.error(step.error or "failed")

        if status_tab is not None:
            with status_tab:
                if step is None or step.status is not StepStatus.COMPLETED:
                    st.caption("Run this step to see its output status.")
                else:
                    render_output_status(st, step.output, key=f"status_{draft.id}")


def render_staged(st, draft: DraftStep, definition, *, key: str) -> None:
    """What a not-yet-run step will produce — type and shape, shaded amber."""
    if definition is None:
        st.caption("Choose a tool to see what this step will produce.")
        return
    try:
        spec = draft.to_operation()
    except ValueError:
        st.caption("Choose a tool to see what this step will produce.")
        return
    render_staged_output(st, spec, definition, key=key)
