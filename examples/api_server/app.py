"""Runnable FastAPI server exposing simple-steps-core to a frontend.

Run it::

    python -m pip install -e ".[api]"
    uvicorn examples.api_server.app:app --reload

Then open http://127.0.0.1:8000/docs for interactive API docs, or point your
React app at the endpoints below.

Endpoints
---------
- ``GET  /operations``            — palette of registered operations for the UI.
- ``POST /workflows``             — validate + create a workflow from steps.
- ``POST /workflows/{id}/run``    — execute the workflow (async).
- ``GET  /workflows/{id}``        — status + per-step results.
- ``GET  /workflows/{id}/dag``    — nodes + edges derived from step references.

This mirrors ``docs/integration.md`` with working code. The store is in-memory;
swap it for a database in production.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from simple_steps_core import (
    SessionManager,
    ValidationError,
    Workflow,
    is_reference,
    make_session_id,
    parse_formula,
    split_reference,
    validate_tool_call,
)

from .operations import ENGINE, REGISTRY
from .store import STORE, WorkflowRecord

app = FastAPI(title="simple-steps-core example API", version="0.1.0")

# Allow a local React dev server to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# One SessionManager per process; serializes writes within a single session.
SESSIONS = SessionManager()


# ── request / response models ────────────────────────────────────────────
class StepIn(BaseModel):
    step_id: str = Field(..., examples=["step_nums"])
    formula: str = Field(..., examples=['=make_list(n=5)'])


class CreateWorkflowIn(BaseModel):
    user_id: str = Field(..., examples=["alice"])
    workflow_id: str = Field(..., examples=["wf-001"])
    steps: list[StepIn]


class StepOut(BaseModel):
    step_id: str
    formula: str
    status: str
    value: Any = None
    error: str | None = None


class WorkflowOut(BaseModel):
    workflow_id: str
    status: str
    steps: list[StepOut]


# ── helpers ──────────────────────────────────────────────────────────────
def _validate_steps(steps: list[StepIn]) -> None:
    """Reject malformed formulas / unknown ops before persisting."""
    for step in steps:
        try:
            call = parse_formula(step.formula)
            validate_tool_call(call, REGISTRY)
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid step {step.step_id!r}: {exc}",
            ) from exc


def _build_workflow(session_id: str, steps: list[StepIn]) -> Workflow:
    wf = Workflow(ENGINE, session_id=session_id)
    for step in steps:
        wf[step.step_id] = step.formula
    return wf


def _workflow_out(workflow_id: str, status: str, wf: Workflow) -> WorkflowOut:
    return WorkflowOut(
        workflow_id=workflow_id,
        status=status,
        steps=[
            StepOut(
                step_id=s.step_id,
                formula=s.formula,
                status=s.status.value,
                value=_jsonable(s.output.value),
                error=s.error,
            )
            for s in wf.steps
        ],
    )


def _jsonable(value: Any) -> Any:
    """Best-effort conversion of a payload to something JSON-serializable."""
    if value is None or isinstance(value, (bool, int, float, str, list, dict)):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if hasattr(value, "model_dump"):  # pydantic-like
        return value.model_dump()
    return repr(value)


# ── endpoints ────────────────────────────────────────────────────────────
@app.get("/operations")
def list_operations() -> list[dict]:
    """Return the operation palette for the frontend."""
    return [d.model_dump() for d in REGISTRY.list_definitions()]


@app.post("/workflows", response_model=WorkflowOut)
def create_workflow(payload: CreateWorkflowIn) -> WorkflowOut:
    """Validate and persist a workflow built from user-supplied steps."""
    _validate_steps(payload.steps)

    session_id = make_session_id(payload.user_id, payload.workflow_id, "run")
    wf = _build_workflow(session_id, payload.steps)

    STORE.save(
        WorkflowRecord(
            workflow_id=payload.workflow_id,
            user_id=payload.user_id,
            snapshot_json=wf.export_session_json(),
            status="created",
        )
    )
    return _workflow_out(payload.workflow_id, "created", wf)


@app.post("/workflows/{workflow_id}/run", response_model=WorkflowOut)
async def run_workflow(workflow_id: str) -> WorkflowOut:
    """Execute a stored workflow asynchronously and persist the new snapshot."""
    record = STORE.load(workflow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown workflow")

    wf = Workflow.import_session_json(record.snapshot_json, ENGINE)
    session_id = wf.context.session_id
    await SESSIONS.get_or_create(session_id)

    STORE.set_status(workflow_id, "running")
    try:
        async with SESSIONS.lock(session_id):
            await wf.arun()
        status = "completed"
    except Exception:
        status = "failed"
    finally:
        STORE.update_snapshot(workflow_id, wf.export_session_json())
        STORE.set_status(workflow_id, status)

    return _workflow_out(workflow_id, status, wf)


@app.get("/workflows/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: str) -> WorkflowOut:
    """Return current status and per-step results."""
    record = STORE.load(workflow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown workflow")
    wf = Workflow.import_session_json(record.snapshot_json, ENGINE)
    return _workflow_out(workflow_id, record.status, wf)


@app.get("/workflows/{workflow_id}/dag")
def get_workflow_dag(workflow_id: str) -> dict:
    """Derive a DAG (nodes + edges) from step formulas for graph rendering."""
    record = STORE.load(workflow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown workflow")

    wf = Workflow.import_session_json(record.snapshot_json, ENGINE)
    nodes: list[dict] = []
    edges: list[dict] = []
    step_ids = {s.step_id for s in wf.steps}

    for step in wf.steps:
        nodes.append({"id": step.step_id, "status": step.status.value})
        call = parse_formula(step.formula)
        for value in call.arguments.values():
            if is_reference(value):
                source, _field = split_reference(value)
                if source in step_ids:
                    edges.append({"from": source, "to": step.step_id})

    return {"nodes": nodes, "edges": edges}
