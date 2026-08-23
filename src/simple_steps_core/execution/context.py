"""
Session context (the payload store)
==================================

Domain models never carry heavy data. Instead, produced values (DataFrames,
lists, API responses) live here, in a per-session store, addressed by an
*output reference*. The context keeps two indexes:

  * ``outputs``      : output_ref  -> value        (the real payload)
  * ``step_to_ref``  : step_id     -> output_ref   (where a step's data went)

This separation lets a Step stay a small, serializable record while its data
stays out-of-band and session-scoped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .session_io import DEFAULT_CODECS, CodecRegistry
from ..domain.models import Cell, Shape


@dataclass
class SessionContext:
    session_id: str
    outputs: dict[str, Any] = field(default_factory=dict)      # ref -> value
    step_to_ref: dict[str, str] = field(default_factory=dict)  # step_id -> ref
    codecs: CodecRegistry = field(default_factory=lambda: DEFAULT_CODECS)

    # ── payload store ────────────────────────────────────────────────────
    def put(self, ref_id: str, value: Any) -> None:
        """Store a payload under an output reference."""
        self.outputs[ref_id] = value

    def get(self, ref_id: str) -> Any:
        """Fetch a payload by its output reference (None if absent)."""
        return self.outputs.get(ref_id)

    def has(self, ref_id: str) -> bool:
        return ref_id in self.outputs

    def owns(self, ref_id: str) -> bool:
        """True when this context owns a reference."""
        return self.has(ref_id)

    def get_meta(self, ref_id: str) -> Shape:
        """Return shape metadata for a stored payload."""
        if not self.owns(ref_id):
            raise KeyError(f"Unknown reference: {ref_id!r}")
        return self.codecs.shape(self.outputs[ref_id])

    def get_view(self, ref_id: str, offset: int = 0, limit: int = 50) -> list[Cell]:
        """Return a paginated, JSON-safe cell view for a stored payload."""
        if not self.owns(ref_id):
            raise KeyError(f"Unknown reference: {ref_id!r}")
        return self.codecs.to_view(self.outputs[ref_id], offset=offset, limit=limit)

    # ── step → ref index ─────────────────────────────────────────────────
    def bind_step(self, step_id: str, ref_id: str) -> None:
        """Record that *step_id* produced the payload stored at *ref_id*."""
        self.step_to_ref[step_id] = ref_id

    def ref_for_step(self, step_id: str) -> str | None:
        """Return the output reference a step produced, if any."""
        return self.step_to_ref.get(step_id)

    def value_for_step(self, step_id: str) -> Any:
        """Convenience: fetch a step's payload directly (None if absent)."""
        ref = self.step_to_ref.get(step_id)
        return self.outputs.get(ref) if ref is not None else None
