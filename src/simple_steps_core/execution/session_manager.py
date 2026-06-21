"""
Session manager
===============

Nothing in the execution layer is implicitly shared, which is what makes
per-user isolation safe: give every logical run its **own**
:class:`SessionContext` and never share one across users or requests.

:class:`SessionManager` centralizes that discipline. It hands out a context per
``session_id`` and a per-session :class:`asyncio.Lock` so writes within one
session are serialized, while different users' sessions proceed concurrently.

Recommended ``session_id`` convention (kept collision-free by the engine's
``{session_id}__{uuid}`` ref scheme)::

    session_id = make_session_id(user_id, workflow_id, run_id)
"""

from __future__ import annotations

import asyncio

from .context import SessionContext


def make_session_id(user_id: str, workflow_id: str, run_id: str) -> str:
    """Build a namespaced, user-scoped session id."""
    return f"{user_id}:{workflow_id}:{run_id}"


class SessionManager:
    """Owns per-user :class:`SessionContext` instances and their locks."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionContext] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # Guards creation of per-session entries (not their payloads).
        self._registry_lock = asyncio.Lock()

    async def get_or_create(self, session_id: str) -> SessionContext:
        """Return the context for *session_id*, creating it on first use."""
        async with self._registry_lock:
            context = self._sessions.get(session_id)
            if context is None:
                context = SessionContext(session_id=session_id)
                self._sessions[session_id] = context
                self._locks[session_id] = asyncio.Lock()
            return context

    def lock(self, session_id: str) -> asyncio.Lock:
        """Return the write lock for an existing session.

        Use ``async with manager.lock(session_id):`` around a run to serialize
        mutations of that one session while other sessions run freely.
        """
        try:
            return self._locks[session_id]
        except KeyError as exc:
            raise KeyError(
                f"No session {session_id!r}; call get_or_create() first."
            ) from exc

    def get(self, session_id: str) -> SessionContext | None:
        return self._sessions.get(session_id)

    def discard(self, session_id: str) -> None:
        """Drop a finished session's context and lock to free memory."""
        self._sessions.pop(session_id, None)
        self._locks.pop(session_id, None)

    def __contains__(self, session_id: str) -> bool:
        return session_id in self._sessions
