"""
Execution engine
================

The engine turns a :class:`ToolCall` into a real result. For each call it:

  1. validates the call against the registry,
  2. resolves any reference-token arguments against the session store,
  3. runs the underlying operation function, and
  4. stores the produced payload under a fresh output reference.

It returns ``(ref_id, value)`` so callers can either keep the lightweight
reference or use the value directly.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..domain.models import ToolCall
from ..operations.registry import OperationRegistry
from ..operations.validation import validate_tool_call
from .context import SessionContext
from .resolver import ReferenceResolver


class CoreEngine:
    def __init__(self, registry: OperationRegistry):
        self.registry = registry

    def execute(self, tool_call: ToolCall, context: SessionContext) -> tuple[str, Any]:
        """Validate, resolve, run, and store one tool call."""
        # 1. Tool-aware validation (operation exists, args fit its contract).
        validate_tool_call(tool_call, self.registry)

        # 2. Swap reference tokens for real upstream payloads.
        resolver = ReferenceResolver(context)
        arguments = resolver.resolve_arguments(tool_call.arguments)

        # 3. Run the underlying operation function.
        operation = self.registry.get_callable(tool_call.operation_id)
        value = operation(**arguments)

        # 4. Store the payload under a unique, session-scoped reference.
        ref_id = f"{context.session_id}__{uuid.uuid4().hex}"
        context.put(ref_id, value)
        return ref_id, value
