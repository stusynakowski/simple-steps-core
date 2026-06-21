"""Unit tests for the built-in orchestrators (map/filter/expand/collapse).

Reference tokens must start with ``step`` and be written as quoted strings in
formulas (e.g. ``over="step_nums"``), matching the reference grammar.
"""

import asyncio

import pytest

from simple_steps_core import (
    CoreEngine,
    MapResult,
    OperationRegistry,
    Workflow,
    register_orchestrators,
)


def _registry():
    registry = OperationRegistry()

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
    wf["step_nums"] = "=make_list(n=4)"
    wf["step_mapped"] = '=map(over="step_nums", op="double")'
    wf.run()

    result = wf["step_mapped"].output.value
    assert isinstance(result, MapResult)
    assert result.ok == [0, 2, 4, 6]
    assert result.failed == []


def test_map_isolates_failures_with_collect():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="map-fail")
    wf["step_nums"] = "=make_list(n=5)"
    wf["step_mapped"] = '=map(over="step_nums", op="fail_on_three", on_error="collect")'
    wf.run()

    result = wf["step_mapped"].output.value
    assert result.ok == [0, 10, 20, 40]      # 3 omitted
    assert result.failed_count == 1
    assert result.failed[0].index == 3


def test_map_fail_fast_raises():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="map-fastfail")
    wf["step_nums"] = "=make_list(n=5)"
    wf["step_mapped"] = '=map(over="step_nums", op="fail_on_three", on_error="fail_fast")'
    with pytest.raises(Exception):
        wf.run()


def test_map_over_async_operation():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="map-async")
    wf["step_nums"] = "=make_list(n=3)"
    wf["step_mapped"] = '=map(over="step_nums", op="adouble")'
    wf.run()
    assert wf["step_mapped"].output.value.ok == [0, 2, 4]


def test_map_ok_field_is_referenceable():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="map-ref")
    wf["step_nums"] = "=make_list(n=4)"
    wf["step_mapped"] = '=map(over="step_nums", op="double")'
    # collapse(add) over the successful values referenced via step_mapped.ok
    wf["step_total"] = '=collapse(over="step_mapped.ok", op="add", initial=0)'
    wf.run()
    assert wf["step_total"].output.value == 0 + 0 + 2 + 4 + 6


def test_filter_keeps_truthy():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="filter-test")
    wf["step_nums"] = "=make_list(n=6)"
    wf["step_evens"] = '=filter(over="step_nums", op="is_even")'
    wf.run()
    assert wf["step_evens"].output.value == [0, 2, 4]


def test_expand_flattens():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="expand-test")
    wf["step_nums"] = "=make_list(n=3)"
    wf["step_expanded"] = '=expand(over="step_nums", op="explode")'
    wf.run()
    assert wf["step_expanded"].output.value == [0, 0, 1, 1, 2, 2]


def test_collapse_reduces():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="collapse-test")
    wf["step_nums"] = "=make_list(n=5)"
    wf["step_sum"] = '=collapse(over="step_nums", op="add", initial=0)'
    wf.run()
    assert wf["step_sum"].output.value == 10


def test_arun_executes_orchestrators():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="arun-test")
    wf["step_nums"] = "=make_list(n=4)"
    wf["step_mapped"] = '=map(over="step_nums", op="adouble")'

    asyncio.run(wf.arun())
    assert wf["step_mapped"].output.value.ok == [0, 2, 4, 6]
