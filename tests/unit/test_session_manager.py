"""Tests for registry freeze and the per-user SessionManager."""

import asyncio

import pytest

from simple_steps_core import (
    OperationRegistry,
    RegistryFrozenError,
    SessionManager,
    make_session_id,
)


def test_freeze_blocks_further_registration():
    registry = OperationRegistry()

    def op(x: int) -> int:
        return x

    registry.register("op", op)
    registry.freeze()
    assert registry.frozen is True

    with pytest.raises(RegistryFrozenError):
        registry.register("op2", op)


def test_make_session_id_is_namespaced():
    assert make_session_id("u1", "wf9", "run3") == "u1:wf9:run3"


def test_session_manager_isolates_users():
    async def scenario():
        manager = SessionManager()
        a = await manager.get_or_create(make_session_id("alice", "wf", "1"))
        b = await manager.get_or_create(make_session_id("bob", "wf", "1"))

        a.put("ref-a", 1)
        b.put("ref-b", 2)

        # Separate contexts: no cross-user bleed.
        assert a is not b
        assert a.get("ref-b") is None
        assert b.get("ref-a") is None

        # get_or_create is idempotent for the same id.
        a_again = await manager.get_or_create(a.session_id)
        assert a_again is a

    asyncio.run(scenario())


def test_session_manager_lock_requires_existing_session():
    manager = SessionManager()
    with pytest.raises(KeyError):
        manager.lock("missing")


def test_session_manager_discard_frees_session():
    async def scenario():
        manager = SessionManager()
        sid = make_session_id("u", "w", "r")
        await manager.get_or_create(sid)
        assert sid in manager
        manager.discard(sid)
        assert sid not in manager

    asyncio.run(scenario())
