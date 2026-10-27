"""The built-in tools: identity, and the reducers gather, count, total, first, last.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

import inspect
import typing
from typing import Any
from typing import Callable


# ─────────────────────────────────────────────────────────────────────────
# identity — the tool that closes the algebra
# ─────────────────────────────────────────────────────────────────────────
def is_identity(fn: Callable) -> bool:
    """True when *fn* is :func:`identity`, through any adapter wrapping it."""
    seen = 0
    while fn is not None and seen < 10:
        if fn is identity:
            return True
        fn, seen = getattr(fn, "__wrapped__", None), seen + 1
    return False


def identity(**row: Any) -> Any:
    """Return what the previous step produced — the default tool.

    Every step is a verb applied to a tool, with no special case for the steps
    that only *reshape*: those apply a verb to ``identity``. ``expand`` over it
    flattens a level, ``filter`` over it keeps what is already truthy, and
    ``source`` over it lifts a literal.

    **It returns the payload, not the row.** A tool here receives a whole row
    (``{"n": 1, "value": [2, 3]}``), but the reshaping verbs need the *cell*
    the previous step produced — returning the row would make
    ``filter``+identity keep everything (a non-empty dict is truthy) and
    ``expand``+identity flatten nothing (a dict is not unpacked). So the
    payload is resolved by convention:

    1. an explicit ``column``, when the step named one;
    2. the ``value`` column, which is what the verbs write by default;
    3. the only column, when the row has exactly one;
    4. otherwise the whole row — nothing else is well defined.

    Case 4 is the honest limit: after ``map(name="score")`` the payload is
    ``score`` and no convention can know it, so bind it —
    ``op("identity", column="score")``.

    ``collapse`` is the exception to all of this: it needs a two-argument
    reducer, so there is nothing for identity to mean there.
    """
    column = row.pop("column", None)
    if column is not None:
        return row[column]
    if VALUE_COLUMN in row:
        return row[VALUE_COLUMN]
    if len(row) == 1:
        return next(iter(row.values()))
    return row


def gather(acc: Any = None, **row: Any) -> list:
    """Collect every payload into one list.

    The default tool for ``collapse``. Where ``identity`` is the map that
    discards nothing, this is the **reduction** that discards nothing — so
    ``collapse`` needs no bespoke tool just to bring a column together, and it
    becomes the exact inverse of ``expand``: a cell holding ``[1, 2, 3]``
    expands to three rows, and three rows gather back into that cell.

    Takes the accumulator first, like every reducer, and resolves each row's
    payload the same way :func:`identity` does — so it works on any grid, not
    only one whose payload column happens to be called ``value``.
    """
    return [*(acc or []), identity(**row)]


def count(acc: Any = None, **row: Any) -> int:
    """How many rows reached this step. Ignores the values entirely."""
    return (acc or 0) + 1


def total(acc: Any = None, **row: Any) -> float:
    """Sum of the payloads. Raises on a payload that will not add."""
    return (acc or 0) + identity(**row)


def first(acc: Any = None, **row: Any) -> Any:
    """The first payload, in row order. Later rows are ignored."""
    return identity(**row) if acc is None else acc


def last(acc: Any = None, **row: Any) -> Any:
    """The last payload, in row order."""
    return identity(**row)


def as_list(**row: Any) -> list:
    """A value as a list, on purpose (reshaping.md §9.2, J-D3): a list stays
    itself, ``None`` becomes ``[]``, anything else ``[value]``. Use it under
    ``map`` before ``expand`` when a single value means a one-item list. Finds
    its value the way :func:`identity` does."""
    value = identity(**row)
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def gather_dict(key: list, value: list) -> dict:
    """The rows of a group as one dict, ``{key: value}``: the inverse of
    ``expand`` over a dict (J-D4)."""
    return dict(zip(key, value))


# What each reducer gives over no rows (docs/design/reshaping.md R6): the
# value it would start from. ``first`` and ``last`` have none, so they give
# ``None``; the ``absent`` cell state (J-D1) will say so better.
gather.empty = []
count.empty = 0
total.empty = 0


#: First-parameter names that mark a tool as a fold, ``(acc, …) -> acc``.
ACCUMULATOR_NAMES = frozenset({"acc", "accumulator", "memo", "carry"})


def _base(fn: Any) -> Any:
    """The plain function under any adapters, and under a ``Tool``."""
    seen = 0
    while fn is not None and seen < 12:
        if getattr(fn, "__wrapped__", None) is not None:
            fn = fn.__wrapped__
        elif type(fn).__name__ in ("Tool", "BoundTool") and callable(getattr(fn, "fn", None)):
            fn = fn.fn
        else:
            break
        seen += 1
    return fn


def reducer_form(fn: Any) -> str:
    """How a tool under ``collapse`` takes its group (reshaping.md §8, R-D13).

    ``"count"``: counts rows. ``"per_column"``: a built-in reducer, run once
    per variable. ``"fold"``: ``(acc, …) -> acc``, one row at a time.
    ``"group"``: called once per group with each column as a list.
    """
    base = _base(fn)
    if base is count:
        return "count"
    if base in (gather, total, first, last):
        return "per_column"
    try:
        first_name = next(iter(inspect.signature(base).parameters), None)
    except (TypeError, ValueError):
        return "fold"
    return "fold" if first_name in ACCUMULATOR_NAMES else "group"


def rows_parameters(fn: Any) -> list[str]:
    """A group function's parameters that take the group's rows: typed as a
    list of dicts or of a record type (``list[Visit]``)."""
    try:
        parameters = inspect.signature(_base(fn)).parameters.values()
    except (TypeError, ValueError):
        return []
    found = []
    for p in parameters:
        if typing.get_origin(p.annotation) in (list, typing.List):
            args = typing.get_args(p.annotation)
            item = args[0] if args else None
            if item is dict or typing.get_origin(item) is dict or \
                    (isinstance(item, type) and hasattr(item, "__annotations__") and item is not str):
                found.append(p.name)
    return found


def empty_value(fn: Callable) -> Any:
    """What reducer *fn* gives over no rows, through any adapter wrapping it."""
    seen = 0
    while fn is not None and seen < 10:
        if hasattr(fn, "empty"):
            value = fn.empty
            return list(value) if isinstance(value, list) else value
        fn, seen = getattr(fn, "__wrapped__", None), seen + 1
    return None


#: Tools every Operation can name without being handed a registry, and the
#: defaults a bare modifier resolves to. A user may name any of these by id in
#: place of their own function — they are the reductions and pass-throughs that
#: would otherwise be written by hand in every workflow.
BUILTIN_TOOLS: dict[str, Callable] = {
    "identity": identity,
    "gather": gather,
    "count": count,
    "total": total,
    "first": first,
    "last": last,
    "as_list": as_list,
    "gather_dict": gather_dict,
}


#: The tool a shape verb applies when none is named — *the one that discards
#: nothing*. For every verb that maps, that is ``identity``; for ``collapse``,
#: whose tool takes an accumulator first, it is ``gather``. The arity is why one
#: cannot stand in for the other.
DEFAULT_TOOL: dict[str, str] = {
    "source": "identity", "select": "identity", "drop": "identity",
    "widen": "identity", "pack": "identity", "slice": "identity", "rename": "identity",
    "sort": "identity", "distinct": "identity",
    "map": "identity", "filter": "identity", "group": "identity",
    "expand": "identity", "collapse": "gather",
}


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .output import VALUE_COLUMN  # noqa: E402
