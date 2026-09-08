"""
Operation registry
==================

An *operation* is a stable, human-authored Python function — the real unit of
work (load a CSV, filter rows, call an LLM). This module:

  * builds an :class:`OperationDefinition` from a function's signature so the
    rest of the system can introspect it, and
  * wraps each registered function in a dual-mode :class:`Operation` so it can
    either be **deferred** (build a ``ToolCall`` for a workflow) or **run**
    immediately (the ``.run(...)`` escape hatch).

Dual-mode follows the Airflow/Prefect task pattern::

    call = load_csv(filepath="a.csv")   # -> ToolCall (nothing executed yet)
    value = load_csv.run(filepath="a")  # -> executes the function now
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Literal

from ..domain.models import Guardrails, OperationDefinition, OperationParam, ToolCall
from .dependencies import ResourceMarker
from .schema import build_input_schema, build_output_schema
from .ui import ToolUI, build_default_ui


def _normalize_ui(ui: Any) -> dict[str, Any]:
    """Coerce the ``ui`` argument into a ``{target: renderer}`` mapping.

    Accepts a prefab-ui protocol document (has a ``"view"`` key) as shorthand
    for ``{"prefab": <doc>}``, or a target→renderer map like
    ``{"streamlit": fn, "prefab": <doc>}``.
    """
    if ui is None:
        return {}
    if isinstance(ui, dict):
        return {"prefab": ui} if "view" in ui else dict(ui)
    raise TypeError("ui must be a prefab protocol dict or a {target: renderer} map")


class RegistryFrozenError(RuntimeError):
    """Raised when registering into a registry that has been frozen."""


class Operation:
    """
    A registered function in two modes.

    Calling the instance (``op(**kwargs)``) is **deferred**: it returns a
    :class:`ToolCall` describing the invocation, which a workflow stores and
    the engine later executes. ``op.run(**kwargs)`` is the **immediate**
    escape hatch that calls the underlying function right away.

    ``is_async`` marks coroutine functions so the engine can ``await`` them.
    ``is_orchestrator`` marks higher-order operations (map/filter/expand/
    collapse) that receive an execution *handle* as their first argument and
    drive sub-operations over a collection.
    """

    def __init__(
        self,
        operation_id: str,
        fn: Callable,
        definition: OperationDefinition,
        *,
        is_async: bool = False,
        is_orchestrator: bool = False,
        ui: ToolUI | None = None,
    ):
        self.operation_id = operation_id
        self.fn = fn
        self.definition = definition
        self.is_async = is_async
        self.is_orchestrator = is_orchestrator
        # UI views keyed by renderer target (prefab, streamlit, ...).
        self.ui = ui if ui is not None else ToolUI()

    @property
    def tool_id(self) -> str:
        """Preferred alias for :attr:`operation_id`."""
        return self.operation_id

    def __call__(self, **kwargs: Any) -> ToolCall:
        """Deferred mode: build a serializable ToolCall (no execution)."""
        return ToolCall(operation_id=self.operation_id, arguments=dict(kwargs))

    def run(self, **kwargs: Any) -> Any:
        """Immediate mode: execute the underlying function now."""
        return self.fn(**kwargs)


def _params_from_signature(fn: Callable, *, skip: int = 0) -> list[OperationParam]:
    """Introspect *fn* into a list of OperationParam, skipping leading params.

    ``skip`` drops the first N positional parameters from the public contract.
    Orchestrators use this to hide the injected execution ``handle`` argument.
    """
    signature = inspect.signature(fn)
    params: list[OperationParam] = []
    for index, (name, parameter) in enumerate(signature.parameters.items()):
        if index < skip:
            continue
        annotation = parameter.annotation
        type_name = (
            getattr(annotation, "__name__", "Any")
            if annotation is not inspect._empty
            else "Any"
        )
        if isinstance(parameter.default, ResourceMarker):
            # Resource params are injected at run time: required, no literal default.
            params.append(
                OperationParam(
                    name=name,
                    type_name=type_name,
                    required=True,
                    default=None,
                    kind="resource",
                )
            )
            continue
        # A data parameter is required when it has no default value.
        required = parameter.default is inspect._empty
        default = None if required else parameter.default
        params.append(
            OperationParam(
                name=name,
                type_name=type_name,
                required=required,
                default=default,
                kind="data",
            )
        )
    return params


class OperationRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, OperationDefinition] = {}
        self._callables: dict[str, Callable] = {}
        self._operations: dict[str, Operation] = {}
        self._frozen: bool = False

    def _guard_mutable(self) -> None:
        if self._frozen:
            raise RegistryFrozenError(
                "Registry is frozen; register all operations during startup "
                "before serving concurrent requests."
            )

    def register(
        self,
        operation_id: str,
        fn: Callable,
        description: str = "",
        *,
        category: str = "",
        type: Literal["source", "dataframe", "raw_output"] = "raw_output",
        ui: Any = None,
        guardrails: Guardrails | None = None,
    ) -> Operation:
        """Introspect *fn*, store its definition, and return an Operation wrapper."""
        self._guard_mutable()
        params = _params_from_signature(fn)
        input_schema = build_input_schema(fn)
        resolved_description = description or (inspect.getdoc(fn) or "").split("\n\n")[0].strip()
        views = _normalize_ui(ui)
        views["prefab"] = views.get("prefab") or build_default_ui(
            operation_id, input_schema, description=resolved_description, guardrails=guardrails
        )
        tool_ui = ToolUI(views)
        definition = OperationDefinition(
            operation_id=operation_id,
            description=resolved_description,
            category=category,
            type=type,
            params=params,
            input_schema=input_schema,
            output_schema=build_output_schema(fn),
            dependencies=[p.name for p in params if p.kind == "resource"],
            ui=tool_ui.definition_for("prefab"),
            guardrails=guardrails,
        )
        operation = Operation(
            operation_id,
            fn,
            definition,
            is_async=inspect.iscoroutinefunction(fn),
            ui=tool_ui,
        )
        self._definitions[operation_id] = definition
        self._callables[operation_id] = fn
        self._operations[operation_id] = operation
        return operation

    def register_orchestrator(
        self,
        operation_id: str,
        fn: Callable,
        description: str = "",
        *,
        category: str = "orchestration",
        ui: Any = None,
        guardrails: Guardrails | None = None,
    ) -> Operation:
        """Register a higher-order operation that receives an execution handle.

        The first positional parameter (the injected ``handle``) is hidden from
        the public :class:`OperationDefinition`, so validation and frontend
        discovery only see the user-facing arguments (``over``, ``op``, ...).
        """
        self._guard_mutable()
        params = _params_from_signature(fn, skip=1)
        input_schema = build_input_schema(fn, skip=1)
        views = _normalize_ui(ui)
        views["prefab"] = views.get("prefab") or build_default_ui(
            operation_id, input_schema, description=description, guardrails=guardrails
        )
        tool_ui = ToolUI(views)
        definition = OperationDefinition(
            operation_id=operation_id,
            description=description,
            category=category,
            type=operation_id if operation_id in {"map", "filter", "expand"} else "orchestrator",
            params=params,
            input_schema=input_schema,
            output_schema=build_output_schema(fn),
            dependencies=[p.name for p in params if p.kind == "resource"],
            ui=tool_ui.definition_for("prefab"),
            guardrails=guardrails,
        )
        operation = Operation(
            operation_id,
            fn,
            definition,
            is_async=inspect.iscoroutinefunction(fn),
            is_orchestrator=True,
            ui=tool_ui,
        )
        self._definitions[operation_id] = definition
        self._callables[operation_id] = fn
        self._operations[operation_id] = operation
        return operation

    def freeze(self) -> None:
        """Make the registry read-only.

        After startup registration completes, freezing the registry guarantees
        no further mutation, which makes concurrent reads safe across requests
        and threads without locking.
        """
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    def list_definitions(self) -> list[OperationDefinition]:
        return list(self._definitions.values())

    def get_definition(self, operation_id: str) -> OperationDefinition:
        if operation_id not in self._definitions:
            raise KeyError(f"Unknown operation: {operation_id}")
        return self._definitions[operation_id]

    def get_callable(self, operation_id: str) -> Callable:
        if operation_id not in self._callables:
            raise KeyError(f"Unknown operation: {operation_id}")
        return self._callables[operation_id]

    def get_operation(self, operation_id: str) -> Operation:
        if operation_id not in self._operations:
            raise KeyError(f"Unknown operation: {operation_id}")
        return self._operations[operation_id]

    def ui_for(self, operation_id: str, target: str = "prefab") -> Any:
        """Return a tool's UI view for a renderer *target* (``prefab``/``streamlit``/…).

        ``prefab`` is always available (auto-built if not supplied); other
        targets return ``None`` when the tool declares none.
        """
        return self.get_operation(operation_id).ui.get(target)

    def has(self, operation_id: str) -> bool:
        """True when an operation with this id is registered."""
        return operation_id in self._definitions


REGISTRY = OperationRegistry()


def register_operation(
    operation_id: str | None = None,
    description: str = "",
    *,
    category: str = "",
    type: Literal["source", "dataframe", "raw_output"] = "raw_output",
    ui: Any = None,
    guardrails: Guardrails | None = None,
):
    """
    Decorator that registers a function as an operation.

    Returns the dual-mode :class:`Operation` wrapper (not the raw function),
    so the decorated name supports both ``name(**kwargs)`` -> ToolCall and
    ``name.run(**kwargs)`` -> immediate execution.

    ``ui`` is a prefab-ui input document or a ``{target: declaration}`` map.
    A target declaration may use separate ``input``/``result`` views or one
    exclusive ``full`` view. The prefab input auto-builds when omitted.
    """

    def decorator(fn: Callable) -> Operation:
        resolved_id = operation_id or fn.__name__
        return REGISTRY.register(
            resolved_id,
            fn,
            description=description,
            category=category,
            type=type,
            ui=ui,
            guardrails=guardrails,
        )

    return decorator
