"""A column argument under ``collapse`` passes each group's values (CA-D1).

Plan P1, B-collapse-arg (found 2026-11-16): a column argument written out
under ``collapse(by=…)`` passed the *whole column* to every group, a silent
wrong answer, where binding by name gave each group its own values.
"""

import pandas as pd

from simple_steps_core import Catalog, Kernel, cols, mod, op, tool, wf


@tool
def mean(temp: list) -> float:
    return round(sum(temp) / len(temp), 4)


@tool
def double(am: float) -> float:
    return am * 2


@tool
def pair(a: list, b: list) -> list:
    return list(zip(a, b))


def _kernel():
    k = Kernel(Catalog(tools=[mean, double, pair]))
    k["v"] = pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "ward": ["A", "B", "A"],
                           "am": [37.0, 39.5, 38.2], "pm": [37.4, 39.0, 38.0]})
    return k


def _by_key(k, step, key, column):
    data = k.step(step).output.data
    return dict(zip(data[key], data[column]))


def test_a_column_argument_gets_its_groups_values():
    k = _kernel()
    k["wm"] = mean[mod.collapse(by="ward")](wf["v"], temp=wf["v"]["am"])
    k.run("wm")
    assert k.step("wm").state == "completed"
    assert _by_key(k, "wm", "ward", "wm") == {"A": 37.6, "B": 39.5}


def test_it_gives_what_binding_by_name_gives():
    k = _kernel()
    k["v2"] = mod.rename(columns={"am": "temp"})(wf["v"])
    k["by_name"] = mean[mod.collapse(by="ward")](wf["v2"])
    k["bound"] = mean[mod.collapse(by="ward")](wf["v2"], temp=wf["v2"]["temp"])
    k.run_all()
    assert _by_key(k, "bound", "ward", "bound") == _by_key(k, "by_name", "ward", "by_name")


def test_a_pivot_with_its_columns_bound():
    k = _kernel()
    k["pk"] = mod.pack(columns=["am", "pm"])(wf["v"])
    k["long"] = mod.expand(columns=["pk"])(wf["pk"])
    k["gd"] = op("gather_dict")[mod.collapse(by="name")](
        wf["long"], key=wf["long"]["key"], value=wf["long"]["pk"])
    k.run("gd")
    assert _by_key(k, "gd", "name", "gd") == {
        "Ada": {"am": 37.0, "pm": 37.4},
        "Ben": {"am": 39.5, "pm": 39.0},
        "Cy": {"am": 38.2, "pm": 38.0},
    }


def test_two_column_arguments_stay_row_aligned_within_a_group():
    k = _kernel()
    k["p"] = pair[mod.collapse(by="ward")](wf["v"], a=wf["v"]["name"], b=wf["v"]["am"])
    k.run("p")
    assert _by_key(k, "p", "ward", "p") == {"A": [("Ada", 37.0), ("Cy", 38.2)],
                                           "B": [("Ben", 39.5)]}


def test_a_column_of_an_aligned_step_gets_its_groups_values():
    k = _kernel()
    k["d"] = double[mod.map()](wf["v"])
    k["dm"] = mean[mod.collapse(by="ward")](wf["v"], temp=wf["d"]["d"])
    k.run("dm")
    assert _by_key(k, "dm", "ward", "dm") == {"A": 75.2, "B": 79.0}


def test_a_column_of_unrelated_rows_is_refused_writing_the_join():
    k = _kernel()
    k["w"] = pd.DataFrame({"temp": [1.0, 2.0, 3.0]})
    k["x"] = mean[mod.collapse(by="ward")](wf["v"], temp=wf["w"]["temp"])
    step = k.step("x")
    assert step.state == "invalid"
    assert any("join" in p.message for p in step.problems)


def test_a_one_cell_argument_is_the_same_value_for_every_group():
    @tool
    def above(temp: list, limit: float) -> int:
        return sum(t > limit for t in temp)

    k = Kernel(Catalog(tools=[above]))
    k["v"] = pd.DataFrame({"ward": ["A", "B", "A"], "temp": [37.0, 39.5, 38.2]})
    k["lim"] = 38.0
    k["n"] = above[mod.collapse(by="ward")](wf["v"], limit=wf["lim"][0][cols["lim"]])
    k.run("n")
    assert _by_key(k, "n", "ward", "n") == {"A": 1, "B": 1}


def test_a_one_value_parameter_is_refused_naming_the_list_it_gets():
    @tool
    def one(temp: float) -> float:
        return temp

    k = Kernel(Catalog(tools=[one]))
    k["v"] = pd.DataFrame({"ward": ["A", "B", "A"], "am": [37.0, 39.5, 38.2]})
    k["x"] = one[mod.collapse(by="ward")](wf["v"], temp=wf["v"]["am"])
    step = k.step("x")
    assert step.state == "invalid"
    assert any("declare temp: list" in p.message for p in step.problems)
