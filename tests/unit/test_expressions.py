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

from simple_steps_core import Catalog, Kernel, cols, join, mod, res, row, stack, tool, wf
from simple_steps_core.operation import op


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
    """True if declaring *make* is refused, or running it fails the step
    (mentioning *mention*)."""
    try:
        k[name] = make()
        if not k.step(name).problems:
            k.run(name)
            step = k.step(name)
            if step.state != "failed":
                return False
            said = " ".join(str(n.get("error", "")) for n in step.output.notes.values())
            return mention.lower() in said.lower()
        said = " ".join(map(str, k.step(name).problems))
    except Exception as e:
        said = str(e)
    return mention.lower() in said.lower()


# ── laws ─────────────────────────────────────────────────────────────────────

def test_E6_header_stays_header(k):
    # D8 (owner, 2026-11-04): no .keys, since a cell can hold a dict's keys
    k.run_all()
    assert not hasattr(wf["p"], "keys")
    k["h"] = wf["p"].header
    k.run_all()
    assert k.step("h").data["name"].tolist() == ["name", "temp", "ward"]


def test_E7_brackets_take_ints_and_strings_only(k):
    assert refused(k, "a", lambda: wf["p"][1.5])
    assert refused(k, "b", lambda: wf["p"][None])


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


def test_E15_D17_a_gathered_list_and_the_view_hold_plain_values():
    k = Kernel(Catalog([]))
    k["p"] = pd.DataFrame({"temp": [36.6, np.nan], "n": pd.array([1, None], dtype="Int64")})
    k["t"] = wf["p"][cols["temp"]]
    k["g"] = op("gather")[mod.collapse()](wf["t"])
    k.run_all()
    gathered = k.step("g").output.data["temp"].iloc[0]
    assert [type(v) for v in gathered] == [float, type(None)]
    cells = [{c: x.get("value") for c, x in r["cells"].items()} for r in k.view("p")["rows"]]
    assert [type(v) for row in cells for v in row.values()] == [float, int, type(None), type(None)]


def test_E18_a_bool_tool_with_no_verb_maps(k):
    k["h"] = is_hot(wf["p"]["temp"])
    k.run("h")
    assert values(k, "h") == [False, True, True]
    assert "filter" not in str(k.step("h").formula)


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


def test_E23_B1_widen_spreads_the_named_column_or_the_one_dict_column():
    k = Kernel(Catalog([]))
    k["p"] = pd.DataFrame({"name": ["Ann"], "info": [{"age": 30, "bed": {"ward": "A"}}]})
    k["w"] = mod.widen("info")(wf["p"])
    k["guess"] = mod.widen()(wf["p"])                   # info is the one column holding dicts
    k.run_all()
    for s in ("w", "guess"):
        data = k.step(s).output.data
        assert [c for c in data.columns if not str(c).startswith("#")] == ["name", "age", "bed"]
        assert data["bed"].iloc[0] == {"ward": "A"}       # one layer: a nested dict stays a value
    k["two"] = pd.DataFrame({"a": [{"x": 1}], "b": [{"y": 2}]})
    assert refused(k, "x", lambda: mod.widen()(wf["two"]), "widen which column")


def test_E24_B2_expand_of_a_dict_column_keeps_the_others():
    k = Kernel(Catalog([]))
    k["p"] = pd.DataFrame({"name": ["Ann"], "info": [{"age": 30, "bed": 4}]})
    k["e"] = mod.expand(columns=["info"])(wf["p"])
    k["only"] = mod.expand(columns=["info"], keep=False)(wf["p"])
    k.run_all()
    assert values(k, "e", "name") == ["Ann", "Ann"]
    assert values(k, "e", "key") == ["age", "bed"] and values(k, "e", "info") == [30, 4]
    assert list(k.step("only").output.data.columns) == ["#p", "key", "info"]


def test_widen_and_expand_mistakes_are_problems_when_written():
    # C1: when the input's columns and types are known, these are invalid at
    # once, the fix written; they used to fail at run, the reason on a cell.
    k = Kernel(Catalog([]))
    k["two"] = pd.DataFrame({"a": [{"x": 1}], "b": [{"y": 2}], "n": [1]})
    k["keyed"] = pd.DataFrame({"info": [{"age": 30}], "key": ["K"]})
    k["w"] = mod.widen()(wf["two"])
    k["z"] = mod.widen(column="zz")(wf["two"])
    k["e"] = mod.expand(columns=["info"])(wf["keyed"])
    assert [(p.code, "mod.widen('a')" in p.message) for p in k.step("w").problems] \
        == [("missing_setting", True)]
    assert [p.code for p in k.step("z").problems] == ["missing_column"]
    assert [p.code for p in k.step("e").problems] == ["column_clash"]
    with pytest.raises(TypeError, match=r"takes a column name, not StepRef"):
        mod.widen(wf["two"])                     # the step taken for a column name (R11)


def test_widen_of_a_source_not_run_yet_is_checked_when_it_runs():
    @tool
    def records() -> pd.DataFrame:
        return pd.DataFrame({"a": [{"x": 1}], "b": [{"y": 2}]})
    k = Kernel(Catalog([records]))
    k["r"] = records[mod.source()]()
    k["w"] = mod.widen()(wf["r"])
    assert k.step("w").problems == ()            # its columns aren't known yet
    assert refused(k, "w", lambda: mod.widen()(wf["r"]), "widen which column")


def test_a_column_argument_never_becomes_or_replaces_an_output_column():
    # C3: a filter returns its input's columns, nothing else. A column argument
    # used to be handed on as a column, and to replace an input column of the
    # same name: filter(v, temp=<fahrenheit>) showed fahrenheit as v's temp.
    @tool
    def hot(temp: float, limit: float = 38) -> bool:
        return temp >= limit

    @tool
    def to_f(temp: float) -> float:
        return temp * 9 / 5 + 32
    k = Kernel(Catalog([hot, to_f]))
    k["v"] = pd.DataFrame({"name": ["Ada", "Ben"], "temp": [37.0, 38.5]})
    k["f"] = to_f[mod.map()](wf["v"])
    k["added"] = hot[mod.filter()](wf["v"], limit=wf["v"][cols["temp"]])
    k["covered"] = hot[mod.filter()](wf["v"], temp=wf["f"][cols["f"]])
    k.run_all()
    assert k.step("added").output.data.to_dict("list") == {"name": ["Ada", "Ben"], "temp": [37.0, 38.5]}
    assert values(k, "covered", "temp") == [37.0, 38.5]


def test_a_widen_field_never_replaces_a_column_unless_told():
    # C4: a field named like a column the input carries used to win, silently.
    k = Kernel(Catalog([]))
    k["s"] = pd.DataFrame({"name": ["Ada", "Ben"],
                           "c": [{"name": "X", "a": 1}, {"name": "Y", "a": 2}]})
    k["declared"] = mod.widen(column="c", columns=["name", "a"])(wf["s"])
    assert [p.code for p in k.step("declared").problems] == ["column_clash"]
    assert refused(k, "found", lambda: mod.widen(column="c")(wf["s"]), "would replace")
    del k["declared"], k["found"]
    k["told"] = mod.widen(column="c", replace=True)(wf["s"])
    k["apart"] = mod.widen(column="c", columns=["a"])(wf["s"])
    k.run_all()
    assert values(k, "told", "name") == ["X", "Y"]
    assert values(k, "apart", "name") == ["Ada", "Ben"]


def test_an_expand_with_no_tool_names_its_column_when_there_are_several():
    # C5: identity used to hand over the whole row, so every row melted into
    # key, value rows. Refused, naming the list column; one column is fine.
    @tool
    def records() -> pd.DataFrame:
        return pd.DataFrame({"name": ["Ann"], "a": [[1, 2]]})
    k = Kernel(Catalog([records]))
    k["s"] = pd.DataFrame({"name": ["Ann", "Ben"], "a": [[1], [2, 3]]})
    k["bare"] = mod.expand()(wf["s"])
    assert [(p.code, "mod.expand(columns=['a'])" in p.message)
            for p in k.step("bare").problems] == [("missing_setting", True)]
    k["r"] = records[mod.source()]()             # its columns known only by running
    assert refused(k, "later", lambda: mod.expand()(wf["r"]), "name it, mod.expand(columns=")
    del k["bare"], k["later"]
    k["named"] = mod.expand(columns=["a"])(wf["s"])
    k["one"] = [1, 2]
    k["flat"] = mod.expand()(wf["one"])
    k.run_all()
    assert values(k, "named", "a") == [1, 2, 3] and values(k, "flat", "flat") == [1, 2]


def test_no_value_means_one_thing_in_every_verb():
    # C6: None, or an absent cell, where a list or a dict belongs gives no rows
    # or absent fields, and one warning with the count; never a failed row. A
    # column argument keeps absent, so the tool gets its default.
    k = Kernel(Catalog([]))
    k["lists"] = pd.DataFrame({"name": ["Ann", "Ben"], "a": [[1, 2], None]})
    k["dicts"] = pd.DataFrame({"name": ["Ann", "Ben"], "c": [{"x": 1}, None]})
    k["e"] = mod.expand(columns=["a"])(wf["lists"])
    k["w"] = mod.widen(column="c")(wf["dicts"])
    k["p"] = pd.DataFrame({"name": ["Ann", "Ben", "Cy"]})
    k["s"] = pd.DataFrame({"name": ["Ann", "Ben"], "score": [1.0, None]})
    k["j"] = join(wf["p"], wf["s"], on="name", how="left")
    k["f"] = op("first_present")[mod.map()](wf["j"], value=wf["j"][cols["score"]], default=0.0)
    k.run_all()
    assert values(k, "e", "a") == [1, 2]
    assert [w.message for w in k.step("e").warnings] == ["1 row held no list (None, or no value): it gave no rows"]
    assert k.step("w").state == "completed" and (1, "x") in k.step("w").output.absent_cells()
    assert [w.message for w in k.step("w").warnings] == ["1 row held no dict (None, or no value): its fields are absent"]
    got = values(k, "f", "f")
    assert got[0] == 1.0 and pd.isna(got[1]) and got[2] == 0.0      # Cy's gap: the default


def test_a_filter_with_no_tool_names_its_column_when_there_are_several():
    # C5: identity handed over the whole row, which is always true, so every
    # row stayed. Refused, pointing to a pick by a condition; one column works.
    k = Kernel(Catalog([]))
    k["s"] = pd.DataFrame({"a": [True, False], "b": [0, 0]})
    k["flags"] = pd.DataFrame({"flag": [True, False]})
    k["all"] = op("identity")[mod.filter()](wf["s"])
    assert [(p.code, "wf['s'][cols['a'] == True]" in p.message)
            for p in k.step("all").problems] == [("missing_setting", True)]
    del k["all"]
    k["kept"] = op("identity")[mod.filter()](wf["flags"])
    k.run_all()
    assert values(k, "kept", "flag") == [True]


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


def test_E27_an_expression_round_trips(k):
    k["a"] = wf["p"][0:2]["name", "temp"]
    k["b"] = wf["p"][cols["temp"] > 37]
    again = Kernel.from_json(k.to_json(), Catalog(TOOLS))
    for s in ("a", "b"):
        assert str(again.step(s).formula) == str(k.step(s).formula)


# ── bugs ─────────────────────────────────────────────────────────────────────

def test_B4_stack_of_nothing_but_ids_is_refused(k):
    assert refused(k, "s", lambda: stack(wf["p"][cols["#"]], wf["p"][cols["#"]]))


def test_B9_a_hash_column_is_not_listed_as_data():
    k = Kernel(Catalog([to_f_v]))
    k["xs"] = [1, 2, 3]
    k["list"] = mod.expand()(wf["xs"])
    k.run_all()
    k["n"] = to_f_v[mod.map()](wf["list"])
    said = " ".join(map(str, k.step("n").problems))
    assert said and "#xs" not in said


def test_B10_rerunning_an_object_step_leaves_readers_fresh():
    k = Kernel(Catalog([scan, scanned]))
    k["r"] = pd.DataFrame({"n": [1, 2]})
    k["s"] = scan[mod.map()](wf["r"])
    k["t"] = scanned[mod.map()](wf["s"])
    k.run_all()
    k.run("s")
    assert k.step("t").state == "completed"


def test_B10_an_objects_version_is_its_own_then_its_fields():
    from dataclasses import dataclass

    from simple_steps_core.output import _data_version

    @dataclass
    class Point:
        x: int

    class Versioned:
        def __init__(self, v):
            self.v = v

        def data_version(self):
            return f"v{self.v}"

    def version(cell):
        return _data_version(pd.DataFrame({"c": [cell]}))

    assert version(Point(1)) == version(Point(1)) != version(Point(2))
    assert version(Versioned(1)) == version(Versioned(1)) != version(Versioned(2))
    assert version(Scan(1)) == version(Scan(1)) != version(Scan(2))


def test_two_different_values_never_share_a_version():
    # A run key matching the wrong result would show it as completed. An object
    # that can't be pickled, whose repr hides what's in it, used to version by
    # its repr: <Model> for every model. Now it gets a version of its own each
    # time, and the step says so; data_version() makes it stable.
    import threading

    from simple_steps_core.output import _data_version

    class Model:
        def __init__(self, w):
            self.w, self.lock = w, threading.Lock()

        def __repr__(self):
            return "<Model>"

    class Versioned(Model):
        def data_version(self):
            return f"w{self.w}"

    def version(cell):
        return _data_version(pd.DataFrame({"c": [cell]}))

    assert version(Model(1)) != version(Model(2))
    assert version(Model(1)) != version(Model(1))        # never reused: it re-runs
    assert version(Versioned(1)) == version(Versioned(1)) != version(Versioned(2))

    @tool
    def fit(n: int) -> object:
        return Model(n)
    k = Kernel(Catalog([fit]))
    k["v"] = pd.DataFrame({"n": [1]})
    k["m"] = fit[mod.map()](wf["v"])
    k.run_all()
    assert [w.message for w in k.step("m").warnings] == [
        "Model has no stable version: the steps that read 'm' re-run each time; "
        "give Model a data_version()"]


def test_B11_a_change_to_a_passed_through_column_makes_the_step_stale():
    k = Kernel(Catalog([key_pp]))
    k["s0"] = pd.DataFrame({"k": ["A"], "n": [1]})
    k["g"] = key_pp[mod.group()](wf["s0"])
    k.run_all()
    k["s0"] = pd.DataFrame({"k": ["A"], "n": [2]})        # k, the bound column, unchanged
    assert k.step("g").state == "stale"


def test_W15_cols_is_columns_and_saved_as_columns():
    # owner, 2026-11-09: cols= and columns= are both acceptable (core-asks L26)
    k = Kernel(Catalog([]))
    k["r"] = pd.DataFrame({"n": [10, 20, 30, 40], "ward": list("ABAB")})
    k["a"] = mod.select(rows=slice(1, 3), cols=["n"])(wf["r"])
    k["b"] = mod.select(rows=slice(1, 3), columns=["n"])(wf["r"])
    k["d"] = mod.drop(cols=["ward"])(wf["r"])
    k.run_all()
    assert values(k, "a") == values(k, "b") == [20, 30]
    assert str(k.step("a").formula) == str(k.step("b").formula).replace("'b'", "'a'")
    assert "cols=" not in str(k.step("a").formula)
    assert list(k.step("d").output.data.columns) == ["n"]
    with pytest.raises(TypeError, match="cols= or columns="):
        mod.select(cols=["n"], columns=["n"])


@tool
def twice_px(n: int) -> int:
    return n * 2


def test_L34_a_column_pick_as_input_decides_the_binding():
    # D6's main form, to_f(wf["p"]["temp"]): two int columns fit, the pick says which
    k = Kernel(Catalog([twice_px]))
    k["r"] = pd.DataFrame({"n": [1, 2, 3], "m": [7, 8, 9]})
    k["d"] = twice_px[mod.map()](wf["r"]["m"])
    assert k.step("d").problems == ()
    k.run_all()
    assert values(k, "d") == [14, 16, 18]
    # the pick prints as written; the binding by type is written too (W10)
    assert str(k.step("d").formula) == 'twice_px[mod.map()](wf["r"][cols["m"]], n=wf["r"][cols["m"]])'


def test_L33_pickers_run_before_the_verb_and_the_plan_knows_the_rows():
    k = Kernel(Catalog([twice_px]))
    k["r"] = pd.DataFrame({"n": [30, 10, 20]})
    k.run("r")
    k["s"] = twice_px[mod.sort(by="n"), mod.slice(start=0, stop=2), mod.map()](wf["r"])
    assert len(k.step("s").output.data) == 2                   # planned: the rows the pickers leave
    k.run("s")
    assert values(k, "s") == [20, 40]
    assert k.workflow.lineage("s") == {"#r": [1, 2]}           # rows 1 and 2 of r, in n's order


def test_L33_distinct_before_a_verb_is_a_step_of_its_own():
    k = Kernel(Catalog([twice_px]))
    k["r"] = pd.DataFrame({"n": [1, 1, 2]})
    k["d"] = twice_px[mod.distinct(), mod.map()](wf["r"])
    assert "at most one is allowed" in str(k.step("d").problems[0])


def test_EX9_a_plain_function_is_refused_as_a_value():
    k = Kernel(Catalog([]))
    with pytest.raises(TypeError, match="@tool"):
        k["fn"] = lambda temp: temp
    assert "fn" not in k
    k["n"] = 3                                                    # a value still is one
    assert k.step("n").state == "completed"


def test_EX12_a_lineage_condition_isnt_positional_a_range_is():
    k = Kernel(Catalog([]))
    k["l"] = pd.DataFrame({"xs": [[1, 2], [3]]})
    k["e"] = mod.expand(columns=["xs"])(wf["l"])
    k["kid"] = wf["e"][row["l"] == 0]
    k["pos"] = wf["e"][0:2]
    assert not any("positions" in str(w) for w in k.step("kid").warnings)
    assert any("positions" in str(w) for w in k.step("pos").warnings)


# ── S12, core asks 012: formula text ─────────────────────────────────────

def test_C42_20_a_step_reference_is_not_iterable():
    """012 #20: `list(wf["s"])` iterated `wf["s"][0]`, `[1]`, … forever (no
    __iter__, so Python fell back to __getitem__). Now it is refused at once."""
    with pytest.raises(TypeError, match="not a list"):
        list(wf["s"])
    with pytest.raises(TypeError):
        list(res["db"])


@pytest.mark.parametrize("on, says", [
    ('wf["s"]', "settings are literals"),
    ('res["db"]', "takes no resource"),
    ('[wf["s"]]', "settings are literals"),
])
def test_C42_20_join_on_takes_column_names_only(on, says):
    """012 #19, #20: a step or resource in join(on=…) is refused when the join
    is built, from Python and from formula text, and nothing hangs."""
    from simple_steps_core import formula
    with pytest.raises(TypeError, match=says):
        join(wf["s"], wf["t"], on=eval(on, {"wf": wf, "res": res}))
    with pytest.raises(ValueError, match=says):
        formula(f'join(wf["s"], wf["t"], on={on})')


from simple_steps_core import resource  # noqa: E402


@resource
class LLM:
    def __init__(self, name: str = "tiny"):
        self.name = name


@tool
def summarize(text: str, llm: LLM) -> str:
    return f"{llm.name}:{text[:3]}"


@tool
def notes() -> pd.DataFrame:
    return pd.DataFrame({"text": ["alpha", "beta"]})


def _llm_kernel():
    k = Kernel(Catalog(tools=[notes, summarize], resources=[LLM]))
    k["s"] = notes[mod.source()]()
    k.define("tiny", LLM)
    return k, summarize


def test_C40_a_resource_by_position_in_formula_text_binds_as_in_python():
    """012 C40: the Python line is accepted and saved as llm=res["tiny"]; the
    same line as formula text was refused. Now both save the same step."""
    from simple_steps_core import formula
    k, summarize = _llm_kernel()
    k["py"] = summarize[mod.map()](wf["s"], res["tiny"])
    k["summary"] = formula('summarize[mod.map()](wf["s"], res["tiny"])')
    assert k.step("summary").formula == k.step("py").formula \
        == 'summarize[mod.map()](wf["s"], llm=res["tiny"])'
    k.run("summary")
    assert list(k.step("summary").output.data["summary"]) == ["tiny:alp", "tiny:bet"]
    assert formula(k.step("summary").formula) == formula('summarize[mod.map()](wf["s"], llm=res["tiny"])')


def test_C40_a_held_resource_with_a_tool_core_cant_see_is_refused():
    """A tool not in the catalog has no parameters to bind to: refused when
    assigned, saying to pass it by keyword, never saved half-bound."""
    from simple_steps_core import formula
    k, _ = _llm_kernel()
    with pytest.raises(TypeError, match="by keyword"):
        k["x"] = formula('nowhere[mod.map()](wf["s"], res["tiny"])')


@tool
def first_letter(city: str) -> str:
    return city[0]


@tool
def towns() -> pd.DataFrame:
    return pd.DataFrame({"n": [2, 1], "city": ["b", "a"]})


def _towns_kernel():
    k = Kernel(Catalog(tools=[towns, first_letter, dbl_n]))
    k["s"] = towns[mod.source()]()
    return k


@tool
def dbl_n(n: int) -> int:
    return 2 * n


@pytest.mark.parametrize("text, says", [
    ('mod.slice(start=n)(wf["s"])', 'mod.slice(start=n): text needs quotes, "n"'),
    ('mod.expand(columns=[n])(wf["s"])', 'mod.expand(columns=[n]): text needs quotes, "n"'),
    ('join(wf["s"], wf["t"], on=n)', 'join(on=n): text needs quotes, "n"'),
    ('join(wf["s"], wf["t"], on=[n, "city"])', 'join(on=[n, \'city\']): text needs quotes, "n"'),
    ('dbl_n[mod.map()](wf["s"], n=x)', 'n=x: x is not defined. A step is wf["x"]; text is "x"'),
    ('dbl_n[mod.map()](s)', 's is not defined. To use the step "s", write wf["s"]'),
])
def test_C41_a_bare_name_is_refused_while_reading(text, says):
    """012 C41, #21, #28, #32: a bare name is a tool only where a tool goes."""
    from simple_steps_core import formula
    with pytest.raises(ValueError) as caught:
        formula(text)
    assert says in str(caught.value)


def test_C41_a_bare_name_in_a_setting_that_takes_a_tool_is_that_tool():
    """mod.sort(by=first_letter) as text is the same step as in Python, and
    round-trips; a name that isn't a tool says to quote it."""
    from simple_steps_core import formula
    k = _towns_kernel()
    k["py"] = mod.sort(by=first_letter)(wf["s"])
    k["text"] = formula('mod.sort(by=first_letter)(wf["s"])')
    assert k.step("text").formula == k.step("py").formula == 'mod.sort(by=first_letter)(wf["s"])'
    k.run("text")
    assert list(k.step("text").output.data["city"]) == ["a", "b"]
    k["bad"] = formula('mod.sort(by=n)(wf["s"])')
    said = " ".join(k.step("bad").problems)
    assert 'by=n: n is not a tool; text needs quotes, by="n"' in said
    assert "<Operation" not in k.step("bad").formula
