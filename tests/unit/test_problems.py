"""Problems with codes, step state, and Output's named fields (phase 3c)."""

from __future__ import annotations

import os
import pickle

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, Problem, mod, tool, wf
from simple_steps_core.problems import CODES


@tool
def readings_p() -> pd.DataFrame:
    return pd.DataFrame({"city": ["SF", "NYC"], "n": [1, 2]})


@tool
def scale_p(n: int, weight: int = 1) -> int:
    return n * weight


@tool
def needs_name_p(name: str) -> str:
    return name


@pytest.fixture
def k():
    k = Kernel(Catalog(tools=[readings_p, scale_p, needs_name_p]))
    k["r"] = readings_p[mod.source()]()
    return k


def first(k, step) -> Problem:
    return k.step(step).problems[0]


# ── the Problem object ───────────────────────────────────────────────────
def test_a_problem_is_its_message_with_a_code():
    p = Problem("'x' is not in this workflow's catalog", "not_in_catalog", step="s")
    assert p == "'x' is not in this workflow's catalog"      # compares as text
    assert str(p) == p.message and isinstance(p, str)
    assert (p.code, p.step, p.severity) == ("not_in_catalog", "s", "error")
    assert repr(p) == ("Problem('not_in_catalog', \"'x' is not in this workflow's "
                       "catalog\", step='s')")
    assert p.to_dict() == {"code": "not_in_catalog",
                           "message": "'x' is not in this workflow's catalog",
                           "step": "s", "argument": None, "row": None,
                           "severity": "error"}


def test_a_problem_needs_a_known_code_and_severity():
    with pytest.raises(ValueError, match="unknown problem code 'nope'"):
        Problem("m", "nope")
    with pytest.raises(ValueError, match="severity is 'error' or 'warning'"):
        Problem("m", "problem", severity="fatal")


def test_a_problem_survives_pickling_and_moving_steps():
    p = Problem("m", "missing_column", step="a", argument="n", row=3)
    q = pickle.loads(pickle.dumps(p))
    assert q.to_dict() == p.to_dict()
    assert p.at("b").step == "b" and p.at("b").code == "missing_column"


# ── what each kind of problem is coded as ────────────────────────────────
def test_steps_report_problems_with_codes_and_their_step(k):
    k.run("r")                    # a source's columns are known once it has run
    k["x"] = tool(os.remove)[mod.map()](wf["r"])
    k["m"] = scale_p[mod.map()](wf["nowhere"])
    k["two"] = scale_p[mod.map(), mod.filter()](wf["r"])
    k["arg"] = scale_p[mod.map()](wf["r"], wieght=2)
    k["set"] = scale_p[mod.map(), mod.retry()](wf["r"])
    k["col"] = needs_name_p[mod.map()](wf["r"])
    found = {name: (first(k, name).code, first(k, name).step)
             for name in ("x", "m", "two", "arg", "set", "col")}
    assert found == {
        "x": ("not_in_catalog", "x"),
        "m": ("missing_step", "m"),
        "two": ("two_shape_verbs", "two"),
        "arg": ("unknown_argument", "arg"),
        "set": ("missing_setting", "set"),
        "col": ("missing_column", "col"),
    }


def test_reading_a_later_step_is_later_step_and_an_invalid_one_is_invalid_input(k):
    k["a"] = scale_p[mod.map()](wf["r"])
    k["b"] = scale_p[mod.map()](wf["r"])
    k["a"] = scale_p[mod.map()](wf["b"])            # a now reads b, which comes after it
    assert first(k, "a").code == "later_step"
    k["b"] = scale_p[mod.map(), mod.name("n")](wf["a"])    # b reads a, which is invalid
    assert first(k, "b").code == "invalid_input"
    assert "root cause: a: input 'b' comes after 'a'" in first(k, "b")


def test_a_different_function_under_a_catalog_name(k):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        @tool(id="scale_p")
        def impostor(n: int) -> int:
            return -n
    k["imp"] = impostor[mod.map()](wf["r"])
    assert first(k, "imp").code == "different_function"


def test_warnings_are_problems_with_a_warning_severity(k):
    k.run("r")
    k["over"] = scale_p[mod.map()](wf["r"], n=5)
    codes = [(w.code, w.severity) for w in k.step("over").warnings]
    assert codes == [("argument_overrides_column", "warning")]
    assert k.step("over").problems == ()          # a warning doesn't block


def test_every_code_used_is_a_documented_code(k):
    k["x"] = tool(os.remove)[mod.map()](wf["nowhere"])
    for step in k.steps:
        for p in (*step.problems, *step.warnings):
            assert p.code in CODES


# ── step state and Output's named fields ─────────────────────────────────
def test_step_state_and_data(k):
    k["s"] = scale_p[mod.map()](wf["r"], weight=10)
    assert k.step("s").state == "staged" and k.step("s").name == "s"
    k.run("s")
    assert k.step("s").state == "completed" == k.step("s").state
    assert k.step("s").data["value"].tolist() == [10, 20]


def test_output_fields_say_what_a_result_was_computed_from(k):
    k["s"] = scale_p[mod.map()](wf["r"], weight=10)
    assert k.step("s").output.staged and k.step("s").output.version is None
    k.run("s")
    out = k.step("s").output
    assert not out.staged and len(out.version) == 12
    assert out.read == {"r": k.step("r").output.version}
    assert out.value_column == "value"
    assert out.ran_with["formula"] == 'scale_p[mod.map()](wf["r"], weight=10)'
    assert not out.stale and out.stale_reason is None
    k["s"] = scale_p[mod.map()](wf["r"], weight=2)
    out = k.step("s").output
    assert out.stale and out.stale_reason == "updated args"


def test_status_is_the_steps_live_part_and_state_its_string(k):
    from simple_steps_core.step import StepStatus
    k["s"] = scale_p[mod.map()](wf["r"], weight=10)
    k.run("s")
    status = k.step("s").status
    assert isinstance(status, StepStatus)
    assert status.state == "completed" == k.step("s").state
    assert status.output is k.step("s").output and status.problems == ()
    assert status.ran_with["formula"] == 'scale_p[mod.map()](wf["r"], weight=10)'
