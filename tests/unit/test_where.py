"""Applying a tool on a condition, `map(where=…)`, and its "else",
`first_present` (docs/design/syntax-review.md); and a single cell
broadcasting like a literal (§3.1 rule 4)."""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, cols, mod, op, tool, wf


@tool
def patients_w() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ann", "Ben", "Cy"], "temp": [36.6, 38.2, 39.1]})


@tool
def config_w() -> pd.DataFrame:
    return pd.DataFrame({"limit": [38.0], "note": ["x"]})


@tool
def is_hot_w(temp: float) -> bool:
    return temp > 38


@tool
def label_w(temp: float) -> str:
    return "hot" if temp > 38 else "ok"


@tool
def nothing_w(temp: float) -> float | None:
    return None


@tool
def to_f_w(temp: float) -> float:
    return round(temp * 1.8 + 32, 2)


@tool
def above_w(temp: float, limit: float) -> bool:
    return temp > limit


@tool
def shaky_w(temp: float) -> bool:
    if temp > 39:
        raise ValueError("too hot to test")
    return temp > 38


CAT = Catalog(tools=[patients_w, config_w, is_hot_w, label_w, nothing_w, to_f_w,
                     above_w, shaky_w])


@pytest.fixture
def k():
    k = Kernel(CAT)
    k["p"] = patients_w[mod.source()]()
    return k


def test_where_runs_the_tool_only_where_the_test_holds(k):
    k["f"] = to_f_w[mod.map(where=is_hot_w)](wf["p"])
    k.run_all()
    out = k.step("f").output
    assert k.step("f").data["value"].tolist()[1:] == [100.76, 102.38]
    assert out.absent_cells() == {(0, "value")}            # Ann: not run, so absent
    assert list(k.step("f").data.index) == [0, 1, 2]       # every row kept, aligned with p


def test_the_skipped_rows_are_absent_not_none(k):
    k["f"] = to_f_w[mod.map(where=is_hot_w)](wf["p"])
    k.run_all()
    cells = [r["cells"]["value"]["state"] for r in k.view("f")["rows"]]
    assert cells == ["absent", "known", "known"]


def test_else_fills_only_the_skipped_rows(k):
    k["f"] = to_f_w[mod.map(where=is_hot_w)](wf["p"])
    k["out"] = op("first_present")[mod.map()](wf["f"], default=wf["p"][cols["temp"]])
    k.run_all()
    assert k.step("out").data["value"].tolist() == [36.6, 100.76, 102.38]


def test_else_keeps_a_none_the_tool_returned(k):
    k["n"] = nothing_w[mod.map(where=is_hot_w)](wf["p"])
    k["out"] = op("first_present")[mod.map()](wf["n"], default=wf["p"][cols["temp"]])
    k.run_all()
    values = k.step("out").data["value"].tolist()
    assert values[0] == 36.6                               # absent: filled
    assert all(pd.isna(v) for v in values[1:])             # None: a value, kept


def test_where_saves_reloads_and_prints_as_written(k):
    k["f"] = to_f_w[mod.map(where=is_hot_w)](wf["p"])
    assert k.step("f").formula == 'to_f_w[mod.map(where=is_hot_w)](wf["p"])'
    loaded = Kernel.from_json(k.to_json(), CAT)
    assert loaded.spec == k.spec and loaded.step("f").formula == k.step("f").formula


def test_where_takes_only_a_test(k):
    k["a"] = to_f_w[mod.map(where=label_w)](wf["p"])
    assert "returning bool" in str(k.step("a").problems[0])
    k["b"] = to_f_w[mod.map(where=38)](wf["p"])
    assert "takes a tool that returns bool" in str(k.step("b").problems[0])


def test_a_test_that_raises_fails_its_row_and_says_where(k):
    """Like any failure nothing catches, it stops the run; the note says the
    test failed (`where: where`), not the tool. The other rows ran."""
    from simple_steps_core import StepFailed
    k["f"] = to_f_w[mod.map(where=shaky_w)](wf["p"])
    with pytest.raises(StepFailed, match="where: ValueError: too hot to test"):
        k.run_all()
    notes = k.step("f").output.notes
    assert notes[2]["where"] == "where"
    assert k.step("f").data["value"].tolist()[1] == 100.76


def test_a_change_to_a_column_the_test_reads_makes_the_step_stale():
    k = Kernel(CAT)
    k["raw"] = [{"name": "Ann", "temp": 36.6}, {"name": "Ben", "temp": 38.2}]
    k["e"] = mod.expand()(wf["raw"])
    k["p"] = mod.widen()(wf["e"])
    k["f"] = to_f_w[mod.map(where=is_hot_w)](wf["p"])
    k.run_all()
    k["raw"] = [{"name": "Ann", "temp": 38.6}, {"name": "Ben", "temp": 38.2}]
    k.run("e"), k.run("p")
    assert k.workflow.stale_rows("f") == ["0.0"]           # Ann now passes the test


# ── a single cell broadcasts like a literal ─────────────────────────────
@pytest.mark.parametrize("limit", ["literal", "cell step", "cell of a table"])
def test_a_single_cell_is_the_same_in_every_call(k, limit):
    k["c"] = config_w[mod.source()]()
    k["lim"] = 38.0
    given = {"literal": 38.0, "cell step": wf["lim"],
             "cell of a table": wf["c"][0][cols["limit"]]}[limit]
    k["h"] = above_w[mod.map()](wf["p"], limit=given)
    k.run_all()
    assert k.step("h").data["value"].tolist() == [False, True, True]


def test_a_one_row_column_is_a_list_not_a_cell(k):
    """A column of another step is a list, even of one row: it pairs by row,
    so it is refused here. Its cell, [0], broadcasts."""
    k["c"] = config_w[mod.source()]()
    k["h"] = above_w[mod.map()](wf["p"], limit=wf["c"][cols["limit"]])
    assert "don't know how they match" in str(k.step("h").problems[0]) \
        or "aren't the rows" in str(k.step("h").problems[0])
