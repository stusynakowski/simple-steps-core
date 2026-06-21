from simple_steps_core.operations.registry import OperationRegistry


def test_registry_registers_callable_and_definition():
    registry = OperationRegistry()

    def add(a: int, b: int = 1):
        return a + b

    registry.register("add", add, description="Add two numbers")
    definition = registry.list_definitions()[0]

    assert definition.operation_id == "add"
    assert registry.get_callable("add")(3, 4) == 7
