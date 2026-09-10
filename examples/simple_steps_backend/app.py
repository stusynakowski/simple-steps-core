"""Reference backend for the ``simple-steps`` app.

``create_app(registry, engine, ...)`` returns a FastAPI app that exposes
simple-steps-core to a React frontend and a (LangGraph) agent:

    GET  /operations                       — tool palette (id, params, JSON Schema)
    POST /workflows                        — create from a list of Operation
    GET  /workflows/{id}                   — status + per-step results
    POST /workflows/{id}/run               — run all steps (async)
    POST /workflows/{id}/steps/{sid}/run   — run one step
    GET  /workflows/{id}/dag               — nodes + edges for graph rendering
    POST /agent/propose                    — agent proposes/edits a step list

Copy this into the ``simple-steps`` repo and register your own operations. The
store is in-memory; swap it for a database.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from simple_steps_core import (
    CoreEngine,
    SessionManager,
    Operation,
    ToolRegistry,
    ValidationError,
    Workflow,
    check_reference_types,
    is_reference,
    split_reference,
)

from .agent import Planner, validate_step, validate_steps
from .store import WorkflowRecord, WorkflowStore


# ── request / response models (module scope for FastAPI) ─────────────────
class CreateWorkflowIn(BaseModel):
    workflow_id: str = Field(..., examples=["wf-001"])
    steps: list[Operation]


class StepView(BaseModel):
    step_id: str
    name: str
    mode: str
    stage: int | str | None = None
    status: str
    value: Any = None
    error: str | None = None


class WorkflowOut(BaseModel):
    workflow_id: str
    status: str
    steps: list[StepView]
    reference_issues: list[dict] = Field(default_factory=list)


class ProposeIn(BaseModel):
    goal: str = Field(..., examples=["load EMEA orders and total them by category"])
    workflow: list[Operation] = Field(default_factory=list)


class ProposeOut(BaseModel):
    steps: list[Operation]
    invalid: list[dict] = Field(default_factory=list)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str, list, dict)):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return repr(value)


def _step_view(step) -> StepView:
    spec = step.spec
    return StepView(
        step_id=step.step_id,
        name=spec.name if spec else step.call.operation_id,
        mode=spec.orchestration.mode if spec else "single",
        stage=spec.stage if spec else None,
        status=step.status.value,
        value=_jsonable(step.output.value),
        error=step.error,
    )


def _step_refs(spec: Operation) -> list[str]:
    refs = [v for v in spec.arguments.values() if is_reference(v)]
    if spec.orchestration.over and is_reference(spec.orchestration.over):
        refs.append(spec.orchestration.over)
    return refs


def _steps_needing_confirmation(wf: Workflow, registry: ToolRegistry) -> list[str]:
    """Step ids whose tool declares guardrails.requires_confirmation."""
    needs: list[str] = []
    for step in wf.steps:
        name = step.spec.name if step.spec else step.call.operation_id
        if not registry.has(name):
            continue
        guardrails = registry.get_definition(name).guardrails
        if guardrails is not None and guardrails.requires_confirmation:
            needs.append(step.step_id)
    return needs


def create_app(
    registry: ToolRegistry,
    engine: CoreEngine,
    *,
    store: WorkflowStore | None = None,
    planner: Planner | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    store = store or WorkflowStore()
    sessions = SessionManager()
    app = FastAPI(title="simple-steps backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:3000", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _build(workflow_id: str, steps: list[Operation]) -> Workflow:
        wf = Workflow(engine, session_id=workflow_id)
        for spec in steps:
            wf.add(spec)
        return wf

    async def _run_and_save(workflow_id: str, runner) -> Workflow:
        """Import the stored snapshot, run via *runner(wf)*, and re-save it."""
        record = store.load(workflow_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown workflow")
        wf = Workflow.import_session_json(record.snapshot_json, engine)
        await sessions.get_or_create(workflow_id)
        try:
            async with sessions.lock(workflow_id):
                await runner(wf)
        except Exception:
            pass  # per-step failures are recorded on the steps
        finally:
            store.update_snapshot(workflow_id, wf.export_session_json())
        return wf

    # ── palette ──────────────────────────────────────────────────────────
    @app.get("/operations")
    def list_operations() -> list[dict]:
        return [d.model_dump() for d in registry.list_definitions()]

    # ── workflow CRUD + run ──────────────────────────────────────────────
    @app.post("/workflows", response_model=WorkflowOut)
    def create_workflow(payload: CreateWorkflowIn) -> WorkflowOut:
        for spec in payload.steps:
            try:
                validate_step(spec, registry)
            except (ValidationError, ValueError) as exc:
                raise HTTPException(
                    status_code=422, detail=f"Invalid step {spec.step_id!r}: {exc}"
                ) from exc
        wf = _build(payload.workflow_id, payload.steps)
        store.save(
            WorkflowRecord(
                workflow_id=payload.workflow_id,
                snapshot_json=wf.export_session_json(),
                status="created",
            )
        )
        return WorkflowOut(
            workflow_id=payload.workflow_id, status="created",
            steps=[_step_view(s) for s in wf.steps],
            reference_issues=check_reference_types(wf, registry),
        )

    @app.get("/workflows/{workflow_id}", response_model=WorkflowOut)
    def get_workflow(workflow_id: str) -> WorkflowOut:
        record = store.load(workflow_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown workflow")
        wf = Workflow.import_session_json(record.snapshot_json, engine)
        return WorkflowOut(
            workflow_id=workflow_id, status=record.status,
            steps=[_step_view(s) for s in wf.steps],
        )

    @app.post("/workflows/{workflow_id}/run", response_model=WorkflowOut)
    async def run_workflow(workflow_id: str, confirm: bool = False) -> WorkflowOut:
        record = store.load(workflow_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown workflow")
        wf = Workflow.import_session_json(record.snapshot_json, engine)
        # Gate steps whose tool declares guardrails.requires_confirmation.
        needs = _steps_needing_confirmation(wf, registry)
        if needs and not confirm:
            raise HTTPException(
                status_code=409,
                detail={"error": "confirmation_required", "steps": needs,
                        "hint": "re-run with ?confirm=true"},
            )
        await sessions.get_or_create(workflow_id)
        store.set_status(workflow_id, "running")
        try:
            async with sessions.lock(workflow_id):
                await wf.arun()
            status = "completed"
        except Exception:
            status = "failed"
        finally:
            store.update_snapshot(workflow_id, wf.export_session_json())
            store.set_status(workflow_id, status)
        return WorkflowOut(
            workflow_id=workflow_id, status=status,
            steps=[_step_view(s) for s in wf.steps],
        )

    @app.post("/workflows/{workflow_id}/steps/{step_id}/run", response_model=WorkflowOut)
    async def run_step(workflow_id: str, step_id: str) -> WorkflowOut:
        record = store.load(workflow_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown workflow")
        if step_id not in Workflow.import_session_json(record.snapshot_json, engine):
            raise HTTPException(status_code=404, detail="Unknown step")
        wf = await _run_and_save(workflow_id, lambda w: w.arun_step(step_id))
        return WorkflowOut(
            workflow_id=workflow_id, status=store.load(workflow_id).status,
            steps=[_step_view(s) for s in wf.steps],
        )

    @app.post("/workflows/{workflow_id}/stages/{stage}/run", response_model=WorkflowOut)
    async def run_stage(workflow_id: str, stage: str) -> WorkflowOut:
        record = store.load(workflow_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown workflow")
        wf0 = Workflow.import_session_json(record.snapshot_json, engine)
        # Path params are strings; match against int or str stages by name.
        match = next((s for s in wf0.stages() if str(s) == stage), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Unknown stage {stage!r}")
        wf = await _run_and_save(workflow_id, lambda w: w.arun_stage(match))
        return WorkflowOut(
            workflow_id=workflow_id, status=store.load(workflow_id).status,
            steps=[_step_view(s) for s in wf.steps],
        )

    @app.get("/workflows/{workflow_id}/dag")
    def get_dag(workflow_id: str) -> dict:
        record = store.load(workflow_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown workflow")
        wf = Workflow.import_session_json(record.snapshot_json, engine)
        step_ids = {s.step_id for s in wf.steps}
        nodes, edges = [], []
        for step in wf.steps:
            nodes.append({"id": step.step_id, "status": step.status.value})
            if step.spec is None:
                continue
            for ref in _step_refs(step.spec):
                source, _ = split_reference(ref)
                if source in step_ids:
                    edges.append({"from": source, "to": step.step_id})
        return {"nodes": nodes, "edges": edges}

    # ── agent ────────────────────────────────────────────────────────────
    @app.post("/agent/propose", response_model=ProposeOut)
    def propose(payload: ProposeIn) -> ProposeOut:
        if planner is None:
            raise HTTPException(
                status_code=503,
                detail="No planner configured. Pass planner=... to create_app "
                "(see agent.build_langgraph_planner).",
            )
        proposed = planner.propose(payload.goal, payload.workflow)
        valid, invalid = validate_steps(proposed, registry)
        return ProposeOut(steps=valid, invalid=invalid)

    return app
