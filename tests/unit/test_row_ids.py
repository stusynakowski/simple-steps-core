"""Row ids (K19, docs/design/row-ids.md): selections pick rows by id, and a
range picks positions."""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, cols, mod, rows, tool, wf
from simple_steps_core.catalog import formula_names
from simple_steps_core.errors import SelectionError


@tool
def patients_r() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "temp_c": [36.6, 38.2, 37.1]})


@tool
def visits_r(name: str) -> list:
    return [f"{name}-1", f"{name}-2"]


@tool
def above_r(temp_c: float, limit: float) -> bool:
    return temp_c > limit


@pytest.fixture
def k():
    k = Kernel(Catalog(tools=[patients_r, visits_r, above_r]))
    k["p"] = patients_r[mod.source()]()
    k["srt"] = mod.sort(by="temp_c", ascending=False)(wf["p"])   # Ben, Cy, Ada
    k.run_all()
    return k


def names(k, step):
    return k.step(step).data["name"].tolist()


def test_a_row_is_picked_by_its_id_wherever_a_sort_put_it(k):
    k["first"] = wf["srt"][0]                      # row id 0 is Ada, now last
    k["pair"] = wf["srt"][[0, 2]]
    k.run_all()
    assert names(k, "first") == ["Ada"]
    assert names(k, "pair") == ["Ada", "Cy"]
    assert list(k.step("pair").data.index) == [0, 2]


def test_a_range_is_positions_the_top_rows(k):
    k["top2"] = wf["srt"][0:2]
    k["last"] = wf["srt"][-1:]
    k.run_all()
    assert names(k, "top2") == ["Ben", "Cy"]
    assert names(k, "last") == ["Ada"]


def test_a_string_row_id_goes_through_rows(k):
    k["e"] = visits_r[mod.expand()](wf["p"])
    k.run("e")
    k["one"] = wf["e"][rows["1.0"]]
    k["two"] = wf["e"][rows[["0.1", "2.0"]]]
    k.run_all()
    assert k.step("one").data["value"].tolist() == ["Ben-1"]
    assert k.step("two").data["value"].tolist() == ["Ada-2", "Cy-1"]
    with pytest.raises(SelectionError, match=r"goes through rows: wf\[…\]\[rows\['1.0'\]\]"):
        wf["e"]["1.0"]


def test_an_id_the_step_doesnt_have_is_a_problem(k):
    k["far"] = wf["srt"][9]
    problem = k.step("far").problems[0]
    assert problem.code == "bad_selection"
    assert "'srt' has no row 9 (its row ids are 1, 2, 0)" in problem


def test_a_negative_row_is_refused_with_the_range_to_use_instead():
    with pytest.raises(SelectionError, match=r"row ids aren't negative.*\[-1:\]"):
        wf["srt"][-1]


def test_a_cell_picked_by_id_as_an_argument_follows_its_row(k):
    # Ada's temperature, though a sort moved her row to the end.
    k["over_ada"] = above_r[mod.filter()](wf["p"], limit=wf["srt"][0][cols["temp_c"]])
    k.run("over_ada")
    assert names(k, "over_ada") == ["Ben", "Cy"]


@pytest.mark.parametrize("text", ['wf["e"][rows["1.0"]]', 'wf["e"][rows[["0.1", "2.0"]]]',
                                  'wf["srt"][[0, 2]]', 'wf["srt"][0:2]'])
def test_selections_by_id_print_and_read_back(k, text):
    k["e"] = visits_r[mod.expand()](wf["p"])
    names_ = formula_names(k.catalog.functions)
    k["s"] = eval(text, {"__builtins__": {}}, names_)
    assert k.step("s").formula == text
