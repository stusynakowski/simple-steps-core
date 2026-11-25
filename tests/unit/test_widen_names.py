"""Widen's names and what it says (roadmap phase 2: W2, W5, W6;
expression-grammar/widen.md U12, U15–U20, U29).

Decided 2026-11-23 (owner): a field's name is a string (an integer key is
``var1``, tidy.md T1); a key starting with ``#`` loses it, and it is said;
two fields with one name, or a field named like a column kept beside it, are
suffixed ``_1`` and it is said (``replace=True`` replaces the column); an
extra field against declared ones is warned, not added; a declared field
missing from every row is warned; more than 50 fields are warned (the keys
are probably values); nothing to discover from is said.
"""

from __future__ import annotations

import pandas as pd

from simple_steps_core import Catalog, Kernel, mod, wf


def widen(values: list, extra: dict | None = None, **settings):
    k = Kernel(Catalog(tools=[]))
    frame = {"v": pd.Series(values, dtype=object)}
    frame.update(extra or {})
    k["d"] = pd.DataFrame(frame)
    k["w"] = mod.widen("v", **settings)(wf["d"])
    try:
        k.run("w")
    except Exception:
        pass
    v = k.view("w")
    names = [c["name"] for c in v["columns"]]
    rows = [[(r["cells"][c].get("value") if r["cells"][c]["state"] == "known"
              else r["cells"][c]["state"]) for c in names] for r in v["rows"]]
    return k, names, rows, [str(w) for w in k.step("w").warnings]


def test_integer_keys_are_named_as_numeric_column_names_are():
    """W2: the view crashed, KeyError: 'var1'."""
    k, names, rows, _ = widen([{1: "x", 2: "y"}])
    assert names == ["var1", "var2"]
    assert rows == [["x", "y"]]


def test_a_hash_key_loses_its_hash_and_it_is_said():
    """W5: the field vanished silently."""
    k, names, rows, warnings = widen([{"#a": 1, "b": 2}])
    assert names == ["a", "b"]
    assert rows == [[1, 2]]
    assert any("#a" in w for w in warnings)


def test_two_fields_with_one_name_are_suffixed_and_it_is_said():
    """W6: keys 1 and "1" failed the whole step."""
    k, names, rows, warnings = widen([{"#a": 1, "a": 2}])
    assert names == ["a", "a_1"]
    assert rows == [[1, 2]]
    assert any("a_1" in w for w in warnings)


def test_a_field_named_like_a_kept_column_is_suffixed():
    """U20: the whole step failed."""
    k, names, rows, warnings = widen([{"a": 1}], extra={"a": [0]})
    assert names == ["a", "a_1"]
    assert rows == [[0, 1]]
    assert any("a_1" in w for w in warnings)


def test_replace_still_replaces_the_column():
    k, names, rows, _ = widen([{"a": 1}], extra={"a": [0]}, replace=True)
    assert names == ["a"]
    assert rows == [[1]]


def test_an_extra_field_against_declared_ones_is_warned_not_added():
    k, names, rows, warnings = widen([{"a": 1, "z": 9}], columns=["a"])
    assert names == ["a"]
    assert any("z" in w for w in warnings)


def test_a_declared_field_missing_from_every_row_is_warned():
    k, names, rows, warnings = widen([{"a": 1}, {"a": 2}], columns=["a", "b"])
    assert rows == [[1, "absent"], [2, "absent"]]
    assert any("b" in w and "every row" in w for w in warnings)


def test_more_than_fifty_fields_are_warned_as_probably_values():
    k, names, rows, warnings = widen([{f"d{i}": i for i in range(60)}])
    assert len(names) == 60
    assert any("probably values" in w for w in warnings)


def test_nothing_to_discover_from_is_said():
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({"v": pd.Series([], dtype=object)})
    k["w"] = mod.widen("v")(wf["d"])
    k.run("w")
    assert any("no rows" in str(w) for w in k.step("w").warnings)
