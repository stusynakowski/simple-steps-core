"""A conversion keeps the value's meaning exactly, or that cell fails
(roadmap phase 2: convert.md CV1, CF1, CF2; the defaults CV6, CV9, CV12).

Decided 2026-11-23 (owner). Today's ``mod.cast``; the arguments for the
other way (``strict=``, ``lossy=``, ``nonzero=``, ``round=``) come with the
canonical ``convert`` (roadmap phase 3), since ``cast``'s keywords name
columns.
"""

from __future__ import annotations

import pandas as pd

from simple_steps_core import Catalog, Kernel, mod, tool, wf


@tool
def seen(x) -> str:
    return f"{type(x).__name__}:{x!r}"


def cast(values: list, to: str) -> list:
    k = Kernel(Catalog(tools=[seen]))
    k["d"] = pd.DataFrame({"x": pd.Series(values, dtype=object)})
    k["c"] = seen[mod.cast(x=to), mod.map()](wf["d"])
    try:
        k.run("c")
    except Exception:
        pass
    out = []
    for r in k.view("c")["rows"]:
        cell = r["cells"]["c"]
        out.append(cell.get("value") if cell["state"] == "known" else cell["state"])
    return out


# ── CF1, CF2: no silent loss ───────────────────────────────────────────────
def test_an_integer_other_than_0_or_1_doesnt_become_a_bool():
    assert cast([0, 1, 2], "bool") == ["bool:False", "bool:True", "blocked"]


def test_a_big_integer_a_float_cant_hold_exactly_fails():
    assert cast([2 ** 60 + 1, 2 ** 60, 7], "float") == ["blocked", "float:1.152921504606847e+18", "float:7.0"]


# ── CV6: "2.0" is a whole number ───────────────────────────────────────────
def test_text_with_a_point_converts_to_an_int_when_whole():
    assert cast(["2", "2.0", "2.5"], "int") == ["int:2", "int:2", "blocked"]


# ── CV9: yes and no ────────────────────────────────────────────────────────
def test_text_to_bool_takes_true_false_yes_no_1_0():
    assert cast(["True", "no", "YES", "1", "0", "maybe"], "bool") == [
        "bool:True", "bool:False", "bool:True", "bool:True", "bool:False", "blocked"]


# ── CV12: structures to text through JSON ──────────────────────────────────
def test_a_list_or_dict_to_text_is_json():
    assert cast([[1, 2], {"a": None}], "str") == ["str:'[1, 2]'", "str:'{\"a\": null}'"]


def test_a_set_to_text_fails_naming_a_tool():
    assert cast([{1, 2}], "str") == ["blocked"]


# ── kept ───────────────────────────────────────────────────────────────────
def test_what_already_held_still_holds():
    assert cast([2.0, 1.7], "int") == ["int:2", "blocked"]          # CV5
    assert cast(["1.5", "abc"], "float") == ["float:1.5", "blocked"]  # CV2, CV3
    assert cast([None], "int") == ["NoneType:None"]                  # CV13
