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

from ..domain.models import Cell, Shape
from .data_store import DataEntry, DataStore
from .resources import ResourceContainer
from .session_io import DEFAULT_CODECS, CodecRegistry


@dataclass
class SessionContext:
    session_id: str
    codecs: CodecRegistry = field(default_factory=lambda: DEFAULT_CODECS)
    resources: ResourceContainer = field(default_factory=ResourceContainer)
    data: DataStore = field(init=False)

    def __post_init__(self) -> None:
        self.data = DataStore(self.codecs)

    # ── back-compat indexes (mutable, backed by the data store) ──────────
    @property
    def outputs(self) -> dict[str, Any]:
        """ref -> value (kept mutable so snapshot import can ``update`` it)."""
        return self.data.values

    @property
    def step_to_ref(self) -> dict[str, str]:
        """step_id -> ref (kept mutable for snapshot import)."""
        return self.data.by_step

    # ── payload store ────────────────────────────────────────────────────
    def put(self, ref_id: str, value: Any) -> None:
        """Store a payload under an output reference."""
        self.data.put(ref_id, value)

    def get(self, ref_id: str) -> Any:
        """Fetch a payload by its output reference (None if absent)."""
        return self.data.get(ref_id)

    def has(self, ref_id: str) -> bool:
        return self.data.has(ref_id)

    def owns(self, ref_id: str) -> bool:
        """True when this context owns a reference."""
        return self.data.has(ref_id)

    def get_meta(self, ref_id: str) -> Shape:
        """Return shape metadata for a stored payload."""
        if not self.data.has(ref_id):
            raise KeyError(f"Unknown reference: {ref_id!r}")
        return self.data.shape(ref_id)

    def get_view(self, ref_id: str, offset: int = 0, limit: int = 50) -> list[Cell]:
        """Return a paginated, JSON-safe cell view for a stored payload."""
        if not self.data.has(ref_id):
            raise KeyError(f"Unknown reference: {ref_id!r}")
        return self.data.preview(ref_id, offset=offset, limit=limit)

    # ── step → ref index ─────────────────────────────────────────────────
    def bind_step(self, step_id: str, ref_id: str) -> None:
        """Record that *step_id* produced the payload stored at *ref_id*."""
        self.data.bind_step(step_id, ref_id)

    def ref_for_step(self, step_id: str) -> str | None:
        """Return the output reference a step produced, if any."""
        return self.data.ref_for_step(step_id)

    def value_for_step(self, step_id: str) -> Any:
        """Convenience: fetch a step's payload directly (None if absent)."""
        return self.data.value_for_step(step_id)

    # ── rich, data-centric access ────────────────────────────────────────
    def entry(self, ref_id: str) -> DataEntry | None:
        """Return the full metadata record for a stored payload."""
        return self.data.entry(ref_id)

    def entry_for_step(self, step_id: str) -> DataEntry | None:
        """Return the metadata record a step produced, if any."""
        return self.data.entry_for_step(step_id)

    def entries(self) -> list[DataEntry]:
        """All produced outputs as metadata records (for UI listing)."""
        return self.data.entries()
