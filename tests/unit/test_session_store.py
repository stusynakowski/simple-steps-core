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


def test_a_reader_of_a_stale_step_is_stale_even_when_its_key_matches():
    # v, given a new expression not run yet, keeps its last data, marked stale:
    # f's key still matches, but f is current only when v is
    k = Kernel(Catalog([to_f_ss, readings_ss]))
    k["v"] = pd.DataFrame({"temp": [36.0, 39.0]})
    k["f"] = to_f_ss[mod.map()](wf["v"])
    k.run_all()
    k["v"] = readings_ss[mod.source()]()
    assert k.step("v").state == "stale"
    assert k.step("f").state == "stale"
