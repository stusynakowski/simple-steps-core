"""A kernel in an interactive session: check, needs_run, on_change, insert and
move (docs/design/interactive-sessions.md)."""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, tool, wf


@tool
def patients_i() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "temp_c": [36.6, 38.2, 37.1]})


@tool
def to_f_i(temp_c: float) -> float:
    return round(temp_c * 9 / 5 + 32, 2)


@tool
def feverish_i(temp_c: float, limit: float = 38) -> bool:
    return temp_c >= limit


@pytest.fixture
def k():
    k = Kernel(Catalog(tools=[patients_i, to_f_i, feverish_i]))
    k["p"] = patients_i[mod.source()]()
    k["sick"] = feverish_i[mod.filter()](wf["p"])
    k["f"] = to_f_i[mod.map()](wf["sick"])
    return k


def snapshot(k):
    return [(s.name, s.state, tuple(s.problems)) for s in k.steps]


# ── check: a proposal, without changing anything ─────────────────────────
def test_check_says_what_a_step_would_have_without_adding_it(k):
    before = snapshot(k)
    assert k.check("g", to_f_i[mod.map()](wf["p"])) == ()
    found = k.check("h", to_f_i[mod.map()](wf["nope"]))
    assert [(p.code, p.step) for p in found] == [("missing_step", "h")]
    assert "g" not in k and "h" not in k and snapshot(k) == before


def test_check_on_an_existing_name_checks_the_replacement_in_place(k):
    k["late"] = to_f_i[mod.map()](wf["p"])
    found = k.check("sick", feverish_i[mod.filter()](wf["late"]))
    assert [p.code for p in found] == ["later_step"]
    assert k.step("sick").problems == ()


def test_check_handles_literals_and_selections(k):
    assert k.check("lit", [1, 2, 3]) == ()
    assert k.check("part", wf["p"][0:2]) == ()


# ── needs_run, and running on stale inputs ───────────────────────────────
def test_needs_run_lists_what_isnt_up_to_date_in_run_order(k):
    assert k.needs_run() == {"p": "staged", "sick": "staged", "f": "staged"}
    k.run_all()
    assert k.needs_run() == {}
    k["sick"] = feverish_i[mod.filter()](wf["p"], limit=37)
    assert k.needs_run() == {"sick": "stale: updated args", "f": "stale: sick is stale"}


def test_a_step_run_on_a_stale_input_is_completed_and_says_so(k):
    k.run_all()
    k["sick"] = feverish_i[mod.filter()](wf["p"], limit=37)
    k.run("f")
    assert k.step("f").state == "completed"
    assert k.needs_run() == {"sick": "stale: updated args", "f": "read stale 'sick'"}
    assert "completed · read stale 'sick'" in repr(k)
    k.run("sick")                                   # sick's data changes
    assert k.needs_run() == {"f": "stale: input sick changed"}
    k.run("f")
    assert k.needs_run() == {}
    assert k.step("f").data["value"].tolist() == [100.76, 98.78]


# ── on_change ────────────────────────────────────────────────────────────
def test_on_change_tells_the_host_what_changed(k):
    events = []
    stop = k.on_change(events.append)
    k.run("p")
    k["sick"] = feverish_i[mod.filter()](wf["p"], limit=37)
    k.rename("f", "temps")
    del k["temps"]
    stop()
    k.run_all()                                      # no longer listening
    assert events == [
        {"action": "run", "changed": ["p", "sick"], "removed": []},
        {"action": "declare", "changed": ["sick"], "removed": []},
        {"action": "rename", "changed": ["temps"], "removed": ["f"]},
        {"action": "remove", "changed": [], "removed": ["temps"]},
    ]


def test_on_change_is_told_even_when_a_run_stops(k):
    @tool
    def boom_i(temp_c: float) -> float:
        raise ValueError("no")
    k2 = Kernel(Catalog(tools=[patients_i, boom_i]))
    k2["p"] = patients_i[mod.source()]()
    k2["b"] = boom_i[mod.map()](wf["p"])
    events = []
    k2.on_change(events.append)
    with pytest.raises(Exception, match="failed"):
        k2.run_all()
    assert events and events[0]["action"] == "run_all" and "b" in events[0]["changed"]


def test_nothing_is_told_when_nothing_changed(k):
    k.run_all()
    events = []
    k.on_change(events.append)
    k["f"] = to_f_i[mod.map()](wf["sick"])           # the same formula again
    assert events == []


# ── insert and move ──────────────────────────────────────────────────────
def test_insert_puts_a_new_step_at_a_position(k):
    k.insert(1, "c", to_f_i[mod.map()](wf["p"]))
    assert list(k) == ["p", "c", "sick", "f"]
    k.insert(-1, "d", to_f_i[mod.map()](wf["p"]))
    assert list(k) == ["p", "c", "sick", "f", "d"]
    with pytest.raises(ValueError, match="reads 'p', which would come after it"):
        k.insert(0, "z", to_f_i[mod.map()](wf["p"]))
    with pytest.raises(ValueError, match="already exists"):
        k.insert(1, "c", to_f_i[mod.map()](wf["p"]))
    assert "z" not in k


def test_move_refuses_to_break_a_valid_step(k):
    k.insert(1, "c", to_f_i[mod.map()](wf["p"]))
    with pytest.raises(ValueError, match="'c' reads 'p', which would come after it"):
        k.move("p", 3)
    k.move("c", -1)
    assert list(k) == ["p", "sick", "f", "c"]


def test_a_move_can_fix_an_order(k):
    k["early"] = to_f_i[mod.map()](wf["p"])
    k.move("early", 1)                               # p, early, sick, f
    k["early"] = to_f_i[mod.map()](wf["f"])           # now reads a later step
    assert [p.code for p in k.step("early").problems] == ["later_step"]
    k.move("early", -1)
    assert list(k) == ["p", "sick", "f", "early"]
    assert k.step("early").problems == ()
