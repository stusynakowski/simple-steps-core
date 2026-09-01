"""Tests for the default prefab-ui builder and UI overrides."""

from typing import Literal

from simple_steps_core import OperationRegistry, build_default_ui


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
    registry = OperationRegistry()

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

