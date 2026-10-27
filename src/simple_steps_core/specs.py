"""Specs: the saved form of each object, as plain frozen values.

A spec is everything needed to produce the same output, assuming what it
references holds the same data. It never holds output data
(docs/design/object-model.md §3). Every object has one: ``k.spec``,
``k.workflow.spec``, ``k.step("f").spec``, ``k.catalog.spec``, and a
resource's ``ResourceSpec``. ``to_dict()`` is the spec as JSON-ready data;
``Kernel.from_spec(spec, catalog)`` builds it back.

``extras`` hold the app's additions by namespace. Core saves and loads them,
and never reads them.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


def _plain(value: Any) -> Any:
    """A deep copy, so a spec doesn't change when its object does."""
    return copy.deepcopy(value)


@dataclass(frozen=True)
class ResourceSpec:
    """A resource: its name, its type's name, and the literal settings to build it."""

    name: str
    type: str
    settings: dict
    extras: dict = field(default_factory=dict)
    source: str = "defined"

    def to_dict(self) -> dict:
        out = {"source": self.source, "type": self.type,
               "settings": _plain(self.settings)}
        if self.extras:
            out["extras"] = _plain(self.extras)
        return out


@dataclass(frozen=True)
class StepSpec:
    """A step: its name and its operation as data."""

    name: str
    operation: dict
    extras: dict = field(default_factory=dict)
    #: For a step declared as a literal (``k["x"] = [3, 1, 2]``), the value, as
    #: ``{"value": <tagged JSON>}``: a literal is the step's recipe. None for
    #: every other step, and for values that aren't literals (a DataFrame is
    #: data, and isn't saved).
    literal: dict | None = None

    def to_dict(self) -> dict:
        out = {"name": self.name, "operation": _plain(self.operation)}
        if self.literal is not None:
            out["literal"] = _plain(self.literal)
        if self.extras:
            out["extras"] = _plain(self.extras)
        return out


@dataclass(frozen=True)
class WorkflowSpec:
    """A workflow: its step specs in order, and its resource specs."""

    steps: tuple[StepSpec, ...]
    resources: tuple[ResourceSpec, ...] = ()
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        from .values import FORMAT_VERSION
        out: dict = {"version": FORMAT_VERSION,
                     "steps": [s.to_dict() for s in self.steps]}
        if self.resources:
            out["resources"] = {r.name: r.to_dict() for r in self.resources}
        if self.extras:
            out["extras"] = _plain(self.extras)
        return out


@dataclass(frozen=True)
class CatalogSpec:
    """A catalog: the names of the entries it allows, and each tool's extras.

    It names code; it never contains it. Tool hashes join it with K20.
    """

    tools: dict
    resource_types: tuple[str, ...]
    builtins: tuple[str, ...]
    modifiers: tuple[str, ...]
    combines: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"tools": _plain(self.tools), "resource_types": list(self.resource_types),
                "builtins": list(self.builtins), "modifiers": list(self.modifiers),
                "combines": list(self.combines)}


@dataclass(frozen=True)
class KernelSpec:
    """A kernel: its workflow spec and its catalog spec — everything needed to
    reproduce the workflow with that set of tools."""

    workflow: WorkflowSpec
    catalog: CatalogSpec

    def to_dict(self) -> dict:
        return {**self.workflow.to_dict(), "catalog": self.catalog.to_dict()}
