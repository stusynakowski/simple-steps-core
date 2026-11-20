"""Clearing a step's output (the app's 015 C53; owner, 2026-11-20).

``k.clear(step)`` keeps the formula and drops the output: the step is
``staged`` again, steps that read it are ``stale``, and the results kept for
it are dropped too, so the next run really calls the tool. (``k[name] = None``
is the other move: the step becomes the empty step.)
"""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, tool, wf

calls: list[float] = []


@tool
def to_f(temp_c: float, offset: float = 0.0) -> float:
    calls.append(temp_c)
    return temp_c * 9 / 5 + 32 + offset


@tool
def bad(x: float) -> float:
    raise ValueError("no")


@tool
def reading() -> pd.DataFrame:
    calls.append(-1.0)
    return pd.DataFrame({"temp_c": [1.0, 2.0]})


def kernel() -> Kernel:
    k = Kernel(Catalog(tools=[to_f, bad, reading]))
    k["p"] = pd.DataFrame({"temp_c": [10.0, 38.2, 20.0]})
    k["f"] = to_f[mod.map()](wf["p"], offset=1.0)
    k["g"] = to_f[mod.map()](wf["f"])
    k["h"] = to_f[mod.map()](wf["g"])
    k.run_all()
    calls.clear()
    return k


def test_clear_stages_the_step_and_keeps_its_formula():
    k = kernel()
    formula = k.step("f").formula
    k.clear("f")
    assert k.step("f").state == "staged"
    assert k.step("f").formula == formula
    assert k.cell("f", 1)["state"] == "pending"
    assert k.workflow.results("f") == []              # nothing kept to come back


def test_its_readers_go_stale_and_staleness_is_not_passed_down():
    k = kernel()
    k.clear("f")
    assert k.step("g").state == "stale"
    assert k.step("h").state == "completed"           # owner, 2026-11-04
    assert "g" in k.needs_run() and "f" in k.needs_run()


def test_the_next_run_calls_the_tool_again():
    k = kernel()
    k.clear("f")
    k.run("f")
    assert calls == [10.0, 38.2, 20.0]
    assert k.step("f").state == "completed"


def test_the_same_formula_put_back_doesnt_bring_the_old_result_back():
    k = kernel()
    k.clear("f")
    k["f"] = to_f[mod.map()](wf["p"], offset=1.0)
    assert k.step("f").state == "staged"
    assert calls == []
    k.run("f")
    assert calls == [10.0, 38.2, 20.0]


def test_no_earlier_result_comes_back_either():
    k = kernel()
    k["f"] = to_f[mod.map()](wf["p"], offset=2.0)    # stale, "updated args"
    k.run("f")
    k.clear("f")
    k["f"] = to_f[mod.map()](wf["p"], offset=1.0)    # an earlier formula
    assert k.step("f").state == "staged"


def test_a_reader_rerun_on_the_same_data_is_current_again():
    k = kernel()
    k.clear("f")
    k.run("g")                                        # runs f first, then g
    assert k.step("f").state == k.step("g").state == "completed"


def test_a_failed_step_clears_to_staged():
    k = kernel()
    k["b"] = bad[mod.map()](wf["p"])
    k.run("b")
    assert k.step("b").state == "failed"
    k.clear("b")
    assert k.step("b").state == "staged"


def test_a_source_clears_and_reads_again():
    k = kernel()
    k["s"] = reading[mod.source()]()
    k.run("s")
    calls.clear()
    k.clear("s")
    assert k.step("s").state == "staged"
    k.run_all()
    assert calls == [-1.0]


def test_a_staged_step_is_left_as_it_is():
    k = kernel()
    k["q"] = to_f[mod.map()](wf["p"])
    k.clear("q")
    assert k.step("q").state == "staged"


def test_cells_run_in_place_go_too():
    k = kernel()
    k["q"] = to_f[mod.map()](wf["p"])
    k.run_cell("q", 1)
    assert k.cell("q", 1)["state"] == "known"
    k.clear("q")
    assert k.cell("q", 1)["state"] == "pending"
    assert not k.step("q").cells_run


def test_a_data_step_is_refused_saying_what_to_do():
    k = kernel()
    with pytest.raises(ValueError, match=r"k\['p'\] = None"):
        k.clear("p")
    assert k.step("p").state == "completed"


def test_listeners_hear_clear():
    k = kernel()
    heard: list[str] = []
    k.on_change(lambda change: heard.append(change["action"]))
    k.clear("f")
    assert heard == ["clear"]


def test_an_unknown_step_is_refused():
    k = kernel()
    with pytest.raises(KeyError):
        k.clear("nope")
