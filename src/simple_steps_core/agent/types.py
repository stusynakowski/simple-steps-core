from dataclasses import dataclass, field
from typing import Protocol

from ..domain.models import ToolCall


@dataclass(frozen=True)
class AgentRequest:
    message: str
    workflow_steps: list[dict] = field(default_factory=list)
    available_operations: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class AgentResponse:
    message: str
    suggested_tool_call: ToolCall | None = None


class Planner(Protocol):
    def plan(self, request: AgentRequest) -> AgentResponse: ...
