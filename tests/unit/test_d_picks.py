"""D-picks: a saved pick follows its row when its source's data is replaced.

A pick names a row of the data as it is when written. When the source is
given new data, core matches the rows it has seen by their values, keeps their
ids, and rewrites each row number a step names to that row's number now. A row
that is gone makes the step ``invalid``, naming it (decisions.md §0, D-picks).
"""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, row, rows, wf


def people(*names):
    temps = {"Zed": 35.0, "Al": 36.0, "Ben": 39.0, "Cy": 37.0, "Di": 38.0}
    return pd.DataFrame({"name": list(names), "temp": [temps[n] for n in names]})


@pytest.fixture
def k():
    k = Kernel(Catalog(tools=[]))
    k["p"] = people("Al", "Ben", "Cy")
    k["one"] = wf["p"][1]                                # Ben
    k["s"] = mod.sort(by="temp")(wf["p"])                # Al, Cy, Ben
    k.run_all()
    k["two"] = wf["s"][0]                                # Al: saved as row["p"] == 0
    k.run_all()
    return k


def names(k, step):
    return k.step(step).data["name"].tolist()


def test_a_row_inserted_above_a_pick_moves_its_number(k):
    k["p"] = people("Zed", "Al", "Ben", "Cy")
    assert k.step("one").formula == 'wf["p"][2]'
    assert k.step("two").formula == 'wf["s"][rows[row["p"] == 1]]'
    k.run_all()
    assert names(k, "one") == ["Ben"] and names(k, "two") == ["Al"]


def test_a_pick_whose_row_is_deleted_is_invalid_naming_it(k):
    k["p"] = people("Al", "Cy")
    one = k.step("one")
    assert one.state == "invalid"
    assert [p.code for p in one.problems] == ["row_gone"]
    assert "'p' row 1 is gone (it was name='Ben', temp=39.0)" in one.problems[0]
    assert names(k, "one") == ["Ben"]                    # its last result, still shown
    assert k.step("two").state != "invalid"              # Al is still there


def test_the_row_given_back_brings_the_pick_back(k):
    k["p"] = people("Al", "Cy")
    k["p"] = people("Cy", "Al", "Ben")                   # Ben back, elsewhere
    assert k.step("one").problems == ()
    assert k.step("one").formula == 'wf["p"][2]'
    k.run_all()
    assert names(k, "one") == ["Ben"]


def test_data_put_back_is_completed_with_no_rerun(k):
    held = k.step("one").output
    k["p"] = people("Al", "Cy")
    k["p"] = people("Al", "Ben", "Cy")
    assert k.step("one").state == "completed"
    assert k.step("one").output is held                  # undo is free (L40d)


def test_a_value_edited_in_place_keeps_its_row(k):
    k["p"] = pd.DataFrame({"name": ["Al", "Ben", "Cy"], "temp": [36.0, 40.0, 37.0]})
    assert k.step("one").formula == 'wf["p"][1]' and k.step("one").problems == ()
    k.run_all()
    assert k.step("one").data["temp"].tolist() == [40.0]  # core-asks L41a


def test_a_new_pick_clears_a_gone_one(k):
    k["p"] = people("Al", "Cy")
    k["one"] = wf["p"][1]                                # Cy, written on the data now
    assert k.step("one").problems == ()
    k.run_all()
    assert names(k, "one") == ["Cy"]


def test_a_position_from_the_end_stays_a_position():
    k = Kernel(Catalog(tools=[]))
    k["p"] = people("Al", "Ben", "Cy")
    k["last"] = wf["p"][-1]
    k.run_all()
    k["p"] = people("Al", "Ben", "Cy", "Di")
    assert k.step("last").formula == 'wf["p"][-1]'
    k.run_all()
    assert names(k, "last") == ["Di"]


def test_an_index_of_its_own_is_left_as_the_users_identity():
    k = Kernel(Catalog(tools=[]))
    k["p"] = people("Al", "Ben").set_axis(["a", "b"])
    k["p"] = people("Zed", "Al", "Ben").set_axis(["z", "a", "b"])
    assert list(k.step("p").data.index) == ["z", "a", "b"]


def test_a_deleted_rows_id_is_never_given_again():
    k = Kernel(Catalog(tools=[]))
    k["p"] = people("Al", "Ben", "Cy")
    k["p"] = people("Al", "Ben")                         # Cy's id 2 goes
    k["p"] = people("Al", "Ben", "Di")                   # Di is new: not id 2
    assert list(k.step("p").data.index) == [0, 1, 3]


def test_a_renamed_step_keeps_its_gone_pick(k):
    k["p"] = people("Al", "Cy")
    k.rename("one", "uno")
    assert [p.code for p in k.step("uno").problems] == ["row_gone"]


def _loaded():
    """A source whose tool reads a 'file' that the test changes."""
    from simple_steps_core import tool
    file = {"rows": people("Al", "Ben", "Cy")}

    @tool
    def load_people() -> pd.DataFrame:
        return file["rows"].copy()

    k = Kernel(Catalog(tools=[load_people]))
    k["p"] = load_people[mod.source()]()
    k["one"] = wf["p"][1]                                # Ben
    k.run_all()
    return k, file, load_people


def test_a_source_tool_run_on_new_data_keeps_the_pick_on_its_row():
    k, file, _ = _loaded()
    file["rows"] = people("Zed", "Al", "Ben", "Cy")
    k.run("p")
    assert k.step("one").formula == 'wf["p"][2]'
    k.run_all()
    assert names(k, "one") == ["Ben"]


def test_a_source_put_back_by_its_tool_puts_the_pick_back():
    k, _, load = _loaded()
    held = k.step("one").output
    k["p"] = people("Zed", "Al", "Ben", "Cy")             # the pick follows Ben to 2
    assert k.step("one").formula == 'wf["p"][2]'
    k["p"] = load[mod.source()]()                       # back: its result is in the store
    assert k.step("one").formula == 'wf["p"][1]'
    assert k.step("one").state == "completed" and k.step("one").output is held


def test_a_widen_is_stale_when_the_dicts_it_spreads_change():
    # found at STRESS=2000: a widen read "no columns", so new keys went unseen
    k = Kernel(Catalog(tools=[]))
    k["s"] = pd.DataFrame({"rec": [{}, {}]})
    k["w"] = mod.widen()(wf["s"])
    k["p"] = mod.pack(columns=["rec"])(wf["s"])
    k.run_all()
    k["s"] = pd.DataFrame({"rec": [{}, {"a": 1}]})
    assert k.step("w").state == "stale" and k.step("p").state == "stale"
    k.run_all()
    assert list(k.step("w").data.columns) == ["a"]
