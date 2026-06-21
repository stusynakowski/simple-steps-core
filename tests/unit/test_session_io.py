"""Tests for full-session snapshot export/import and the codec registry."""

import pytest

from simple_steps_core import (
    CodecRegistry,
    CoreEngine,
    MapResult,
    OperationRegistry,
    SessionSnapshot,
    SnapshotError,
    Workflow,
    register_orchestrators,
)


def _registry():
    registry = OperationRegistry()

    def make_list(n: int) -> list[int]:
        return list(range(n))

    def double(x: int) -> int:
        return x * 2

    registry.register("make_list", make_list)
    registry.register("double", double)
    register_orchestrators(registry)
    return registry


def _built_workflow():
    engine = CoreEngine(_registry())
    wf = Workflow(engine, session_id="snap")
    wf["step_nums"] = "=make_list(n=4)"
    wf["step_mapped"] = '=map(over="step_nums", op="double")'
    wf.run()
    return engine, wf


def test_snapshot_roundtrip_restores_structure_and_payloads():
    engine, wf = _built_workflow()
    data = wf.export_session_json()

    restored = Workflow.import_session_json(data, engine)

    # Structure preserved.
    assert [s.step_id for s in restored.steps] == ["step_nums", "step_mapped"]
    # Payloads restored into the session.
    assert restored.context.value_for_step("step_nums") == [0, 1, 2, 3]
    # Pydantic payloads round-trip with full type fidelity.
    mapped = restored.context.value_for_step("step_mapped")
    assert isinstance(mapped, MapResult)
    assert mapped.ok == [0, 2, 4, 6]


def test_snapshot_reattaches_inline_step_value():
    engine, wf = _built_workflow()
    restored = Workflow.import_session_json(wf.export_session_json(), engine)
    assert restored["step_nums"].output.value == [0, 1, 2, 3]


def test_snapshot_json_is_stable_model():
    _engine, wf = _built_workflow()
    snapshot = wf.export_session()
    assert isinstance(snapshot, SessionSnapshot)
    reparsed = SessionSnapshot.from_json(snapshot.to_json())
    assert reparsed.session_id == "snap"
    assert {e.ref for e in reparsed.payloads} == set(wf.context.outputs)


def test_unencodable_payload_raises_clear_error():
    codecs = CodecRegistry()

    class Opaque:
        pass

    with pytest.raises(SnapshotError):
        codecs.encode(Opaque())


def test_custom_codec_roundtrip():
    codecs = CodecRegistry()

    class Money:
        def __init__(self, cents: int):
            self.cents = cents

    codecs.register("money", Money, lambda m: m.cents, lambda c: Money(c))
    encoding, data = codecs.encode(Money(150))
    assert encoding == "money"
    assert data == 150
    assert codecs.decode("money", data).cents == 150
