"""Gaps and types in data you give (roadmap phase 2: F1, F2).

F1 (owner, 2026-11-24, "B"): every gap written into a data step (``NaN``,
``pd.NA``, ``None``) is **absent**: a blank you write is "no value". A known
``None`` comes only from a tool that returns ``None``.

F2 (owner, 2026-11-24): **a column's type is its dtype, as given**, never
worked out from its values. A float column holding only whole numbers and
gaps stays float (it used to become ``Int64``: 008 C14), and a warning says
how to make it integers, without changing anything.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from simple_steps_core import Catalog, Kernel, mod, stack, tool, wf

seen: list = []


@tool
def opt(y: Optional[float]) -> float:
    seen.append(y)
    return 0.0


@tool
def typed(y: float) -> float:
    return y


@tool
def load() -> pd.DataFrame:
    return pd.DataFrame({"x": [1.5, None]})


def states(k: Kernel, step: str, row: int) -> dict:
    return {c: v["state"] for c, v in k.view(step)["rows"][row]["cells"].items()}


# ── F1: a gap you write is absent ──────────────────────────────────────────
def test_every_kind_of_gap_in_a_data_step_is_absent():
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({
        "f_nan": [1.5, np.nan],
        "F_na": pd.array([1.5, None], dtype="Float64"),
        "o_none": pd.Series(["a", None], dtype=object),
        "s_na": pd.array(["a", None], dtype="string"),
        "i_na": pd.array([1, None], dtype="Int64"),
    })
    assert set(states(k, "d", 1).values()) == {"absent"}
    assert set(states(k, "d", 0).values()) == {"known"}


def test_an_absent_cell_shows_no_value():
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({"x": [1.5, None]})
    cell = k.cell("d", 1, "x")
    assert cell["state"] == "absent"
    assert "value" not in cell or cell["value"] is None


def test_a_tool_still_gets_none_for_a_gap_when_it_accepts_one():
    k = Kernel(Catalog(tools=[opt]))
    k["d"] = pd.DataFrame({"y": [None, 5.5]})
    k["m"] = opt[mod.map()](wf["d"])
    seen.clear()
    k.run("m")
    assert seen == [None, 5.5]


def test_a_tool_that_doesnt_accept_a_gap_is_still_refused_when_declared():
    k = Kernel(Catalog(tools=[typed]))
    k["d"] = pd.DataFrame({"y": [None, 5.5]})
    k["m"] = typed[mod.map()](wf["d"])
    assert k.step("m").problems


def test_a_source_tools_gap_is_absent_too():
    k = Kernel(Catalog(tools=[load]))
    k["s"] = load[mod.source()]()
    k.run("s")
    assert states(k, "s", 1) == {"x": "absent"}


def test_values_copied_from_a_stack_keep_their_gaps_absent():
    """The finding: a stack's absent cells, written into a data step, were
    known ``None``."""
    k = Kernel(Catalog(tools=[]))
    k["a"] = pd.DataFrame({"x": [1.0]})
    k["b"] = pd.DataFrame({"y": [2.0]})
    k["s"] = stack(wf["a"], wf["b"])
    k.run_all()
    out = k.step("s").output
    k["copy"] = out.data[["x", "y"]].copy()
    assert states(k, "copy", 0)["y"] == "absent"
    assert states(k, "copy", 1)["x"] == "absent"


def test_gaps_stay_absent_when_the_data_is_replaced():
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({"x": [1.0, None, 3.0]})
    k["d"] = pd.DataFrame({"x": [1.0, None, 3.0, 4.0]})
    assert states(k, "d", 1) == {"x": "absent"}
    assert states(k, "d", 3) == {"x": "known"}


def test_gaps_stay_absent_through_save_and_load(tmp_path):
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({"x": [1.0, None], "t": ["a", None]})
    k.save(tmp_path)
    back = Kernel.load(tmp_path, Catalog(tools=[]))
    assert states(back, "d", 1) == {"x": "absent", "t": "absent"}


# ── F2: the dtype decides ──────────────────────────────────────────────────
def test_a_float_column_of_whole_numbers_and_gaps_stays_float():
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({"t": [37.0, None, 38.0]})
    assert str(k.step("d").output.data["t"].dtype) == "float64"
    assert k.cell("d", 0, "t")["value"] == 37.0
    assert isinstance(k.cell("d", 0, "t")["value"], float)


def test_it_is_warned_with_the_way_to_make_it_integers():
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({"t": [37.0, None, 38.0]})
    messages = [w for w in k.step("d").warnings]
    assert any("t" in m and "Int64" in m for m in messages)


def test_a_declared_nullable_float_column_stays_float():
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({"x": pd.array([1.0, None], dtype="Float64")})
    assert str(k.step("d").output.data["x"].dtype) == "Float64"


def test_a_declared_integer_column_stays_integers_and_isnt_warned():
    k = Kernel(Catalog(tools=[]))
    k["d"] = pd.DataFrame({"n": pd.array([1, None, 3], dtype="Int64")})
    assert str(k.step("d").output.data["n"].dtype) == "Int64"
    assert not k.step("d").warnings


def test_floats_with_a_fraction_or_with_no_gap_arent_warned():
    k = Kernel(Catalog(tools=[]))
    k["a"] = pd.DataFrame({"x": [1.5, None]})
    k["b"] = pd.DataFrame({"x": [1.0, 2.0]})
    assert not k.step("a").warnings
    assert not k.step("b").warnings


def test_a_tool_gets_the_float_not_an_int():
    k = Kernel(Catalog(tools=[opt]))
    k["d"] = pd.DataFrame({"y": [None, 5.0]})
    k["m"] = opt[mod.map()](wf["d"])
    seen.clear()
    k.run("m")
    assert seen == [None, 5.0]
    assert isinstance(seen[1], float)
