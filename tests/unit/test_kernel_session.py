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
    assert k.needs_run() == {"sick": "stale: updated args", "f": "read stale 'sick'"}


def test_a_step_run_on_a_stale_input_is_completed_and_says_so(k):
    k.run_all()
    k["sick"] = feverish_i[mod.filter()](wf["p"], limit=37)
    k.run("f", fresh=False)                         # on purpose: on what sick shows
    assert k.step("f").state == "completed"
    assert k.needs_run() == {"sick": "stale: updated args", "f": "read stale 'sick'"}
    assert "completed · read stale 'sick'" in repr(k)
    k.run("sick")                                   # sick's data changes
    assert k.needs_run() == {"f": "stale: input sick changed"}
    k.run("f")
    assert k.needs_run() == {}
    assert k.step("f").data["f"].tolist() == [100.76, 98.78]


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


# ── G13: a step is re-checked when its input's columns change ────────────
@tool
def label_i(name: str) -> str:
    return name.upper()


@pytest.fixture
def k13():
    k = Kernel(Catalog(tools=[patients_i, to_f_i, feverish_i, label_i]))
    k["p"] = patients_i[mod.source()]()
    k["sick"] = feverish_i[mod.filter()](wf["p"])
    k["f"] = to_f_i[mod.map()](wf["sick"])
    k["g"] = to_f_i[mod.map()](wf["f"], temp_c=1.0)
    k.run_all()
    return k


def test_a_reader_whose_column_is_gone_is_a_problem_once_its_input_runs(k13):
    k13["sick"] = label_i[mod.map()](wf["p"])        # sick no longer has temp_c
    k13.run("sick")
    f = k13.step("f")
    assert f.state == "invalid"
    assert [(p.code, p.message) for p in f.problems] == [
        ("missing_column", "to_f_i() needs 'temp_c', which 'sick' does not have (it has sick). "
                           "No column of 'sick' is float (sick: str): convert one, "
                           "mod.cast(sick='float'), or bind one, temp_c=wf['sick'][cols['sick']]")]
    assert [p.code for p in k13.step("g").problems] == ["invalid_input"]
    assert k13.validate()["f"] == f.problems
    assert f.data["f"].tolist() == [100.76]             # what it showed is kept


def test_fixing_the_input_clears_the_problem(k13):
    k13["sick"] = label_i[mod.map()](wf["p"])
    k13.run("sick")
    k13["sick"] = feverish_i[mod.filter()](wf["p"])
    k13.run("sick")
    assert k13.step("f").problems == () and k13.step("g").problems == ()
    k13.run_all()
    assert [s.state for s in k13.steps] == ["completed"] * 4


def test_until_the_input_reruns_its_reader_may_still_run_on_what_it_shows(k13):
    k13["sick"] = label_i[mod.map()](wf["p"])        # re-declared, not run
    assert k13.step("f").problems == ()
    k13.run("f", fresh=False)                        # sick's old output passes through
    assert k13.needs_run()["f"] == "read stale 'sick'"


def test_editing_an_input_warns_a_reader_at_once_that_it_will_break(k13):
    k13["sick"] = label_i[mod.map()](wf["p"])        # re-declared, not run
    f = k13.step("f")
    assert f.problems == ()                          # it can still run on what sick shows
    # and it read sick, which is stale now (SS7): run("f") runs sick first
    assert [(w.code, w.severity, w.step) for w in f.warnings] == [
        ("likely_missing_column", "warning", "f"), ("read_stale", "warning", "f")]
    assert "expects 'temp_c' from 'sick', which is predicted to produce (sick)" in f.warnings[0]
    k13.run("sick")                                  # the warning becomes the problem
    assert [p.code for p in k13.step("f").problems] == ["missing_column"]
    assert k13.step("f").warnings == ()


def test_an_edit_that_keeps_the_column_warns_as_before_any_run(k13):
    # PL: an edited input is planned again, so its reader is told what a
    # reader of a step that never ran is told (005 C), nothing more
    k13["sick"] = feverish_i[mod.filter()](wf["p"], limit=37)
    assert [w.code for w in k13.step("f").warnings] == ["unconfirmed_column", "read_stale"]


# ── PL: a step is checked against its inputs' plans, never what they show ──
def test_a_reader_is_checked_against_what_an_edited_input_will_produce(k13):
    k13["sick"] = label_i[mod.map()](wf["p"])        # will give sick, shows temp_c
    k13["s"] = mod.sort(by="sick")(wf["sick"])
    assert k13.step("s").problems == () and k13.step("s").state == "staged"
    k13["t"] = mod.sort(by="temp_c")(wf["sick"])     # shown, but won't be produced
    assert [p.code for p in k13.step("t").problems] == ["missing_setting"]
    assert "(it has sick)" in k13.step("t").problems[0]
    k13.run("s")                                     # runs sick first (C9)
    assert k13.step("s").state == "completed"


def test_a_reader_declared_before_the_edit_is_checked_again_against_the_plan(k13):
    k13["s"] = mod.sort(by="sick")(wf["sick"])       # sick's filter has no sick column yet
    assert [p.code for p in k13.step("s").problems] == ["missing_setting"]
    k13["sick"] = label_i[mod.map()](wf["p"])        # now it will
    assert k13.step("s").problems == ()
    k13["sick"] = feverish_i[mod.filter()](wf["p"])  # put back: shows its result
    assert [p.code for p in k13.step("s").problems] == ["missing_setting"]


def test_an_edit_plans_its_readers_again_in_either_order(k13):
    # s's problems don't change, its plan does: u, after it, must see that
    def states(edit_first):
        k = Kernel(Catalog(tools=[patients_i, to_f_i, feverish_i, label_i]))
        k["p"] = patients_i[mod.source()]()
        k["sick"] = feverish_i[mod.filter()](wf["p"])
        k.run_all()
        edit = lambda: k.__setitem__("sick", mod.select(columns=["name"])(wf["p"]))
        edit_first and edit()
        k["s"] = mod.sort(by="name")(wf["sick"])
        k["u"] = mod.select(columns=["temp_c"])(wf["s"])
        edit_first or edit()
        return [(k.step(n).state, [p.code for p in k.step(n).problems]) for n in ("s", "u")]
    assert states(True) == states(False) == [("staged", []), ("invalid", ["missing_setting"])]


def test_a_chain_of_edited_steps_is_planned_once_each():
    # each plan reads its input's plan: made again on every ask, a chain of
    # n edited steps took 4^n (40 steps: forever); made once, it is linear
    import time
    k = Kernel(Catalog(tools=[]))
    k["p"] = pd.DataFrame({"a": [3, 1, 2], "b": [1, 2, 3]})
    for i in range(30):
        k[f"s{i}"] = mod.sort(by="a")(wf["p" if i == 0 else f"s{i - 1}"])
    k.run_all()
    start = time.perf_counter()
    for i in range(30):
        k[f"s{i}"] = mod.sort(by="b")(wf["p" if i == 0 else f"s{i - 1}"])
    k["r"] = mod.sort(by="a")(wf["s29"])
    assert time.perf_counter() - start < 10
    assert k.step("r").state == "staged"


# ── SS7: what is stale is among the warnings; delete anyway ───────────────
def test_a_stale_step_says_why_among_its_warnings(k13):
    k13["sick"] = feverish_i[mod.filter()](wf["p"], limit=37)
    sick, f = k13.step("sick"), k13.step("f")
    assert [(w.code, w.severity) for w in sick.warnings] == [("stale", "warning")]
    assert "stale: updated args" in sick.warnings[0]
    assert "read 'sick', which is stale (updated args); run('f') runs it first" in [
        str(w) for w in f.warnings if w.code == "read_stale"][0]
    assert [w.code for w in k13.step("g").warnings] == []      # g read f, which isn't stale
    k13.run("f")
    assert [w.code for w in k13.step("f").warnings] == []


def test_a_check_writing_warnings_keeps_the_stale_note(k13):
    k13["p"] = pd.DataFrame({"name": ["Al"], "temp_c": [39.0]})
    sick = k13.step("sick")
    sick.warnings = ()                               # what a re-check does
    assert [w.code for w in sick.warnings] == ["stale"]


def test_remove_refuses_a_step_that_is_read_unless_forced(k13):
    with pytest.raises(ValueError, match="'f' read"):
        k13.remove("sick")
    k13.remove("sick", force=True)
    assert "sick" not in k13
    f = k13.step("f")
    assert f.state == "invalid" and any("sick" in str(p) for p in f.problems)
    assert [p.code for p in k13.step("g").problems] == ["invalid_input"]


def test_a_step_name_with_a_dot_or_a_hash_is_refused(k):
    with pytest.raises(ValueError, match="can't contain '.'.*write 'a_b'"):
        k["a.b"] = to_f_i[mod.map()](wf["p"])
    with pytest.raises(ValueError, match="can't start with '#'"):
        k["#x"] = to_f_i[mod.map()](wf["p"])
    with pytest.raises(ValueError, match="can't contain '.'"):
        k.rename("f", "f.2")
    assert "a.b" not in k and "f" in k
