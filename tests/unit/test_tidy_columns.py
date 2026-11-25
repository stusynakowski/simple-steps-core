"""Column names in data given and in outputs (roadmap phase 2: tidy.md C2,
C3; T1, T5).

Decided 2026-11-23 (owner): duplicate names are **suffixed**, ``a``,
``a_1``, and said (C2: refused with a raw pandas error); hierarchical
(MultiIndex) columns are **flattened**, their parts joined by an underscore,
``t_am`` (C3: named as tuple text).
"""

from __future__ import annotations

import pandas as pd

from simple_steps_core import Catalog, Kernel, mod, tool, wf


def names(k: Kernel, step: str) -> list:
    return [c["name"] for c in k.view(step)["columns"]]


def test_duplicate_names_are_suffixed_and_said():
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame([[1, 2, 3]], columns=["a", "a", "a"])
    assert names(k, "d") == ["a", "a_1", "a_2"]
    assert [c.get("value") for c in k.view("d")["rows"][0]["cells"].values()] == [1, 2, 3]
    assert any("a_1" in str(w) for w in k.step("d").warnings)


def test_names_that_collide_once_made_text_are_still_refused():
    """Two different names made one by making them text (0 and "var0"):
    refused, naming both, as core-asks L21b asks. Whether they are suffixed
    instead is open, for the owner (2026-11-25)."""
    import pytest
    from simple_steps_core.errors import SelectionError
    k = Kernel(Catalog(tools=[]))
    with pytest.raises(SelectionError, match="are both 'var0'"):
        k["d"] = pd.DataFrame([[1, 2]], columns=[0, "var0"])


def test_hierarchical_columns_are_flattened_with_an_underscore():
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame([[1, 2]], columns=pd.MultiIndex.from_tuples([("t", "am"), ("t", "pm")]))
    assert names(k, "d") == ["t_am", "t_pm"]


def test_a_table_tools_duplicate_columns_are_suffixed_too():
    @tool
    def twice(frame: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame([[1, 2]], columns=["x", "x"])
    k = Kernel(Catalog(tools=[twice]))
    k["d"] = pd.DataFrame({"x": [1]})
    k["t"] = twice[mod.table()](wf["d"])
    k.run("t")
    assert names(k, "t") == ["x", "x_1"]
    assert any("x_1" in str(w) for w in k.step("t").warnings)
