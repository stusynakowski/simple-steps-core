"""Type-driven orchestration inference.

The card configures orchestration from one choice — "read step2" — by comparing
what that step produces with what the parameter declares. These tests pin the
comparison, which is pure and needs no Streamlit.
"""

import pytest

from simple_steps_core import OrchestrationConfig, ToolRegistry, register_orchestrators
from simple_steps_core.streamlit.panels import DraftStep, DraftWorkflow
from simple_steps_core.streamlit.panels.inference import (
    effective_output,
    infer_binding,
)


@pytest.fixture
def registry():
    reg = ToolRegistry()
    register_orchestrators(reg)

    def batches(n: int) -> list[list[float]]:
        return [[1.0, 2.0]] * n

    def readings() -> list[float]:
        return [1.0, 2.0, 3.0]

    def double(value: float) -> float:            # wants one element
        return value * 2

    def mean(rows: list[float]) -> float:         # wants the whole column
        return sum(rows) / len(rows)

    def rows_of_rows(groups: list[list[float]]) -> int:
        return len(groups)

    def untyped(value):                           # no annotation
        return value

    for name, fn in (("batches", batches), ("readings", readings), ("double", double),
                     ("mean", mean), ("rows_of_rows", rows_of_rows), ("untyped", untyped)):
        reg.register(name, fn)
    return reg


def _schema(registry, tool, param):
    return registry.get_definition(tool).input_schema["properties"][param]


# ── what a step produces ─────────────────────────────────────────────────
def test_single_step_produces_its_return_type(registry):
    draft = DraftStep(id="step1", op="readings")
    schema, accessor = effective_output(draft, registry)
    assert schema == {"items": {"type": "number"}, "title": "Result", "type": "array"}
    assert accessor is None


def test_mapped_step_produces_a_map_result_read_through_ok(registry):
    """A MapResult iterates its own fields, not its items, so `.ok` is required."""
    draft = DraftStep(id="step2", op="double",
                      orchestration=OrchestrationConfig(mode="map", over="step1"))
    schema, accessor = effective_output(draft, registry)
    assert schema["type"] == "array"
    assert schema["items"]["type"] == "number"
    assert accessor == ".ok"


def test_expand_flattens_rather_than_wrapping(registry):
    draft = DraftStep(id="step2", op="readings",
                      orchestration=OrchestrationConfig(mode="expand", over="step1"))
    schema, accessor = effective_output(draft, registry)
    assert schema["type"] == "array" and schema["items"]["type"] == "number"
    assert accessor is None


def test_filter_takes_its_element_type_from_its_source(registry):
    """`filter` returns the items it was given, not its predicate's bool."""
    drafts = DraftWorkflow()
    source = DraftStep(id="step1", op="readings")
    filtered = DraftStep(id="step2", op="double",
                         orchestration=OrchestrationConfig(mode="filter", over="step1"))
    drafts.steps = [source, filtered]

    schema, _ = effective_output(filtered, registry, drafts)
    assert schema["type"] == "array"
    assert schema["items"]["type"] == "number"     # not boolean


# ── the inference itself ─────────────────────────────────────────────────
def test_column_into_scalar_param_infers_map(registry):
    """The element-wise case: a column of floats into a float parameter."""
    upstream = DraftStep(id="step1", op="readings")          # list[float]
    binding = infer_binding("step1", upstream, _schema(registry, "double", "value"),
                            registry)
    assert binding.mode == "map"
    assert binding.reference == "step1"


def test_column_into_list_param_infers_once(registry):
    """The statistical case: pass the whole column to a tool that wants a list."""
    upstream = DraftStep(id="step1", op="readings")          # list[float]
    binding = infer_binding("step1", upstream, _schema(registry, "mean", "rows"),
                            registry)
    assert binding.mode == "single"
    assert binding.reference == "step1"


def test_mapped_upstream_into_list_param_collects_through_ok(registry):
    """Collecting the results of a fan-out: `.ok` plus a single call."""
    upstream = DraftStep(id="step1", op="double",
                         orchestration=OrchestrationConfig(mode="map", over="step0"))
    binding = infer_binding("step1", upstream, _schema(registry, "mean", "rows"),
                            registry)
    assert binding.mode == "single"
    assert binding.reference == "step1.ok"


def test_mapped_upstream_into_scalar_param_maps_over_ok(registry):
    upstream = DraftStep(id="step1", op="double",
                         orchestration=OrchestrationConfig(mode="map", over="step0"))
    binding = infer_binding("step1", upstream, _schema(registry, "double", "value"),
                            registry)
    assert binding.mode == "map"
    assert binding.reference == "step1.ok"


def test_nested_column_into_list_param_infers_map(registry):
    """list[list[float]] into a list[float] parameter: each row is one item."""
    upstream = DraftStep(id="step1", op="batches")           # list[list[float]]
    binding = infer_binding("step1", upstream, _schema(registry, "mean", "rows"),
                            registry)
    assert binding.mode == "map"


def test_nested_column_into_nested_param_infers_once(registry):
    upstream = DraftStep(id="step1", op="batches")           # list[list[float]]
    binding = infer_binding("step1", upstream,
                            _schema(registry, "rows_of_rows", "groups"), registry)
    assert binding.mode == "single"


def test_unannotated_parameter_falls_back_to_once(registry):
    """Nothing to compare, so pass it through and let the user correct it."""
    upstream = DraftStep(id="step1", op="readings")
    binding = infer_binding("step1", upstream, _schema(registry, "untyped", "value"),
                            registry)
    assert binding.mode == "single"


def test_integers_satisfy_a_float_parameter(registry):
    upstream = DraftStep(id="step1", op="readings")
    binding = infer_binding("step1", upstream, {"type": "integer"}, registry)
    assert binding.mode == "map"        # element-wise, int vs float is compatible


def test_a_bool_returning_per_item_tool_infers_filter(registry):
    """A predicate applied element-wise means 'keep what passes', not 'flags'."""
    def above(value: float, cutoff: float = 1.0) -> bool:
        return value > cutoff
    registry.register("above", above)

    upstream = DraftStep(id="step1", op="readings")            # list[float]
    binding = infer_binding("step1", upstream, _schema(registry, "above", "value"),
                            registry, target_definition=registry.get_definition("above"))
    assert binding.mode == "filter"


def test_a_value_returning_per_item_tool_still_infers_map(registry):
    upstream = DraftStep(id="step1", op="readings")
    binding = infer_binding("step1", upstream, _schema(registry, "double", "value"),
                            registry, target_definition=registry.get_definition("double"))
    assert binding.mode == "map"
