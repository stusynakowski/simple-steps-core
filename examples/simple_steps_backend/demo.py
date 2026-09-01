"""Runnable demo wiring for the reference backend.

Registers a few sample tools and a deterministic stub planner (so the
``/agent/propose`` endpoint works without an LLM), then builds the app::

    python -m pip install -e ".[api]"
    uvicorn examples.simple_steps_backend.demo:app --reload

Replace the tools with your own, and swap ``StubPlanner`` for
``build_langgraph_planner(registry)`` once an LLM is configured.
"""

from __future__ import annotations

from simple_steps_core import (
    CoreEngine,
    StepSpec,
    ToolRegistry,
    register_orchestrators,
)

from .agent import Planner
from .app import create_app

registry = ToolRegistry()


def make_list(n: int) -> list[int]:
    """Create the list [0, 1, ..., n-1]."""
    return list(range(n))


def square(x: int) -> int:
    """Square a number."""
    return x * x


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


registry.register("make_list", make_list, description="Create [0..n-1].")
registry.register("square", square, description="Square a number.")
registry.register("add", add, description="Add two numbers.")
register_orchestrators(registry)
registry.freeze()


class StubPlanner:
    """A deterministic stand-in for a real LangGraph/LLM planner.

    It ignores the goal and returns a fixed 3-step plan, purely so the endpoint
    is runnable and testable out of the box. Replace with an LLM planner.
    """

    def propose(self, goal: str, current: list[StepSpec]) -> list[StepSpec]:
        return [
            StepSpec(step_id="step_nums", name="make_list", arguments={"n": 5}),
            StepSpec(
                step_id="step_sq", name="square",
                orchestration={"mode": "map", "over": "step_nums"},
            ),
        ]


PLANNER: Planner = StubPlanner()
app = create_app(registry, CoreEngine(registry), planner=PLANNER)
