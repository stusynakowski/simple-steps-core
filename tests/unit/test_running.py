"""Running brings steps up to date (owner, 2026-11-16).

``k.run_all()`` and ``k.run(x)`` run only what isn't current: a step never
run, or stale. A completed or failed step whose inputs, tool and expression
haven't changed is left as it is, so a reopened session or a second "Run all"
doesn't redo slow work. ``force=True`` recomputes anyway (a retry).
"""

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, tool, wf

CALLS: list = []


@tool
def slow(n: int) -> int:
    CALLS.append(("slow", n))
    return n * 10


@tool
def slower(slow: int) -> int:
    CALLS.append(("slower", slow))
    return slow + 1


@tool
def flaky(n: int) -> int:
    CALLS.append(("flaky", n))
    if n == 2:
        raise ValueError("two")
    return n


CAT = Catalog(tools=[slow, slower, flaky])


@pytest.fixture
def k():
    CALLS.clear()
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2, 3]})
    k["a"] = slow[mod.map()](wf["s"])
    k["b"] = slower[mod.map()](wf["a"])
    k.run_all()
    CALLS.clear()
    return k


def test_a_second_run_all_runs_nothing(k):
    k.run_all()
    assert CALLS == []
    assert k.needs_run() == {}


def test_run_of_a_current_step_runs_nothing(k):
    k.run("b")
    assert CALLS == []
    assert k.step("b").state == "completed"


def test_force_recomputes(k):
    k.run("b", force=True)
    assert CALLS == [("slower", 10), ("slower", 20), ("slower", 30)]
    CALLS.clear()
    k.run_all(force=True)
    assert [c[0] for c in CALLS] == ["slow"] * 3 + ["slower"] * 3


def test_an_edit_reruns_what_it_changed_and_no_more(k):
    k["s"] = pd.DataFrame({"n": [1, 2, 4]})       # one value changed
    k.run_all()
    assert ("slow", 4) in CALLS and ("slower", 40) in CALLS
    assert k.step("b").output.data["b"].tolist() == [11, 21, 41]
    assert k.needs_run() == {}


def test_a_reader_whose_input_came_back_the_same_is_left_as_it_is(k):
    k["a"] = slow[mod.map(), mod.retry(times=2)](wf["s"])   # a new expression, same values
    k.run_all()
    assert [c[0] for c in CALLS] == ["slow"] * 3            # b isn't re-run
    assert k.step("b").state == "completed"


def test_run_of_a_step_runs_what_it_needs_first(k):
    k["a"] = slow[mod.map(), mod.retry(times=3)](wf["s"])
    k.run("b")
    assert [c[0] for c in CALLS] == ["slow"] * 3
    assert k.step("b").state == "completed"


def test_a_failed_step_is_current_until_forced(k):
    k["f"] = flaky[mod.map(), mod.try_except()](wf["s"])
    k.run_all()
    assert k.step("f").state == "failed"
    CALLS.clear()
    k.run_all()
    assert CALLS == []                                    # its inputs haven't changed
    k.run("f", force=True)                                # a retry
    assert [c[0] for c in CALLS] == ["flaky"] * 3


def test_a_staged_step_runs(k):
    k["c"] = slow[mod.map()](wf["s"])
    k.run_all()
    assert [c[0] for c in CALLS] == ["slow"] * 3


def test_an_invalid_step_is_still_refused_by_name(k):
    k["bad"] = slow[mod.map()](wf["nowhere"])
    k.run_all()                                           # skipped, saying why
    with pytest.raises(ValueError, match="invalid"):
        k.run("bad")


def test_a_reopened_session_runs_nothing(k, tmp_path):
    k.save(tmp_path / "session", outputs=True)
    loaded = Kernel.load(tmp_path / "session", CAT)
    CALLS.clear()
    loaded.run_all()
    assert CALLS == []


def test_a_source_tool_reads_again_when_named_but_not_on_run_all():
    world = {"n": [1, 2]}

    @tool
    def load() -> pd.DataFrame:
        CALLS.append(("load",))
        return pd.DataFrame(world)

    k = Kernel(Catalog(tools=[load, slow]))
    k["p"] = load[mod.source()]()
    k["a"] = slow[mod.map()](wf["p"])
    k.run_all()
    CALLS.clear()
    k.run_all()
    assert CALLS == []                                    # kept until asked to read again
    world["n"] = [1, 5]                                   # the outside world changed
    k.run("p")                                            # a reload
    assert CALLS == [("load",)]
    assert k.step("a").state == "stale"
    k.run_all()
    assert k.step("a").output.data["a"].tolist() == [10, 50]


def test_an_explicitly_bound_column_that_changes_makes_its_step_stale():
    # found 2026-11-16: binding by type writes slow=wf["a"]["a"], and the row
    # fingerprint left that column out, so b stayed completed on new data
    CALLS.clear()
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2, 3]})
    k["a"] = slow[mod.map()](wf["s"])
    k["b"] = slower[mod.map()](wf["a"])
    assert 'slow=wf["a"]' in k.step("b").formula
    k.run_all()
    k["s"] = pd.DataFrame({"n": [1, 2, 4]})
    k.run("a")
    assert k.step("b").state == "stale"


def test_a_failure_nothing_handles_still_stops_run_all_without_rerunning():
    from simple_steps_core.errors import StepFailed
    CALLS.clear()
    k = Kernel(CAT)
    k["s"] = pd.DataFrame({"n": [1, 2, 3]})
    k["f"] = flaky[mod.map()](wf["s"])
    with pytest.raises(StepFailed):
        k.run_all()
    CALLS.clear()
    with pytest.raises(StepFailed, match="try_except"):
        k.run_all()                                       # it still says so
    assert CALLS == []                                    # without redoing the work
