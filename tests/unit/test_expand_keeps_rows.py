"""Expand never loses a row (roadmap phase 2: I2; expand.md V4).

Owner, 2026-11-22: "keep row, absent": a cell with nothing to expand
(``[]``, ``()``, ``{}``, ``None``, a gap) keeps its row, its item absent, so
unnesting never loses a row. It is said, as a warning, but nothing is
dropped. Both paths: a tool's list (``mod.expand()``) and columns unpacked
(``mod.expand(columns=…)``).
"""

from __future__ import annotations

import pandas as pd

from simple_steps_core import Catalog, Kernel, mod, op, tool, wf


@tool
def parts(x: str) -> list:
    return [] if x == "" else x.split("-")


def run_view(k: Kernel, step: str) -> tuple[list, list, list]:
    k.run(step)
    v = k.view(step)
    names = [c["name"] for c in v["columns"]]
    rows = [[(r["cells"][c].get("value") if r["cells"][c]["state"] == "known"
              else r["cells"][c]["state"]) for c in names] for r in v["rows"]]
    return names, rows, [r.get("lineage", {}).get("#d") for r in v["rows"]]


def kernel(values: list) -> Kernel:
    k = Kernel(Catalog(tools=[parts]))
    k["d"] = pd.DataFrame({"id": list(range(len(values))),
                           "v": pd.Series(values, dtype=object)})
    return k


# ── a tool's list, or a cell's ──────────────────────────────────────────────
def test_an_empty_list_none_and_a_gap_keep_their_rows():
    k = kernel([[1, 2], [], None])
    k["e"] = op("identity")[mod.expand()](wf["d"]["v"])
    names, rows, parents = run_view(k, "e")
    assert rows == [[1], [2], ["absent"], ["absent"]]
    assert parents == [0, 0, 1, 2]                    # each kept row names its parent


def test_it_is_said():
    k = kernel([[1], [], None])
    k["e"] = op("identity")[mod.expand()](wf["d"]["v"])
    k.run("e")
    assert any("kept" in w and "absent" in w for w in k.step("e").warnings)


def test_an_empty_dict_keeps_its_row_its_key_and_value_absent():
    k = kernel([{"a": 1}, {}])
    k["e"] = op("identity")[mod.expand()](wf["d"]["v"])
    names, rows, _ = run_view(k, "e")
    assert dict(zip(names, rows[1])) == {"key": "absent", "value": "absent"}


def test_a_tool_returning_an_empty_list_keeps_the_row():
    k = Kernel(Catalog(tools=[parts]))
    k["d"] = pd.DataFrame({"x": ["a-b", "", "c"]})
    k["e"] = parts[mod.expand()](wf["d"])
    names, rows, parents = run_view(k, "e")
    assert rows == [["a"], ["b"], ["absent"], ["c"]]
    assert parents == [0, 0, 1, 2]


# ── columns unpacked ────────────────────────────────────────────────────────
def test_unpacking_columns_keeps_the_row_and_its_other_columns():
    k = kernel([[1, 2], [], None])
    k["e"] = op("identity")[mod.expand(columns=["v"])](wf["d"])
    names, rows, _ = run_view(k, "e")
    assert names == ["id", "v"]
    assert rows == [[0, 1], [0, 2], [1, "absent"], [2, "absent"]]


def test_an_empty_list_unpacked_was_lost_silently_and_is_kept_now():
    k = kernel([[], [3]])
    k["e"] = op("identity")[mod.expand(columns=["v"])](wf["d"])
    names, rows, _ = run_view(k, "e")
    assert rows == [[0, "absent"], [1, 3]]
    assert any("kept" in w for w in k.step("e").warnings)


def test_an_empty_dict_unpacked_keeps_its_row():
    k = kernel([{"a": 1}, {}])
    k["e"] = op("identity")[mod.expand(columns=["v"])](wf["d"])
    names, rows, _ = run_view(k, "e")
    assert names == ["id", "key", "v"]
    assert rows[1] == [1, "absent", "absent"]


# ── the row count ───────────────────────────────────────────────────────────
def test_expand_never_gives_fewer_rows_than_it_was_given():
    k = kernel([[1, 2], [], None, [3], {}])
    k["e"] = op("identity")[mod.expand()](wf["d"]["v"])
    k["e2"] = op("identity")[mod.expand(columns=["v"])](wf["d"])
    for step in ("e", "e2"):
        try:
            k.run(step)
        except Exception:
            pass
        assert len(k.view(step)["rows"]) >= 5
