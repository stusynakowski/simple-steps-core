from .types import AgentRequest, AgentResponse, Planner


class AgentService:
    """Thin adapter so app transport layers can call a planner uniformly."""

    def __init__(self, planner: Planner):
        self._planner = planner

    def invoke(self, request: AgentRequest) -> AgentResponse:
        return self._planner.plan(request)
