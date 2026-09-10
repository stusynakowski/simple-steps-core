"""
Inspection helpers
==================

Every user-facing object exposes two things (see docs/object-model.md):

* ``__repr__`` — one dense line, safe for logs (no payloads).
* ``info()``   — a rich, tabular :class:`SummaryTable` that renders as a table
  in notebooks (via ``_repr_html_``) and as aligned text in logs (``__str__``).

:class:`SummaryTable` is the single value object all ``info()`` methods build,
so the look-and-feel stays consistent across the whole model. It never holds
payloads — only labels, counts, shapes, and statuses.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any


def _cell(value: Any) -> str:
    """Render one cell as a short, safe string (never a heavy payload)."""
    if value is None:
        return ""
    return str(value)


@dataclass
class SummaryTable:
    """A small, printable table with an HTML view for notebooks.

    ``columns`` are optional headers; ``rows`` is a list of rows (each a list of
    cells). ``caption`` is an optional dim sub-title line under the title.
    """

    title: str
    rows: list[list[Any]] = field(default_factory=list)
    columns: list[str] | None = None
    caption: str = ""

    def add_row(self, *cells: Any) -> "SummaryTable":
        self.rows.append(list(cells))
        return self

    # ── text rendering (logs / plain terminals) ─────────────────────────
    def __str__(self) -> str:
        grid = [[_cell(c) for c in row] for row in self.rows]
        headers = self.columns or []
        widths: list[int] = []
        for col in range(len(headers) if headers else (max((len(r) for r in grid), default=0))):
            cells = [row[col] for row in grid if col < len(row)]
            header_w = len(headers[col]) if col < len(headers) else 0
            widths.append(max([header_w, *(len(c) for c in cells)] or [0]))

        lines = [self.title]
        if self.caption:
            lines.append(self.caption)
        if headers:
            lines.append("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
            lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
        for row in grid:
            lines.append("  ".join(row[i].ljust(widths[i]) if i < len(widths) else row[i]
                                    for i in range(len(row))))
        return "\n".join(lines)

    __repr__ = __str__

    # ── HTML rendering (Jupyter / notebooks) ────────────────────────────
    def _repr_html_(self) -> str:
        parts = [f"<div style='font-family:var(--jp-code-font-family,monospace)'>"]
        parts.append(f"<strong>{html.escape(self.title)}</strong>")
        if self.caption:
            parts.append(f"<div style='color:#888;font-size:90%'>{html.escape(self.caption)}</div>")
        parts.append("<table style='border-collapse:collapse;margin-top:4px'>")
        if self.columns:
            parts.append("<tr>" + "".join(
                f"<th style='text-align:left;padding:2px 10px 2px 0;"
                f"border-bottom:1px solid #ccc'>{html.escape(c)}</th>"
                for c in self.columns
            ) + "</tr>")
        for row in self.rows:
            parts.append("<tr>" + "".join(
                f"<td style='padding:2px 10px 2px 0;vertical-align:top'>"
                f"{html.escape(_cell(c))}</td>"
                for c in row
            ) + "</tr>")
        parts.append("</table></div>")
        return "".join(parts)
