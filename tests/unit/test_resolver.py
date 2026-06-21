"""Tests for reference resolution against a session context."""

import pytest

from simple_steps_core.execution.context import SessionContext
from simple_steps_core.execution.resolver import ReferenceResolver


def test_resolves_plain_step_reference():
    context = SessionContext(session_id="s")
    context.put("ref-1", [1, 2, 3])
    context.bind_step("step1", "ref-1")

    resolver = ReferenceResolver(context)
    assert resolver.resolve_value("step1") == [1, 2, 3]


def test_resolves_dotted_field_on_dict_payload():
    context = SessionContext(session_id="s")
    context.put("ref-1", {"total": 42})
    context.bind_step("step1", "ref-1")

    resolver = ReferenceResolver(context)
    assert resolver.resolve_value("step1.total") == 42


def test_non_reference_passes_through():
    resolver = ReferenceResolver(SessionContext(session_id="s"))
    assert resolver.resolve_value("data.csv") == "data.csv"
    assert resolver.resolve_value(7) == 7


def test_unknown_step_reference_raises():
    resolver = ReferenceResolver(SessionContext(session_id="s"))
    with pytest.raises(KeyError):
        resolver.resolve_value("step1")


def test_resolve_arguments_mixes_literals_and_references():
    context = SessionContext(session_id="s")
    context.put("ref-1", [10])
    context.bind_step("step1", "ref-1")

    resolver = ReferenceResolver(context)
    resolved = resolver.resolve_arguments({"data": "step1", "limit": 5})
    assert resolved == {"data": [10], "limit": 5}
