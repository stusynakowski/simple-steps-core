"""A reusable FastAPI factory that turns a registry of tools into an API.

``build_app(registry, engine)`` exposes three endpoints:

- ``GET  /tools``  — the palette (each tool's id, description, and JSON Schema).
- ``POST /call``   — run one tool immediately: ``{operation_id, arguments}``.
- ``POST /run``    — run a workflow of :class:`Operation` steps, wiring outputs
                     between steps and orchestrating (map/filter/...) inline.

The session (data store, references) is created and managed per request, so the
caller only thinks in terms of tools and steps.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from simple_steps_core import (
    CoreEngine,
    ToolRegistry,
    Operation,
    ToolCall,
    ValidationError,
    Workflow,
    make_session_id,
    validate_tool_call,
)


class CallIn(BaseModel):
    operation_id: str = Field(..., examples=["add"])
    arguments: dict[str, Any] = Field(default_factory=dict, examples=[{"a": 2, "b": 3}])


class RunIn(BaseModel):
    steps: list[Operation]


def _jsonable(value: Any) -> Any:
    """Best-effort conversion of a payload to something JSON-serializable."""
    if value is None or isinstance(value, (bool, int, float, str, list, dict)):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return repr(value)


def build_app(
    registry: ToolRegistry,
    engine: CoreEngine,
    *,
    title: str = "simple_steps server",
) -> FastAPI:
    app = FastAPI(title=title, version="0.1.0")

    @app.get("/tools")
    def list_tools() -> list[dict]:
        """The tool palette: id, description, params, and JSON Schema."""
        return [d.model_dump() for d in registry.list_definitions()]

    @app.post("/call")
    def call_tool(body: CallIn) -> dict:
        """Run a single tool immediately and return its value."""
        call = ToolCall(operation_id=body.operation_id, arguments=body.arguments)
        try:
            validate_tool_call(call, registry)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        wf = Workflow(engine, session_id="call")
        wf["result"] = call
        try:
            wf.run()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"value": _jsonable(wf["result"].output.value)}

    @app.post("/run")
    def run_workflow(body: RunIn) -> dict:
        """Run a workflow of steps; later steps reference earlier outputs."""
        wf = Workflow(engine, session_id=make_session_id("server", "wf", "run"))
        for spec in body.steps:
            try:
                wf.add(spec)  # compiles the Operation (validates orchestration)
            except (ValueError, TypeError) as exc:
                raise HTTPException(
                    status_code=422, detail=f"Invalid step {spec.step_id!r}: {exc}"
                ) from exc

        results: list[dict] = []
        for spec in body.steps:
            try:
                step = wf.run_step(spec.step_id)
            except Exception as exc:
                results.append(
                    {"step_id": spec.step_id, "status": "failed", "value": None, "error": str(exc)}
                )
                break
            results.append(
                {
                    "step_id": step.step_id,
                    "status": step.status.value,
                    "value": _jsonable(step.output.value),
                    "error": None,
                }
            )
        return {"steps": results}

    return app
