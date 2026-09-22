"""Orchestrating over a DataFrame.

Iterating a DataFrame in Python yields its **column names**, so a fan-out over
a frame used to run once per column and say nothing about it. These tests pin
the two rules that replaced that: rows arrive as dicts, and a frame that goes
into an orchestration comes back out as a frame.
"""

import pytest

from simple_steps_core import (
    CoreEngine,
    Operation,
    OrchestrationConfig,
    ToolCall,
    ToolRegistry,
    Workflow,
    is_frame,
    items_of,
    register_orchestrators,
    select_positions,
)

pd = pytest.importorskip("pandas")


def _registry():
    registry = ToolRegistry()

    def load_frame() -> "pd.DataFrame":
        return pd.DataFrame(
            {"a": [1, 2, 3], "region": ["east", "west", "east"]}
        )

    def is_big(row: dict) -> bool:
        return row["a"] > 1

    def region_of(row: dict) -> str:
        return row["region"]

    def score(row: dict) -> int:
        return row["a"] * 10

    def split_row(row: dict) -> list[dict]:
        return [{"a": row["a"], "half": row["a"] / 2}]

    def add_a(acc, row: dict) -> int:
        running = acc["a"] if isinstance(acc, dict) else acc
        return running + row["a"]

    for fn in (load_frame, is_big, region_of, score, split_row, add_a):
        registry.register(fn.__name__, fn)
    register_orchestrators(registry)
    return registry


def _run(mode_call: ToolCall) -> Workflow:
    workflow = Workflow(CoreEngine(_registry()), session_id="frame")
    workflow["step1"] = ToolCall(operation_id="load_frame")
    workflow["step2"] = mode_call
    workflow.run()
    return workflow


# ── the bug this fixes ───────────────────────────────────────────────────
def test_map_runs_once_per_row_not_once_per_column():
    workflow = _run(ToolCall(operation_id="map",
                             arguments={"over": "step1", "op": "score"}))
    result = workflow["step2"].output.value

    # Three rows, not two columns.
    assert len(result.outcomes) == 3
    assert result.ok == [10, 20, 30]


def test_a_row_reaches_a_tool_as_a_plain_dict():
    seen = []
    registry = _registry()
    registry.register("capture", lambda row: seen.append(row) or True)

    workflow = Workflow(CoreEngine(registry), session_id="capture")
    workflow["step1"] = ToolCall(operation_id="load_frame")
    workflow["step2"] = ToolCall(operation_id="map",
                                 arguments={"over": "step1", "op": "capture"})
    workflow.run()

    assert seen[0] == {"a": 1, "region": "east"}
    assert all(isinstance(row, dict) for row in seen)


# ── shape preservation ───────────────────────────────────────────────────
def test_filtering_a_frame_returns_a_frame():
    workflow = _run(ToolCall(operation_id="filter",
                             arguments={"over": "step1", "op": "is_big"}))
    out = workflow["step2"].output.value

    assert is_frame(out)
    assert list(out["a"]) == [2, 3]
    assert list(out.columns) == ["a", "region"]


def test_filtering_preserves_dtypes_and_index_labels():
    workflow = _run(ToolCall(operation_id="filter",
                             arguments={"over": "step1", "op": "is_big"}))
    source = workflow["step1"].output.value
    out = workflow["step2"].output.value

    assert dict(out.dtypes) == dict(source.dtypes)
    # iloc selection keeps the original row labels, so a row stays identifiable.
    assert list(out.index) == [1, 2]


def test_grouping_a_frame_gives_a_frame_per_bucket():
    workflow = _run(ToolCall(operation_id="group",
                             arguments={"over": "step1", "op": "region_of"}))
    groups = workflow["step2"].output.value

    assert groups.keys() == ["east", "west"]
    assert all(is_frame(bucket) for bucket in groups.values())
    assert list(groups["east"]["a"]) == [1, 3]
    assert list(groups["east"].index) == [0, 2]


def test_expanding_a_frame_of_dict_rows_rebuilds_a_frame():
    workflow = _run(ToolCall(operation_id="expand",
                             arguments={"over": "step1", "op": "split_row"}))
    out = workflow["step2"].output.value

    assert is_frame(out)
    assert list(out.columns) == ["a", "half"]
    assert list(out["half"]) == [0.5, 1.0, 1.5]


def test_collapsing_a_frame_reduces_over_rows():
    workflow = _run(ToolCall(operation_id="collapse",
                             arguments={"over": "step1", "op": "add_a", "initial": 0}))
    assert workflow["step2"].output.value == 6


def test_a_list_still_behaves_exactly_as_before():
    """Shape preservation must not change the non-frame path."""
    registry = _registry()
    registry.register("numbers", lambda: [1, 2, 3])
    registry.register("big", lambda x: x > 1)

    workflow = Workflow(CoreEngine(registry), session_id="list")
    workflow["step1"] = ToolCall(operation_id="numbers")
    workflow["step2"] = ToolCall(operation_id="filter",
                                 arguments={"over": "step1", "op": "big"})
    workflow.run()

    assert workflow["step2"].output.value == [2, 3]


def test_a_frame_flows_through_the_operation_spec_too():
    workflow = Workflow(CoreEngine(_registry()), session_id="spec")
    workflow.add(Operation(step_id="step1", name="load_frame"))
    workflow.add(
        Operation(
            step_id="step2",
            name="is_big",
            orchestration=OrchestrationConfig(mode="filter", over="step1"),
        )
    )
    workflow.run()

    assert is_frame(workflow["step2"].output.value)
    assert len(workflow["step2"].output.value) == 2


# ── the helpers on their own ─────────────────────────────────────────────
def test_items_of_reads_rows_from_a_frame_and_leaves_lists_alone():
    frame = pd.DataFrame({"a": [1, 2]})
    assert items_of(frame) == [{"a": 1}, {"a": 2}]
    assert items_of([1, 2]) == [1, 2]
    assert items_of((x for x in [1, 2])) == [1, 2]


def test_select_positions_matches_the_container_it_was_given():
    frame = pd.DataFrame({"a": [1, 2, 3]})
    assert list(select_positions(frame, [0, 2])["a"]) == [1, 3]
    assert select_positions(["x", "y", "z"], [0, 2]) == ["x", "z"]


def test_is_frame_does_not_need_pandas_imported_to_say_no():
    assert is_frame([1, 2, 3]) is False
    assert is_frame({"a": 1}) is False
    assert is_frame(pd.DataFrame({"a": [1]})) is True


# ── stratification: group -> per-stratum op -> one table ─────────────────
# This was silently broken: a plain dict iterates its KEYS, so a map over a
# group result handed each tool a bare label and lost the rows.
def _strata_registry():
    registry = _registry()

    def summarize_stratum(group) -> dict:
        return {
            "region": group.key,
            "rows": len(group),
            "total": int(group.rows["a"].sum()),
        }

    registry.register("summarize_stratum", summarize_stratum)
    return registry


def _stratified(registry) -> Workflow:
    workflow = Workflow(CoreEngine(registry), session_id="strata")
    workflow["step1"] = ToolCall(operation_id="load_frame")
    workflow["step2"] = ToolCall(operation_id="group",
                                 arguments={"over": "step1", "op": "region_of"})
    workflow["step3"] = ToolCall(operation_id="map",
                                 arguments={"over": "step2", "op": "summarize_stratum"})
    workflow.run()
    return workflow


def test_a_per_stratum_tool_receives_the_rows_not_the_key():
    workflow = _stratified(_strata_registry())
    rows = workflow["step3"].output.value.ok

    assert rows == [
        {"region": "east", "rows": 2, "total": 4},
        {"region": "west", "rows": 1, "total": 2},
    ]


def test_the_stratified_rows_assemble_into_a_table():
    """The end of the pipeline: one row per stratum, ready to save."""
    workflow = _stratified(_strata_registry())
    table = pd.DataFrame(workflow["step3"].output.value.ok)

    assert list(table.columns) == ["region", "rows", "total"]
    assert len(table) == 2
    assert table.loc[table["region"] == "east", "total"].item() == 4


def test_iterating_groups_yields_records_and_lookup_still_works():
    groups = _stratified(_strata_registry())["step2"].output.value

    assert [g.key for g in groups] == ["east", "west"]
    assert all(is_frame(g.rows) for g in groups)
    assert len(groups) == 2
    assert "east" in groups and "south" not in groups
    assert list(groups["east"]["a"]) == [1, 3]        # dict-style lookup survives


def test_a_stratum_can_be_reduced_as_well_as_mapped():
    """collapse over the strata folds them into one value."""
    registry = _strata_registry()
    registry.register("add_sizes", lambda acc, group: (
        (acc if isinstance(acc, int) else len(acc)) + len(group)
    ))

    workflow = Workflow(CoreEngine(registry), session_id="strata-reduce")
    workflow["step1"] = ToolCall(operation_id="load_frame")
    workflow["step2"] = ToolCall(operation_id="group",
                                 arguments={"over": "step1", "op": "region_of"})
    workflow["step3"] = ToolCall(operation_id="collapse",
                                 arguments={"over": "step2", "op": "add_sizes", "initial": 0})
    workflow.run()

    assert workflow["step3"].output.value == 3        # 2 east rows + 1 west row


# ── the unresolved-reference trap ────────────────────────────────────────
def test_fanning_out_over_a_string_is_refused_not_iterated_by_character():
    """`over="s1"` is a literal string: the grammar only resolves "step*".

    Left alone it produced one item per character — two "results" from a
    two-character step id — which is the worst kind of wrong answer.
    """
    registry = _registry()
    registry.register("shout", lambda x: str(x).upper())

    workflow = Workflow(CoreEngine(registry), session_id="badref")
    workflow["s1"] = ToolCall(operation_id="load_frame")
    workflow["s2"] = ToolCall(operation_id="map",
                              arguments={"over": "s1", "op": "shout"})

    with pytest.raises(TypeError, match="must start with 'step'"):
        workflow.run()


def test_items_of_refuses_a_bare_string():
    with pytest.raises(TypeError, match="not a collection"):
        items_of("step1")
