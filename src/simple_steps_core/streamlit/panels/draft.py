"""
Draft state
===========

The dashboard's editing model. A :class:`DraftStep` is one row a user is
authoring — it may be incomplete (no tool chosen, a ``map`` without an ``over``)
in ways the frozen domain models reject, which is why the dashboard cannot hold
``Operation`` objects directly while editing.

This module is the bridge, and it is **pure Python**: no Streamlit, no session
state. That is what lets the panels above it be extracted and tested.

    Workflow  ──from_step──▶  DraftStep  ──to_operation──▶  Operation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simple_steps_core import (
    Operation,
    OrchestrationConfig,
    Step,
    StepExecutionConfig,
    Workflow,
)

__all__ = ["DraftStep", "DraftWorkflow"]


@dataclass
class DraftStep:
    """One step being authored. Mutable and tolerant of half-finished state."""

    id: str
    op: str | None = None
    stage: str | int | None = None
    #: argument name -> earlier step id it is bound to
    sources: dict[str, str] = field(default_factory=dict)
    orchestration: OrchestrationConfig = field(default_factory=OrchestrationConfig)
    execution: StepExecutionConfig = field(default_factory=StepExecutionConfig)
    #: literal argument values the user typed
    arguments: dict[str, Any] = field(default_factory=dict)
    #: True once the user picks a mode by hand, which stops inference
    #: from overwriting it on the next rerun.
    mode_locked: bool = False

    @property
    def is_fanned_out(self) -> bool:
        """True when this step runs more than one unit of work."""
        return self.orchestration.mode != "single"

    def primary_param(self, data_params) -> str | None:
        """The parameter that receives this step's data.

        Mirrors the library's own inference (``_infer_item_arg``): the explicit
        ``item_arg`` when set, else the first required parameter, else the first.
        """
        if self.orchestration.item_arg:
            return self.orchestration.item_arg
        required = [p.name for p in data_params if p.required]
        if required:
            return required[0]
        return data_params[0].name if data_params else None

    def data_source(self, data_params) -> str | None:
        """The earlier step this one consumes, however the mode expresses it.

        A fan-out records it as ``orchestration.over``; a single call records it
        as a reference bound to the primary parameter. One question, one answer,
        regardless of mode.
        """
        if self.is_fanned_out:
            return self.orchestration.over
        primary = self.primary_param(data_params)
        return self.sources.get(primary) if primary else None

    def set_data_source(self, source: str | None, data_params) -> None:
        """Route *source* to wherever the current mode keeps it."""
        primary = self.primary_param(data_params)
        if self.is_fanned_out:
            self.orchestration = self.orchestration.model_copy(update={"over": source})
            if primary:
                self.sources.pop(primary, None)   # the orchestrator supplies it
        else:
            self.orchestration = self.orchestration.model_copy(update={"over": None})
            if primary:
                if source:
                    self.sources[primary] = source
                else:
                    self.sources.pop(primary, None)

    def merged_arguments(self) -> dict[str, Any]:
        """Literal values with reference bindings layered on top."""
        merged = dict(self.arguments)
        merged.update(self.sources)
        return merged

    def to_operation(self) -> Operation:
        """Compile to the domain spec. Raises while the draft is incomplete."""
        if not self.op:
            raise ValueError(f"step {self.id!r} has no tool selected")
        return Operation(
            step_id=self.id,
            name=self.op,
            stage=self.stage,
            arguments=self.merged_arguments(),
            orchestration=self.orchestration,
            execution=self.execution,
        )

    @classmethod
    def from_step(cls, step: Step, known_ids: set[str]) -> "DraftStep":
        """Rebuild a draft row from a workflow's own step."""
        spec = step.spec
        if spec is None:
            return cls(id=step.step_id, op=step.call.operation_id,
                       arguments=dict(step.call.arguments))

        sources, literals = {}, {}
        for name, value in spec.arguments.items():
            if isinstance(value, str) and value in known_ids and value != step.step_id:
                sources[name] = value
            else:
                literals[name] = value
        return cls(
            id=step.step_id, op=spec.name, stage=spec.stage, sources=sources,
            orchestration=spec.orchestration, execution=spec.execution,
            arguments=literals,
            # A mode that came from a saved workflow is a deliberate choice.
            # Re-inferring it would silently rewrite the spec and reset the step.
            mode_locked=True,
        )


@dataclass
class DraftWorkflow:
    """The ordered draft rows plus the edits the toolbar performs on them.

    Every mutation is a plain method here rather than a Streamlit callback, so
    the step-management rules are testable without a browser.
    """

    steps: list[DraftStep] = field(default_factory=list)
    step_seq: int = 0
    stage_seq: int = 0

    # ── lookup ───────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)

    def __contains__(self, step_id: str) -> bool:
        return any(d.id == step_id for d in self.steps)

    def ids(self) -> list[str]:
        return [d.id for d in self.steps]

    def get(self, step_id: str) -> DraftStep | None:
        return next((d for d in self.steps if d.id == step_id), None)

    def prior_to(self, step_id: str) -> list[str]:
        """Step ids a step may reference — everything authored before it."""
        out: list[str] = []
        for d in self.steps:
            if d.id == step_id:
                break
            if d.op:
                out.append(d.id)
        return out

    # ── mutation ─────────────────────────────────────────────────────────
    def add(self) -> DraftStep:
        """Append a new empty row with the next ``step*`` id.

        Ids stay ``step``-prefixed on purpose: the reference grammar only
        resolves tokens matching ``^step…``, so any other name silently becomes
        a literal (see docs/api-reference.md § 3).
        """
        self.step_seq += 1
        draft = DraftStep(id=f"step{self.step_seq}")
        self.steps.append(draft)
        return draft

    def remove(self, step_ids: list[str]) -> None:
        self.steps = [d for d in self.steps if d.id not in set(step_ids)]

    def swap(self, first: str, second: str) -> None:
        """Exchange two rows' positions."""
        index = {d.id: i for i, d in enumerate(self.steps)}
        if first in index and second in index:
            i, j = index[first], index[second]
            self.steps[i], self.steps[j] = self.steps[j], self.steps[i]

    def group(self, step_ids: list[str]) -> str | None:
        """Put the selected rows in one new stage; returns the stage name."""
        chosen = [d for d in self.steps if d.id in set(step_ids)]
        if len(chosen) < 2:
            return None
        self.stage_seq += 1
        stage = f"stage{self.stage_seq}"
        for d in chosen:
            d.stage = stage
        return stage

    def ungroup(self, step_ids: list[str]) -> None:
        for d in self.steps:
            if d.id in set(step_ids):
                d.stage = None

    def clear(self) -> None:
        self.steps.clear()
        self.step_seq = 0
        self.stage_seq = 0

    # ── domain bridge ────────────────────────────────────────────────────
    def specs(self) -> dict[str, Operation]:
        """Every row that compiles, as domain specs. Incomplete rows are skipped."""
        out: dict[str, Operation] = {}
        for d in self.steps:
            if not d.op:
                continue
            try:
                out[d.id] = d.to_operation()
            except ValueError:
                continue
        return out

    def author_into(self, workflow: Workflow) -> dict[str, str]:
        """Sync the draft into *workflow*; returns {step_id: why it can't run}.

        A half-authored row is normal while editing (``map`` chosen before
        ``over``). The library validates on assignment, so such a row is kept
        out of the workflow and its own message returned rather than raised.
        """
        specs = self.specs()
        for step_id in list(workflow._steps):
            if step_id not in specs:
                del workflow[step_id]

        problems: dict[str, str] = {}
        for step_id, spec in specs.items():
            if step_id in workflow and workflow[step_id].spec == spec:
                continue
            try:
                workflow[step_id] = spec
            except (ValueError, TypeError) as exc:
                problems[step_id] = str(exc)
        return problems

    @classmethod
    def from_workflow(cls, workflow: Workflow) -> "DraftWorkflow":
        """Rebuild the whole draft from a workflow's steps."""
        known = {s.step_id for s in workflow.steps}
        drafts = [DraftStep.from_step(s, known) for s in workflow.steps]
        stages = {d.stage for d in drafts if d.stage}
        return cls(steps=drafts, step_seq=len(drafts), stage_seq=len(stages))
