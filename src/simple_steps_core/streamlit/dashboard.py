"""
Streamlit dashboard
===================

An optional, generic UI for building and running workflows from a tools file —
the Streamlit counterpart of the FastAPI ``Server``. Users write one file that
registers tools (and optional ``CONFIG`` / ``RESOURCES``), import ``Dashboard``,
and call it at the bottom::

    from simple_steps_core import register_tool
    from simple_steps_core.streamlit import Dashboard

    @register_tool("add")
    def add(a: int, b: int) -> int:
        return a + b

    if __name__ == "__main__":
        Dashboard().run()

then run it with ``python mytools.py`` (needs ``pip install
"simple-steps-core[dashboard]"``).

The **tool contract** is the generic UI schema, and this module renders every
widget from it — nothing here hard-codes a tool:

  * ``definition.params`` — name, ``kind`` (``data`` is asked for, ``resource``
    is injected by the runtime), ``required`` and the signature default;
  * ``definition.input_schema`` — the JSON-Schema type that picks the widget;
  * ``definition.guardrails`` — ``arguments[name]`` bounds/enums/lengths that
    constrain it, plus ``destructive`` / ``requires_confirmation`` flags.

Each tool also carries a ``ToolUI`` (``operation.ui``) of per-surface views
keyed by target, each with two lifecycle phases:

  * ``operation.ui.prefab`` — a prefab-ui protocol (for a React frontend);
  * ``operation.ui.input("streamlit")`` — ``render(st, *, key, defaults) ->
    args dict``. Absent, a form is auto-built from the contract above;
  * ``operation.ui.result("streamlit")`` — ``render(st, *, key, result) ->
    None``, where ``result`` is the ``StepOutput`` (``result.value`` plus the
    timing fields). Absent, the value is shown as a table or scalar.

A tool that supplies its own ``input`` view owns its whole form, so the Step
Manager cannot offer reference binding ("use an earlier step's output") for it;
tools using the auto-form get that picker per argument.

Streamlit is imported lazily so importing this module never requires it.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from typing import Any

# Absolute imports: `streamlit run` executes this file as a top-level script
# (no parent package), so relative imports would fail.
from simple_steps_core.loader import load_tools_module
from simple_steps_core.operations.orchestrations import register_orchestrators
from simple_steps_core.operations.registry import REGISTRY, Tool

_ENV_TOOLS = "SIMPLE_STEPS_TOOLS"

# The Step Manager row scrolls horizontally instead of wrapping/shrinking its
# cards — keyed so the CSS below can target it (see `_render_app`).
_CARDS_KEY = "step_cards_row"
_CARD_WIDTH = 260

# JSON-Schema scalar types -> the Python names a user recognises.
_SCALAR_TYPES = {
    "integer": "int", "number": "float", "string": "str",
    "boolean": "bool", "null": "None",
}




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


def render_resource_params(st, params) -> None:
    """Show a tool's injected resource params — supplied by the runtime, not the user."""
    names = [p.name for p in params if p.kind == "resource"]
    if names:
        st.caption(
            ":material/database: injected resource"
            f"{'s' if len(names) > 1 else ''}: " + ", ".join(f"`{n}`" for n in names)
        )


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


def render_tool_result(st, operation: Tool, result: Any, *, key: str) -> None:
    """Render a completed ``StepOutput`` with the tool's result view, or a fallback.

    A tool's own view (``ui.result("streamlit")``) receives the ``StepOutput``
    as ``result``, so it can read both ``result.value`` and the timing fields.
    The fallback renders the value as a table when it is tabular, and with the
    type-appropriate Streamlit widget otherwise.
    """
    renderer = operation.ui.result("streamlit") if operation is not None else None
    if renderer is not None:
        renderer(st, key=key, result=result)
        return

    value = result.value

    if value is None:
        st.caption("no output")
        return
    if isinstance(value, bool) or isinstance(value, (int, float, str)):
        st.write(value)
        return
    st.dataframe(_to_dataframe(value), width="stretch")


def _clock(ts: Any) -> str:
    """Format an epoch timestamp as a readable wall-clock time."""
    if ts is None:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S.%f")[:-3]
    except (TypeError, ValueError, OSError):
        return str(ts)


def render_output_status(st, output) -> None:
    """The timing/shape side of a completed ``StepOutput`` — the Status tab."""
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

    # Every cell is a string: a mixed-type column has no Arrow type to convert to.
    st.dataframe(
        pd.DataFrame([{"field": f, "value": str(v)} for f, v in rows]),
        width="stretch", hide_index=True,
    )


def _default_orchestration() -> dict[str, Any]:
    # Shape only — mirrors OrchestrationConfig.
    return {"mode": "single", "over": None, "item_arg": None, "initial": None}


def _default_execution() -> dict[str, Any]:
    # Mirrors StepExecutionConfig's fields exactly. Anything extra here breaks
    # round-tripping, since a reloaded step is seeded from `model_dump()`.
    return {"run": "manual", "timeout": None, "retries": 0, "cache": False,
            "concurrency": 1, "on_item_error": None}


def output_type_name(definition) -> str:
    """The tool's declared return type, read off its ``output_schema``."""
    schema = (definition.output_schema or {}).get("properties", {}).get("result", {})
    jtype = schema.get("type")

    if jtype == "array":
        item = (schema.get("items") or {}).get("type")
        return f"list[{_SCALAR_TYPES.get(item, item)}]" if item else "list"
    if jtype == "object":
        return "dict"
    return _SCALAR_TYPES.get(jtype, jtype or "Any")


def staged_output_type(d: dict[str, Any], definition) -> str:
    """What a staged step will produce — a fan-out wraps the tool's type in a MapResult."""
    if definition is None:
        return "?"
    inner = output_type_name(definition)
    orch = d.get("orchestration") or _default_orchestration()
    if orch["mode"] != "single":
        return f"MapResult[{inner}]"
    return inner


def is_fanned_out(d: dict[str, Any]) -> bool:
    """True when the step has a real orchestration component (not a single call)."""
    orch = d.get("orchestration") or _default_orchestration()
    return orch["mode"] != "single"


def returns_dataframe(definition) -> bool:
    """True when the tool declares a dataframe return (the library's own signal)."""
    return definition is not None and definition.type == "dataframe"


def _staging_dataframe(d: dict[str, Any], arguments: dict[str, Any]):
    """A one-row preview of what a not-yet-run step will do (op + orchestration)."""
    import pandas as pd

    orch = d.get("orchestration") or _default_orchestration()
    row = {
        "step": d["id"],
        "operation": d["op"] or "—",
        "stage": d["stage"] or "—",
        "mode": orch["mode"],
        "arguments": ", ".join(f"{k}={v!r}" for k, v in arguments.items()) or "—",
    }
    if orch["mode"] != "single":
        execu = d.get("execution") or _default_execution()
        row["over"] = orch["over"] or "—"
        row["item_arg"] = orch["item_arg"] or "(auto)"
        row["concurrency"] = execu["concurrency"]
        row["on_item_error"] = execu["on_item_error"] or "(default)"
    return pd.DataFrame([row])


def _to_dataframe(value: Any):
    """Best-effort tabular view of a completed step's output.

    Orchestrator results (``MapResult``) become one row per item (index,
    status, value, error); dataframes pass through; lists/dicts/scalars are
    coerced into a small table.
    """
    import pandas as pd

    from simple_steps_core.domain.models import MapResult

    if isinstance(value, MapResult):
        return pd.DataFrame([
            {"index": o.index, "status": o.status.value, "value": o.value, "error": o.error}
            for o in value.outcomes
        ])
    if hasattr(value, "columns") and hasattr(value, "iloc"):
        return value  # already dataframe-like
    if isinstance(value, list):
        if value and all(isinstance(v, dict) for v in value):
            return pd.DataFrame(value)
        return pd.DataFrame({"value": value})
    if isinstance(value, dict):
        return pd.DataFrame([value])
    return pd.DataFrame({"value": [value]})


# ─────────────────────────────────────────────────────────────────────────
# The Streamlit app (imports streamlit lazily; runs under `streamlit run`)
# ─────────────────────────────────────────────────────────────────────────
def _render_app(config: dict[str, Any], resources: dict[str, Any]) -> None:
    import streamlit as st

    from simple_steps_core.domain.models import StepExecutionConfig, OrchestrationConfig, Operation, StepStatus
    from simple_steps_core.execution.engine import CoreEngine
    from simple_steps_core.execution.workflow import Workflow

    definitions = REGISTRY.list_definitions()
    tool_ids = [d.operation_id for d in definitions]

    st.set_page_config(page_title=config.get("title", "simple-steps"), layout="wide")
    #st.title(config.get("title", "simple-steps dashboard"))


    st.markdown(
    """
    <style>
    /* Target the expander header */
    [data-testid="stExpander"] details summary {
        padding-top: 0.20rem !important;
        padding-bottom: 0.20rem !important;
        min-height: unset !important;
    }
    /* Target the text inside the header */
    [data-testid="stExpander"] details summary p {
        font-size: 14px !important; /* Optional: shrink text slightly */
    }
    </style>
    """,
    unsafe_allow_html=True
)



    def _register_resources(target: Workflow) -> None:
        for name, provider in resources.items():
            if callable(provider):
                target.context.resources.register(name, provider)
            else:
                target.context.resources.register_value(name, provider)

    st.session_state.setdefault("selected_steps", [])
    st.session_state.setdefault("selected_steps_nonce", 0)

    def _touch_selection_widget() -> None:
        # The step-selector segmented control is keyed by this nonce (see
        # below). Bumping it forces a fresh remount next render, reseeded
        # from `selected_steps` via `default=` — needed whenever we set
        # `selected_steps` from code rather than from a click on that widget
        # itself, since a widget only re-reads `default=` on (re)mount.
        st.session_state.selected_steps_nonce += 1

    def _rerun() -> None:
        # st.segmented_control's pressed/selected styling also desyncs from
        # its true value after an *explicit* st.rerun() (a normal on_click-
        # triggered rerun is fine), so treat it the same as a code-driven
        # change above.
        _touch_selection_widget()
        st.rerun()

    # One Workflow for the whole session — the same object you'd build in Python:
    #   wf["step1"] = make_list(n=5); wf["step2"] = scale(x="step1"); wf.run()
    if "wf" not in st.session_state:
        wf = Workflow(CoreEngine(REGISTRY), session_id="dashboard")
        _register_resources(wf)
        st.session_state.wf = wf
    wf: Workflow = st.session_state.wf

    def _draft_from_workflow(target: Workflow) -> list[dict[str, Any]]:
        """Rebuild the lightweight `draft` list from a workflow's own steps."""
        step_ids = {s.step_id for s in target.steps}
        rebuilt = []
        for step in target.steps:
            spec = step.spec
            sources: dict[str, str] = {}
            if spec is not None:
                for name, value in spec.arguments.items():
                    if isinstance(value, str) and value in step_ids and value != step.step_id:
                        sources[name] = value
                st.session_state[f"cached_args_{step.step_id}"] = dict(spec.arguments)
            rebuilt.append({
                "id": step.step_id,
                "op": spec.name if spec is not None else step.call.operation_id,
                "stage": spec.stage if spec is not None else None,
                "sources": sources,
                "orchestration": spec.orchestration.model_dump() if spec is not None else _default_orchestration(),
                "execution": spec.execution.model_dump() if spec is not None else _default_execution(),
            })
        return rebuilt

    def _load_workflow(data: str) -> None:
        """Replace the session's workflow with one imported from a full snapshot."""
        imported = Workflow.import_session_json(data, CoreEngine(REGISTRY))
        _register_resources(imported)
        st.session_state.wf = imported
        loaded_draft = _draft_from_workflow(imported)
        st.session_state.draft = loaded_draft
        # select every loaded step so the segmented control reflects them right away
        st.session_state.selected_steps = [d["id"] for d in loaded_draft]
        st.session_state.step_seq = len(imported.steps)
        st.session_state.stage_seq = len({s.spec.stage for s in imported.steps if s.spec and s.spec.stage})

    def _sample_workflow_json() -> str:
        """A small make_list -> scale chain, already run, used as a demo/test fixture."""
        sample = Workflow(CoreEngine(REGISTRY), session_id="sample")
        sample["step1"] = Operation(step_id="step1", name="make_list", arguments={"n": 5})
        sample["step2"] = Operation(step_id="step2", name="scale", arguments={"x": "step1", "factor": 3})
        sample.run()
        return sample.export_session_json()

    # ── Sidebar: the tools available in the registry ─────────────────────
    with st.sidebar:
        with st.expander("Manage Workflow"):
            try:
                export_data = wf.export_session_json() if wf.steps else None
            except Exception as exc:
                export_data = None
                st.caption(f"Can't export yet: {exc}")
            st.download_button(
                ":material/download: Export workflow",
                data=export_data or "",
                file_name="workflow.json",
                mime="application/json",
                disabled=export_data is None,
            )
            uploaded = st.file_uploader("Import workflow", type="json", key="wf_upload")
            if uploaded is not None and st.button(":material/upload: Load uploaded workflow"):
                try:
                    _load_workflow(uploaded.getvalue().decode("utf-8"))
                except Exception as exc:
                    st.error(f"Couldn't load that workflow: {exc}")
                else:
                    _rerun()
            if {"make_list", "scale"} <= set(tool_ids):
                st.caption("Sample workflow — make_list → scale, already run.")
                if st.button(":material/science: Load sample workflow"):
                    _load_workflow(_sample_workflow_json())
                    _rerun()

        st.divider()
        with st.expander("Tools"):
            for d in definitions:
                with st.expander(d.operation_id):
                    st.caption(d.description or "—")
                    st.write({p.name: p.type_name for p in d.params if p.kind == "data"})
        with st.expander("Resources"):
            if resources:
                st.caption("Resources: " + ", ".join(resources))

    # ── Draft steps: lightweight UI state, authored into `wf` each rerun ──
    # `draft` mirrors the Python script one line at a time: {"id", "op",
    # "stage"}. Only structural edits (add/remove/group/ungroup/swap) are
    # true widget callbacks — they touch this small list, not the engine, so
    # they're free. Running a step needs its freshly-collected form
    # arguments, which only exist once the form has rendered, so runs are
    # requested during the render pass and executed once at the end (still
    # only on an explicit button press — nothing runs on every rerun).
    st.session_state.setdefault("draft", [])           # [{"id", "op", "stage"}]
    st.session_state.setdefault("step_seq", 0)
    st.session_state.setdefault("stage_seq", 0)
    draft: list[dict[str, Any]] = st.session_state.draft

    def _selected() -> list[str]:
        return list(st.session_state.get("selected_steps") or [])

    def _add_step() -> None:
        st.session_state.step_seq += 1
        sid = f"step{st.session_state.step_seq}"
        draft.append({
            "id": sid, "op": None, "stage": None,
            "sources": {}, "orchestration": _default_orchestration(), "execution": _default_execution(),
        })
        # newly added step is selected right away, ready to edit in the viewer
        st.session_state.selected_steps = [*_selected(), sid]
        _touch_selection_widget()

    def _remove_selected() -> None:
        selected = set(_selected())
        st.session_state.draft = [d for d in draft if d["id"] not in selected]
        for sid in selected:
            if sid in wf:
                del wf[sid]
        st.session_state.selected_steps = []
        _touch_selection_widget()

    def _swap_selected() -> None:
        selected = _selected()
        if len(selected) != 2:
            return
        i = next(i for i, d in enumerate(draft) if d["id"] == selected[0])
        j = next(i for i, d in enumerate(draft) if d["id"] == selected[1])
        draft[i], draft[j] = draft[j], draft[i]

    def _group_selected() -> None:
        selected = set(_selected())
        if len(selected) < 2:
            return
        st.session_state.stage_seq += 1
        stage = f"Stage {st.session_state.stage_seq}"
        for d in draft:
            if d["id"] in selected:
                d["stage"] = stage
        st.session_state.selected_steps = []
        _touch_selection_widget()

    def _ungroup_selected() -> None:
        selected = set(_selected())
        for d in draft:
            if d["id"] in selected:
                d["stage"] = None
        st.session_state.selected_steps = []
        _touch_selection_widget()

    def _clear_all() -> None:
        st.session_state.draft = []
        st.session_state.selected_steps = []
        st.session_state.pop("wf", None)
        _touch_selection_widget()

    # ── Workflow Manager toolbar ───────────────────────────────────────────
    with st.expander("Workflow Manager", expanded=True):
        select_col, manage_col = st.columns([5, 1])
        with select_col:
            def _label(sid: str) -> str:
                d = next(d for d in draft if d["id"] == sid)
                return f"{sid} · {d['op'] or '—'}" + (f" [{d['stage']}]" if d["stage"] else "")

            option_ids = {d["id"] for d in draft}
            selected_now = st.segmented_control(
                "Current steps",
                options=[d["id"] for d in draft],
                format_func=_label,
                selection_mode="multi",
                default=[sid for sid in st.session_state.selected_steps if sid in option_ids],
                key=f"selected_steps_widget_{st.session_state.selected_steps_nonce}",
            )
            st.session_state.selected_steps = selected_now or []
            with st.container(horizontal=True, vertical_alignment="top",gap="xxsmall"):
                st.button(":material/add_circle_outline: Add", on_click=_add_step)
                st.button(":material/remove_circle_outline: Remove", on_click=_remove_selected,
                          disabled=not _selected())
                st.button(":material/swap_horiz: Swap", on_click=_swap_selected,
                          disabled=len(_selected()) != 2)
        with manage_col:
            with st.container(horizontal=True, vertical_alignment="top"):
                with st.popover("Group into stages"):
                    st.button(":material/merge_type: Group selected", on_click=_group_selected,
                            disabled=len(_selected()) < 2)
                    st.button(":material/call_split: Ungroup selected", on_click=_ungroup_selected,
                            disabled=not _selected())
                with st.popover(":material/smart_toy: Assistant"):
                    st.caption("Assistant placeholder")

        st.divider()
        with st.container(horizontal=True, gap="xxsmall"):
            run_all = st.button(":material/play_arrow: Run all", disabled=not draft)
            with st.popover(":material/refresh: Reset", disabled=not draft):
                st.warning("This removes every step and clears all results. This can't be undone.")
                st.button(":material/warning: Yes, clear everything", on_click=_clear_all)

    if not draft:
        st.info("Add a step to begin.")
        return

    # Force the horizontal row to scroll instead of wrap/shrink its cards.
    st.markdown(
        f"""
        <style>
        div.st-key-{_CARDS_KEY} {{
            overflow-x: auto;
            overflow-y: hidden;
            padding-bottom: 0.5rem;
        }}
        div.st-key-{_CARDS_KEY} > div {{
            flex-wrap: nowrap !important;
            min-width: max-content;
        }}
        div.st-key-{_CARDS_KEY} > div > div {{
            flex-shrink: 0 !important;
        }}
        div[class*="st-key-card_"] {{
            min-width: {_CARD_WIDTH}px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Step Manager: cards in draft order; same-stage cards share a group ─
    specs: dict[str, Operation] = {}
    run_requests: list[tuple[str, str]] = []   # ("step"|"stage"|"from", id)


    # this should be a fragment 

    def _render_card(d: dict[str, Any]) -> None:

        # need view controls here
        st.session_state.setdefault(f"step_view_controller_{d['id']}", [":material/step:",":material/function:", ":material/dataset:"])


        sid = d["id"]
        prior = [s["id"] for s in draft if s["id"] != sid and s["id"] in specs]
        d.setdefault("sources", {})
        d.setdefault("orchestration", _default_orchestration())
        d.setdefault("execution", _default_execution())
        args_cache_key = f"cached_args_{sid}"

        def _reset_step(sid: str = sid) -> None:
            if sid in wf:
                del wf[sid]

        # step control_header # container
        
        with st.container(key=f"step_{sid}_card", gap="xxsmall"):

            # steop contoller
            if ":material/step:" in st.session_state[f"step_view_controller_{sid}"]:
                with st.expander(":material/step: Step Controls", expanded=True,type="compact"):
                    
                    #st.session_state.setdefault(f"step_view_controller_{sid}", [":material/step:",":material/function:", ":material/dataset:"])
                    #with step_contol_container:
                        #with st.container(horizontal=True, gap="xxsmall", horizontal_alignment="left"):

                    
                    with st.container(horizontal=True, gap="xxsmall",key=f"step_{sid}_controller"):
                        #st.write(f"{sid}")
                        with st.container(horizontal=True, gap="xxsmall",width="content",horizontal_alignment="left"):
                            if st.button(":material/play_arrow:", key=f"run_{sid}", help="Run this step",type="primary"):
                                run_requests.append(("step", sid))
                            st.button(":material/refresh:", key=f"reset_{sid}", help="Clear this step's output",
                                        on_click=_reset_step, disabled=sid not in wf,type="secondary")
                        #if st.button(":material/fast_forward:", key=f"ff_{sid}", help="Run this step and every step after it",type="secondary"):
                        #    run_requests.append(("from", sid))
                        with st.container(horizontal=True, gap="xxsmall",key=f"step_{sid}_header_controls",horizontal_alignment="center"):
                            st.space("stretch")
                            

                        
                        #   st.header(f"{sid}")
                        #exec_col,view_col = st.columns(2)
                        with st.container(horizontal=True, gap="xxsmall",width="content",horizontal_alignment="right",key=f"step_{sid}_view_controls"):
                            
                            with st.popover(":material/visibility:",type="secondary"):
                            #visibility
                                st.header("View Selection")
                                st.segmented_control(
                                label=f"{sid}",
                                selection_mode="multi",
                                options=[":material/step:", ":material/function:",":material/dataset:",":material/analytics:", ":material/smart_toy:",":material/settings:"],
                                key=f"step_view_controller_{sid}",
                                # seeded by the setdefault above; passing `default=`
                                # as well is what Streamlit warns about
                                help="Select Step components to see for this step",
                                label_visibility="collapsed"
                                )
                            
                    # make on change component here



                            

                    st.markdown("___")
                

            if ":material/function:" in st.session_state[f"step_view_controller_{sid}"]:
                #with st.expander(":material/function: Operation"):
                with st.expander(":material/function: Operation",type="compact"):
                    d["op"] = st.selectbox(
                        ":material/construction: Tool ", tool_ids,
                        index=tool_ids.index(d["op"]) if d["op"] in tool_ids else None,
                        placeholder="choose an operation…",
                        key=f"op_{sid}",)
                    arguments, op = _render_function_tabs(d, prior)
                    st.markdown("___")
                #step_op_tab, step_input_tab, step_runtime_settings_tab = st.tabs([":material/construction: Tool", ":material/input: Input", ":material/settings: run settings"])
                #with st.expander(":material/function: Operation"):


                    #with step_op_tab:

                        

                    #with step_input_tab:
                        
                        #st.markdown("This panel allows you to configure the input for this step.")

                    #if ":material/settings:" in selected_step_controls:
                    #with st.expander(":material/settings: Settings"):
                    #with step_runtime_settings_tab:
                    #    st.markdown("This panel allows you to configure the settings for this step.")
                    

            else:
                arguments = st.session_state.get(args_cache_key, {})
                op = REGISTRY.get_operation(d["op"]) if d["op"] else None





            if ":material/tune:" in st.session_state[f"step_view_controller_{sid}"]:
                with st.expander(":material/tune: Advanced Settings"):  #else st.container():
                    st.markdown("This panel allows you to configure additional settings for this step.")


            #if ":material/smart_toy:" in selected_step_controls:
            #    with st.expander(":material/smart_toy: Agent "):
            #        st.markdown("This panel shows the orchestration and execution details for this step.")



            # The segmented control fully mounts/unmounts these two panels
            # (not just collapse) — when a panel is unmounted, the Function
            # panel's inputs aren't rendered, so we reuse the last collected
            # arguments/config rather than losing the step's spec.
            #if ":material/function:" in view:




            if d["op"]:
                orch, execu = d["orchestration"], d["execution"]
                specs[sid] = Operation(
                    step_id=sid, name=d["op"], stage=d["stage"], arguments=arguments,
                    orchestration=OrchestrationConfig(
                        mode=orch["mode"], over=orch["over"],
                        item_arg=orch["item_arg"], initial=orch["initial"],
                    ),
                    execution=StepExecutionConfig(
                        run=execu["run"], timeout=execu["timeout"],
                        retries=int(execu["retries"]), cache=execu["cache"],
                        concurrency=int(execu["concurrency"]),
                        on_item_error=execu["on_item_error"],
                    ),
                )
                

            if ":material/dataset:" in st.session_state[f"step_view_controller_{sid}"]:
                with st.expander(":material/output: Result", expanded=True,type="compact"):
                    step_data_output_tab,step_output_analysis_tab = st.tabs([":material/dataset: Value", ":material/analytics: Status"])
                    with step_data_output_tab:
                    #with st.expander(":material/dataset: Output", expanded=True):
                        rec = wf[sid] if sid in wf else None
                        if rec is None or rec.status is StepStatus.PENDING:
                            definition = op.definition if op is not None else None
                            # The staging table only earns its space when there is
                            # something tabular to preview: a fan-out's per-item
                            # plan, or a tool that returns a dataframe. Otherwise
                            # a staged step is just a type waiting to be filled.
                            if is_fanned_out(d) or returns_dataframe(definition):
                                st.dataframe(
                                    _staging_dataframe(d, arguments),
                                    width="stretch", hide_index=True,
                                )
                            else:
                                st.text(f"(staged) output {sid}: {staged_output_type(d, definition)}")
                        elif rec.status is StepStatus.RUNNING:
                            st.info("running…")
                        elif rec.status is StepStatus.COMPLETED:
                            st.success("done")
                            render_tool_result(st, op, rec.output, key=f"result_{sid}")
                        elif rec.status is StepStatus.FAILED:
                            st.error(rec.error or "failed")
                    with step_output_analysis_tab:
                        rec = wf[sid] if sid in wf else None
                        if rec is None or rec.output is None or rec.status is not StepStatus.COMPLETED:
                            st.caption("Run this step to see its output status.")
                        else:
                            render_output_status(st, rec.output)

    def _render_function_tabs(d: dict[str, Any], prior: list[str]) -> tuple[dict[str, Any], Tool | None]:
        """The Function panel's tabs: Input (arguments + orchestration) and Runtime.

        Returns the merged ``arguments`` dict (by-hand values + reference
        tokens) and the selected Operation (or None until one is chosen).
        """
        sid = d["id"]

        if not d["op"]:
            st.caption("Choose a tool first.")
            return {}, None

        step_input_tab, step_runtime_settings_tab = st.tabs(
            [":material/input: Input", ":material/settings: Runtime settings"]
        )
        op = REGISTRY.get_operation(d["op"])
        definition = op.definition
        data_params = [p for p in definition.params if p.kind == "data"]
        param_names = [p.name for p in data_params]
        custom_renderer = op.ui.input("streamlit")
        cached = st.session_state.get(f"cached_args_{sid}", {})
        arguments: dict[str, Any] = {}

        with step_input_tab:
            if definition.description:
                st.caption(definition.description)

            guard = definition.guardrails
            if guard is not None and (guard.destructive or guard.requires_confirmation):
                flags = []
                if guard.destructive:
                    flags.append("destructive")
                if guard.requires_confirmation:
                    flags.append("needs confirmation")
                st.warning(
                    f":material/warning: {' · '.join(flags)}"
                    + (f" — {guard.usage}" if guard.usage else "")
                )

            # Resource params are injected by the runtime; show them, don't ask.
            render_resource_params(st, definition.params)

            if custom_renderer is not None:
                # The tool owns its whole form; no by-hand/reference split.
                arguments = custom_renderer(st, key=f"form_{sid}", defaults=cached) or {}
                if prior:
                    st.caption(
                        "This tool renders its own form, so argument references "
                        "aren't available here."
                    )
            elif not data_params:
                st.caption("This tool takes no arguments.")
            else:
                for param in data_params:
                    name = param.name
                    current = d["sources"].get(name, "(value)")

                    # Bind to an earlier step's output, or supply a literal.
                    if prior:
                        options = ["(value)", *prior]
                        chosen = st.selectbox(
                            f"{name} — source", options,
                            index=options.index(current) if current in options else 0,
                            key=f"src_{sid}_{name}",
                            help="Use a literal value, or the output of an earlier step.",
                        )
                    else:
                        chosen = "(value)"

                    if chosen == "(value)":
                        d["sources"].pop(name, None)
                        value = render_literal_arg(
                            st, definition, param,
                            key=f"form_{sid}", default=cached.get(name),
                        )
                        # An empty optional field means "use the tool's default".
                        if value is None and not param.required:
                            continue
                        arguments[name] = value
                    else:
                        d["sources"][name] = chosen
                        arguments[name] = chosen  # a step-id reference

            # Orchestration applies to every tool, referenced or not.
            with st.expander("Orchestration Settings", type="compact"):
                st.caption("Orchestration — run this tool once, or fan it out over a collection.")
                modes = ["single", "map", "filter", "expand", "collapse"]
                orch = d["orchestration"]
                orch["mode"] = st.selectbox(
                    "mode", modes, index=modes.index(orch["mode"]), key=f"orch_mode_{sid}",
                )
                if orch["mode"] != "single":
                    if not prior:
                        st.caption("Add an earlier step to fan out over.")
                    over_options = ["(none)", *prior]
                    current_over = orch["over"] if orch["over"] in over_options else "(none)"
                    over = st.selectbox(
                        "over — the collection to fan out across", over_options,
                        index=over_options.index(current_over), key=f"orch_over_{sid}",
                    )
                    orch["over"] = None if over == "(none)" else over

                    item_options = ["(auto)", *param_names]
                    current_item = orch["item_arg"] if orch["item_arg"] in item_options else "(auto)"
                    item_arg = st.selectbox(
                        "item argument — which param each item binds to", item_options,
                        index=item_options.index(current_item), key=f"orch_item_{sid}",
                    )
                    orch["item_arg"] = None if item_arg == "(auto)" else item_arg

                    st.caption(
                        "Concurrency, retries and per-item error policy are "
                        "**Runtime settings** — this tab only shapes the data."
                    )
                    if orch["mode"] == "collapse":
                        orch["initial"] = st.text_input(
                            "initial — seed value for the accumulator",
                            value="" if orch["initial"] is None else str(orch["initial"]),
                            key=f"orch_initial_{sid}",
                        )

        with step_runtime_settings_tab:
            st.caption("How this step is invoked.")
            execu = d["execution"]
            # sync/async is derived from the tool (``Tool.is_async``), never set
            # here — show it rather than offering a control that does nothing.
            st.caption(f":material/bolt: call style: `{'async' if op.is_async else 'sync'}` (from the tool)")
            run_modes = ["manual", "auto"]
            execu["run"] = st.selectbox("run", run_modes, index=run_modes.index(execu["run"]), key=f"exec_run_{sid}",
                                          help="'manual' waits for the Run button; 'auto' is a hint for orchestrated runners.")
            has_timeout = st.checkbox("set a timeout", value=execu["timeout"] is not None, key=f"exec_timeout_on_{sid}")
            execu["timeout"] = (
                st.number_input("timeout (seconds)", min_value=0.0, value=float(execu["timeout"] or 30.0),
                                  key=f"exec_timeout_{sid}")
                if has_timeout else None
            )
            execu["retries"] = st.number_input("retries", min_value=0, step=1,
                                                 value=int(execu["retries"]), key=f"exec_retries_{sid}",
                                                 help="Retries one unit of work — the whole call when "
                                                      "mode is 'single', one item when fanned out.")
            execu["cache"] = st.checkbox("cache result", value=execu["cache"], key=f"exec_cache_{sid}")

            # Per-item conduct only means something once there is more than one unit.
            if is_fanned_out(d):
                st.markdown("___")
                st.caption(f"Per-item conduct for this `{d['orchestration']['mode']}` step.")
                execu["concurrency"] = st.number_input(
                    "concurrency", min_value=1, step=1,
                    value=int(execu["concurrency"]), key=f"exec_conc_{sid}",
                    help="How many items run at once.",
                )
                error_options = ["(default)", "collect", "fail_fast", "skip"]
                current_err = execu["on_item_error"] or "(default)"
                on_item_error = st.selectbox(
                    "on_item_error", error_options,
                    index=error_options.index(current_err), key=f"exec_item_err_{sid}",
                    help="What a single failed item does to the batch.",
                )
                execu["on_item_error"] = None if on_item_error == "(default)" else on_item_error

        # Remember what the user typed so an unmounted panel can re-author the spec.
        st.session_state[f"cached_args_{sid}"] = dict(arguments)
        return arguments, op


    def _author_hidden(d: dict[str, Any]) -> None:
        """Keep an unselected step's spec authored into `wf` without rendering it."""
        sid = d["id"]
        if not d["op"]:
            return
        d.setdefault("orchestration", _default_orchestration())
        d.setdefault("execution", _default_execution())
        arguments = st.session_state.get(f"cached_args_{sid}", {})
        orch, execu = d["orchestration"], d["execution"]
        specs[sid] = Operation(
            step_id=sid, name=d["op"], stage=d["stage"], arguments=arguments,
            orchestration=OrchestrationConfig(
                mode=orch["mode"], over=orch["over"],
                item_arg=orch["item_arg"], initial=orch["initial"],
            ),
            execution=StepExecutionConfig(
                run=execu["run"], timeout=execu["timeout"],
                retries=int(execu["retries"]), cache=execu["cache"],
                concurrency=int(execu["concurrency"]),
                on_item_error=execu["on_item_error"],
            ),
        )

    #with st.expander("Step Manager", expanded=True):
    selected = set(_selected())
    if not selected:
        st.info("Select one or more steps above to view them here.")

    st.markdown(
        f"""
        <style>
        .st-key-{_CARDS_KEY} {{
            background-color: black;
            padding: 20px;
            border-radius: 12px;
            color: white;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


    with st.container(horizontal=True, wrap=False, gap="xxsmall", key=_CARDS_KEY):
        rendered: set[str] = set()
        for d in draft:
            if d["id"] in rendered:
                continue
            if d["stage"] is None:
                #with st.expander("Step 1: Input Data", type="step", expanded=True):
                    stage = d["stage"]
                    members = [m for m in draft if m["stage"] == stage]
                    visible_members = [m for m in members if m["id"] in selected]
                    for member in members:
                        if member["id"] not in selected:
                            _author_hidden(member)
                            
            if visible_members:
                #with st.container():
                    #st.caption(f"🗂 {stage}")
                    #if st.button(":material/play_arrow: Run stage", key=f"run_stage_{stage}"):
                    #    run_requests.append(("stage", stage))
                    
                    
                        for member in visible_members:
                            #with st.container(wrap=False, gap="xxsmall", border=True):
                            with st.expander(f"{member['id']}", expanded=True):
                            #st.write(f"{member['id']}")
                                _render_card(member)
            rendered.update(m["id"] for m in members)

    # ── Author the draft into the workflow (structure only, cheap) ───────
    for step_id in list(wf._steps):
        if step_id not in specs:
            del wf[step_id]

    # A half-authored step is normal while editing (e.g. mode="map" chosen
    # before `over`). The library validates on assignment, so keep the step out
    # of the workflow and surface its own message rather than crashing the page.
    incomplete: dict[str, str] = {}
    for sid, spec in specs.items():
        if sid not in wf or wf[sid].spec != spec:
            try:
                wf[sid] = spec
            except (ValueError, TypeError) as exc:
                incomplete[sid] = str(exc)
    for sid, message in incomplete.items():
        st.warning(f":material/warning: **{sid}** isn't runnable yet — {message}")

    # ── Execute only what was explicitly requested this run ──────────────
    ran = False
    if run_all:
        try:
            wf.run_by_stages()
        except Exception:
            pass          # the failure is recorded on the step's record
        ran = True
    for kind, target in run_requests:
        try:
            if kind == "stage":
                wf.run_stage(target)
            elif kind == "from":
                order = [s.step_id for s in wf.steps]
                for sid in order[order.index(target):]:
                    wf.run_step(sid)      # stop the chain at the first failure
            else:
                wf.run_step(target)
        except Exception:
            pass
        ran = True
    if ran:
        _rerun()


# ─────────────────────────────────────────────────────────────────────────
# Importable entry point
# ─────────────────────────────────────────────────────────────────────────
def _under_streamlit_runtime() -> bool:
    """True when this process is already running under ``streamlit run``."""
    try:
        from streamlit.runtime import Runtime
    except Exception:
        return False
    return Runtime.exists()


def _launch_streamlit(script_path: str, *, port: int | None = None) -> None:
    """Relaunch ``script_path``'s tools under ``streamlit run`` (this module)."""
    try:
        from streamlit.web import cli as stcli  # noqa: F401
    except ImportError as exc:  # pragma: no cover - optional extra
        raise SystemExit(
            'The dashboard needs Streamlit. Install it with:\n'
            '    pip install "simple-steps-core[dashboard]"'
        ) from exc

    import subprocess

    env = {**os.environ, _ENV_TOOLS: os.path.abspath(script_path)}
    cmd = ["streamlit", "run", os.path.abspath(__file__)]
    if port:
        cmd += ["--server.port", str(port)]
    raise SystemExit(subprocess.call(cmd, env=env))


def _render_from_env() -> None:
    """Streamlit entry: load the tools file named in the environment, then render."""
    import streamlit as st

    @st.cache_resource
    def _load(path: str):
        module = load_tools_module(path)
        if not REGISTRY.has("map"):
            register_orchestrators(REGISTRY)
        config = dict(getattr(module, "CONFIG", {}) or {})
        resources = dict(getattr(module, "RESOURCES", {}) or {})
        return config, resources

    tools_path = os.environ.get(_ENV_TOOLS) or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not tools_path:
        st.error("No tools file given. Call Dashboard().run() from your tools script.")
        return

    config, resources = _load(tools_path)
    _render_app(config, resources)


class Dashboard:
    """Run the generic workflow dashboard for the tools in your own script.

    Put this at the bottom of the same script that registers your tools::

        from simple_steps_core import register_tool
        from simple_steps_core.streamlit import Dashboard

        @register_tool("add")
        def add(a: int, b: int) -> int:
            return a + b

        CONFIG = {"title": "My Tools"}   # optional
        RESOURCES = {}                    # optional

        if __name__ == "__main__":
            Dashboard().run()

    Then start it with ``python myscript.py``. Pass ``port=`` to override the
    port from ``CONFIG``.
    """

    def __init__(self, *, port: int | None = None) -> None:
        self._port = port

    def run(self) -> None:
        caller = sys._getframe(1).f_globals

        if _under_streamlit_runtime():
            # `streamlit run myscript.py` — tools are already registered above.
            if not REGISTRY.has("map"):
                register_orchestrators(REGISTRY)
            config = dict(caller.get("CONFIG", {}) or {})
            resources = dict(caller.get("RESOURCES", {}) or {})
            _render_app(config, resources)
            return

        script = caller.get("__file__")
        if not script:
            raise SystemExit("Dashboard().run() must be called from a script file.")
        config = dict(caller.get("CONFIG", {}) or {})
        _launch_streamlit(script, port=self._port or config.get("port"))


if __name__ == "__main__":
    _render_from_env()
