"""
Streamlit dashboard
===================

An optional, generic UI for building and running workflows from a tools file —
the Streamlit counterpart of ``simple-steps-core-server``. Users write one file
that registers tools (and optional ``CONFIG`` / ``RESOURCES``), then run::

    pip install "simple-steps-core[dashboard]"
    simple-steps-core-dashboard mytools.py

The **tool contract** (``params`` / ``input_schema`` / ``guardrails``) is the
generic UI schema. Each tool carries a ``ToolUI`` (``operation.ui``) holding
per-surface views keyed by target, all rendering from that one contract:

  * ``operation.ui.prefab`` — a prefab-ui protocol (for a React frontend), and
  * ``operation.ui.get("streamlit")`` — a Python callable ``render(st, key,
    defaults) -> args dict`` used here. When a tool has no Streamlit view, this
    module auto-builds a Streamlit form from the contract.

Streamlit is imported lazily so importing this module never requires it.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# Absolute imports: `streamlit run` executes this file as a top-level script
# (no parent package), so relative imports would fail.
from simple_steps_core.loader import load_tools_module
from simple_steps_core.operations.orchestrations import register_orchestrators
from simple_steps_core.operations.registry import REGISTRY, Operation

_ENV_TOOLS = "SIMPLE_STEPS_TOOLS"

# The Step Manager row scrolls horizontally instead of wrapping/shrinking its
# cards — keyed so the CSS below can target it (see `_render_app`).
_CARDS_KEY = "step_cards_row"
_CARD_WIDTH = 260


# ─────────────────────────────────────────────────────────────────────────
# Form rendering — the generic default renderer (takes `st` so it is testable)
# ─────────────────────────────────────────────────────────────────────────
def render_tool_form(
    st,
    operation: Operation,
    *,
    key: str,
    defaults: dict[str, Any] | None = None,
    available_steps: list[str] | None = None,
) -> dict[str, Any]:
    """Render a tool's argument form and return the collected arguments.

    Uses the tool's own ``ui.get("streamlit")`` view when present; otherwise
    builds a default form from the tool contract. Each data argument also offers
    a "use the output of an earlier step" reference picker.
    """
    defaults = defaults or {}
    available_steps = available_steps or []

    renderer = operation.ui.input("streamlit")
    if renderer is not None:
        return renderer(st, key=key, defaults=defaults)

    definition = operation.definition
    props = definition.input_schema.get("properties", {})
    rules = getattr(definition.guardrails, "arguments", {}) if definition.guardrails else {}
    args: dict[str, Any] = {}

    for param in definition.params:
        if param.kind != "data":
            continue  # resources are injected, never user-supplied
        name = param.name
        prop = props.get(name, {})
        rule = rules.get(name)

        # Reference vs literal: pick "(value)" or an earlier step's output.
        if available_steps:
            source = st.selectbox(
                f"{name} — source",
                ["(value)", *available_steps],
                key=f"{key}_{name}_src",
            )
            if source != "(value)":
                args[name] = source  # a step-id reference
                continue

        default = defaults.get(name, param.default)
        enum = prop.get("enum") or (rule.enum if rule and rule.enum else None)
        jtype = prop.get("type")

        if enum is not None:
            index = enum.index(default) if default in enum else 0
            args[name] = st.selectbox(name, enum, index=index, key=f"{key}_{name}")
        elif jtype == "boolean":
            args[name] = st.checkbox(name, value=bool(default), key=f"{key}_{name}")
        elif jtype in ("integer", "number"):
            kwargs: dict[str, Any] = {}
            if rule and rule.minimum is not None:
                kwargs["min_value"] = rule.minimum
            if rule and rule.maximum is not None:
                kwargs["max_value"] = rule.maximum
            seed = default if isinstance(default, (int, float)) else 0
            value = st.number_input(name, value=seed, key=f"{key}_{name}", **kwargs)
            args[name] = int(value) if jtype == "integer" else float(value)
        else:
            text = st.text_input(name, value="" if default is None else str(default), key=f"{key}_{name}")
            args[name] = text

    return args


def _render_literal_arg(st, operation: Operation, param, *, key: str, default: Any) -> Any:
    """Render one by-hand value widget for a data param (no reference picker).

    Used by the Step Manager's "Operation" tab, where reference binding has
    already been split out into its own "Inputs" tab.
    """
    definition = operation.definition
    props = definition.input_schema.get("properties", {})
    rules = getattr(definition.guardrails, "arguments", {}) if definition.guardrails else {}
    prop = props.get(param.name, {})
    rule = rules.get(param.name)
    seed = default if default is not None else param.default
    enum = prop.get("enum") or (rule.enum if rule and rule.enum else None)
    jtype = prop.get("type")

    if enum is not None:
        index = enum.index(seed) if seed in enum else 0
        return st.selectbox(param.name, enum, index=index, key=key)
    if jtype == "boolean":
        return st.checkbox(param.name, value=bool(seed), key=key)
    if jtype in ("integer", "number"):
        kwargs: dict[str, Any] = {}
        if rule and rule.minimum is not None:
            kwargs["min_value"] = rule.minimum
        if rule and rule.maximum is not None:
            kwargs["max_value"] = rule.maximum
        value = st.number_input(param.name, value=seed if isinstance(seed, (int, float)) else 0, key=key, **kwargs)
        return int(value) if jtype == "integer" else float(value)
    return st.text_input(param.name, value="" if seed is None else str(seed), key=key)


def render_tool_result(st, operation: Operation, result: Any, *, key: str) -> None:
    """Render a completed output with the custom result view or a generic fallback."""
    renderer = operation.ui.result("streamlit")
    if renderer is not None:
        renderer(st, key=key, result=result)
        return
    st.write(result.value)


def _default_orchestration() -> dict[str, Any]:
    return {"mode": "single", "over": None, "item_arg": None, "concurrency": 1,
            "on_error": None, "retries": 0, "initial": None}


def _default_execution() -> dict[str, Any]:
    return {"mode": "sync", "run": "manual", "timeout": None, "retries": 0, "cache": False}


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
        row["over"] = orch["over"] or "—"
        row["item_arg"] = orch["item_arg"] or "(auto)"
        row["concurrency"] = orch["concurrency"]
        row["on_error"] = orch["on_error"] or "(default)"
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
def _render_app() -> None:
    import streamlit as st

    from simple_steps_core.domain.models import ExecutionConfig, OrchestrationConfig, StepSpec, StepStatus
    from simple_steps_core.execution.engine import CoreEngine
    from simple_steps_core.execution.workflow import Workflow

    @st.cache_resource
    def _load(path: str):
        module = load_tools_module(path)
        if not REGISTRY.has("map"):
            register_orchestrators(REGISTRY)
        config = dict(getattr(module, "CONFIG", {}) or {})
        resources = dict(getattr(module, "RESOURCES", {}) or {})
        return module, config, resources

    tools_path = os.environ.get(_ENV_TOOLS) or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not tools_path:
        st.error("No tools file given. Run: simple-steps-core-dashboard mytools.py")
        return

    _module, config, resources = _load(tools_path)
    definitions = REGISTRY.list_definitions()
    tool_ids = [d.operation_id for d in definitions]

    st.set_page_config(page_title=config.get("title", "simple-steps"), layout="wide")
    #st.title(config.get("title", "simple-steps dashboard"))

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
        sample["step1"] = StepSpec(step_id="step1", name="make_list", arguments={"n": 5})
        sample["step2"] = StepSpec(step_id="step2", name="scale", arguments={"x": "step1", "factor": 3})
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
            with st.container(horizontal=True, vertical_alignment="top"):
                st.button(":material/add_circle_outline: Add", on_click=_add_step)
                st.button(":material/remove_circle_outline: Remove", on_click=_remove_selected,
                          disabled=not _selected())
                st.button(":material/swap_horiz: Swap", on_click=_swap_selected,
                          disabled=len(_selected()) != 2)
        with manage_col:
            with st.popover("Group into stages"):
                st.button(":material/merge_type: Group selected", on_click=_group_selected,
                           disabled=len(_selected()) < 2)
                st.button(":material/call_split: Ungroup selected", on_click=_ungroup_selected,
                           disabled=not _selected())

            with st.popover(":material/smart_toy: assisstent"):
                st.write("placeholder for assistant functionality")

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
    specs: dict[str, StepSpec] = {}
    run_requests: list[tuple[str, str]] = []   # ("step"|"stage"|"from", id)

    def _render_card(d: dict[str, Any]) -> None:
        sid = d["id"]
        prior = [s["id"] for s in draft if s["id"] != sid and s["id"] in specs]
        d.setdefault("sources", {})
        d.setdefault("orchestration", _default_orchestration())
        d.setdefault("execution", _default_execution())
        args_cache_key = f"cached_args_{sid}"

        def _reset_step(sid: str = sid) -> None:
            if sid in wf:
                del wf[sid]

        with st.container(key=f"card_{sid}"), st.expander(f"Step {sid}", expanded=True, key=f"step_{sid}"):
            exec_col, view_col = st.columns(2)
            with exec_col:
                with st.container(horizontal=True, gap="xxsmall", horizontal_alignment="left"):
                    if st.button(":material/play_arrow:", key=f"run_{sid}", help="Run this step"):
                        run_requests.append(("step", sid))
                    st.button(":material/refresh:", key=f"reset_{sid}", help="Clear this step's output",
                              on_click=_reset_step, disabled=sid not in wf)
                    if st.button(":material/fast_forward:", key=f"ff_{sid}", help="Run this step and every step after it"):
                        run_requests.append(("from", sid))
            with view_col:
                # segmented control: which of the two panels below start expanded.
                # Seed the key once in session_state instead of passing `default=`
                # on every call — some widgets re-apply `default` on reruns that
                # weren't triggered by that widget, silently undoing the user's
                # last selection.
                st.session_state.setdefault(f"view_{sid}", [":material/function:", ":material/dataset:"])
                with st.container(horizontal=True, horizontal_alignment="right"):
                    view = st.segmented_control(
                        "Step view", label_visibility="collapsed",
                        options=[":material/function:", ":material/dataset:"],
                        selection_mode="multi", key=f"view_{sid}",
                    )

            # The segmented control fully mounts/unmounts these two panels
            # (not just collapse) — when a panel is unmounted, the Function
            # panel's inputs aren't rendered, so we reuse the last collected
            # arguments/config rather than losing the step's spec.
            if ":material/function:" in view:
                with st.expander(":material/function: Function", expanded=True):
                    arguments, op = _render_function_tabs(d, prior)
                if op is not None:
                    st.session_state[args_cache_key] = arguments
            else:
                arguments = st.session_state.get(args_cache_key, {})
                op = REGISTRY.get_operation(d["op"]) if d["op"] else None

            if d["op"]:
                orch, execu = d["orchestration"], d["execution"]
                specs[sid] = StepSpec(
                    step_id=sid, name=d["op"], stage=d["stage"], arguments=arguments,
                    orchestration=OrchestrationConfig(
                        mode=orch["mode"], over=orch["over"], item_arg=orch["item_arg"],
                        concurrency=int(orch["concurrency"]), on_error=orch["on_error"],
                        retries=int(orch["retries"]), initial=orch["initial"],
                    ),
                    execution=ExecutionConfig(
                        mode=execu["mode"], run=execu["run"], timeout=execu["timeout"],
                        retries=int(execu["retries"]), cache=execu["cache"],
                    ),
                )

            if ":material/dataset:" in view:
                with st.expander(":material/dataset: Output", expanded=True):
                    rec = wf[sid] if sid in wf else None
                    if rec is None or rec.status is StepStatus.PENDING:
                        st.caption("staged — not yet run")
                        st.dataframe(_staging_dataframe(d, arguments), width="stretch", hide_index=True)
                    elif rec.status is StepStatus.RUNNING:
                        st.info("running…")
                    elif rec.status is StepStatus.COMPLETED:
                        st.success("done")
                        custom_result = op.ui.result("streamlit") if op is not None else None
                        if custom_result is not None:
                            render_tool_result(st, op, rec.output, key=f"result_{sid}")
                        else:
                            st.dataframe(_to_dataframe(rec.output.value), width="stretch")
                    elif rec.status is StepStatus.FAILED:
                        st.error(rec.error or "failed")

    def _render_function_tabs(d: dict[str, Any], prior: list[str]) -> tuple[dict[str, Any], Operation | None]:
        """The Function panel's three tabs: Operation, Inputs, Exec.

        Returns the merged ``arguments`` dict (by-hand values + reference
        tokens) and the selected Operation (or None until one is chosen).
        """
        sid = d["id"]
        op_tab, inputs_tab, exec_tab = st.tabs(["Operation", "Inputs", "Exec"])

        with op_tab:
            d["op"] = st.selectbox(
                "operation", tool_ids,
                index=tool_ids.index(d["op"]) if d["op"] in tool_ids else None,
                placeholder="choose an operation…",
                key=f"op_{sid}",
            )
        if not d["op"]:
            with inputs_tab:
                st.caption("Choose an operation first.")
            with exec_tab:
                st.caption("Choose an operation first.")
            return {}, None

        op = REGISTRY.get_operation(d["op"])
        definition = op.definition
        data_params = [p.name for p in definition.params if p.kind == "data"]
        custom_renderer = op.ui.input("streamlit")
        cached = st.session_state.get(f"cached_args_{sid}", {})

        with op_tab:
            if custom_renderer is not None:
                # The tool owns its whole form; no by-hand/reference split.
                arguments = custom_renderer(st, key=f"form_{sid}", defaults=cached)
            else:
                arguments = {}
                for name in data_params:
                    source = d["sources"].get(name, "(value)")
                    if source != "(value)":
                        st.text_input(name, value=f"← {source}", disabled=True,
                                       key=f"opview_{sid}_{name}", help="Bound in the Inputs tab")
                        continue
                    param = next(p for p in definition.params if p.name == name)
                    arguments[name] = _render_literal_arg(
                        st, op, param, key=f"form_{sid}_{name}", default=cached.get(name),
                    )

        with inputs_tab:
            if custom_renderer is not None:
                st.caption("This tool renders its own form, so argument references aren't available here.")
            elif not prior:
                st.caption("No earlier steps to reference yet.")
            else:
                st.caption("Bind an argument to an earlier step's output instead of a literal value.")
                for name in data_params:
                    current = d["sources"].get(name, "(value)")
                    options = ["(value)", *prior]
                    chosen = st.selectbox(
                        name, options, index=options.index(current) if current in options else 0,
                        key=f"src_{sid}_{name}",
                    )
                    if chosen == "(value)":
                        d["sources"].pop(name, None)
                    else:
                        d["sources"][name] = chosen
                        arguments[name] = chosen

            st.divider()
            st.caption("Orchestration — run this tool once, or fan it out over a collection.")
            modes = ["single", "map", "filter", "expand", "collapse"]
            orch = d["orchestration"]
            orch["mode"] = st.selectbox("mode", modes, index=modes.index(orch["mode"]), key=f"orch_mode_{sid}")
            if orch["mode"] != "single":
                over_options = ["(none)", *prior]
                current_over = orch["over"] if orch["over"] in over_options else "(none)"
                over = st.selectbox("over — the collection to fan out across", over_options,
                                      index=over_options.index(current_over), key=f"orch_over_{sid}")
                orch["over"] = None if over == "(none)" else over

                item_options = ["(auto)", *data_params]
                current_item = orch["item_arg"] if orch["item_arg"] in item_options else "(auto)"
                item_arg = st.selectbox("item argument — which param each item binds to", item_options,
                                          index=item_options.index(current_item), key=f"orch_item_{sid}")
                orch["item_arg"] = None if item_arg == "(auto)" else item_arg

                orch["concurrency"] = st.number_input("concurrency", min_value=1, step=1,
                                                        value=int(orch["concurrency"]), key=f"orch_conc_{sid}")
                error_options = ["(default)", "collect", "fail_fast", "skip"]
                current_err = orch["on_error"] or "(default)"
                on_error = st.selectbox("on_error", error_options, index=error_options.index(current_err),
                                          key=f"orch_err_{sid}")
                orch["on_error"] = None if on_error == "(default)" else on_error
                orch["retries"] = st.number_input("retries", min_value=0, step=1,
                                                    value=int(orch["retries"]), key=f"orch_retries_{sid}")
                if orch["mode"] == "collapse":
                    orch["initial"] = st.text_input(
                        "initial — seed value for the accumulator",
                        value="" if orch["initial"] is None else str(orch["initial"]),
                        key=f"orch_initial_{sid}",
                    )

        with exec_tab:
            st.caption("How this step is invoked.")
            execu = d["execution"]
            exec_modes = ["sync", "async"]
            execu["mode"] = st.selectbox("mode", exec_modes, index=exec_modes.index(execu["mode"]), key=f"exec_mode_{sid}")
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
                                                 value=int(execu["retries"]), key=f"exec_retries_{sid}")
            execu["cache"] = st.checkbox("cache result", value=execu["cache"], key=f"exec_cache_{sid}")

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
        specs[sid] = StepSpec(
            step_id=sid, name=d["op"], stage=d["stage"], arguments=arguments,
            orchestration=OrchestrationConfig(
                mode=orch["mode"], over=orch["over"], item_arg=orch["item_arg"],
                concurrency=int(orch["concurrency"]), on_error=orch["on_error"],
                retries=int(orch["retries"]), initial=orch["initial"],
            ),
            execution=ExecutionConfig(
                mode=execu["mode"], run=execu["run"], timeout=execu["timeout"],
                retries=int(execu["retries"]), cache=execu["cache"],
            ),
        )

    with st.expander("Step Manager", expanded=True):
        selected = set(_selected())
        if not selected:
            st.info("Select one or more steps above to view them here.")
        with st.container(horizontal=True, wrap=False, gap="small", key=_CARDS_KEY):
            rendered: set[str] = set()
            for d in draft:
                if d["id"] in rendered:
                    continue
                if d["stage"] is None:
                    (_render_card if d["id"] in selected else _author_hidden)(d)
                    rendered.add(d["id"])
                    continue
                stage = d["stage"]
                members = [m for m in draft if m["stage"] == stage]
                visible_members = [m for m in members if m["id"] in selected]
                for member in members:
                    if member["id"] not in selected:
                        _author_hidden(member)
                if visible_members:
                    with st.container(border=True):
                        st.caption(f"🗂 {stage}")
                        if st.button(":material/play_arrow: Run stage", key=f"run_stage_{stage}"):
                            run_requests.append(("stage", stage))
                        with st.container(horizontal=True, wrap=False, gap="small"):
                            for member in visible_members:
                                _render_card(member)
                rendered.update(m["id"] for m in members)

    # ── Author the draft into the workflow (structure only, cheap) ───────
    for step_id in list(wf._steps):
        if step_id not in specs:
            del wf[step_id]
    for sid, spec in specs.items():
        if sid not in wf or wf[sid].spec != spec:
            wf[sid] = spec

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
# Console-script entry point
# ─────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> None:
    """``simple-steps-core-dashboard SCRIPT`` — launch the Streamlit dashboard."""
    parser = argparse.ArgumentParser(
        prog="simple-steps-core-dashboard",
        description="Launch a Streamlit dashboard for the tools declared in a Python script.",
    )
    parser.add_argument("script", help="Path to a Python script that declares tools.")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        from streamlit.web import cli as stcli  # noqa: F401
    except ImportError as exc:  # pragma: no cover - optional extra
        raise SystemExit(
            'The dashboard needs Streamlit. Install it with:\n'
            '    pip install "simple-steps-core[dashboard]"'
        ) from exc

    import subprocess

    env = {**os.environ, _ENV_TOOLS: os.path.abspath(args.script)}
    cmd = ["streamlit", "run", os.path.abspath(__file__)]
    if args.port:
        cmd += ["--server.port", str(args.port)]
    raise SystemExit(subprocess.call(cmd, env=env))


if __name__ == "__main__":
    _render_app()
