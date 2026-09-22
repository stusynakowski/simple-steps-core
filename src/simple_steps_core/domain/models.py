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
class ToolParam(BaseModel):
    """One parameter of an operation, derived from its function signature."""

    name: str
    type_name: str = "Any"          # human-readable annotation, e.g. "str"
    required: bool = False          # True when the param has no default
    default: Any = None             # default value when not required
    kind: Literal["data", "resource"] = "data"  # resource params are injected
    # For a resource param: the container key to inject from, which is the
    # parameter name unless Resource("other_name") overrode it. Lets a tool
    # call its parameter `fs` while binding to the `file_system` resource.
    resource_name: str | None = None

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


class ToolDefinition(BaseModel):
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
    params: list[ToolParam] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)   # JSON Schema (data params)
    output_schema: dict[str, Any] | None = None                  # JSON Schema (return type)
    dependencies: list[str] = Field(default_factory=list)        # resource container keys
    resource: str | None = None                                  # owning resource, if bound
    ui: dict[str, Any] | None = None                             # prefab input, input/result, or full declaration
    guardrails: Guardrails | None = None                         # usage + argument policy

    model_config = {"frozen": True}
    @property
    def tool_id(self) -> str:
        """Preferred alias for :attr:`operation_id` (a definition names a tool)."""
        return self.operation_id

    def __repr__(self) -> str:
        return f"<ToolDefinition {self.operation_id!r} · {len(self.params)} param(s)>"

    def info(self):
        """A tabular view of the tool's contract (params + docs)."""
        from ..inspect import SummaryTable

        table = SummaryTable(
            f"Tool · {self.operation_id}",
            caption=self.description,
            columns=["param", "type", "required", "default", "kind"],
        )
        for p in self.params:
            table.add_row(p.name, p.type_name, p.required,
                          "" if p.default is None else p.default, p.kind)
        return table

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
    started_at: float | None = None  # epoch seconds when the step began
    ended_at: float | None = None    # epoch seconds when the step finished

    @property
    def duration(self) -> float | None:
        """Wall-clock seconds the step took, if it has run."""
        if self.started_at is None or self.ended_at is None:
            return None
        return self.ended_at - self.started_at


class Shape(BaseModel):
    """Lightweight metadata describing a referenced payload."""

    kind: Literal["dataframe", "raw"]
    rows: int
    columns: list[str] = Field(default_factory=list)
    value_type: str | None = None
    # False when ``rows`` is a floor rather than a count: a lazy Collection
    # (a paged API, a glob) knows its items only by reading them. Renderers
    # should show "?" or "n+" instead of claiming an exact size.
    rows_known: bool = True

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
    """**Shape only**: how a step's input data fans out and comes back.

    ``single`` runs the tool once. ``map``/``filter``/``expand``/``collapse``/
    ``group`` apply the step's own tool across the collection referenced by
    ``over``. Under ``group`` the step's tool is the **key function**: each
    item is passed to it and the result becomes the bucket the item lands in.

    How that work is *conducted* — concurrency, per-item error policy, retries,
    timeouts — belongs to :class:`StepExecutionConfig`. The two configs are
    isolated by concern: nothing here describes runtime behavior.
    """

    mode: Literal["single", "map", "filter", "expand", "collapse", "group"] = "single"
    over: str | None = None          # step reference to the collection (e.g. "step1")
    item_arg: str | None = None      # tool param each item binds to (default: inferred)
    initial: Any = None              # seed accumulator for ``collapse``

    # No silent drops: a field that moved scope must fail loudly, not vanish.
    model_config = {"frozen": True, "extra": "forbid"}


class StepExecutionConfig(BaseModel):
    """**Conduct only**: how a step's unit of work is carried out.

    Isolated to the step scope: it never inherits from or overrides the stage
    or workflow configs (see docs/object-model.md). ``mode`` (sync/async) is
    derived from the tool, not set here.

    The unit of work is defined by :class:`OrchestrationConfig.mode` — the whole
    call when ``single``, one item when fanned out. So ``retries`` means "retry
    the unit" in both cases, and ``concurrency`` / ``on_item_error`` apply only
    when there is more than one unit (``map``/``filter``/``expand``).
    """

    run: Literal["auto", "manual"] = "manual"   # gate this step
    timeout: float | None = None
    retries: int = 0
    cache: bool = False
    concurrency: int = 1                        # parallel units; fan-out modes only
    on_item_error: Literal["collect", "fail_fast", "skip"] | None = None

    # No silent drops: a field that moved scope must fail loudly, not vanish.
    model_config = {"frozen": True, "extra": "forbid"}


class StageExecutionConfig(BaseModel):
    """How a **stage's steps** run together (phase-level coordination).

    Isolated to the stage scope. ``steps='parallel'`` is only valid when the
    stage's steps do not reference one another.
    """

    steps: Literal["sequential", "parallel"] = "sequential"
    concurrency: int = 1
    on_step_error: Literal["stop", "continue"] = "stop"
    run: Literal["auto", "manual"] = "manual"   # gate this phase

    # No silent drops: a field that moved scope must fail loudly, not vanish.
    model_config = {"frozen": True, "extra": "forbid"}


class WorkflowExecutionConfig(BaseModel):
    """How a **workflow's stages** run (top-level coordination).

    Isolated to the workflow scope.
    """

    stages: Literal["sequential"] = "sequential"
    on_stage_error: Literal["stop", "continue"] = "stop"
    run: Literal["auto", "manual"] = "manual"   # gate the whole workflow

    # No silent drops: a field that moved scope must fail loudly, not vanish.
    model_config = {"frozen": True, "extra": "forbid"}


# Default per-item failure policy by orchestration mode.
#: The built-in resource that owns the orchestrators. Their tool ids are
#: ``orchestration-map``, ``orchestration-filter``, ... and the bare names
#: (``map``, ``filter``, ...) stay registered as aliases, so saved workflows
#: and existing specs keep resolving.
ORCHESTRATION_RESOURCE = "orchestration"


def orchestrator_id(mode: str) -> str:
    """The qualified tool id backing an orchestration *mode*."""
    return f"{ORCHESTRATION_RESOURCE}-{mode}"


_ORCH_DEFAULT_ON_ERROR = {
    "map": "collect",
    "expand": "collect",
    "filter": "skip",
    "group": "skip",
}


class Operation(BaseModel):
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
    execution: StepExecutionConfig = Field(default_factory=StepExecutionConfig)

    model_config = {"frozen": True}

    @property
    def tool(self) -> str:
        """The id of the Tool this operation runs (alias of :attr:`name`)."""
        return self.name

    def __repr__(self) -> str:
        mode = self.orchestration.mode
        breadth = "" if mode == "single" else f" {mode}(over={self.orchestration.over!r})"
        stage = "" if self.stage is None else f" stage={self.stage!r}"
        return f"<Operation {self.step_id!r} tool={self.name!r}{breadth}{stage}>"

    def to_tool_call(self) -> ToolCall:
        """Compile this spec into the executable ToolCall.

        ``single`` yields a direct call; the orchestrated modes yield a call to
        the matching orchestrator (``map``/``filter``/``expand``/``collapse``)
        with this step's tool as the per-item ``op``.

        Shape (``mode``/``over``/``item_arg``/``initial``) comes from
        ``orchestration``; conduct (``concurrency``/``on_item_error``/
        ``retries``) comes from ``execution``.
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
            return ToolCall(operation_id=orchestrator_id("collapse"), arguments=call_args)

        # Conduct comes from the execution config; shape came from orchestration.
        # The orchestrators are ordinary tools, so their runtime policy has to
        # arrive as arguments — this is the one place the two configs meet.
        execution = self.execution
        call_args["concurrency"] = execution.concurrency
        call_args["on_error"] = execution.on_item_error or _ORCH_DEFAULT_ON_ERROR[orch.mode]
        call_args["retries"] = execution.retries
        return ToolCall(operation_id=orchestrator_id(orch.mode), arguments=call_args)


class Step(BaseModel):
    """A single workflow step: what to run and what it produced."""

    step_id: str
    call: ToolCall                  # the structured operation invocation
    spec: Operation | None = None    # structured authoring intent (if built from a Operation)
    status: StepStatus = StepStatus.PENDING
    output: StepOutput = Field(default_factory=StepOutput)
    error: str | None = None
    def __repr__(self) -> str:
        dur = self.output.duration
        tail = "" if dur is None else f" {dur:.3f}s"
        return f"<Step {self.step_id!r} {self.status.value} tool={self.call.operation_id!r}{tail}>"

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

    def __repr__(self) -> str:
        return (f"<MapResult {self.ok_count} ok, {self.failed_count} failed "
                f"of {len(self.outcomes)}>")
