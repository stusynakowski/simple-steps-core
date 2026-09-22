"""
Serving
=======

Turn a plain Python script that just *declares tools* into a running HTTP API.

A user writes a script like::

    from simple_steps_core import register_tool
    from simple_steps_core.serving import Server

    @register_tool("add")
    def add(a: int, b: int) -> int:
        return a + b

    CONFIG = {"title": "My Tools", "port": 8000}   # optional

    if __name__ == "__main__":
        Server().run()

and runs it with ``python myscript.py``. Importing this file registers its tools
on ``REGISTRY``; ``Server().run()`` adds the built-in orchestrators and serves
three endpoints: ``GET /tools``, ``POST /call``, and ``POST /run``.
FastAPI/uvicorn are optional — install the ``api`` extra (``pip install
"simple-steps-core[api]"``).
"""

from __future__ import annotations

import sys
import types
from typing import Any

from pydantic import BaseModel, Field

from .domain.models import Operation, ToolCall
from .execution.engine import CoreEngine
from .execution.workflow import Workflow
from .operations.orchestrations import register_orchestrators
from .operations.registry import REGISTRY, ToolRegistry
from .operations.resource_spec import install_resources
from .operations.validation import ValidationError, validate_tool_call


# ── request models (module scope so FastAPI resolves them) ───────────────
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


def _step_out(step) -> dict:
    return {
        "step_id": step.step_id,
        "status": step.status.value,
        "value": _jsonable(step.output.value),
        "error": step.error,
    }


def build_app(
    registry: ToolRegistry,
    engine: CoreEngine,
    *,
    title: str = "simple-steps-core server",
    resources: Any = None,
):
    """Build a FastAPI app exposing *registry*'s tools.

    ``resources`` maps a resource name to a factory (callable) or an
    already-built instance; each is registered on every per-request session so
    tools that declare ``Resource()`` parameters can run.
    """
    from fastapi import FastAPI, HTTPException

    resources = resources or {}
    app = FastAPI(title=title, version="0.1.0")

    def _new_workflow(session_id: str) -> Workflow:
        wf = Workflow(engine, session_id=session_id)
        install_resources(wf.context.resources, resources)
        return wf

    @app.get("/tools")
    def list_tools() -> list[dict]:
        """The tool palette: id, description, params, JSON Schema."""
        return [d.model_dump() for d in registry.list_definitions()]

    @app.post("/call")
    def call_tool(body: CallIn) -> dict:
        """Run a single tool immediately and return its value."""
        call = ToolCall(operation_id=body.operation_id, arguments=body.arguments)
        try:
            validate_tool_call(call, registry)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        wf = _new_workflow("call")
        wf["result"] = call
        try:
            wf.run()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"value": _jsonable(wf["result"].output.value)}

    @app.post("/run")
    def run_workflow(body: RunIn) -> dict:
        """Run a workflow of steps; later steps reference earlier outputs."""
        wf = _new_workflow("run")
        for spec in body.steps:
            try:
                wf.add(spec)
            except (ValueError, TypeError) as exc:
                raise HTTPException(
                    status_code=422, detail=f"Invalid step {spec.step_id!r}: {exc}"
                ) from exc
        results: list[dict] = []
        for spec in body.steps:
            try:
                results.append(_step_out(wf.run_step(spec.step_id)))
            except Exception as exc:
                results.append(
                    {"step_id": spec.step_id, "status": "failed", "value": None, "error": str(exc)}
                )
                break
        return {"steps": results}

    return app


def app_from_module(module, *, registry: ToolRegistry = REGISTRY) -> tuple[Any, dict]:
    """Build the app + resolved server config from a loaded tools module."""
    config: dict[str, Any] = dict(getattr(module, "CONFIG", {}) or {})
    resources: Any = getattr(module, "RESOURCES", None) or {}

    if config.get("orchestrators", True) and not registry.has("map"):
        register_orchestrators(registry)
    if config.get("freeze", True) and not registry.frozen:
        registry.freeze()

    app = build_app(
        registry,
        CoreEngine(registry),
        title=config.get("title", "simple-steps-core server"),
        resources=resources,
    )
    return app, config


class Server:
    """Serve the tools registered in your own script as an HTTP API.

    Put this at the bottom of the same script that registers your tools::

        from simple_steps_core import register_tool
        from simple_steps_core.serving import Server

        @register_tool("add")
        def add(a: int, b: int) -> int:
            return a + b

        CONFIG = {"title": "My Tools", "port": 8000}   # optional
        RESOURCES = [my_resource]                       # optional: specs,
                                                        # or {name: factory}

        if __name__ == "__main__":
            Server().run()

    Then start it with ``python myscript.py``. Pass ``host=`` / ``port=`` to
    override the values from ``CONFIG``.
    """

    def __init__(self, *, host: str | None = None, port: int | None = None) -> None:
        self._host = host
        self._port = port

    def run(self) -> None:
        caller = sys._getframe(1).f_globals
        module = types.SimpleNamespace(
            CONFIG=dict(caller.get("CONFIG", {}) or {}),
            # Not coerced to a dict: RESOURCES may be a list of ResourceSpec.
            RESOURCES=caller.get("RESOURCES", None) or {},
        )
        app, config = app_from_module(module)

        host = self._host or config.get("host", "127.0.0.1")
        port = self._port or config.get("port", 8000)

        try:
            import uvicorn
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise SystemExit(
                "The server needs FastAPI + uvicorn. Install them with:\n"
                '    pip install "simple-steps-core[api]"'
            ) from exc

        uvicorn.run(app, host=host, port=port)
