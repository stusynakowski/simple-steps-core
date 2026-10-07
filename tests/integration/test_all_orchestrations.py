"""The one consolidated example, asserted end to end.

Imports the shared registry + builders from ``examples/all_orchestrations`` and
checks every orchestration's output. This is what keeps that example honest —
one registry of tools, every shape verb, both fan-out chains, the execution
modifiers, serialization, staging/validation and per-row failure.
"""

import sys
from pathlib import Path

import pytest

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "all_orchestrations"
sys.path.insert(0, str(_EXAMPLE))

import pipeline  # noqa: E402  (path inserted above)


@pytest.fixture(scope="module")
def wf():
    return pipeline.run()


# ── sources: a value is one cell until a verb fans out ──────────────────
def test_source_is_a_grid_of_rows(wf):
    assert wf.step("readings").output.shape == (4, 2)
    assert wf.step("records").output.shape == (2, 1)


# ── map: n -> n, input columns carried through plus a payload ───────────
def test_map_adds_a_payload_column_and_keeps_the_rest(wf):
    scored = wf.step("scored").output
    assert scored.values == [10, 20, 30, 20]
    assert list(scored.data.columns) == ["city", "n", "score"]


# ── row-axis reshapers (no tool) ────────────────────────────────────────
def test_filter_keeps_only_matching_rows(wf):
    assert list(wf.step("kept").output.data["n"]) == [2, 3, 2]


def test_slice_takes_rows_by_position(wf):
    assert len(wf.step("head2").output.data) == 2


def test_sort_reorders_rows_descending(wf):
    assert list(wf.step("ranked").output.data["score"]) == [30, 20, 20, 10]


def test_distinct_keeps_first_of_each_group(wf):
    assert list(wf.step("unique_city").output.data["city"]) == ["SF", "NYC", "LA"]


# ── column-axis reshapers (no tool) ─────────────────────────────────────
def test_select_keeps_named_columns_in_order(wf):
    assert list(wf.step("picked").output.data.columns) == ["city", "score"]


def test_drop_removes_named_columns(wf):
    assert "score" not in wf.step("dropped").output.data.columns


def test_rename_changes_names_keeps_values(wf):
    renamed = wf.step("renamed").output.data
    assert "count" in renamed.columns and "n" not in renamed.columns


# ── group -> collapse: the stratified summary ───────────────────────────
def test_group_marks_rows_without_nesting(wf):
    bucketed = wf.step("bucketed").output.data
    assert "bucket" in bucketed.columns and len(bucketed) == 4


def test_collapse_by_group_sums_per_city(wf):
    per_city = wf.step("per_city").output.data.set_index("bucket")["value"]
    assert per_city.to_dict() == {"SF": 4, "NYC": 2, "LA": 2}


# ── collapse to one row ─────────────────────────────────────────────────
def test_collapse_count_and_sum(wf):
    assert wf.step("n_rows").output.item() == 4
    assert wf.step("sum_n").output.item() == 8


# ── expand (unnest longer) and expand -> widen ──────────────────────────
def test_expand_makes_the_grid_longer(wf):
    assert len(wf.step("bursts").output.data) == 1 + 2 + 3 + 2


def test_expand_then_widen_spreads_records_into_columns(wf):
    spread = wf.step("spread").output.data
    assert len(spread) == 8
    assert {"axis", "val"} <= set(spread.columns)


# ── widen (unnest wider) straight off a column of records ───────────────
def test_widen_lifts_fields_into_columns(wf):
    assert list(wf.step("wide").output.data.columns) == ["value", "city", "temp"]


# ── sweep: the cross product of parameters ──────────────────────────────
def test_sweep_builds_one_row_per_combination(wf):
    sweep = wf.step("grid_search").output.data
    assert list(sweep.columns) == ["model", "window", "value"]
    assert len(sweep) == 4


# ── execution modifiers are shape-preserving ────────────────────────────
def test_execution_modifiers_do_not_change_the_result(wf):
    assert wf.step("robust").output.values == [10, 20, 30, 20]


# ── verb inference: passing a reference picks the shape verb ─────────────
def _inferred_kind(wf, sid):
    return wf.step(sid).operation.to_dict()["modifiers"][0]["kind"]


def test_passing_a_reference_infers_the_verb(wf):
    assert _inferred_kind(wf, "auto_map") == "map"
    assert _inferred_kind(wf, "auto_filter") == "filter"
    assert _inferred_kind(wf, "auto_collapse") == "collapse"
    assert _inferred_kind(wf, "auto_expand") == "expand"


def test_inferred_steps_produce_the_same_results_as_explicit_ones(wf):
    assert wf.step("auto_map").output.values == [10, 20, 30, 20]        # like scored
    assert wf.step("auto_filter").output.data["n"].tolist() == [2, 3, 2]  # like kept
    assert wf.step("auto_collapse").output.item() == 8                  # like sum_n
    assert len(wf.step("auto_expand").output.data) == 8                 # like bursts


# ── standard Python types as sources: each is one cell, reshaped by a verb ──
def test_standard_types_are_one_cell(wf):
    assert wf.step("a_list").output.shape == (1, 1)
    assert wf.step("a_list").output.data["value"].iloc[0] == [1, 2, 3, 4]
    assert wf.step("a_dict").output.shape == (1, 1)
    assert wf.step("a_scalar").output.shape == (1, 1)


def test_a_list_cell_expands_and_a_dict_cell_widens(wf):
    assert wf.step("from_list").output.values == [1, 2, 3, 4]
    row = wf.step("from_dict").output.data.iloc[0]
    assert row["x"] == 10 and row["y"] == 20


def test_a_tuple_column_widens_positionally(wf):
    cols = list(wf.step("split").output.data.columns)
    assert "c0" in cols and "c1" in cols


def test_builtin_reducers(wf):
    assert wf.step("gathered").output.item() == [1, 2, 3, 2]
    assert wf.step("total_n").output.item() == 8
    assert wf.step("first_n").output.item() == 1
    assert wf.step("last_n").output.item() == 2


def test_chained_map_over_a_map(wf):
    assert wf.step("again").output.values == [10, 20, 30, 20]


# ── combine verbs — read more than one grid (operation constructors) ──
def test_combine_verbs_read_more_than_one_grid(wf):
    # join: a lookup on a shared key, left-preserving
    enriched = wf.step("enriched").output.data
    assert list(enriched.columns) == ["city", "n", "region"]
    assert list(enriched["region"]) == ["west", "east", "west", "west"]
    # stack: rows appended — the sum of both inputs
    assert list(wf.step("all_readings").output.data["n"]) == [1, 2, 3, 2, 5, 6]
    # zip: two grids aligned by position, columns unioned
    zipped = wf.step("zipped").output.data
    assert list(zipped.columns) == ["n", "score"]
    assert zipped.to_dict("list") == {"n": [1, 2, 3, 2], "score": [10, 20, 30, 20]}


def test_positional_access_and_catalog(wf):
    assert wf[0].id == "readings"          # first step, by position
    assert wf[-1].id == "zipped"           # last step
    cat = pipeline.grid.catalog()
    assert "scale" in cat and cat["count"]["origin"] == "builtin"


# ── every declared step is valid and completed ──────────────────────────
def test_the_whole_workflow_is_valid_and_done(wf):
    assert all(not p for p in wf.validate().values())
    assert all(st.status == "completed" for st in wf.steps.values())


# ── failure: the ledger keeps every unit, failed ones re-drivable ───────
def test_failure_lands_in_the_ledger_not_an_exception():
    fail = pipeline.failure()
    failed = fail.step("out").output.failed
    assert list(failed.index) == [1, 3]        # the two readings whose n == 2
    assert fail.step("out").output.ok.shape[0] == 2


# ── staging / validation happen before anything runs ────────────────────
def test_validation_reports_problems_without_running():
    checks = pipeline.validation()
    problems = checks.validate()
    assert problems["readings"] == () and problems["scored"] == ()
    assert "nope" in problems["bad_arg"][0]
    assert "not an earlier step" in problems["dangling"][0]
    # the good step is staged with a predicted cell count, nothing executed
    assert "map scale" in checks.step("scored").describe()


# ── serialization round-trip reproduces the outputs ─────────────────────
def test_full_session_roundtrip_reproduces_results():
    original, reloaded = pipeline.roundtrip()
    assert reloaded.step("scored").output.values == original.step("scored").output.values
    assert reloaded.step("per_city").output.data.equals(
        original.step("per_city").output.data
    )



# ── resources: FakeDB / FakeLLM, bound and unbound tools (core-proposals/007) ──
# Test ids (T1.x slice 1, T2.x slice 2) match the tables in 007-mvp-resources.md.
@pytest.fixture()
def res_run():
    return pipeline.run_resources()


def test_T1_1_unbound_tool_takes_one_db_instance(res_run):
    wf, live = res_run
    assert wf.step("regions").output.values == ["west", "east", "west", "west"]
    # regions, regions_bound and inferred each read 4 rows — one instance served all
    assert live["db"].reads == 12


def test_T1_2_unbound_tool_takes_the_llm(res_run):
    wf, live = res_run
    assert wf.step("summaries").output.values == ["[fake-1] A", "[fake-1] B"]
    assert live["llm"].calls == 3            # 2 summaries + the bound `hello`


def test_T1_3_T1_4_a_resource_is_not_a_column_and_declares_without_the_object():
    wf = pipeline.build_resources()          # nothing loaded, nothing run
    assert all(p == () for p in wf.validate().values())
    assert pipeline.grid.predicted_columns(wf.step("summaries").output) == ["text", "value"]


def test_T1_5_running_without_the_resource_is_a_clear_problem():
    wf = pipeline.build_resources()
    with pytest.raises(pipeline.grid.ResourceNotLoaded, match="resource 'llm' is not loaded"):
        wf.run("summaries")
    live = pipeline.live_resources()
    del live["llm"]
    with pytest.raises(pipeline.grid.ResourceNotLoaded, match="'llm'"):
        wf.run("summaries", resources=live)
    assert wf.step("summaries").status == "staged"   # the tool never ran


def test_T1_6_T1_8_wrong_type_unknown_name_unmarked_method_are_refused():
    problems = pipeline.resource_problems().validate()
    assert problems["wrong_type"] == (
        "summarize() declares llm: FakeLLM, but it is bound to resource 'db' (FakeDB)",)
    assert "no resource named 'nope'" in problems["unknown"][0]
    assert problems["unmarked"] == ("reset is not a tool of FakeDB; its tools are: lookup",)
    assert "is a resource (FakeLLM), not a column" in problems["not_a_column"][0]


def test_T1_7_a_subclass_fits_its_base(res_run):
    wf, live = res_run
    assert wf.validate()["tiny_summaries"] == ()
    assert wf.step("tiny_summaries").output.values == ["[tiny-1] A", "[tiny-1] B"]
    assert live["tiny"].calls == 2


def test_T1_9_saves_the_declaration_never_the_object():
    import json
    blob = pipeline.build_resources().to_dict()
    ops = {e["step_id"]: e["operation"] for e in blob["steps"]}
    assert ops["summaries"]["arguments"] == {"llm": {"$res": "llm"}}
    assert blob["resources"]["llm"] == {"source": "defined", "type": "FakeLLM",
                                        "settings": {"model": "fake-1"}}
    json.dumps(blob)                         # no object anywhere


def test_T1_10_T2_4_reloads_and_runs(res_run):
    original, reloaded = pipeline.resource_roundtrip()
    assert reloaded.to_dict() == original.to_dict()
    assert all(p == () for p in reloaded.validate().values())
    reloaded.run_all(resources=pipeline.live_resources())
    ran, _ = res_run
    for sid in ("summaries", "regions", "regions_bound", "hello"):
        assert reloaded.step(sid).output.data.equals(ran.step(sid).output.data)


def test_T1_11_redefining_a_resource_marks_its_readers_stale(res_run):
    wf, live = res_run
    wf.define("llm", pipeline.FakeLLM, model="fake-2")
    assert wf.step("summaries").status == "stale"
    assert wf.step("regions").status == "completed"      # does not use llm
    live["llm"] = pipeline.FakeLLM(model="fake-2")
    wf.run("summaries", resources=live)
    assert wf.step("summaries").output.values == ["[fake-2] A", "[fake-2] B"]


def test_T2_1_T2_2_bound_tools_run_on_their_instance(res_run):
    wf, _ = res_run
    assert wf.step("regions_bound").operation.tool_id == "FakeDB.lookup"
    assert wf.step("regions_bound").output.values == ["west", "east", "west", "west"]
    assert wf.step("inferred").output.values == ["west", "east", "west", "west"]
    assert wf.step("hello").output.data.iloc[0, 0] == "[fake-1] HI"


def test_T2_3_catalog_lists_types_settings_and_marked_tools_only():
    cat = pipeline.grid.resource_catalog()
    db, llm = cat["FakeDB"], cat["FakeLLM"]
    assert [s["name"] for s in db["settings"]] == ["table"]
    assert list(db["tools"]) == ["FakeDB.lookup"]          # not reset
    assert db["tools"]["FakeDB.lookup"]["description"] == "The region stored for a key, or None."
    assert [p["name"] for p in db["tools"]["FakeDB.lookup"]["params"]] == ["key"]
    assert [s["name"] for s in llm["settings"]] == ["model"]
    assert list(llm["tools"]) == ["FakeLLM.complete"]
    assert cat["TinyLLM"]["bases"] == ["TinyLLM", "FakeLLM"]


def test_T2_6_tool_code_may_call_unmarked_methods():
    wf = pipeline.build_resources()
    wf["fresh"] = pipeline.lookup_fresh[pipeline.mod.map()](
        wf["readings"], db=pipeline.res["db"])
    live = pipeline.live_resources()
    wf.run("fresh", resources=live)
    assert wf.step("fresh").output.values == ["west", "east", "west", "west"]
    assert live["db"].reads == 1             # each row reset, then read


def test_marked_methods_stay_ordinary_and_unregistered():
    db = pipeline.FakeDB()
    assert db.lookup("SF") == "west" and db.reads == 1
    db.reset()
    assert db.reads == 0
    tools = pipeline.grid.TOOLS
    assert "lookup" not in tools and "complete" not in tools
    assert "enrich" in tools and "summarize" in tools     # unbound tools are ordinary


def test_tool_on_a_method_is_refused_with_a_pointer_to_bound_tool():
    with pytest.raises(TypeError, match="@bound_tool"):
        class Bad:
            @pipeline.tool
            def lookup(self, key: str) -> str:
                return key


def test_the_live_object_must_match_the_declared_type():
    wf = pipeline.build_resources()
    live = pipeline.live_resources()
    live["llm"] = pipeline.FakeDB()
    with pytest.raises(TypeError, match="declared FakeLLM"):
        wf.run("summaries", resources=live)


def test_settings_must_be_literals():
    class Warehouse:
        def __init__(self, seed: pipeline.pd.DataFrame):
            self.seed = seed
    with pytest.raises(TypeError, match="literal settings only"):
        pipeline.grid.Workflow().define("wh", Warehouse, seed=None)
    with pytest.raises(TypeError, match="no setting 'modle'"):
        pipeline.grid.Workflow().define("llm", pipeline.FakeLLM, modle="x")
