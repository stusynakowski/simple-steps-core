"""group labels rows: their columns, plus a key (owner, 2026-10-27)."""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, Operation, mod, tool, wf


@tool
def patients_g() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Ben", "Cy", "Di"], "ward": ["A", "B", "A", "B"],
                         "temp_c": [36.6, 38.2, 37.1, 39.0]})


@tool
def band_g(temp_c: float) -> str:
    return "fever" if temp_c >= 38 else "normal"


@tool
def initial_g(name: str) -> str:
    return name[0]


@tool
def risky_g(temp_c: float) -> str:
    if temp_c > 38.5:
        raise ValueError("too hot")
    return "ok"


@pytest.fixture
def k():
    k = Kernel(Catalog(tools=[patients_g, band_g, initial_g, risky_g]))
    k["p"] = patients_g[mod.source()]()
    k.run("p")
    return k


def test_group_keeps_the_rows_and_columns_and_adds_the_key(k):
    k["g"] = band_g[mod.group()](wf["p"])
    k.run("g")
    data = k.step("g").data
    assert list(data.columns) == ["name", "ward", "temp_c", "group"]
    assert data["group"].tolist() == ["normal", "fever", "normal", "fever"]
    assert list(data.index) == list(k.step("p").data.index)        # same row ids


def test_the_key_is_named_with_name(k):
    k["g"] = band_g[mod.group(name="band")](wf["p"])
    k.run("g")
    assert list(k.step("g").data.columns) == ["name", "ward", "temp_c", "band"]


def test_collapse_follows_group_directly(k):
    k["g"] = band_g[mod.group(name="band")](wf["p"])
    k["per_band"] = Operation(tool="count")[mod.collapse(by="band")](wf["g"])
    k.run_all()
    assert k.step("per_band").data.to_dict("list") == {"band": ["normal", "fever"],
                                                        "value": [2, 2]}


def test_the_plan_before_running_is_the_inputs_columns_plus_the_key(k):
    k["g"] = band_g[mod.group(name="band")](wf["p"])
    columns = k.step("g").output.plan["columns"]
    assert columns["names"] == ["name", "ward", "temp_c", "band"]


def test_a_key_named_like_an_input_column_is_refused_unless_replace(k):
    k["g"] = band_g[mod.group(name="ward")](wf["p"])
    assert [p.code for p in k.step("g").problems] == ["column_clash"]
    k["g"] = band_g[mod.group(name="ward", replace=True)](wf["p"])
    k.run("g")
    data = k.step("g").data
    assert list(data.columns) == ["name", "ward", "temp_c"]
    assert data["ward"].tolist() == ["normal", "fever", "normal", "fever"]


def test_by_a_column_name_is_refused_and_points_to_collapse(k):
    k["g"] = band_g[mod.group(by="ward")](wf["p"])
    problem = k.step("g").problems[0]
    assert problem.code == "unknown_setting"
    assert problem.message.startswith("'ward' is already a column: collapse(by='ward')")


def test_by_a_tool_is_refused_the_steps_own_tool_is_the_key(k):
    k["g"] = band_g[mod.group(by=initial_g)](wf["p"])
    assert "write <key tool>[mod.group()]" in k.step("g").problems[0]
    k["g"] = initial_g[mod.group(name="initial")](wf["p"])
    k.run("g")
    assert k.step("g").data["initial"].tolist() == ["A", "B", "C", "D"]


def test_a_row_whose_key_failed_is_failed_and_keeps_its_columns(k):
    k["g"] = risky_g[mod.group(name="flag"), mod.try_except()](wf["p"])
    k.run("g")
    out = k.step("g").output
    assert list(out.data.columns) == ["name", "ward", "temp_c", "flag"]
    assert list(out.row_states) == ["known", "known", "known", "failed"]
    assert out.data.loc[3, "name"] == "Di"
