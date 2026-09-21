"""Streamlit components are pure adapters: no Streamlit, no session state, no mutation.

Every test here runs the real components against a fake ``st``, which is the
point of the design — if a component needed a live Streamlit runtime or reached
into ``st.session_state``, none of this would work.
"""

from contextlib import contextmanager

import pytest

from simple_steps_core import (
    ArgGuardrail,
    CoreEngine,
    Guardrails,
    Operation,
    OrchestrationConfig,
    Resource,
    StepExecutionConfig,
    ToolRegistry,
    Workflow,
    register_orchestrators,
)
from simple_steps_core.streamlit import components as C


class FakeSt:
    """Records every call; returns each widget's seeded value."""

    def __init__(self, clicks: set[str] | None = None):
        self.calls: list[tuple[str, object]] = []
        self.clicks = clicks or set()

    def _log(self, kind, payload=None):
        self.calls.append((kind, payload))

    # Real tab/column objects are context managers; the fake must be too.
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    # text
    def markdown(self, body, **kw): self._log("markdown", body)
    def caption(self, body, **kw): self._log("caption", body)
    def text(self, body, **kw): self._log("text", body)
    def write(self, *a, **kw): self._log("write", a[0] if a else None)
    def code(self, body, **kw): self._log("code", body)
    def json(self, body, **kw): self._log("json", body)
    def error(self, body, **kw): self._log("error", body)
    def warning(self, body, **kw): self._log("warning", body)
    def success(self, body, **kw): self._log("success", body)
    def info(self, body, **kw): self._log("info", body)
    def dataframe(self, df, **kw):
        # Shaded frames arrive as pandas Stylers; record the frame and the fill.
        if hasattr(df, "data"):
            self._log("style", df)
            self._log("dataframe", df.data)
        else:
            self._log("dataframe", df)
    def metric(self, label, value, **kw): self._log("metric", (label, value))
    def divider(self, **kw): self._log("divider")

    # widgets
    def button(self, label, key=None, **kw):
        self._log("button", label)
        return key in self.clicks

    def selectbox(self, label, options, index=None, key=None, **kw):
        options = list(options)
        self._log("selectbox", (label, options))
        return options[index] if index is not None and index < len(options) else (
            options[0] if options else None)

    def number_input(self, label, value=None, key=None, **kw):
        self._log("number_input", (label, value))
        return value

    def text_input(self, label, value="", key=None, **kw):
        self._log("text_input", (label, value))
        return value

    def text_area(self, label, value="", key=None, **kw):
        self._log("text_area", (label, value))
        return value

    def checkbox(self, label, value=False, key=None, **kw):
        self._log("checkbox", (label, value))
        return value

    def columns(self, n, **kw):
        return [FakeSt(self.clicks) for _ in range(n if isinstance(n, int) else len(n))]

    @contextmanager
    def expander(self, label, **kw):
        self._log("expander", label)
        yield self

    @contextmanager
    def container(self, **kw):
        self._log("container")
        yield self

    @contextmanager
    def popover(self, label="", **kw):
        self._log("popover", label)
        yield self

    def tabs(self, labels, **kw):
        self._log("tabs", list(labels))
        return [self for _ in labels]

    def segmented_control(self, label, options, default=None, key=None, **kw):
        self._log("segmented_control", (label, list(options)))
        return list(default or [])

    def download_button(self, label, **kw):
        self._log("download_button", label)
        return False

    def file_uploader(self, label, **kw):
        self._log("file_uploader", label)
        return None

    def space(self, *a, **kw):
        self._log("space")

    # queries
    def kinds(self):
        return [k for k, _ in self.calls]

    def payloads(self, kind):
        return [p for k, p in self.calls if k == kind]

    def text_blob(self):
        return " ".join(str(p) for k, p in self.calls
                        if p is not None and k != "style")

    def fills(self):
        """Background colours applied to any shaded frame."""
        out = []
        for styler in self.payloads("style"):
            try:
                rendered = styler.to_html()
            except Exception:                      # pragma: no cover
                continue
            for name, colour in (("staged", "255, 193, 7"), ("ok", "76, 175, 80"),
                                 ("failed", "244, 67, 54")):
                if colour in rendered:
                    out.append(name)
        return sorted(set(out))


def _registry():
    """Annotated functions — an unannotated return yields output_schema=None,
    which is exactly why the staged-output component would say 'Any'."""
    registry = ToolRegistry()
    register_orchestrators(registry)

    def mk(n: int) -> list[int]:
        return list(range(n))

    def scale(x: int) -> int:
        return x * 2

    def charge(amount: int) -> str:
        return f"charged {amount}"

    def greet(names=Resource()) -> str:
        return "hi"

    registry.register("mk", mk, "Make a list.")
    registry.register("scale", scale, "Double it.")
    registry.register(
        "charge", charge, "Charge.",
        guardrails=Guardrails(destructive=True,
                              arguments={"amount": ArgGuardrail(minimum=1, maximum=10)}),
    )
    registry.register("greet", greet, "Greet.")
    return registry


def _ran_workflow():
    registry = _registry()
    wf = Workflow(CoreEngine(registry), session_id="t")
    wf["step1"] = Operation(step_id="step1", name="mk", arguments={"n": 3}, stage="load")
    wf["step2"] = Operation(
        step_id="step2", name="scale", stage="work",
        orchestration=OrchestrationConfig(mode="map", over="step1"),
        execution=StepExecutionConfig(concurrency=2, retries=1),
    )
    wf.run()
    return registry, wf


# ── the package contract ─────────────────────────────────────────────────
def test_importing_components_does_not_require_streamlit():
    """`st` is a parameter, never a module import — that is what makes these testable."""
    import sys
    for name, module in sys.modules.items():
        if name.startswith("simple_steps_core.streamlit.components"):
            assert not hasattr(module, "st"), f"{name} imported streamlit at module level"


def test_every_registered_component_is_callable():
    for cls, component in C.COMPONENTS.items():
        assert callable(component), cls


def test_render_dispatches_by_type():
    _, wf = _ran_workflow()
    st = FakeSt()
    C.render(st, wf, key="wf")
    assert "dataframe" in st.kinds()


def test_render_raises_for_unregistered_type():
    with pytest.raises(TypeError, match="no Streamlit component"):
        C.render(FakeSt(), object(), key="x")


# ── components render real objects ───────────────────────────────────────
def test_workflow_component_uses_library_info():
    _, wf = _ran_workflow()
    st = FakeSt()
    C.render_workflow(st, wf, key="wf")
    frame = st.payloads("dataframe")[0]
    assert list(frame.columns) == wf.info().columns


def test_workflow_validation_component():
    _, wf = _ran_workflow()
    st = FakeSt()
    C.render_workflow_validation(st, wf, key="wf")
    assert st.payloads("dataframe")


def test_step_component_shows_status_and_output():
    _, wf = _ran_workflow()
    st = FakeSt()
    C.render_step(st, wf["step1"], key="s1")
    assert "step1" in st.text_blob()
    assert "completed" in st.text_blob()


def test_step_component_actions_are_caller_supplied():
    """The component never runs anything itself — it calls back."""
    _, wf = _ran_workflow()
    ran = []
    st = FakeSt(clicks={"s1_run"})
    C.render_step(st, wf["step1"], key="s1", on_run=ran.append)
    assert [s.step_id for s in ran] == ["step1"]


def test_step_component_without_callbacks_draws_no_buttons():
    _, wf = _ran_workflow()
    st = FakeSt()
    C.render_step(st, wf["step1"], key="s1")
    assert "button" not in st.kinds()


def test_map_result_component_lists_items():
    _, wf = _ran_workflow()
    st = FakeSt()
    C.render_output(st, wf["step2"].output, key="o")
    frame = st.payloads("dataframe")[0]
    assert list(frame["value"]) == [0, 2, 4]
    assert st.fills() == ["ok"]            # every item ran


def test_completed_output_shows_only_the_value():
    """No status line, no duration, no 'done' banner — just the data."""
    _, wf = _ran_workflow()
    st = FakeSt()
    C.render_output(st, wf["step1"].output, key="o")
    assert st.kinds() == ["style", "dataframe"]


def test_scalar_output_is_shaded_too():
    from simple_steps_core import StepOutput

    st = FakeSt()
    C.render_output(st, StepOutput(value=6), key="o")
    assert list(st.payloads("dataframe")[0]["value"]) == [6]
    assert st.fills() == ["ok"]


def test_output_status_component_is_all_strings():
    """A mixed-type column has no Arrow type to convert to."""
    _, wf = _ran_workflow()
    st = FakeSt()
    C.render_output_status(st, wf["step1"].output, key="o")
    frame = st.payloads("dataframe")[0]
    assert all(isinstance(v, str) for v in frame["value"])


def test_guardrails_component_warns_on_destructive():
    registry = _registry()
    st = FakeSt()
    C.render_guardrails(st, registry.get_definition("charge").guardrails, key="g")
    assert any("destructive" in str(w) for w in st.payloads("warning"))


def test_resource_params_component_names_injected_deps():
    registry = _registry()
    st = FakeSt()
    C.render_resource_params(st, registry.get_definition("greet").params)
    assert "names" in st.text_blob()


def test_tool_registry_component_lists_every_tool():
    registry = _registry()
    st = FakeSt()
    C.render_tool_registry(st, registry, key="reg")
    blob = st.text_blob()
    assert "mk" in blob and "scale" in blob and "charge" in blob


# ── editors return new frozen instances ──────────────────────────────────
def test_edit_orchestration_returns_shape_only():
    config = OrchestrationConfig(mode="map", over="step1")
    st = FakeSt()
    result = C.edit_orchestration(st, config, key="o", prior_steps=["step1"],
                                  param_names=["x"])
    assert isinstance(result, OrchestrationConfig)
    assert set(result.model_dump()) == {"mode", "over", "item_arg", "initial"}


def test_edit_step_execution_hides_item_fields_when_single():
    config = StepExecutionConfig()
    single = FakeSt()
    C.edit_step_execution(single, config, key="e", fanned_out=False)
    assert "concurrency" not in single.text_blob()

    fanned = FakeSt()
    C.edit_step_execution(fanned, config, key="e", fanned_out=True)
    assert "concurrency" in fanned.text_blob()


def test_editors_do_not_mutate_the_original():
    config = StepExecutionConfig(retries=3)
    st = FakeSt()
    result = C.edit_step_execution(st, config, key="e")
    assert config.retries == 3            # untouched
    assert isinstance(result, StepExecutionConfig)


# ── staged output ────────────────────────────────────────────────────────
def test_staged_output_shows_type_and_shape_shaded_amber():
    registry = _registry()
    spec = Operation(step_id="step1", name="mk", arguments={"n": 3})
    st = FakeSt()
    C.render_staged_output(st, spec, registry.get_definition("mk"), key="s")
    row = st.payloads("dataframe")[0].iloc[0]
    assert row["type"] == "list[int]"
    assert row["shape"] == "1 cell"
    assert st.fills() == ["staged"]


def test_staged_output_wraps_fanned_out_type_and_names_its_shape():
    registry = _registry()
    spec = Operation(step_id="step2", name="scale",
                     orchestration=OrchestrationConfig(mode="map", over="step1"))
    st = FakeSt()
    C.render_staged_output(st, spec, registry.get_definition("scale"), key="s")
    row = st.payloads("dataframe")[0].iloc[0]
    assert row["type"] == "MapResult[int]"
    assert "one cell per item of step1" == row["shape"]


# ── references shown as shell variables ──────────────────────────────────
def test_format_reference_wraps_step_tokens():
    assert C.format_reference("step1") == "${step1}"
    assert C.format_reference("step10") == "${step10}"


def test_format_reference_keeps_the_accessor_inside_the_braces():
    """`.ok` is part of the reference, not something tacked on after it."""
    assert C.format_reference("step2.ok") == "${step2.ok}"


def test_format_reference_leaves_non_references_alone():
    """Safe as a selectbox format_func, which sees sentinels and literals too."""
    assert C.format_reference("(a value)") == "(a value)"
    assert C.format_reference(20.0) == "20.0"
    assert C.format_reference(None) == ""


def test_reference_options_preserve_workflow_order():
    """step10 sorting before step2 would misrepresent the workflow."""
    assert C.reference_options(["step1", "step2", "step10"]) == ["step1", "step2", "step10"]
    assert C.reference_options(["step1"], sentinel="(a value)") == ["(a value)", "step1"]
