"""
Tabular helpers — what a "row" means to an orchestrator
=======================================================

Iterating a DataFrame in Python yields its **column names**, not its rows. So
``map(over=a_frame)`` would quietly run once per column — two items for a
three-row frame, with no error to notice. This module is the one place that
knows better.

Two jobs:

**Iteration.** :func:`items_of` turns a step's output into the items an
orchestrator should fan out over. A DataFrame yields one ``dict`` per row;
everything else iterates normally.

**Shape preservation.** A frame that goes into ``filter`` comes back out as a
frame. :func:`select_positions` rebuilds it with ``iloc``, so dtypes, column
order and the original index survive exactly — which rebuilding from dicts
would not.

Pandas is never imported here. A frame is recognized structurally (it has
``columns``, ``iloc`` and ``to_dict``), matching how the rest of the codebase
already sniffs for one, so core keeps working without pandas installed.
"""

from __future__ import annotations

from typing import Any


def is_frame(value: Any) -> bool:
    """True when *value* quacks like a pandas DataFrame."""
    return (
        hasattr(value, "columns")
        and hasattr(value, "iloc")
        and hasattr(value, "to_dict")
    )


def items_of(over: Any) -> list[Any]:
    """The items an orchestrator should fan out over.

    A DataFrame yields one plain ``dict`` per row, so tools stay ordinary
    Python and never import pandas. Anything else iterates as usual — a list, a
    :class:`~.collections.Collection`, a generator's output.
    """
    if is_frame(over):
        return over.to_dict("records")
    if isinstance(over, (str, bytes)):
        # Iterating a string yields characters, so a fan-out over one silently
        # produces one item per letter. That is never what someone meant; it is
        # almost always a reference that did not resolve, because the reference
        # grammar only recognizes tokens starting with "step" (see
        # domain/references.py) — `over="s1"` is a literal string, `over="step1"`
        # is a reference.
        raise TypeError(
            f"Cannot fan out over the string {over!r}: a string is not a "
            "collection. If this was meant to reference an earlier step, note "
            "that step references must start with 'step' (e.g. 'step1'), "
            "otherwise the value is treated as a literal."
        )
    return list(over)


def select_positions(original: Any, positions: list[int]) -> Any:
    """Take the rows of *original* at *positions*, preserving its type.

    For a frame this is ``iloc``, so dtypes and index labels come through
    untouched. For anything else it is ordinary indexing into a list.
    """
    if is_frame(original):
        return original.iloc[positions]
    items = list(original)
    return [items[p] for p in positions]


def rows_to_frame(rows: list[Any], like: Any) -> Any:
    """Build a frame of the same class as *like* from a list of row dicts.

    Used by ``expand``, whose output rows are new and so cannot be selected
    from the original by position. Falls back to returning ``rows`` unchanged
    when they are not all dicts — a flat-map is allowed to produce scalars, and
    forcing those into a frame would be a lie about the data.
    """
    if not rows or not all(isinstance(row, dict) for row in rows):
        return rows
    frame_class = type(like)
    try:
        # Keep the original column order where the new rows share it.
        columns = [c for c in like.columns if any(c in row for row in rows)]
        extra = [k for row in rows for k in row if k not in columns]
        ordered = columns + list(dict.fromkeys(extra))
        return frame_class(rows, columns=ordered or None)
    except Exception:
        # A frame class that will not take (rows, columns=...) is not worth
        # failing the whole step over; hand back the rows.
        return rows
