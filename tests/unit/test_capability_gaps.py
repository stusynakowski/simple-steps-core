"""The gaps an external capability audit found against 0.1.0.

Each test here pins one reported behaviour. They share a theme: a workflow that
was quietly *wrong* — an ignored index, a literal that looked like a reference,
a model iterated as field tuples, data riding along with a definition — rather
than one that raised.
"""

import json

import pytest

from simple_steps_core import (
    CoreEngine,
    Operation,
    OrchestrationConfig,
    StepExecutionConfig,
    StepStatus,
    ToolCall,
    ToolRegistry,
    Workflow,
    register_orchestrators,
)


def _registry():
    registry = ToolRegistry()
    register_orchestrators(registry)
    registry.register("rows", lambda: [{"n": 1, "name": "a"}, {"n": 2, "name": "b"}])
    registry.register("nested", lambda: {"rows": [{"name": "x"}, {"name": "y"}],
                                         "total": 9})
    registry.register("take", lambda v: v)
    registry.register("nums", lambda: [1, 2, 3, 4])
    return registry


def _two_step(registry, ref, source="rows"):
    workflow = Workflow(CoreEngine(registry), session_id="gap")
    workflow["step1"] = ToolCall(operation_id=source)
    workflow["step2"] = ToolCall(operation_id="take", arguments={"v": ref})
    return workflow


# ── flow.index_ref ───────────────────────────────────────────────────────
def test_a_bracket_index_selects_one_item():
    workflow = _two_step(_registry(), "step1[0]")
    workflow.run()
    assert workflow["step2"].output.value == {"n": 1, "name": "a"}


def test_an_index_can_be_followed_by_a_field():
    workflow = _two_step(_registry(), "step1[1].name")
    workflow.run()
    assert workflow["step2"].output.value == "b"


def test_a_field_can_be_followed_by_an_index():
    workflow = _two_step(_registry(), "step1.rows[1].name", source="nested")
    workflow.run()
    assert workflow["step2"].output.value == "y"


def test_an_out_of_range_index_raises_instead_of_returning_everything():
    """The old behaviour handed back the whole list, which reads as success."""
    workflow = _two_step(_registry(), "step1[99]")
    with pytest.raises(IndexError, match="out of range"):
        workflow.run()


def test_indexing_something_unindexable_says_so():
    workflow = _two_step(_registry(), "step1.total[0]", source="nested")
    with pytest.raises(TypeError, match="not indexable"):
        workflow.run()


def test_a_missing_field_names_the_keys_that_exist():
    workflow = _two_step(_registry(), "step1.missing", source="nested")
    with pytest.raises(KeyError, match="rows"):
        workflow.run()


def test_a_quoted_bracket_key_is_a_key_not_an_index():
    registry = _registry()
    registry.register("digits", lambda: {"0": "zero", "1": "one"})
    workflow = _two_step(registry, 'step1["0"]', source="digits")
    workflow.run()
    assert workflow["step2"].output.value == "zero"


# ── flow.unknown_ref / inspect.validate ──────────────────────────────────
def test_a_reference_to_a_step_that_does_not_exist_fails_validation():
    workflow = _two_step(_registry(), "step99")
    issues = workflow.validate().rows
    assert any("bad reference" in row[1] for row in issues)


def test_a_typo_that_loses_the_step_prefix_is_flagged_as_suspicious():
    """`stpe1` is a literal string, so nothing resolves and nothing complained."""
    workflow = _two_step(_registry(), "stpe1")
    issues = workflow.validate().rows

    assert any("suspicious literal" in row[1] for row in issues)
    assert any("step1" in row[2] for row in issues)


def test_a_literal_naming_a_step_exactly_is_flagged_too():
    registry = _registry()
    workflow = Workflow(CoreEngine(registry), session_id="gap")
    workflow["ingest"] = ToolCall(operation_id="rows")
    workflow["step2"] = ToolCall(operation_id="take", arguments={"v": "ingest"})

    issues = workflow.validate().rows
    assert any("suspicious literal" in row[1] for row in issues)


@pytest.mark.parametrize("literal", [
    "hello world this is a prompt",
    "/mnt/data/file.csv",
    "rows",
    "",
])
def test_ordinary_literals_are_not_flagged(literal):
    """Most string arguments are just strings; the check must stay quiet."""
    workflow = _two_step(_registry(), literal)
    issues = workflow.validate().rows
    assert not any("suspicious" in row[1] for row in issues), issues


def test_a_valid_workflow_still_reports_ok():
    workflow = _two_step(_registry(), "step1")
    assert workflow.validate().rows[0][1].endswith("ok")


# ── orch.map over a previous map ─────────────────────────────────────────
def _chain_registry():
    registry = _registry()

    def half(x):
        if x == 2:
            raise ValueError("cannot halve 2")
        return x / 2

    registry.register("half", half)
    registry.register("tenx", lambda x: x * 10)
    registry.register("is_big", lambda x: x > 5)
    return registry


def _chain():
    workflow = Workflow(CoreEngine(_chain_registry()), session_id="chain")
    workflow["step1"] = ToolCall(operation_id="nums")
    workflow["step2"] = ToolCall(operation_id="map",
                                 arguments={"over": "step1", "op": "half"})
    workflow["step3"] = ToolCall(operation_id="map",
                                 arguments={"over": "step2", "op": "tenx"})
    workflow.run()
    return workflow


def test_mapping_over_a_map_step_iterates_items_not_model_fields():
    """Bare iteration of a MapResult yielded one ('outcomes', [...]) tuple."""
    outcomes = _chain()["step3"].output.value.outcomes
    assert len(outcomes) == 4
    assert [o.value for o in outcomes if o.status is StepStatus.COMPLETED] == [5.0, 15.0, 20.0]


def test_an_upstream_failure_stays_pinned_to_its_own_item():
    outcomes = {o.index: o for o in _chain()["step3"].output.value.outcomes}

    assert outcomes[1].status is StepStatus.FAILED
    assert outcomes[1].error == "cannot halve 2"      # the original error, carried
    assert outcomes[0].status is StepStatus.COMPLETED  # siblings unaffected


def test_a_failed_item_is_not_re_run_by_the_next_step():
    registry = _chain_registry()
    seen = []
    registry.register("watch", lambda x: seen.append(x) or x)

    workflow = Workflow(CoreEngine(registry), session_id="norerun")
    workflow["step1"] = ToolCall(operation_id="nums")
    workflow["step2"] = ToolCall(operation_id="map",
                                 arguments={"over": "step1", "op": "half"})
    workflow["step3"] = ToolCall(operation_id="map",
                                 arguments={"over": "step2", "op": "watch"})
    workflow.run()

    # 4 items in, 1 failed upstream: the survivor op sees exactly 3.
    assert len(seen) == 3
    assert None not in seen


def test_the_other_modes_consume_the_successful_values():
    workflow = _chain()
    engine = workflow.engine
    workflow["step4"] = ToolCall(operation_id="filter",
                                 arguments={"over": "step3", "op": "is_big"})
    workflow.run_step("step4")
    assert workflow["step4"].output.value == [15.0, 20.0]

    workflow["step5"] = ToolCall(operation_id="expand", arguments={"over": "step3"})
    workflow.run_step("step5")
    assert workflow["step5"].output.value == [5.0, 15.0, 20.0]
    assert engine is workflow.engine


# ── orch.nested ──────────────────────────────────────────────────────────
def test_two_levels_of_fan_out_flatten_in_order():
    """documents -> pages -> paragraphs, previously untested territory."""
    registry = _registry()
    registry.register("documents", lambda: ["doc-a", "doc-b"])
    registry.register("pages_of", lambda doc: [f"{doc}/p1", f"{doc}/p2"])
    registry.register("paragraphs_of", lambda page: [f"{page}#1", f"{page}#2"])
    registry.register("label", lambda para: para.upper())

    workflow = Workflow(CoreEngine(registry), session_id="nested")
    workflow["step1"] = ToolCall(operation_id="documents")
    workflow["step2"] = ToolCall(operation_id="expand",
                                 arguments={"over": "step1", "op": "pages_of"})
    workflow["step3"] = ToolCall(operation_id="expand",
                                 arguments={"over": "step2", "op": "paragraphs_of"})
    workflow["step4"] = ToolCall(operation_id="map",
                                 arguments={"over": "step3", "op": "label"})
    workflow.run()

    assert workflow["step2"].output.value == [
        "doc-a/p1", "doc-a/p2", "doc-b/p1", "doc-b/p2"]
    assert len(workflow["step3"].output.value) == 8
    assert workflow["step3"].output.value[0] == "doc-a/p1#1"
    assert workflow["step4"].output.value.ok[0] == "DOC-A/P1#1"


# ── persist.recipe_only ──────────────────────────────────────────────────
def _ran_workflow():
    registry = _registry()
    registry.register("shout", lambda row: str(row).upper())

    workflow = Workflow(CoreEngine(registry), session_id="rec")
    workflow.add(Operation(step_id="step1", name="rows"))
    workflow.add(Operation(step_id="step2", name="shout",
                           orchestration=OrchestrationConfig(mode="map", over="step1"),
                           execution=StepExecutionConfig(concurrency=4, retries=2)))
    workflow.run()
    return workflow, registry


def test_the_recipe_carries_no_computed_values():
    """Step embeds output.value inline, so a dump shipped the data."""
    workflow, _registry_ = _ran_workflow()
    blob = workflow.to_json()

    assert "'n': 1" not in blob and '"name": "a"' not in blob
    for step in json.loads(blob):
        assert step["output"]["value"] is None
        assert step["output"]["ref"] is None
        assert step["status"] == "pending"


def test_the_recipe_keeps_everything_needed_to_rerun():
    workflow, registry = _ran_workflow()
    reloaded = Workflow.from_json(workflow.to_json(), CoreEngine(registry),
                                  session_id="rerun")

    assert [s.step_id for s in reloaded.steps] == ["step1", "step2"]
    assert reloaded["step2"].spec.execution.concurrency == 4
    assert reloaded["step2"].spec.execution.retries == 2
    assert reloaded["step2"].spec.orchestration.mode == "map"

    reloaded.run()
    assert reloaded["step2"].output.value.ok == [
        "{'N': 1, 'NAME': 'A'}", "{'N': 2, 'NAME': 'B'}"]


def test_recipe_does_not_disturb_the_live_workflow():
    workflow, _registry_ = _ran_workflow()
    workflow.to_json()

    assert workflow["step1"].status is StepStatus.COMPLETED
    assert workflow["step1"].output.value == [{"n": 1, "name": "a"},
                                              {"n": 2, "name": "b"}]


def test_a_session_export_does_carry_the_data():
    """The other half of the contract: export_session is how data travels."""
    workflow, registry = _ran_workflow()
    restored = Workflow.import_session_json(workflow.export_session_json(),
                                            CoreEngine(registry))

    assert restored["step1"].output.value == [{"n": 1, "name": "a"},
                                              {"n": 2, "name": "b"}]
    assert restored["step1"].status is StepStatus.COMPLETED
