"""Your tools — just decorate plain functions.

Everything registered here becomes callable through the API in ``app.py``.
This is the only file you edit to add capabilities.
"""

from __future__ import annotations

from simple_steps_core import register_tool


@register_tool("add", description="Add two numbers.")
def add(a: int, b: int) -> int:
    return a + b


@register_tool("make_list", description="Create the list [0, 1, ..., n-1].")
def make_list(n: int) -> list[int]:
    return list(range(n))


@register_tool("square", description="Square a number.")
def square(x: int) -> int:
    return x * x


@register_tool("to_upper", description="Uppercase a string.")
def to_upper(text: str) -> str:
    return text.upper()
