"""
Reference grammar
=================

A *reference* is a token that points at another step's output instead of a
literal value, e.g. ``step1`` or ``step1.total``. This module owns only the
**grammar** of references (what they look like) — it knows nothing about
which steps exist or how to fetch their data. Actual resolution against a
session store lives in ``execution/resolver.py``.
"""

from __future__ import annotations

import re

# A reference is "step" + identifier, optionally followed by dotted field
# accessors or bracket indexers, e.g. step1, step_2.total, step3.rows[0].
_REFERENCE_RE = re.compile(r"^step[\w-]*(?:\.\w+|\[[^\]]*\])*$", re.IGNORECASE)


def is_reference(value: object) -> bool:
    """True if *value* is a string shaped like a step reference token."""
    if not isinstance(value, str) or not value:
        return False
    return bool(_REFERENCE_RE.match(value))


def split_reference(token: str) -> tuple[str, str | None]:
    """
    Split a reference into its (step_id, field) parts.

    ``"step1"``        -> ("step1", None)
    ``"step1.total"``  -> ("step1", "total")

    Only the first dotted accessor is returned as ``field``; deeper paths are
    left for the resolver to interpret. Bracket indexers are ignored here.
    """
    head = token.split("[", 1)[0]        # drop any bracket indexer
    if "." in head:
        step_id, field = head.split(".", 1)
        return step_id, field
    return head, None
