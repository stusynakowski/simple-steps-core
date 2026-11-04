"""The session model, read off the result store (decisions.md SM, ST5): a
step whose run key the store holds is that result again, with no re-run."""

from __future__ import annotations

import pandas as pd

from simple_steps_core import Catalog, Kernel, mod, tool, wf


@tool
def to_f_ss(temp: float) -> float:
    return round(temp * 1.8 + 32, 1)


def kernel() -> Kernel:
    k = Kernel(Catalog([to_f_ss]))
    k["v"] = pd.DataFrame({"temp": [36.0, 39.0]})
    k["f"] = to_f_ss[mod.map()](wf["v"])
    k.run_all()
    return k


def test_an_expression_put_back_is_completed_with_no_rerun():          # S7
    k = kernel()
    ran = k.step("f").output
    k["f"] = to_f_ss[mod.map(), mod.name("x")](wf["v"])
    assert k.step("f").state == "stale"
    k["f"] = to_f_ss[mod.map()](wf["v"])
    assert k.step("f").state == "completed" and k.step("f").output is ran


def test_a_step_made_invalid_keeps_showing_its_last_values():           # S8
    k = kernel()
    k["v"] = pd.DataFrame({"t": [36.0, 39.0]})
    assert k.step("f").state == "invalid"
    assert k.step("f").data["value"].tolist() == [96.8, 102.2]


def test_the_column_put_back_is_completed_with_no_rerun():              # S9
    k = kernel()
    ran = k.step("f").output
    k["v"] = pd.DataFrame({"t": [36.0, 39.0]})
    k["v"] = pd.DataFrame({"temp": [36.0, 39.0]})
    assert k.step("f").state == "completed" and k.step("f").output is ran


@tool
def readings_ss() -> pd.DataFrame:
    return pd.DataFrame({"temp": [36.0, 39.0]})


def test_a_reader_of_a_stale_step_stays_completed_and_names_it():
    # v, given a new expression not run yet, keeps its last data, marked stale.
    # f read that data: it stays completed, saying it read v stale; staleness
    # isn't passed down the chain (owner, 2026-11-04)
    k = Kernel(Catalog([to_f_ss, readings_ss]))
    k["v"] = pd.DataFrame({"temp": [36.0, 39.0]})
    k["f"] = to_f_ss[mod.map()](wf["v"])
    k.run_all()
    k["v"] = readings_ss[mod.source()]()
    assert k.step("v").state == "stale"
    assert k.step("f").state == "completed"
    assert k.needs_run()["f"] == "read stale 'v'"
    k.run("f")                                      # runs v first (C9)
    assert k.step("v").state == k.step("f").state == "completed"


def _empty_chain() -> Kernel:
    """s1 sorts an empty source, so a pick of its row 0 is refused when s1
    runs; s4 groups by that pick's rows. Found by the property test L40d."""
    from simple_steps_core import op
    k = Kernel(Catalog([]))
    k["s0"] = pd.DataFrame({"k": pd.Series([], dtype=object)})
    k["s1"] = mod.sort(by="k")(wf["s0"])
    k["s2"] = wf["s1"][0]
    k["s4"] = op("count")[mod.collapse(by="#s2")](wf["s0"])
    try:
        k.run_all()
    except ValueError:
        pass
    return k


def test_a_step_turned_invalid_by_a_run_makes_what_groups_by_it_invalid():
    # s2 is refused only when s1 runs; s4 groups by s2, so it can't stand
    k = _empty_chain()
    assert k.step("s2").state == "invalid"
    assert k.step("s4").state == "invalid"


@tool
def nothing_ss() -> pd.DataFrame:
    return pd.DataFrame({"k": pd.Series([], dtype=object)})


def test_a_pick_into_a_restored_result_is_checked_against_it():
    # s0's expression edited and put back: s1's result comes back from the
    # store, and s2's pick is checked against it again, as when s1 ran
    k = Kernel(Catalog([nothing_ss]))
    k["s0"] = nothing_ss[mod.source()]()
    k["s1"] = mod.sort(by="k")(wf["s0"])
    k["s2"] = wf["s1"][0]
    try:
        k.run_all()
    except ValueError:
        pass
    assert k.step("s2").state == "invalid"
    original = k.step("s0").operation
    k["s0"] = mod.sort(by="k")(wf["s0"])                  # reads itself: invalid
    k["s0"] = original
    assert (k.step("s1").state, k.step("s2").state) == ("completed", "invalid")
