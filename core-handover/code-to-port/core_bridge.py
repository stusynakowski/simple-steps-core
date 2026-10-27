"""
core_bridge.py — the seam between this app and ``simple_steps_core``
===================================================================

``simple_steps_core`` is the heart of the backend: it owns the tool registry,
the tool contracts (:class:`ToolDefinition` / :class:`ToolParam`), resources
and the engine. **This repo never edits core.** Where core cannot yet express
something we need, the gap is shimmed here and recorded in
``docs/core-proposals/008-core-changes.md``.

Every shim below is tagged with the proposal section that removes it::

    SHIM(core §C17)  grid: mod.table() hands the grid to the first
                     parameter, not the one typed DataFrame
    SHIM(core §C18)  grid.catalog()'s description is the docstring's first
                     line, not its first paragraph
    SHIM(core §G)    the engine's ToolDefinition.type has no 'step' member
                     (not asked: the engine is retiring)

When core lands one of those, delete the tagged block. Nothing else should
need to change — that is the point of keeping them in one file.

Core 9a86a0d closed §A, §B, §E, §J (``grid.tool_entry``), §K (``mod.table``),
§L (references in arguments), §M (``infer_verb`` on a bound method), §N
(``mod.auto``) and §O (``grid.check_modifier``); their shims are gone.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from simple_steps_core import register_tool as _core_register_tool

# `simple-steps-core` is declared as a git dependency, so an environment can
# end up with a core older than this app expects. Fail with the fix rather than
# a bare ImportError from four frames down: SIMPLE_STEPS/__init__ imports this
# module, so an older core otherwise makes the whole package unimportable and
# the traceback points here instead of at the install.
try:
    from simple_steps_core import REGISTRY, ResourceSpec
except ImportError as exc:  # pragma: no cover - environment-dependent
    import simple_steps_core as _core

    # `name_from` is the name that could not be imported; `name` is the module
    # it was wanted from, which is not the useful half here.
    _missing = getattr(exc, "name_from", None) or "ResourceSpec"
    raise ImportError(
        "This version of simple-steps needs a newer simple-steps-core.\n"
        f"  missing: {_missing}\n"
        f"  found core at: {getattr(_core, '__file__', '?')}\n"
        "\nResourceSpec landed in core on 2026-09-22. Upgrade it with:\n"
        "  pip install --upgrade --force-reinstall "
        '"simple-steps-core @ git+https://github.com/stusynakowski/simple-steps-core.git"\n'
        "\nIf you are working from a checkout of this repo, point core at the\n"
        "submodule instead so the two cannot drift:\n"
        "  git submodule update --init external/simple-steps-core\n"
        "  pip install -e external/simple-steps-core"
    ) from exc

__all__ = [
    "core_contract",
    "register_with_core",
    "simple_step_resource",
    "needs_whole_frame_shim",
]


# --------------------------------------------------------------------------- #
# The contract                                                                #
# --------------------------------------------------------------------------- #

#: Core's return type name → its cardinality word (``Output.form``).
_FORM = {"DataFrame": "grid", "Series": "column"}


def docstring_summary(fn: Callable) -> str:
    """The first paragraph of *fn*'s docstring, joined into one line.

    SHIM(core §C18): ``grid.catalog()``'s ``description`` is the docstring's
    first *line*, so a summary wrapped over two lines is cut mid-sentence —
    ``"Create a step from a single raw value. The value is stored in a"``.
    Delete when core takes the first paragraph.
    """
    lines = []
    for line in (inspect.getdoc(fn) or "").splitlines():
        if not line.strip():
            if lines:
                break
            continue
        lines.append(line.strip())
    return " ".join(lines)


@dataclass
class CoreContract:
    """What core says about a tool: ``grid.tool_entry`` plus the engine
    registry's resource fields."""

    tool_id: str
    description: str
    output_type: str = "Any"
    output_form: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    resource: Optional[str] = None
    params: List[Dict[str, Any]] = field(default_factory=list)


def core_contract(
    fn: Callable,
    tool_id: str,
    *,
    category: str = "",
    operation_type: str = "raw_output",
    description: Optional[str] = None,
    resource: Optional[str] = None,
) -> CoreContract:
    """
    Register *fn* with core and return its contract.

    Everything about the tool's signature and docstring is core's
    ``grid.tool_entry``: each parameter's type, ``choices`` for a ``Literal``
    and its ``Args:`` text, and the return type. The summary is the first
    paragraph of the docstring (SHIM core §C18). The engine
    registry adds what the grid doesn't track: a parameter's ``kind``
    (data or resource), the resource it is bound to, and dependencies.
    """
    from simple_steps_core import grid

    entry = grid.tool_entry(tool_id, fn, "declared")
    # An explicit description still wins over the docstring summary.
    resolved_description = description or docstring_summary(fn) or entry["description"] or ""

    tool = register_with_core(
        fn,
        tool_id,
        description=resolved_description,
        category=category,
        operation_type=operation_type,
        resource=resource,
    )
    definition = REGISTRY.get_definition(getattr(tool, "operation_id", tool_id))
    by_name = {p["name"]: p for p in entry["params"]}

    params: List[Dict[str, Any]] = []
    for p in definition.params:
        grid_param = by_name.get(p.name, {})
        params.append({
            "name": p.name,
            "type_name": grid_param.get("type") or p.type_name or "Any",
            "required": p.required,
            "default": p.default,
            "kind": p.kind,
            "resource_name": p.resource_name,
            "description": grid_param.get("description") or "",
            # The allowed values of a Literal, or None when unconstrained.
            "options": grid_param.get("choices"),
        })

    returns = entry.get("returns") or "Any"
    return CoreContract(
        tool_id=definition.operation_id,
        description=definition.description,
        output_type=returns,
        output_form=_FORM.get(returns),
        dependencies=list(definition.dependencies),
        resource=definition.resource,
        params=params,
    )


# SHIM(core §G): core's ToolDefinition.type has no 'step' member, and this
# repo's v0.2 default operation type *is* 'step' — one call, one return value,
# no row iteration. Registering it raises a pydantic literal_error, so it is
# translated on the way into core and kept verbatim in the local
# OperationDefinition. 'raw_output' is the closest core member: a single raw
# value out, no tabular orchestration.
_CORE_TYPE_ALIASES = {
    "step": "raw_output",
    "rowmap": "map",
}


def core_operation_type(operation_type: str) -> str:
    """Translate one of this repo's operation types into a member core accepts."""
    return _CORE_TYPE_ALIASES.get(operation_type, operation_type)


def register_with_core(
    fn: Callable,
    tool_id: str,
    *,
    description: str = "",
    category: str = "",
    operation_type: str = "raw_output",
    resource: Optional[str] = None,
    aliases: Tuple[str, ...] = (),
):
    """
    Put *fn* into core's registry and return core's ``Tool``.

    ``operation_type`` is translated through :func:`core_operation_type` first
    — see SHIM(core §G) above. Core's ``register_tool`` also annotates ``type``
    as only ``source | dataframe | raw_output``, but every member of
    ``ToolDefinition.type`` works at runtime; that one is a wrong annotation,
    not a wrong behaviour (proposal §D).
    """
    operation_type = core_operation_type(operation_type)
    if resource is not None:
        return REGISTRY.register(
            tool_id, fn,
            description=description, category=category, type=operation_type,
            resource=resource, aliases=aliases,
        )
    return _core_register_tool(
        tool_id, description, category=category, type=operation_type,
    )(fn)


# --------------------------------------------------------------------------- #
# Resources                                                                   #
# --------------------------------------------------------------------------- #

def simple_step_resource(
    name: Any,
    factory: Optional[Callable[[], Any]] = None,
    *,
    value: Any = None,
    check: Optional[Callable[[Any], Any]] = None,
    description: str = "",
) -> ResourceSpec:
    """
    Declare a resource — an object tools use — and get back core's
    :class:`ResourceSpec` to hang tools off.

    A spec with no ``factory`` and no ``value`` is **namespace-only**: it
    groups tools and injects nothing. That is how core models its own
    built-ins (the ``orchestration`` resource), and how this repo models its
    built-in tool groups::

        reshape = simple_step_resource("reshape", description="Table reshaping.")

        @reshape.tool("add_column", category="Data Reshaping", type="map")
        def add_column(df: pd.DataFrame, name: str, expression: str) -> pd.DataFrame:
            ...

    Bound tools register under a qualified id (``reshape-add_column``) with the
    bare name kept as an alias, so saved workflows keep resolving. A
    namespace-only spec becomes resource-backed later by adding ``factory=``
    to this same call — tool ids do not move, because they derive from *name*.

    **On a class**, it declares a resource *type* for the grid (core 007): the
    constructor's parameters are its literal settings, and the methods marked
    ``@simple_step_tool`` are its bound tools. Unmarked methods are never tools::

        @simple_step_resource
        class ClinicalDB:
            def __init__(self, url: str): ...

            @simple_step_tool
            def query(self, sql: str) -> pd.DataFrame: ...   # res["db"].query(…)

            def close(self) -> None: ...                     # not a tool
    """
    if inspect.isclass(name):
        from simple_steps_core import grid
        from .resources import register_type
        return register_type(grid.resource(name))
    return ResourceSpec(
        name,
        factory=factory,
        value=value,
        check=check,
        description=description,
        registry=REGISTRY,
    )


# --------------------------------------------------------------------------- #
# Grid execution gaps                                                         #
# --------------------------------------------------------------------------- #

def needs_whole_frame_shim(verb: str) -> bool:
    """Whether a step must run on the legacy engine instead of core's grid.

    SHIM(core §C17): ``mod.table()`` hands the grid to the tool's *first*
    parameter. A whole-table tool whose ``pd.DataFrame`` parameter comes
    later — ``f(n: int, data: pd.DataFrame)`` — is refused: "f() needs
    'data', which 'r' does not have". ``grid_runner._plan_table`` leaves those
    as ``dataframe``, and the legacy orchestrator binds the table by type.
    Delete when ``table`` binds the parameter typed ``DataFrame``.
    """
    return verb == "dataframe"
