"""
Workflow and app components
===========================

Components for :class:`Workflow`, :class:`Stage`, :class:`App`,
:class:`Session`, :class:`ResourceContainer`, :class:`SessionContext` and
:class:`DataStore`.

These are the thinnest adapters in the package: each object already exposes an
``info()`` (and sometimes ``validate()`` / ``check_all()`` / ``preview()``)
returning a ``SummaryTable``, so the component's whole job is to place that
table and offer the object's own actions as caller-supplied callbacks.
"""

from __future__ import annotations

from simple_steps_core import (
    App,
    DataStore,
    ResourceContainer,
    Session,
    SessionContext,
    Stage,
    Workflow,
)

from .base import empty, summary

__all__ = [
    "render_workflow", "render_workflow_validation", "render_stage",
    "render_app", "render_session", "render_resources", "render_session_context",
    "render_data_store", "render_preview",
]


# ── workflow ─────────────────────────────────────────────────────────────
def render_workflow(st, workflow: Workflow, *, key: str,
                    on_run=None, on_run_stages=None, on_clear=None) -> None:
    """The spreadsheet view of a workflow, plus caller-supplied run actions."""
    if len(workflow) == 0:
        empty(st, "No steps yet.")
    else:
        summary(st, workflow.info(), key=f"{key}_info")

    if on_run is None and on_run_stages is None and on_clear is None:
        return
    with st.container(horizontal=True, gap="xxsmall"):
        if on_run is not None and st.button(":material/play_arrow: Run all",
                                            key=f"{key}_run", disabled=len(workflow) == 0):
            on_run(workflow)
        if on_run_stages is not None and st.button(":material/layers: Run by stages",
                                                   key=f"{key}_stages",
                                                   disabled=len(workflow) == 0):
            on_run_stages(workflow)
        if on_clear is not None and st.button(":material/refresh: Clear",
                                              key=f"{key}_clear", disabled=len(workflow) == 0):
            on_clear(workflow)


def render_workflow_validation(st, workflow: Workflow, *, key: str) -> None:
    """The preflight table — unknown tools, bad references, missing resources."""
    summary(st, workflow.validate(), key=f"{key}_validate")
    missing = workflow.missing_resources()
    if missing:
        st.warning(":material/warning: missing resources: "
                   + ", ".join(f"`{n}`" for n in missing))


def render_preview(st, workflow: Workflow, step_id: str, *, key: str,
                   limit: int = 5) -> None:
    """A payload-free preview of one step's output."""
    summary(st, workflow.preview(step_id, limit=limit), key=f"{key}_preview")


def render_stage(st, stage: Stage, *, key: str, on_run=None) -> None:
    """One stage view — a groupby over steps, not a container."""
    summary(st, stage.info(), key=f"{key}_info")
    if on_run is not None and st.button(":material/play_arrow: Run stage", key=f"{key}_run"):
        on_run(stage)


def render_stages(st, workflow: Workflow, *, key: str, on_run=None) -> None:
    """Every stage of a workflow, in order."""
    views = workflow.stage_views()
    if not views:
        empty(st, "No stages — steps are ungrouped.")
        return
    for stage in views:
        with st.expander(repr(stage), expanded=False):
            render_stage(st, stage, key=f"{key}_{stage}", on_run=on_run)


# ── app facade ───────────────────────────────────────────────────────────
def render_app(st, app: App, *, key: str) -> None:
    """The App overview — config, tools, resources, live sessions."""
    summary(st, app.info(), key=f"{key}_info")


def render_session(st, session: Session, *, key: str) -> None:
    """One user's session — its workflows and resources."""
    summary(st, session.info(), key=f"{key}_info")


# ── resources and payload store ──────────────────────────────────────────
def render_resources(st, resources: ResourceContainer, *, key: str,
                     required_by: dict[str, list[str]] | None = None,
                     on_check=None) -> None:
    """Declared resources and their load state; ``on_check`` runs the hello-worlds."""
    summary(st, resources.info(required_by=required_by), key=f"{key}_info")
    if on_check is not None and st.button(":material/health_and_safety: Check all",
                                          key=f"{key}_check",
                                          disabled=not resources.names()):
        on_check(resources)


def render_resource_check(st, resources: ResourceContainer, *, key: str) -> None:
    """Run and show every resource's check — the pre-batch hello-world."""
    summary(st, resources.check_all(), key=f"{key}_checks")


def render_session_context(st, context: SessionContext, *, key: str) -> None:
    """What the session's payload store currently holds."""
    import pandas as pd

    entries = context.entries()
    if not entries:
        empty(st, "No payloads stored yet.")
        return
    st.dataframe(
        pd.DataFrame([
            {"ref": e.ref_id, "step": _step_for(context, e.ref_id),
             "kind": getattr(e.shape, "kind", "—"),
             "rows": getattr(e.shape, "rows", "—")}
            for e in entries
        ]),
        width="stretch", hide_index=True,
    )


def render_data_store(st, store: DataStore, *, key: str) -> None:
    """Raw payload-store contents (refs only — never the payloads themselves)."""
    import pandas as pd

    entries = list(store.entries()) if hasattr(store, "entries") else []
    if not entries:
        empty(st, "Store is empty.")
        return
    st.dataframe(pd.DataFrame([{"ref": e.ref_id} for e in entries]),
                 width="stretch", hide_index=True)


def _step_for(context: SessionContext, ref_id: str) -> str:
    for step_id, ref in context.step_to_ref.items():
        if ref == ref_id:
            return step_id
    return "—"
