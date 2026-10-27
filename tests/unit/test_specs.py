"""Specs on every object, and extras (docs/design/object-model.md §3,
docs/design/extensions.md)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, resource, tool, wf
from simple_steps_core.specs import KernelSpec, StepSpec, WorkflowSpec


@tool
def patients_s() -> pd.DataFrame:
    return pd.DataFrame({"temp_c": [36.6, 38.2]})


@tool(extras={"simple_steps.ui": {"temp_c": "slider"}})
def to_f_s(temp_c: float) -> float:
    return round(temp_c * 1.8 + 32, 2)


@resource
class Thermo:
    def __init__(self, unit: str = "C"):
        self.unit = unit


@pytest.fixture
def cat():
    return Catalog(tools=[patients_s, to_f_s], resources=[Thermo])


@pytest.fixture
def k(cat):
    k = Kernel(cat)
    k.define("thermo", Thermo, unit="F")
    k["p"] = patients_s[mod.source()]()
    k["f"] = to_f_s[mod.map()](wf["p"])
    return k


def test_every_object_has_a_spec(k):
    step = k.step("f").spec
    assert isinstance(step, StepSpec) and step.name == "f"
    assert step.operation["tool_id"] == "to_f_s"
    assert isinstance(k.workflow.spec, WorkflowSpec)
    assert [s.name for s in k.workflow.spec.steps] == ["p", "f"]
    resource_spec = k.workflow.resources["thermo"].spec
    assert (resource_spec.name, resource_spec.type, resource_spec.settings) == (
        "thermo", "Thermo", {"unit": "F"})
    assert isinstance(k.spec, KernelSpec)
    assert k.spec.catalog.tools == {"patients_s": {"extras": {}},
                                    "to_f_s": {"extras": {"simple_steps.ui": {"temp_c": "slider"}}}}
    assert k.spec.catalog.resource_types == ("Thermo",)


def test_a_spec_never_holds_output_data(k):
    k.run_all()
    text = k.to_json()
    assert "97.88" not in text and "temp_c" not in json.dumps(json.loads(text)["steps"])


def test_a_spec_doesnt_change_when_its_object_does(k):
    before = k.step("f").spec
    k.step("f").extras["simple_steps.ui"] = {"color": "red"}
    assert before.extras == {}


def test_save_and_load_give_an_equal_spec(k, cat):
    assert Kernel.from_json(k.to_json(), cat).spec == k.spec
    assert Kernel.from_spec(k.spec, cat).spec == k.spec


def test_extras_stay_with_a_step_and_round_trip(k, cat):
    k.step("f").extras["simple_steps.ui"] = {"color": "red"}
    k.extras["simple_steps.meta"] = {"title": "Fever"}
    k.workflow.resources["thermo"].extras["simple_steps.ui"] = {"icon": "gauge"}
    k["f"] = to_f_s[mod.map()](wf["p"])           # re-declared: extras stay
    assert k.step("f").extras == {"simple_steps.ui": {"color": "red"}}
    loaded = Kernel.from_json(k.to_json(), cat)
    assert loaded.step("f").extras == {"simple_steps.ui": {"color": "red"}}
    assert loaded.extras == {"simple_steps.meta": {"title": "Fever"}}
    assert loaded.workflow.resources["thermo"].extras == {"simple_steps.ui": {"icon": "gauge"}}


def test_unknown_namespaces_survive_a_round_trip(k, cat):
    k.step("p").extras["someone.else"] = {"anything": [1, 2]}
    loaded = Kernel.from_json(k.to_json(), cat)
    assert loaded.step("p").extras == {"someone.else": {"anything": [1, 2]}}


def test_editing_extras_doesnt_make_a_step_stale(k):
    k.run_all()
    k.step("p").extras["simple_steps.ui"] = {"color": "blue"}
    assert [s.state for s in k.steps] == ["completed", "completed"]


def test_extras_must_be_namespaced_literals_to_be_saved(k):
    k.step("f").extras["ui"] = {"color": "red"}
    with pytest.raises(ValueError, match="dotted namespace"):
        k.to_json()
    k.step("f").extras.pop("ui")
    k.step("f").extras["simple_steps.ui"] = object()
    with pytest.raises(TypeError, match="must hold literals"):
        k.to_json()
