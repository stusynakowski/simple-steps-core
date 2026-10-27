"""Reshaping is closed: the laws of docs/design/reshaping.md §10.

One test per law. A law that holds today is a plain test; one that waits on a
decision is ``xfail(strict=True)`` naming it, so it fails loudly the day it
starts to hold and the mark comes off. Tests of proposed moves (``mod.pack``,
``expand(columns=…)``, ``by="#v"``) are written in the proposed spelling.
"""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, join, mod, stack, tool, wf, zip_
from simple_steps_core.operation import op

gather, first, identity = op("gather"), op("first"), op("identity")


@tool
def visits_rc() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Ada", "Ben", "Cy"], "ward": ["A", "A", "B", "A"],
                         "temp": [37.0, 38.5, 36.9, 39.1]})


@tool
def wards_rc() -> pd.DataFrame:
    return pd.DataFrame({"ward": ["A", "B"], "head": ["Dr X", "Dr Y"]})


@tool
def named_rc() -> pd.DataFrame:
    """A source that names its rows, with an id that looks like a child's."""
    return pd.DataFrame({"name": ["p", "q"]}, index=["a", "a.1"])


@tool
def readings_rc(name: str) -> list:
    return [len(name), len(name) * 10]


@tool
def two_rc(name: str) -> list:
    return [name + "0", name + "1"]


@tool
def hot_rc(temp: float) -> bool:
    return temp > 37.5


@tool
def cold_rc(temp: float) -> bool:
    return temp < 0


@tool
def backwards_rc(value: list) -> list:
    return list(reversed(value))


@tool
def reorder_rc(df: pd.DataFrame) -> pd.DataFrame:
    """A table tool whose index looks like its input's, but isn't."""
    return df.sort_values("temp", ascending=False).reset_index(drop=True)


TOOLS = [visits_rc, wards_rc, named_rc, readings_rc, two_rc, hot_rc, cold_rc,
         backwards_rc, reorder_rc]


@pytest.fixture
def k():
    k = Kernel(Catalog(tools=TOOLS))
    k["v"] = visits_rc[mod.source()]()
    k["w"] = wards_rc[mod.source()]()
    k["t"] = mod.select(columns=["temp"])(wf["v"])
    return k


def data(k, step) -> pd.DataFrame:
    return k.step(step).data


def state(k, step) -> str:
    return k.workflow.steps[step].state


def same_rows(a: pd.DataFrame, b: pd.DataFrame) -> None:
    """The same samples: the same ids, each with the same values, in any order."""
    assert sorted(map(str, a.index)) == sorted(map(str, b.index))
    pd.testing.assert_frame_equal(a.loc[list(b.index), list(b.columns)], b,
                                  check_dtype=False)


# ── pack and unpack: lossless ────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="R-D3: unpacking a gathered list gives new ids (R1, M9)")
def test_L1_unpacking_a_packed_column_gives_back_its_rows(k):
    k["packed"] = gather[mod.collapse()](wf["t"])
    k["unpacked"] = identity[mod.expand()](wf["packed"])
    k["names"] = mod.select(columns=["name"])(wf["v"])
    k["side"] = zip_(wf["names"], wf["unpacked"])
    k.run_all()
    assert data(k, "packed").iloc[0, 0] == [37.0, 38.5, 36.9, 39.1]
    same_rows(data(k, "unpacked"), data(k, "t"))
    assert tuple(data(k, "side").loc[2]) == ("Ben", 36.9)           # each beside its own name


def test_L2_packing_an_unpacked_list_gives_back_the_list(k):
    k["packed"] = gather[mod.collapse()](wf["t"])
    k["unpacked"] = identity[mod.expand()](wf["packed"])
    k["again"] = gather[mod.collapse()](wf["unpacked"])
    k.run_all()
    assert data(k, "again").iloc[0, 0] == data(k, "packed").iloc[0, 0]


@pytest.mark.xfail(strict=True, reason="R-D2: no mod.pack; widen keeps the dict column (G10)")
def test_L3_widening_a_packed_row_gives_back_the_row(k):
    k["rec"] = mod.pack(columns=["name", "ward", "temp"])(wf["v"])
    k["back"] = mod.widen()(wf["rec"])
    k.run_all()
    assert data(k, "rec").iloc[0, 0] == {"name": "Ada", "ward": "A", "temp": 37.0}
    pd.testing.assert_frame_equal(data(k, "back"), data(k, "v"), check_dtype=False)


@pytest.mark.xfail(strict=True, reason="R-D2, R-D3: block via a list of dicts loses ids")
def test_L4_a_block_through_a_list_of_dicts_comes_back(k):
    k["rec"] = mod.pack(columns=["name", "ward", "temp"])(wf["v"])
    k["packed"] = gather[mod.collapse()](wf["rec"])
    k["rows"] = mod.expand(columns=["value"])(wf["packed"])
    k["back"] = mod.widen()(wf["rows"])
    k.run_all()
    same_rows(data(k, "back"), data(k, "v"))


@pytest.mark.xfail(strict=True, reason="R-D1, R-D2, R-D4: no dict of lists, no lockstep expand")
def test_L5_a_block_through_a_dict_of_lists_comes_back(k):
    k["lists"] = gather[mod.collapse()](wf["v"])                  # one row: name, ward, temp lists
    k["packed"] = mod.pack(columns=["name", "ward", "temp"])(wf["lists"])
    k["lists2"] = mod.widen()(wf["packed"])
    k["back"] = mod.expand(columns=["name", "ward", "temp"])(wf["lists2"])
    k.run_all()
    assert list(data(k, "lists").columns) == ["name", "ward", "temp"]
    same_rows(data(k, "back"), data(k, "v"))


@pytest.mark.xfail(strict=True, reason="R-D1, R-D3, R-D4: groups unpack to new ids ('A.0')")
def test_L6_unpacking_groups_gives_back_the_rows(k):
    k["vt"] = mod.select(columns=["ward", "temp"])(wf["v"])
    k["groups"] = gather[mod.collapse(by="ward")](wf["vt"])       # ward, temp (a list)
    k["back"] = mod.expand(columns=["temp"])(wf["groups"])
    k.run_all()
    assert data(k, "groups").loc["A", "temp"] == [37.0, 38.5, 39.1]
    same_rows(data(k, "back"), data(k, "vt"))


def test_L7_expand_then_collapse_by_its_parent_gives_one_row_per_parent(k):
    k["e"] = readings_rc[mod.expand()](wf["v"])
    k["back"] = gather[mod.collapse(by="#v")](wf["e"])
    k["side"] = zip_(wf["v"], wf["back"])
    k.run_all()
    assert list(data(k, "back").index) == [0, 1, 2, 3]
    assert data(k, "back").loc[2, "value"] == [3, 30]               # Ben
    assert state(k, "side") == "completed"


# ── reorder, rename, place: lossless ─────────────────────────────────────────

def test_L8_sort_is_a_permutation(k):
    k["srt"] = mod.sort(by="temp")(wf["v"])
    k.run_all()
    assert list(data(k, "srt").index) == [2, 0, 1, 3]
    same_rows(data(k, "srt"), data(k, "v"))


def test_L9_rename_then_rename_back_is_the_grid(k):
    k["r"] = mod.rename(columns={"temp": "t_c"})(wf["v"])
    k["rr"] = mod.rename(columns={"t_c": "temp"})(wf["r"])
    k.run_all()
    pd.testing.assert_frame_equal(data(k, "rr"), data(k, "v"))


def test_L10_zipping_two_selections_of_a_grid_gives_the_grid(k):
    k["a"] = mod.select(columns=["name"])(wf["v"])
    k["b"] = mod.select(columns=["ward", "temp"])(wf["v"])
    k["z"] = zip_(wf["a"], wf["b"])
    k.run_all()
    pd.testing.assert_frame_equal(data(k, "z"), data(k, "v"), check_dtype=False)


def test_L11_filter_and_sort_commute(k):
    k["f"] = hot_rc[mod.filter()](wf["v"])
    k["fs"] = mod.sort(by="temp")(wf["f"])
    k["s"] = mod.sort(by="temp")(wf["v"])
    k["sf"] = hot_rc[mod.filter()](wf["s"])
    k.run_all()
    pd.testing.assert_frame_equal(data(k, "fs"), data(k, "sf"))


@pytest.mark.xfail(strict=True, reason="R-D5, R-D6: stack keeps no row map; no by='#a'")
def test_L12_a_stack_splits_back_into_its_inputs(k):
    k["a"] = mod.select(columns=["temp"])(wf["v"])
    k["b"] = mod.select(columns=["temp"])(wf["v"])
    k["s"] = stack(wf["a"], wf["b"])
    k["back"] = first[mod.collapse(by="#a")](wf["s"])
    k.run_all()
    same_rows(data(k, "back"), data(k, "a"))


@pytest.mark.xfail(strict=True, reason="R-D5, R-D6: join keeps no row map (M4)")
def test_L13_a_join_collapses_back_to_one_side(k):
    k["j"] = join(wf["v"], wf["w"], on="ward", how="left")
    k["back"] = first[mod.collapse(by="#v")](wf["j"])
    k["heads"] = mod.select(columns=["head"])(wf["back"])
    k["side"] = zip_(wf["v"], wf["heads"])
    k.run_all()
    assert list(data(k, "back").index) == [0, 1, 2, 3]
    assert data(k, "side").loc[2, "head"] == "Dr Y"                 # Ben, ward B


# ── trace: every cell knows its input rows ───────────────────────────────────

def test_L14_a_collapsed_cell_traces_to_its_group(k):
    k["c"] = op("count")[mod.collapse(by="ward")](wf["v"])
    k.run_all()
    inputs = k.cell("c", "A", "value")["inputs"]
    assert {i["step"] for i in inputs} == {"v"}
    assert all(i["rows"] == [0, 1, 3] for i in inputs)


@pytest.mark.xfail(strict=True, reason="R-D6: join keeps no row map (M4)")
def test_L15_a_joined_cell_traces_to_its_pair(k):
    k["j"] = join(wf["v"], wf["w"], on="ward")
    k.run_all()
    row = next(i for i, n in data(k, "j")["name"].items() if n == "Ben")
    inputs = k.cell("j", row, "head")["inputs"]
    assert {(i["step"], i["id"]) for i in inputs} >= {("w", 1)}
    assert all(i["state"] == "known" for i in inputs)


@pytest.mark.xfail(strict=True, reason="R-D7: no origins; counted ids pair by accident (M5)")
def test_L16_zip_across_origins_is_refused_when_declared(k):
    k["jw"] = join(wf["w"], wf["v"], on="ward")
    k["jn"] = mod.select(columns=["head"])(wf["jw"])
    k["z"] = zip_(wf["v"], wf["jn"])
    assert state(k, "z") == "invalid"


@pytest.mark.xfail(strict=True, reason="R-D7: refused when it runs (M9 fixed), not yet when declared")
def test_L16b_items_a_tool_rewrote_dont_pair_with_the_packed_rows(k):
    k["packed"] = gather[mod.collapse()](wf["t"])
    k["rev"] = backwards_rc[mod.map()](wf["packed"])
    k["items"] = identity[mod.expand()](wf["rev"])
    k["z"] = zip_(wf["v"], wf["items"])
    assert state(k, "z") == "invalid"


def test_L17_row_ids_are_never_parsed(k):
    k["n"] = named_rc[mod.source()]()
    k["e"] = two_rc[mod.expand()](wf["n"])
    k.run_all()
    assert data(k, "e").loc["a.1", "value"] == "p1"                 # item 1 of row a
    (parent,) = k.cell("e", "a.1", "value")["inputs"]
    assert parent["id"] == "a"


def test_L18_empty_packs_to_an_empty_list_and_back(k):
    k["none"] = cold_rc[mod.filter()](wf["t"])
    k["packed"] = gather[mod.collapse()](wf["none"])
    k["back"] = identity[mod.expand()](wf["packed"])
    k.run_all()
    assert data(k, "packed").iloc[0, 0] == []
    assert len(data(k, "back")) == 0


@pytest.mark.xfail(strict=True, reason="R-D9: distinct traces only to the row it kept (M3)")
def test_L19_distinct_traces_to_every_row_it_stands_for(k):
    k["d"] = mod.distinct(columns=["ward"])(wf["v"])
    k.run_all()
    (inp,) = k.cell("d", 0, "ward")["inputs"]
    assert inp["rows"] == [0, 1, 3]


@pytest.mark.xfail(strict=True, reason="R-D7, R-D9: table keeps the tool's index (M6)")
def test_L20_a_table_is_its_own_origin(k):
    k["tb"] = reorder_rc[mod.table()](wf["v"])                      # ids 0…3, other rows
    k["names"] = mod.select(columns=["name"])(wf["v"])
    k["temps"] = mod.select(columns=["temp"])(wf["tb"])
    k["z"] = zip_(wf["names"], wf["temps"])
    assert state(k, "z") == "invalid"


@pytest.mark.xfail(strict=True, reason="R-D8: the plan doesn't say how to go back")
def test_L21_the_plan_says_how_to_go_back(k):
    k["srt"] = mod.sort(by="temp")(wf["v"])
    k["f"] = hot_rc[mod.filter()](wf["v"])
    k["tb"] = reorder_rc[mod.table()](wf["v"])
    assert k.workflow.steps["srt"].plan["inverse"] == "rebuild"
    assert k.workflow.steps["f"].plan["inverse"] == "trace"
    assert k.workflow.steps["tb"].plan["inverse"] == "opaque"


# ── uneven data: jagged JSON (§9) ────────────────────────────────────────────

@tool
def tags_rc() -> pd.DataFrame:
    return pd.DataFrame({"rid": [1, 2, 3], "tags": [["a", "b"], [], ["d"]]})


@tool
def meta_rc() -> pd.DataFrame:
    return pd.DataFrame({"meta": [{"x": 1, "y": 2}, {"x": 3}, {"x": None, "z": {"deep": True}}]})


@tool
def mixed_rc() -> pd.DataFrame:
    return pd.DataFrame({"tags": [["a"], "c", None]})


@tool
def scores_rc() -> pd.DataFrame:
    return pd.DataFrame({"scores": [{"2026-01": 3, "2026-02": 4}]})


@pytest.fixture
def j():
    return Kernel(Catalog(tools=[tags_rc, meta_rc, mixed_rc, scores_rc]))


def run(k):
    try:
        k.run_all()
    except Exception:
        pass


@pytest.mark.xfail(strict=True, reason="J-D5, R-D4, R-D5: [] loses its parent (J3)")
def test_L22_jagged_lists_round_trip_empty_included(j):
    j["r"] = tags_rc[mod.source()]()
    j["e"] = mod.expand(columns=["tags"])(wf["r"])
    j["back"] = gather[mod.collapse(by="#r")](wf["e"])
    run(j)
    assert data(j, "back").loc[0, "tags"] == ["a", "b"]            # rid 1
    assert data(j, "back").loc[1, "tags"] == []                    # rid 2: [] kept
    assert list(data(j, "back").index) == list(data(j, "r").index)


@pytest.mark.xfail(strict=True, reason="J-D1, J-D2: widen fails rows missing a key (J4)")
def test_L23_widen_takes_the_union_and_marks_missing_keys_absent(j):
    j["m"] = meta_rc[mod.source()]()
    j["w"] = mod.widen()(wf["m"])
    run(j)
    out = j.workflow.steps["w"].output
    assert state(j, "w") == "completed"
    assert list(out.data.columns) == ["x", "y", "z"]
    assert str(out.states.at[1, "y"]) == "absent"                   # no "y" key
    assert str(out.states.at[2, "x"]) == "known"                    # "x": null
    assert out.data["x"].tolist()[:2] == [1, 3]                     # ints stay ints


@pytest.mark.xfail(strict=True, reason="J-D1, R-D2: no pack; absent and null look alike (J4)")
def test_L24_packing_widened_uneven_dicts_gives_them_back(j):
    j["m"] = meta_rc[mod.source()]()
    j["w"] = mod.widen()(wf["m"])
    j["back"] = mod.pack(columns=["x", "y", "z"])(wf["w"])
    run(j)
    assert data(j, "back").iloc[:, 0].tolist() == data(j, "m")["meta"].tolist()


@pytest.mark.xfail(strict=True, reason="J-D3: expand wraps a bare string (J1)")
def test_L25_expand_doesnt_normalise_a_bare_string(j):
    j["m"] = mixed_rc[mod.source()]()
    j["e"] = identity[mod.expand()](wf["m"])
    run(j)
    assert state(j, "e") == "failed"
    assert "not a list" in str(j.workflow.steps["e"].output.notes.get(1))
    assert "a" in data(j, "e").iloc[:, 0].tolist()                  # the other rows ran


@pytest.mark.xfail(strict=True, reason="J-D4: expand of a dict gives one row (J5)")
def test_L26_expanding_a_mapping_gives_key_value_rows(j):
    j["s"] = scores_rc[mod.source()]()
    j["e"] = identity[mod.expand()](wf["s"])
    run(j)
    assert data(j, "e")[["key", "value"]].values.tolist() == [["2026-01", 3], ["2026-02", 4]]


@pytest.mark.xfail(strict=True, reason="J-D3: expand of None gives a None row (J2)")
def test_L27_expanding_none_gives_no_rows(j):
    j["m"] = mixed_rc[mod.source()]()
    j["n"] = mod.select(rows=[2])(wf["m"])                         # the None row
    j["e"] = identity[mod.expand()](wf["n"])
    run(j)
    assert len(data(j, "e")) == 0


# ── # columns and reductions (§5.1, §5.2) ────────────────────────────────────

@tool
def row_keys_rc(**row) -> list:
    return sorted(row)


@pytest.fixture
def e(k):
    k["e"] = readings_rc[mod.expand()](wf["v"])                   # #v: the parent visit
    return k


def test_L28_positions_count_variables_only(e):
    from simple_steps_core import cols
    e["first"] = wf["e"][cols[0]]
    e.run_all()
    assert "#v" in data(e, "e").columns
    assert list(data(e, "first").columns) == ["#v", "value"]       # cols[0] is value; #v is kept


def test_L29_tools_get_variables_only(e):
    k2 = Kernel(Catalog(tools=TOOLS + [row_keys_rc]))
    k2["v"] = visits_rc[mod.source()]()
    k2["e"] = readings_rc[mod.expand()](wf["v"])
    k2["keys"] = row_keys_rc[mod.map()](wf["e"])
    k2.run_all()
    assert "#v" in data(k2, "e").columns
    assert all(not c.startswith("#") for keys in data(k2, "keys")["value"] for c in keys)


def test_L30_zip_of_one_origin_keeps_one_hash_column(e):
    e["a"] = mod.rename(columns={"value": "a"})(wf["e"])
    e["b"] = mod.rename(columns={"value": "b"})(wf["e"])
    e["z"] = zip_(wf["a"], wf["b"])
    e.run_all()
    assert list(data(e, "z").columns).count("#v") == 1


@pytest.mark.xfail(strict=True, reason="R-D5 (step 5): the refusal doesn't say the trace was dropped")
def test_L31_dropping_the_trace_is_a_loss_you_choose(e):
    e["d"] = mod.drop(columns=["#v"])(wf["e"])
    assert state(e, "d") != "invalid"                               # dropping is allowed
    e["back"] = gather[mod.collapse(by="#v")](wf["d"])
    assert state(e, "back") == "invalid"
    assert any("dropped" in str(p) for p in e.workflow.steps["back"].problems)


@pytest.mark.xfail(strict=True, reason="R-D12, R9: the key is in the payload; rows are in a note, not #vt")
def test_L32_a_reduction_lists_the_rows_it_reduced(k):
    k["vt"] = mod.select(columns=["ward", "temp"])(wf["v"])
    k["tot"] = op("total")[mod.collapse(by="ward")](wf["vt"])
    k.run_all()
    assert data(k, "tot").loc["A", "#vt"] == [0, 1, 3]


@pytest.mark.xfail(strict=True, reason="R-D10, R-D12, R9: the key is in the payload; no #vt to unpack")
def test_L33_a_statistic_goes_back_beside_its_rows(k):
    k["vt"] = mod.select(columns=["ward", "temp"])(wf["v"])
    k["tot"] = op("total")[mod.collapse(by="ward")](wf["vt"])
    k["each"] = mod.expand(columns=["#vt"])(wf["tot"])
    k["names"] = mod.select(columns=["name"])(wf["v"])
    k["side"] = zip_(wf["names"], wf["each"])
    k.run_all()
    assert data(k, "side").loc[2, "temp"] == 36.9                   # Ben, ward B's total
    assert data(k, "side").loc[0, "temp"] == pytest.approx(114.6)   # Ada, ward A's total


def test_L34_reducers_over_no_rows_give_their_empty_value(k):
    k["none"] = cold_rc[mod.filter()](wf["t"])
    for reducer in ["count", "total", "gather"]:
        k[reducer] = op(reducer)[mod.collapse()](wf["none"])
    k.run_all()
    assert data(k, "count").iloc[0, 0] == 0
    assert data(k, "total").iloc[0, 0] == 0
    assert data(k, "gather").iloc[0, 0] == []


@tool
def risky_rc(temp: float) -> float:
    if temp > 39:
        raise ValueError("too hot")
    return temp


def test_L35_a_group_holding_a_failed_row_is_blocked():
    k = Kernel(Catalog(tools=[visits_rc, risky_rc]))
    k["v"] = visits_rc[mod.source()]()
    k["r"] = risky_rc[mod.map(), mod.try_except()](wf["v"])
    k["tot"] = op("total")[mod.collapse()](wf["r"])
    run(k)
    assert str(k.workflow.steps["tot"].output.states.iloc[0, 0]) == "blocked"


# ── same samples: pairing across origins (guarantee 3) ───────────────────────

@tool
def label_rc(name: str, head: str) -> str:
    return f"{name}/{head}"


@tool
def ints_rc() -> pd.DataFrame:
    return pd.DataFrame({"x": [10, 20]}, index=[1, 2])


@tool
def strs_rc() -> pd.DataFrame:
    return pd.DataFrame({"y": ["a", "b"]}, index=["1", "2"])


@pytest.mark.xfail(strict=True, reason="R-D7 (step 4): column arguments pair equal ids across origins (M10)")
def test_L36_a_column_argument_from_another_origin_is_refused():
    k = Kernel(Catalog(tools=[visits_rc, wards_rc, label_rc]))
    k["v"] = visits_rc[mod.source()]()
    k["w"] = wards_rc[mod.source()]()
    k["jw"] = join(wf["w"], wf["v"], on="ward")                     # ordered by ward: not v's rows
    from simple_steps_core import cols
    k["lab"] = label_rc[mod.map()](wf["v"], head=wf["jw"][cols["head"]])
    assert state(k, "lab") == "invalid"


@pytest.mark.xfail(strict=True, reason="R-D7 (step 4): ids are matched as text, so 1 pairs with '1' (M11)")
def test_L37_ids_keep_their_type():
    k = Kernel(Catalog(tools=[ints_rc, strs_rc]))
    k["a"] = ints_rc[mod.source()]()
    k["b"] = strs_rc[mod.source()]()
    k["z"] = zip_(wf["a"], wf["b"], match_ids=True)                 # even on purpose: 1 is not "1"
    run(k)
    assert state(k, "z") == "failed"


@pytest.mark.xfail(strict=True, reason="R-D7 (step 4): no match_ids opt-in")
def test_L38_match_ids_pairs_equal_ids_on_purpose():
    k = Kernel(Catalog(tools=[ints_rc]))
    k["a"] = ints_rc[mod.source()]()
    k["b"] = ints_rc[mod.source()]()                                # same ids, unrelated steps
    k["b2"] = mod.rename(columns={"x": "x2"})(wf["b"])
    k["refused"] = zip_(wf["a"], wf["b2"])
    assert state(k, "refused") == "invalid"
    k["z"] = zip_(wf["a"], wf["b2"], match_ids=True)
    k.run_all()
    assert data(k, "z").to_dict("list") == {"x": [10, 20], "x2": [10, 20]}


# ── per-row staleness (guarantee 2) ──────────────────────────────────────────

def test_L41_changing_one_row_makes_only_its_group_stale():
    k = Kernel(Catalog(tools=[]))
    k["v"] = pd.DataFrame({"ward": ["A", "A", "B"], "temp": [1.0, 2.0, 3.0]})
    k["tot"] = op("count")[mod.collapse(by="ward")](wf["v"])
    k.run_all()
    k["v"] = pd.DataFrame({"ward": ["A", "A", "B"], "temp": [1.0, 2.0, 9.0]})   # ward B's row
    stale = {r["#"]: r["state"] for r in k.view("tot")["rows"]}
    assert stale == {"A": "known", "B": "stale"}
