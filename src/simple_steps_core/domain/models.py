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
from typing import Any, Literal

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
    kind: Literal["data", "resource"] = "data"  # resource params are injected

    model_config = {"frozen": True}


class ArgGuardrail(BaseModel):
    """Constraints on one argument's acceptable values (JSON-Schema-like)."""

    enum: list[Any] | None = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    note: str = ""

    model_config = {"frozen": True}


class Guardrails(BaseModel):
    """Policy for how a tool may be used and which arguments are acceptable.

    ``arguments`` is enforced at validation time (on literal values; reference
    tokens are checked at run time). The remaining fields are declarative
    guidance the UI and agent read.
    """

    usage: str = ""                                   # how/when to use the tool
    rules: list[str] = Field(default_factory=list)    # free-form policy statements
    arguments: dict[str, ArgGuardrail] = Field(default_factory=dict)
    read_only: bool = False
    destructive: bool = False
    requires_confirmation: bool = False

    model_config = {"frozen": True}


class OperationDefinition(BaseModel):
    """A registered operation's public contract (id + params + docs)."""

    operation_id: str
    description: str = ""
    category: str = ""
    type: Literal[
        "source",
        "map",
        "filter",
        "dataframe",
        "expand",
        "raw_output",
        "orchestrator",
    ] = "raw_output"
    params: list[OperationParam] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)   # JSON Schema (data params)
    output_schema: dict[str, Any] | None = None                  # JSON Schema (return type)
    dependencies: list[str] = Field(default_factory=list)        # resource param names
    ui: dict[str, Any] | None = None                             # prefab input, input/result, or full declaration
    guardrails: Guardrails | None = None                         # usage + argument policy

    model_config = {"frozen": True}
    @property
    def tool_id(self) -> str:
        """Preferred alias for :attr:`operation_id` (a definition names a tool)."""
        return self.operation_id

# ─────────────────────────────────────────────────────────────────────────
# ToolCall (a durable, serialized invocation of one operation)
# ─────────────────────────────────────────────────────────────────────────
class ToolCall(BaseModel):
    """
    A deferred call: "run operation X with these keyword arguments."

    This is the canonical, durable representation of an operation invocation.
    Arguments are plain JSON-safe values or reference tokens (e.g. ``"step1"``)
    that the execution layer resolves at run time.
    """

    operation_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}
    @property
    def tool_id(self) -> str:
        """Preferred alias for :attr:`operation_id` (a call names a tool)."""
        return self.operation_id

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


class Shape(BaseModel):
    """Lightweight metadata describing a referenced payload."""

    kind: Literal["dataframe", "raw"]
    rows: int
    columns: list[str] = Field(default_factory=list)
    value_type: str | None = None

    model_config = {"frozen": True}


class Cell(BaseModel):
    """JSON-safe value cell for grid-oriented frontend views."""

    row_id: str
    column_id: str
    value: Any = None
    display_value: str = ""

    model_config = {"frozen": True}


class StepError(BaseModel):
    """Structured details for an operation failure."""

    message: str
    type: str
    traceback: str | None = None

    model_config = {"frozen": True}


class StepResult(BaseModel):
    """Reference-only result returned by the runtime contract execution API."""

    step_id: str
    ref_id: str
    status: Literal["success", "failed"]
    shape: Shape
    error: StepError | None = None

    model_config = {"frozen": True}


class OrchestrationConfig(BaseModel):
    """How a step applies its tool across inputs (breadth).

    ``single`` runs the tool once. ``map``/``filter``/``expand``/``collapse``
    apply the step's own tool across the collection referenced by ``over``.
    """

    mode: Literal["single", "map", "filter", "expand", "collapse"] = "single"
    over: str | None = None          # step reference to the collection (e.g. "step1")
    item_arg: str | None = None      # tool param each item binds to (default: inferred)
    concurrency: int = 1
    on_error: Literal["collect", "fail_fast", "skip"] | None = None
    retries: int = 0
    initial: Any = None              # seed accumulator for ``collapse``

    model_config = {"frozen": True}


class ExecutionConfig(BaseModel):
    """How a step is invoked (orthogonal to orchestration)."""

    mode: Literal["sync", "async"] = "sync"
    run: Literal["auto", "manual"] = "manual"   # user controls execution by default
    timeout: float | None = None
    retries: int = 0
    cache: bool = False

    model_config = {"frozen": True}


# Default per-item failure policy by orchestration mode.
_ORCH_DEFAULT_ON_ERROR = {"map": "collect", "expand": "collect", "filter": "skip"}


class StepSpec(BaseModel):
    """A structured step: a tool to run plus how to orchestrate and execute it.

    Orchestration is declared **when the step is defined**: the step names the
    tool (``name``) and the orchestration config says whether to run it once or
    fan it out across a collection. :meth:`to_tool_call` compiles the spec into
    the executable :class:`ToolCall` the engine runs.
    """

    step_id: str
    name: str                                    # operation to run
    stage: int | str | None = None               # optional group for staged execution
    arguments: dict[str, Any] = Field(default_factory=dict)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

    model_config = {"frozen": True}

    def to_tool_call(self) -> ToolCall:
        """Compile this spec into the executable ToolCall.

        ``single`` yields a direct call; the orchestrated modes yield a call to
        the matching orchestrator (``map``/``filter``/``expand``/``collapse``)
        with this step's tool as the per-item ``op``.
        """
        orch = self.orchestration
        if orch.mode == "single":
            if orch.over is not None:
                raise ValueError("orchestration.over is only valid when mode != 'single'")
            return ToolCall(operation_id=self.name, arguments=dict(self.arguments))

        if not orch.over:
            raise ValueError(
                f"orchestration.over (a step reference) is required for mode {orch.mode!r}"
            )

        # Orchestrated modes call the matching orchestrator with this step's tool
        # as the per-item ``op``; this step's ``arguments`` become shared constant
        # kwargs passed to every sub-call (the item fills the item parameter).
        call_args: dict[str, Any] = {"over": orch.over, "op": self.name}
        if orch.item_arg is not None:
            call_args["arg"] = orch.item_arg
        if self.arguments:
            call_args["args"] = dict(self.arguments)
        if orch.mode == "collapse":
            call_args["initial"] = orch.initial
            return ToolCall(operation_id="collapse", arguments=call_args)

        call_args["concurrency"] = orch.concurrency
        call_args["on_error"] = orch.on_error or _ORCH_DEFAULT_ON_ERROR[orch.mode]
        call_args["retries"] = orch.retries
        return ToolCall(operation_id=orch.mode, arguments=call_args)


class Step(BaseModel):
    """A single workflow step: what to run and what it produced."""

    step_id: str
    call: ToolCall                  # the structured operation invocation
    spec: StepSpec | None = None    # structured authoring intent (if built from a StepSpec)
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
