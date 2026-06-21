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
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from ..domain.models import Step, StepOutput

_JSON_SCALARS = (type(None), bool, int, float, str)


class SnapshotError(RuntimeError):
    """Raised when a payload cannot be encoded or decoded for a snapshot."""


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


class CodecRegistry:
    """Maps Python values to/from serializable payload envelopes.

    Register custom codecs for non-JSON types by name and Python type::

        codecs.register("dataframe", pd.DataFrame, encode_df, decode_df)
    """

    def __init__(self) -> None:
        # name -> (type, encode, decode)
        self._codecs: dict[str, tuple[type, Callable[[Any], Any], Callable[[Any], Any]]] = {}

    def register(
        self,
        name: str,
        type_: type,
        encode: Callable[[Any], Any],
        decode: Callable[[Any], Any],
    ) -> None:
        self._codecs[name] = (type_, encode, decode)

    def encode(self, value: Any) -> tuple[str, Any]:
        """Return ``(encoding, data)`` for *value*."""
        for name, (type_, enc, _dec) in self._codecs.items():
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
