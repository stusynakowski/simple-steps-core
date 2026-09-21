"""
Workflow toolbar and sidebar panels
===================================

The step-selection toolbar, the run controls, the tool palette and the
import/export sidebar. Each takes its state explicitly and hands every action
back through a callback, so none of them touches ``st.session_state``.
"""

from __future__ import annotations

from simple_steps_core import ToolRegistry, Workflow

from ..components import render_tool_registry, render_workflow_validation
from .draft import DraftWorkflow

__all__ = [
    "render_workflow_toolbar",
    "render_run_controls",
    "render_tool_palette",
    "render_workflow_io",
    "render_problems",
]


def render_workflow_toolbar(st, drafts: DraftWorkflow, *, key: str,
                            selected: list[str], nonce: int = 0,
                            on_select=None, on_add=None, on_remove=None,
                            on_swap=None, on_group=None, on_ungroup=None) -> list[str]:
    """Step selector plus the add/remove/swap/group controls.

    Returns the currently selected step ids.
    """
    def _label(step_id: str) -> str:
        draft = drafts.get(step_id)
        if draft is None:
            return step_id
        return f"{step_id} · {draft.op or '—'}" + (f" [{draft.stage}]" if draft.stage else "")

    option_ids = set(drafts.ids())
    chosen = st.segmented_control(
        "Current steps",
        options=drafts.ids(),
        format_func=_label,
        selection_mode="multi",
        default=[s for s in selected if s in option_ids],
        key=f"{key}_selected_{nonce}",
    ) or []

    if on_select is not None:
        on_select(chosen)

    with st.container(horizontal=True, vertical_alignment="top", gap="xxsmall"):
        if on_add is not None:
            st.button(":material/add_circle_outline: Add", key=f"{key}_add", on_click=on_add)
        if on_remove is not None:
            st.button(":material/remove_circle_outline: Remove", key=f"{key}_remove",
                      disabled=not chosen, on_click=on_remove, args=(chosen,))
        if on_swap is not None:
            st.button(":material/swap_horiz: Swap", key=f"{key}_swap",
                      disabled=len(chosen) != 2, on_click=on_swap, args=(chosen,))

    if on_group is not None or on_ungroup is not None:
        with st.popover("Group into stages"):
            if on_group is not None:
                st.button(":material/merge_type: Group selected", key=f"{key}_group",
                          disabled=len(chosen) < 2, on_click=on_group, args=(chosen,))
            if on_ungroup is not None:
                st.button(":material/call_split: Ungroup selected", key=f"{key}_ungroup",
                          disabled=not chosen, on_click=on_ungroup, args=(chosen,))

    return chosen


def render_run_controls(st, drafts: DraftWorkflow, *, key: str,
                        on_clear=None) -> bool:
    """Run-all and reset.

    Returns True when run-all was pressed this rerun. Running is a *return
    value* rather than a callback because the caller must run only after every
    card has rendered and contributed its freshly-collected arguments.
    """
    with st.container(horizontal=True, gap="xxsmall"):
        run_all = st.button(":material/play_arrow: Run all", key=f"{key}_run_all",
                            disabled=not len(drafts),type="primary")
        if on_clear is not None:
            with st.popover(":material/refresh: Reset", disabled=not len(drafts)):
                st.warning("This removes every step and clears all results. "
                           "This can't be undone.")
                st.button(":material/warning: Yes, clear everything",
                          key=f"{key}_clear", on_click=on_clear)
    return run_all


def render_tool_palette(st, registry: ToolRegistry, *, key: str, on_select=None) -> None:
    """The registry as a browsable palette — the component does the drawing."""
    render_tool_registry(st, registry, key=key, on_select=on_select)


def render_workflow_io(st, workflow: Workflow, *, key: str, on_load=None,
                       sample_json=None, sample_available: bool = False) -> None:
    """Export / import / load-sample controls for a whole session."""
    try:
        export_data = workflow.export_session_json() if workflow.steps else None
    except Exception as exc:                      # noqa: BLE001 - surfaced to the user
        export_data = None
        st.caption(f"Can't export yet: {exc}")

    st.download_button(
        ":material/download: Export workflow",
        data=export_data or "",
        file_name="workflow.json",
        mime="application/json",
        disabled=export_data is None,
        key=f"{key}_export",
    )

    uploaded = st.file_uploader("Import workflow", type="json", key=f"{key}_upload")
    if uploaded is not None and on_load is not None and st.button(
        ":material/upload: Load uploaded workflow", key=f"{key}_load"
    ):
        try:
            on_load(uploaded.getvalue().decode("utf-8"))
        except Exception as exc:                  # noqa: BLE001 - surfaced to the user
            st.error(f"Couldn't load that workflow: {exc}")

    if sample_available and on_load is not None and sample_json is not None:
        st.caption("Sample workflow — the readings pipeline, already run.")
        if st.button(":material/science: Load sample workflow", key=f"{key}_sample"):
            on_load(sample_json())


def render_problems(st, problems: dict[str, str]) -> None:
    """Steps the library refused, with its own message for each."""
    for step_id, message in problems.items():
        st.warning(f":material/warning: **{step_id}** isn't runnable yet — {message}")


def render_validation(st, workflow: Workflow, *, key: str) -> None:
    """The workflow preflight table."""
    render_workflow_validation(st, workflow, key=key)
