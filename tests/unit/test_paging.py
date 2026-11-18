"""A page costs the page, not the step (the app's ask 014 C50; C52).

``k.view(step, (start, stop))`` and ``k.cell(step, row, column)`` read only the
rows they return, and give exactly what cutting the full view gives; a step's
state is read without building a state per row.
"""

import time

import numpy as np
import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, op, tool, wf


@tool
def double(n: float) -> float:
    return n * 2


@tool
def risky(n: float) -> float:
    if n % 3 == 1:
        raise ValueError("one more than a multiple of three")
    return n


@tool
def pair(n: float) -> list:
    return [n, n + 0.5]


@tool
def big(n: float) -> bool:
    return n > 4


CAT = Catalog(tools=[double, risky, pair, big])


@pytest.fixture
def k():
    k = Kernel(CAT)
    k["src"] = pd.DataFrame({"n": np.arange(10, dtype=float), "ward": list("ABABABABAB")})
    k["d"] = double[mod.map()](wf["src"])
    k["r"] = risky[mod.map(), mod.try_except()](wf["src"])             # failed rows
    k["e"] = pair[mod.expand()](wf["src"])                            # lineage, .idx
    k["c"] = op("gather")[mod.collapse(by="ward")](wf["src"])         # list lineage
    k.run_all()
    k["src"] = pd.DataFrame({"n": np.r_[np.arange(9), 99.0], "ward": list("ABABABABAB")})
    k.run("src")                                                      # d, r, e stale
    k["f"] = big[mod.filter()](wf["d"])                              # staged: maybe rows
    return k


WINDOWS = [(0, 3), (4, 7), (8, 10), (5, 50), (12, 20), (-3, 10), (0, 0), (3, 3)]


@pytest.mark.parametrize("step", ["src", "d", "r", "e", "c", "f"])
@pytest.mark.parametrize("window", WINDOWS)
def test_a_page_is_the_full_view_cut(k, step, window):
    full = k.view(step, None)
    page = k.view(step, window)
    assert page["rows"] == full["rows"][slice(*window)]
    assert page["window"] == {"start": window[0], "stop": min(window[1], full["window"]["of"]),
                              "of": full["window"]["of"]}
    assert {key: v for key, v in page.items() if key not in ("rows", "window")} == \
        {key: v for key, v in full.items() if key not in ("rows", "window")}


@pytest.mark.parametrize("step", ["src", "d", "r", "e", "c", "f"])
def test_a_cell_is_its_row_of_the_full_view(k, step):
    full = k.view(step, None)
    columns = [c["name"] for c in full["columns"]]
    for row in range(-len(full["rows"]), len(full["rows"]) + 2):
        for column in columns:
            cell = k.cell(step, row, column)
            if -len(full["rows"]) <= row < len(full["rows"]):
                entry = full["rows"][row]
                expected = entry["cells"].get(column, {"state": entry["state"]})
                assert {key: cell[key] for key in expected} == expected, (step, row, column)
                assert cell["lineage"] == entry["lineage"]
            else:
                assert cell["state"] in ("missing", "unknown"), (step, row, column)


def test_a_step_reads_its_state_as_before(k):
    assert {n: k.step(n).state for n in k.workflow.steps} == {
        "src": "completed", "d": "stale", "r": "stale", "e": "stale",
        "c": "stale", "f": "staged"}
    k.run_all()
    assert k.step("r").state == "failed"


def test_a_page_of_a_million_rows_costs_the_page():
    k = Kernel(CAT)
    k["src"] = pd.DataFrame({"n": np.arange(1_000_000, dtype=float)})
    k["d"] = double[mod.map()](wf["src"])
    k.run_all()
    k.view("d", (0, 50))                                   # warm
    timings = {}
    for label, call in [("first page", lambda: k.view("d", (0, 50))),
                        ("middle page", lambda: k.view("d", (500_000, 500_050))),
                        ("last page", lambda: k.view("d", (999_950, 1_000_000))),
                        ("a cell", lambda: k.cell("d", 999_999, "d")),
                        ("a state", lambda: k.step("d").state)]:
        started = time.perf_counter()
        call()
        timings[label] = time.perf_counter() - started
    # 13.6 s for a page and 0.3 s for a state at 1.0.3; generous bounds, so
    # a busy machine doesn't fail them
    assert max(timings.values()) < 0.5, timings
    assert k.view("d", (999_998, 1_000_000))["rows"][-1]["cells"]["d"]["value"] == 1_999_998.0
