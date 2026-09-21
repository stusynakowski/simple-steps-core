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
    edit_data_input,
    execution_popover,
    orchestration_popover,
    render_guardrails,
    render_literal_arg,
    render_output,
    render_output_status,
    render_resource_params,
    render_staged_output,
)
from .draft import DraftStep

__all__ = ["render_step_card", "render_operation_panel", "render_result_panel",
           "render_staged", "render_arguments",
           "render_step_controls", "STEP_VIEWS"]

#: The view toggles a card offers, in display order.
STEP_VIEWS = [":material/step:", ":material/function:", ":material/dataset:"]


def render_step_card(st, draft: DraftStep, *, key: str, registry,
                     tool_ids: list[str], prior: list[str],
                     step=None, views: list[str] | None = None,
                     on_run=None, on_reset=None) -> DraftStep:
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
                    render_operation_panel(st, draft, key=key, tool=tool, prior=prior)
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
                           prior: list[str]) -> None:
    """The Operation pane, kept deliberately small.

    Visible: the tool, where its data comes from, how it is applied, and the
    literal arguments that actually need a value. Everything else — item
    binding, accumulator seed, timeouts, retries, concurrency — lives behind two
    small popovers, because a step card is only ~260px wide and those knobs are
    rarely touched.
    """
    if tool is None:
        st.caption("Unknown tool.")
        return

    definition = tool.definition
    data_params = [p for p in definition.params if p.kind == "data"]
    param_names = [p.name for p in data_params]

    if definition.guardrails is not None:
        render_guardrails(st, definition.guardrails, key=f"guard_{draft.id}")
    render_resource_params(st, definition.params)

    # ── one routing decision, asked the same way in every mode ───────────
    mode, source = edit_data_input(
        st, draft.orchestration.mode, draft.data_source(data_params),
        key=f"data_{draft.id}", prior_steps=prior, takes_data=bool(data_params),
    )
    draft.orchestration = draft.orchestration.model_copy(update={"mode": mode})
    draft.set_data_source(source, data_params)

    main_arg_col,additional_arg_col=st.columns([2,1])

    # ── only the arguments that still need a value ───────────────────────
    with main_arg_col:
        render_arguments(st, draft, key=key, definition=definition,
                        data_params=data_params, prior=prior, tool=tool)

    # ── the rest, one click away ─────────────────────────────────────────
    #with st.container(horizontal=True, gap="xxsmall", width="content"):
    with additional_arg_col:

        with st.popover("Tool Settings :material/settings:", help="Tool-specific settings"):
            st.caption("Tool-specific settings go here. default literal arguments")

        #if draft.is_fanned_out:
        draft.orchestration = orchestration_popover(
            st, draft.orchestration, key=f"orch_{draft.id}",
                param_names=param_names, inferred=draft.primary_param(data_params),
            )
        draft.execution = execution_popover(
            st, draft.execution, key=f"exec_{draft.id}",
            fanned_out=draft.is_fanned_out,
        )


def render_arguments(st, draft: DraftStep, *, key: str, definition, data_params,
                     prior: list[str], tool: Tool) -> None:
    """Literal widgets for the arguments the data row did not already route.

    The parameter that receives the step's data is never shown here — it is
    either bound by the routing row above or supplied per item by the
    orchestrator. Typed widgets are kept as-is: a number stays a number input.
    """
    custom = tool.ui.input("streamlit")
    if custom is not None:
        draft.arguments = custom(st, key=f"form_{draft.id}",
                                 defaults=dict(draft.arguments)) or {}
        return

    if not data_params:
        return

    routed = draft.primary_param(data_params) if (
        draft.is_fanned_out or draft.data_source(data_params)
    ) else None

    literals: dict[str, Any] = {}
    for param in data_params:
        if param.name == routed:
            continue
        value = render_literal_arg(st, definition, param, key=f"form_{draft.id}",
                                   default=draft.arguments.get(param.name))
        # An empty optional field means "use the tool's own default".
        if value is None and not param.required:
            continue
        literals[param.name] = value

    draft.arguments = literals
    # Keep only the binding the routing row owns.
    draft.sources = {k: v for k, v in draft.sources.items() if k == routed}


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
