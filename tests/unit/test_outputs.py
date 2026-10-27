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


# ── G12: mod.name as a list, a mapping or a pattern ──────────────────────────

@tool
def split_name(name: str) -> tuple[str, str]:
    return tuple(name.split(" ")) if " " in name else (name,)


@tool
def to_f(n: int) -> float:
    return n * 1.8 + 32


@pytest.fixture
def g12():
    k = Kernel(Catalog(tools=[bounds, split_name, to_f]))
    k["x"] = pd.DataFrame({"n": [1, 3]})                                # (bounds fails n = 2 on purpose)
    k["p"] = pd.DataFrame({"name": ["Ada Lovelace", "Cy"]})
    return k


@pytest.mark.parametrize("naming, columns", [
    (mod.name(pattern="{field}_c"), ["lo_c", "hi_c"]),
    (mod.name({"lo": "low"}), ["low", "hi"]),
    (mod.name({"lo": "low"}, pattern="{step}_{field}"), ["s_low", "s_hi"]),
])
def test_G12_a_mapping_or_pattern_names_a_records_fields_and_the_plan_agrees(g12, naming, columns):
    g12["s"] = bounds[mod.map(), naming](wf["x"])
    assert g12.step("s").plan["columns"]["names"] == columns
    g12.run_all()
    assert list(g12.step("s").data.columns) == columns


def test_G12_a_list_spreads_a_sequence_and_a_wrong_length_fails_its_row(g12):
    g12["s"] = split_name[mod.map(), mod.name(["first", "last"])](wf["p"])
    with pytest.raises(StepFailed):
        g12.run_all()
    out = g12.step("s").output
    assert out.data.loc[0, "first"] == "Ada" and out.data.loc[0, "last"] == "Lovelace"
    assert "returned 1 values for 2 names" in str(out.notes[1])


def test_G12_a_pattern_names_a_single_value(g12):
    g12["f"] = to_f[mod.map(), mod.name(pattern="{field}_f")](wf["x"])
    g12.run_all()
    assert list(g12.step("f").data.columns) == ["value_f"]


@pytest.mark.parametrize("naming, says", [
    (lambda: to_f[mod.map(), mod.name(["a", "b"])], "2 names to one value"),
    (lambda: bounds[mod.map(), mod.name(["a", "b"])], "rename its fields with a mapping"),
    (lambda: bounds[mod.map(), mod.name({"zz": "q"})], "doesn't have"),
    (lambda: bounds[mod.map(), mod.name(pattern="nope")], "needs {field}"),
    (lambda: bounds[mod.map(), mod.name(["a", "a"])], "two columns one name"),
])
def test_G12_a_name_that_doesnt_fit_is_refused_when_declared(g12, naming, says):
    g12["s"] = naming()(wf["x"])
    assert says in str(g12.step("s").problems)


def test_G12_the_formula_prints_as_written(g12):
    g12["s"] = bounds[mod.map(), mod.name({"lo": "low"}, pattern="{field}_c")](wf["x"])
    assert g12.step("s").formula == 'bounds[mod.map(), mod.name({"lo": "low"}, pattern="{field}_c")](wf["x"])'


# ── G12: kernel-wide naming conventions (outputs-and-reshaping.md §10) ───────

from simple_steps_core import Naming  # noqa: E402


@tool
def toF(n: int) -> float:  # noqa: N802  (camel on purpose)
    return n * 1.8 + 32


def test_G12_a_kernel_pattern_names_every_step_without_its_own():
    cat = Catalog(tools=[bounds, toF])
    k = Kernel(cat, naming=Naming(pattern="{step}_{field}"))
    k["x"] = pd.DataFrame({"n": [1, 3]})
    k["b"] = bounds[mod.map()](wf["x"])
    k["f"] = toF[mod.map(), mod.name("temp")](wf["x"])                  # its own name wins
    k["s"] = mod.sort(by="n")(wf["x"])                                   # writes nothing new
    assert k.step("b").plan["columns"]["names"] == ["b_lo", "b_hi"]
    k.run_all()
    assert {n: list(k.step(n).data.columns) for n in "bfs"} == {
        "b": ["b_lo", "b_hi"], "f": ["temp"], "s": ["n"]}
    back = Kernel.from_json(k.to_json(), cat)                           # saved with the kernel
    assert back.naming == Naming(pattern="{step}_{field}")


def test_G12_a_kernel_case_warns_and_never_renames():
    k = Kernel(Catalog(tools=[toF]), naming=Naming(case="snake"))
    k["x"] = pd.DataFrame({"n": [1]})
    k["f"] = toF[mod.map(), mod.name("tempF")](wf["x"])
    assert any("isn't snake case" in str(w) for w in k.step("f").warnings)
    k.run_all()
    assert list(k.step("f").data.columns) == ["tempF"]


def test_G12_a_kernel_without_naming_saves_as_before():
    k = Kernel(Catalog(tools=[toF]))
    assert "naming" not in k.to_json()


# ── K18: timeout is enforced; G7: a failure says where; G6, G7: warnings ─────

import time  # noqa: E402


@tool
def slow(n: int) -> int:
    time.sleep(0.4 if n == 2 else 0)
    return n


@tool
def risky(n: int) -> int:
    if n == 2:
        raise ValueError("boom")
    return n


@pytest.fixture
def k18():
    k = Kernel(Catalog(tools=[slow, risky]))
    k["x"] = pd.DataFrame({"n": [1, 2, 3]})
    return k


def test_K18_a_call_past_its_timeout_fails_and_says_where(k18):
    k18["t"] = slow[mod.map(), mod.try_except(), mod.timeout(seconds=0.05)](wf["x"])
    started = time.perf_counter()
    k18.run_all()
    assert time.perf_counter() - started < 0.35                       # didn't wait for the slow call
    note = k18.step("t").output.notes[1]
    assert note["where"] == "timeout" and "took longer than 0.05s" in note["error"]
    assert k18.step("t").data["value"].tolist()[0::2] == [1, 3]


def test_G7_a_failure_says_which_layer_gave_up(k18):
    k18["r"] = risky[mod.map(), mod.try_except(), mod.retry(times=2)](wf["x"])
    k18["rn"] = mod.rename(columns={"value": "n"})(wf["r"])
    k18["u"] = risky[mod.map()](wf["rn"])                              # reads the failed row
    k18.run_all()
    assert k18.step("r").output.notes[1]["where"] == "retry"
    assert k18.step("r").output.notes[1]["attempts"] == 3
    assert k18.step("u").output.notes[1]["where"] == "upstream"


def test_G6_a_default_that_doesnt_fit_the_return_type_warns(k18):
    k18["d"] = risky[mod.map(), mod.try_except(default="n/a")](wf["x"])
    assert [w.code for w in k18.step("d").warnings] == ["default_type"]
    k18.run_all()
    assert any("used try_except's default" in str(w) for w in k18.step("d").warnings)


def test_G7_a_modifier_before_the_verb_says_it_covers_the_whole_step(k18):
    k18["o"] = risky[mod.retry(times=2), mod.map()](wf["x"])
    assert [w.code for w in k18.step("o").warnings] == ["modifier_order"]
    assert "retries the whole step" in str(k18.step("o").warnings[0])
