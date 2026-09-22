"""
Operation registry
==================

An *operation* is a stable, human-authored Python function — the real unit of
work (load a CSV, filter rows, call an LLM). This module:

  * builds an :class:`ToolDefinition` from a function's signature so the
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

from ..domain.models import Guardrails, ToolDefinition, ToolParam, ToolCall
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


class Tool:
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
        definition: ToolDefinition,
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

    def __repr__(self) -> str:
        kind = ("orchestrator" if self.is_orchestrator
                else "async" if self.is_async else "tool")
        return f"<Tool {self.operation_id!r} {kind} · {len(self.definition.params)} param(s)>"

    def __call__(self, **kwargs: Any) -> ToolCall:
        """Deferred mode: build a serializable ToolCall (no execution)."""
        return ToolCall(operation_id=self.operation_id, arguments=dict(kwargs))

    def run(self, **kwargs: Any) -> Any:
        """Immediate mode: execute the underlying function now."""
        return self.fn(**kwargs)


def _params_from_signature(fn: Callable, *, skip: int = 0) -> list[ToolParam]:
    """Introspect *fn* into a list of ToolParam, skipping leading params.

    ``skip`` drops the first N positional parameters from the public contract.
    Orchestrators use this to hide the injected execution ``handle`` argument.
    """
    signature = inspect.signature(fn)
    params: list[ToolParam] = []
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
            # ``Resource("file_system")`` overrides the container key, so a tool
            # can name its parameter `fs` and still bind to `file_system`.
            params.append(
                ToolParam(
                    name=name,
                    type_name=type_name,
                    required=True,
                    default=None,
                    kind="resource",
                    resource_name=parameter.default.name,
                )
            )
            continue
        # A data parameter is required when it has no default value.
        required = parameter.default is inspect._empty
        default = None if required else parameter.default
        params.append(
            ToolParam(
                name=name,
                type_name=type_name,
                required=required,
                default=default,
                kind="data",
            )
        )
    return params


#: Separates a resource name from a tool name in a bound tool's id.
RESOURCE_SEPARATOR = "-"


def qualify(resource: str, tool_name: str) -> str:
    """The id of *tool_name* when bound to *resource* (``file_system-list_files``).

    Already-qualified names pass through, so re-registering is idempotent.
    """
    prefix = f"{resource}{RESOURCE_SEPARATOR}"
    return tool_name if tool_name.startswith(prefix) else f"{prefix}{tool_name}"


def split_qualified(tool_id: str) -> tuple[str | None, str]:
    """Split ``"file_system-list_files"`` into ``("file_system", "list_files")``.

    An unbound id yields ``(None, tool_id)``. Only the first separator splits,
    so a tool name may itself contain a hyphen.
    """
    resource, sep, name = tool_id.partition(RESOURCE_SEPARATOR)
    return (resource, name) if sep else (None, tool_id)


class ResourceBindingError(TypeError):
    """Raised when a resource-bound tool reaches for a resource it does not own."""


def _resource_keys(params: list[ToolParam]) -> list[str]:
    """The container keys a tool's resource params inject from, in order."""
    keys: list[str] = []
    for param in params:
        if param.kind != "resource":
            continue
        key = param.resource_name or param.name
        if key not in keys:
            keys.append(key)
    return keys


def _bind_resource_params(
    params: list[ToolParam], owner: str, tool_id: str
) -> list[ToolParam]:
    """Point a bound tool's unqualified resource params at *owner*, and enforce.

    A tool bound to a resource may use **that resource and no other**: an
    unnamed ``Resource()`` binds to the owner regardless of what the parameter
    is called, and a ``Resource("something_else")`` is rejected at import time
    rather than failing at run time on a missing injection.
    """
    bound: list[ToolParam] = []
    for param in params:
        if param.kind != "resource":
            bound.append(param)
            continue
        # An unnamed Resource() on a bound tool means "my owner", whatever the
        # parameter happens to be called (`fs`, `client`, `db`).
        if param.resource_name in (None, owner):
            bound.append(param.model_copy(update={"resource_name": owner}))
            continue
        raise ResourceBindingError(
            f"Tool {tool_id!r} is bound to resource {owner!r} but its parameter "
            f"{param.name!r} asks for resource {param.resource_name!r}. A "
            f"resource-bound tool may only use its own resource; register it "
            f"with @register_tool instead if it genuinely needs both."
        )
    return bound


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._callables: dict[str, Callable] = {}
        self._operations: dict[str, Tool] = {}
        # alias -> canonical tool id. Lets the short orchestrator names ("map")
        # keep resolving after they moved under the orchestration resource.
        self._aliases: dict[str, str] = {}
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
        resource: str | None = None,
        aliases: tuple[str, ...] = (),
    ) -> Tool:
        """Introspect *fn*, store its definition, and return an Operation wrapper.

        ``resource`` binds the tool to a resource: its id is namespaced as
        ``{resource}-{operation_id}``, and it may inject that resource and no
        other (see :func:`_bind_resource_params`). ``aliases`` registers extra
        ids that resolve to this tool.
        """
        self._guard_mutable()
        params = _params_from_signature(fn)
        if resource is not None:
            operation_id = qualify(resource, operation_id)
            params = _bind_resource_params(params, resource, operation_id)
        input_schema = build_input_schema(fn)
        resolved_description = description or (inspect.getdoc(fn) or "").split("\n\n")[0].strip()
        views = _normalize_ui(ui)
        views["prefab"] = views.get("prefab") or build_default_ui(
            operation_id, input_schema, description=resolved_description, guardrails=guardrails
        )
        tool_ui = ToolUI(views)
        definition = ToolDefinition(
            operation_id=operation_id,
            description=resolved_description,
            category=category,
            type=type,
            params=params,
            input_schema=input_schema,
            output_schema=build_output_schema(fn),
            dependencies=_resource_keys(params),
            resource=resource,
            ui=tool_ui.definition_for("prefab"),
            guardrails=guardrails,
        )
        operation = Tool(
            operation_id,
            fn,
            definition,
            is_async=inspect.iscoroutinefunction(fn),
            ui=tool_ui,
        )
        self._definitions[operation_id] = definition
        self._callables[operation_id] = fn
        self._operations[operation_id] = operation
        for alias in aliases:
            self.add_alias(alias, operation_id)
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
        resource: str | None = None,
        aliases: tuple[str, ...] = (),
    ) -> Tool:
        """Register a higher-order operation that receives an execution handle.

        The first positional parameter (the injected ``handle``) is hidden from
        the public :class:`ToolDefinition`, so validation and frontend
        discovery only see the user-facing arguments (``over``, ``op``, ...).
        """
        self._guard_mutable()
        params = _params_from_signature(fn, skip=1)
        short_id = operation_id
        if resource is not None:
            operation_id = qualify(resource, operation_id)
            params = _bind_resource_params(params, resource, operation_id)
        input_schema = build_input_schema(fn, skip=1)
        views = _normalize_ui(ui)
        views["prefab"] = views.get("prefab") or build_default_ui(
            operation_id, input_schema, description=description, guardrails=guardrails
        )
        tool_ui = ToolUI(views)
        definition = ToolDefinition(
            operation_id=operation_id,
            description=description,
            category=category,
            type=short_id if short_id in {"map", "filter", "expand"} else "orchestrator",
            params=params,
            input_schema=input_schema,
            output_schema=build_output_schema(fn),
            dependencies=_resource_keys(params),
            resource=resource,
            ui=tool_ui.definition_for("prefab"),
            guardrails=guardrails,
        )
        operation = Tool(
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
        for alias in aliases:
            self.add_alias(alias, operation_id)
        return operation

    # ── aliases ──────────────────────────────────────────────────────────
    def add_alias(self, alias: str, tool_id: str) -> None:
        """Register *alias* as another id for *tool_id*.

        Used to keep the bare orchestrator names (``map``, ``collapse``)
        resolving after they moved under the orchestration resource, so saved
        workflows and existing specs are not invalidated by the rename.
        """
        self._guard_mutable()
        if alias in self._definitions:
            raise ValueError(
                f"Cannot alias {alias!r} to {tool_id!r}: a tool is already "
                f"registered under that id."
            )
        self._aliases[alias] = tool_id

    def resolve(self, operation_id: str) -> str:
        """The canonical tool id for *operation_id* (following one alias hop)."""
        if operation_id in self._definitions:
            return operation_id
        return self._aliases.get(operation_id, operation_id)

    def aliases(self) -> dict[str, str]:
        """A copy of the alias -> canonical id map."""
        return dict(self._aliases)

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

    def list_definitions(self) -> list[ToolDefinition]:
        return list(self._definitions.values())

    def get_definition(self, operation_id: str) -> ToolDefinition:
        resolved = self.resolve(operation_id)
        if resolved not in self._definitions:
            raise KeyError(f"Unknown operation: {operation_id}")
        return self._definitions[resolved]

    def get_callable(self, operation_id: str) -> Callable:
        resolved = self.resolve(operation_id)
        if resolved not in self._callables:
            raise KeyError(f"Unknown operation: {operation_id}")
        return self._callables[resolved]

    def get_operation(self, operation_id: str) -> Tool:
        resolved = self.resolve(operation_id)
        if resolved not in self._operations:
            raise KeyError(f"Unknown operation: {operation_id}")
        return self._operations[resolved]

    def tools_for(self, resource: str) -> list[ToolDefinition]:
        """Every tool bound to *resource*, in registration order."""
        return [d for d in self._definitions.values() if d.resource == resource]

    def ui_for(self, operation_id: str, target: str = "prefab") -> Any:
        """Return a tool's UI view for a renderer *target* (``prefab``/``streamlit``/…).

        ``prefab`` is always available (auto-built if not supplied); other
        targets return ``None`` when the tool declares none.
        """
        return self.get_operation(operation_id).ui.get(target)

    def has(self, operation_id: str) -> bool:
        """True when an operation with this id (or alias) is registered."""
        return self.resolve(operation_id) in self._definitions


REGISTRY = ToolRegistry()


def register_tool(
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

    def decorator(fn: Callable) -> Tool:
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
