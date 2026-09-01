"""
Serving
=======

Turn a plain Python script that just *declares tools* into a running HTTP API.

A user writes a script like::

    from simple_steps_core import register_tool

    @register_tool("add")
    def add(a: int, b: int) -> int:
        return a + b

    CONFIG = {"title": "My Tools", "port": 8000}   # optional

and runs it with the console script::

    simple-steps-core-server myscript.py

The CLI imports the script (which registers its tools on ``REGISTRY``), adds the
built-in orchestrators, and serves three endpoints: ``GET /tools``, ``POST
/call``, and ``POST /run``. FastAPI/uvicorn are optional — install the ``api``
extra (``pip install "simple-steps-core[api]"``).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .domain.models import StepSpec, ToolCall
from .execution.engine import CoreEngine
from .execution.workflow import Workflow
from .operations.orchestrations import register_orchestrators
from .operations.registry import REGISTRY, OperationRegistry
from .operations.validation import ValidationError, validate_tool_call


# ── request models (module scope so FastAPI resolves them) ───────────────
class CallIn(BaseModel):
    operation_id: str = Field(..., examples=["add"])
    arguments: dict[str, Any] = Field(default_factory=dict, examples=[{"a": 2, "b": 3}])


class RunIn(BaseModel):
    steps: list[StepSpec]


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
    registry: OperationRegistry,
    engine: CoreEngine,
    *,
    title: str = "simple-steps-core server",
    resources: dict[str, Any] | None = None,
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
        for name, provider in resources.items():
            if callable(provider):
                wf.context.resources.register(name, provider)
            else:
                wf.context.resources.register_value(name, provider)
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


def load_tools_module(path: str | Path):
    """Import a user script by path, running its ``@register_operation`` calls."""
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"No such script: {path}")
    spec = importlib.util.spec_from_file_location("_simple_steps_user_tools", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # Let the script import sibling modules relative to its own folder.
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    return module


def app_from_module(module, *, registry: OperationRegistry = REGISTRY) -> tuple[Any, dict]:
    """Build the app + resolved server config from a loaded tools module."""
    config: dict[str, Any] = dict(getattr(module, "CONFIG", {}) or {})
    resources: dict[str, Any] = dict(getattr(module, "RESOURCES", {}) or {})

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


def main(argv: list[str] | None = None) -> None:
    """Console-script entry point: ``simple-steps-core-server SCRIPT``."""
    parser = argparse.ArgumentParser(
        prog="simple-steps-core-server",
        description="Serve the tools declared in a Python script as an HTTP API.",
    )
    parser.add_argument("script", help="Path to a Python script that declares tools.")
    parser.add_argument("--host", default=None, help="Bind host (default 127.0.0.1).")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default 8000).")
    args = parser.parse_args(argv)

    module = load_tools_module(args.script)
    app, config = app_from_module(module)

    host = args.host or config.get("host", "127.0.0.1")
    port = args.port or config.get("port", 8000)

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SystemExit(
            "The server needs FastAPI + uvicorn. Install them with:\n"
            '    pip install "simple-steps-core[api]"'
        ) from exc

    uvicorn.run(app, host=host, port=port)
