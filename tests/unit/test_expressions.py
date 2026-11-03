"""The expression cleanup: syntax-review.md §8's laws and §4's bugs (phase4-plan S0).

One test per law or bug that the core-asks tests (test_core_asks.py) don't
already cover. A law that holds today is a plain test; one that waits is
``xfail(strict=True)`` naming its step of phase4-plan.md, so it fails loudly
the day it starts to hold and the mark comes off. Tests of proposed moves are
written in the proposed spelling.

Covered elsewhere, not repeated: E1–E5 (core-asks L25–L26, L7), E11 and E16
(superseded by CA-A and CA-E: L50b, L21a), E12 (test_where.py), E13 (L1),
E17 (L23), E21 (L6, L10–L12), B5–B8 (L50, L21, E8, E19). E10 (a list of rows
to a ``dict`` parameter) is superseded by CA-A. E22 (per-row staleness) is
written when S5 is detailed: core has no per-row staleness to test yet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, cols, mod, stack, tool, wf


@tool
def to_f(temp: float) -> float:
    return temp * 9 / 5 + 32


@tool
def mean(temp: list[float]) -> float:
    return sum(temp) / len(temp)


@tool
def is_hot(temp: float) -> bool:
    return temp >= 38.0


@tool
def show(value: int) -> int:
    return value


@tool
def to_f_v(t: list) -> int:
    return len(t)


@tool
def add_k(n: int, k: int) -> int:
    return n + k


class Scan:
    """An object without a stable repr: its default repr holds its address."""

    def __init__(self, n: int):
        self.n = n


@tool
def scan(n: int) -> Scan:
    return Scan(n)


@tool
def scanned(value: Scan) -> int:
    return value.n


@tool
def key_pp(k: str) -> str:
    return k.lower()


TOOLS = [to_f, mean, is_hot, show, to_f_v, add_k, scan, scanned, key_pp]


@pytest.fixture
def k() -> Kernel:
    k = Kernel(Catalog(TOOLS))
    k["p"] = pd.DataFrame({"name": ["Ann", "Ben", "Cy"], "temp": [36.6, 38.2, 39.0],
                           "ward": ["A", "B", "A"]})
    return k


def values(k: Kernel, step: str, column: str | None = None) -> list:
    data = k.step(step).output.data
    data = data[[c for c in data.columns if not str(c).startswith("#")]]
    return list(data[column] if column else data.iloc[:, 0])


def refused(k: Kernel, name: str, make, mention: str = "") -> bool:
    """True if declaring or running *make* is refused (mentioning *mention*)."""
    try:
        k[name] = make()
        if not k.step(name).problems:
            k.run(name)
            return False
        said = " ".join(map(str, k.step(name).problems))
    except Exception as e:
        said = str(e)
    return mention.lower() in said.lower()


# ── laws ─────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="S3 (D8): .header becomes .keys")
def test_E6_keys_lists_a_steps_data_names():
    assert wf["p"].keys == ["name", "temp", "ward"]


def test_E7_brackets_take_ints_and_strings_only(k):
    assert refused(k, "a", lambda: wf["p"][1.5])
    assert refused(k, "b", lambda: wf["p"][None])


@pytest.mark.xfail(strict=True, reason="S3 (CA-A, N2): a bare call infers map and writes it")
def test_E8_a_column_to_a_value_parameter_is_a_call_per_row(k):
    k["f"] = to_f(wf["p"]["temp"])
    k.run("f")
    assert values(k, "f") == pytest.approx([97.88, 100.76, 102.2])
    assert "mod.map()" in str(k.step("f").formula)


@pytest.mark.xfail(strict=True, reason="S3 (CA-D1): a column to list[T] is one call, the verb written")
def test_E9_a_column_to_a_list_parameter_is_one_call(k):
    k["m"] = mean(wf["p"]["temp"])
    k.run("m")
    assert values(k, "m") == pytest.approx([(36.6 + 38.2 + 39.0) / 3])
    assert "auto" not in str(k.step("m").formula)


def test_E14_B3_a_hash_column_is_refused_as_an_argument(k):
    assert refused(k, "x", lambda: show[mod.source()](value=wf["p"][cols["#"]]), "#")


def test_E15_a_row_holds_plain_python_values():
    seen = []

    @tool
    def look(temp: float | None) -> int:
        seen.append(temp)
        return 0

    k = Kernel(Catalog([look]))
    k["p"] = pd.DataFrame({"temp": [36.6, np.nan]})
    k["x"] = look[mod.map()](wf["p"])
    k.run("x")
    assert [type(v) for v in seen] == [float, type(None)]


@pytest.mark.xfail(strict=True, reason="S3 (N2): an inferred verb is never filter")
def test_E18_a_bool_tool_with_no_verb_maps(k):
    k["h"] = is_hot(wf["p"]["temp"])
    k.run("h")
    assert values(k, "h") == [False, True, True]
    assert "filter" not in str(k.step("h").formula)


@pytest.mark.xfail(strict=True, reason="S3 (D21, B5): nothing runs that the expression doesn't show")
def test_E19_the_saved_expression_names_what_runs(k):
    k["f"] = to_f(wf["p"])
    formula = str(k.step("f").formula)
    assert "auto" not in formula and "mod.map()" in formula


def test_E20_a_list_literal_is_one_value_and_expand_makes_rows(k):
    k["xs"] = [1, 2, 3]
    k["rows"] = mod.expand()(wf["xs"])
    k.run_all()
    assert len(k.step("xs").output.data) == 1
    assert values(k, "rows") == [1, 2, 3]


@pytest.mark.xfail(strict=True, reason="S1 (B1, D31): widen names its column")
def test_E23_B1_widen_spreads_the_named_column():
    k = Kernel(Catalog([]))
    k["p"] = pd.DataFrame({"name": ["Ann"], "info": [{"age": 30, "bed": 4}]})
    k["w"] = mod.widen("info")(wf["p"])
    k.run("w")
    data = k.step("w").output.data
    assert [c for c in data.columns if not str(c).startswith("#")] == ["name", "age", "bed"]
    assert refused(k, "x", lambda: mod.widen()(wf["p"]), "info")


@pytest.mark.xfail(strict=True, reason="S1 (B2, D32): expand(columns=) takes dicts as key/value rows")
def test_E24_B2_expand_of_a_dict_column_keeps_the_others():
    k = Kernel(Catalog([]))
    k["p"] = pd.DataFrame({"name": ["Ann"], "info": [{"age": 30, "bed": 4}]})
    k["e"] = mod.expand(columns=["info"])(wf["p"])
    k.run("e")
    assert values(k, "e", "name") == ["Ann", "Ann"]


@pytest.mark.xfail(strict=True, reason="S7 (D33): melt and pivot")
def test_E25_melt_then_pivot_gives_back_the_table():
    k = Kernel(Catalog([]))
    k["p"] = pd.DataFrame({"name": ["Ann", "Ben"], "am": [1, 2], "pm": [3, 4]})
    k["long"] = mod.melt(columns=["am", "pm"], into=("when", "v"))(wf["p"])
    k["wide"] = mod.pivot(by="name", key="when", value="v")(wf["long"])
    k.run_all()
    assert values(k, "wide", "am") == [1, 2] and values(k, "wide", "pm") == [3, 4]


@pytest.mark.xfail(strict=True, reason="S6 (D23): sweep's values come in the call")
def test_E26_a_setting_never_reaches_the_tool():
    k = Kernel(Catalog([add_k]))
    k["s"] = add_k[mod.sweep("k")](n=1, k=[10, 20])
    k.run("s")
    assert values(k, "s") == [11, 21]


@pytest.mark.xfail(strict=True, reason="S3 (core-asks M4): the new picks save, reload and print back")
def test_E27_an_expression_round_trips(k):
    k["a"] = wf["p"][0:2]["name", "temp"]
    k["b"] = wf["p"][cols["temp"] > 37]
    again = Kernel.from_json(k.to_json(), Catalog(TOOLS))
    for s in ("a", "b"):
        assert str(again.step(s).formula) == str(k.step(s).formula)


# ── bugs ─────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="S1 (B4, D29): stack of an ids-only step is refused")
def test_B4_stack_of_nothing_but_ids_is_refused(k):
    assert refused(k, "s", lambda: stack(wf["p"][cols["#"]], wf["p"][cols["#"]]))


@pytest.mark.xfail(strict=True, reason="S1 (B9): # is never counted as a step's data")
def test_B9_a_hash_column_is_not_listed_as_data():
    k = Kernel(Catalog([to_f_v]))
    k["xs"] = [1, 2, 3]
    k["list"] = mod.expand()(wf["xs"])
    k.run_all()
    k["n"] = to_f_v[mod.map()](wf["list"])
    said = " ".join(map(str, k.step("n").problems))
    assert said and "#xs" not in said


@pytest.mark.xfail(strict=True, reason="S1 (B10, D57): an object's data version is stable")
def test_B10_rerunning_an_object_step_leaves_readers_fresh():
    k = Kernel(Catalog([scan, scanned]))
    k["r"] = pd.DataFrame({"n": [1, 2]})
    k["s"] = scan[mod.map()](wf["r"])
    k["t"] = scanned[mod.map()](wf["s"])
    k.run_all()
    k.run("s")
    assert k.step("t").state == "completed"


@pytest.mark.xfail(strict=True, reason="S1 (B11): a passed-through column makes its step stale")
def test_B11_a_change_to_a_passed_through_column_makes_the_step_stale():
    k = Kernel(Catalog([key_pp]))
    k["s0"] = pd.DataFrame({"k": ["A"], "n": [1]})
    k["g"] = key_pp[mod.group()](wf["s0"])
    k.run_all()
    k["s0"] = pd.DataFrame({"k": ["A"], "n": [2]})        # k, the bound column, unchanged
    assert k.step("g").state == "stale"
