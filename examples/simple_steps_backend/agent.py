"""Agent planning for the simple-steps app.

The agent's job is to turn a natural-language goal (plus the current workflow)
into a **validated list of Operation** the user can review, edit, and run. This
module defines:

- ``Planner`` — the protocol the backend depends on.
- ``validate_steps`` — compile + validate proposed steps against the registry,
  splitting valid steps from invalid ones (so the UI can flag problems).
- ``build_langgraph_planner`` — a reference LangGraph/LLM planner (adapt in the
  ``simple-steps`` app; imported lazily so this file has no hard agent deps).

The backend stays framework-agnostic: it depends only on ``Planner``. Wire a
real LangGraph agent in your app, or inject a stub in tests.
"""

from __future__ import annotations

from typing import Protocol

from simple_steps_core import (
    Operation,
    ToolRegistry,
    ValidationError,
    validate_tool_call,
)


class Planner(Protocol):
    """Proposes/modifies a list of steps for a goal and current workflow."""

    def propose(self, goal: str, current: list[Operation]) -> list[Operation]: ...


def validate_step(spec: Operation, registry: ToolRegistry) -> None:
    """Raise ValidationError/ValueError if *spec* is not runnable as-is."""
    if not registry.has(spec.name):
        raise ValidationError(f"Unknown operation: {spec.name!r}")
    validate_tool_call(spec.to_tool_call(), registry)   # to_tool_call may raise ValueError


def validate_steps(
    steps: list[Operation], registry: ToolRegistry
) -> tuple[list[Operation], list[dict]]:
    """Split *steps* into (valid, invalid). Invalid items carry a reason."""
    valid: list[Operation] = []
    invalid: list[dict] = []
    for spec in steps:
        try:
            validate_step(spec, registry)
        except (ValidationError, ValueError) as exc:
            invalid.append({"step_id": spec.step_id, "reason": str(exc)})
        else:
            valid.append(spec)
    return valid, invalid


# ─────────────────────────────────────────────────────────────────────────
# Reference LangGraph / LLM planner (adapt this in the simple-steps app).
# Lazily imports langchain/langgraph so importing this module never requires
# them. Configure an LLM (e.g. OPENAI_API_KEY) to use it.
# ─────────────────────────────────────────────────────────────────────────
def build_langgraph_planner(registry: ToolRegistry, *, model: str = "openai:gpt-4o-mini") -> Planner:
    """Build an LLM planner that emits a validated ``list[Operation]``.

    Uses structured output (the LLM must return objects matching ``Operation``),
    grounded on the operation palette + JSON Schemas. Wrap this as a LangGraph
    node in your app if you want memory / multi-turn planning.
    """
    from langchain.chat_models import init_chat_model  # requires langchain + provider
    from pydantic import BaseModel, Field

    class Proposal(BaseModel):
        steps: list[Operation] = Field(default_factory=list)
        notes: str = ""

    palette = _palette_prompt(registry)
    llm = init_chat_model(model).with_structured_output(Proposal)

    class _LangGraphPlanner:
        def propose(self, goal: str, current: list[Operation]) -> list[Operation]:
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT + "\n\n" + palette},
                {"role": "user", "content": _user_prompt(goal, current)},
            ]
            proposal: Proposal = llm.invoke(messages)
            return proposal.steps

    return _LangGraphPlanner()


_SYSTEM_PROMPT = (
    "You help users build data workflows as a list of steps. Each step names one "
    "tool from the palette and supplies its arguments. To use the output of an "
    "earlier step as an argument, pass that step's id as a string (ids must start "
    "with 'step'). To apply a tool across a collection, set orchestration.mode to "
    "map/filter/expand/collapse and orchestration.over to the collection's step id. "
    "Only use tools from the palette; only supply arguments listed in a tool's schema."
)


def _palette_prompt(registry: ToolRegistry) -> str:
    lines = ["AVAILABLE TOOLS:"]
    for d in registry.list_definitions():
        required = [p.name for p in d.params if p.required and p.kind == "data"]
        optional = [p.name for p in d.params if not p.required and p.kind == "data"]
        lines.append(
            f"- {d.operation_id}: {d.description or '(no description)'} "
            f"| required={required} optional={optional}"
        )
    return "\n".join(lines)


def _user_prompt(goal: str, current: list[Operation]) -> str:
    if current:
        existing = ", ".join(s.step_id for s in current)
        return f"Current steps: {existing}\nGoal: {goal}\nReturn the full updated step list."
    return f"Goal: {goal}\nReturn the steps to accomplish it."
