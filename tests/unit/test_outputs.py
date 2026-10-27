"""Outputs, finished (docs/design/phase4-plan.md, step A): a fold's starting
value (G5), records spread into columns (G8), widen reading declared records
(G9), mod.name's forms (G12), warnings for defaults and where a row failed
(G6, G7), and timeout (K18)."""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, tool, wf
from simple_steps_core.errors import StepFailed


# ── G5: a fold's starting value (A-D1) ───────────────────────────────────────

class _NoEmpty:
    pass


@tool
def fold_untyped(acc, n: int) -> int:
    return acc + n


@tool
def fold_float(acc: float, n: int) -> float:
    return acc + n


@tool
def fold_list(acc: list, n: int) -> list:
    return acc + [n]


@tool
def fold_model(acc: _NoEmpty, n: int) -> _NoEmpty:
    return acc


@pytest.fixture
def g5():
    k = Kernel(Catalog(tools=[fold_untyped, fold_float, fold_list, fold_model]))
    k["x"] = pd.DataFrame({"n": [3, 1, 2]})
    return k


def test_G5_a_fold_starts_from_its_accumulator_types_empty_value(g5):
    g5["f"] = fold_float[mod.collapse()](wf["x"])
    g5["l"] = fold_list[mod.collapse()](wf["x"])
    g5.run_all()
    assert g5.step("f").data["value"].tolist() == [6.0]
    assert g5.step("l").data["value"].tolist() == [[3, 1, 2]]


def test_G5_a_fold_whose_type_has_no_empty_value_is_refused_when_declared(g5):
    g5["m"] = fold_model[mod.collapse()](wf["x"])
    assert [p.code for p in g5.step("m").problems] == ["missing_setting"]
    assert "give initial=" in g5.step("m").problems[0]


def test_G5_a_given_initial_is_where_it_starts(g5):
    g5["i"] = fold_float[mod.collapse(initial=10)](wf["x"])
    g5.run_all()
    assert g5.step("i").data["value"].tolist() == [16]


def test_G5_an_untyped_fold_starts_at_None_and_says_so_when_that_fails(g5):
    g5["u"] = fold_untyped[mod.collapse()](wf["x"])
    with pytest.raises(StepFailed):
        g5.run_all()
    assert "acc starts as None: give initial=" in str(g5.step("u").output.notes)
