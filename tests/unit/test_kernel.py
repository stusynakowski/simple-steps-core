"""The Kernel: a workflow, its catalog and its loaded resources
(docs/design/object-model.md §4.12, docs/design/interactive-sessions.md)."""

from __future__ import annotations

import os
import warnings

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, bound_tool, mod, res, resource, tool, wf


@tool
def patients_k() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "temp_c": [36.6, 38.2, 37.1]})


@tool
def to_f_k(temp_c: float) -> float:
    return round(temp_c * 9 / 5 + 32, 2)


@tool
def feverish_k(temp_c: float, limit: float = 38) -> bool:
    return temp_c >= limit


@resource
class Ward:
    built = 0

    def __init__(self, name: str = "A"):
        self.name = name
        Ward.built += 1

    @bound_tool
    def label(self, name: str) -> str:
        return f"{self.name}:{name}"


@pytest.fixture
def cat():
    return Catalog(tools=[patients_k, to_f_k, feverish_k], resources=[Ward])


@pytest.fixture
def k(cat):
    k = Kernel(cat)
    k["p"] = patients_k[mod.source()]()
    k["sick"] = feverish_k[mod.filter()](wf["p"])
    k["f"] = to_f_k[mod.map()](wf["sick"])
    return k


def values(k, step):
    return k.step(step).output.data["value"].tolist()


def test_a_kernel_needs_a_catalog():
    with pytest.raises(TypeError, match="pass a Catalog"):
        Kernel([to_f_k])


def test_declaring_checks_and_plans_without_running(k):
    assert k.validate() == {"p": (), "sick": (), "f": ()}
    assert [s.state for s in k.steps] == ["staged"] * 3
    assert len(k) == 3 and list(k) == ["p", "sick", "f"] and "f" in k


def test_run_runs_inputs_that_never_ran_first(k):
    k.run("f")
    assert [s.state for s in k.steps] == ["completed"] * 3
    assert values(k, "f") == [100.76]


def test_a_stale_input_passes_through_as_it_is(k):
    k.run_all()
    k["sick"] = feverish_k[mod.filter()](wf["p"], limit=37)
    assert k.step("sick").state == "stale"
    k.run("f")
    # f is computed from what sick shows: its old output, one row.
    assert values(k, "f") == [100.76]
    assert k.step("sick").state == "stale"
    k.run("sick")
    assert k.step("f").state == "stale"
    k.run("f")
    assert values(k, "f") == [100.76, 98.78]


def test_steps_are_found_by_name_or_position(k):
    assert k.step(2) is k.step("f") and k.step(-1) is k.step("f")
    assert k[0].id == "p"
    with pytest.raises(IndexError, match="no step at position 9"):
        k.step(9)
    with pytest.raises(KeyError, match="no step 'nope'"):
        k.step("nope")


def test_rename_and_delete(k):
    k.rename("sick", "fever")
    assert list(k) == ["p", "fever", "f"]
    assert k.step("f").operation.to_source() == 'to_f_k[mod.map()](wf["fever"])'
    with pytest.raises(ValueError, match="'f' read"):
        del k["fever"]
    del k["f"]
    assert list(k) == ["p", "fever"]


def test_a_tool_outside_the_catalog_is_a_problem(k):
    k["x"] = tool(os.remove)[mod.map()](wf["p"])
    assert k.step("x").problems == ("'remove' is not in this workflow's catalog",)


def test_resources_are_built_from_their_spec_when_first_needed(k):
    Ward.built = 0
    k.define("ward", Ward, name="B")
    k["labels"] = res["ward"].label[mod.map()](wf["p"])
    assert k.resources.loaded == [] and Ward.built == 0
    k.run("labels")
    assert values(k, "labels") == ["B:Ada", "B:Ben", "B:Cy"]
    assert k.resources.loaded == ["ward"] and Ward.built == 1
    k.run("labels")
    assert Ward.built == 1                          # built once
    k.define("ward", Ward, name="C")                # new settings: built afresh
    k.run("labels")
    assert values(k, "labels") == ["C:Ada", "C:Ben", "C:Cy"]


def test_an_attached_resource_is_used_as_it_is(k):
    k.define("ward", Ward)
    k.resources.attach("ward", Ward(name="Z"))
    k["labels"] = res["ward"].label[mod.map()](wf["p"])
    k.run("labels")
    assert values(k, "labels") == ["Z:Ada", "Z:Ben", "Z:Cy"]
    with pytest.raises(TypeError, match="resource 'ward' is a Ward"):
        k.resources.attach("ward", object())
    with pytest.raises(KeyError, match="no resource 'other'"):
        k.resources.attach("other", Ward())


def test_a_resource_type_outside_the_catalog_cannot_be_defined():
    k = Kernel(Catalog(tools=[patients_k]))
    with pytest.raises(ValueError, match="Ward is not in this workflow's catalog"):
        k.define("ward", Ward)


def test_saving_and_loading_against_a_catalog(k, cat):
    k.run_all()
    text = k.to_json()
    assert '"value"' not in text                     # a spec, no output data
    loaded = Kernel.from_json(text, cat)
    assert [s.state for s in loaded.steps] == ["staged"] * 3
    loaded.run("f")
    assert values(loaded, "f") == [100.76]
    smaller = Kernel.from_json(text, cat.without("to_f_k"))
    assert smaller.step("f").problems == ("'to_f_k' is not in this workflow's catalog",)


def test_two_kernels_in_one_process_share_nothing():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        @tool(id="grade_k")
        def grade_a(temp_c: float) -> str:
            return "a"

        @tool(id="grade_k")
        def grade_b(temp_c: float) -> str:
            return "b"
    ka = Kernel(Catalog(tools=[patients_k, grade_a]))
    kb = Kernel(Catalog(tools=[patients_k, grade_b]))
    for k, grade in ((ka, grade_a), (kb, grade_b)):
        k["p"] = patients_k[mod.source()]()
        k["g"] = grade[mod.map()](wf["p"])
        k.run_all()
    assert values(ka, "g") == ["a"] * 3 and values(kb, "g") == ["b"] * 3


def test_a_kernel_shows_itself_as_a_table(k):
    k.run("f")
    k["x"] = tool(os.remove)[mod.map()](wf["p"])
    lines = repr(k).splitlines()
    assert lines[0] == "Kernel: 4 steps, 3 tools (+ built-ins), 0 resources"
    assert lines[1].split() == ["#", "step", "formula", "state", "shape", "problem"]
    assert lines[2].split()[:2] == ["0", "p"] and "completed  3×2" in lines[2]
    assert lines[4].split()[1:3] == ["f", 'to_f_k[mod.map()](wf["sick"])']
    assert "invalid" in lines[5] and "'remove' is not in this workflow's catalog" in lines[5]
    page = k._repr_html_()
    assert page.startswith("<p>Kernel: 4 steps") and "<td>to_f_k[mod.map()](wf[&quot;sick&quot;])</td>" in page


def test_an_empty_kernel_shows_its_heading():
    assert repr(Kernel(Catalog())) == "Kernel: 0 steps, 0 tools (+ built-ins), 0 resources"


def test_a_shadowed_rows_is_refused_through_a_kernel_too(k):
    rows = [10, 20, 30]  # noqa: F841 — shadows core's `rows`, which is the point
    with pytest.raises(TypeError, match="'rows' is reserved for row selection"):
        k["x"] = [1, 2]
