"""
Streamlit dashboard
===================

The ready-made Step Manager app — and, since the component extraction, only a
**wiring layer**. Everything it draws comes from two packages below it:

    components/   one renderer per core object (Workflow, Step, Tool, configs…)
    panels/       composite dashboard modules built from those components
        draft.py      DraftStep / DraftWorkflow — the editing model (pure Python)
        step_card.py  one step's card: controls, Operation panel, Result panel
        toolbar.py    step selector, run controls, tool palette, import/export

What stays here is exactly what a panel must not own: ``st.session_state``, the
live ``Workflow``, and the decision of when to run. Panels receive their state
explicitly and hand every action back through an ``on_…`` callback, which is why
they are testable with a fake ``st`` (see tests/unit/test_panels.py).

Users write one tools file that registers tools (plus optional ``CONFIG`` /
``RESOURCES``), import ``Dashboard``, and call it at the bottom::

    from simple_steps_core import register_tool
    from simple_steps_core.streamlit import Dashboard

    @register_tool("add")
    def add(a: int, b: int) -> int:
        return a + b

    if __name__ == "__main__":
        Dashboard().run()

then run it with ``python mytools.py`` (needs ``pip install
"simple-steps-core[dashboard]"``).

To build a different surface, import the components and panels directly rather
than reusing this module.

Streamlit is imported lazily so importing this module never requires it.
"""

from __future__ import annotations

import os
import sys
from typing import Any

# Absolute imports: `streamlit run` executes this file as a top-level script
# (no parent package), so relative imports would fail.
from simple_steps_core.domain.models import (
    Operation,
    OrchestrationConfig,
)
from simple_steps_core.execution.engine import CoreEngine
from simple_steps_core.execution.workflow import Workflow
from simple_steps_core.loader import load_tools_module
from simple_steps_core.operations.orchestrations import register_orchestrators
from simple_steps_core.operations.registry import REGISTRY
from simple_steps_core.streamlit.components import render_resources
from simple_steps_core.streamlit.panels import (
    STEP_VIEWS,
    DraftWorkflow,
    render_problems,
    render_run_controls,
    render_step_card,
    render_tool_palette,
    render_workflow_io,
    render_workflow_toolbar,
)

_ENV_TOOLS = "SIMPLE_STEPS_TOOLS"


def _fragment(fn):
    """``st.fragment`` applied lazily, so importing this module needs no Streamlit.

    Falls back to calling the function directly on Streamlit versions without
    fragments — the dashboard then simply reruns the whole page as before.
    """
    def wrapper(st, *args, **kwargs):
        decorated = getattr(st, "fragment", None)
        if decorated is None:
            return fn(st, *args, **kwargs)
        cached = getattr(fn, "_fragment_impl", None)
        if cached is None:
            cached = decorated(lambda *a, **k: fn(st, *a, **k))
            fn._fragment_impl = cached
        return cached(*args, **kwargs)

    return wrapper

# The Step Manager row scrolls horizontally instead of wrapping/shrinking its
# cards — keyed so the CSS below can target it (see `_render_app`).
_CARDS_KEY = "step_cards_row"
_CARD_WIDTH = 260

# The Step Manager row scrolls horizontally instead of wrapping its cards.
_CARD_CSS = f"""
<style>
[data-testid="stExpander"] details summary {{
    padding-top: 0.20rem !important;
    padding-bottom: 0.20rem !important;
    min-height: unset !important;
}}
[data-testid="stExpander"] details summary p {{ font-size: 14px !important; }}
div.st-key-{_CARDS_KEY} {{
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 0.5rem;
}}
div.st-key-{_CARDS_KEY} > div {{
    flex-wrap: nowrap !important;
    min-width: max-content;
}}
div.st-key-{_CARDS_KEY} > div > div {{ flex-shrink: 0 !important; }}
div[class*="st-key-card_"] {{ min-width: {_CARD_WIDTH}px; }}
</style>
"""

# JSON-Schema scalar types -> the Python names a user recognises.
_SCALAR_TYPES = {
    "integer": "int", "number": "float", "string": "str",
    "boolean": "bool", "null": "None",
}




def _render_app(config: dict[str, Any], resources: dict[str, Any]) -> None:
    """Wire the panels together. This function owns session state; panels do not."""
    import streamlit as st

    definitions = REGISTRY.list_definitions()
    tool_ids = [d.operation_id for d in definitions]

    st.set_page_config(page_title=config.get("title", "simple-steps"), layout="wide")
    st.markdown(_CARD_CSS, unsafe_allow_html=True)

    def _register_resources(target: Workflow) -> None:
        for name, provider in resources.items():
            if callable(provider):
                target.context.resources.register(name, provider)
            else:
                target.context.resources.register_value(name, provider)

    st.session_state.setdefault("selected_steps", [])
    st.session_state.setdefault("selected_steps_nonce", 0)

    def _touch_selection_widget() -> None:
        # The step selector is keyed by this nonce so it remounts and re-reads
        # `default=` whenever selection changes from code rather than a click.
        st.session_state.selected_steps_nonce += 1

    def _rerun() -> None:
        _touch_selection_widget()
        st.rerun()

    # One Workflow and one DraftWorkflow for the whole session.
    if "wf" not in st.session_state:
        workflow = Workflow(CoreEngine(REGISTRY), session_id="dashboard")
        _register_resources(workflow)
        st.session_state.wf = workflow
    wf: Workflow = st.session_state.wf

    if "drafts" not in st.session_state:
        st.session_state.drafts = DraftWorkflow()
    drafts: DraftWorkflow = st.session_state.drafts

    def _selected() -> list[str]:
        return list(st.session_state.get("selected_steps") or [])

    # ── structural edits: plain calls on the draft model ──────────────────
    def _add_step() -> None:
        draft = drafts.add()
        st.session_state.selected_steps = [*_selected(), draft.id]
        _touch_selection_widget()

    def _remove_steps(step_ids: list[str]) -> None:
        for step_id in step_ids:
            if step_id in wf:
                del wf[step_id]
        drafts.remove(step_ids)
        st.session_state.selected_steps = []
        _touch_selection_widget()

    def _swap_steps(step_ids: list[str]) -> None:
        if len(step_ids) == 2:
            drafts.swap(*step_ids)

    def _group_steps(step_ids: list[str]) -> None:
        drafts.group(step_ids)
        st.session_state.selected_steps = []
        _touch_selection_widget()

    def _ungroup_steps(step_ids: list[str]) -> None:
        drafts.ungroup(step_ids)
        st.session_state.selected_steps = []
        _touch_selection_widget()

    def _clear_all() -> None:
        drafts.clear()
        st.session_state.selected_steps = []
        st.session_state.pop("wf", None)
        _touch_selection_widget()

    def _load_workflow(data: str) -> None:
        imported = Workflow.import_session_json(data, CoreEngine(REGISTRY))
        _register_resources(imported)
        st.session_state.wf = imported
        st.session_state.drafts = DraftWorkflow.from_workflow(imported)
        st.session_state.selected_steps = st.session_state.drafts.ids()
        _rerun()

    #: Tools the built-in sample chain needs, in the order it wires them.
    _SAMPLE_CHAIN = ("load_batches", "unpack_batch", "above_cutoff", "accumulate_stats")

    def _sample_workflow_json() -> str:
        """The example pipeline, already run: load -> expand -> filter -> collapse."""
        sample = Workflow(CoreEngine(REGISTRY), session_id="sample")
        _register_resources(sample)
        sample["step1"] = Operation(step_id="step1", name="load_batches",
                                    arguments={"batches": 3, "per_batch": 4})
        sample["step2"] = Operation(
            step_id="step2", name="unpack_batch",
            orchestration=OrchestrationConfig(mode="expand", over="step1"))
        sample["step3"] = Operation(
            step_id="step3", name="above_cutoff", arguments={"cutoff": 25.0},
            orchestration=OrchestrationConfig(mode="filter", over="step2"))
        sample["step4"] = Operation(
            step_id="step4", name="accumulate_stats",
            orchestration=OrchestrationConfig(mode="collapse", over="step3"))
        sample.run()
        return sample.export_session_json()

    # ── sidebar ──────────────────────────────────────────────────────────
    with st.sidebar:
        with st.expander("Manage Workflow"):
            render_workflow_io(
                st, wf, key="io", on_load=_load_workflow,
                sample_json=_sample_workflow_json,
                sample_available=set(_SAMPLE_CHAIN) <= set(tool_ids),
            )
        st.divider()
        with st.expander("Tools"):
            render_tool_palette(st, REGISTRY, key="palette")
        with st.expander("Resources"):
            render_resources(st, wf.context.resources, key="res")

    # ── toolbar ──────────────────────────────────────────────────────────
    # A fragment's callback runs in its own script run, so a local list would be
    # thrown away before the executing pass ever sees it. The queue lives in
    # session state and is drained once, at the end of a full run.
    st.session_state.setdefault("pending_runs", [])

    with st.expander("Workflow Manager", expanded=True):
        select_col, manage_col = st.columns([5, 1])
        with select_col:
            selected_now = render_workflow_toolbar(
                st, drafts, key="toolbar", selected=_selected(),
                nonce=st.session_state.selected_steps_nonce,
                on_add=_add_step, on_remove=_remove_steps, on_swap=_swap_steps,
            )
            st.session_state.selected_steps = selected_now
        with manage_col:
            with st.container(horizontal=True, vertical_alignment="top"):
                with st.popover("Group into stages"):
                    st.button(":material/merge_type: Group selected",
                              disabled=len(selected_now) < 2,
                              on_click=_group_steps, args=(selected_now,))
                    st.button(":material/call_split: Ungroup selected",
                              disabled=not selected_now,
                              on_click=_ungroup_steps, args=(selected_now,))
                with st.popover(":material/smart_toy: Assistant"):
                    st.caption("Assistant placeholder")

        st.divider()
        run_all = render_run_controls(st, drafts, key="run", on_clear=_clear_all)

    if not len(drafts):
        st.info("Add a step to begin.")
        return

    selected = set(selected_now)
    if not selected:
        st.info("Select one or more steps above to view them here.")

    # ── step cards, grouped by stage ─────────────────────────────────────
    with st.container(horizontal=True, wrap=False, gap="xxsmall", key=_CARDS_KEY):
        for stage, members in _by_stage(drafts):
            visible = [m for m in members if m.id in selected]
            if not visible:
                continue
            for draft in visible:
                _step_fragment(
                    st, draft,
                    tool_ids=tool_ids,
                    prior=drafts.prior_to(draft.id),
                    workflow=wf,
                )

    # ── author the draft into the workflow ───────────────────────────────
    render_problems(st, drafts.author_into(wf))

    # ── execute only what was explicitly requested this rerun ────────────
    pending: list[str] = st.session_state.pending_runs
    st.session_state.pending_runs = []

    ran = False
    if run_all:
        try:
            wf.run_by_stages()
        except Exception:
            pass          # the failure is recorded on the step's record
        ran = True
    for step_id in pending:
        if step_id not in wf:
            continue      # the step was removed, or is not runnable yet
        try:
            wf.run_step(step_id)
        except Exception:
            pass
        ran = True
    if ran:
        _rerun()


def _step_fragment(st, draft, *, tool_ids, prior, workflow) -> None:
    """One step's card, isolated as a fragment.

    Editing a card — picking a tool, typing an argument, changing orchestration —
    reruns only this fragment instead of the whole page. Running still needs the
    full script (the workflow is shared state and later steps may consume this
    one's output), so the run request is recorded here and ``st.rerun(scope="app")``
    escalates it.
    """
    views = st.session_state.setdefault(
        f"step_view_controller_{draft.id}", list(STEP_VIEWS)
    )
    with st.expander(f"{draft.id}", expanded=True):
        _view_picker(st, draft.id)
        render_step_card(
            st, draft, key=f"card_{draft.id}", registry=REGISTRY,
            tool_ids=tool_ids, prior=prior,
            step=workflow[draft.id] if draft.id in workflow else None,
            views=views,
            on_run=lambda d: _request_run(st, d),
            on_reset=_reset_step,
        )


def _request_run(st, draft) -> None:
    """Queue a run and escalate out of the fragment to the full script.

    Running cannot happen inside the fragment: the workflow is shared state and
    later steps consume this one's output, so the whole page has to re-render.
    """
    queued = list(st.session_state.get("pending_runs", []))
    if draft.id not in queued:
        queued.append(draft.id)
    st.session_state.pending_runs = queued
    st.rerun(scope="app")


def _reset_step(draft) -> None:
    """Clear one step's output (the workflow is reached via session state)."""
    import streamlit as st

    workflow = st.session_state.get("wf")
    if workflow is not None and draft.id in workflow:
        del workflow[draft.id]


def _view_picker(st, step_id: str) -> None:
    """Per-card view toggles. Owns the session-state key so the panel need not."""
    with st.container(horizontal=True, gap="xxsmall", width="content",
                      horizontal_alignment="right"):
        with st.popover(":material/visibility:", type="secondary"):
            st.segmented_control(
                label=step_id, selection_mode="multi",
                options=[*STEP_VIEWS, ":material/analytics:", ":material/smart_toy:",
                         ":material/settings:"],
                key=f"step_view_controller_{step_id}",
                help="Select Step components to see for this step",
                label_visibility="collapsed",
            )


def _by_stage(drafts: DraftWorkflow):
    """Draft rows grouped by stage, preserving first-seen order."""
    groups: dict[Any, list] = {}
    for draft in drafts:
        groups.setdefault(draft.stage, []).append(draft)
    return list(groups.items())


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
