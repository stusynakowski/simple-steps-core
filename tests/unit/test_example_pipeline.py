"""The shipped example's pipeline, run end to end.

    step1  load_batches      single             list[list[float]]  one cell
    step2  unpack_batch      expand   over=1    list[float]        one cell per reading
    step3  above_cutoff      filter   over=2    list[float]        readings that pass
    step4  accumulate_stats  collapse over=3    dict               one cell of statistics

Keeping this test green is what stops the example drifting from the tools it
documents.
"""

import pytest

from simple_steps_core import (
    CoreEngine,
    Operation,
    OrchestrationConfig,
    StepStatus,
    Workflow,
    register_orchestrators,
)
from simple_steps_core.operations.registry import REGISTRY


@pytest.fixture(scope="module")
def example():
    import streamlit_example.example_tools_and_resources as module

    register_orchestrators(REGISTRY)
    return module


def _pipeline(example, *, batches=3, per_batch=4, cutoff=25.0) -> Workflow:
    wf = Workflow(CoreEngine(REGISTRY), session_id="pipeline")
    for name, provider in example.RESOURCES.items():
        wf.context.resources.register(name, provider)

    wf["step1"] = Operation(step_id="step1", name="load_batches",
                            arguments={"batches": batches, "per_batch": per_batch})
    wf["step2"] = Operation(step_id="step2", name="unpack_batch",
                            orchestration=OrchestrationConfig(mode="expand", over="step1"))
    wf["step3"] = Operation(step_id="step3", name="above_cutoff",
                            arguments={"cutoff": cutoff},
                            orchestration=OrchestrationConfig(mode="filter", over="step2"))
    wf["step4"] = Operation(step_id="step4", name="accumulate_stats",
                            orchestration=OrchestrationConfig(mode="collapse", over="step3"))
    return wf


def test_pipeline_validates_before_running(example):
    assert "✓ ok" in str(_pipeline(example).validate())


def test_every_stage_of_the_pipeline_completes(example):
    wf = _pipeline(example)
    wf.run()
    assert all(s.status is StepStatus.COMPLETED for s in wf.steps)


def test_source_is_one_nested_cell(example):
    wf = _pipeline(example, batches=3, per_batch=4)
    wf.run()
    value = wf["step1"].output.value
    assert len(value) == 3 and all(len(batch) == 4 for batch in value)


def test_expand_flattens_to_one_cell_per_reading(example):
    wf = _pipeline(example, batches=3, per_batch=4)
    wf.run()
    readings = wf["step2"].output.value
    assert len(readings) == 12                       # 3 batches x 4 readings
    assert all(isinstance(r, float) for r in readings)


def test_filter_keeps_only_readings_at_or_above_the_cutoff(example):
    wf = _pipeline(example, cutoff=25.0)
    wf.run()
    kept = wf["step3"].output.value
    assert kept and all(r >= 25.0 for r in kept)
    assert set(kept) <= set(wf["step2"].output.value)


def test_collapse_reduces_to_one_cell_of_statistics(example):
    wf = _pipeline(example, cutoff=25.0)
    wf.run()
    kept = wf["step3"].output.value
    stats = wf["step4"].output.value

    assert stats["count"] == len(kept)
    assert stats["minimum"] == min(kept)
    assert stats["maximum"] == max(kept)
    assert stats["mean"] == pytest.approx(sum(kept) / len(kept), abs=0.01)


def test_cutoff_that_excludes_everything_still_runs(example):
    """A filter can legitimately keep nothing; collapse then has no items."""
    wf = _pipeline(example, cutoff=1000.0)
    wf.run()
    assert wf["step3"].output.value == []
    assert wf["step4"].status is StepStatus.COMPLETED
    assert wf["step4"].output.value is None


def test_pipeline_shape_is_visible_before_running(example):
    """Staged cells announce type and shape, which is what the grid shows."""
    from simple_steps_core.streamlit.components import staged_frame

    wf = _pipeline(example)
    row = staged_frame(wf["step2"].spec, REGISTRY.get_definition("unpack_batch")).iloc[0]
    assert row["type"] == "list[float]"        # expand flattens, it does not wrap
    assert row["shape"] == "one cell per item produced from step1"
    assert row["state"] == "staged"

    collapsed = staged_frame(wf["step4"].spec,
                             REGISTRY.get_definition("accumulate_stats")).iloc[0]
    assert collapsed["type"] == "dict"         # collapse yields the accumulator
    assert collapsed["shape"] == "1 cell"


def test_identity_replaces_the_custom_expand_tool(example):
    """`expand` + built-in `identity` reshapes with no bespoke tool."""
    wf = _pipeline(example)
    wf["step2"] = Operation(step_id="step2", name="identity",
                            orchestration=OrchestrationConfig(mode="expand", over="step1"))
    wf.run()

    batches = wf["step1"].output.value
    readings = wf["step2"].output.value
    assert readings == [value for batch in batches for value in batch]
    assert wf["step4"].output.value["count"] == len(wf["step3"].output.value)
