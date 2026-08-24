"""The whole server in a few lines: define tools -> get a running API.

Run it::

    python -m pip install -e ".[api]"
    uvicorn examples.simple_server.app:app --reload   # http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from simple_steps_core import REGISTRY, CoreEngine, register_orchestrators

from . import tools  # noqa: F401  — importing registers the tools on REGISTRY
from .server import build_app

# Add the built-in orchestrators (map/filter/expand/collapse), then lock it.
register_orchestrators(REGISTRY)
REGISTRY.freeze()

app = build_app(REGISTRY, CoreEngine(REGISTRY))
