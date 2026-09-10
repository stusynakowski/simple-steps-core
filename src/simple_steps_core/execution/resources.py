"""
Resource container
==================

Holds the runtime *resources* (database connections, HTTP/LLM clients, config)
that tools declare with :func:`Resource` and the engine injects at call time.

Lifecycle (see docs/object-model.md): **declare → load → check → use**.

* **declare** — ``register(name, factory, check=...)`` records *how* to build it
  (cheap, no connection). ``check`` is an optional "hello-world" callable.
* **load** — the instance is built lazily on first use, or eagerly via
  :meth:`load_all`.
* **check** *(optional)* — :meth:`check` / :meth:`check_all` run the tiny
  hello-world to prove the resource works before a big batch.
* **use** — tools receive the injected instance at call time.

Resources are kept separate from session payloads: they have their own
lifecycle, are created lazily, and are **never serialized** into a snapshot —
on session load they are reconstructed from their registered factories.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..inspect import SummaryTable


class ResourceMissingError(KeyError):
    """Raised when a tool requires a resource that was never registered."""


@dataclass(frozen=True)
class ResourceCheck:
    """Result of a single resource health check."""

    name: str
    status: str            # "ok" | "failed" | "skipped"
    latency: float | None = None
    sample: str = ""
    error: str = ""

    _MARK = {"ok": "\u2713", "failed": "\u2717", "skipped": "\u2298"}

    def __repr__(self) -> str:
        mark = self._MARK.get(self.status, "?")
        secs = "" if self.latency is None else f" {self.latency:.2f}s"
        tail = f" {self.error}" if self.error else (f" {self.sample}" if self.sample else "")
        return f"<ResourceCheck {self.name} {mark} {self.status}{secs}{tail}>"


class ResourceContainer:
    """A per-session registry of injectable runtime resources."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Any]] = {}
        self._instances: dict[str, Any] = {}
        self._checks: dict[str, Callable[[Any], Any]] = {}
        self._errors: dict[str, str] = {}

    # ── declare ──────────────────────────────────────────────────────────
    def register(
        self,
        name: str,
        factory: Callable[[], Any],
        *,
        check: Callable[[Any], Any] | None = None,
    ) -> None:
        """Register a zero-arg factory; built lazily on first use.

        ``check`` is an optional callable taking the built instance and running
        a trivial "hello-world" (e.g. ``lambda db: db.execute("SELECT 1")``).
        """
        self._factories[name] = factory
        if check is not None:
            self._checks[name] = check

    def register_value(
        self, name: str, value: Any, *, check: Callable[[Any], Any] | None = None
    ) -> None:
        """Register an already-constructed resource instance."""
        self._instances[name] = value
        if check is not None:
            self._checks[name] = check

    def has(self, name: str) -> bool:
        return name in self._instances or name in self._factories

    # ── load ─────────────────────────────────────────────────────────────
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

    def is_loaded(self, name: str) -> bool:
        return name in self._instances

    def load(self, name: str) -> Any:
        """Eagerly build a resource now (fail-fast)."""
        return self.get(name)

    def load_all(self) -> None:
        """Eagerly build every declared resource (fail-fast setup)."""
        for name in self.names():
            self.get(name)

    # ── check (optional health check) ────────────────────────────────────
    def check(self, name: str) -> ResourceCheck:
        """Run a resource's hello-world check (or a weaker load-only test)."""
        if not self.has(name):
            return ResourceCheck(name, "failed", error="not registered")
        start = time.perf_counter()
        try:
            instance = self.get(name)
        except Exception as exc:                       # noqa: BLE001 - report, don't raise
            self._errors[name] = str(exc)
            return ResourceCheck(name, "failed", error=f"load failed: {exc}")

        check_fn = self._checks.get(name)
        if check_fn is None:
            # No hello-world provided: the load itself is the (weaker) test.
            return ResourceCheck(name, "skipped", latency=time.perf_counter() - start)
        try:
            result = check_fn(instance)
        except Exception as exc:                       # noqa: BLE001
            self._errors[name] = str(exc)
            return ResourceCheck(name, "failed",
                                 latency=time.perf_counter() - start, error=str(exc))
        sample = "" if result is None else repr(result)
        if len(sample) > 40:
            sample = sample[:37] + "..."
        return ResourceCheck(name, "ok", latency=time.perf_counter() - start, sample=sample)

    def check_all(self) -> SummaryTable:
        """Check every resource and report all results (does not stop at first fail)."""
        table = SummaryTable(
            "Resource checks",
            columns=["resource", "status", "latency", "detail"],
        )
        for name in sorted(self.names()):
            r = self.check(name)
            latency = "" if r.latency is None else f"{r.latency:.2f}s"
            detail = r.error or r.sample
            table.add_row(name, f"{ResourceCheck._MARK.get(r.status, '?')} {r.status}",
                          latency, detail)
        return table

    def names(self) -> list[str]:
        return sorted({*self._factories, *self._instances})

    def clone(self) -> "ResourceContainer":
        """A new container seeded with these declarations (own instance cache).

        Factories and checks are copied so each session builds its **own**
        instances lazily; already-built values are shared by reference.
        """
        other = ResourceContainer()
        other._factories = dict(self._factories)
        other._instances = dict(self._instances)
        other._checks = dict(self._checks)
        return other

    def _source(self, name: str) -> str:
        if name in self._instances and name not in self._factories:
            return "value"
        return "factory"

    def _status(self, name: str) -> str:
        if name in self._errors:
            return "error"
        if self.is_loaded(name):
            return "loaded"
        return "declared"

    # ── inspection ───────────────────────────────────────────────────────
    def info(self, required_by: dict[str, list[str]] | None = None) -> SummaryTable:
        """A tabular overview of every resource and its status."""
        cols = ["resource", "source", "status", "check?"]
        if required_by is not None:
            cols.append("required_by")
        table = SummaryTable("Resources", columns=cols)
        for name in self.names():
            row = [
                name,
                self._source(name),
                self._status(name),
                "yes" if name in self._checks else "no",
            ]
            if required_by is not None:
                row.append(", ".join(required_by.get(name, [])) or "-")
            table.add_row(*row)
        return table

    def __repr__(self) -> str:
        n = len(self.names())
        loaded = sum(1 for x in self.names() if self.is_loaded(x))
        return f"<Resources {n} declared, {loaded} loaded>"

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
