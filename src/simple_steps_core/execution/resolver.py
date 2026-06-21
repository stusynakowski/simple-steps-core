"""
Reference resolution
====================

Before an operation runs, any argument that is a reference token (``step1``,
``step1.total``) must be swapped for the real value produced by that step.
The :class:`ReferenceResolver` does exactly that, reading payloads out of a
:class:`SessionContext`. Grammar lives in ``domain/references.py``; this is
the part that needs live session state, so it belongs in the execution layer.
"""

from __future__ import annotations

from typing import Any

from ..domain.references import is_reference, split_reference
from .context import SessionContext


class ReferenceResolver:
    """Resolves reference tokens in arguments against a session's outputs."""

    def __init__(self, context: SessionContext):
        self.context = context

    def resolve_value(self, value: Any) -> Any:
        """
        Resolve a single argument value.

        Non-references pass through unchanged. A reference like ``step1`` is
        replaced by that step's payload; ``step1.total`` additionally pulls
        the ``total`` field/key from that payload.
        """
        if not is_reference(value):
            return value

        step_id, field = split_reference(value)
        if self.context.ref_for_step(step_id) is None:
            raise KeyError(f"Reference to unknown or unrun step: {step_id!r}")

        payload = self.context.value_for_step(step_id)
        if field is None:
            return payload
        return self._get_field(payload, field)

    def resolve_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Resolve every value in an arguments mapping."""
        return {name: self.resolve_value(value) for name, value in arguments.items()}

    @staticmethod
    def _get_field(payload: Any, field: str) -> Any:
        """Read *field* from a payload, supporting mappings and attributes."""
        if isinstance(payload, dict):
            return payload[field]
        return getattr(payload, field)
