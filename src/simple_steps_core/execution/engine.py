"""
Execution engine
================

The engine turns a :class:`ToolCall` into a real result. For each call it:

  1. validates the call against the registry,
  2. resolves any reference-token arguments against the session store,
  3. runs the underlying operation function (sync or async), and
  4. stores the produced payload under a fresh output reference.

It returns ``(ref_id, value)`` so callers can either keep the lightweight
reference or use the value directly.

Two execution surfaces exist:

  * :meth:`CoreEngine.aexecute` — the async core; ``await`` it from async code.
  * :meth:`CoreEngine.execute`  — a sync wrapper that runs the async core to
    completion. It stays backward compatible for plain sync operations and
    also transparently drives async/orchestrator operations, as long as it is
    not called from within an already-running event loop.

Orchestrators (``map``/``filter``/``expand``/``collapse``) are higher-order
operations. They receive an :class:`ExecutionHandle` as their first argument
so they can run sub-operations over a collection while sharing this engine's
registry and the active session context.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from ..domain.models import ToolCall
from ..operations.registry import OperationRegistry
from ..operations.validation import validate_tool_call
from .context import SessionContext
from .resolver import ReferenceResolver


class ExecutionHandle:
    """Engine access handed to an orchestrator so it can drive sub-operations.

    Orchestrators iterate over a collection and invoke a named operation per
    item. ``run`` executes that sub-operation directly (no reference
    resolution, no session storage) because the per-item value is already a
    concrete Python object; only the orchestrator's aggregate result is stored.
    """

    def __init__(self, engine: "CoreEngine", context: SessionContext):
        self._engine = engine
        self.context = context
        self.registry = engine.registry

    async def run(self, operation_id: str, /, **kwargs: Any) -> Any:
        """Execute a sub-operation by id with literal keyword arguments."""
        return await self._engine._call_operation(operation_id, kwargs)

    def get_definition(self, operation_id: str):
        """Look up a sub-operation's contract (used to infer item arg names)."""
        return self.registry.get_definition(operation_id)


class CoreEngine:
    def __init__(self, registry: OperationRegistry):
        self.registry = registry

    # ── async core ───────────────────────────────────────────────────────
    async def aexecute(self, tool_call: ToolCall, context: SessionContext) -> tuple[str, Any]:
        """Validate, resolve, run (awaiting if needed), and store one tool call."""
        # 1. Tool-aware validation (operation exists, args fit its contract).
        validate_tool_call(tool_call, self.registry)

        operation = self.registry.get_operation(tool_call.operation_id)
        resolver = ReferenceResolver(context)
        arguments = resolver.resolve_arguments(tool_call.arguments)

        if operation.is_orchestrator:
            # 2/3. Orchestrators receive an execution handle and drive sub-ops.
            handle = ExecutionHandle(self, context)
            value = await operation.fn(handle, **arguments)
        elif operation.is_async:
            value = await operation.fn(**arguments)
        else:
            # Run blocking sync work off the event loop so it can't stall it.
            value = await asyncio.to_thread(operation.fn, **arguments)

        # 4. Store the payload under a unique, session-scoped reference.
        ref_id = f"{context.session_id}__{uuid.uuid4().hex}"
        context.put(ref_id, value)
        return ref_id, value

    # ── sync wrapper ─────────────────────────────────────────────────────
    def execute(self, tool_call: ToolCall, context: SessionContext) -> tuple[str, Any]:
        """Synchronous entry point.

        Plain sync operations run inline (unchanged original behavior).
        Async/orchestrator operations are driven to completion via
        :func:`asyncio.run`. Calling this from inside an already-running event
        loop raises; use :meth:`aexecute` there.
        """
        operation = self.registry.get_operation(tool_call.operation_id)
        if not (operation.is_async or operation.is_orchestrator):
            # Fast path: keep the original inline behavior for sync ops.
            validate_tool_call(tool_call, self.registry)
            resolver = ReferenceResolver(context)
            arguments = resolver.resolve_arguments(tool_call.arguments)
            value = operation.fn(**arguments)
            ref_id = f"{context.session_id}__{uuid.uuid4().hex}"
            context.put(ref_id, value)
            return ref_id, value

        return _run_coro(self.aexecute(tool_call, context))

    # ── internal: low-level sub-operation call (no resolve, no store) ─────
    async def _call_operation(self, operation_id: str, kwargs: dict[str, Any]) -> Any:
        """Run an operation's callable directly, awaiting/offloading as needed.

        Used by orchestrators for per-item sub-calls. Arguments are treated as
        final literal values: no reference resolution and no session storage.
        """
        operation = self.registry.get_operation(operation_id)
        if operation.is_async:
            return await operation.fn(**kwargs)
        return await asyncio.to_thread(operation.fn, **kwargs)


def _run_coro(coro):
    """Run *coro* to completion, refusing to nest inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise RuntimeError(
        "CoreEngine.execute() cannot drive an async/orchestrator operation from "
        "within a running event loop; await CoreEngine.aexecute() instead."
    )
