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


# ── G8: a declared record spreads into one column per field ──────────────────

from typing import NamedTuple, TypedDict  # noqa: E402


class LoHi(TypedDict):
    lo: int
    hi: int


class Pair(NamedTuple):
    a: int
    b: str


@tool
def bounds(n: int) -> LoHi:
    return {"lo": n - 1, "hi": n + 1} if n != 2 else {"lo": 0, "extra": 9}


@tool
def maybe_bounds(n: int) -> LoHi | None:
    return None if n == 1 else {"lo": n, "hi": n}


@tool
def pair(n: int) -> Pair:
    return Pair(n, str(n))


@tool
def many_bounds(n: int) -> list[LoHi]:
    return [{"lo": n, "hi": n + k} for k in range(2)]


@pytest.fixture
def g8():
    k = Kernel(Catalog(tools=[bounds, maybe_bounds, pair, many_bounds]))
    k["x"] = pd.DataFrame({"n": [1, 2, 3]})
    return k


def test_G8_a_record_spreads_into_its_fields_and_the_plan_knows(g8):
    g8["p"] = pair[mod.map()](wf["x"])
    assert g8.step("p").plan["columns"] == {"certainty": "exact", "names": ["a", "b"]}
    g8.run_all()
    assert g8.step("p").data.to_dict("list") == {"a": [1, 2, 3], "b": ["1", "2", "3"]}


def test_G8_each_row_is_held_to_the_declaration(g8):
    g8["b"] = bounds[mod.map()](wf["x"])
    with pytest.raises(StepFailed):
        g8.run_all()
    out = g8.step("b").output
    assert str(out.states.at[1, "hi"]) == "failed" and str(out.states.at[1, "lo"]) == "known"
    assert "missing field 'hi'" in str(out.notes[1])
    assert any("'extra'" in str(w) for w in g8.step("b").warnings)


def test_G8_an_optional_record_gives_None_in_every_field(g8):
    g8["m"] = maybe_bounds[mod.map()](wf["x"])
    g8.run_all()
    assert g8.step("m").data.to_dict("list") == {"lo": [None, 2, 3], "hi": [None, 2, 3]}


def test_G8_a_list_of_records_expands_into_rows_and_fields(g8):
    g8["e"] = many_bounds[mod.expand()](wf["x"])
    g8.run_all()
    assert list(g8.step("e").data.columns) == ["#x", "lo", "hi"]


def test_G8_one_name_keeps_the_record_in_one_cell(g8):
    g8["one"] = pair[mod.map(), mod.name("both")](wf["x"])
    g8.run_all()
    assert list(g8.step("one").data.columns) == ["both"]


# ── G9: widen reads a declared record, so its plan is exact ──────────────────

def test_G9_widen_spreads_the_declared_fields_and_plans_them(g8):
    g8["one"] = bounds[mod.map(), mod.name("value")](wf["x"])        # kept in one cell
    g8["w"] = mod.widen()(wf["one"])
    assert g8.step("w").plan["columns"] == {"certainty": "exact", "names": ["lo", "hi"]}
    g8["ok"] = mod.select(rows=[0])(wf["x"])                          # n = 1 only: no bad row
    g8["one2"] = bounds[mod.map(), mod.name("value")](wf["ok"])
    g8["w2"] = mod.widen()(wf["one2"])
    g8.run_all()
    assert g8.step("w2").data.to_dict("list") == {"lo": [0], "hi": [2]}
