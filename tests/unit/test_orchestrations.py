"""Unit tests for the built-in orchestrators (map/filter/expand/collapse).

Reference tokens must start with ``step`` and be written as quoted strings in
the ``over`` argument (e.g. ``over="step_nums"``), matching the reference grammar.
"""

import asyncio

import pytest

from simple_steps_core import (
    CoreEngine,
    MapResult,
    Operation,
    OrchestrationConfig,
    ToolRegistry,
    ToolCall,
    Workflow,
    register_orchestrators,
)


def _registry():
    registry = ToolRegistry()

    def make_list(n: int) -> list[int]:
        return list(range(n))

    def double(x: int) -> int:
        return x * 2

    def is_even(x: int) -> bool:
        return x % 2 == 0

    def explode(x: int) -> list[int]:
        return [x, x]

    def add(acc: int, item: int) -> int:
        return acc + item

    async def adouble(x: int) -> int:
        await asyncio.sleep(0)
        return x * 2

    def fail_on_three(x: int) -> int:
        if x == 3:
            raise ValueError("no threes")
        return x * 10

    registry.register("make_list", make_list)
    registry.register("double", double)
    registry.register("is_even", is_even)
    registry.register("explode", explode)
    registry.register("add", add)
    registry.register("adouble", adouble)
    registry.register("fail_on_three", fail_on_three)
    register_orchestrators(registry)
    return registry


def test_map_collects_per_item_outcomes():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="map-test")
    wf["step_nums"] = ToolCall(operation_id="make_list", arguments={"n": 4})
    wf["step_mapped"] = ToolCall(operation_id="map", arguments={"over": "step_nums", "op": "double"})
    wf.run()

    result = wf["step_mapped"].output.value
    assert isinstance(result, MapResult)
    assert result.ok == [0, 2, 4, 6]
    assert result.failed == []


def test_map_isolates_failures_with_collect():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="map-fail")
    wf["step_nums"] = ToolCall(operation_id="make_list", arguments={"n": 5})
    wf["step_mapped"] = ToolCall(operation_id="map", arguments={"over": "step_nums", "op": "fail_on_three", "on_error": "collect"})
    wf.run()

    result = wf["step_mapped"].output.value
    assert result.ok == [0, 10, 20, 40]      # 3 omitted
    assert result.failed_count == 1
    assert result.failed[0].index == 3


def test_map_fail_fast_raises():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="map-fastfail")
    wf["step_nums"] = ToolCall(operation_id="make_list", arguments={"n": 5})
    wf["step_mapped"] = ToolCall(operation_id="map", arguments={"over": "step_nums", "op": "fail_on_three", "on_error": "fail_fast"})
    with pytest.raises(Exception):
        wf.run()


def test_map_over_async_operation():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="map-async")
    wf["step_nums"] = ToolCall(operation_id="make_list", arguments={"n": 3})
    wf["step_mapped"] = ToolCall(operation_id="map", arguments={"over": "step_nums", "op": "adouble"})
    wf.run()
    assert wf["step_mapped"].output.value.ok == [0, 2, 4]


def test_map_ok_field_is_referenceable():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="map-ref")
    wf["step_nums"] = ToolCall(operation_id="make_list", arguments={"n": 4})
    wf["step_mapped"] = ToolCall(operation_id="map", arguments={"over": "step_nums", "op": "double"})
    # collapse(add) over the successful values referenced via step_mapped.ok
    wf["step_total"] = ToolCall(operation_id="collapse", arguments={"over": "step_mapped.ok", "op": "add", "initial": 0})
    wf.run()
    assert wf["step_total"].output.value == 0 + 0 + 2 + 4 + 6


def test_filter_keeps_truthy():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="filter-test")
    wf["step_nums"] = ToolCall(operation_id="make_list", arguments={"n": 6})
    wf["step_evens"] = ToolCall(operation_id="filter", arguments={"over": "step_nums", "op": "is_even"})
    wf.run()
    assert wf["step_evens"].output.value == [0, 2, 4]


def test_expand_flattens():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="expand-test")
    wf["step_nums"] = ToolCall(operation_id="make_list", arguments={"n": 3})
    wf["step_expanded"] = ToolCall(operation_id="expand", arguments={"over": "step_nums", "op": "explode"})
    wf.run()
    assert wf["step_expanded"].output.value == [0, 0, 1, 1, 2, 2]


def test_collapse_reduces():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="collapse-test")
    wf["step_nums"] = ToolCall(operation_id="make_list", arguments={"n": 5})
    wf["step_sum"] = ToolCall(operation_id="collapse", arguments={"over": "step_nums", "op": "add", "initial": 0})
    wf.run()
    assert wf["step_sum"].output.value == 10


def test_arun_executes_orchestrators():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="arun-test")
    wf["step_nums"] = ToolCall(operation_id="make_list", arguments={"n": 4})
    wf["step_mapped"] = ToolCall(operation_id="map", arguments={"over": "step_nums", "op": "adouble"})

    asyncio.run(wf.arun())
    assert wf["step_mapped"].output.value.ok == [0, 2, 4, 6]


# ── identity: reshape without transforming ───────────────────────────────
def _reshape_registry():
    registry = ToolRegistry()
    register_orchestrators(registry)

    def nested(n: int) -> list[list[int]]:
        return [[i, i + 1] for i in range(n)]

    def mixed() -> list:
        return [1, 0, 2, None, 3]

    registry.register("nested", nested)
    registry.register("mixed", mixed)
    return registry


def test_identity_is_registered_with_the_orchestrators():
    registry = _reshape_registry()
    assert registry.has("identity")
    params = registry.get_definition("identity").params
    assert [p.name for p in params] == ["value"]


def test_expand_with_identity_flattens_one_level():
    """The common reshape: a cell of lists becomes one row per inner element."""
    registry = _reshape_registry()
    wf = Workflow(CoreEngine(registry), session_id="r")
    wf["step1"] = Operation(step_id="step1", name="nested", arguments={"n": 3})
    wf["step2"] = Operation(step_id="step2", name="identity",
                            orchestration=OrchestrationConfig(mode="expand", over="step1"))
    wf.run()
    assert wf["step1"].output.value == [[0, 1], [1, 2], [2, 3]]
    assert wf["step2"].output.value == [0, 1, 1, 2, 2, 3]


def test_map_with_identity_gives_one_cell_per_item():
    registry = _reshape_registry()
    wf = Workflow(CoreEngine(registry), session_id="r")
    wf["step1"] = Operation(step_id="step1", name="nested", arguments={"n": 2})
    wf["step2"] = Operation(step_id="step2", name="identity",
                            orchestration=OrchestrationConfig(mode="map", over="step1"))
    wf.run()
    result = wf["step2"].output.value
    assert [o.value for o in result.outcomes] == [[0, 1], [1, 2]]
    assert result.failed == []


def test_filter_with_identity_keeps_truthy_items():
    registry = _reshape_registry()
    wf = Workflow(CoreEngine(registry), session_id="r")
    wf["step1"] = Operation(step_id="step1", name="mixed")
    wf["step2"] = Operation(step_id="step2", name="identity",
                            orchestration=OrchestrationConfig(mode="filter", over="step1"))
    wf.run()
    assert wf["step2"].output.value == [1, 2, 3]


# ── identity is the default per-item op ──────────────────────────────────
def test_fan_out_modes_default_their_op_to_identity():
    """`map`/`filter`/`expand` are complete calls with only `over`."""
    registry = _reshape_registry()
    for name in ("map", "filter", "expand"):
        param = next(p for p in registry.get_definition(name).params if p.name == "op")
        assert param.required is False
        assert param.default == "identity"


def test_collapse_still_requires_an_op():
    """A reduce needs a two-argument combiner; identity takes one."""
    registry = _reshape_registry()
    param = next(p for p in registry.get_definition("collapse").params if p.name == "op")
    assert param.required is True

    wf = Workflow(CoreEngine(registry), session_id="c")
    wf["step1"] = ToolCall(operation_id="nested", arguments={"n": 2})
    wf["step2"] = ToolCall(operation_id="collapse", arguments={"over": "step1"})
    with pytest.raises(Exception, match="op"):
        wf.run()


def test_expand_with_no_op_flattens():
    registry = _reshape_registry()
    wf = Workflow(CoreEngine(registry), session_id="d")
    wf["step1"] = ToolCall(operation_id="nested", arguments={"n": 3})
    wf["step2"] = ToolCall(operation_id="expand", arguments={"over": "step1"})
    wf.run()
    assert wf["step2"].output.value == [0, 1, 1, 2, 2, 3]


def test_map_and_filter_with_no_op():
    registry = _reshape_registry()
    wf = Workflow(CoreEngine(registry), session_id="e")
    wf["step1"] = ToolCall(operation_id="mixed", arguments={})
    wf["step2"] = ToolCall(operation_id="map", arguments={"over": "step1"})
    wf["step3"] = ToolCall(operation_id="filter", arguments={"over": "step1"})
    wf.run()
    assert [o.value for o in wf["step2"].output.value.outcomes] == [1, 0, 2, None, 3]
    assert wf["step3"].output.value == [1, 2, 3]


# ── group ────────────────────────────────────────────────────────────────
# `group` is the inverse of `expand`: its `op` is a KEY function, and each
# item lands in the bucket named by the key its op returned.
def _group_registry():
    registry = ToolRegistry()

    def words() -> list[str]:
        return ["apple", "avocado", "blueberry", "cherry", "banana"]

    def first_letter(word: str) -> str:
        return word[0]

    def unhashable_key(word: str) -> list:
        return [word]

    def total(acc: int, item: str) -> int:
        return acc + len(item)

    registry.register("words", words)
    registry.register("first_letter", first_letter)
    registry.register("unhashable_key", unhashable_key)
    registry.register("total", total)
    register_orchestrators(registry)
    return registry


def test_group_buckets_items_by_the_key_its_op_returns():
    wf = Workflow(CoreEngine(_group_registry()), session_id="group")
    wf["step1"] = ToolCall(operation_id="words")
    wf["step2"] = ToolCall(operation_id="group", arguments={"over": "step1", "op": "first_letter"})
    wf.run()

    assert wf["step2"].output.value.to_dict() == {
        "a": ["apple", "avocado"],
        "b": ["blueberry", "banana"],
        "c": ["cherry"],
    }


def test_group_keeps_first_appearance_order_for_keys_and_items():
    wf = Workflow(CoreEngine(_group_registry()), session_id="group-order")
    wf["step1"] = ToolCall(operation_id="words")
    wf["step2"] = ToolCall(operation_id="group", arguments={"over": "step1", "op": "first_letter"})
    wf.run()

    groups = wf["step2"].output.value
    assert groups.keys() == ["a", "b", "c"]              # keys in first-seen order
    assert groups["b"] == ["blueberry", "banana"]        # items in original order
    # Iterating yields records, not keys — that is what makes a per-stratum
    # fan-out possible.
    assert [g.key for g in groups] == ["a", "b", "c"]
    assert [len(g) for g in groups] == [2, 2, 1]


def test_group_buckets_the_item_not_the_key():
    """The bucket holds the original items, so a per-group reduce sees them."""
    registry = _group_registry()
    wf = Workflow(CoreEngine(registry), session_id="group-values")
    wf["step1"] = ToolCall(operation_id="words")
    wf["step2"] = ToolCall(operation_id="group", arguments={"over": "step1", "op": "first_letter"})
    wf.run()

    assert all(isinstance(v, list) for v in wf["step2"].output.value.values())
    assert wf["step2"].output.value["c"] == ["cherry"]


def test_group_skips_an_unhashable_key_by_default():
    wf = Workflow(CoreEngine(_group_registry()), session_id="group-unhashable")
    wf["step1"] = ToolCall(operation_id="words")
    wf["step2"] = ToolCall(operation_id="group", arguments={"over": "step1", "op": "unhashable_key"})
    wf.run()

    assert wf["step2"].output.value.to_dict() == {}


def test_group_fail_fast_reports_the_unhashable_key():
    wf = Workflow(CoreEngine(_group_registry()), session_id="group-strict")
    wf["step1"] = ToolCall(operation_id="words")
    wf["step2"] = ToolCall(
        operation_id="group",
        arguments={"over": "step1", "op": "unhashable_key", "on_error": "fail_fast"},
    )
    with pytest.raises(TypeError, match="unhashable"):
        wf.run()


def test_group_spec_compiles_through_the_orchestration_mode():
    registry = _group_registry()
    wf = Workflow(CoreEngine(registry), session_id="group-spec")
    wf.add(Operation(step_id="step1", name="words"))
    wf.add(
        Operation(
            step_id="step2",
            name="first_letter",
            orchestration=OrchestrationConfig(mode="group", over="step1"),
        )
    )
    assert wf["step2"].call.operation_id == "orchestration-group"

    wf.run()
    assert wf["step2"].output.value["a"] == ["apple", "avocado"]
