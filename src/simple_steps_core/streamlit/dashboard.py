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


def render_tool_result(st, operation: Operation, result: Any, *, key: str) -> None:
    """Render a completed output with the custom result view or a generic fallback."""
    renderer = operation.ui.result("streamlit")
    if renderer is not None:
        renderer(st, key=key, result=result)
        return
    st.write(result.value)


# ─────────────────────────────────────────────────────────────────────────
# The Streamlit app (imports streamlit lazily; runs under `streamlit run`)
# ─────────────────────────────────────────────────────────────────────────
def _render_app() -> None:
    import streamlit as st

    from simple_steps_core.domain.models import StepSpec, StepStatus
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
    st.title(config.get("title", "simple-steps dashboard"))

    # One Workflow for the whole session — the same object you'd build in Python:
    #   wf["step1"] = make_list(n=5); wf["step2"] = scale(x="step1"); wf.run()
    if "wf" not in st.session_state:
        wf = Workflow(CoreEngine(REGISTRY), session_id="dashboard")
        for name, provider in resources.items():
            if callable(provider):
                wf.context.resources.register(name, provider)
            else:
                wf.context.resources.register_value(name, provider)
        st.session_state.wf = wf
    wf: Workflow = st.session_state.wf

    st.session_state.setdefault("steps", [])          # [{"id": "step1", "op": "make_list"}]
    steps = st.session_state.steps

    # ── Sidebar: the tools available in the registry ─────────────────────
    with st.sidebar:
        with st.expander("Tools"):
            for d in definitions:
                with st.expander(d.operation_id):
                    st.caption(d.description or "—")
                    st.write({p.name: p.type_name for p in d.params if p.kind == "data"})
        with st.expander("Resources"):
            if resources:
                st.caption("Resources: " + ", ".join(resources))

    # ── Top bar: add a step, run the whole workflow, or clear it ──────────
    add, run, clear = st.columns(3)
    
    if add.button("➕ Add step", use_container_width=True):
        steps.append({"id": f"step{len(steps) + 1}", "op": None})
        st.rerun()
    run_all = run.button("▶ Run all", use_container_width=True, disabled=not steps)
    if clear.button("🗑 Clear", use_container_width=True):
        st.session_state.steps = []
        st.session_state.pop("wf", None)
        st.rerun()

    if not steps:
        st.info("Add a step to begin.")
        return

    # ── Kanban board: each step is a card, placed in a lane by its status ─
    # A card mirrors a line of the Python script; a step may reference the
    # output of any earlier step by its id. Outputs live on the workflow's
    # Step records, which are themselves held in st.session_state["wf"].
    specs: dict[str, StepSpec] = {}
    run_one: str | None = None

    def _card(step: dict, i: int) -> None:
        nonlocal run_one
        sid = step["id"]
        prior = [s["id"] for s in steps[:i] if s["op"]]
        top = st.columns([4, 1])
        top[0].markdown(f"**{sid}**")
        if top[1].button("🗑", key=f"rm_{sid}", help="Remove step"):
            steps.pop(i)
            st.rerun()
        step["op"] = st.selectbox(
            "operation", tool_ids,
            index=tool_ids.index(step["op"]) if step["op"] in tool_ids else None,
            placeholder="choose an operation…",
            key=f"op_{sid}", label_visibility="collapsed",
        )
        if not step["op"]:
            return
        op = REGISTRY.get_operation(step["op"])
        arguments = render_tool_form(st, op, key=f"form_{sid}", available_steps=prior)
        specs[sid] = StepSpec(step_id=sid, name=step["op"], arguments=arguments)
        if st.button("▶ Run", key=f"run_{sid}", use_container_width=True):
            run_one = sid
        if sid in wf:
            rec = wf[sid]
            if rec.status is StepStatus.COMPLETED:
                st.success("output")
                render_tool_result(st, op, rec.output, key=f"result_{sid}")
            elif rec.status is StepStatus.FAILED:
                st.error(rec.error or "failed")

    lanes = {"todo": "🟡 To run", "done": "🟢 Done", "failed": "🔴 Failed"}
    board: dict[str, list[tuple[int, dict]]] = {key: [] for key in lanes}
    for i, step in enumerate(steps):
        rec = wf[step["id"]] if step["id"] in wf else None
        if rec and rec.status is StepStatus.COMPLETED:
            board["done"].append((i, step))
        elif rec and rec.status is StepStatus.FAILED:
            board["failed"].append((i, step))
        else:
            board["todo"].append((i, step))

    for col, (key, title) in zip(st.columns(len(lanes)), lanes.items()):
        with col:
            st.markdown(f"### {title}")
            for i, step in board[key]:
                with st.container(border=True):
                    _card(step, i)

    # ── Author the steps into the workflow, then run — via its own methods ─
    def _author() -> None:
        for rec in list(wf.steps):
            if rec.step_id not in specs:
                del wf[rec.step_id]
        for sid, spec in specs.items():
            if sid not in wf or wf[sid].spec != spec:
                wf[sid] = spec

    if run_one or run_all:
        _author()
        try:
            wf.run() if run_all else wf.run_step(run_one)
        except Exception:
            pass          # the failure is recorded on the step's record
        st.rerun()


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
