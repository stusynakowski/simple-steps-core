"""
Workflow
========

A :class:`Workflow` is an ordered collection of steps plus the machinery to
run them against a :class:`SessionContext`. It is the main user-facing object
in the execution layer and supports an ergonomic, spreadsheet-like API::

    wf = Workflow(engine)
    wf["step1"] = load_csv(filepath="a.csv")     # assign a ToolCall
    wf["step2"] = filter_rows(data="step1")       # reference an earlier step
    wf.run()                                       # execute in order

Assignment accepts either a :class:`ToolCall` (from deferred operation calls)
or a formula string (``"=load_csv(filepath='a.csv')"``), which is parsed into
a ToolCall. Running a step records its status, output reference, and any error
back onto the :class:`Step` record, and binds the produced payload to the
step id in the session so later steps can reference it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain.formulas import parse_formula, render_formula
from ..domain.models import Step, StepOutput, StepStatus, ToolCall
from .context import SessionContext
from .engine import CoreEngine

if TYPE_CHECKING:
    from .session_io import CodecRegistry, SessionSnapshot


class Workflow:
    def __init__(self, engine: CoreEngine, session_id: str = "default"):
        self.engine = engine
        self.context = SessionContext(session_id=session_id)
        # Insertion order is the execution order; dict preserves it.
        self._steps: dict[str, Step] = {}

    # ── dict-like authoring API ──────────────────────────────────────────
    def __setitem__(self, step_id: str, value: ToolCall | str) -> None:
        """Add or replace a step from a ToolCall or a formula string."""
        formula = self._to_formula(value)
        self._steps[step_id] = Step(step_id=step_id, formula=formula)

    def __getitem__(self, step_id: str) -> Step:
        return self._steps[step_id]

    def __contains__(self, step_id: str) -> bool:
        return step_id in self._steps

    def __len__(self) -> int:
        return len(self._steps)

    @property
    def steps(self) -> list[Step]:
        """Steps in execution (insertion) order."""
        return list(self._steps.values())

    # ── execution ────────────────────────────────────────────────────────
    def run_step(self, step_id: str) -> Step:
        """Execute a single step and record its outcome on the Step record."""
        step = self._steps[step_id]
        tool_call = parse_formula(step.formula)

        step.status = StepStatus.RUNNING
        try:
            ref_id, value = self.engine.execute(tool_call, self.context)
        except Exception as exc:
            # Capture the failure on the step rather than raising blindly, so
            # callers can inspect partial workflow state after a failure.
            step.status = StepStatus.FAILED
            step.error = str(exc)
            raise

        # Success: bind the payload to this step id and record the output.
        self.context.bind_step(step_id, ref_id)
        step.output = StepOutput(ref=ref_id, value=value, kind=type(value).__name__)
        step.status = StepStatus.COMPLETED
        step.error = None
        return step

    def run(self) -> list[Step]:
        """Execute every step in order and return the updated records."""
        for step_id in list(self._steps):
            self.run_step(step_id)
        return self.steps

    # ── async execution ──────────────────────────────────────────────────
    async def arun_step(self, step_id: str) -> Step:
        """Async counterpart of :meth:`run_step` (awaits the engine)."""
        step = self._steps[step_id]
        tool_call = parse_formula(step.formula)

        step.status = StepStatus.RUNNING
        try:
            ref_id, value = await self.engine.aexecute(tool_call, self.context)
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.error = str(exc)
            raise

        self.context.bind_step(step_id, ref_id)
        step.output = StepOutput(ref=ref_id, value=value, kind=type(value).__name__)
        step.status = StepStatus.COMPLETED
        step.error = None
        return step

    async def arun(self) -> list[Step]:
        """Execute every step in order on the event loop and return records.

        Steps run sequentially because later steps may reference earlier
        outputs; per-item concurrency happens *inside* orchestrator steps.
        """
        for step_id in list(self._steps):
            await self.arun_step(step_id)
        return self.steps

    # ── persistence ──────────────────────────────────────────────────────
    def to_json(self) -> str:
        """Serialize the workflow's steps to JSON (payloads excluded)."""
        from pydantic import TypeAdapter

        adapter = TypeAdapter(list[Step])
        return adapter.dump_json(self.steps).decode()

    @classmethod
    def from_json(cls, data: str, engine: CoreEngine, session_id: str = "default") -> "Workflow":
        """Rebuild a workflow's steps from JSON (no payloads restored)."""
        from pydantic import TypeAdapter

        workflow = cls(engine, session_id=session_id)
        adapter = TypeAdapter(list[Step])
        for step in adapter.validate_json(data):
            workflow._steps[step.step_id] = step
        return workflow

    # ── full-session persistence (structure + payloads) ──────────────────
    def export_session(self, codecs: "CodecRegistry | None" = None) -> "SessionSnapshot":
        """Capture steps *and* the session's payloads as one snapshot."""
        from .session_io import DEFAULT_CODECS, build_snapshot

        return build_snapshot(
            session_id=self.context.session_id,
            steps=self.steps,
            outputs=self.context.outputs,
            step_to_ref=self.context.step_to_ref,
            codecs=codecs or DEFAULT_CODECS,
        )

    def export_session_json(self, codecs: "CodecRegistry | None" = None) -> str:
        """Convenience: :meth:`export_session` serialized to a JSON string."""
        return self.export_session(codecs).to_json()

    @classmethod
    def import_session(
        cls,
        snapshot: "SessionSnapshot",
        engine: CoreEngine,
        codecs: "CodecRegistry | None" = None,
    ) -> "Workflow":
        """Rebuild a workflow *and* its session payloads from a snapshot."""
        from .session_io import DEFAULT_CODECS, restore_payloads

        workflow = cls(engine, session_id=snapshot.session_id)
        for step in snapshot.steps:
            workflow._steps[step.step_id] = step.model_copy(deep=True)

        outputs = restore_payloads(snapshot, codecs or DEFAULT_CODECS)
        workflow.context.outputs.update(outputs)
        workflow.context.step_to_ref.update(snapshot.step_to_ref)

        # Re-attach inline values so completed steps expose their data again.
        for step in workflow._steps.values():
            ref = step.output.ref
            if ref is not None and ref in outputs:
                step.output = step.output.model_copy(update={"value": outputs[ref]})
        return workflow

    @classmethod
    def import_session_json(
        cls,
        data: str,
        engine: CoreEngine,
        codecs: "CodecRegistry | None" = None,
    ) -> "Workflow":
        """Convenience: :meth:`import_session` from a JSON string."""
        from .session_io import SessionSnapshot

        return cls.import_session(SessionSnapshot.from_json(data), engine, codecs)

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _to_formula(value: ToolCall | str) -> str:
        """Normalize an assigned value to a canonical formula string."""
        if isinstance(value, ToolCall):
            return render_formula(value)
        if isinstance(value, str):
            # Validate/normalize by round-tripping through the parser.
            return render_formula(parse_formula(value))
        raise TypeError(
            "Workflow steps must be assigned a ToolCall or a formula string, "
            f"got {type(value).__name__}"
        )
