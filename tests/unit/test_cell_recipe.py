"""A cell's recipe (plan P7r): the expression that makes it, run back.

``k.cell(step, row, column)["recipe"]`` is the step's formula with its input
picked down to the cell's row(s), and each argument paired with the input
picked to the same row. Running that formula as a step gives the cell again.
"""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, tool, wf
from simple_steps_core.formula import formula


@tool
def scale(x: float, by: float = 2.0) -> float:
    return x * by


@tool
def big(x: float) -> bool:
    return x > 1


@tool
def add(x: float, y: float) -> float:
    return x + y


@tool
def sumup(x: list) -> float:
    return sum(x)


@tool
def split(x: float) -> list:
    return [x, -x]


@tool
def rgb(x: float) -> tuple[float, float, float]:
    return (x, x + 1, x + 2)


def kernel() -> Kernel:
    k = Kernel(Catalog(tools=[scale, big, add, sumup, split, rgb]))
    k["src"] = pd.DataFrame({"g": ["a", "b", "a"], "x": [1.0, 2.0, 3.0], "y": [10.0, 20.0, 30.0]})
    k["f"] = big[mod.filter()](wf["src"])
    k["s"] = scale[mod.map()](wf["f"]["x"], by=3.0)
    k["p"] = add[mod.map()](wf["src"]["x"], y=wf["src"]["y"])
    k["t"] = sumup[mod.collapse(by="g")](wf["src"])
    k["e"] = split[mod.expand()](wf["src"]["x"])
    k["c"] = rgb[mod.map()](wf["src"]["x"])
    k["cp"] = wf["f"]["x"]
    return k


def _values(k: Kernel, name: str) -> list:
    view = k.view(name)
    first = view["columns"][0]["name"]
    return [r["cells"][first].get("value") for r in view["rows"]]


def _run_back(k: Kernel, text: str) -> list:
    k["_recipe"] = formula(text)
    k.run("_recipe", force=True)
    try:
        return _values(k, "_recipe")
    finally:
        del k["_recipe"]


@pytest.mark.parametrize("name, row, text, of", [
    ("f", 0, 'big[mod.filter()](wf["src"][1])', "row"),
    ("s", 1, 'scale[mod.map()](wf["f"][1][cols["x"]], by=3.0)', "row"),
    ("p", 2, 'add[mod.map()](wf["src"][2][cols["x"]], y=wf["src"][2][cols["y"]])', "row"),
    ("t", 0, 'sumup[mod.collapse(by="g")](wf["src"][[0, 2]])', "rows"),
    ("e", 3, 'split[mod.expand()](wf["src"][1][cols["x"]])', "row"),
    ("c", 2, 'rgb[mod.map()](wf["src"][2][cols["x"]])', "row"),
    ("cp", 1, 'wf["f"][1][cols["x"]]', "row"),
])
def test_recipe_is_the_expression_for_the_cell(name, row, text, of):
    k = kernel()
    k.run_all()
    column = k.view(name)["columns"][-1]["name"]
    assert k.cell(name, row, column)["recipe"] == {"formula": text, "of": of}


@pytest.mark.parametrize("name", ["f", "s", "p", "t", "e", "c", "cp"])
def test_every_recipe_runs_back_to_its_cell(name):
    """Each row's recipe, run as a step, gives that row (expand: its parent's items)."""
    k = kernel()
    k.run_all()
    view = k.view(name)
    first = view["columns"][0]["name"]
    for r, entry in enumerate(view["rows"]):
        recipe = k.cell(name, r, first)["recipe"]
        assert recipe["of"] in ("row", "rows")
        back = _run_back(k, recipe["formula"])
        assert entry["cells"][first]["value"] in back
        if name != "e":
            assert back == [entry["cells"][first]["value"]]


def test_a_recipe_follows_row_ids_through_a_filter():
    """Row 0 of s is row 0 of f, which is row 1 of src: the pick names f's row."""
    k = kernel()
    k.run_all()
    assert k.cell("s", 0, "s")["inputs"][0]["row"] == 0
    assert k.cell("s", 0, "s")["recipe"]["formula"].startswith('scale[mod.map()](wf["f"][0]')
    assert k.cell("f", 0, "x")["recipe"]["formula"] == 'big[mod.filter()](wf["src"][1])'


def test_a_staged_cell_knows_its_recipe():
    k = kernel()                                    # nothing run
    assert k.cell("c", 1, "c")["recipe"] == {
        "formula": 'rgb[mod.map()](wf["src"][1][cols["x"]])', "of": "row"}


def test_a_cell_whose_row_is_not_known_yet_gives_the_steps_formula():
    k = kernel()                                    # f hasn't run: s's rows aren't known
    cell = k.cell("s", 1, "s")
    assert cell["state"] == "unknown"
    assert cell["recipe"] == {"formula": 'scale[mod.map()](wf["f"][cols["x"]], by=3.0)',
                              "of": "step"}


def test_data_and_values_have_no_smaller_recipe():
    k = kernel()
    k["limit"] = 2.0
    k.run_all()
    assert k.cell("src", 0, "x")["recipe"] == {"formula": "<DataFrame 3×3>", "of": "step"}
    assert k.cell("limit", 0, "limit")["recipe"] == {"formula": "2.0", "of": "step"}


def test_a_table_step_recipe_is_the_whole_step():
    @tool
    def head(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.head(2)
    k = Kernel(Catalog(tools=[head]))
    k["src"] = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
    k["h"] = head[mod.table()](wf["src"])
    k.run_all()
    column = k.view("h")["columns"][0]["name"]
    assert k.cell("h", 0, column)["recipe"] == {"formula": 'head[mod.table()](wf["src"])',
                                                "of": "step"}
