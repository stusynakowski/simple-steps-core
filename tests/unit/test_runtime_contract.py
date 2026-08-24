from simple_steps_core import (
    Cell,
    CoreEngine,
    OperationRegistry,
    SessionContext,
    Shape,
    StepResult,
    ToolCall,
)


def test_contract_symbols_and_tool_call():
    call = ToolCall(operation_id="op", arguments={"value": "step_a"})

    assert call.operation_id == "op"
    assert call.arguments == {"value": "step_a"}
    assert Cell(row_id="0", column_id="value", value=1, display_value="1")
    assert Shape(kind="raw", rows=1, columns=["value"], value_type="int")


def test_operation_definition_includes_category_and_type():
    registry = OperationRegistry()

    def load() -> list[int]:
        return [1, 2]

    registry.register("load", load, category="sources", type="source")

    definition = registry.get_definition("load")
    assert definition.category == "sources"
    assert definition.type == "source"


def test_execute_step_returns_reference_only_result_and_shape():
    registry = OperationRegistry()

    def make_rows():
        return [{"name": "a", "score": 1}, {"name": "b", "score": 2}]

    registry.register("make_rows", make_rows)
    engine = CoreEngine(registry)
    context = SessionContext(session_id="session-a")

    result = engine.execute_step(
        ToolCall(operation_id="make_rows"),
        context,
        step_id="step_rows",
    )

    assert isinstance(result, StepResult)
    assert result.status == "success"
    assert result.step_id == "step_rows"
    assert result.ref_id.startswith("session-a__")
    assert result.shape == context.get_meta(result.ref_id)
    assert result.shape.kind == "raw"
    assert result.shape.rows == 2
    assert result.shape.columns == ["name", "score"]
    assert result.error is None
    assert context.value_for_step("step_rows") == [
        {"name": "a", "score": 1},
        {"name": "b", "score": 2},
    ]


def test_execute_step_captures_operation_failure_as_step_error():
    registry = OperationRegistry()

    def boom():
        raise RuntimeError("kaboom")

    registry.register("boom", boom)
    engine = CoreEngine(registry)
    context = SessionContext(session_id="session-a")

    result = engine.execute_step(ToolCall(operation_id="boom"), context, step_id="step_fail")

    assert result.status == "failed"
    assert result.ref_id == ""
    assert result.error is not None
    assert result.error.message == "kaboom"
    assert result.error.type == "RuntimeError"
    assert result.shape.rows == 0
    assert context.ref_for_step("step_fail") is None


def test_context_views_for_raw_shapes_and_pagination():
    context = SessionContext(session_id="s")
    context.put("ref-dict", {"a": 1, "b": None})
    context.put("ref-list-dict", [{"a": 1}, {"b": 2}, {"a": 3, "b": 4}])
    context.put("ref-list", [10, 20, 30])
    context.put("ref-scalar", "done")
    context.put("ref-none", None)

    assert context.owns("ref-dict")
    assert not context.owns("other-ref")
    assert context.get_meta("ref-dict") == Shape(
        kind="raw",
        rows=1,
        columns=["a", "b"],
        value_type="dict",
    )
    assert context.get_view("ref-dict") == [
        Cell(row_id="0", column_id="a", value=1, display_value="1"),
        Cell(row_id="0", column_id="b", value=None, display_value=""),
    ]

    assert context.get_meta("ref-list-dict").columns == ["a", "b"]
    assert context.get_view("ref-list-dict", offset=1, limit=1) == [
        Cell(row_id="1", column_id="a", value=None, display_value=""),
        Cell(row_id="1", column_id="b", value=2, display_value="2"),
    ]
    assert context.get_view("ref-list", offset=1, limit=2) == [
        Cell(row_id="1", column_id="value", value=20, display_value="20"),
        Cell(row_id="2", column_id="value", value=30, display_value="30"),
    ]
    assert context.get_view("ref-scalar") == [
        Cell(row_id="0", column_id="value", value="done", display_value="done")
    ]
    assert context.get_view("ref-none") == []
