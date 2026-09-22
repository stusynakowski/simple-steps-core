"""
Step and output components
==========================

Components for :class:`Step`, :class:`Operation`, :class:`ToolCall`,
:class:`StepOutput`, :class:`MapResult` and :class:`ItemOutcome` — the objects
that describe *what a step will do* and *what it produced*.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from simple_steps_core import (
    Collection,
    Groups,
    ItemOutcome,
    MapResult,
    MediaAsset,
    Operation,
    Step,
    StepOutput,
    StepStatus,
    ToolCall,
    Tool,
)
from simple_steps_core.domain.tabular import is_frame

from .base import summary_frame  # noqa: F401  (re-exported for callers)
from .configs import is_fanned_out, render_orchestration, render_step_execution
from .media import render_media_asset, render_media_grid

__all__ = [
    "shade", "shade_by_status", "staged_frame",
    "STAGED_FILL", "OK_FILL", "FAILED_FILL",
    "render_step",
    "render_operation",
    "render_tool_call",
    "render_output",
    "render_output_status",
    "render_map_result",
    "render_staged_output",
    "to_dataframe",
    "render_value",
    "render_groups",
    "render_collection",
    "output_type_name",
]

_SCALAR_TYPES = {
    "integer": "int", "number": "float", "string": "str",
    "boolean": "bool", "null": "None",
}

_STATUS_ICON = {
    StepStatus.PENDING: ":material/schedule:",
    StepStatus.RUNNING: ":material/autorenew:",
    StepStatus.COMPLETED: ":material/check_circle:",
    StepStatus.FAILED: ":material/error:",
}


# ── specs ────────────────────────────────────────────────────────────────
def render_tool_call(st, call: ToolCall, *, key: str) -> None:
    """The durable call record: which tool, which arguments."""
    st.caption(f"`{call.operation_id}`")
    if call.arguments:
        st.json(call.arguments, expanded=False)
    else:
        st.caption("no arguments")


def render_operation(st, spec: Operation, *, key: str) -> None:
    """An authored step spec — tool, shape, conduct."""
    st.caption(f"tool `{spec.name}`" + (f" · stage `{spec.stage}`" if spec.stage else ""))
    render_orchestration(st, spec.orchestration, key=f"{key}_orch")
    render_step_execution(st, spec.execution, key=f"{key}_exec",
                          fanned_out=is_fanned_out(spec.orchestration))


def render_step(st, step: Step, *, key: str, operation: Tool | None = None,
                on_run=None, on_reset=None) -> None:
    """One step: status header, spec, and output. Actions are caller-supplied."""
    icon = _STATUS_ICON.get(step.status, "")
    st.markdown(f"{icon} **{step.step_id}** — {step.status.value}")

    if on_run is not None or on_reset is not None:
        with st.container(horizontal=True, gap="xxsmall"):
            if on_run is not None and st.button(":material/play_arrow:",
                                                key=f"{key}_run", help="Run this step"):
                on_run(step)
            if on_reset is not None:
                st.button(":material/refresh:", key=f"{key}_reset",
                          help="Clear this step's output", on_click=on_reset, args=(step,))

    if step.spec is not None:
        render_operation(st, step.spec, key=f"{key}_spec")
    else:
        render_tool_call(st, step.call, key=f"{key}_call")

    if step.status is StepStatus.FAILED:
        st.error(step.error or "failed")
    elif step.status is StepStatus.COMPLETED:
        render_output(st, step.output, key=f"{key}_out", operation=operation)


# ── outputs ──────────────────────────────────────────────────────────────
def render_output(st, output: StepOutput, *, key: str,
                  operation: Tool | None = None, shaded: bool = True) -> None:
    """A completed output — **the value and nothing else**.

    No status line, no duration, no headline: anything beyond the value is
    opt-in, either through the tool's own result view or by turning on the
    Status view. Cells are shaded green to mark "this ran and produced data".
    """
    renderer = operation.ui.result("streamlit") if operation is not None else None
    if renderer is not None:
        renderer(st, key=key, result=output)
        return

    render_value(st, output.value, key=key, shaded=shaded)


def render_value(st, value: Any, *, key: str, shaded: bool = True) -> None:
    """Draw one produced value with the renderer its *type* deserves.

    The grid is a spreadsheet, so anything tabular stays a shaded frame. What
    earns its own renderer is what a frame renders badly: media (show the
    picture), a lazy source (a window, not a repr), and a group result (one
    frame per bucket).
    """
    if value is None:
        st.caption("no output")
        return
    if isinstance(value, MapResult):
        render_map_result(st, value, key=key, shaded=shaded)
        return
    if isinstance(value, MediaAsset):
        render_media_asset(st, value, key=key)
        return
    if _is_media_sequence(value):
        render_media_grid(st, list(value), key=key)
        return
    # Checked before Collection: Groups is one, but strata read better as tabs.
    if _is_group_result(value):
        render_groups(st, value, key=key, shaded=shaded)
        return
    if isinstance(value, Collection):
        render_collection(st, value, key=key, shaded=shaded)
        return

    frame = to_dataframe(value)
    st.dataframe(shade(frame, OK_FILL) if shaded else frame, width="stretch")


def _is_media_sequence(value: Any) -> bool:
    """A non-empty list/tuple of media assets — a contact sheet, not a table."""
    return (
        isinstance(value, (list, tuple))
        and len(value) > 0
        and all(isinstance(item, MediaAsset) for item in value)
    )


def _is_group_result(value: Any) -> bool:
    """Strata to show as tabs: a :class:`Groups`, or a plain dict of buckets."""
    if isinstance(value, Groups):
        return len(value) > 0
    if not isinstance(value, dict) or not value:
        return False
    return all(is_frame(v) for v in value.values()) or all(
        isinstance(v, list) for v in value.values()
    )


def render_groups(st, groups: Any, *, key: str, shaded: bool = True) -> None:
    """One tab per stratum, each holding that stratum's own rows."""
    pairs = list(groups.items())
    labels = [f"{k} ({_bucket_size(v)})" for k, v in pairs]
    for tab, (name, bucket) in zip(st.tabs(labels), pairs):
        with tab:
            render_value(tab, bucket, key=f"{key}_{name}", shaded=shaded)


def _bucket_size(bucket: Any) -> int:
    try:
        return len(bucket)
    except TypeError:
        return 0


def render_collection(st, collection: Collection, *, key: str,
                      shaded: bool = True, limit: int = 50) -> None:
    """A lazy source: a window of its items, plus what it is and how fresh.

    Only ``limit`` items are read — previewing a source must not walk it.
    """
    page = collection.head(limit=limit)
    if _is_media_sequence(page):
        render_media_grid(st, page, key=key)
    else:
        frame = to_dataframe(page)
        st.dataframe(shade(frame, OK_FILL) if shaded else frame, width="stretch")

    known = collection.count()
    size = f"{known} item(s)" if known is not None else f"{len(page)}+ item(s)"
    stamp = f" · `{collection.version}`" if collection.version else ""
    st.caption(f":material/bolt: {type(collection).__name__} · {size}{stamp}")


def render_map_result(st, result: MapResult, *, key: str, shaded: bool = True) -> None:
    """A fan-out result — one row per item, shaded by that item's own outcome.

    When every successful item produced media, the table is replaced by a
    contact sheet: mapping a resize over a folder should *show the pictures*.
    Failures are still reported underneath, so nothing is hidden by the grid.
    """
    produced = [o.value for o in result.outcomes
                if o.status is StepStatus.COMPLETED]
    if produced and all(isinstance(v, MediaAsset) for v in produced):
        render_media_grid(st, produced, key=key)
        failures = [o for o in result.outcomes if o.status is StepStatus.FAILED]
        if failures:
            st.caption(f":material/error: {len(failures)} item(s) failed")
            frame = to_dataframe(MapResult(outcomes=failures))
            st.dataframe(shade_by_status(frame) if shaded else frame, width="stretch")
        return

    frame = to_dataframe(result)
    st.dataframe(shade_by_status(frame) if shaded else frame, width="stretch")


def render_output_status(st, output: StepOutput, *, key: str) -> None:
    """The timing/shape side of a completed output."""
    import pandas as pd

    value = output.value
    rows = [
        ("kind", output.kind or "—"),
        ("ref", output.ref or "—"),
        ("python type", type(value).__name__),
        ("duration", f"{output.duration:.3f}s" if output.duration is not None else "—"),
        ("started", _clock(output.started_at)),
        ("ended", _clock(output.ended_at)),
    ]
    if isinstance(value, (list, tuple, dict, str)):
        rows.append(("length", str(len(value))))
    # Every cell a string: a mixed-type column has no Arrow type to convert to.
    st.dataframe(pd.DataFrame([{"field": f, "value": str(v)} for f, v in rows]),
                 width="stretch", hide_index=True)


def render_staged_output(st, spec: Operation, definition, *, key: str,
                         shaded: bool = True) -> None:
    """What a not-yet-run step will produce: its type and shape, shaded amber."""
    frame = staged_frame(spec, definition)
    st.dataframe(shade(frame, STAGED_FILL) if shaded else frame,
                 width="stretch", hide_index=True)


# ── cell shading (the spreadsheet signal) ────────────────────────────────
#: Semi-transparent so the shading reads correctly in both light and dark themes.
STAGED_FILL = "rgba(255, 193, 7, 0.28)"      # amber — planned, not yet run
OK_FILL = "rgba(76, 175, 80, 0.28)"          # green — ran and produced a value
FAILED_FILL = "rgba(244, 67, 54, 0.28)"      # red — ran and raised


def shade(frame, fill: str):
    """Shade every cell of *frame*. Returns a Styler (st.dataframe renders it)."""
    return frame.style.map(lambda _: f"background-color: {fill}")


def shade_by_status(frame, status_column: str = "status"):
    """Shade each row by its per-item status — green for ok, red for failed."""
    def _row(row):
        fill = OK_FILL if row.get(status_column) == "completed" else FAILED_FILL
        return [f"background-color: {fill}"] * len(row)

    return frame.style.apply(_row, axis=1)


def staged_frame(spec: Operation, definition):
    """What a step *will* produce: declared type and the shape we can infer.

    Shape is knowable before a run only from the orchestration: a fan-out over a
    collection produces one cell per item, a single call produces one.
    """
    import pandas as pd

    orch = spec.orchestration
    shapes = {
        "single": "1 cell",
        "map": f"one cell per item of {orch.over}",
        "expand": f"one cell per item produced from {orch.over}",
        "filter": f"the items of {orch.over} that pass",
        "collapse": "1 cell",
        "group": f"one bucket per distinct key of {orch.over}",
    }
    return pd.DataFrame([{
        "output": spec.step_id,
        "type": staged_output_type(spec, definition),
        "shape": shapes.get(orch.mode, "1 cell"),
        "state": "staged",
    }])


# ── type helpers (read off the tool contract) ────────────────────────────
def output_type_name(definition) -> str:
    """The tool's declared return type, read off its ``output_schema``."""
    if definition is None:
        return "?"
    schema = (definition.output_schema or {}).get("properties", {}).get("result", {})
    return _schema_type(schema)


def _schema_type(schema: dict) -> str:
    """One JSON-Schema node as a Python type name, recursing into arrays."""
    jtype = schema.get("type")
    if jtype == "array":
        items = schema.get("items")
        return f"list[{_schema_type(items)}]" if items else "list"
    if jtype == "object":
        # A model/dataclass return (MediaAsset, a pydantic model) carries its
        # class name as the schema title, and "dict" would be true but useless.
        # A plain ``-> dict`` has no properties and is titled after the wrapper
        # field ("Result"), so both conditions are needed to trust the title.
        title = schema.get("title")
        if title and title != "Result" and schema.get("properties"):
            return title
        return "dict"
    return _SCALAR_TYPES.get(jtype, jtype or "Any")


def staged_output_type(spec: Operation, definition) -> str:
    """What a staged step will produce, per orchestration mode.

    The modes do not share a return shape, so this mirrors what each
    orchestrator actually returns (see ``operations/orchestrations.py``):

    ``single``   the tool's own return type
    ``map``      ``MapResult[T]`` — outcomes, ok and failed
    ``expand``   a flat ``list`` — each item's iterable concatenated
    ``filter``   the *input* collection, narrowed — a frame stays a frame
    ``group``    ``dict[K, items]`` — the tool's return type is the key K
    ``collapse`` the accumulator type — one cell
    """
    inner = output_type_name(definition)
    mode = spec.orchestration.mode

    if mode == "map":
        return f"MapResult[{inner}]"
    if mode == "expand":
        # op returns an iterable per item; expand concatenates them.
        return inner if inner.startswith("list[") else f"list[{inner}]"
    if mode == "filter":
        # The elements come from `over`, not from this tool — and the container
        # is whatever `over` was, since filter preserves shape.
        return f"same as {spec.orchestration.over or 'input'}"
    if mode == "group":
        # The tool is the key function, so its return type is the stratum key.
        return f"Groups[{inner}]"
    return inner               # single and collapse both yield the tool's type


def to_dataframe(value: Any):
    """Best-effort tabular view of a completed step's output."""
    import pandas as pd

    if isinstance(value, MapResult):
        return pd.DataFrame([
            {"index": o.index, "status": o.status.value, "value": o.value, "error": o.error}
            for o in value.outcomes
        ])
    if is_frame(value):
        return value  # already dataframe-like
    if isinstance(value, MediaAsset):
        return pd.DataFrame([{"name": value.name, "media_type": value.media_type,
                              "path": value.path}])
    if isinstance(value, Collection):
        return to_dataframe(value.head())
    if isinstance(value, list):
        if value and all(isinstance(v, MediaAsset) for v in value):
            return pd.DataFrame([{"name": v.name, "media_type": v.media_type,
                                  "path": v.path} for v in value])
        if value and all(isinstance(v, dict) for v in value):
            return pd.DataFrame(value)
        return pd.DataFrame({"value": value})
    if isinstance(value, dict):
        return pd.DataFrame([value])
    return pd.DataFrame({"value": [value]})


def render_item_outcome(st, outcome: ItemOutcome, *, key: str) -> None:
    """One item of a fan-out."""
    st.caption(f"[{outcome.index}] {outcome.status.value}"
               + (f" — {outcome.error}" if outcome.error else ""))


def _clock(ts: Any) -> str:
    """Format an epoch timestamp as a readable wall-clock time."""
    if ts is None:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S.%f")[:-3]
    except (TypeError, ValueError, OSError):
        return str(ts)
