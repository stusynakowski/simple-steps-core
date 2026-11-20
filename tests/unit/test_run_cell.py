"""Running one staged cell in place (P7r; owner, 2026-11-20): "click on that
staged cell, run it … we would see that cell populated but everything else
would be staged"; and its recipe follows updates to the reference data.
"""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, tool, wf


@tool
def scale(x: float, by: float = 2.0) -> float:
    return x * by


@tool
def add(x: float, y: float) -> float:
    return x + y


@tool
def big(x: float) -> bool:
    return x > 1


@tool
def picky(x: float) -> float:
    if x == 2.0:
        raise ValueError("two is not allowed")
    return x


def kernel() -> Kernel:
    k = Kernel(Catalog(tools=[scale, add, big, picky]))
    k["src"] = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [10.0, 20.0, 30.0]})
    k["s"] = scale[mod.map()](wf["src"], by=3.0)
    k["p"] = add[mod.map()](wf["src"]["x"], y=wf["src"]["y"])
    k.run("src")
    return k


def _shown(k: Kernel, name: str, column: str | None = None) -> list:
    column = column or name
    return [(r["state"], r["cells"][column].get("value")) for r in k.view(name)["rows"]]


def test_one_cell_runs_and_the_rest_stay_staged():
    k = kernel()
    row = k.run_cell("s", 1)
    assert row["cells"]["s"] == {"state": "known", "type": "float", "value": 6.0}
    assert _shown(k, "s") == [("pending", None), ("known", 6.0), ("pending", None)]
    assert k.workflow.steps["s"].state == "staged"
    assert k.needs_run() == {"s": "staged", "p": "staged"}
    assert {x: k.cell("s", 1, "s")[x] for x in ("state", "value")} == {"state": "known", "value": 6.0}


def test_a_paired_argument_is_read_at_the_same_row():
    k = kernel()
    assert k.run_cell("p", 2)["cells"]["p"]["value"] == 33.0


def test_a_cell_keeps_to_its_row_when_rows_are_added_above():
    k = kernel()
    k.run_cell("s", 1)                                     # x = 2.0
    k["src"] = pd.DataFrame({"x": [0.5, 1.0, 2.0, 3.0], "y": [5.0, 10.0, 20.0, 30.0]})
    k.run("src")
    assert _shown(k, "s") == [("pending", None), ("pending", None),
                              ("known", 6.0), ("pending", None)]
    # the recipe follows it too: its row is #2 now
    assert k.cell("s", 2, "s")["recipe"]["formula"] == 'scale(x=wf["src"][2]["x"], by=3.0)'


def test_a_cell_whose_row_is_removed_is_gone():
    k = kernel()
    k.run_cell("s", 1)
    k["src"] = pd.DataFrame({"x": [1.0, 3.0], "y": [10.0, 30.0]})
    k.run("src")
    assert [state for state, _ in _shown(k, "s")] == ["pending", "pending"]


def test_a_cell_goes_stale_when_what_it_read_changes():
    k = kernel()
    k.run_cell("s", 1)
    k["src"] = pd.DataFrame({"x": [1.0, 9.0, 3.0], "y": [10.0, 20.0, 30.0]})
    k.run("src")
    cell = k.cell("s", 1, "s")
    assert (cell["state"], cell["value"]) == ("stale", 6.0)
    assert "changed" in cell["because"]


def test_a_change_to_a_column_it_doesnt_read_leaves_it_known():
    k = kernel()
    k.run_cell("s", 1)                                     # reads x, not y
    k["src"] = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [10.0, 99.0, 30.0]})
    k.run("src")
    assert k.cell("s", 1, "s")["state"] == "known"


def test_editing_the_formula_drops_it_and_a_full_run_replaces_it():
    k = kernel()
    k.run_cell("s", 1)
    k["s"] = scale[mod.map()](wf["src"], by=4.0)
    assert [state for state, _ in _shown(k, "s")] == ["pending"] * 3
    k.run_cell("s", 0)
    k.run("s")
    assert _shown(k, "s") == [("known", 4.0), ("known", 8.0), ("known", 12.0)]
    assert k.workflow.steps["s"].cells_run == {}


def test_a_failing_cell_fails_with_its_reason():
    k = kernel()
    k["f"] = picky[mod.map()](wf["src"])
    row = k.run_cell("f", 1)
    assert row["cells"]["f"]["state"] == "failed"
    assert "two is not allowed" in row["cells"]["f"]["error"]
    assert k.workflow.steps["f"].state == "staged"


def test_run_cell_says_what_it_cant_do():
    k = kernel()
    k["only"] = big[mod.filter()](wf["src"])
    with pytest.raises(ValueError, match="run in place on a map"):
        k.run_cell("only", 0)
    k.run("s")
    with pytest.raises(ValueError, match="has run"):
        k.run_cell("s", 0)
    with pytest.raises(IndexError, match="which has 3 rows"):
        k.run_cell("p", 7)
    k2 = Kernel(Catalog(tools=[scale]))
    k2["src"] = pd.DataFrame({"x": [1.0]})
    k2["a"] = scale[mod.map()](wf["src"])
    k2["b"] = scale[mod.map()](wf["a"])
    with pytest.raises(ValueError, match="has not run"):
        k2.run_cell("b", 0)


def test_run_cell_tells_listeners():
    k = kernel()
    heard = []
    k.on_change(heard.append)
    k.run_cell("s", 0)
    assert heard and heard[-1]["action"] == "run_cell" and "s" in heard[-1]["changed"]


def test_a_saved_session_keeps_its_cells_run_in_place(tmp_path):
    k = kernel()
    k.run_cell("s", 1)
    report = k.save(tmp_path / "session", outputs=True)
    assert report["steps"]["s"]["cells_run"] == {"file": "data/s/cells.json"}
    back = Kernel.load(tmp_path / "session", k.workflow.catalog)
    assert _shown(back, "s") == [("pending", None), ("known", 6.0), ("pending", None)]
    # and saving again after a full run removes the file
    k.run("s")
    k.save(tmp_path / "session", outputs=True)
    assert not (tmp_path / "session" / "data" / "s" / "cells.json").exists()
