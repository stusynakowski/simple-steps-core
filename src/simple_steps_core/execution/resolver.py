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

from ..domain.references import is_reference, parse_reference
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

        step_id, accessors = parse_reference(value)
        if self.context.ref_for_step(step_id) is None:
            raise KeyError(f"Reference to unknown or unrun step: {step_id!r}")

        payload = self.context.value_for_step(step_id)
        for position, accessor in enumerate(accessors):
            payload = self._walk(payload, accessor, value, accessors[:position])
        return payload

    def resolve_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Resolve every value in an arguments mapping."""
        return {name: self.resolve_value(value) for name, value in arguments.items()}

    @staticmethod
    def _walk(payload: Any, accessor: str | int, token: str, walked: list) -> Any:
        """Take one step along a reference path, failing loudly when it cannot.

        An accessor that does not fit the payload is a bug in the workflow, so
        it raises here naming the token and how far it got. Silently handing
        back the un-indexed payload — the old behavior for brackets — turned a
        typo into a wrong answer further downstream.
        """
        reached = f"{token!r}" + (f" (after {walked})" if walked else "")
        if isinstance(accessor, int):
            try:
                return payload[accessor]
            except (IndexError, KeyError) as exc:
                raise IndexError(
                    f"Index [{accessor}] is out of range for {reached}: "
                    f"the value is a {type(payload).__name__} of length "
                    f"{_length_of(payload)}."
                ) from exc
            except TypeError as exc:
                raise TypeError(
                    f"Cannot index {reached} with [{accessor}]: the value is a "
                    f"{type(payload).__name__}, which is not indexable."
                ) from exc

        if isinstance(payload, dict):
            if accessor not in payload:
                raise KeyError(
                    f"{accessor!r} is not a key of {reached}: available keys are "
                    f"{sorted(map(str, payload))[:10]}."
                )
            return payload[accessor]
        try:
            return getattr(payload, accessor)
        except AttributeError as exc:
            raise AttributeError(
                f"{accessor!r} is not a field of {reached}: the value is a "
                f"{type(payload).__name__}."
            ) from exc


def _length_of(payload: Any) -> str:
    try:
        return str(len(payload))
    except TypeError:
        return "unknown"
