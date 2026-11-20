"""A cell's recipe (plan P7r): the call that makes it, with the cells it read.

``k.cell(step, row, column)["recipe"]``: ``formula`` is the tool called on
picks, one per parameter (owner, 2026-11-20: "a map should show the paired
references; a collapse the reference column or ranges; a tool with several
outputs ``operation(inputs)[0]``"). ``as_step`` is the step's formula picked
to those rows: declared as a step, it gives the cell again.
"""

from __future__ import annotations

from typing import NamedTuple

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


class RGB(NamedTuple):
    r: float
    g: float
    b: float


@tool
def channels(x: float) -> RGB:
    return RGB(x, x + 1, x + 2)


def kernel() -> Kernel:
    k = Kernel(Catalog(tools=[scale, big, add, sumup, split, rgb, channels]))
    k["src"] = pd.DataFrame({"g": ["a", "b", "a"], "x": [1.0, 2.0, 3.0], "y": [10.0, 20.0, 30.0]})
    k["f"] = big[mod.filter()](wf["src"])
    k["s"] = scale[mod.map()](wf["f"]["x"], by=3.0)
    k["p"] = add[mod.map()](wf["src"]["x"], y=wf["src"]["y"])
    k["t"] = sumup[mod.collapse(by="g")](wf["src"])
    k["e"] = split[mod.expand()](wf["src"]["x"])
    k["c"] = rgb[mod.map()](wf["src"]["x"])
    k["ch"] = channels[mod.map()](wf["src"]["x"])
    k["cp"] = wf["f"]["x"]
    return k


def _run_back(k: Kernel, text: str) -> list:
    k["_recipe"] = formula(text)
    k.run("_recipe", force=True)
    try:
        view = k.view("_recipe")
        return [[c.get("value") for c in r["cells"].values()] for r in view["rows"]]
    finally:
        del k["_recipe"]


@pytest.mark.parametrize("name, row, column, text", [
    # a map: each parameter with the cell it read, a paired argument's too
    ("s", 1, "s", 'scale(x=wf["f"][1][cols["x"]], by=3.0)'),
    ("p", 2, "p", 'add(x=wf["src"][2][cols["x"]], y=wf["src"][2][cols["y"]])'),
    # a collapse: the column, over the group's rows
    ("t", 0, "t", 'sumup(x=wf["src"][[0, 2]][cols["x"]])'),
    ("t", 1, "t", 'sumup(x=wf["src"][[1]][cols["x"]])'),
    # several outputs: the call, then the part the cell holds
    ("e", 3, "e", 'split(x=wf["src"][1][cols["x"]])[1]'),
    ("ch", 2, "g", 'channels(x=wf["src"][2][cols["x"]])["g"]'),
    ("c", 2, "c", 'rgb(x=wf["src"][2][cols["x"]])'),
    # a copied cell is its pick
    ("cp", 1, "x", 'wf["f"][1][cols["x"]]'),
    ("f", 0, "y", 'wf["src"][1][cols["y"]]'),
    ("t", 0, "g", 'wf["src"][[0, 2]][cols["g"]]'),
])
def test_a_cells_formula_is_its_call(name, row, column, text):
    k = kernel()
    k.run_all()
    assert k.cell(name, row, column)["recipe"]["formula"] == text


def test_a_filters_cell_says_what_kept_it():
    k = kernel()
    k.run_all()
    recipe = k.cell("f", 0, "y")["recipe"]
    assert recipe["kept_by"] == 'big(x=wf["src"][1][cols["x"]])'
    assert recipe["as_step"] == 'big[mod.filter()](wf["src"][1])'


def test_a_group_that_runs_on_is_a_range():
    k = Kernel(Catalog(tools=[sumup]))
    k["v"] = pd.DataFrame({"g": ["a", "a", "a", "b"], "x": [1.0, 2.0, 3.0, 4.0],
                           "am": [5.0, 6.0, 7.0, 8.0]})
    k["t"] = sumup[mod.collapse(by="g")](wf["v"], x=wf["v"]["am"])
    k.run_all()
    cell = k.cell("t", 0, "t")
    assert cell["value"] == 18.0
    assert cell["recipe"]["formula"] == 'sumup(x=wf["v"][0:3][cols["am"]])'
    assert cell["recipe"]["of"] == "rows"


def test_a_binding_core_wrote_by_type_shows_its_cell():
    k = Kernel(Catalog(tools=[scale]))
    k["src"] = pd.DataFrame({"temp": [1.0, 2.0]})
    k["s"] = scale[mod.map()](wf["src"]["temp"])
    k.run_all()
    assert k.cell("s", 1, "s")["recipe"]["formula"] == 'scale(x=wf["src"][1][cols["temp"]])'


@pytest.mark.parametrize("name", ["f", "s", "p", "t", "e", "c", "ch", "cp"])
def test_every_recipe_as_a_step_gives_its_row(name):
    """Each row's ``as_step``, declared, gives that row (an expand: its parent's items)."""
    k = kernel()
    k.run_all()
    view = k.view(name)
    for r, entry in enumerate(view["rows"]):
        first = next(iter(entry["cells"]))
        recipe = k.cell(name, r, first)["recipe"]
        assert recipe["of"] in ("row", "rows")
        back = _run_back(k, recipe["as_step"])
        mine = [c.get("value") for c in entry["cells"].values()]
        assert mine in back if name == "e" else back == [mine]


def test_a_recipe_follows_row_ids_through_a_filter():
    """Row 0 of s is row 0 of f, which is row 1 of src."""
    k = kernel()
    k.run_all()
    assert k.cell("s", 0, "s")["recipe"]["formula"] == 'scale(x=wf["f"][0][cols["x"]], by=3.0)'
    assert k.cell("f", 0, "x")["recipe"]["formula"] == 'wf["src"][1][cols["x"]]'


def test_a_staged_cell_knows_its_recipe():
    k = kernel()                                    # nothing run
    assert k.cell("c", 1, "c")["recipe"]["formula"] == 'rgb(x=wf["src"][1][cols["x"]])'


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


# ── K-cell: a cell's inputs name the cells it read ─────────────────────────
def test_a_paired_argument_is_the_one_cell_of_this_row():
    k = kernel()
    k.run_all()
    inputs = {i["argument"]: i for i in k.cell("p", 1, "p")["inputs"]}
    assert (inputs["y"]["row"], inputs["y"]["values"]) == (1, {"y": 20.0})
    assert "rows" not in inputs["y"]


def test_a_collapses_paired_argument_is_its_groups_rows():
    k = Kernel(Catalog(tools=[sumup]))
    k["v"] = pd.DataFrame({"g": ["a", "b", "a"], "am": [5.0, 6.0, 7.0]})
    k["t"] = sumup[mod.collapse(by="g")](wf["v"], x=wf["v"]["am"])
    k.run_all()
    (entry,) = k.cell("t", 0, "t")["inputs"]
    assert (entry["argument"], entry["columns"], entry["rows"]) == ("x", ["am"], [0, 2])


def test_a_recipe_costs_no_more_on_a_big_step():
    """Worked out from ids and the formula: no cell is read."""
    import time
    k = Kernel(Catalog(tools=[scale]))
    k["src"] = pd.DataFrame({"x": [float(i) for i in range(200_000)]})
    k["d"] = scale[mod.map()](wf["src"])
    k.run_all()
    wf_, row_id = k.workflow, k.workflow.steps["d"].output.data.index[150_000]
    wf_.recipe("d", row_id, "d")
    started = time.perf_counter()
    recipe = wf_.recipe("d", row_id, "d")
    assert time.perf_counter() - started < 0.05
    assert recipe["formula"] == 'scale(x=wf["src"][150000][cols["x"]])'
