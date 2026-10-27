"""The Catalog: what a workflow may use (docs/design/object-model.md §4.3)."""

from __future__ import annotations

import os
import types
import warnings

import pandas as pd
import pytest

from simple_steps_core import bound_tool, Catalog, mod, res, resource, tool, wf, zip_
from simple_steps_core.workflow import Workflow


@tool
def patients_c() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Ben"], "temp_c": [36.6, 38.2]})


@tool(tags=["units"], extras={"simple_steps.ui": {"temp_c": "slider"}})
def to_f_c(temp_c: float) -> float:
    """Celsius to Fahrenheit."""
    return round(temp_c * 9 / 5 + 32, 2)


@tool
def outsider_c(temp_c: float) -> float:
    return 0.0


@tool
def key_c(name: str) -> str:
    return name[0]


@resource
class WardDB:
    def __init__(self, ward: str = "A"):
        self.ward = ward

    @bound_tool
    def ward_of(self, name: str) -> str:
        return self.ward


@pytest.fixture
def cat():
    return Catalog(tools=[patients_c, to_f_c])


def fever(cat) -> Workflow:
    w = Workflow(catalog=cat)
    w["p"] = patients_c[mod.source()]()
    w["f"] = to_f_c[mod.map()](wf["p"])
    return w


# ── what a catalog holds ─────────────────────────────────────────────────
def test_a_catalog_has_its_tools_and_every_builtin_by_default(cat):
    assert set(cat.tools) == {"patients_c", "to_f_c"}
    assert {"identity", "count", "gather"} <= cat.builtins
    assert {"map", "filter", "retry", "try_except"} <= cat.modifiers
    assert cat.combines == {"join", "stack", "zip"}
    assert "to_f_c" in cat and "map" in cat and "join" in cat
    assert "outsider_c" not in cat


def test_only_tools_go_in_a_catalog():
    def plain(x):
        return x
    with pytest.raises(TypeError, match="Decorate it with @tool"):
        Catalog(tools=[plain])


def test_two_different_tools_cannot_share_a_name():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # @tool warns that it replaces one

        @tool(id="dup_c")
        def one(x: int) -> int:
            return x

        @tool(id="dup_c")
        def two(x: int) -> int:
            return -x
    with pytest.raises(ValueError, match="two different tools are named 'dup_c'"):
        Catalog(tools=[one, two])


def test_without_removes_named_entries_and_refuses_unknown_names(cat):
    smaller = cat.without("count", "retry", "join", "to_f_c")
    assert "count" not in smaller and "retry" not in smaller
    assert "join" not in smaller and "to_f_c" not in smaller
    assert "to_f_c" in cat                         # the original is unchanged
    with pytest.raises(KeyError, match="'nope'"):
        cat.without("nope")


def test_from_modules_collects_tools_and_resource_types():
    module = types.ModuleType("lab_tools")
    module.to_f_c, module.patients_c = to_f_c, patients_c
    WardDB_here = type("WardHere", (), {"__init__": lambda self: None,
                                        "__module__": "lab_tools"})
    module.WardHere = resource(WardDB_here)
    found = Catalog.from_modules(module)
    assert set(found.tools) == {"to_f_c", "patients_c"}
    assert set(found.resource_types) == {"WardHere"}


def test_a_tool_carries_its_tags_and_extras(cat):
    assert to_f_c.tags == ("units",)
    assert to_f_c.extras == {"simple_steps.ui": {"temp_c": "slider"}}
    entry = cat.describe()["tools"]["to_f_c"]
    assert entry["tags"] == ["units"]
    assert entry["extras"] == {"simple_steps.ui": {"temp_c": "slider"}}


def test_extras_keys_are_namespaces_and_values_are_literals():
    with pytest.raises(ValueError, match="dotted namespace"):
        tool(extras={"ui": {}})(lambda x: x)
    with pytest.raises(TypeError, match="must hold literals"):
        tool(extras={"simple_steps.ui": object()})(lambda x: x)


def test_describe_lists_only_what_the_catalog_has(cat):
    found = cat.without("count", "retry").describe()
    assert set(found) == {"tools", "modifiers", "combines", "resource_types"}
    assert "count" not in found["tools"] and "to_f_c" in found["tools"]
    assert "retry" not in found["modifiers"] and "map" in found["modifiers"]
    assert found["tools"]["to_f_c"]["origin"] == "declared"
    assert found["tools"]["identity"]["origin"] == "builtin"


def test_a_catalog_prints_its_entries_by_kind(cat):
    text = repr(cat.without("count"))
    assert text.splitlines()[0] == "Catalog: 2 tools, 0 resource types, 1 built-ins removed"
    assert "patients_c, to_f_c" in text


# ── a workflow checked against its catalog ───────────────────────────────
def test_a_tool_outside_the_catalog_is_a_problem_and_never_runs(cat):
    w = fever(cat)
    w["x"] = outsider_c[mod.map()](wf["p"])
    w["rm"] = tool(os.remove)[mod.map()](wf["p"])
    assert w.step("x").problems == ("'outsider_c' is not in this workflow's catalog",)
    assert w.step("rm").problems == ("'remove' is not in this workflow's catalog",)
    assert w.step("f").problems == ()
    w.run("p")
    with pytest.raises(ValueError, match="is invalid and cannot run"):
        w.run("x")


def test_a_removed_modifier_or_combine_is_a_problem(cat):
    w = fever(cat.without("retry", "zip"))
    w["r"] = to_f_c[mod.map(), mod.retry(times=2)](wf["p"])
    w["z"] = zip_(wf["p"], wf["f"])
    assert w.step("r").problems == ("modifier 'retry' is not in this workflow's catalog",)
    assert w.step("z").problems == ("'zip' is not in this workflow's catalog",)


def test_a_tool_given_as_a_setting_must_be_in_the_catalog(cat):
    w = fever(cat)
    w["g"] = to_f_c[mod.collapse(by=key_c)](wf["p"])
    assert "tool 'key_c' is not in this workflow's catalog" in w.step("g").problems


def test_a_different_function_under_a_catalog_name_is_refused(cat):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        @tool(id="to_f_c")
        def impostor(temp_c: float) -> float:
            return -1.0
    w = fever(cat)
    w["imp"] = impostor[mod.map()](wf["p"])
    assert w.step("imp").problems == (
        "'to_f_c' is a different function from the tool of that name in this "
        "workflow's catalog",)


def test_catalog_problems_survive_a_recheck(cat):
    w = fever(cat)
    w["x"] = outsider_c[mod.map()](wf["f"])
    w["f"] = to_f_c[mod.map()](wf["p"])            # re-declaring f re-checks x
    assert w.step("x").problems == ("'outsider_c' is not in this workflow's catalog",)


def test_a_resource_type_outside_the_catalog_cannot_be_defined(cat):
    w = fever(cat)
    with pytest.raises(ValueError, match="WardDB is not in this workflow's catalog"):
        w.define("db", WardDB)
    ok = Workflow(catalog=Catalog(tools=[patients_c], resources=[WardDB]))
    ok.define("db", WardDB, ward="B")
    ok["p"] = patients_c[mod.source()]()
    ok["w"] = res["db"].ward_of[mod.map()](wf["p"])
    assert ok.step("w").problems == ()


# ── isolation: two catalogs in one process (K24) ─────────────────────────
def test_each_workflow_runs_its_own_catalogs_tool():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        @tool(id="score_iso")
        def score_a(temp_c: float) -> str:
            return "a"

        @tool(id="score_iso")
        def score_b(temp_c: float) -> str:
            return "b"
    wa = Workflow(catalog=Catalog(tools=[patients_c, score_a]))
    wb = Workflow(catalog=Catalog(tools=[patients_c, score_b]))
    for w, handle in ((wa, score_a), (wb, score_b)):
        w["p"] = patients_c[mod.source()]()
        w["s"] = handle[mod.map()](wf["p"])
        w.run_all()
    assert wa.step("s").output.data["value"].tolist() == ["a", "a"]
    assert wb.step("s").output.data["value"].tolist() == ["b", "b"]
    # Loaded from the same file, each runs the tool its own catalog has.
    text = wa.to_json()
    for catalog, expected in ((Catalog(tools=[patients_c, score_a]), "a"),
                              (Catalog(tools=[patients_c, score_b]), "b")):
        loaded = Workflow.from_json(text, catalog=catalog)
        loaded.run_all()
        assert loaded.step("s").output.data["value"].tolist() == [expected] * 2


# ── loading against a catalog ────────────────────────────────────────────
def test_a_loaded_workflow_is_checked_against_the_catalog(cat):
    w = fever(cat)
    text = w.to_json()
    loaded = Workflow.from_json(text, catalog=cat)
    loaded.run_all()
    assert loaded.step("f").output.data["value"].tolist() == [97.88, 100.76]
    smaller = Workflow.from_json(text, catalog=cat.without("to_f_c"))
    assert smaller.step("f").problems == ("'to_f_c' is not in this workflow's catalog",)
