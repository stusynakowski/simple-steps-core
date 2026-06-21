"""Demo operations and registry setup for the example API server.

In a real backend these would live in your own package and be loaded as packs.
They are intentionally simple so the server is runnable with no extra services.
"""

from __future__ import annotations

import asyncio

from simple_steps_core import CoreEngine, OperationRegistry, register_orchestrators


def make_list(n: int) -> list[int]:
    """Create the list ``[0, 1, ..., n-1]``."""
    return list(range(n))


def total(data: list[int]) -> int:
    """Sum a list of integers."""
    return sum(data)


def double(x: int) -> int:
    """Return ``x * 2`` (used as a per-item op for orchestrators)."""
    return x * 2


def is_even(x: int) -> bool:
    """Predicate used by ``filter``."""
    return x % 2 == 0


async def slow_square(x: int) -> int:
    """An async per-item op to demonstrate concurrency inside ``map``."""
    await asyncio.sleep(0.05)
    if x == 7:
        raise ValueError("unlucky 7")
    return x * x


def build_registry() -> OperationRegistry:
    """Register demo operations + built-in orchestrators, then freeze.

    Freezing after startup makes the registry read-only, which keeps concurrent
    request handling safe without locks.
    """
    registry = OperationRegistry()
    registry.register("make_list", make_list, description="Create [0..n-1]")
    registry.register("total", total, description="Sum a list of ints")
    registry.register("double", double, description="Multiply an int by 2")
    registry.register("is_even", is_even, description="True when an int is even")
    registry.register("slow_square", slow_square, description="Async square (fails on 7)")
    register_orchestrators(registry)
    registry.freeze()
    return registry


# Built once at import time; shared read-only across requests.
REGISTRY = build_registry()
ENGINE = CoreEngine(REGISTRY)
