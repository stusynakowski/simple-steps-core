"""The app's 008 asks (docs/core-proposals/008-core-changes.md), one test each.

Each test is the ask's "Done when" line, so a fix can't regress after the app
adopts it. scripts/core_asks.py runs the same checks as probes.
"""

import json
import warnings

import pandas as pd
import pytest

from simple_steps_core import (
    bound_tool,
    Catalog,
    cols,
    join,
    mod,
    Operation,
    Output,
    res,
    rows,
    tool,
    wf as unbound_wf,
    zip_,
)
from simple_steps_core.catalog import (
    builtin_tools,
    catalog,
    check_modifier,
    formula_names,
    shape_verbs,
    value_column,
)
from simple_steps_core.checks import check, columns_unknown, infer_verb
from simple_steps_core.combines import _combine_zip
from simple_steps_core.errors import PayloadError, SelectionError, StepFailed
from simple_steps_core.modifiers import modifier_catalog
from simple_steps_core.operation import op
from simple_steps_core.output import ROW_ID, STATES
from simple_steps_core.references import _encode_ref
from simple_steps_core.verbs import collapse_, grid, map_
from simple_steps_core.workflow import Workflow

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
    # slice carries its input's columns, so it inherits "not known yet".
    # (A map step is only its results, so its columns are always known.)
    w["head"] = mod.slice(stop=4)(w["readings"])
    w["picked"] = mod.select(over=w["head"], columns=["city", "n"])
    w["typo"] = mod.select(over=w["head"], columns=["cty"])
    assert w.step("picked").problems == () and w.step("typo").problems == ()
    assert columns_unknown(w.step("head").output)
    w.run_all()
    assert w.step("picked").output.data.to_dict("list") == {
        "city": ["SF", "NYC", "SF", "LA"], "n": [1, 2, 3, 2]}
    # the deferred check is decided once the source has run — a real typo fails
    assert "names 'cty'" in w.step("typo").problems[0]


def test_K1_a_literal_source_has_known_columns(wf):
    assert not columns_unknown(wf.step("readings").output)
    wf["typo"] = mod.select(over=wf["readings"], columns=["cty"])
    assert "names 'cty'" in wf.step("typo").problems[0]


def test_K2_inference_does_not_depend_on_run_state(wf):
    wf["x"] = add_008(wf["readings"])
    unrun = Workflow()
    unrun["readings"] = to_rows_008.bind(data=DATA)[mod.source()]
    unrun["x"] = add_008(unrun["readings"])
    kinds = [w.step("x").output.meta["auto"]["verb"] for w in (wf, unrun)]
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


def test_N2_an_explicit_argument_beats_a_same_named_column_with_a_warning(wf):
    wf["x"] = tag_008[mod.map()](wf["readings"], city="NYC")
    assert wf.step("x").problems == ()              # allowed: it may be deliberate
    assert wf.step("x").warnings[0] == (
        "city='NYC' overrides the 'city' column of 'readings' for every row; "
        "drop the argument to use the column")
    wf.run("x")
    assert wf.step("x").output.values == ["NYC"] * 4
    wf["y"] = tag_008[mod.map()](wf["readings"])     # no argument, no warning
    assert not any("overrides" in w for w in wf.step("y").warnings)


def test_C13_an_output_never_silently_replaces_an_input_column(wf):
    """map and expand output only what the tool produced (owner, 2026-10-20),
    so they can't replace an input column. group carries its input's columns
    and adds its key (owner, 2026-10-27), so a key named like an input column
    is refused, unless replace=True says to replace it."""
    @tool
    def twice_008(n) -> list:
        return [n, n]
    wf["m"] = dbl_008[mod.map(name="n")](wf["readings"])
    wf["e"] = twice_008[mod.expand()](wf["readings"])
    wf["clash"] = dbl_008[mod.group(name="n")](wf["readings"])
    wf["g"] = dbl_008[mod.group(name="n", replace=True)](wf["readings"])
    assert [p.code for p in wf.step("clash").problems] == ["column_clash"]
    assert "group's key 'n' would replace the 'n' column" in wf.step("clash").problems[0]
    wf.remove("clash")
    wf.run_all()
    for sid, columns in (("m", ["n"]), ("e", ["value"]), ("g", ["city", "n"])):
        assert wf.step(sid).problems == ()
        assert list(wf.step(sid).output.data.columns) == columns, sid
    assert list(wf.step("g").output.data["n"]) == [2, 4, 6, 4]           # the key
    assert list(wf.step("readings").output.data["n"]) == [1, 2, 3, 2]   # untouched


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
    blob = {"tool": "scale_008", "input": None, "arguments": {},
            "modifiers": [{"kind": "retry", "settings": {}}, {"kind": "map", "settings": {}}]}
    problems = check(Operation.from_dict(blob, {"scale_008": scale_008.fn}))
    assert problems == ("retry needs times= — it has no default, so a step "
                        "without it cannot run",)
    assert check(scale_008[mod.timeout()]) == (
        "timeout needs seconds= — it has no default, so a step without it "
        "cannot run",)


def test_C6_the_same_formula_resolves_in_whichever_workflow():
    w1, w2 = Workflow(), Workflow()
    w1["r"] = pd.DataFrame({"n": [1, 2]})
    w2["r"] = pd.DataFrame({"n": [7, 8]})
    line = scale_008[mod.map()](unbound_wf["r"])
    for w in (w1, w2):
        w["x"] = line
        w.run("x")
    assert w1.step("x").output.values == [10, 20]
    assert w2.step("x").output.values == [70, 80]
    assert w1.to_dict()["steps"][1]["operation"]["input"] == {"$ref": "r"}


def test_C6_grid_wf_is_a_reference_not_a_workflow():
    with pytest.raises(KeyError):
        unbound_wf[0]
    with pytest.raises(AttributeError, match="not a workflow"):
        unbound_wf.run


def test_K5_a_string_over_is_refused_in_python():
    with pytest.raises(TypeError, match=r"pass wf\['readings'\]"):
        mod.map(over="readings")
    # JSON keeps string ids
    op_ = Operation.from_dict({"tool": "scale_008", "input": "readings",
                                    "arguments": {}, "modifiers": [{"kind": "map", "settings": {}}]})
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
    cat = modifier_catalog()
    assert (cat["map"]["takes_tool"], cat["map"]["default_tool"]) == (True, None)
    assert (cat["select"]["takes_tool"], cat["select"]["default_tool"]) == (False, "identity")
    assert (cat["collapse"]["takes_tool"], cat["collapse"]["default_tool"]) == ("optional", "gather")
    assert cat["retry"]["takes_tool"] is None


# ── Phase 2: failure as state (C10), missing is None (C14), R8 ─────────
CALLS = {"plus1": 0, "total": 0}


@tool
def risky_008(n: int) -> int:
    if n == 2:
        raise ValueError("boom")
    return n * 100


@tool
def plus1_008(value: int) -> int:
    CALLS["plus1"] += 1
    return value + 1


@tool
def total_008(acc, value):
    CALLS["total"] += 1
    return (acc or 0) + value


@tool
def is_pos_008(value: int) -> bool:
    return value > 0


@pytest.fixture()
def failing():
    for k in CALLS:
        CALLS[k] = 0
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1, 2, 3]})
    # try_except: let a's failures through, so they flow downstream as state
    # (without it, run_all stops at `a` — see the try_except tests below).
    w["a"] = risky_008[mod.map(), mod.try_except()](w["r"])
    return w


def test_C10_a_bad_reference_is_a_declaration_problem_that_names_its_root():
    w = Workflow()
    w["a"] = scale_008[mod.map()](w["nope"])          # no KeyError
    w["c"] = scale_008[mod.map()](w["a"])
    assert w.step("a").state == "invalid"
    assert "not an earlier step" in w.step("a").problems[0]
    assert "root cause: a: input 'nope'" in w.step("c").problems[0]
    assert w.root_cause("c") == ("a", "input 'nope', which is not an earlier step")


def test_C10_a_forward_reference_says_it_comes_after():
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1, 2]})
    w["a"] = scale_008[mod.map()](w["r"], weight=w["w"])
    w["w"] = 2
    assert w.step("a").problems == (
        "argument 'weight' 'w' comes after 'a'; a step can only read earlier steps",)


def test_R8_C10_a_failed_cell_keeps_the_type_and_blocks_its_row(failing):
    failing["b"] = plus1_008[mod.map()](failing["a"])
    failing.run_all()
    a, b = failing.step("a").output, failing.step("b").output
    assert str(a.data["value"].dtype) == "Int64"          # not float64
    assert a.values == [100, None, 300]
    assert failing.step("b").problems == ()               # not refused as float
    assert b.values == [101, None, 301]
    assert CALLS["plus1"] == 2                            # never called for row 1
    assert b.row_states[1] == "blocked"                   # the tool wasn't called
    assert b.notes[1] == {"error": "upstream cell a[1] failed",
                          "cause": "a[1]: ValueError: boom"}


def test_C10_the_root_cause_travels_through_every_verb(failing):
    failing["kept"] = is_pos_008[mod.filter()](failing["a"])
    failing["ordered"] = mod.sort(by="value", ascending=False)(failing["a"])
    failing["sum"] = total_008[mod.collapse(initial=0)](failing["a"])
    failing["again"] = plus1_008[mod.map()](failing["kept"])
    failing.run_all()
    for sid in ("kept", "ordered", "again"):
        out = failing.step(sid).output
        assert out.row_states[1] == "blocked", sid
        assert out.notes[1]["cause"] == "a[1]: ValueError: boom", sid
    assert 1 in failing.step("kept").output.data.index    # carried, not filtered
    assert failing.step("sum").output.values == [None]
    assert CALLS["total"] == 0                            # the reducer never ran


def test_C10_an_argument_with_a_failed_cell_blocks_every_row(failing):
    @tool
    def use_008(n: int, table=None) -> int:
        CALLS["plus1"] += 1
        return n
    failing["u"] = use_008[mod.map()](failing["r"], table=failing["a"])
    failing.run_all()
    assert failing.step("u").output.values == [None, None, None]
    assert CALLS["plus1"] == 0
    assert {n["cause"] for n in failing.step("u").output.notes.values()} == {
        "a[1]: ValueError: boom"}


def test_C10_fixing_the_root_marks_what_it_blocked_stale(failing):
    """009 decision 3: stale means an input's data really changed."""
    failing["b"] = plus1_008[mod.map()](failing["a"])
    failing.run_all()
    failing.run("a")                                   # same result: still fresh
    assert failing.step("b").state != "stale"
    failing["a"] = risky_008[mod.map(), mod.try_except(default=0)](failing["r"])
    failing.run("a")                                   # the fix changes a's data
    assert failing.step("b").state == "stale"
    assert failing.step("b").output.values == [101, None, 301]   # old data kept


def test_C14_missing_is_none_and_nullability_is_checked():
    @tool
    def inc_opt_008(n: int | None) -> int:
        return 1 if n is None else n + 1

    @tool
    def inc_008(n: int) -> int:
        return n + 1

    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1, None, 3]})
    w["o"] = inc_opt_008[mod.map()](w["r"])
    w["i"] = inc_008[mod.map()](w["r"])
    w.run_all()
    assert str(w.step("r").output.data["n"].dtype) == "Int64"
    assert w.step("o").output.values == [2, 1, 4]
    assert str(w.step("o").output.data["value"].dtype) == "int64"
    assert w.step("i").problems == (
        "r.n can be None, but inc_008() takes n: int; accept int | None, or "
        "filter the Nones first",)


# ── Phase 3: saved format v2 — C11, C1, C2, C7 (K9), K17 ────────────────
import datetime  # noqa: E402

from _module_tools import module_tools  # noqa: E402

#: This module's tools, by name: what reloading a saved workflow needs.
TOOLS_008 = module_tools(globals())



def _reload(w):
    return Workflow.from_json(w.to_session_json(), TOOLS_008)


@pytest.mark.parametrize("value", [
    3, 2.5, "x", True, None, [1, 2], {"k": [1, {"z": None}]},
    (1, 2), {1: "one"}, {1, 2}, {"$ref": "not a ref"}, ((1, 2), frozenset({3})),
])
def test_C11_every_literal_round_trips_with_its_type(wf, value):
    wf["s"] = scale_008.bind(weight=value)[mod.map()](wf["readings"])
    back = _reload(wf).step("s").operation.arguments["weight"]
    assert back == value and type(back) is type(value)


def test_C11_a_non_literal_is_refused_at_declaration(wf):
    wf["d"] = scale_008.bind(weight=datetime.date(2024, 1, 1))[mod.map()](wf["readings"])
    assert wf.step("d").problems == (
        "weight: a date isn't a literal; pass a str ('2024-01-01'), or make it a step",)


def test_K17_v5_is_written_and_other_versions_are_refused_clearly(wf):
    """Files from before the redesign aren't loaded (decided 2026-10-26)."""
    assert json.loads(wf.to_json())["version"] == 5
    v4 = {"version": 5, "steps": [{"name": "r", "operation": {
        "tool": "scale_008", "input": None, "arguments": {"weight": 2},
        "modifiers": [{"kind": "map", "settings": {}}]}}]}
    loaded = Workflow.from_dict(v4, TOOLS_008)
    assert loaded.step("r").operation.arguments == {"weight": 2}
    for older in (1, 2, 3, 4):
        with pytest.raises(ValueError, match="before the redesign; this core reads version 5"):
            Workflow.from_dict({**v4, "version": older})
    with pytest.raises(ValueError, match="this core reads version 5. Upgrade"):
        Workflow.from_dict({**v4, "version": 6})


def test_C1_a_reference_in_a_setting_resolves_and_goes_stale(wf):
    wf["cols"] = ["city"]
    wf["s"] = op("identity")[mod.select(columns=wf["cols"])](wf["readings"])
    wf.run_all()
    assert wf.step("s").output.data.to_dict("list") == {"city": ["SF", "NYC", "SF", "LA"]}
    wf["cols"] = ["n"]
    assert wf.step("s").state == "stale"
    assert _reload(wf).step("s").operation == wf.step("s").operation


def test_C1_positional_arguments_bind_like_keywords(wf):
    wf["w"] = 2
    assert scale_008(wf["readings"], wf["w"]) == scale_008(wf["readings"], weight=wf["w"])


def test_C1_a_reference_arrives_in_the_shape_its_type_asks_for(wf):
    @tool
    def g_008(n, vals: list) -> int:
        return n + sum(vals)

    @tool
    def h_008(n, vals: int) -> int:
        return n

    wf["col"] = pd.DataFrame({"v": [10, 20]})
    wf["g"] = g_008[mod.map()](wf["readings"], vals=wf["col"])
    wf["h"] = h_008[mod.map()](wf["readings"], vals=wf["col"])
    assert "is a column; to pair its rows" in wf.step("h").problems[0]
    wf.run("g")
    assert wf.step("g").output.values == [31, 32, 33, 32]


def test_C2_a_tool_in_a_setting_runs_and_round_trips(wf):
    @tool
    def neg_n_008(n):
        return -n

    @tool
    def first_letter_008(city):
        return city[0]

    wf["s"] = op("identity")[mod.sort(by=neg_n_008)](wf["readings"])
    wf["c"] = add_008[mod.collapse(by=first_letter_008, initial=0)](wf["readings"])
    wf.run_all()
    assert list(wf.step("s").output.data["n"]) == [3, 2, 2, 1]
    assert wf.step("c").output.data.to_dict("list") == {
        "first_letter_008": ["S", "N", "L"], "value": [4, 2, 2]}
    assert json.loads(wf.to_json())["steps"][1]["operation"]["modifiers"][0]["settings"] == {
        "by": {"$tool": "neg_n_008"}}
    # The tools are defined here, not at the top of the module, so they are
    # named when reloading: nothing is registered to find them by (K24).
    back = Workflow.from_json(wf.to_session_json(),
                              {**TOOLS_008, "neg_n_008": neg_n_008,
                               "first_letter_008": first_letter_008})
    back.run("s")
    assert list(back.step("s").output.data["n"]) == [3, 2, 2, 1]
    by = next(x for x in modifier_catalog()["sort"]["settings"] if x["name"] == "by")
    assert by["type"].endswith("| tool")


def test_C2_a_lambda_runs_but_cannot_be_saved(wf):
    wf["s"] = op("identity")[mod.sort(by=lambda n: -n)](wf["readings"])
    with pytest.raises(PayloadError, match="register it with @tool"):
        wf.to_json()


@pytest.fixture()
def prices():
    w = Workflow()
    w["p"] = pd.DataFrame({"name": list("abcde"), "qty": [1, 2, 3, 4, 5],
                           "price": [10.0, 20.0, 30.0, 40.0, 50.0]})
    w["o"] = pd.DataFrame({"n": [1, 2]})
    return w


def test_C7_selections_as_steps(prices):
    prices["block"] = prices["p"][1:3][cols["name":"price"]]
    prices["by_pos"] = prices["p"][1:3][cols[0:2]]
    prices["cell"] = prices["p"][4][cols["price"]]          # row id 4
    prices["last"] = prices["p"][-1:][cols["price"]]        # the last row, by position
    prices.run_all()
    assert prices.step("block").output.data.to_dict("list") == {
        "name": ["b", "c"], "qty": [2, 3], "price": [20.0, 30.0]}
    assert list(prices.step("block").output.data.index) == [1, 2]   # ids kept
    assert prices.step("by_pos").output.data.to_dict("list") == {"name": ["b", "c"], "qty": [2, 3]}
    assert prices.step("cell").output.data.to_dict("list") == {"price": [50.0]}
    assert prices.step("last").output.data.to_dict("list") == {"price": [50.0]}


def test_C7_every_spelling_saves_identically(prices):
    a = prices["p"][1:3][cols["name":"price"]]
    b = prices["p"][cols["name":"price"], 1:3]
    c = prices["p"][rows[1:3], cols["name":"price"]]
    assert a == b == c
    assert _encode_ref(a) == {"$ref": "p", "rows": {"start": 1, "stop": 3},
                                   "columns": {"from": "name", "to": "price"}}


def test_C7_a_selection_as_an_argument_converts_by_type(prices):
    @tool
    def total_l_008(n, prices: list) -> float:
        return n + sum(prices)

    @tool
    def total_f_008(n, prices: float) -> float:
        return n + prices

    prices["l"] = total_l_008[mod.map()](prices["o"], prices=prices["p"][cols["price"]])
    prices["f"] = total_f_008[mod.map()](prices["o"], prices=prices["p"][cols["price"]])
    prices.run("l")
    assert prices.step("l").output.values == [151.0, 152.0]      # a list: the whole column
    # K19: a float takes one value per row, from the row with the same id.
    assert prices.step("f").problems == ()
    prices.run("f")
    assert prices.step("f").output.values == [11.0, 22.0]


def test_C7_refusals(prices):
    with pytest.raises(SelectionError, match=r"cols\['price'\]"):
        prices["p"]["price"]
    with pytest.raises(SelectionError, match="names or positions"):
        cols[["name", 2]]
    with pytest.raises(SelectionError, match="already has its rows"):
        prices["p"][1:5][2]
    with pytest.raises(SelectionError, match="empty"):
        prices["p"][[]]
    with pytest.raises(TypeError, match="can't be a tool's input"):
        scale_008[mod.map()](prices["p"][1:3])
    prices["far"] = prices["p"][9]
    assert prices.step("far").problems == (
        "select: 'p' has no row 9 (its row ids are 0, 1, 2, 3, 4)",)


def test_C7_column_names_are_strings():
    w = Workflow()
    w["y"] = pd.DataFrame({2023: [1, 2], 2024: [3, 4]})
    assert list(w.step("y").output.data.columns) == ["2023", "2024"]
    with pytest.raises(SelectionError, match="both become '1'"):
        w["clash"] = pd.DataFrame({1: [1], "1": [2]})


def test_C7_rows_and_cols_are_reserved():
    with pytest.raises(ValueError, match="reserved for row selection"):
        tool(id="rows")(lambda n: n)

    def declare_with_own_rows():
        rows = [10, 20, 30]  # noqa: F841 — the shadowing being refused
        Workflow()["x"] = 1

    with pytest.raises(TypeError, match="Rename your variable"):
        declare_with_own_rows()


def test_K9_select_takes_rows_and_columns(wf):
    wf["x"] = op("identity")[mod.select(columns=["n"], rows=[0, 2])](wf["readings"])
    wf.run("x")
    assert wf.step("x").output.data.to_dict("list") == {"n": [1, 3]}


# ── Phase 4 (first slice): an unrun source says what it will produce ────
from typing import Annotated, TypedDict  # noqa: E402


class Readings008(TypedDict):
    city: str
    n: int


@tool
def load_typed_008(path: str) -> Annotated[pd.DataFrame, Readings008]:
    return pd.DataFrame({"city": ["SF", "NYC"], "n": [1, 2]})


@tool
def load_raw_008(path: str) -> pd.DataFrame:
    return pd.DataFrame({"city": ["SF", "NYC"], "n": [1, 2], "extra": [0, 0]})


@tool
def shout_008(city: int) -> int:
    return city


def test_C5_a_typed_source_stages_its_columns_and_types_but_not_its_rows():
    w = Workflow()
    w["r"] = load_typed_008[mod.source()](path="x")
    plan = w.step("r").plan
    assert plan["columns"] == {"certainty": "exact", "names": ["city", "n"]}
    assert plan["types"] == {"city": "str", "n": "int"}
    assert plan["rows"]["certainty"] == "unknown"
    assert "run load_typed_008" in plan["rows"]["resolve"]
    assert w.step("r").describe() == (
        "source load_typed_008 · columns city (str), n (int) · rows unknown until it runs")
    assert list(w.step("r").output.data.columns) == ["city", "n"]


def test_C5_declared_columns_and_types_are_checked_before_the_source_runs():
    w = Workflow()
    w["r"] = load_typed_008[mod.source()](path="x")
    w["typo"] = mod.select(columns=["cty"])(w["r"])              # columns are known
    w["typed"] = shout_008[mod.map()](w["r"])                     # city is a str
    w["fine"] = scale_008[mod.map()](w["r"])
    assert "names 'cty'" in w.step("typo").problems[0]
    assert w.step("typed").problems == (
        "shout_008() declares city: int, but 'r' will have city as str",)
    assert w.step("fine").plan["types"] == {"value": "any"}       # only its results


def test_C5_a_source_that_breaks_its_declared_columns_fails():
    @tool
    def liar_008(path: str) -> Annotated[pd.DataFrame, Readings008]:
        return pd.DataFrame({"town": ["SF"]})
    w = Workflow()
    w["r"] = liar_008[mod.source()](path="x")
    w.run("r")
    assert w.step("r").state == "failed"
    assert w.step("r").output.notes[0]["error"] == (
        "liar_008 declares columns city, n; it returned town")


def test_C9_some_columns_stated_rows_unknown():
    w = Workflow()
    w["r"] = load_raw_008[mod.source(), mod.expect(columns={"city": str},
                                                   more_columns=True)](path="x")
    plan = w.step("r").plan
    assert plan["columns"] == {"certainty": "stated", "names": ["city"], "more": True}
    assert plan["types"] == {"city": "str"}
    assert w.step("r").describe() == (
        "source load_raw_008 · columns city (str) + maybe more (stated) · "
        "rows unknown until it runs")
    w["later"] = mod.select(columns=["extra"])(w["r"])           # may still arrive
    assert w.step("later").problems == ()
    w.run_all()
    assert w.step("later").output.data.to_dict("list") == {"extra": [0, 0]}
    back = Workflow.from_json(w.to_json(), TOOLS_008)            # saved as names
    assert back.step("r").plan["types"] == {"city": "str"}


def test_C9_an_undeclared_source_says_how_to_resolve_its_columns():
    w = Workflow()
    w["r"] = load_raw_008[mod.source()](path="x")
    columns = w.step("r").plan["columns"]
    assert columns["certainty"] == "unknown" and columns["names"] == []
    assert any("Annotated[pd.DataFrame" in r for r in columns["resolve"])
    assert any("mod.expect(columns=" in r for r in columns["resolve"])
    assert w.step("r").describe() == (
        "source load_raw_008 · columns unknown until it runs · rows unknown until it runs")


def test_C9_stated_rows_stage_and_are_checked_at_run(wf):
    w = Workflow()
    w["r"] = load_typed_008[mod.source(), mod.expect(rows=12)](path="x")
    assert w.step("r").plan["rows"] == {"certainty": "stated", "count": 12}
    assert w.step("r").output.meta["expected"] == 12
    w.run("r")
    assert w.step("r").output.notes[0]["error"] == "expected 12 rows, got 2"
    wf["kept"] = op("identity")[mod.filter(), mod.expect(rows=10)](wf["readings"])
    assert "at most 4 rows; expect(rows=10) can't hold" in wf.step("kept").problems[0]
    wf["empty"] = scale_008[mod.map(), mod.expect()](wf["readings"])
    assert "expect needs rows=" in wf.step("empty").problems[0]


def test_C9_a_step_that_ran_has_an_exact_plan(wf):
    assert wf.step("readings").plan == {
        "rows": {"certainty": "exact", "count": 4},
        "columns": {"certainty": "exact", "names": ["city", "n"]},
        "types": {"city": "str", "n": "int"}}


# ── A failure stops the run, unless the step catches it (mod.try_except) ──
@pytest.fixture()
def two_branches():
    for k in CALLS:
        CALLS[k] = 0
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1, 2, 3]})
    w["ok"] = scale_008[mod.map()](w["r"])                 # runs before the failure
    return w


def test_an_uncaught_failure_stops_run_all(two_branches):
    w = two_branches
    w["a"] = risky_008[mod.map()](w["r"])
    w["b"] = plus1_008[mod.map()](w["a"])
    w["other"] = scale_008[mod.map()](w["r"], weight=2)    # independent branch
    with pytest.raises(StepFailed) as stopped:
        w.run_all()
    err = stopped.value
    assert (err.step_id, err.cell, err.error) == ("a", 1, "ValueError: boom")
    assert "b" in err.not_run and "The run stopped" in str(err)
    assert w.step("ok").state == "completed"              # kept
    assert w.step("b").state == "staged" and CALLS["plus1"] == 0


def test_a_single_run_records_the_failure_without_raising(two_branches):
    w = two_branches
    w["a"] = risky_008[mod.map()](w["r"])
    w.run("a")
    assert w.step("a").state == "failed"


def test_try_except_with_a_default_completes_the_row(two_branches):
    w = two_branches
    w["a"] = risky_008[mod.map(), mod.try_except(default=0)](w["r"])
    w["b"] = plus1_008[mod.map()](w["a"])
    w.run_all()
    a = w.step("a").output
    assert a.values == [100, 0, 300] and w.step("a").state == "completed"
    assert a.notes[1] == {"error": "caught ValueError: boom; used the default",
                          "caught": True}
    assert a.row_states[1] == "known"                     # completed with the default
    assert w.step("b").output.values == [101, 1, 301]


def test_try_except_without_a_default_lets_the_run_continue(two_branches):
    w = two_branches
    w["a"] = risky_008[mod.map(), mod.try_except()](w["r"])
    w["b"] = plus1_008[mod.map()](w["a"])
    w.run_all()                                            # does not raise
    assert w.step("a").state == "failed"
    assert w.step("b").output.notes[1]["cause"] == "a[1]: ValueError: boom"
    assert CALLS["plus1"] == 2


def test_try_except_default_none_is_a_value_not_no_default(two_branches):
    w = two_branches
    w["a"] = risky_008[mod.map(), mod.try_except(default=None)](w["r"])
    w.run_all()
    assert w.step("a").state == "completed"
    assert w.step("a").output.values == [100, None, 300]


def test_try_except_on_catches_only_the_named_exceptions(two_branches):
    w = two_branches
    w["a"] = risky_008[mod.map(), mod.try_except(default=0, on=[KeyError])](w["r"])
    with pytest.raises(StepFailed, match="ValueError: boom"):
        w.run_all()
    w["a"] = risky_008[mod.map(), mod.try_except(default=0, on=[ValueError])](w["r"])
    w.run_all()
    assert w.step("a").output.values == [100, 0, 300]


def test_try_except_saves_its_settings_by_name(two_branches):
    w = two_branches
    w["a"] = risky_008[mod.map(), mod.try_except(default=0, on=[ValueError])](w["r"])
    saved = json.loads(w.to_json())["steps"][-1]["operation"]["modifiers"]
    assert {"kind": "try_except", "settings": {"default": 0, "on": ["ValueError"]}} in saved
    back = Workflow.from_json(w.to_session_json(), TOOLS_008)
    back.run_all()
    assert back.step("a").output.values == [100, 0, 300]


def test_a_failing_source_stops_the_run_or_is_caught():
    @tool
    def broken_008(path: str) -> pd.DataFrame:
        raise OSError("no such file")

    w = Workflow()
    w["src"] = broken_008[mod.source()](path="x")
    w["after"] = scale_008[mod.map()](w["src"])
    with pytest.raises(StepFailed, match="OSError: no such file"):
        w.run_all()
    w["src"] = broken_008[mod.source(), mod.try_except(default=[])](path="x")
    w.run("src")
    assert w.step("src").state == "completed"


# ── Phase 5: the boundary — C3, K12, M, P, N, C12 ───────────────────────


def _core_modules():
    """The package and every module in it, for checking a name exists nowhere."""
    import sys
    return [m for n, m in sys.modules.items() if n.split(".")[0] == "simple_steps_core"]


def test_C3_functions_instead_of_globals():
    assert "identity" in builtin_tools()
    assert "map" in shape_verbs() and "retry" not in shape_verbs()
    # K24: nothing is registered, so there is no list of every declared tool.
    assert not any(hasattr(m, "declared_tools") or hasattr(m, "resource_types")
                   for m in _core_modules())
    out = map_(grid(pd.DataFrame({"n": [1]})), scale_008.fn, name="s")
    assert value_column(out) == "s"


def test_C3_a_modifier_is_checked_on_its_own():
    assert check_modifier("map", {"nme": "s"}) == (
        "map takes no parameter 'nme'; it accepts axis, name, replace, retries",)
    assert check_modifier("retry") == (
        "retry needs times= — it has no default, so a step without it cannot run",)
    assert check_modifier("retry", {"times": 2}) == ()
    assert scale_008[mod.retry()].check() == check_modifier("retry")


def test_C3_tags_reach_the_catalog():
    @tool(tags=["rowmap", "app"])
    def tagged_008(n: int) -> int:
        return n
    described = catalog({"tagged_008": tagged_008})
    assert described["tagged_008"]["tags"] == ["rowmap", "app"]
    assert described["identity"]["tags"] == []


def test_C3_a_catalog_is_fixed_once_made():
    """There is no registry to freeze (K24): what a workflow may use is its
    catalog, which can only be narrowed, into a new catalog."""
    assert not any(hasattr(m, "freeze") for m in _core_modules())
    cat = Catalog(tools=[scale_008])
    smaller = cat.without("scale_008")
    assert "scale_008" in cat and "scale_008" not in smaller
    assert not hasattr(cat, "add")


def test_K12_a_table_tool_gets_the_whole_grid(wf):
    @tool
    def piv_008(df: pd.DataFrame) -> pd.DataFrame:
        return df.groupby("city", as_index=False)["n"].sum()

    wf["p"] = piv_008[mod.table()](wf["readings"])
    wf["inferred"] = piv_008(wf["readings"])
    assert wf.step("inferred").output.meta["auto"]["verb"] == "table"
    assert wf.step("p").describe() == (
        "table piv_008 · columns unknown until it runs · rows unknown until it runs")
    wf.run("p")
    assert wf.step("p").output.data.to_dict("list") == {
        "city": ["LA", "NYC", "SF"], "n": [2, 2, 4]}


def test_K12_a_table_tool_that_returns_no_frame_fails(wf):
    @tool
    def not_a_frame_008(df: pd.DataFrame) -> int:
        return 3
    wf["t"] = not_a_frame_008[mod.table()](wf["readings"])
    wf.run("t")
    assert wf.step("t").output.notes[0]["error"] == (
        "TypeError: table expects a DataFrame back, got int")


def test_M_infer_verb_drops_a_methods_self():
    class DB008:
        @bound_tool
        def lookup(self, key: str) -> str:
            return key
    upstream = grid(pd.DataFrame({"key": ["SF"]}))
    assert infer_verb(DB008.lookup, upstream, {})[0] == "map"
    assert infer_verb((DB008, "lookup"), upstream, {})[0] == "map"


@tool
def is_big_008(n) -> bool:
    return n > 1


@tool
def fan_008(n) -> list:
    return [n] * n


def test_N_auto_is_saved_as_auto_and_resolved_at_run(wf):
    wf["f"] = is_big_008[mod.auto()](wf["readings"])
    wf["e"] = fan_008[mod.auto()](wf["readings"])
    wf["c"] = add_008[mod.auto()](wf["readings"])
    wf["s"] = scale_008[mod.auto(), mod.retry(times=1)](wf["readings"])
    assert wf.step("f").output.meta["auto"] == {
        "verb": "filter", "provisional": True,
        "reason": "it returns a bool per row, so keep the rows that pass; "
                  "adds breaker(after=5)"}
    wf.run_all()
    picked = {sid: wf.step(sid).output.meta["auto"]["verb"] for sid in "fecs"}
    assert picked == {"f": "filter", "e": "expand", "c": "collapse", "s": "map"}
    assert [m.kind for m in wf.step("s").operation.modifiers] == ["retry", "auto"]
    back = Workflow.from_json(wf.to_session_json(), TOOLS_008)
    assert back.step("s").operation == wf.step("s").operation
    assert modifier_catalog()["auto"]["row_rule"] == "unknown"


def test_P_to_source_round_trips(wf):
    wf["cfg"] = ["n"]
    wf["p"] = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    ops = [
        scale_008[mod.map(name="s"), mod.retry(times=2)](wf["readings"], weight=2),
        op("identity")[mod.select(columns=wf["cfg"])](wf["readings"]),
        scale_008.bind(weight=(1, 2))[mod.map(), mod.try_except(default={1: "x"},
                                                                on=[ValueError])](wf["readings"]),
        scale_008[mod.map()](wf["readings"], weight=wf["p"][0][cols["a"]]),
        join(wf["readings"], wf["readings"], on="city", how="left"),
        add_008[mod.auto()](wf["readings"]),
        scale_008.bind(weight=2)[mod.retry(times=1)],
    ]
    names = formula_names(TOOLS_008)
    for operation in ops:
        text = operation.to_source()
        assert eval(text, {"__builtins__": {}}, names) == operation, text
    assert ops[0].to_source() == (
        'scale_008[mod.map(name="s"), mod.retry(times=2)](wf["readings"], weight=2)')


def test_C12_kwargs_tools_warn_and_say_so():
    with pytest.warns(UserWarning, match=r"kw_008 accepts \*\*opts"):
        @tool
        def kw_008(n: int, **opts) -> int:
            return n
    assert catalog({"kw_008": kw_008})["kw_008"]["open"] is True
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1]})
    w["x"] = kw_008[mod.map()](w["r"], colr="red")
    assert "colr= isn't a named parameter of kw_008; it lands in **opts unchecked" in w.step("x").warnings


# ── 009 step 1: results only, shared row ids, strict zip_ (C16 for expand) ──
@tool
def fan_ids_009(n) -> list:
    return [n * 10 + k for k in range(n)]


@tool
def neg_009(n: int) -> int:
    return -n


@pytest.fixture()
def r3():
    w = Workflow()
    w["r"] = pd.DataFrame({"city": ["SF", "NYC", "LA"], "n": [1, 2, 0]})
    return w


def test_009_expand_ids_derive_from_the_parent(r3):
    r3["items"] = fan_ids_009[mod.expand()](r3["r"])
    r3["as_n"] = mod.rename(columns={"value": "n"})(r3["items"])
    r3["again"] = fan_ids_009[mod.expand()](r3["as_n"])     # nested: 0.0 → 0.0.k
    r3.run_all()
    assert list(r3.step("items").output.data.index) == ["0.0", "1.0", "1.1"]
    assert list(r3.step("items").output.data.columns) == ["value"]   # results only
    assert list(r3.step("again").output.data.index)[:2] == ["0.0.0", "0.0.1"]


def test_009_zip_gives_each_item_its_parent_row(r3):
    r3["items"] = fan_ids_009[mod.expand()](r3["r"])
    r3["with_parent"] = zip_(r3["items"], r3["r"])         # row 2 expanded to nothing
    r3.run_all()
    out = r3.step("with_parent").output.data
    assert list(out.index) == ["0.0", "1.0", "1.1"]
    assert out.to_dict("list") == {"value": [10, 20, 21], "city": ["SF", "NYC", "NYC"],
                                   "n": [1, 2, 2]}


def test_009_zip_after_a_sort_pairs_by_id_not_position(r3):
    r3["sorted"] = mod.sort(by="n", ascending=False)(r3["r"])
    r3["neg"] = neg_009[mod.map()](r3["sorted"])
    r3["pairs"] = zip_(r3["r"], r3["neg"])
    r3.run_all()
    assert r3.step("pairs").output.data.to_dict("list") == {
        "city": ["SF", "NYC", "LA"], "n": [1, 2, 0], "value": [-1, -2, 0]}


def test_009_zip_never_drops_a_row(r3):
    r3["head"] = mod.slice(stop=2)(r3["r"])                 # rows 0, 1 of 0, 1, 2
    r3["kept"] = neg_009[mod.map()](r3["head"])             # its own column: value
    r3["short_first"] = zip_(r3["kept"], r3["r"])
    r3["long_first"] = zip_(r3["r"], r3["kept"])
    r3.run("head")
    r3.run("kept")
    r3.run("short_first")
    r3.run("long_first")
    assert r3.step("short_first").output.notes[0]["error"] == (
        "zip_ pairs rows by id: row 2 of 'r' has no matching row in 'kept'. "
        "For a partial match, use join")
    assert r3.step("long_first").output.notes[0]["error"] == (
        "zip_ pairs rows by id: row 2 of 'r' has no matching row in 'kept'. "
        "For a partial match, use join")
    with pytest.raises(StepFailed, match="use join"):
        r3.run_all()


def test_009_zip_of_loaded_tables_pairs_by_id_and_refuses_extra_rows():
    """Loaded tables all get ids 0…n-1, so they pair by id; a longer one is refused."""
    w = Workflow()
    w["a"] = pd.DataFrame({"x": [1, 2]})
    w["b"] = pd.DataFrame({"y": [3, 4]})
    w["c"] = pd.DataFrame({"z": [5, 6, 7]})
    w["ab"] = zip_(w["a"], w["b"])
    w["ac"] = zip_(w["a"], w["c"])
    w.run("ab")
    w.run("ac")
    assert w.step("ab").output.data.to_dict("list") == {"x": [1, 2], "y": [3, 4]}
    assert "row 2 of 'c' has no matching row in 'a'" in w.step("ac").output.notes[0]["error"]


def test_009_string_row_ids_survive_a_saved_session(r3):
    r3["items"] = fan_ids_009[mod.expand()](r3["r"])
    r3.run_all()
    back = Workflow.from_json(r3.to_session_json(), TOOLS_008)
    assert list(back.step("items").output.data.index) == ["0.0", "1.0", "1.1"]
    assert list(back.step("r").output.data.index) == [0, 1, 2]


def test_009_a_failed_parent_keeps_one_placeholder_row_with_its_id(r3):
    @tool
    def picky_009(n) -> list:
        if n == 2:
            raise ValueError("no")
        return [n]
    r3["items"] = picky_009[mod.expand(), mod.try_except()](r3["r"])
    r3.run_all()
    items = r3.step("items").output
    assert items.row_states["1.0"] == "failed"
    assert items.notes["1.0"]["unit"] == 1                # its parent row


# ── 009 step 2: versions from data hashes, read stamps, stale from versions ──
@tool
def times10_009(n: int) -> int:
    return n * 10


@pytest.fixture()
def chain():
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1, 2]})
    w["a"] = times10_009[mod.map()](w["r"])
    w["b"] = op("identity")[mod.select(columns=["value"])](w["a"])
    w.run_all()
    return w


def test_009_every_step_with_data_has_a_version_and_its_read_stamps(chain):
    assert chain.version("r") and chain.version("a")
    assert chain.step("a").output.meta["read"] == {"r": chain.version("r")}
    assert chain.step("b").output.meta["read"] == {"a": chain.version("a")}


def test_009_equal_data_has_an_equal_version():
    w = Workflow()
    w["x"] = pd.DataFrame({"n": [1, 2]})
    w["y"] = pd.DataFrame({"n": [1, 2]})
    w["z"] = pd.DataFrame({"n": [1, 3]})
    assert w.version("x") == w.version("y") != w.version("z")


def test_009_an_identical_rerun_leaves_readers_fresh(chain):
    chain.run("a")
    assert chain.step("b").state == "completed"


def test_009_changed_data_makes_readers_stale_and_keeps_their_data(chain):
    chain["r"] = pd.DataFrame({"n": [5, 6]})
    assert chain.step("a").state == "stale"
    assert chain.step("b").state == "stale"            # stale through a
    assert chain.step("a").output.values == [10, 20]    # old data still readable
    chain["r"] = pd.DataFrame({"n": [1, 2]})            # back to what a read
    assert chain.step("a").state == "completed"
    assert chain.step("b").state == "completed"


def test_009_a_changed_resource_makes_its_readers_stale():
    class Scaler009:
        def __init__(self, k: int = 1):
            self.k = k

    @tool
    def scaled_009(n: int, s: Scaler009) -> int:
        return n * s.k

    w = Workflow()
    w.define("s", Scaler009, k=2)
    w["r"] = pd.DataFrame({"n": [1]})
    w["x"] = scaled_009[mod.map()](w["r"], s=res["s"])
    w.run_all(resources={"s": Scaler009(2)})
    w.define("s", Scaler009, k=2)                       # same settings: fresh
    assert w.step("x").state == "completed"
    w.define("s", Scaler009, k=3)
    assert w.step("x").state == "stale"


def test_009_stamps_and_staleness_survive_a_saved_session(chain):
    chain["r"] = pd.DataFrame({"n": [5, 6]})
    back = Workflow.from_json(chain.to_session_json(), TOOLS_008)
    assert back.step("a").state == "stale"
    assert back.step("a").output.meta["read"] == chain.step("a").output.meta["read"]
    back.run_all()
    assert back.step("b").state == "completed"
    assert back.step("a").output.values == [50, 60]


def test_009_an_output_saved_without_stamps_keeps_the_old_rule(chain):
    del chain.step("a").output.meta["read"]
    chain["r"] = pd.DataFrame({"n": [1, 2]})            # same data
    assert chain.step("a").state == "stale"            # legacy: any change marks it


# ── 009 step 3: auto — its default breaker, implicit auto, direct calls, setting ──
SPENT = {"calls": 0}


@tool
def flaky_009(n: int) -> int:
    SPENT["calls"] += 1
    if n < 0:
        raise ValueError("bad key")
    return n


@pytest.fixture()
def spent():
    SPENT["calls"] = 0
    return SPENT


def _all_fail(n_rows=20):
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [-1] * n_rows})
    return w


def test_009_a_systematic_failure_trips_autos_breaker_after_5_calls(spent):
    w = _all_fail()
    w["x"] = flaky_009(w["r"])                              # implicit auto
    w.run("x")
    out = w.step("x").output
    assert spent["calls"] == 5                              # not 20
    assert out.notes[4]["error"] == "ValueError: bad key"   # the 5th real failure
    assert out.notes[5]["error"] == (
        "not run: stopped after 5 failures in a row (ValueError: bad key)")
    assert list(out.row_states) == ["failed"] * 20
    assert w.step("x").output.meta["auto"]["reason"].endswith("adds breaker(after=5)")


def test_009_sporadic_failures_never_trip_it(spent):
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [-1, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 1]})
    w["x"] = flaky_009(w["r"])
    w.run("x")
    assert spent["calls"] == 12
    assert w.step("x").output.values[1::2] == [1] * 6


def test_009_the_breaker_can_be_undone_or_changed(spent):
    w = _all_fail(10)
    w["never"] = flaky_009[mod.auto(), mod.breaker(after=None)](w["r"])
    w["early"] = flaky_009[mod.auto(), mod.breaker(after=2)](w["r"])
    w["stated"] = flaky_009[mod.map()](w["r"])              # you chose: no defaults
    w.run("never")
    assert spent["calls"] == 10
    spent["calls"] = 0
    w.run("early")
    assert spent["calls"] == 2
    spent["calls"] = 0
    w.run("stated")
    assert spent["calls"] == 10
    assert json.loads(w.to_json())["steps"][1]["operation"]["modifiers"] == [
        {"kind": "breaker", "settings": {"after": None}}, {"kind": "auto", "settings": {}}]


def test_009_try_except_never_swallows_a_breaker_stop(spent):
    w = _all_fail(8)
    w["x"] = flaky_009[mod.auto(), mod.try_except(default=0)](w["r"])
    w.run("x")
    # try_except sits outside the breaker: each failure becomes 0, so no
    # failure reaches the breaker and every row runs — the user's choice.
    assert w.step("x").output.values == [0] * 8
    w["y"] = flaky_009[mod.try_except(default=0), mod.auto()](w["r"])
    spent["calls"] = 0
    w.run("y")
    assert spent["calls"] == 5                               # stopped; not turned into 0s
    out = w.step("y").output
    assert out.notes[out.data.index[-1]]["error"].startswith("not run: stopped")


def test_009_a_direct_call_runs_over_rows_only_when_the_frame_doesnt_fit():
    @tool
    def plus_one_009(n: int) -> int:
        return n + 1

    @tool
    def width_009(df: pd.DataFrame) -> int:
        return len(df.columns)

    @tool
    def untyped_009(n):
        return n

    frame = pd.DataFrame({"n": [1, 2, 3]})
    out = plus_one_009(frame)
    assert isinstance(out, Output) and out.values == [2, 3, 4]
    assert width_009(frame) == 1                            # fits as-is
    assert untyped_009(frame) is frame                       # untyped: as-is
    assert plus_one_009(5) == 6                              # parens still run


def test_009_an_unwritten_orchestration_is_always_auto(wf):
    """Implicit auto is always on: the switch that turned it off was
    process-wide state, and is gone (K24)."""
    assert [m.kind for m in scale_008(wf["readings"]).modifiers] == ["auto"]
    wf["ok"] = scale_008[mod.auto()](wf["readings"])        # stated auto works too
    wf.run("ok")
    assert wf.step("ok").output.values == [10, 20, 30, 20]


# ── 009 step 4: known unknowns are shown — wf.preview and wf.cell ─────────
@tool
def score_009(n: int) -> float:
    if n < 0:
        raise ValueError("negative")
    return n * 1.5


@tool
def big_009(n: int) -> bool:
    return n > 1


@pytest.fixture()
def unrun():
    w = Workflow()
    w["r"] = load_typed_008[mod.source()](path="x")        # city: str, n: int
    w["s"] = score_009(w["r"])
    return w


def test_009_known_columns_unknown_rows_are_shown_with_a_marker(unrun):
    view = unrun.preview("r")
    assert view["columns"] == [{"name": "city", "type": "str", "#": 0},
                               {"name": "n", "type": "int", "#": 1}]
    assert view["rows"] == []
    assert view["row_count"]["certainty"] == "unknown"
    marker = view["markers"][0]
    assert marker["kind"] == "rows" and marker["text"].startswith("‹rows unknown — ")
    assert "run load_typed_008" in marker["resolve"]


def test_009_a_later_step_names_the_step_it_is_waiting_on(unrun):
    marker = unrun.preview("s")["markers"][0]
    assert marker["because"] == "its input 'r' doesn't know its row count yet"
    assert marker["resolve"][0] == "run 'r'"
    assert unrun.preview("s")["columns"] == [{"name": "value", "type": "float", "#": 0}]


def test_009_some_columns_known_shows_a_more_columns_marker():
    w = Workflow()
    w["r"] = load_raw_008[mod.source(), mod.expect(columns={"city": str},
                                                   more_columns=True)](path="x")
    kinds = {m["kind"]: m["text"] for m in w.preview("r")["markers"]}
    assert kinds["columns"] == "‹+ maybe more columns›"
    assert kinds["rows"].startswith("‹rows unknown")


def test_009_planned_rows_are_pending_or_maybe(wf):
    wf["s"] = score_009[mod.map()](wf["readings"])
    wf["k"] = big_009[mod.filter()](wf["readings"])
    s, k = wf.preview("s"), wf.preview("k")
    assert [r["state"] for r in s["rows"]] == ["pending"] * 4
    assert s["rows"][0]["cells"] == {"value": {"state": "pending", "type": "float"}}
    assert [r["state"] for r in k["rows"]] == ["maybe"] * 4
    assert k["markers"][0]["text"] == "‹0–4 rows — filter keeps at most the 4 rows it reads›"


def test_009_a_run_step_shows_values_failures_and_staleness(unrun):
    unrun["s"] = score_009[mod.auto(), mod.try_except()](unrun["r"])
    unrun.run_all()
    drawn = unrun.preview("s")["rows"]
    assert [r["state"] for r in drawn] == ["known", "known"]          # load gives n = 1, 2
    unrun["r"] = load_typed_008[mod.source()](path="y")             # re-declared: s is stale
    assert [r["state"] for r in unrun.preview("s")["rows"]] == ["stale", "stale"]
    assert unrun.preview("s")["rows"][0]["cells"]["value"]["value"] == 1.5   # old value kept


def test_009_clicking_a_cell_says_what_is_there_or_expected(unrun):
    before = unrun.cell("s", 1, "value")
    assert (before["state"], before["type"]) == ("unknown", "float")   # row 1, if it exists
    assert before["resolve"][0] == "run 'r'"
    unrun.run("r")
    unrun.run("s")
    known = unrun.cell("s", 1, "value")
    assert (known["state"], known["value"]) == ("known", 3.0)
    # 010 C27: one entry per binding — the column read and the argument it fed
    assert known["inputs"] == [{"step": "r", "id": 1, "row": 1, "columns": ["n"], "argument": "n",
                                "state": "known", "values": {"n": 2}, "more": 0}]
    assert unrun.cell("s", 9, "value")["because"] == "row 9 of 's', which has 2 rows (0–1)"
    assert unrun.cell("s", 0, "nope")["state"] == "missing"


def test_009_a_failed_and_a_blocked_cell(wf):
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1, -1]})
    w["s"] = score_009[mod.map(), mod.try_except()](w["r"])
    w["t"] = op("identity")[mod.select(columns=["value"])](w["s"])
    w.run_all()
    failed = w.cell("s", 1, "value")
    assert (failed["state"], failed["error"]) == ("failed", "ValueError: negative")
    blocked = w.cell("t", 1, "value")
    assert blocked["state"] == "blocked" and blocked["cause"] == "s[1]: ValueError: negative"


def test_009_an_invalid_step_says_why(wf):
    wf["bad"] = score_009[mod.map()](wf["nope"])
    view = wf.preview("bad")
    assert view["state"] == "invalid"
    assert view["markers"][0]["text"] == "‹can't run — input 'nope', which is not an earlier step›"


# ── 009: an output is data, states and meta ─────────────────────────────
def test_009_an_output_is_data_states_and_meta(failing):
    failing.run_all()
    out = failing.step("a").output
    assert out.states.shape == out.data.shape
    assert list(out.row_states) == ["known", "failed", "known"]
    assert out.notes == {1: {"error": "ValueError: boom", "caught": True}}   # only row 1
    assert out.meta["version"] and "ledger" not in vars(out)


def test_009_a_zip_carries_each_cells_state(failing):
    failing["view"] = zip_(failing["r"], failing["a"])
    failing.run_all()
    view = failing.step("view").output
    assert [str(v) for v in view.states.loc[1]] == ["known", "blocked"]   # n known, value blocked
    assert view.notes[1]["cause"] == "a[1]: ValueError: boom"
    assert failing.step("view").state == "failed"           # shown, but the run went on


def test_009_printing_an_output_shows_states_and_notes(failing):
    failing.run_all()
    text = str(failing.step("a").output)
    assert text.splitlines()[0] == "<Output map · 3 row(s) × 1 col(s), 1 failed>"
    assert "failed" in text and "ValueError: boom (caught)" in text
    staged = Workflow()
    staged["r"] = load_typed_008[mod.source()](path="x")
    assert str(staged.step("r").output) == (
        "<Output source · staged>\ncolumns city (str), n (int) · rows unknown until it runs")


def test_009_states_and_notes_survive_a_saved_session(failing):
    failing.run_all()
    back = Workflow.from_json(failing.to_session_json(), TOOLS_008)
    out = back.step("a").output
    assert list(out.row_states) == ["known", "failed", "known"]
    assert out.notes == {1: {"error": "ValueError: boom", "caught": True}}   # id stays an int



def test_009_a_cell_shows_the_input_values_that_produced_it(failing):
    """009: clicking a cell names its input row and that row's values — looked
    up from the row id, never stored per cell."""
    failing.run_all()
    failed = failing.cell("a", 1, "value")
    assert failed["inputs"] == [{"step": "r", "id": 1, "row": 1, "columns": ["n"], "argument": "n",
                                 "state": "known", "values": {"n": 2}, "more": 0}]   # n = 2 raised
    assert "inputs" not in failing.step("a").output.meta                # nothing stored
    failing["view"] = zip_(failing["r"], failing["a"])
    failing.run("view")
    # a zip cell comes from the one input that supplied its column
    assert [(i["step"], i["id"], i["state"]) for i in failing.cell("view", 1, "value")["inputs"]] == [
        ("a", 1, "failed")]
    assert [(i["step"], i["id"]) for i in failing.cell("view", 1, "n")["inputs"]] == [("r", 1)]


def test_009_an_expanded_item_points_to_its_parent_row(r3):
    r3["items"] = fan_ids_009[mod.expand()](r3["r"])
    r3.run_all()
    cell = r3.cell("items", 2, "value")                                   # id "1.1"
    assert cell["id"] == "1.1"
    assert cell["inputs"][0]["id"] == 1 and cell["inputs"][0]["values"] == {"n": 2}


def test_009_wide_input_rows_show_a_few_values_and_count_the_rest():
    @tool
    def width_010(**row) -> int:                  # reads the whole row
        return len(row)

    w = Workflow()
    w["r"] = pd.DataFrame({f"c{i}": [i] for i in range(9)})
    w["s"] = width_010[mod.map()](w["r"])
    w["one"] = op("identity")[mod.select(columns=["c0"])](w["r"])
    w.run_all()
    inputs = w.cell("s", 0, "value")["inputs"]
    assert len(inputs) == 9                       # one binding per column read
    copied = w.cell("one", 0, "c0")["inputs"]
    assert copied == [{"step": "r", "id": 0, "row": 0, "columns": ["c0"], "argument": None,
                       "state": "known", "values": {"c0": 0}, "more": 0}]



# ── 009: a stale value says what it was computed with ───────────────────
@tool
def weigh_009(n: int, weight: float = 1.0) -> float:
    return n * weight


def test_009_a_stale_value_says_it_was_computed_with_the_old_arguments():
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1, 2]})
    w["s"] = weigh_009[mod.map()](w["r"], weight=1.5)
    w.run_all()
    assert w.arg_changes("s") == []
    w["s"] = weigh_009[mod.map()](w["r"], weight=2.0)          # edit the argument
    assert w.arg_changes("s") == [{"name": "weight", "was": "1.5", "now": "2.0"}]
    cell = w.cell("s", 1, "value")
    assert (cell["state"], cell["value"]) == ("stale", 3.0)     # 2 × 1.5, the old value
    assert cell["because"] == "stale output · computed with weight=1.5 (now 2.0)"
    assert cell["computed_with"] == {"weight": "1.5"}
    view = w.preview("s")
    assert view["computed_with"] == "values below were computed with weight=1.5 (now 2.0)"
    w.run("s")
    assert w.arg_changes("s") == [] and w.cell("s", 1, "value")["value"] == 4.0


def test_009_an_added_argument_and_a_changed_orchestration_are_named():
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1]})
    w["s"] = weigh_009[mod.map()](w["r"])
    w.run_all()
    w["s"] = weigh_009[mod.map()](w["r"], weight=3.0)
    assert w.arg_changes("s") == [{"name": "weight", "was": "1.0", "now": "3.0",
                                   "was_default": True}]
    assert w.cell("s", 0, "value")["because"] == (
        "stale output · computed with weight=1.0, the default (now 3.0)")
    w.run("s")
    w["s"] = weigh_009[mod.map(), mod.retry(times=2)](w["r"], weight=3.0)
    change = w.arg_changes("s")[0]
    assert change["name"] == "formula" and "mod.retry(times=2)" in change["now"]


def test_009_a_stale_value_from_an_upstream_change_doesnt_claim_new_arguments():
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1]})
    w["s"] = weigh_009[mod.map()](w["r"], weight=2.0)
    w.run_all()
    w["r"] = pd.DataFrame({"n": [5]})
    cell = w.cell("s", 0, "value")
    assert cell["because"] == "stale output (input r changed)" and "changed" not in cell



# ── 010: the app's asks at b9f66d5 ──────────────────────────────────────
@tool
def double_n_010(n: int) -> int:
    return n * 2


@tool
def add_total_010(acc, value: float) -> float:
    return (acc or 0) + value


@tool
def load_010(path: str) -> pd.DataFrame:
    return pd.DataFrame({"n": [1, 2]})


def test_C22_zip_refuses_a_column_both_grids_have():
    w = Workflow()
    w["r"] = pd.DataFrame({"city": ["SF", "NYC", "LA"], "n": [1, 0, 2]})
    w["d"] = double_n_010[mod.map(name="n")](w["r"])
    w["z"] = zip_(w["r"], w["d"])
    assert w.step("z").problems == (
        "zip_: 'n' is in both 'r' and 'd'; rename one (mod.map(name=…) or mod.rename)",)
    with pytest.raises(ValueError, match="is invalid and cannot run"):
        w.run("z")


def test_C22_zip_columns_known_only_at_run_are_checked_then():
    w = Workflow()
    w["src"] = load_010[mod.source()](path="x")
    w["d"] = double_n_010[mod.map(name="n")](w["src"])
    w["z"] = zip_(w["src"], w["d"])
    assert w.step("z").problems == ()                       # src's columns not known yet
    w.run("src")
    assert "'n' is in both 'src' and 'd'" in w.step("z").problems[0]   # re-checked
    w2 = Workflow()
    w2["a"] = pd.DataFrame({"n": [1]})
    w2["b"] = pd.DataFrame({"n": [2]})
    frames = [w2.step("a").output.data.copy(), w2.step("b").output.data.copy()]
    frames[0].attrs["name"], frames[1].attrs["name"] = "a", "b"
    with pytest.raises(ValueError, match="'n' is in both 'a' and 'b'"):
        _combine_zip(frames, {})                       # the run-time guard


def test_C23_collapse_by_a_missing_column_is_refused():
    w = Workflow()
    w["r"] = pd.DataFrame({"city": ["SF", "NYC"], "n": [1, 2]})
    w["s"] = scale_008[mod.map()](w["r"])                   # only `value`
    w["c"] = add_total_010[mod.collapse(by="city", initial=0)](w["s"])
    assert w.step("c").problems == (
        "collapse groups by 'city', which 's' does not have (it has value)",)


def test_C23_the_run_time_guard_fails_the_step():
    with pytest.raises(SelectionError, match="collapse groups by 'city'"):
        collapse_(grid(pd.DataFrame({"n": [1]})), lambda acc, row: acc, by="city")



def test_C27_every_input_cell_is_named_with_its_argument():
    w = Workflow()
    w["r"] = pd.DataFrame({"city": ["SF", "NYC", "LA"], "n": [1, 2, 3]})
    w["w"] = pd.DataFrame({"w": [1.5]})
    w["s"] = scale_008[mod.map()](w["r"], weight=w["w"][0][cols["w"]])
    w.run("s")
    assert w.cell("s", 1, "value")["inputs"] == [
        {"step": "r", "id": 1, "row": 1, "columns": ["n"], "argument": "n", "state": "known",
         "values": {"n": 2}, "more": 0},
        {"step": "w", "id": 0, "row": 0, "columns": ["w"], "argument": "weight", "state": "known",
         "values": {"w": 1.5}},
    ]


def test_C27_settings_resources_and_group_rows_are_named_too(wf):
    wf["cfg"] = ["n"]
    wf["sel"] = op("identity")[mod.select(columns=wf["cfg"])](wf["readings"])
    wf["g"] = mod.rename(columns={"n": "count"})(wf["readings"])
    wf.run_all()
    sel = wf.cell("sel", 0, "n")["inputs"]
    assert [i["argument"] for i in sel] == [None, "select.columns"]
    assert sel[1]["step"] == "cfg"
    assert wf.cell("g", 0, "count")["inputs"][0]["columns"] == ["n"]   # renamed from n
    total = add_008[mod.collapse(initial=0)](wf["readings"])
    wf["t"] = total
    wf.run("t")
    rows_ = wf.cell("t", 0, "value")["inputs"][0]
    assert rows_["argument"] == "n" and rows_["rows"] == [0, 1, 2, 3]


def test_C24_input_states_are_cell_states(failing):
    failing["b"] = plus1_008[mod.map()](failing["a"])
    failing.run_all()
    states = {i["state"] for r in (0, 1, 2) for i in failing.cell("b", r, "value")["inputs"]}
    assert states <= set(STATES) | {"stale", "pending", "missing", "unknown"}
    assert failing.cell("b", 1, "value")["inputs"][0]["state"] == "failed"



def test_C21_whether_an_output_stops_a_run_is_public(failing, spent):
    failing.run_all()                                   # a has try_except: caught
    assert failing.step("a").output.uncaught == [] and not failing.step("a").output.stops_run
    w = Workflow()
    w["r"] = pd.DataFrame({"n": [1, -1, -1, -1, -1, -1, -1]})
    w["x"] = flaky_009(w["r"])                          # auto: breaker stops after 5
    w.run("x")
    out = w.step("x").output
    assert out.stops_run and out.uncaught == [1, 2, 3, 4, 5, 6]     # a breaker stop counts
    w["y"] = op("identity")[mod.select(columns=["value"])](w["x"])
    w.run("y")
    assert w.step("y").output.uncaught == []            # blocked, not its own failure


@pytest.fixture()
def rows3():
    w = Workflow()
    w["r"] = pd.DataFrame({"city": ["SF", "NYC", "LA"], "n": [1, 2, 3]})
    w["s"] = scale_008[mod.map()](w["r"])                   # reads n only
    w["t"] = mod.select(columns=["value"])(w["s"])
    w.run_all()
    return w


def test_C25_editing_one_input_row_makes_only_its_cells_stale(rows3):
    rows3["r"] = pd.DataFrame({"city": ["SF", "NYC", "LA"], "n": [1, 20, 3]})
    assert rows3.step("s").state == "stale"
    assert rows3.stale_rows("s") == [1] and rows3.stale_rows("t") == [1]    # flows on
    assert [r["state"] for r in rows3.preview("s")["rows"]] == ["known", "stale", "known"]
    assert rows3.cell("s", 0, "value")["state"] == "known"
    assert list(rows3.step("s").output.view()["state"]) == ["known", "stale", "known"]


def test_C25_an_unread_column_changing_leaves_it_fresh(rows3):
    rows3["r"] = pd.DataFrame({"city": ["SF", "BOS", "LA"], "n": [1, 2, 3]})
    assert rows3.step("s").state == "completed" and rows3.stale_rows("s") == []


def test_C25_rows_added_or_an_argument_change_make_every_row_stale(rows3):
    rows3["r"] = pd.DataFrame({"city": ["SF", "NYC", "LA", "SEA"], "n": [1, 2, 3, 4]})
    assert rows3.stale_rows("s") is None
    rows3.run_all()
    rows3["s"] = scale_008[mod.map()](rows3["r"], weight=2)
    assert rows3.stale_rows("s") is None


def test_C25_row_staleness_survives_a_saved_session(rows3):
    rows3["r"] = pd.DataFrame({"city": ["SF", "NYC", "LA"], "n": [1, 20, 3]})
    back = Workflow.from_json(rows3.to_session_json(), TOOLS_008)
    assert back.stale_rows("s") == [1]
    back.run_all()
    assert back.stale_rows("s") == [] and back.step("s").output.values == [10, 200, 30]



# ── "#" is the row-id column (2026-10-23) ───────────────────────────────
def test_hash_is_the_row_number_0_to_n_minus_1_on_every_step(wf):
    """'#' always counts 0…n-1 down the grid — even after a filter, whose rows
    still link to the input rows they came from (internally, by id)."""
    @tool
    def big_hash(n: int) -> bool:
        return n > 1

    wf["k"] = big_hash[mod.filter()](wf["readings"])        # keeps input rows 1, 2, 3
    wf["s"] = scale_008[mod.map()](wf["k"])
    wf.run_all()
    assert list(wf.step("s").output.view()["#"]) == [0, 1, 2]
    assert [r["#"] for r in wf.preview("s")["rows"]] == [0, 1, 2]
    cell = wf.cell("s", 0, "value")                          # '#0' of s
    assert cell["inputs"][0]["step"] == "k" and cell["inputs"][0]["row"] == 0
    assert wf.cell("k", 0, "n")["inputs"][0]["row"] == 1     # k's #0 is readings' #1
    assert str(wf.step("s").output).splitlines()[1].split()[0] == "#"
    assert ROW_ID == "#"


def test_a_table_with_its_own_hash_column_is_refused():
    with pytest.raises(SelectionError, match="'#', which is reserved for row ids"):
        Workflow()["bad"] = pd.DataFrame({"#": [1], "n": [2]})


def test_a_predefined_index_becomes_a_column():
    w = Workflow()
    w["p"] = pd.DataFrame({"n": [5, 6]}, index=pd.Index(["a", "b"], name="code"))
    w["q"] = pd.DataFrame({"n": [7]}, index=[10])                    # unnamed
    assert w.step("p").output.view()[["#", "code", "n"]].to_dict("list") == {
        "#": [0, 1], "code": ["a", "b"], "n": [5, 6]}
    assert list(w.step("q").output.data.columns) == ["index", "n"]
    with pytest.raises(SelectionError, match="a column already has that name"):
        Workflow()["clash"] = pd.DataFrame({"code": [1]}, index=pd.Index(["x"], name="code"))


def test_row_ids_and_column_names_can_be_referenced(wf):
    @tool
    def width_hdr(names: list) -> int:
        return len(names)

    wf["ids"] = wf["readings"][cols["#"]]
    wf["both"] = wf["readings"][1:3][cols[["#", "n"]]]
    wf["picked"] = op("identity")[mod.select(columns=["#", "city"])](wf["readings"])
    wf["hdr"] = wf["readings"].header
    wf["w"] = width_hdr.bind(names=wf["readings"].header)[mod.source()]
    wf.run_all()
    assert wf.step("ids").output.data.to_dict("list") == {"#": [0, 1, 2, 3]}
    assert wf.step("both").output.data.to_dict("list") == {"#": [1, 2], "n": [2, 3]}
    assert list(wf.step("picked").output.data.columns) == ["#", "city"]
    assert wf.step("hdr").output.data.to_dict("list") == {"name": ["city", "n"]}
    assert wf.step("w").output.data.iloc[0, 0] == 2
    assert wf.step("w").operation.to_source() == 'width_hdr[mod.source()](names=wf["readings"].header)'
    back = Workflow.from_json(wf.to_session_json(), TOOLS_008)
    back.run_all()
    assert back.step("w").output.data.iloc[0, 0] == 2



def test_columns_are_numbered_0_to_m_minus_1_like_rows(wf):
    """A column's number is its position — what cols[1] or cols[0:2] select."""
    wf["picked"] = wf["readings"][cols[1]]
    wf.run_all()
    view = wf.preview("readings")
    assert [(c["name"], c["#"]) for c in view["columns"]] == [("city", 0), ("n", 1)]
    assert wf.cell("readings", 2, "n")["column_number"] == 1
    assert list(wf.step("picked").output.data.columns) == ["n"]          # cols[1] is "n"
