"""Basic smoke test script for simple-steps-core.

Run with:
	python runme.py

This script exercises a stable happy path:
1) register operations,
2) build and run a workflow step,
3) execute it,
4) validate outputs,
5) run an operation through the engine directly.
"""

from simple_steps_core import CoreEngine, OperationRegistry, StepStatus, ToolCall, Workflow


def main() -> int:
	registry = OperationRegistry()

	def make_list(n: int) -> list[int]:
		return list(range(n))

	def total(data: list[int]) -> int:
		return sum(data)

	registry.register("make_list", make_list, description="Create [0..n-1]")
	registry.register("total", total, description="Sum a list of ints")

	engine = CoreEngine(registry)
	workflow = Workflow(engine, session_id="runme")

	make_list_op = registry.get_operation("make_list")
	total_op = registry.get_operation("total")

	workflow["step1"] = make_list_op(n=5)

	steps = workflow.run()

	step1 = steps[0]
	assert step1.status is StepStatus.COMPLETED
	assert step1.output is not None and step1.output.value == [0, 1, 2, 3, 4]

	ref_id, total_value = engine.execute(
		ToolCall(operation_id="total", arguments={"data": step1.output.value}),
		workflow.context,
	)
	assert ref_id.startswith("runme__")
	assert total_value == 10

	print("runme smoke test passed")
	print(f"step1: {step1.output.value}")
	print(f"total: {total_value}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
