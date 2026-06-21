"""
Domain models
=============

These are the *concepts* of Simple Steps — the durable, serializable shapes
that describe **what** to run, not **how** it runs. They hold no payload data
(no DataFrames, no large objects) and depend on nothing from other layers.

All models are Pydantic v2 so we get, for free:
  * shape validation on construction,
  * JSON save/load via ``model_dump_json()`` / ``model_validate_json()``,
  * a stable, inspectable schema the agent layer can reason about.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────
# Operation description (the "shape" of a registered tool)
# ─────────────────────────────────────────────────────────────────────────
class OperationParam(BaseModel):
    """One parameter of an operation, derived from its function signature."""

    name: str
    type_name: str = "Any"          # human-readable annotation, e.g. "str"
    required: bool = False          # True when the param has no default
    default: Any = None             # default value when not required

    model_config = {"frozen": True}


class OperationDefinition(BaseModel):
    """A registered operation's public contract (id + params + docs)."""

    operation_id: str
    description: str = ""
    params: list[OperationParam] = Field(default_factory=list)

    model_config = {"frozen": True}


# ─────────────────────────────────────────────────────────────────────────
# ToolCall (a durable, serialized invocation of one operation)
# ─────────────────────────────────────────────────────────────────────────
class ToolCall(BaseModel):
    """
    A deferred call: "run operation X with these keyword arguments."

    This is the canonical intermediate representation a formula parses into
    and renders back from. Arguments are plain JSON-safe values or reference
    tokens (e.g. ``"step1"``) that the execution layer resolves at run time.
    """

    operation_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


# ─────────────────────────────────────────────────────────────────────────
# Step lifecycle
# ─────────────────────────────────────────────────────────────────────────
class StepStatus(str, Enum):
    """Lifecycle state of a step's data output."""

    PENDING = "pending"             # not yet run
    RUNNING = "running"             # currently executing
    COMPLETED = "completed"         # ran successfully, output available
    FAILED = "failed"               # ran but raised an error

    @property
    def is_terminal(self) -> bool:
        """True once the step has finished, success or failure."""
        return self in (StepStatus.COMPLETED, StepStatus.FAILED)

    @property
    def has_output(self) -> bool:
        """True only when a usable output exists."""
        return self is StepStatus.COMPLETED


class StepOutput(BaseModel):
    """
    Pointer to (and optional inline copy of) what a step produced.

    The heavy payload normally lives in the session store, addressed by
    ``ref``. ``value`` may hold small inline results; large data should stay
    out of the model and be fetched from the store by reference.
    """

    ref: str | None = None          # session-store key for the full data
    value: Any = None               # inline value for small results (optional)
    kind: str | None = None         # "dataframe", "raw", "list", etc.


class Step(BaseModel):
    """A single workflow step: what to run and what it produced."""

    step_id: str
    formula: str                    # e.g. "=load_csv(filepath='a.csv')"
    status: StepStatus = StepStatus.PENDING
    output: StepOutput = Field(default_factory=StepOutput)
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────
# Orchestrator outcomes (iterative / partial-failure results)
# ─────────────────────────────────────────────────────────────────────────
class ItemOutcome(BaseModel):
    """The result of processing one item inside an orchestrator (e.g. ``map``).

    A single item may succeed or fail independently of its siblings, so each
    carries its own status and either a ``value`` or an ``error``.
    """

    index: int
    status: StepStatus = StepStatus.PENDING
    value: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is StepStatus.COMPLETED


class MapResult(BaseModel):
    """Aggregate result of an orchestrator that processes a collection.

    ``outcomes`` preserves per-item order and status. The ``ok`` / ``failed``
    helpers are exposed as attributes so downstream steps can reference them
    with dotted tokens, e.g. ``=summarize(rows=step2.ok)`` keeps only the
    successful values, while ``step2.failed`` drives a retry pass.
    """

    outcomes: list[ItemOutcome] = Field(default_factory=list)

    @property
    def ok(self) -> list[Any]:
        """Successful values, in original order."""
        return [o.value for o in self.outcomes if o.status is StepStatus.COMPLETED]

    @property
    def failed(self) -> list[ItemOutcome]:
        """Outcomes that failed, for inspection or re-driving."""
        return [o for o in self.outcomes if o.status is StepStatus.FAILED]

    @property
    def values(self) -> list[Any]:
        """All values in order (failed items contribute ``None``)."""
        return [o.value for o in self.outcomes]

    @property
    def ok_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status is StepStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status is StepStatus.FAILED)
