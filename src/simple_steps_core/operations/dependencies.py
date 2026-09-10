"""
Resource dependencies
=====================

A *resource* parameter is a runtime object a tool needs to do its work — a
database connection, an HTTP/LLM client, a config object — that is **not** part
of the data flow. It is injected from the session's resource container at run
time, and is deliberately hidden from the tool's JSON Schema so an agent never
sees (or supplies) it.

Mark a resource parameter by giving it a :func:`Resource` default::

    @register_tool("load_orders")
    def load_orders(region: str, db: Database = Resource()) -> DataFrame:
        ...

``region`` is a data parameter (in the schema); ``db`` is a resource parameter
(injected, excluded from the schema, listed in the definition's dependencies).
"""

from __future__ import annotations

from typing import Any


class ResourceMarker:
    """Sentinel default marking a parameter as an injected runtime resource.

    ``name`` overrides the container key; it defaults to the parameter name.
    """

    __slots__ = ("name",)

    def __init__(self, name: str | None = None):
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Resource(name={self.name!r})"


def Resource(name: str | None = None) -> Any:
    """Return a marker used as a parameter default to declare a resource.

    Typed as ``Any`` so it can stand in for any annotated parameter type
    without upsetting type checkers at the call site.
    """
    return ResourceMarker(name)
