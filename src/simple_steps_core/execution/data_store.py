"""
Data store
==========

A data-centric replacement for the two loose dicts the session used to keep.
Every produced value is wrapped in a self-describing :class:`DataEntry` that
records its reference, origin step, kind, shape, and serialization codec, so
the UI and snapshot layers can reason about outputs without touching the raw
object.

The store keeps two indexes, exactly as before:

  * ``_values``  : ref     -> value      (the live payload)
  * ``_by_step`` : step_id -> ref        (where a step's output went)

plus ``_entries`` : ref -> DataEntry (the metadata sidecar).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..domain.models import Cell, Shape
from .session_io import CodecRegistry


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DataEntry:
    """A single step output plus everything the system knows about it."""

    ref: str
    value: Any
    step_id: str | None
    kind: str
    shape: Shape
    codec: str | None = None       # serialization codec name; None => ephemeral
    ephemeral: bool = False        # true => omitted from snapshots (recompute)
    created_at: datetime = field(default_factory=_utcnow)


class DataStore:
    """Holds all step outputs as :class:`DataEntry` records."""

    def __init__(self, codecs: CodecRegistry):
        self._codecs = codecs
        self._values: dict[str, Any] = {}
        self._by_step: dict[str, str] = {}
        self._entries: dict[str, DataEntry] = {}

    # ── write ────────────────────────────────────────────────────────────
    def put(self, ref_id: str, value: Any, *, step_id: str | None = None) -> DataEntry:
        """Store a payload and build its metadata entry."""
        self._values[ref_id] = value
        shape = self._codecs.shape(value)
        codec = self._codecs.codec_name_for(value)
        entry = DataEntry(
            ref=ref_id,
            value=value,
            step_id=step_id,
            kind=shape.value_type or shape.kind,
            shape=shape,
            codec=codec,
            ephemeral=codec is None,
        )
        self._entries[ref_id] = entry
        if step_id is not None:
            self._by_step[step_id] = ref_id
        return entry

    def bind_step(self, step_id: str, ref_id: str) -> None:
        """Record that *step_id* produced the payload at *ref_id*."""
        self._by_step[step_id] = ref_id
        entry = self._entries.get(ref_id)
        if entry is not None and entry.step_id is None:
            entry.step_id = step_id

    # ── read by reference ────────────────────────────────────────────────
    def get(self, ref_id: str) -> Any:
        return self._values.get(ref_id)

    def has(self, ref_id: str) -> bool:
        return ref_id in self._values

    def entry(self, ref_id: str) -> DataEntry | None:
        return self._entries.get(ref_id)

    def entries(self) -> list[DataEntry]:
        return list(self._entries.values())

    # ── read by step ─────────────────────────────────────────────────────
    def ref_for_step(self, step_id: str) -> str | None:
        return self._by_step.get(step_id)

    def value_for_step(self, step_id: str) -> Any:
        ref = self._by_step.get(step_id)
        return self._values.get(ref) if ref is not None else None

    def entry_for_step(self, step_id: str) -> DataEntry | None:
        ref = self._by_step.get(step_id)
        return self._entries.get(ref) if ref is not None else None

    # ── data-centric helpers ─────────────────────────────────────────────
    def shape(self, ref_id: str) -> Shape:
        return self._codecs.shape(self._values[ref_id])

    def preview(self, ref_id: str, offset: int = 0, limit: int = 50) -> list[Cell]:
        return self._codecs.to_view(self._values[ref_id], offset=offset, limit=limit)

    # ── raw indexes (kept mutable for back-compat with snapshot import) ──
    @property
    def values(self) -> dict[str, Any]:
        return self._values

    @property
    def by_step(self) -> dict[str, str]:
        return self._by_step
