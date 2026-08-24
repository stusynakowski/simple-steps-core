"""example_server.py — declare tools, then serve them with one command.

Run it::

    python -m pip install -e ".[api]"
    simple-steps-core-server example_server.py

This file only declares tools (and an optional CONFIG). The
``simple-steps-core-server`` command imports it, adds the built-in orchestrators
(map/filter/expand/collapse), and serves:

    GET  /tools   — the palette (id, description, JSON Schema)
    POST /call    — run one tool: {"operation_id": "add", "arguments": {...}}
    POST /run     — run a workflow: {"steps": [ ...StepSpec... ]}
"""

from simple_steps_core import register_operation


@register_operation("add", description="Add two numbers.")
def add(a: int, b: int) -> int:
    return a + b


@register_operation("make_list", description="Create the list [0, 1, ..., n-1].")
def make_list(n: int) -> list[int]:
    return list(range(n))


@register_operation("square", description="Square a number.")
def square(x: int) -> int:
    return x * x


# Optional server configuration (every key is optional).
CONFIG = {
    "title": "My Tools",
    "host": "127.0.0.1",
    "port": 8000,
    # "orchestrators": True,   # add map/filter/expand/collapse (default True)
    # "freeze": True,          # lock the registry after loading (default True)
}

# Optional runtime resources injected into tools that declare `Resource()`:
# RESOURCES = {"db": lambda: connect_db()}

