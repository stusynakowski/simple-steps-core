"""The app's 008 asks (docs/core-proposals/008-core-changes.md), one test each.

Each test is the ask's "Done when" line, so a fix can't regress after the app
adopts it. scripts/core_asks.py runs the same checks as probes.
"""

import json
import warnings

import pandas as pd
import pytest

from simple_steps_core import grid
from simple_steps_core.grid import Workflow, mod, op, tool

warnings.simplefilter("ignore", UserWarning)    # tools re-declared per test


@tool
def scale_008(n, weight=1):
    return n * 10 * weight


@tool
def add_008(acc, n):
    return (acc or 0) + n


@tool
def to_rows_008(data: str) -> pd.DataFrame:
    return pd.DataFrame(json.loads(data))


@tool
def tag_008(city):
    return city


@tool
def dbl_008(n):
    return n * 2


DATA = json.dumps({"city": ["SF", "NYC", "SF", "LA"], "n": [1, 2, 3, 2]})


@pytest.fixture()
def wf():
    w = Workflow()
    w["readings"] = pd.DataFrame({"city": ["SF", "NYC", "SF", "LA"], "n": [1, 2, 3, 2]})
    return w


# ── Priority 1 ───────────────────────────────────────────────────────────
def test_K1_an_unrun_source_defers_column_checks_then_checks_them():
    w = Workflow()
    w["readings"] = to_rows_008.bind(data=DATA)[mod.source()]
    w["scored"] = scale_008[mod.map(name="score")](w["readings"])
    w["picked"] = mod.select(over=w["scored"], columns=["city", "score"])
    w["typo"] = mod.select(over=w["scored"], columns=["cty"])
    assert w.step("picked").problems == () and w.step("typo").problems == ()
    assert grid.columns_unknown(w.step("scored").output)
    w.run_all()
    assert w.step("picked").output.data.to_dict("list") == {
        "city": ["SF", "NYC", "SF", "LA"], "score": [10, 20, 30, 20]}
    # the deferred check is decided once the source has run — a real typo fails
    assert "names 'cty'" in w.step("typo").problems[0]


def test_K1_a_literal_source_has_known_columns(wf):
    assert not grid.columns_unknown(wf.step("readings").output)
    wf["typo"] = mod.select(over=wf["readings"], columns=["cty"])
    assert "names 'cty'" in wf.step("typo").problems[0]


def test_K2_inference_does_not_depend_on_run_state(wf):
    wf["x"] = add_008(wf["readings"])
    unrun = Workflow()
    unrun["readings"] = to_rows_008.bind(data=DATA)[mod.source()]
    unrun["x"] = add_008(unrun["readings"])
    kinds = [w.step("x").operation.shape_verb.kind for w in (wf, unrun)]
    assert kinds == ["collapse", "collapse"]


def test_K3_an_operation_used_as_an_input_is_refused(wf):
    inner = op("identity")[mod.select(columns=["n"])](wf["readings"])
    with pytest.raises(TypeError, match="can't be an input yet"):
        scale_008[mod.map()](inner)
    with pytest.raises(TypeError, match="can't be an input yet"):
        scale_008[mod.map(over=inner)]
    with pytest.raises(TypeError, match="can't be an input yet"):
        scale_008(inner)


def test_K4_over_given_twice_is_refused(wf):
    wf["other"] = pd.DataFrame({"n": [5]})
    with pytest.raises(TypeError, match="Give the input once"):
        scale_008[mod.map(over=wf["readings"])](wf["other"])


def test_N2_an_explicit_argument_beats_a_same_named_column(wf):
    wf["x"] = tag_008[mod.map()](wf["readings"], city="NYC")
    wf.run("x")
    assert wf.step("x").output.values == ["NYC"] * 4


def test_C13_an_explicit_name_cannot_silently_replace_a_column(wf):
    wf["x"] = dbl_008[mod.map(name="n")](wf["readings"])
    assert wf.step("x").problems == (
        "map writes 'n', which readings already has; choose another name "
        "(name=…), or say replace=True",)
    wf["y"] = dbl_008[mod.map(name="n", replace=True)](wf["readings"])
    wf.run("y")
    assert list(wf.step("y").output.data["n"]) == [2, 4, 6, 4]


def test_C13_the_default_payload_overwriting_is_a_warning_not_a_problem(wf):
    wf["a"] = scale_008[mod.map()](wf["readings"])
    wf["b"] = scale_008[mod.map()](wf["a"])                # a has `value` already
    assert wf.step("b").problems == ()
    assert any("writes 'value' over" in w for w in wf.step("b").warnings)


# ── Priority 2 / 3 ───────────────────────────────────────────────────────
def test_N1_a_union_setting_accepts_its_members():
    class DB:
        def __init__(self, table: dict | None = None):
            self.table = table
    Workflow().define("db", DB, table={"SF": "n"})
    Workflow().define("db", DB, table=None)
    with pytest.raises(TypeError, match="declared dict | None"):
        Workflow().define("db", DB, table=3)


def test_N1_a_union_parameter_accepts_a_bound_literal(wf):
    @tool
    def opt_008(n, k: int | None = None):
        return n
    wf["x"] = opt_008.bind(k=3)[mod.map()](wf["readings"])
    assert wf.step("x").problems == ()


def test_O_a_missing_required_setting_is_a_problem_without_a_workflow():
    blob = {"tool_id": "scale_008", "input": None, "arguments": {},
            "modifiers": [{"kind": "retry", "params": {}}, {"kind": "map", "params": {}}]}
    problems = grid.check(grid.Operation.from_dict(blob))
    assert problems == ("retry needs times= — it has no default, so a step "
                        "without it cannot run",)
    assert grid.check(scale_008[mod.timeout()]) == (
        "timeout needs seconds= — it has no default, so a step without it "
        "cannot run",)


def test_C6_the_same_formula_resolves_in_whichever_workflow():
    w1, w2 = Workflow(), Workflow()
    w1["r"] = pd.DataFrame({"n": [1, 2]})
    w2["r"] = pd.DataFrame({"n": [7, 8]})
    line = scale_008[mod.map()](grid.wf["r"])
    for w in (w1, w2):
        w["x"] = line
        w.run("x")
    assert w1.step("x").output.values == [10, 20]
    assert w2.step("x").output.values == [70, 80]
    assert w1.to_dict()["steps"][1]["operation"]["input"] == {"$ref": "r"}


def test_C6_grid_wf_is_a_reference_not_a_workflow():
    with pytest.raises(KeyError):
        grid.wf[0]
    with pytest.raises(AttributeError, match="not a workflow"):
        grid.wf.run


def test_K5_a_string_over_is_refused_in_python():
    with pytest.raises(TypeError, match=r"pass wf\['readings'\]"):
        mod.map(over="readings")
    # JSON keeps string ids
    op_ = grid.Operation.from_dict({"tool_id": "scale_008", "input": "readings",
                                    "arguments": {}, "modifiers": [{"kind": "map", "params": {}}]})
    assert str(op_.input) == "readings"


def test_K8_a_tool_less_verb_is_callable_on_a_reference(wf):
    wf["n_only"] = mod.select(columns=["n"])(wf["readings"])
    assert wf.step("n_only").operation == op("identity")[mod.select(columns=["n"])](wf["readings"])
    wf.run("n_only")
    assert list(wf.step("n_only").output.data.columns) == ["n"]
    with pytest.raises(TypeError, match="needs a tool"):
        mod.map()(wf["readings"])


def test_K11_a_list_over_points_at_the_combine_verbs(wf):
    wf["other"] = pd.DataFrame({"n": [5]})
    with pytest.raises(TypeError, match="use join, stack or zip_"):
        scale_008[mod.map(over=[wf["readings"], wf["other"]])]


def test_K13_the_modifier_catalog_says_which_verbs_take_a_tool():
    cat = grid.modifier_catalog()
    assert (cat["map"]["takes_tool"], cat["map"]["default_tool"]) == (True, None)
    assert (cat["select"]["takes_tool"], cat["select"]["default_tool"]) == (False, "identity")
    assert (cat["collapse"]["takes_tool"], cat["collapse"]["default_tool"]) == ("optional", "gather")
    assert cat["retry"]["takes_tool"] is None
