"""A test helper: the tools a test module defines at its top level, by name.

@tool registers nothing (K24), so loading a saved workflow by name needs the
tools passed in. Tests that used to rely on the process-wide registry pass
``module_tools(globals())`` instead: it reads the module's tools each time, so
tools defined further down the file are included.
"""

from __future__ import annotations

from collections.abc import Mapping

from simple_steps_core.catalog import ToolHandle


class module_tools(Mapping):
    def __init__(self, scope: dict):
        self._scope = scope

    def _tools(self) -> dict:
        return {v.id: v.fn for v in self._scope.values() if isinstance(v, ToolHandle)}

    def __getitem__(self, key):
        return self._tools()[key]

    def __iter__(self):
        return iter(self._tools())

    def __len__(self):
        return len(self._tools())
