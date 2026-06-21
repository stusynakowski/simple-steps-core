"""Tests for the reference grammar helpers (domain layer)."""

from simple_steps_core.domain.references import is_reference, split_reference


def test_is_reference_accepts_step_tokens():
    assert is_reference("step1")
    assert is_reference("step_2")
    assert is_reference("step1.total")
    assert is_reference("step3.rows[0]")


def test_is_reference_rejects_non_references():
    assert not is_reference("data.csv")
    assert not is_reference("hello")
    assert not is_reference("")
    assert not is_reference(42)


def test_split_reference_without_field():
    assert split_reference("step1") == ("step1", None)


def test_split_reference_with_field():
    assert split_reference("step1.total") == ("step1", "total")


def test_split_reference_ignores_bracket_indexer():
    assert split_reference("step1[0]") == ("step1", None)
