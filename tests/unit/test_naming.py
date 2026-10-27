"""mod.name: what a step's output column is called (G12). The last naming
modifier wins; with none, columns keep their defaults (owner, 2026-10-27)."""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, Operation, mod, tool, wf
from simple_steps_core.catalog import formula_names


@tool
def patients_n() -> pd.DataFrame:
    return pd.DataFrame({"ward": ["A", "B", "A"], "temp_c": [36.6, 38.2, 37.1]})


@tool
def to_f_n(temp_c: float) -> float:
    return round(temp_c * 9 / 5 + 32, 2)


@tool
def both_n(temp_c: float) -> list:
    return [temp_c, temp_c]


@tool
def add_n(acc: float, temp_c: float) -> float:
    return (acc or 0) + temp_c


@tool
def grid_n(model: str) -> str:
    return model.upper()


@tool
def hot_n(temp_c: float) -> bool:
    return temp_c > 37


@pytest.fixture
def k():
    k = Kernel(Catalog(tools=[patients_n, to_f_n, both_n, add_n, grid_n, hot_n]))
    k["p"] = patients_n[mod.source()]()
    return k


@pytest.mark.parametrize("step, columns", [
    (lambda: to_f_n[mod.map(), mod.name("temp_f")](wf["p"]), ["temp_f"]),
    (lambda: both_n[mod.expand(), mod.name("reading")](wf["p"]), ["#p", "reading"]),
    (lambda: add_n[mod.collapse(by="ward"), mod.name("total")](wf["p"]), ["#p", "ward", "total"]),
    (lambda: to_f_n[mod.group(), mod.name("band")](wf["p"]), ["ward", "temp_c", "band"]),
    (lambda: grid_n[mod.sweep(model=["a", "b"]), mod.name("upper")](), ["model", "upper"]),
    (lambda: to_f_n[mod.name("temp_f")](wf["p"]), ["temp_f"]),                       # auto
])
def test_mod_name_names_the_output_column(k, step, columns):
    k["s"] = step()
    assert k.step("s").problems == ()
    k.run_all()
    assert list(k.step("s").data.columns) == columns


def test_without_mod_name_the_default_stays(k):
    k["s"] = to_f_n[mod.map()](wf["p"])
    k.run_all()
    assert list(k.step("s").data.columns) == ["value"]


def test_the_last_naming_modifier_wins_wherever_it_is_written(k):
    k["s"] = to_f_n[mod.name("first"), mod.map(), mod.retry(times=1), mod.name("last")](wf["p"])
    k.run_all()
    assert list(k.step("s").data.columns) == ["last"]


def test_the_plan_before_running_uses_the_name(k):
    k["s"] = to_f_n[mod.map(), mod.name("temp_f")](wf["p"])
    assert k.step("s").output.plan["columns"]["names"] == ["temp_f"]


def test_name_on_the_verb_is_retired(k):
    k["s"] = to_f_n[mod.map(name="temp_f")](wf["p"])
    problem = k.step("s").problems[0]
    assert problem.code == "unknown_setting"
    assert problem.message == ("map's name= is retired: name the output with "
                               'mod.name("temp_f") after the verb')


@pytest.mark.parametrize("step, message", [
    (lambda: hot_n[mod.filter(), mod.name("x")](wf["p"]), "filter writes no new values"),
    (lambda: to_f_n[mod.map(), mod.name("#")](wf["p"]), "'#' is the row id"),
    (lambda: to_f_n[mod.map(), mod.name("")](wf["p"]), "mod.name needs a column name"),
])
def test_a_bad_name_is_a_problem(k, step, message):
    k["s"] = step()
    problem = k.step("s").problems[0]
    assert problem.code == "bad_name" and message in problem


def test_mod_name_takes_one_name():
    with pytest.raises(TypeError, match="takes one name"):
        mod.name("a", "b")


def test_a_named_step_prints_saves_and_loads(k):
    k["s"] = to_f_n[mod.map(), mod.name("temp_f")](wf["p"])
    assert k.step("s").formula == 'to_f_n[mod.map(), mod.name("temp_f")](wf["p"])'
    again = Kernel(k.catalog)
    again["p"] = patients_n[mod.source()]()
    again["s"] = eval(k.step("s").formula, {"__builtins__": {}}, formula_names(k.catalog.functions))
    assert again.step("s").spec.operation == k.step("s").spec.operation
    loaded = Kernel.from_json(k.to_json(), k.catalog)
    loaded.run_all()
    assert list(loaded.step("s").data.columns) == ["temp_f"]


def test_a_named_key_feeds_collapse(k):
    k["g"] = to_f_n[mod.group(), mod.name("band")](wf["p"])
    k["c"] = Operation(tool="count")[mod.collapse(by="band")](wf["g"])
    k.run_all()
    assert list(k.step("c").data.columns) == ["#g", "band", "value"]
