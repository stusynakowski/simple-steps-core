"""Stages: a named group of consecutive steps (decision SG, plan P7a, P-D7).

A stage groups the steps that do one part of the work (loading, cleaning,
analysis) so the workflow reads, folds and runs in parts. It adds no input,
output or computation, so it is in no id; core keeps it valid through every
edit: a step inserted inside joins it, a step moved out leaves, a rename
follows, a deleted step goes, and two stages never overlap.
"""

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, tool, wf

CALLS: list = []


@tool
def step_tool(n: int) -> int:
    CALLS.append(n)
    return n + 1


CAT = Catalog(tools=[step_tool])


@pytest.fixture
def k():
    CALLS.clear()
    k = Kernel(CAT)
    k["raw"] = pd.DataFrame({"n": [1, 2]})
    for previous, name in [("raw", "a"), ("a", "b"), ("b", "c"), ("c", "d")]:
        k[name] = step_tool[mod.map(), mod.name("n")](wf[previous])
    return k


def test_a_stage_groups_consecutive_steps(k):
    assert k.stage("clean", first="a", last="c") == ["a", "b", "c"]
    assert k.stages == {"clean": ["a", "b", "c"]}
    assert k.stage_of("b") == "clean" and k.stage_of("d") is None


def test_run_stage_runs_its_steps_and_what_they_need(k):
    k.stage("clean", first="b", last="c")
    k.run_stage("clean")
    assert {n: k.step(n).state for n in ("raw", "a", "b", "c", "d")} == {
        "raw": "completed", "a": "completed", "b": "completed", "c": "completed", "d": "staged"}
    CALLS.clear()
    k.run_stage("clean")
    assert CALLS == []                                   # current: nothing redone
    k.run_stage("clean", force=True)
    assert len(CALLS) == 4                               # b and c, two rows each


def test_a_step_inserted_inside_joins_and_one_at_the_edge_doesnt(k):
    k.stage("clean", first="a", last="c")
    k.insert(2, "a2", step_tool[mod.map(), mod.name("n")](wf["a"]))   # between a and b
    k.insert(1, "before", step_tool[mod.map(), mod.name("n")](wf["raw"]))  # before a
    k["after"] = step_tool[mod.map(), mod.name("n")](wf["d"])         # appended
    assert k.stages["clean"] == ["a", "a2", "b", "c"]


def test_a_step_moved_out_leaves_and_one_moved_in_joins(k):
    k.stage("clean", first="a", last="b")
    k["x"] = pd.DataFrame({"n": [5]})                    # reads nothing: free to move
    k.move("x", 2)                                       # between a and b
    assert k.stages["clean"] == ["a", "x", "b"]
    k.move("x", 5)                                       # to the end
    assert k.stages["clean"] == ["a", "b"]


def test_a_rename_follows_and_a_deleted_step_goes(k):
    k.stage("clean", first="b", last="c")
    k.rename("b", "bee")
    assert k.stages["clean"] == ["bee", "c"]
    k.remove("d")
    k.remove("c")
    assert k.stages["clean"] == ["bee"]
    k.remove("bee", force=True)
    assert "clean" not in k.stages                       # its last step gone, so is it


def test_stages_never_overlap_and_are_checked(k):
    k.stage("load", first="raw", last="a")
    with pytest.raises(ValueError, match="already in stage 'load'"):
        k.stage("clean", first="a", last="c")
    with pytest.raises(ValueError, match="comes after"):
        k.stage("clean", first="c", last="b")
    with pytest.raises(KeyError, match="no step 'nope'"):
        k.stage("clean", first="b", last="nope")
    k.stage("load", first="raw", last="b")               # redefining a stage replaces it
    assert k.stages["load"] == ["raw", "a", "b"]
    k.unstage("load")
    assert k.stages == {}
    with pytest.raises(KeyError, match="no stage 'load'"):
        k.run_stage("load")


def test_a_stage_is_saved_and_loaded_and_is_in_no_id(k, tmp_path):
    before = k.id
    k.stage("clean", first="a", last="c")
    assert k.id == before                                # it changes no output
    assert Kernel.from_json(k.to_json(), CAT).stages == {"clean": ["a", "b", "c"]}
    k.save(tmp_path / "session")
    assert Kernel.load(tmp_path / "session", CAT).stages == {"clean": ["a", "b", "c"]}


def test_a_saved_stage_naming_steps_that_arent_there_loads_what_is(k):
    import json
    k.stage("clean", first="a", last="c")
    blob = json.loads(k.to_json())
    blob["steps"] = [s for s in blob["steps"] if s["name"] not in ("b", "c", "d")]
    loaded = Kernel.from_json(json.dumps(blob), CAT)
    assert loaded.stages == {"clean": ["a"]}
