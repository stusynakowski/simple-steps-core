from simple_steps_core.domain.models import ToolCall
from simple_steps_core.execution.context import SessionContext
from simple_steps_core.execution.engine import CoreEngine
from simple_steps_core.operations.registry import OperationRegistry


def test_engine_executes_registered_operation_with_session_context():
    registry = OperationRegistry()

    def greet(name: str):
        return f"hello {name}"

    registry.register("greet", greet)
    engine = CoreEngine(registry)
    context = SessionContext(session_id="session-a")

    ref_id, value = engine.execute(ToolCall(operation_id="greet", arguments={"name": "stuart"}), context)

    assert ref_id.startswith("session-a__")
    assert value == "hello stuart"
    assert context.get(ref_id) == "hello stuart"
