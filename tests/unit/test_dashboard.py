"""Tests for the Streamlit dashboard's generic form renderer.

These exercise ``render_tool_form`` with a fake ``st`` so no Streamlit install
or browser is needed.
"""

from simple_steps_core import ToolRegistry, StepOutput
from simple_steps_core.streamlit.dashboard import render_tool_form, render_tool_result


class FakeSt:
    """Minimal stand-in that returns each widget's seed value."""

    def slider(self, label, mn, mx, value=None, key=None):
        return value

    def selectbox(self, label, options, index=0, key=None):
        return options[index]

    def checkbox(self, label, value=False, key=None):
        return value

    def number_input(self, label, value=0, key=None, **kwargs):
        return value

    def text_input(self, label, value="", key=None):
        return value

    def write(self, value):
        self.written = value


def _registry():
    registry = ToolRegistry()

    def scale(x: int, factor: int = 2) -> int:
        return x * factor

    def custom(n: int) -> int:
        return n

    registry.register("scale", scale)
    registry.register("custom", custom, ui={"streamlit": lambda st, *, key, defaults: {"n": 42}})
    return registry


def test_auto_form_reads_the_contract():
    registry = _registry()
    args = render_tool_form(FakeSt(), registry.get_operation("scale"), key="k", available_steps=[])
    assert args == {"x": 0, "factor": 2}   # x has no default -> 0; factor default 2


def test_custom_streamlit_ui_is_used_when_provided():
    registry = _registry()
    args = render_tool_form(FakeSt(), registry.get_operation("custom"), key="k")
    assert args == {"n": 42}               # the tool's own render function wins


def test_ui_map_keeps_both_prefab_and_streamlit_targets():
    registry = ToolRegistry()

    def pick(region: str) -> str:
        return region

    prefab = {"view": {"type": "Card", "children": []}, "state": {"region": "EMEA"}}
    render = lambda st, *, key, defaults: {"region": "APAC"}   # noqa: E731
    registry.register("pick", pick, ui={"prefab": prefab, "streamlit": render})

    # the supplied prefab view is kept verbatim (not auto-built)...
    assert registry.ui_for("pick", "prefab") == prefab
    assert registry.get_definition("pick").ui == prefab
    # ...and the Streamlit view is what the dashboard renders.
    op = registry.get_operation("pick")
    assert render_tool_form(FakeSt(), op, key="k") == {"region": "APAC"}


def test_reference_picker_wires_an_argument_to_a_step():
    registry = _registry()

    class PickStep(FakeSt):
        def selectbox(self, label, options, index=0, key=None):
            # source pickers are ["(value)", *steps] — choose the step.
            return options[1] if options and options[0] == "(value)" else options[index]

    args = render_tool_form(PickStep(), registry.get_operation("scale"),
                            key="k", available_steps=["step_1"])
    assert args["x"] == "step_1"           # argument is now a reference


def test_custom_streamlit_result_ui_is_used_when_provided():
    registry = ToolRegistry()
    rendered = {}

    def render_result(st, *, key, result):
        rendered.update(key=key, value=result.value)

    operation = registry.register(
        "plot",
        lambda x: x,
        ui={
            "streamlit": {
                "input": lambda st, *, key, defaults: {"x": 1},
                "result": render_result,
            }
        },
    )
    render_tool_result(FakeSt(), operation, StepOutput(value={"points": []}), key="result")
    assert rendered == {"key": "result", "value": {"points": []}}


def test_streamlit_result_falls_back_to_write():
    registry = _registry()
    st = FakeSt()
    render_tool_result(st, registry.get_operation("scale"), StepOutput(value=6), key="result")
    assert st.written == 6
