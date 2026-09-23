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

Assignment takes a :class:`ToolCall` (produced by a deferred operation call).
Running a step records its status, output reference, and any error back onto
the :class:`Step` record, and binds the produced payload to the step id in the
session so later steps can reference it.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..domain.models import (
    Operation,
    StageExecutionConfig,
    Step,
    StepOutput,
    StepStatus,
    ToolCall,
    WorkflowExecutionConfig,
)
from ..inspect import SummaryTable
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
        # Per-stage config, keyed by stage tag (membership lives on the Step).
        self.stage_config: dict[int | str | None, StageExecutionConfig] = {}
        # How this workflow's stages run (isolated to the workflow scope).
        self.execution = WorkflowExecutionConfig()

    # ── dict-like authoring API ──────────────────────────────────────────
    def __setitem__(self, step_id: str, value: ToolCall | Operation) -> None:
        """Add or replace a step from a ToolCall or a Operation.

        A :class:`Operation` is compiled to its executable ToolCall and retained
        on the step so the orchestration/execution intent stays inspectable.
        """
        if isinstance(value, Operation):
            self._steps[step_id] = Step(
                step_id=step_id, call=value.to_tool_call(), spec=value
            )
        elif isinstance(value, ToolCall):
            self._steps[step_id] = Step(step_id=step_id, call=value)
        else:
            raise TypeError(
                "Workflow steps must be assigned a ToolCall or a Operation, "
                f"got {type(value).__name__}"
            )

    def add(self, spec: Operation) -> None:
        """Add a step from a Operation, keyed by its own ``step_id``."""
        self[spec.step_id] = spec

    def __getitem__(self, step_id: str) -> Step:
        return self._steps[step_id]

    def __delitem__(self, step_id: str) -> None:
        del self._steps[step_id]

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
        tool_call = step.call

        started = time.time()
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
        step.output = StepOutput(
            ref=ref_id, value=value, kind=type(value).__name__,
            started_at=started, ended_at=time.time(),
        )
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
        tool_call = step.call

        started = time.time()
        step.status = StepStatus.RUNNING
        try:
            ref_id, value = await self.engine.aexecute(tool_call, self.context)
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.error = str(exc)
            raise

        self.context.bind_step(step_id, ref_id)
        step.output = StepOutput(
            ref=ref_id, value=value, kind=type(value).__name__,
            started_at=started, ended_at=time.time(),
        )
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

    # ── stages ──────────────────────────────────────────────────────
    # A step's stage comes from its Operation; steps assigned as a raw ToolCall
    # (no spec) are ungrouped (stage ``None``).
    @staticmethod
    def _stage_of(step: Step) -> int | str | None:
        return step.spec.stage if step.spec is not None else None

    def stages(self) -> list[int | str | None]:
        """Distinct stages in first-appearance (execution) order."""
        ordered: list[int | str | None] = []
        for step in self._steps.values():
            stage = self._stage_of(step)
            if stage not in ordered:
                ordered.append(stage)
        return ordered

    def steps_in_stage(self, stage: int | str | None) -> list[Step]:
        """Steps belonging to *stage*, in insertion order."""
        return [s for s in self._steps.values() if self._stage_of(s) == stage]

    def run_stage(self, stage: int | str | None) -> list[Step]:
        """Run every step in *stage* (in order) and return those steps."""
        return [self.run_step(s.step_id) for s in self.steps_in_stage(stage)]

    def run_by_stages(self) -> list[Step]:
        """Run the whole workflow one stage at a time, in stage order."""
        for stage in self.stages():
            self.run_stage(stage)
        return self.steps

    async def arun_stage(self, stage: int | str | None) -> list[Step]:
        """Async counterpart of :meth:`run_stage`."""
        ran: list[Step] = []
        for step in self.steps_in_stage(stage):
            ran.append(await self.arun_step(step.step_id))
        return ran

    async def arun_by_stages(self) -> list[Step]:
        """Async counterpart of :meth:`run_by_stages`."""
        for stage in self.stages():
            await self.arun_stage(stage)
        return self.steps

    # ── stages as views ──────────────────────────────────────────────────
    def stage(self, stage_id: int | str | None) -> "Stage":
        """Return a computed :class:`Stage` view over steps tagged *stage_id*."""
        return Stage(self, stage_id)

    def stage_views(self) -> list["Stage"]:
        """A :class:`Stage` view per distinct stage, in first-appearance order."""
        return [Stage(self, s) for s in self.stages()]

    # ── validation / preflight ───────────────────────────────────────────
    def _tool_of(self, step: Step) -> str:
        return step.spec.name if step.spec is not None else step.call.operation_id

    def missing_resources(self) -> list[str]:
        """Resource names required by this workflow's tools but not registered."""
        needed: set[str] = set()
        for step in self._steps.values():
            try:
                definition = self.engine.registry.get_definition(self._tool_of(step))
            except KeyError:
                continue
            needed.update(definition.dependencies)
        return sorted(n for n in needed if not self.context.resources.has(n))

    def validate(self) -> SummaryTable:
        """Dry-run checks (no execution): tools exist, references resolve in
        order, no argument *looks* like a mistyped reference, and required
        resources are registered. Empty issues means it's OK."""
        from ..domain.references import is_reference, split_reference

        table = SummaryTable("Workflow validation", columns=["step", "check", "detail"])
        seen: list[str] = []
        all_ids = list(self._steps)
        for step in self._steps.values():
            sid = step.step_id
            tool_id = self._tool_of(step)
            if not self.engine.registry.has(tool_id):
                table.add_row(sid, "\u2717 unknown tool", tool_id)
            for value in step.call.arguments.values():
                if not isinstance(value, str):
                    continue
                if is_reference(value):
                    ref_step, _ = split_reference(value)
                    if ref_step not in seen:
                        table.add_row(sid, "\u2717 bad reference",
                                      f"{value!r} not produced by an earlier step")
                    continue
                # Not reference-shaped, so it is a literal — but a literal that
                # names or nearly names a step is almost always a typo that
                # lost the "step" prefix, and it fails silently as a string.
                suspicion = _suspicious_literal(value, all_ids)
                if suspicion is not None:
                    table.add_row(sid, "! suspicious literal", suspicion)
            seen.append(sid)
        for name in self.missing_resources():
            table.add_row("-", "\u2717 missing resource", name)
        if not table.rows:
            table.add_row("all", "\u2713 ok", "tools, references and resources check out")
        return table

    # ── inspection ───────────────────────────────────────────────────────
    def _status_counts(self, steps: list[Step]) -> str:
        from collections import Counter

        counts = Counter(s.status.value for s in steps)
        return ", ".join(f"{n} {name}" for name, n in counts.items()) or "empty"

    def preview(self, step_id: str, limit: int = 5) -> SummaryTable:
        """A small, payload-free preview of a step's current output."""
        step = self._steps[step_id]
        table = SummaryTable(f"Preview \u00b7 {step_id}", columns=["field", "value"])
        table.add_row("status", step.status.value)
        table.add_row("kind", step.output.kind or "-")
        ref = step.output.ref
        if ref is not None and self.context.has(ref):
            shape = self.context.get_meta(ref)
            table.add_row("shape", f"{shape.kind} rows={shape.rows}")
        sample = repr(step.output.value)
        if len(sample) > 80:
            sample = sample[:77] + "..."
        table.add_row("sample", sample)
        return table

    def info(self) -> SummaryTable:
        """Spreadsheet-style overview: one row per step (operation + data)."""
        table = SummaryTable(
            f"Workflow \u00b7 {self.context.session_id}",
            caption=self._status_counts(self.steps),
            columns=["step", "tool", "mode", "stage", "status", "duration"],
        )
        for step in self._steps.values():
            mode = step.spec.orchestration.mode if step.spec else "single"
            stage = self._stage_of(step)
            dur = step.output.duration
            table.add_row(
                step.step_id, self._tool_of(step), mode,
                "-" if stage is None else str(stage),
                step.status.value,
                "" if dur is None else f"{dur:.3f}s",
            )
        return table

    def __repr__(self) -> str:
        return (f"<Workflow {self.context.session_id!r} \u00b7 {len(self._steps)} steps \u00b7 "
                f"{self._status_counts(self.steps)}>")

    # ── persistence ──────────────────────────────────────────────────────
    def recipe(self) -> list[Step]:
        """The steps as a runnable *definition*: no results, nothing computed.

        Each step keeps what it needs to run again — its id, its compiled
        :class:`ToolCall`, and its :class:`Operation` spec (stage,
        orchestration and execution config) — and is handed back at
        ``pending`` with an empty output.

        This is the difference between sharing a workflow and sharing its data.
        ``Step`` embeds ``output.value`` inline, so dumping the live steps ships
        every computed value with the definition. Use :meth:`export_session`
        when you *do* want the data to travel.
        """
        return [
            step.model_copy(
                deep=True,
                update={"status": StepStatus.PENDING,
                        "output": StepOutput(),
                        "error": None},
            )
            for step in self.steps
        ]

    def to_json(self) -> str:
        """Serialize the workflow's definition to JSON (no computed values).

        Round-trips through :meth:`from_json`. For structure *and* payloads,
        use :meth:`export_session_json` / :meth:`import_session_json`.
        """
        from pydantic import TypeAdapter

        adapter = TypeAdapter(list[Step])
        return adapter.dump_json(self.recipe()).decode()

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


class Stage:
    """A computed groupby view over a Workflow's steps sharing a ``stage`` tag.

    The Workflow owns the Steps; a Stage owns nothing — it just references the
    steps whose tag matches and carries the phase's config.
    """

    def __init__(self, workflow: "Workflow", stage_id: int | str | None):
        self.workflow = workflow
        self.stage_id = stage_id

    @property
    def steps(self) -> list[Step]:
        return self.workflow.steps_in_stage(self.stage_id)

    @property
    def config(self) -> StageExecutionConfig:
        return self.workflow.stage_config.get(self.stage_id, StageExecutionConfig())

    def run(self) -> list[Step]:
        return self.workflow.run_stage(self.stage_id)

    def info(self) -> SummaryTable:
        steps = self.steps
        table = SummaryTable(
            f"Stage {self.stage_id!r}",
            caption=self.workflow._status_counts(steps),
            columns=["step", "tool", "status"],
        )
        for s in steps:
            table.add_row(s.step_id, self.workflow._tool_of(s), s.status.value)
        return table

    def __repr__(self) -> str:
        steps = self.steps
        return (f"<Stage {self.stage_id!r} \u00b7 {len(steps)} steps \u00b7 "
                f"{self.workflow._status_counts(steps)}>")


def _suspicious_literal(value: str, step_ids: list[str]) -> str | None:
    """Explain why a plain string argument looks like a mistyped reference.

    Only tokens starting with ``step`` are references (see
    ``domain/references.py``), so ``"stpe1"`` or ``"s1"`` is passed to the tool
    as a literal string and nothing complains. That is a silent wrong answer,
    and the one clue available before running is that the literal resembles a
    step id. Returns ``None`` for ordinary strings, which most arguments are.
    """
    import difflib

    if not value or len(value) > 64 or " " in value:
        return None                      # prose, a path, a prompt: not a typo
    head = value.split(".", 1)[0].split("[", 1)[0]
    if head in step_ids:
        return (f"{value!r} is a literal string, but a step is named {head!r}. "
                "References must start with 'step' to resolve.")
    close = difflib.get_close_matches(head, step_ids, n=1, cutoff=0.8)
    if close:
        return (f"{value!r} is a literal string, but closely matches step "
                f"{close[0]!r}. References must start with 'step' to resolve.")
    return None
