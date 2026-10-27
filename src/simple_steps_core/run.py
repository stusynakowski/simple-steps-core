"""Running an operation: compiling its modifier stack into a callable, and auto.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from typing import Callable
import inspect
import pandas as pd


def _resolve_tool_setting(value: Any, table: dict) -> Any:
    """A ``$tool`` setting as its function; anything else unchanged."""
    if isinstance(value, ToolHandle):
        return value.fn
    if isinstance(value, ToolRef):
        if value.id not in table:
            raise KeyError(f"setting names tool {value.id!r}, which is not registered")
        found = table[value.id]
        return found.fn if isinstance(found, ToolHandle) else found
    return value


#: Verbs that run a tool once per row: auto gives them its breaker (009 §7).
ROW_WISE = frozenset({"map", "filter", "group", "expand"})


def _auto_defaults(operation: Operation, kind: str) -> list["Modifier"]:
    """The default modifiers auto adds for *kind* — none the step already states."""
    stated = {m.kind for m in operation.modifiers}
    defaults = []
    if kind in ROW_WISE and "breaker" not in stated:
        defaults.append(Modifier("breaker", {"after": BREAKER_AFTER}))
    return defaults


def _runs_over_rows(fn: Callable, data: Any, given: dict) -> bool:
    """Does *data* fail to fit the tool as one argument, while its rows would?

    True when *data* is a grid, the tool's first free parameter is typed and a
    grid doesn't fit that type (``n: int``), and the grid's columns supply
    every required parameter. A tool typed to take a frame, or untyped, is
    called with the frame as-is.
    """
    if not isinstance(data, (pd.DataFrame, Output)):
        return False
    try:
        parameters = [p for p in _signature(fn).parameters.values()
                      if p.kind not in (inspect.Parameter.VAR_POSITIONAL,
                                        inspect.Parameter.VAR_KEYWORD)
                      and p.name not in given]
    except (TypeError, ValueError):
        return False
    if not parameters or parameters[0].annotation is inspect.Parameter.empty:
        return False
    if _type_fits(pd.DataFrame, parameters[0].annotation) is not False:
        return False
    columns = set(_rows_frame(data).columns)
    required = [p.name for p in parameters if p.default is inspect.Parameter.empty]
    return bool(required) and all(name in columns for name in required)


def _with_verb(operation: Operation, kind: str) -> Operation:
    """*operation* with its ``auto`` replaced by the verb *kind* and auto's defaults.

    The defaults go just inside the verb (``[retry, breaker, map]``,
    innermost first), so they see every unit's final outcome.
    """
    defaults = _auto_defaults(operation, kind)
    modifiers: list = []
    for m in operation.modifiers:
        if m.kind == "auto":
            modifiers += defaults
            modifiers.append(Modifier(kind, {}))
        else:
            modifiers.append(m)
    return replace(operation, modifiers=tuple(modifiers))


def _resolve_auto(operation: Operation, upstream: Any) -> tuple[Operation, str, str]:
    """(concrete operation, verb, reason) for an ``auto`` step over *upstream*."""
    fn = operation.fn or TOOLS.get(operation.tool_id) or BUILTIN_TOOLS.get(operation.tool_id)
    if fn is None:
        return _with_verb(operation, "map"), "map", "the tool isn't known; assuming per row"
    kind, why = infer_verb(fn, upstream, operation.arguments)
    added = _auto_defaults(operation, kind)
    if added:
        why += "; adds " + ", ".join(repr(m) for m in added)
    return _with_verb(operation, kind), kind, why


def _is_auto(operation: Operation) -> bool:
    return any(m.kind == "auto" for m in operation.modifiers)


def _provisional(operation: Operation, workflow: "Workflow | None") -> tuple[Operation, str, str]:
    """Resolve ``auto`` against what is known now — the staged or run input."""
    upstream = None
    if workflow is not None and operation.input is not None:
        step = workflow.steps.get(str(operation.input))
        upstream = None if step is None else step.output
    return _resolve_auto(operation, upstream)


def compile_operation(operation: Operation, tools: dict[str, Callable]) -> Callable:
    """Apply an Operation's stack to its tool, innermost-first.

    This is the moment the data becomes behaviour: ``[retry, map]`` compiles to
    ``map(retry(tool))`` — the same object graph ``@map`` over ``@retry`` over
    the function would have produced at definition time.
    """
    table = {**BUILTIN_TOOLS, **TOOLS, **tools}
    if operation.tool_id not in table:
        raise KeyError(f"unknown tool {operation.tool_id!r}; have {sorted(table)}")
    if _is_auto(operation):
        # 008 N: the verb is picked from the data this call receives.
        def run_auto(source: Any) -> Any:
            concrete, _, _ = _resolve_auto(operation, source)
            return compile_operation(concrete, tools)(source)
        return run_auto
    # The adapter is always innermost: it is what turns a plain function into
    # something a verb can drive, and it carries the bound literals inside
    # every modifier, so a retry re-runs the same call and a map passes them to
    # every item.
    fn = _d_apply(table[operation.tool_id], **operation.arguments)
    for modifier in operation.modifiers:               # innermost first
        # 008 C2: a tool named in a setting is resolved from the same table.
        modifier = Modifier(modifier.kind, {
            k: _resolve_tool_setting(v, table) for k, v in modifier.params.items()})
        factory = DECORATORS.get(modifier.kind)
        if factory is None:
            raise KeyError(
                f"no decorator registered for modifier {modifier.kind!r}; "
                f"known: {sorted(DECORATORS)}"
            )
        fn = factory(fn, **modifier.params)
    return fn


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .system_tools import BUILTIN_TOOLS  # noqa: E402
from .catalog import (  # noqa: E402
    TOOLS,
    ToolHandle,
    _signature,
    _type_fits,
)
from .checks import infer_verb  # noqa: E402
from .modifiers import (  # noqa: E402
    BREAKER_AFTER,
    DECORATORS,
    Modifier,
    _d_apply,
)
from .operation import Operation  # noqa: E402
from .output import Output  # noqa: E402
from .references import ToolRef  # noqa: E402
from .verbs import _rows_frame  # noqa: E402
from .workflow import Workflow  # noqa: E402
