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

#: One accessor at a time: a dotted field, or whatever sits inside brackets.
_ACCESSOR_RE = re.compile(r"(?:^|\.)(?P<field>[\w-]+)|\[(?P<index>[^\]]*)\]")


def is_reference(value: object) -> bool:
    """True if *value* is a string shaped like a step reference token."""
    if not isinstance(value, str) or not value:
        return False
    return bool(_REFERENCE_RE.match(value))


def parse_reference(token: str) -> tuple[str, list[str | int]]:
    """Split a reference into its step id and an ordered list of accessors.

    Field names come back as ``str`` and bracket indexers as ``int``, so a
    resolver can walk them in order::

        "step1"                -> ("step1", [])
        "step1.total"          -> ("step1", ["total"])
        "step1.rows[0].name"   -> ("step1", ["rows", 0, "name"])
        "step1[2]"             -> ("step1", [2])

    A bracket holding a quoted string is a **key**, not an index, so a dict
    keyed by digits stays reachable: ``step1["0"]`` -> ``("step1", ["0"])``.
    """
    head = token.split(".", 1)[0].split("[", 1)[0]
    accessors: list[str | int] = []
    step_id = ""
    for position, part in enumerate(_ACCESSOR_RE.finditer(token)):
        field, index = part.group("field"), part.group("index")
        if position == 0 and field is not None and not accessors:
            step_id = field
            continue
        if field is not None:
            accessors.append(field)
        elif index is not None:
            literal = index.strip()
            if len(literal) >= 2 and literal[0] == literal[-1] and literal[0] in "\"'":
                accessors.append(literal[1:-1])          # a quoted key
            else:
                try:
                    accessors.append(int(literal))
                except ValueError:
                    accessors.append(literal)            # a bare word key
    return step_id or head, accessors


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
