"""What widen opens, on uneven rows (roadmap phase 2: I1, W1, W3;
expression-grammar/widen.md U3–U5, U7, U11, U13).

Decided 2026-11-23 (owner), after pandas' convention: a **sequence** (a list,
a tuple) opens **by position**, as wide as the longest row, a missing position
**absent**; a mapping by key, the union of the keys; nothing to open (``None``,
a gap, ``()``, ``{}``) gives absent fields; a **unit** (a string, a number, an
array) or something not openable as it is (a set) **fails its own row**, and
the failure stays visible even when nothing in the column opens.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from simple_steps_core import Catalog, Kernel, mod, wf


def widen(values: list, **settings):
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({"id": list(range(len(values))), "v": pd.Series(values, dtype=object)})
    k["w"] = mod.widen("v", **settings)(wf["d"])
    try:
        k.run("w")
    except Exception:
        pass
    v = k.view("w")
    names = [c["name"] for c in v["columns"]]
    rows = [[(r["cells"][c].get("value") if r["cells"][c]["state"] == "known"
              else r["cells"][c]["state"]) for c in names] for r in v["rows"]]
    return k, names, rows


# ── sequences, by position ─────────────────────────────────────────────────
def test_a_list_opens_by_position_as_a_tuple_does():
    _, names, rows = widen([[1, 2], [3, 4]])
    assert names == ["id", "var0", "var1"]
    assert rows == [[0, 1, 2], [1, 3, 4]]


def test_ragged_sequences_go_to_the_longest_the_missing_absent():
    _, names, rows = widen([(1, 2, 3), (4,)])
    assert names == ["id", "var0", "var1", "var2"]
    assert rows == [[0, 1, 2, 3], [1, 4, "absent", "absent"]]


def test_an_empty_tuple_beside_others_gives_absent_fields():
    _, names, rows = widen([(), (1,)])
    assert rows == [[0, "absent"], [1, 1]]


def test_lists_and_tuples_together_are_sequences_alike():
    _, names, rows = widen([[1, 2], (3,)])
    assert rows == [[0, 1, 2], [1, 3, "absent"]]


def test_declared_names_name_the_positions():
    _, names, rows = widen([[1, 2], [3]], columns=["a", "b"])
    assert names == ["id", "a", "b"]
    assert rows == [[0, 1, 2], [1, 3, "absent"]]


# ── units, and what isn't openable ─────────────────────────────────────────
def test_a_string_among_dicts_fails_its_own_row():
    k, names, rows = widen([{"a": 1}, "oops"])
    assert rows[0][names.index("a")] == 1
    assert rows[1][names.index("a")] == "failed"


def test_when_nothing_opens_the_failures_stay_visible():
    """I1: a column of strings gave no columns, and its failures vanished."""
    k, names, rows = widen(["ab", "cd"])
    assert k.step("w").state == "failed"
    assert all("failed" in r for r in rows)
    error = k.cell("w", 0, names[-1]).get("error") or ""
    assert "str" in error


def test_an_array_is_a_unit_and_fails_its_row():
    k, names, rows = widen([{"a": 1}, np.array([1, 2])])
    assert rows[1][names.index("a")] == "failed"


def test_a_set_fails_its_row_naming_the_fix():
    k, names, rows = widen([{"a": 1}, {1, 2}])
    assert rows[1][names.index("a")] == "failed"
    note = str(k.step("w").output.notes)
    assert "sort" in note


def test_when_nothing_opens_and_it_is_the_only_column_nothing_vanishes():
    """I1, as found (blocks.md §5): a table of one column of strings widened
    to no columns at all, completed, the strings gone without a word."""
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({"v": ["ab", "cd"]})
    k["w"] = mod.widen("v")(wf["d"])
    try:
        k.run("w")
    except Exception:
        pass
    assert k.step("w").state == "failed"
    view = k.view("w")
    assert view["columns"], "the failures need a column to show in"
    assert all(cell["state"] == "failed" for r in view["rows"] for cell in r["cells"].values())
