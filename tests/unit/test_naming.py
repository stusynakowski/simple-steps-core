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


def test_without_mod_name_the_output_takes_the_steps_name(k):
    # D9 (core-asks L23): not `value`
    k["s"] = to_f_n[mod.map()](wf["p"])
    k.run_all()
    assert list(k.step("s").data.columns) == ["s"]


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
    assert list(k.step("c").data.columns) == ["#g", "band", "c"]


# ── D9: one output column takes its step's name ───────────────────────────
def test_a_rename_renames_the_column_and_what_reads_it(k):
    k["s"] = to_f_n[mod.map()](wf["p"])
    k["top"] = mod.sort(by="s", ascending=False)(wf["s"])
    k["only"] = mod.select(columns=["s"])(wf["top"])
    k.run_all()
    held = k.step("s").output.data["s"].tolist()
    k.rename("s", "temp_f")
    assert k.step("temp_f").state == "completed"                  # no re-run
    assert k.step("temp_f").data["temp_f"].tolist() == held
    assert k.step("top").formula == 'mod.sort(by="temp_f", ascending=False)(wf["temp_f"])'
    assert k.step("only").formula == 'wf["top"][cols["temp_f"]]'
    assert k.step("only").problems == ()                         # checked against top's plan
    k.run_all()
    assert list(k.step("only").data.columns) == ["temp_f"]


def test_a_step_named_like_an_input_column_keeps_value_and_says_so():
    k = Kernel(Catalog(tools=[to_f_n]))
    k["p"] = pd.DataFrame({"temp": [37.0]})
    k["temp"] = to_f_n[mod.map()](wf["p"])
    k.run_all()
    assert list(k.step("temp").data.columns) == ["value"]
    assert [w.code for w in k.step("temp").warnings] == ["step_name_taken"]


def test_an_expand_of_dicts_keeps_key_and_value():
    from simple_steps_core.operation import op
    identity = op("identity")
    k = Kernel(Catalog(tools=[]))
    k["s"] = pd.DataFrame({"scores": [{"a": 1, "b": 2}]})
    k["e"] = identity[mod.expand()](wf["s"])
    k.run_all()
    assert [c for c in k.step("e").data.columns if not c.startswith("#")] == ["key", "value"]


def test_map_after_map_runs_untyped():
    @tool
    def plus_n(value):
        return value + 1
    k = Kernel(Catalog(tools=[plus_n]))
    k["p"] = pd.DataFrame({"n": [1, 2]})
    k["a"] = plus_n[mod.map()](wf["p"])                # the only column, untyped (W13)
    k["b"] = plus_n[mod.map()](wf["a"])
    k.run_all()
    assert k.step("b").data["b"].tolist() == [3, 4]
    assert k.step("b").formula == 'plus_n[mod.map()](wf["a"], value=wf["a"][cols["a"]])'


# ── S4: a dict's keys as columns (core-asks L22) ──────────────────────────
@tool
def pair_n(n: int) -> dict:
    return {"a": n, "b": n + 1} if n != 2 else {"a": n}


def test_a_dict_result_gives_one_column_per_key():
    k = Kernel(Catalog(tools=[pair_n]))
    k["r"] = pd.DataFrame({"n": [1, 2, 3]})
    k["x"] = pair_n[mod.map()](wf["r"])
    plan = k.step("x").plan["columns"]
    assert plan["certainty"] == "unknown" and "its keys are its columns" in plan["because"]
    k.run_all()
    assert k.step("x").data.to_dict("list") == {"a": [1, 2, 3], "b": [2, None, 4]}
    assert k.step("x").output.absent_cells() == {(1, "b")}   # row 1's dict had no b (C6)


def test_one_name_keeps_the_dict_in_one_cell():
    k = Kernel(Catalog(tools=[pair_n]))
    k["r"] = pd.DataFrame({"n": [1]})
    k["x"] = pair_n[mod.map(), mod.name("d")](wf["r"])
    k.run_all()
    assert k.step("x").data.to_dict("list") == {"d": [{"a": 1, "b": 2}]}
