"""
Base adapters
=============

The primitives every other component is built from.

Almost every user-facing object in the library exposes ``info()`` returning a
:class:`~simple_steps_core.SummaryTable`, so :func:`summary` is the single
adapter most components route through — the library owns the *content*, this
module owns only how it looks in Streamlit.

Component conventions (the whole package follows these):

* ``render_x(st, obj, *, key, on_… = None) -> None`` — draw *obj*. Actions are
  offered as buttons but the **caller** supplies behavior via ``on_…``
  callbacks, so a component never mutates anything it was handed.
* ``edit_x(st, obj, *, key) -> X`` — draw widgets seeded from *obj* and return
  a new instance. The domain configs are frozen, so editing means replacing.
* ``st`` is always the first positional parameter, never imported at module
  level, so every component is unit-testable with a fake and importing this
  package never requires Streamlit.
* ``key`` is a required prefix for every widget, so the same component can be
  drawn twice on one page without colliding.
"""

from __future__ import annotations

from typing import Any

from simple_steps_core import SummaryTable

__all__ = ["summary", "summary_frame", "caption_list", "empty"]


def summary_frame(table: SummaryTable):
    """A ``SummaryTable`` as a pandas DataFrame (columns preserved when named)."""
    import pandas as pd

    if not table.rows:
        return pd.DataFrame(columns=table.columns or [])
    # Every cell becomes a string: a SummaryTable column may mix ints, bools and
    # None, and a mixed object column has no Arrow type to convert to.
    def _cells(row):
        return ["" if c is None else str(c) for c in row]

    if table.columns:
        width = len(table.columns)
        padded = [_cells(list(r) + [None] * (width - len(r))) for r in table.rows]
        return pd.DataFrame(padded, columns=table.columns)
    return pd.DataFrame([_cells(r) for r in table.rows])


def summary(st, table: SummaryTable, *, key: str | None = None,
            title: bool = True, caption: bool = True) -> None:
    """Render a ``SummaryTable`` — the adapter nearly every component uses.

    ``title``/``caption`` let a caller suppress the heading when the table is
    already inside a titled container (an expander, say).
    """
    if title and table.title:
        st.markdown(f"**{table.title}**")
    if caption and table.caption:
        st.caption(table.caption)
    if not table.rows:
        st.caption("— nothing to show —")
        return
    st.dataframe(summary_frame(table), width="stretch", hide_index=True, key=key)


def caption_list(st, label: str, values: list[str], *, icon: str = "") -> None:
    """One dim line listing *values*, or nothing at all when empty."""
    if not values:
        return
    prefix = f"{icon} " if icon else ""
    st.caption(f"{prefix}{label}: " + ", ".join(f"`{v}`" for v in values))


def empty(st, message: str) -> None:
    """The one place 'there is nothing here yet' is phrased."""
    st.caption(message)


def _scalar(value: Any) -> bool:
    """True for values Streamlit can print directly rather than tabulate."""
    return value is None or isinstance(value, (bool, int, float, str))
