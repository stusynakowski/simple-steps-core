"""
Loader
======

Import a user's *tools file* — a plain Python script that declares tools with
``@register_tool`` / ``@register_tool`` (plus optional ``CONFIG`` /
``RESOURCES``). Running the module executes those decorators, registering the
tools on the shared ``REGISTRY``.

This is deliberately transport-agnostic: the optional FastAPI server
(:mod:`simple_steps_core.serving`) loads tools this way, and so can any other
host, without either requiring the other.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_tools_module(path: str | Path):
    """Import a user script by path, running its ``@register_tool`` calls."""
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"No such script: {path}")
    spec = importlib.util.spec_from_file_location("_simple_steps_user_tools", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # Let the script import sibling modules relative to its own folder.
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    return module
