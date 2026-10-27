"""Row ids (K19, docs/design/row-ids.md): selections pick rows by id, and a
range picks positions."""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, cols, mod, rows, tool, wf
from simple_steps_core.catalog import formula_names
from simple_steps_core.errors import SelectionError


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


def test_a_row_is_picked_by_its_id_wherever_a_sort_put_it(k):
    k["first"] = wf["srt"][0]                      # row id 0 is Ada, now last
    k["pair"] = wf["srt"][[0, 2]]
    k.run_all()
    assert names(k, "first") == ["Ada"]
    assert names(k, "pair") == ["Ada", "Cy"]
    assert list(k.step("pair").data.index) == [0, 2]


def test_a_range_is_positions_the_top_rows(k):
    k["top2"] = wf["srt"][0:2]
    k["last"] = wf["srt"][-1:]
    k.run_all()
    assert names(k, "top2") == ["Ben", "Cy"]
    assert names(k, "last") == ["Ada"]


def test_a_string_row_id_goes_through_rows(k):
    k["e"] = visits_r[mod.expand()](wf["p"])
    k.run("e")
    k["one"] = wf["e"][rows["1.0"]]
    k["two"] = wf["e"][rows[["0.1", "2.0"]]]
    k.run_all()
    assert k.step("one").data["value"].tolist() == ["Ben-1"]
    assert k.step("two").data["value"].tolist() == ["Ada-2", "Cy-1"]
    with pytest.raises(SelectionError, match=r"goes through rows: wf\[…\]\[rows\['1.0'\]\]"):
        wf["e"]["1.0"]


def test_an_id_the_step_doesnt_have_is_a_problem(k):
    k["far"] = wf["srt"][9]
    problem = k.step("far").problems[0]
    assert problem.code == "bad_selection"
    assert "'srt' has no row 9 (its row ids are 1, 2, 0)" in problem


def test_a_negative_row_is_refused_with_the_range_to_use_instead():
    with pytest.raises(SelectionError, match=r"row ids aren't negative.*\[-1:\]"):
        wf["srt"][-1]


def test_a_cell_picked_by_id_as_an_argument_follows_its_row(k):
    # Ada's temperature, though a sort moved her row to the end.
    k["over_ada"] = above_r[mod.filter()](wf["p"], limit=wf["srt"][0][cols["temp_c"]])
    k.run("over_ada")
    assert names(k, "over_ada") == ["Ben", "Cy"]


@pytest.mark.parametrize("text", ['wf["e"][rows["1.0"]]', 'wf["e"][rows[["0.1", "2.0"]]]',
                                  'wf["srt"][[0, 2]]', 'wf["srt"][0:2]'])
def test_selections_by_id_print_and_read_back(k, text):
    k["e"] = visits_r[mod.expand()](wf["p"])
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


def test_a_list_parameter_still_gets_the_whole_column(kw):
    kw["s"] = sum_ws_r[mod.map()](wf["p"], ws=wf["weights"][cols["w"]])
    kw.run_all()
    assert kw.step("s").data["value"].tolist() == [60, 60, 60]


def test_a_row_the_column_has_no_value_for_is_blocked_with_the_reason(kw):
    kw["few"] = mod.slice(stop=2)(wf["wts"])                      # p's rows 0, 1: no row 2
    kw["s"] = scale_r[mod.map()](wf["p"], w=wf["few"][cols["w"]])
    kw.run_all()                                                  # doesn't stop the run
    out = kw.step("s").output
    assert out.data["value"].tolist()[:2] == [366.0, 764.0]
    assert list(out.row_states) == ["known", "known", "blocked"]
    assert out.notes[2]["cause"] == "w: 'few' has no row 2"


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
    k.run("side")
    assert k.step("side").state == "failed"
    assert "no matching row in 'renamed'" in str(k.step("side").output.notes)



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
    k["ben"] = wf["n"][rows["Ben"]]
    k.run_all()
    assert list(k.step("n").data.index) == ["Ada", "Ben"]
    assert list(k.step("n").data.columns) == ["temp_c"]          # no "index" column
    assert k.step("ben").data["temp_c"].tolist() == [38.2]


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


def test_a_groups_row_id_is_its_key(kc):
    assert list(kc.step("per_ward").data.index) == ["A", "B"]
    kc["b"] = wf["per_ward"][rows["B"]]
    kc.run("b")
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


def test_hash_is_the_row_id_not_the_row_number(k):
    """`#` is the row id (reshaping.md R-D11): after a sort it follows the rows."""
    from simple_steps_core import cols
    k["ids"] = wf["srt"][cols["#"]]
    k.run_all()
    assert k.step("ids").data["#"].tolist() == [1, 2, 0]           # Ben, Cy, Ada
    assert k.step("srt").output.view()["#"].tolist() == [1, 2, 0]
    assert [r["#"] for r in k.view("srt")["rows"]] == [1, 2, 0]
    assert [r["position"] for r in k.view("srt")["rows"]] == [0, 1, 2]
