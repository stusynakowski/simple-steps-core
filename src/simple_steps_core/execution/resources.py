"""
Resource container
==================

Holds the runtime *resources* (database connections, HTTP/LLM clients, config)
that tools declare with :func:`Resource` and the engine injects at call time.

Resources are kept separate from session payloads: they have their own
lifecycle, are created lazily, and are **never serialized** into a snapshot —
on session load they are reconstructed from their registered factories.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ResourceMissingError(KeyError):
    """Raised when a tool requires a resource that was never registered."""


class ResourceContainer:
    """A per-session registry of injectable runtime resources."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Any]] = {}
        self._instances: dict[str, Any] = {}

    def register(self, name: str, factory: Callable[[], Any]) -> None:
        """Register a zero-arg factory; the instance is built lazily on first use."""
        self._factories[name] = factory

    def register_value(self, name: str, value: Any) -> None:
        """Register an already-constructed resource instance."""
        self._instances[name] = value

    def has(self, name: str) -> bool:
        return name in self._instances or name in self._factories

    def get(self, name: str) -> Any:
        """Return the resource, instantiating and caching a factory on first use."""
        if name in self._instances:
            return self._instances[name]
        if name in self._factories:
            value = self._factories[name]()
            self._instances[name] = value
            return value
        raise ResourceMissingError(
            f"No resource registered for {name!r}; register it on the session's "
            "ResourceContainer before running a tool that depends on it."
        )

    def names(self) -> list[str]:
        return list({*self._factories, *self._instances})

    def aclose(self) -> None:
        """Close instantiated resources that expose a ``close`` method."""
        for value in self._instances.values():
            close = getattr(value, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    # A failing close on one resource must not block the rest.
                    pass
        self._instances.clear()
