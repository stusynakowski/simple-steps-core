"""Filling an absent cell, `first_present`; `map(where=…)`, removed; and a
single cell broadcasting like a literal (§3.1 rule 4)."""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, cols, join, mod, op, tool, wf


@tool
def patients_w() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ann", "Ben", "Cy"], "temp": [36.6, 38.2, 39.1]})


@tool
def config_w() -> pd.DataFrame:
    return pd.DataFrame({"limit": [38.0], "note": ["x"]})


@tool
def to_f_w(temp: float) -> float:
    return round(temp * 1.8 + 32, 2)


@tool
def is_hot_w(temp: float) -> bool:
    return temp > 38


@tool
def above_w(temp: float, limit: float) -> bool:
    return temp > limit


CAT = Catalog(tools=[patients_w, config_w, to_f_w, is_hot_w, above_w])


@pytest.fixture
def k():
    k = Kernel(CAT)
    k["p"] = patients_w[mod.source()]()
    return k


def test_map_takes_no_where(k):
    # EX4 (owner, 2026-11-03): a filter, then a join, says the same thing.
    k["f"] = to_f_w[mod.map(where=is_hot_w)](wf["p"])
    assert "map takes no parameter 'where'" in str(k.step("f").problems[0])


def test_first_present_fills_a_gap_and_keeps_a_none(k):
    # A left join leaves Cy's score absent; Ben's None is a value, kept.
    k["s"] = pd.DataFrame({"name": ["Ann", "Ben"], "score": [1.0, None]})
    k["j"] = join(wf["p"], wf["s"], on="name", how="left")
    k["v"] = mod.rename(columns={"score": "value"})(wf["j"])     # value binds by name
    k["out"] = op("first_present")[mod.map()](wf["v"], default=0.0)
    k.run_all()
    values = k.step("out").data["out"].tolist()
    assert values[0] == 1.0 and pd.isna(values[1]) and values[2] == 0.0


# ── a single cell broadcasts like a literal ─────────────────────────────
@pytest.mark.parametrize("limit", ["literal", "cell step", "cell of a table"])
def test_a_single_cell_is_the_same_in_every_call(k, limit):
    k["c"] = config_w[mod.source()]()
    k["lim"] = 38.0
    given = {"literal": 38.0, "cell step": wf["lim"],
             "cell of a table": wf["c"][0][cols["limit"]]}[limit]
    k["h"] = above_w[mod.map()](wf["p"], limit=given)
    k.run_all()
    assert k.step("h").data["h"].tolist() == [False, True, True]


def test_a_one_row_column_is_a_list_not_a_cell(k):
    """A column of another step is a list, even of one row: it pairs by row,
    so it is refused here. Its cell, [0], broadcasts."""
    k["c"] = config_w[mod.source()]()
    k["h"] = above_w[mod.map()](wf["p"], limit=wf["c"][cols["limit"]])
    assert "don't know how they match" in str(k.step("h").problems[0]) \
        or "aren't the rows" in str(k.step("h").problems[0])
