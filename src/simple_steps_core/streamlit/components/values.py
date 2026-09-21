"""
Value-object components
=======================

The small records the runtime hands back: :class:`StepStatus`,
:class:`StepError`, :class:`StepResult`, :class:`ItemOutcome`, :class:`Shape`,
:class:`Cell`, :class:`DataEntry`, :class:`ResourceCheck`,
:class:`SessionSnapshot`, :class:`AppConfig`, plus the tool-UI declarations
:class:`ToolUI` / :class:`ToolUIView`.

Each is one or two lines of Streamlit — they exist so that *every* object the
library exposes has a component, and so the dispatch table in ``__init__`` has
no holes.
"""

from __future__ import annotations

from simple_steps_core import (
    AppConfig,
    Cell,
    DataEntry,
    ItemOutcome,
    ResourceCheck,
    SessionSnapshot,
    Shape,
    StepError,
    StepResult,
    StepStatus,
    ToolRegistry,
    ToolUI,
    ToolUIView,
)

__all__ = [
    "render_status", "render_step_error", "render_step_result", "render_item_outcome",
    "render_shape", "render_cell", "render_data_entry", "render_resource_check",
    "render_snapshot", "render_app_config", "render_tool_ui", "render_tool_ui_view",
    "render_tool_registry",
]

_STATUS_ICON = {
    StepStatus.PENDING: ":material/schedule:",
    StepStatus.RUNNING: ":material/autorenew:",
    StepStatus.COMPLETED: ":material/check_circle:",
    StepStatus.FAILED: ":material/error:",
}


def render_status(st, status: StepStatus, *, key: str) -> None:
    """A status badge."""
    st.caption(f"{_STATUS_ICON.get(status, '')} {status.value}")


def render_step_error(st, error: StepError, *, key: str) -> None:
    """A structured failure — message up front, traceback folded away."""
    st.error(f"**{error.type}** — {error.message}")
    if error.traceback:
        with st.expander("traceback", expanded=False):
            st.code(error.traceback)


def render_step_result(st, result: StepResult, *, key: str) -> None:
    """The engine's reference-only step result."""
    st.json(result.model_dump(), expanded=False)


def render_item_outcome(st, outcome: ItemOutcome, *, key: str) -> None:
    """One item of a fan-out."""
    st.caption(
        f"[{outcome.index}] {_STATUS_ICON.get(outcome.status, '')} {outcome.status.value}"
        + (f" — {outcome.error}" if outcome.error else "")
    )


def render_shape(st, shape: Shape, *, key: str) -> None:
    """Payload metadata — never the payload."""
    bits = [f"`{shape.kind}`", f"{shape.rows} row(s)"]
    if shape.columns:
        bits.append(f"{len(shape.columns)} column(s)")
    if shape.value_type:
        bits.append(f"`{shape.value_type}`")
    st.caption(" · ".join(bits))


def render_cell(st, cell: Cell, *, key: str) -> None:
    """One grid cell."""
    st.caption(f"{cell.row_id}/{cell.column_id}: {cell.display_value or cell.value}")


def render_data_entry(st, entry: DataEntry, *, key: str) -> None:
    """One payload-store entry."""
    st.caption(f"`{entry.ref_id}`")
    if getattr(entry, "shape", None) is not None:
        render_shape(st, entry.shape, key=f"{key}_shape")


def render_resource_check(st, check: ResourceCheck, *, key: str) -> None:
    """The result of one resource's hello-world."""
    ok = getattr(check, "ok", None)
    label = getattr(check, "name", "resource")
    if ok is False:
        st.error(f"`{label}` — {getattr(check, 'error', 'check failed')}")
    else:
        st.caption(f":material/check_circle: `{label}` ok")


def render_snapshot(st, snapshot: SessionSnapshot, *, key: str) -> None:
    """A captured session — step count and payload count, no payloads."""
    steps = getattr(snapshot, "steps", []) or []
    payloads = getattr(snapshot, "payloads", {}) or {}
    st.caption(f"{len(steps)} step(s) · {len(payloads)} payload(s)")


def render_app_config(st, config: AppConfig, *, key: str) -> None:
    """The app's own settings."""
    import pandas as pd

    st.dataframe(
        pd.DataFrame([{"setting": k, "value": str(v)}
                      for k, v in config.model_dump().items()]),
        width="stretch", hide_index=True,
    )


def render_tool_ui(st, ui: ToolUI, *, key: str) -> None:
    """Which render targets a tool declares, and which phases each defines."""
    targets = ui.targets()
    if not targets:
        st.caption("no custom UI — the auto-form is used")
        return
    for target in targets:
        view = ui.for_target(target)
        st.caption(f"`{target}` — " + _phases(view))


def render_tool_ui_view(st, view: ToolUIView, *, key: str) -> None:
    """One target's declared lifecycle phases."""
    st.caption(_phases(view))


def _phases(view: ToolUIView | None) -> str:
    if view is None:
        return "—"
    if view.is_full:
        return "full (owns the whole experience)"
    phases = [name for name, declared in
              (("input", view.input is not None), ("result", view.result is not None))
              if declared]
    return " + ".join(phases) if phases else "—"


def render_tool_registry(st, registry: ToolRegistry, *, key: str, on_select=None) -> None:
    """The tool palette, straight off the registry."""
    from .tools import render_registry

    definitions = registry.list_definitions()
    st.caption(f"{len(definitions)} tool(s)"
               + (" · frozen" if registry.frozen else ""))
    render_registry(st, definitions, key=key, on_select=on_select)
