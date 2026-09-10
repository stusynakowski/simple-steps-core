"""Tests for the default prefab-ui builder and UI overrides."""

from typing import Literal

import pytest

from simple_steps_core import ToolRegistry, ToolUIView, build_default_ui


def test_default_ui_is_prefab_protocol():
    schema = {
        "type": "object",
        "properties": {
            "region": {"type": "string", "title": "Region"},
            "limit": {"type": "integer", "default": 100},
        },
        "required": ["region"],
    }
    ui = build_default_ui("load", schema, description="Load rows.")
    assert set(ui) == {"view", "state"}
    assert ui["view"]["type"] == "Card"
    # defaults seed the state, keyed by field name
    assert ui["state"] == {"limit": 100}
    # header carries title + description
    header = ui["view"]["children"][0]["children"]
    assert header[0] == {"type": "CardTitle", "content": "Load"}
    assert {"type": "CardDescription", "content": "Load rows."} in header


def test_enum_becomes_combobox():
    schema = {
        "type": "object",
        "properties": {"mode": {"enum": ["a", "b"], "title": "Mode"}},
        "required": ["mode"],
    }
    fields = build_default_ui("op", schema)["view"]["children"][1]["children"][0]["children"]
    combobox = fields[0]["children"][1]
    assert combobox["type"] == "Combobox"
    assert [o["value"] for o in combobox["children"]] == ["a", "b"]


def test_boolean_becomes_switch():
    schema = {"type": "object", "properties": {"active": {"type": "boolean", "title": "Active"}}}
    field = build_default_ui("op", schema)["view"]["children"][1]["children"][0]["children"][0]
    assert field == {"type": "Switch", "name": "active", "label": "Active", "required": False}


def test_registration_auto_builds_ui_and_override_wins():
    registry = ToolRegistry()

    def choose(color: Literal["red", "green"]) -> str:
        return color

    registry.register("choose", choose)
    auto = registry.get_definition("choose").ui
    assert auto["view"]["type"] == "Card"

    custom = {"view": {"type": "Card", "children": []}, "state": {}}

    def choose2(color: str) -> str:
        return color

    registry.register("choose2", choose2, ui=custom)
    assert registry.get_definition("choose2").ui == custom


def test_guardrails_shape_the_default_ui():
    from simple_steps_core import ArgGuardrail, Guardrails

    schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "title": "Kind"},   # no schema enum
            "score": {"type": "integer", "title": "Score"},
        },
        "required": ["kind", "score"],
    }
    guardrails = Guardrails(arguments={
        "kind": ArgGuardrail(enum=["A", "B"]),              # -> dropdown
        "score": ArgGuardrail(minimum=0, maximum=100),      # -> numeric bounds
    })
    fields = build_default_ui("op", schema, guardrails=guardrails)["view"]["children"][1]["children"][0]["children"]
    kind_input = fields[0]["children"][1]
    assert kind_input["type"] == "Combobox"
    assert [o["value"] for o in kind_input["children"]] == ["A", "B"]
    score_input = fields[1]["children"][1]
    assert score_input["min"] == 0 and score_input["max"] == 100


def test_unified_ui_holds_multiple_targets():
    registry = ToolRegistry()

    def pick(region: str) -> str:
        return region

    render = lambda st, *, key, defaults: {"region": "EMEA"}   # noqa: E731
    registry.register("pick", pick, ui={"streamlit": render})

    op = registry.get_operation("pick")
    assert set(op.ui.targets()) == {"streamlit", "prefab"}
    # prefab is auto-built and mirrored onto the serialized definition.
    assert op.ui.prefab["view"]["type"] == "Card"
    assert registry.ui_for("pick", "prefab") == registry.get_definition("pick").ui
    # the streamlit view is retrievable; unknown targets return None.
    assert registry.ui_for("pick", "streamlit") is render
    assert registry.ui_for("pick", "vue") is None


def test_composed_ui_exposes_input_and_result_and_serializes_both():
    registry = ToolRegistry()
    input_ui = {"view": {"type": "Input"}, "state": {}}
    result_ui = {"view": {"type": "Plot"}, "state": {}}

    registry.register(
        "plot",
        lambda x: x,
        ui={"prefab": {"input": input_ui, "result": result_ui}},
    )

    operation = registry.get_operation("plot")
    assert operation.ui.input("prefab") == input_ui
    assert operation.ui.result("prefab") == result_ui
    assert operation.ui.full("prefab") is None
    assert operation.ui.get("prefab") == input_ui
    assert registry.get_definition("plot").ui == {
        "input": input_ui,
        "result": result_ui,
    }


def test_full_ui_is_exclusive_and_is_the_legacy_primary_view():
    full_ui = {"view": {"type": "PlotBuilder"}, "state": {}}
    registry = ToolRegistry()
    registry.register("plot", lambda x: x, ui={"prefab": {"full": full_ui}})

    operation = registry.get_operation("plot")
    assert operation.ui.full("prefab") == full_ui
    assert operation.ui.get("prefab") == full_ui
    assert registry.get_definition("plot").ui == {"full": full_ui}

    with pytest.raises(ValueError, match="either 'full'"):
        ToolUIView(input={}, full={})


def test_composed_ui_requires_an_input_view():
    with pytest.raises(ValueError, match="must define an 'input'"):
        ToolUIView(result={})


