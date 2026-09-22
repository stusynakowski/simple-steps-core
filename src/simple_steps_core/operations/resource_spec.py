"""
Resource specs — a resource and the tools that come with it
===========================================================

A :class:`ResourceSpec` is a *standard resource*: the runtime object (how to
build it, how to check it) together with the tools that ship with it. Declaring
one looks like::

    file_system = ResourceSpec(
        "file_system",
        factory=lambda: Path("/data"),
        check=lambda root: root.exists(),
        description="The project data directory.",
    )

    @file_system.tool("list_files")
    def list_files(pattern: str, fs = Resource()) -> Collection:
        return FileListing(root=str(fs), pattern=pattern,
                           version=f"mtime:{fs.stat().st_mtime}")

    app.register_resource(file_system)      # factory + check + every tool

Two rules distinguish a bound tool from one registered with ``@register_tool``:

**Its id is namespaced.** ``list_files`` bound to ``file_system`` registers as
``file_system-list_files``. The name says what it can touch, and two resources
can each ship a ``list`` without colliding.

**It may use its own resource and no other.** An unnamed ``Resource()`` in a
bound tool's signature injects the owning resource whatever the parameter is
called; asking for a *different* resource by name raises
:class:`~.registry.ResourceBindingError` at import time, not at run time.
A tool that genuinely needs two resources is not a resource's tool — register
it unbound with ``@register_tool``.

A spec with no ``factory`` and no ``value`` is a **namespace-only** resource:
it groups tools that need no injected object. The built-in ``orchestration``
resource is one of those — its tools receive an execution handle from the
engine rather than a resource from the container.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from ..inspect import SummaryTable
from .registry import REGISTRY, Tool, ToolRegistry, qualify

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..execution.resources import ResourceContainer


class ResourceSpec:
    """A named runtime resource plus the tools bound to it."""

    def __init__(
        self,
        name: str,
        factory: Callable[[], Any] | None = None,
        *,
        value: Any = None,
        check: Callable[[Any], Any] | None = None,
        description: str = "",
        registry: ToolRegistry | None = None,
    ) -> None:
        if factory is not None and value is not None:
            raise ValueError(
                f"Resource {name!r} takes a factory or a value, not both."
            )
        self.name = name
        self.factory = factory
        self.value = value
        self.check = check
        self.description = description
        self.registry = registry if registry is not None else REGISTRY
        self._tool_ids: list[str] = []

    # ── authoring ────────────────────────────────────────────────────────
    def qualified(self, tool_name: str) -> str:
        """The registered id a tool of this resource gets."""
        return qualify(self.name, tool_name)

    def tool(self, tool_name: str | Callable | None = None, **kwargs: Any):
        """Register a tool bound to this resource.

        Usable bare (``@fs.tool``) or with a name and the usual
        :func:`~.registry.register_tool` options (``description``,
        ``category``, ``type``, ``ui``, ``guardrails``)::

            @file_system.tool("list_files", description="List matching files.")
            def list_files(pattern: str, fs = Resource()) -> Collection: ...
        """
        return self._decorator(tool_name, kwargs, orchestrator=False)

    def orchestrator(self, tool_name: str | Callable | None = None, **kwargs: Any):
        """Register a higher-order tool bound to this resource.

        Same as :meth:`tool`, but the function's first positional parameter is
        the engine-injected execution handle and is hidden from the contract.
        """
        return self._decorator(tool_name, kwargs, orchestrator=True)

    def _decorator(self, tool_name, kwargs: dict, *, orchestrator: bool):
        register = (
            self.registry.register_orchestrator if orchestrator else self.registry.register
        )

        def decorate(fn: Callable, name: str | None) -> Tool:
            operation = register(
                name or fn.__name__, fn, resource=self.name, **kwargs
            )
            self._tool_ids.append(operation.operation_id)
            return operation

        # Bare form: @resource.tool (the decorated function arrives directly).
        if callable(tool_name):
            return decorate(tool_name, None)
        return lambda fn: decorate(fn, tool_name)

    # ── installation ─────────────────────────────────────────────────────
    @property
    def is_namespace_only(self) -> bool:
        """True when this resource groups tools but injects nothing."""
        return self.factory is None and self.value is None

    def install(self, container: "ResourceContainer") -> None:
        """Declare this resource on a container (no-op if namespace-only)."""
        if self.is_namespace_only:
            return
        if self.value is not None:
            container.register_value(self.name, self.value, check=self.check)
        else:
            container.register(self.name, self.factory, check=self.check)

    # ── inspection ───────────────────────────────────────────────────────
    def tool_ids(self) -> list[str]:
        """Ids of the tools bound to this resource, in registration order."""
        return list(self._tool_ids)

    def tools(self):
        """The :class:`~..domain.models.ToolDefinition` of each bound tool."""
        return [self.registry.get_definition(t) for t in self._tool_ids]

    def info(self) -> SummaryTable:
        kind = "namespace" if self.is_namespace_only else (
            "value" if self.value is not None else "factory"
        )
        table = SummaryTable(
            f"Resource · {self.name}",
            caption=self.description or f"{kind} resource · "
                                        f"{len(self._tool_ids)} tool(s)",
            columns=["tool", "params", "description"],
        )
        for definition in self.tools():
            params = ", ".join(
                p.name for p in definition.params if p.kind == "data"
            ) or "-"
            table.add_row(definition.tool_id, params, definition.description or "-")
        if not self._tool_ids:
            table.add_row("(none)", "-", "-")
        return table

    def __repr__(self) -> str:
        kind = "namespace" if self.is_namespace_only else (
            "value" if self.value is not None else "factory"
        )
        checked = " check" if self.check else ""
        return (f"<ResourceSpec {self.name!r} {kind}{checked} · "
                f"{len(self._tool_ids)} tool(s)>")


def install_resources(
    container: "ResourceContainer",
    declared: Mapping[str, Any] | Sequence[Any] | None,
) -> None:
    """Declare *declared* onto *container*, whatever shape it arrives in.

    A tools file's ``RESOURCES`` may be:

    * a sequence of :class:`ResourceSpec` — ``[file_system, database]``;
    * a mapping of name to spec, factory, or value —
      ``{"photos": photos, "db": connect, "cfg": settings}``.

    A spec brings its own name, factory and check, so a mapping key that
    points at one is only a label; the spec's own name is what tools bind to.
    Anything callable is a factory, and anything else is an already-built
    value — the rule the dashboard and the HTTP server have always used.
    """
    if not declared:
        return
    entries = (
        declared.items() if isinstance(declared, Mapping)
        else [(None, item) for item in declared]
    )
    for name, provider in entries:
        if isinstance(provider, ResourceSpec):
            provider.install(container)
        elif callable(provider):
            container.register(name, provider)
        else:
            container.register_value(name, provider)
