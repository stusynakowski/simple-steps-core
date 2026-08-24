"""
Session snapshot & payload codecs
=================================

``Workflow.to_json`` persists only *structure* (steps/formulas). This module
adds full-session export/import: the step structure **plus** the out-of-band
payloads held in :class:`SessionContext`, bundled into one serializable
:class:`SessionSnapshot` you can store in a database or hand to another worker.

Payloads are encoded through a :class:`CodecRegistry`:

  * JSON-native values pass through as ``"json"``.
  * Pydantic models (e.g. :class:`MapResult`) round-trip with full type
    fidelity as ``"pydantic"`` (class path + ``model_dump``).
  * Anything else (DataFrames, custom objects) needs a registered codec keyed
    by type; otherwise export raises a clear :class:`SnapshotError` rather than
    silently pickling, which would be an arbitrary-code-execution risk on load.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from typing import Any

from pydantic import BaseModel, Field

from ..domain.models import Cell, Shape, Step, StepOutput

_JSON_SCALARS = (type(None), bool, int, float, str)


class SnapshotError(RuntimeError):
    """Raised when a payload cannot be encoded or decoded for a snapshot."""


@runtime_checkable
class StoreBackend(Protocol):
    """Minimal storage backend used by session contexts."""

    def put(self, ref_id: str, value: Any) -> None: ...

    def get(self, ref_id: str) -> Any: ...

    def has(self, ref_id: str) -> bool: ...

    def items(self) -> Iterable[tuple[str, Any]]: ...


@dataclass
class InMemoryStore:
    """Default in-process store backend."""

    data: dict[str, Any] = field(default_factory=dict)

    def put(self, ref_id: str, value: Any) -> None:
        self.data[ref_id] = value

    def get(self, ref_id: str) -> Any:
        return self.data.get(ref_id)

    def has(self, ref_id: str) -> bool:
        return ref_id in self.data

    def items(self) -> Iterable[tuple[str, Any]]:
        return self.data.items()


def _is_jsonable(value: Any) -> bool:
    """Best-effort check that *value* is composed only of JSON-native types."""
    if isinstance(value, _JSON_SCALARS):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_jsonable(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_jsonable(v) for k, v in value.items())
    return False


def _import_symbol(path: str):
    """Import a ``"module:Qualname"`` symbol path back to the object."""
    module_name, _, qualname = path.partition(":")
    obj: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, _JSON_SCALARS):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)


def _cell(row_id: int | str, column_id: str, value: Any) -> Cell:
    safe_value = _json_safe(value)
    return Cell(
        row_id=str(row_id),
        column_id=str(column_id),
        value=safe_value,
        display_value="" if value is None else str(value),
    )


def _columns_for_rows(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            column = str(key)
            if column not in seen:
                seen.add(column)
                columns.append(column)
    return columns


def _dataframe_shape(value: Any) -> Shape | None:
    if not hasattr(value, "columns"):
        return None
    try:
        rows = len(value)
        columns = [str(column) for column in value.columns]
    except Exception:
        return None
    return Shape(kind="dataframe", rows=rows, columns=columns, value_type=type(value).__name__)


def _generic_shape(value: Any) -> Shape:
    dataframe_shape = _dataframe_shape(value)
    if dataframe_shape is not None:
        return dataframe_shape
    if value is None:
        return Shape(kind="raw", rows=0, columns=[], value_type="NoneType")
    if isinstance(value, dict):
        return Shape(kind="raw", rows=1, columns=[str(k) for k in value], value_type="dict")
    if isinstance(value, list):
        if not value:
            return Shape(kind="raw", rows=0, columns=[], value_type="list")
        if all(isinstance(row, dict) for row in value):
            return Shape(kind="raw", rows=len(value), columns=_columns_for_rows(value), value_type="list")
        return Shape(kind="raw", rows=len(value), columns=["value"], value_type="list")
    if isinstance(value, BaseModel):
        data = value.model_dump(mode="json")
        return Shape(kind="raw", rows=1, columns=[str(k) for k in data], value_type=type(value).__name__)
    return Shape(kind="raw", rows=1, columns=["value"], value_type=type(value).__name__)


def _dataframe_view(value: Any, offset: int, limit: int) -> list[Cell] | None:
    if not hasattr(value, "columns") or not hasattr(value, "iloc"):
        return None
    try:
        page = value.iloc[offset : offset + limit]
        rows = page.to_dict(orient="records")
    except Exception:
        return None
    cells: list[Cell] = []
    for row_index, row in enumerate(rows, start=offset):
        for column in value.columns:
            cells.append(_cell(row_index, str(column), row.get(column)))
    return cells


def _generic_view(value: Any, offset: int = 0, limit: int = 50) -> list[Cell]:
    dataframe_view = _dataframe_view(value, offset, limit)
    if dataframe_view is not None:
        return dataframe_view
    if value is None or limit <= 0:
        return []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return [_cell(0, str(key), item) for key, item in value.items()] if offset == 0 else []
    if isinstance(value, list):
        page = value[offset : offset + limit]
        if all(isinstance(row, dict) for row in value):
            columns = _columns_for_rows(value)
            cells: list[Cell] = []
            for row_index, row in enumerate(page, start=offset):
                for column in columns:
                    cells.append(_cell(row_index, column, row.get(column)))
            return cells
        return [_cell(row_index, "value", item) for row_index, item in enumerate(page, start=offset)]
    return [_cell(0, "value", value)] if offset == 0 else []


class CodecRegistry:
    """Maps Python values to/from serializable payload envelopes.

    Register custom codecs for non-JSON types by name and Python type::

        codecs.register("dataframe", pd.DataFrame, encode_df, decode_df)
    """

    def __init__(self) -> None:
        # name -> (type, encode, decode, shape, to_view)
        self._codecs: dict[
            str,
            tuple[
                type,
                Callable[[Any], Any],
                Callable[[Any], Any],
                Callable[[Any], Shape],
                Callable[[Any, int, int], list[Cell]],
            ],
        ] = {}

    def register(
        self,
        name: str,
        type_: type,
        encode: Callable[[Any], Any],
        decode: Callable[[Any], Any],
        *,
        shape: Callable[[Any], Shape] | None = None,
        to_view: Callable[[Any, int, int], list[Cell]] | None = None,
    ) -> None:
        self._codecs[name] = (
            type_,
            encode,
            decode,
            shape or _generic_shape,
            to_view or _generic_view,
        )

    def encode(self, value: Any) -> tuple[str, Any]:
        """Return ``(encoding, data)`` for *value*."""
        for name, (type_, enc, _dec, _shape, _to_view) in self._codecs.items():
            if isinstance(value, type_):
                return name, enc(value)
        if isinstance(value, BaseModel):
            cls = type(value)
            return "pydantic", {
                "cls": f"{cls.__module__}:{cls.__qualname__}",
                "data": value.model_dump(mode="json"),
            }
        if _is_jsonable(value):
            return "json", value
        raise SnapshotError(
            f"No codec for value of type {type(value).__name__!r}. Register a "
            f"codec via CodecRegistry.register(...) to include it in a snapshot."
        )

    def codec_name_for(self, value: Any) -> str | None:
        """Return the codec name that *would* encode *value*, without encoding it.

        Returns ``None`` when no codec applies (the value is ephemeral and will
        be omitted from snapshots), so callers can classify data cheaply.
        """
        for name, (type_, _enc, _dec, _shape, _to_view) in self._codecs.items():
            if isinstance(value, type_):
                return name
        if isinstance(value, BaseModel):
            return "pydantic"
        if _is_jsonable(value):
            return "json"
        return None

    def shape(self, value: Any) -> Shape:
        """Return lightweight metadata for *value*."""
        for type_, _enc, _dec, shape, _to_view in self._codecs.values():
            if isinstance(value, type_):
                return shape(value)
        return _generic_shape(value)

    def to_view(self, value: Any, offset: int = 0, limit: int = 50) -> list[Cell]:
        """Return a paginated, JSON-safe cell view for *value*."""
        offset = max(offset, 0)
        limit = max(limit, 0)
        for type_, _enc, _dec, _shape, to_view in self._codecs.values():
            if isinstance(value, type_):
                return to_view(value, offset, limit)
        return _generic_view(value, offset, limit)

    def decode(self, encoding: str, data: Any) -> Any:
        """Reconstruct a value from ``(encoding, data)``."""
        if encoding in self._codecs:
            return self._codecs[encoding][2](data)
        if encoding == "pydantic":
            cls = _import_symbol(data["cls"])
            return cls.model_validate(data["data"])
        if encoding == "json":
            return data
        raise SnapshotError(f"Unknown payload encoding: {encoding!r}")


# A process-wide default registry. Extend it at startup for custom types.
DEFAULT_CODECS = CodecRegistry()


# ─────────────────────────────────────────────────────────────────────────
# Snapshot models
# ─────────────────────────────────────────────────────────────────────────
class PayloadEnvelope(BaseModel):
    """One stored payload: its session ref plus an encoded representation."""

    ref: str
    encoding: str
    data: Any = None


class SessionSnapshot(BaseModel):
    """A complete, serializable picture of a workflow run.

    Structure (steps/formulas/status) and data (payloads) travel together, so a
    snapshot can be stored and later restored to resume or inspect a run.
    """

    version: int = 1
    session_id: str
    steps: list[Step] = Field(default_factory=list)
    step_to_ref: dict[str, str] = Field(default_factory=dict)
    payloads: list[PayloadEnvelope] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data: str) -> "SessionSnapshot":
        return cls.model_validate_json(data)


def _lightweight_step(step: Step) -> Step:
    """Copy a step with inline payload stripped (real data lives in payloads)."""
    output = StepOutput(ref=step.output.ref, value=None, kind=step.output.kind)
    return step.model_copy(update={"output": output})


def build_snapshot(
    session_id: str,
    steps: list[Step],
    outputs: dict[str, Any],
    step_to_ref: dict[str, str],
    codecs: CodecRegistry = DEFAULT_CODECS,
) -> SessionSnapshot:
    """Assemble a :class:`SessionSnapshot` from session state."""
    payloads: list[PayloadEnvelope] = []
    for ref, value in outputs.items():
        encoding, data = codecs.encode(value)
        payloads.append(PayloadEnvelope(ref=ref, encoding=encoding, data=data))
    return SessionSnapshot(
        session_id=session_id,
        steps=[_lightweight_step(s) for s in steps],
        step_to_ref=dict(step_to_ref),
        payloads=payloads,
    )


def restore_payloads(
    snapshot: SessionSnapshot, codecs: CodecRegistry = DEFAULT_CODECS
) -> dict[str, Any]:
    """Decode a snapshot's payloads back into a ``ref -> value`` mapping."""
    return {env.ref: codecs.decode(env.encoding, env.data) for env in snapshot.payloads}
