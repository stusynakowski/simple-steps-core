"""Row ids (K19, docs/design/row-ids.md): selections pick rows by id, and a
range picks positions."""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, cols, mod, rows, tool, wf
from simple_steps_core.catalog import formula_names
from simple_steps_core.errors import SelectionError
from simple_steps_core.operation import op


@tool
def patients_r() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "temp_c": [36.6, 38.2, 37.1]})


@tool
def visits_r(name: str) -> list:
    return [f"{name}-1", f"{name}-2"]


@tool
def above_r(temp_c: float, limit: float) -> bool:
    return temp_c > limit


@pytest.fixture
def k():
    k = Kernel(Catalog(tools=[patients_r, visits_r, above_r]))
    k["p"] = patients_r[mod.source()]()
    k["srt"] = mod.sort(by="temp_c", ascending=False)(wf["p"])   # Ben, Cy, Ada
    k.run_all()
    return k


def names(k, step):
    return k.step(step).data["name"].tolist()


def test_a_row_is_picked_by_its_number_and_saved_as_its_lineage(k):
    """S5d (CA-B1): a typed row number is the row shown there; staging saves
    its lineage, so the pick follows the row."""
    k["first"] = wf["srt"][0]                      # Ben, shown first
    k["pair"] = wf["srt"][[0, 2]]                  # Ben and Ada
    k.run_all()
    assert names(k, "first") == ["Ben"]
    assert names(k, "pair") == ["Ben", "Ada"]
    assert k.step("first").formula == 'wf["srt"][rows[row["p"] == 1]]'
    assert k.step("pair").formula == 'wf["srt"][rows[(row["p"] == 1) | (row["p"] == 0)]]'


def test_a_range_is_positions_the_top_rows(k):
    k["top2"] = wf["srt"][0:2]
    k["last"] = wf["srt"][-1:]
    k.run_all()
    assert names(k, "top2") == ["Ben", "Cy"]
    assert names(k, "last") == ["Ada"]
    assert k.step("top2").formula == 'wf["srt"][0:2]'      # a range stays a range (S5-D2)


def test_a_text_row_id_is_refused_with_the_number_to_use(k):
    k["e"] = visits_r[mod.expand()](wf["p"])
    k.run("e")
    for make in (lambda: wf["e"][rows["1.0"]], lambda: wf["e"]["1.0"]):
        with pytest.raises(SelectionError, match="row numbers, as shown in #"):
            make()


def test_a_row_the_step_doesnt_have_is_a_problem(k):
    k["far"] = wf["srt"][9]
    problem = k.step("far").problems[0]
    assert problem.code == "bad_selection"
    assert "'srt' has no row 9 (it has 3: 0–2)" in problem


def test_minus_one_is_the_last_row(k):
    k["last"] = wf["srt"][-1]
    k.run_all()
    assert names(k, "last") == ["Ada"]


def test_a_cell_picked_for_an_argument_follows_its_row(k):
    # Ada's temperature: shown at row 2, saved as her lineage.
    k["over_ada"] = above_r[mod.filter()](wf["p"], limit=wf["srt"][2][cols["temp_c"]])
    k.run("over_ada")
    assert names(k, "over_ada") == ["Ben", "Cy"]
    assert 'row["p"] == 0' in k.step("over_ada").formula


@pytest.mark.parametrize("text", ['wf["srt"][0:2]', 'wf["srt"][rows[row["p"] == 1]]',
                                  'wf["e"][rows[(row["p"] == 1) & (row["p"].idx == 0)]]',
                                  'wf["srt"][cols["temp_c"] > 37.0]'])
def test_saved_picks_print_and_read_back(k, text):
    k["e"] = visits_r[mod.expand()](wf["p"])
    k.run("e")
    names_ = formula_names(k.catalog.functions)
    k["s"] = eval(text, {"__builtins__": {}}, names_)
    assert k.step("s").formula == text


# ── a column as an argument pairs row by row, by id (K19 part 2) ─────────
@tool
def scale_r(temp_c: float, w: float = 1) -> float:
    return round(temp_c * w, 1)


@tool
def scale_untyped_r(temp_c, w=1):
    return round(temp_c * w, 1)


@tool
def sum_ws_r(temp_c: float, ws: list) -> float:
    return sum(ws)


@tool
def weight_r(name: str) -> int:
    return {"Ada": 10, "Ben": 20, "Cy": 30}[name]


@pytest.fixture
def kw():
    k = Kernel(Catalog(tools=[patients_r, scale_r, scale_untyped_r, sum_ws_r, weight_r]))
    k["p"] = patients_r[mod.source()]()
    k["weights"] = pd.DataFrame({"w": [10, 20, 30]})              # unrelated to p
    k["wts"] = weight_r[mod.map(), mod.name("w")](wf["p"])         # p's rows: Ada 10, Ben 20, Cy 30
    k["warm"] = mod.sort(by="temp_c", ascending=False)(wf["p"])   # ids 1, 2, 0
    return k


@pytest.mark.parametrize("tool_", [scale_r, scale_untyped_r])
def test_a_column_pairs_with_the_rows_that_share_its_ids(kw, tool_):
    """Within one origin a column argument pairs by id, wherever a sort put the
    rows; from an unrelated step it is refused (R-D7, reshaping.md §6)."""
    kw["s"] = tool_[mod.map()](wf["warm"], w=wf["wts"][cols["w"]])
    assert kw.step("s").problems == ()
    kw.run_all()
    # Ben (id 1) x 20, Cy (id 2) x 30, Ada (id 0) x 10, in the sorted order.
    assert kw.step("s").data["value"].tolist() == [764.0, 1113.0, 366.0]
    assert list(kw.step("s").data.index) == [1, 2, 0]
    kw["u"] = tool_[mod.map()](wf["warm"], w=wf["weights"][cols["w"]])
    assert [p.code for p in kw.step("u").problems] == ["unmatched_rows"]
    assert "match_ids=True" in kw.step("u").problems[0]


def test_a_list_parameter_gets_the_whole_column_as_one_cell(kw):
    """CA-D1: under map a column passes each row's cell, whatever the type; a
    column of unrelated rows is refused. The whole column is one gathered cell."""
    kw["s"] = sum_ws_r[mod.map()](wf["p"], ws=wf["weights"][cols["w"]])
    assert [p.code for p in kw.step("s").problems] == ["unmatched_rows"]
    kw["all"] = op("gather")[mod.collapse()](wf["weights"])
    kw["s2"] = sum_ws_r[mod.map()](wf["p"], ws=wf["all"])
    kw.run_all()
    assert kw.step("s2").data["value"].tolist() == [60, 60, 60]


def test_a_column_that_leaves_a_row_without_a_value_is_refused(kw):
    """L1: few has p's rows 0 and 1, not 2; pairing would leave row 2 with no
    value, so it's refused when declared, pointing to a join."""
    kw["few"] = mod.slice(stop=2)(wf["wts"])
    kw["s"] = scale_r[mod.map()](wf["p"], w=wf["few"][cols["w"]])
    assert [p.code for p in kw.step("s").problems] == ["bad_pairing"]
    assert "join" in str(kw.step("s").problems[0])


def test_under_a_whole_table_verb_a_column_stays_whole():
    @tool
    def tally_r(rows: pd.DataFrame, w: float) -> pd.DataFrame:
        return rows
    k = Kernel(Catalog(tools=[patients_r, tally_r]))
    k["p"] = patients_r[mod.source()]()
    k["weights"] = pd.DataFrame({"w": [10, 20, 30]})
    k["t"] = tally_r[mod.table()](wf["p"], w=wf["weights"][cols["w"]])
    assert [p.code for p in k.step("t").problems] == ["wrong_shape"]


# ── zip_ pairs by id (K19 part 3) ────────────────────────────────────────
# A grid that shares no row ids with another is refused, never paired by
# position: tested with the ids new rows get (part 4), since until then every
# source counts its rows from 0.


def test_zip_pairs_by_id_after_one_side_was_sorted(k):
    from simple_steps_core import zip_
    k["t"] = mod.select(columns=["temp_c"])(wf["srt"])                  # ids 1, 2, 0
    k["renamed"] = mod.rename(columns={"temp_c": "t"})(wf["t"])
    k["side"] = zip_(wf["p"], wf["renamed"])
    k.run_all()
    data = k.step("side").data
    assert (data["temp_c"] == data["t"]).all()                          # each row with its own
    assert list(data.index) == [0, 1, 2]


def test_zip_refuses_rows_one_side_doesnt_have(k):
    from simple_steps_core import zip_
    k["hot"] = mod.slice(start=0, stop=2)(wf["srt"])                  # ids 1, 2
    k["renamed"] = mod.rename(columns={"name": "who", "temp_c": "t"})(wf["hot"])
    k["side"] = zip_(wf["p"], wf["renamed"])
    k.run_all()
    assert k.step("side").state == "invalid"          # L2: refused once both have run
    assert "Use join" in str(k.step("side").problems[0])



# ── the ids new rows get (K19 part 4) ────────────────────────────────────
@tool
def by_name_r() -> pd.DataFrame:
    return pd.DataFrame({"temp_c": [36.6, 38.2]}, index=["Ada", "Ben"])


@tool
def add_temp_r(acc: float, temp_c: float) -> float:
    return (acc or 0) + temp_c


def test_a_source_tools_own_index_is_its_row_ids():
    k = Kernel(Catalog(tools=[by_name_r]))
    k["n"] = by_name_r[mod.source()]()
    k.run_all()
    k["ben"] = wf["n"][1]                          # a source's row stays a row number
    k.run_all()
    assert list(k.step("n").data.index) == ["Ada", "Ben"]       # core's ids (S5-D5)
    assert list(k.step("n").data.columns) == ["temp_c"]          # no "index" column
    assert k.step("ben").data["temp_c"].tolist() == [38.2]
    assert k.step("ben").formula == 'wf["n"][1]'


@tool
def notes_r() -> pd.DataFrame:
    return pd.DataFrame({"note": ["x", "y", "z"]}, index=["Ada", "Ben", "Cy"])


def test_zip_refuses_grids_that_share_no_row_ids_rather_than_pair_by_position():
    from simple_steps_core import zip_
    k = Kernel(Catalog(tools=[patients_r, notes_r]))
    k["p"] = patients_r[mod.source()]()                          # ids 0, 1, 2
    k["n"] = notes_r[mod.source()]()                             # ids Ada, Ben, Cy: same length
    k["side"] = zip_(wf["p"], wf["n"])                            # unrelated: refused when declared
    assert k.step("side").state == "invalid"
    assert "join(p, n" in k.step("side").problems[0]
    k["vouched"] = zip_(wf["p"], wf["n"], match_ids=True)         # vouched, but the ids differ
    from simple_steps_core.errors import StepFailed
    with pytest.raises(StepFailed, match="share none"):
        k.run_all()
    assert "Use join" in str(k.step("vouched").output.notes)


BASE = {"name": ["Ada", "Ben", "Cy", "Di"], "ward": ["A", "B", "A", "B"],
        "temp_c": [36.6, 38.2, 37.1, 39.0]}


@pytest.fixture
def kc():
    k = Kernel(Catalog(tools=[add_temp_r]))
    k["p"] = pd.DataFrame(BASE)
    k["per_ward"] = add_temp_r[mod.collapse(by="ward")](wf["p"])
    k.run_all()
    return k


def test_a_group_is_picked_by_its_key(kc):
    assert list(kc.step("per_ward").data.index) == ["A", "B"]   # core's ids (S5-D5)
    kc["b"] = wf["per_ward"][1]
    kc.run("b")
    assert kc.step("b").formula == 'wf["per_ward"][rows[cols["ward"] == "B"]]'
    assert kc.step("b").data.to_dict("list") == {"#p": [[1, 3]], "ward": ["B"], "value": [77.2]}


def test_a_change_to_one_row_makes_only_its_group_stale(kc):
    kc["p"] = pd.DataFrame({**BASE, "temp_c": [36.6, 40.0, 37.1, 39.0]})   # Ben, ward B
    assert kc.needs_run()["per_ward"] == "stale: input p changed"
    assert kc.workflow.stale_rows("per_ward") == ["B"]


def test_a_row_moving_group_makes_both_groups_stale(kc):
    kc["p"] = pd.DataFrame({**BASE, "ward": ["A", "A", "A", "B"]})          # Ben: B -> A
    assert kc.workflow.stale_rows("per_ward") == ["A", "B"]


def test_a_new_group_makes_the_whole_step_stale(kc):
    kc["p"] = pd.DataFrame({**BASE, "ward": ["A", "B", "C", "B"]})          # Cy: a new ward
    assert kc.step("per_ward").state == "stale"
    assert kc.workflow.stale_rows("per_ward") is None


def test_the_view_shows_row_numbers_and_lineage_not_row_ids(k):
    """S5a (CA-B1): `#` in the view is the row number; where a row came from
    is its lineage, the parent's row number. Core's ids stay in `.data`."""
    assert k.step("srt").data.index.tolist() == [1, 2, 0]         # core's ids (S5-D5)
    assert [r["#"] for r in k.view("srt")["rows"]] == [0, 1, 2]
    assert [r["lineage"]["#p"] for r in k.view("srt")["rows"]] == [1, 2, 0]   # Ben, Cy, Ada
