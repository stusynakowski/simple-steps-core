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
from simple_steps_core.errors import StepFailed
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
    ("s", 1, "s", 'scale(x=wf["f"][1]["x"], by=3.0)'),
    ("p", 2, "p", 'add(x=wf["src"][2]["x"], y=wf["src"][2]["y"])'),
    # a collapse: the column, over the group's rows
    ("t", 0, "t", 'sumup(x=wf["src"][[0, 2]]["x"])'),
    ("t", 1, "t", 'sumup(x=wf["src"][[1]]["x"])'),
    # several outputs: the call, then the part the cell holds
    ("e", 3, "e", 'split(x=wf["src"][1]["x"])[1]'),
    ("ch", 2, "g", 'channels(x=wf["src"][2]["x"])["g"]'),
    ("c", 2, "c", 'rgb(x=wf["src"][2]["x"])'),
    # a copied cell is its pick
    ("cp", 1, "x", 'wf["f"][1]["x"]'),
    ("f", 0, "y", 'wf["src"][1]["y"]'),
    ("t", 0, "g", 'wf["src"][[0, 2]]["g"]'),
])
def test_a_cells_formula_is_its_call(name, row, column, text):
    k = kernel()
    k.run_all()
    assert k.cell(name, row, column)["recipe"]["formula"] == text


def test_a_filters_cell_says_what_kept_it():
    k = kernel()
    k.run_all()
    recipe = k.cell("f", 0, "y")["recipe"]
    assert recipe["kept_by"] == 'big(x=wf["src"][1]["x"])'
    assert recipe["as_step"] == 'big[mod.filter()](wf["src"][1])'


def test_a_group_that_runs_on_is_a_range():
    k = Kernel(Catalog(tools=[sumup]))
    k["v"] = pd.DataFrame({"g": ["a", "a", "a", "b"], "x": [1.0, 2.0, 3.0, 4.0],
                           "am": [5.0, 6.0, 7.0, 8.0]})
    k["t"] = sumup[mod.collapse(by="g")](wf["v"], x=wf["v"]["am"])
    k.run_all()
    cell = k.cell("t", 0, "t")
    assert cell["value"] == 18.0
    assert cell["recipe"]["formula"] == 'sumup(x=wf["v"][0:3]["am"])'
    assert cell["recipe"]["of"] == "rows"


def test_a_binding_core_wrote_by_type_shows_its_cell():
    k = Kernel(Catalog(tools=[scale]))
    k["src"] = pd.DataFrame({"temp": [1.0, 2.0]})
    k["s"] = scale[mod.map()](wf["src"]["temp"])
    k.run_all()
    assert k.cell("s", 1, "s")["recipe"]["formula"] == 'scale(x=wf["src"][1]["temp"])'


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
    assert k.cell("s", 0, "s")["recipe"]["formula"] == 'scale(x=wf["f"][0]["x"], by=3.0)'
    assert k.cell("f", 0, "x")["recipe"]["formula"] == 'wf["src"][1]["x"]'


def test_a_staged_cell_knows_its_recipe():
    k = kernel()                                    # nothing run
    assert k.cell("c", 1, "c")["recipe"]["formula"] == 'rgb(x=wf["src"][1]["x"])'


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
    assert recipe["formula"] == 'scale(x=wf["src"][150000]["x"])'


# ── 015 C55: the by-value form, the call on the values it read ─────────────
@pytest.mark.parametrize("name, row, column, text", [
    ("s", 1, "s", "scale(x=3.0, by=3.0)"),
    ("p", 2, "p", "add(x=3.0, y=30.0)"),
    ("t", 0, "t", "sumup(x=[1.0, 3.0])"),
    ("e", 3, "e", "split(x=2.0)[1]"),
    ("ch", 2, "g", 'channels(x=3.0)["g"]'),
    ("c", 2, "c", "rgb(x=3.0)"),
    # a copied cell is its value
    ("cp", 1, "x", "3.0"),
    ("f", 0, "y", "20.0"),
    ("t", 0, "g", '"a"'),
])
def test_a_cells_by_value_is_its_call_on_the_values(name, row, column, text):
    k = kernel()
    k.run_all()
    assert k.cell(name, row, column)["recipe"]["by_value"] == text


@pytest.mark.parametrize("name", ["s", "p", "t", "e", "c", "ch", "cp", "f"])
def test_every_by_value_evaluates_to_its_cell(name):
    """First, middle and last row, every column a tool made or copied."""
    k = kernel()
    k.run_all()
    tools = {t.__name__: t for t in (scale, big, add, sumup, split, rgb)}
    # a record's field is written ["g"] (owner, 2026-11-20); read it by name
    tools["channels"] = lambda **kw: channels(**kw)._asdict()
    view = k.view(name)
    for r in sorted({0, len(view["rows"]) // 2, len(view["rows"]) - 1}):
        for column, shown in view["rows"][r]["cells"].items():
            cell = k.cell(name, r, column)
            got = eval(cell["recipe"]["by_value"], dict(tools))
            assert (list(got) if isinstance(got, tuple) else got) == \
                (list(cell["value"]) if isinstance(cell["value"], tuple) else cell["value"])


def test_a_failed_rows_by_value_is_what_it_ran_on():
    @tool
    def inverse(x: float) -> float:
        return 1 / x
    k = Kernel(Catalog(tools=[inverse]))
    k["src"] = pd.DataFrame({"x": [2.0, 0.0]})
    k["i"] = inverse[mod.map()](wf["src"])
    with pytest.raises(StepFailed):
        k.run_all()
    cell = k.cell("i", 1, "i")
    assert cell["state"] == "failed"
    assert cell["recipe"]["by_value"] == "inverse(x=0.0)"
    with pytest.raises(ZeroDivisionError):
        eval(cell["recipe"]["by_value"], {"inverse": inverse})


def test_a_staged_cell_on_known_inputs_has_one():
    k = kernel()
    k.run("src")
    assert k.cell("c", 1, "c")["recipe"]["by_value"] == "rgb(x=2.0)"


def test_a_cell_whose_inputs_are_pending_says_why_it_has_none():
    k = kernel()
    k["src2"] = scale[mod.map()](wf["src"]["x"])
    k["w"] = add[mod.map()](wf["src"]["x"], y=wf["src2"]["src2"])   # src2 not run
    k.run("src")
    recipe = k.cell("w", 0, "w")["recipe"]
    assert "by_value" not in recipe
    assert "src2" in recipe["by_value_because"]


def test_a_stale_cell_says_it_ran_on_earlier_values():
    k = kernel()
    k.run_all()
    k["src"] = pd.DataFrame({"g": ["a", "b", "a"], "x": [1.0, 2.0, 9.0], "y": [10.0, 20.0, 30.0]})
    recipe = k.cell("c", 2, "c")["recipe"]
    assert "by_value" not in recipe
    assert "earlier" in recipe["by_value_because"]


def test_a_value_with_no_literal_form_says_so():
    import numpy as np

    @tool
    def msum(m: np.ndarray) -> float:
        return float(m.sum())
    k = Kernel(Catalog(tools=[msum]))
    k["src"] = pd.DataFrame({"m": [np.ones(2), np.zeros(2)]})
    k["t"] = msum[mod.map()](wf["src"])
    k.run_all()
    recipe = k.cell("t", 0, "t")["recipe"]
    assert recipe["formula"] == 'msum(m=wf["src"][0]["m"])'
    assert "by_value" not in recipe
    assert "ndarray" in recipe["by_value_because"]


def test_data_has_no_by_value():
    k = kernel()
    k.run_all()
    assert "by_value" not in k.cell("src", 0, "x")["recipe"]
