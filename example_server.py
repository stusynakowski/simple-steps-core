"""example_server.py — declare tools, then serve them by running this file.

Run it::

    python -m pip install -e ".[api]"
    python example_server.py

This file declares tools (and an optional CONFIG), then ``Server().run()`` adds
the built-in orchestrators (map/filter/expand/collapse) and serves:

    GET  /tools   — the palette (id, description, JSON Schema)
    POST /call    — run one tool: {"operation_id": "add", "arguments": {...}}
    POST /run     — run a workflow: {"steps": [ ...Operation... ]}
"""

from simple_steps_core import register_tool
from simple_steps_core.serving import Server


@register_tool("add", description="Add two numbers.")
def add(a: int, b: int) -> int:
    return a + b


@register_tool("make_list", description="Create the list [0, 1, ..., n-1].")
def make_list(n: int) -> list[int]:
    return list(range(n))


@register_tool("square", description="Square a number.")
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


if __name__ == "__main__":
    Server().run()

