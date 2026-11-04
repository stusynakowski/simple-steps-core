"""S3's binding (CA-A): decided when a step is written, saved in its expression.

A required parameter takes the column of its name. Failing that, it takes the
one column whose type fits, written into the expression, so the saved step
says what runs. Two that fit, or none, make the step ``invalid``, writing the
fix. A parameter with a default takes a column only when bound to it.
"""

from __future__ import annotations

import pandas as pd

from simple_steps_core import Catalog, Kernel, cols, mod, tool, wf


@tool
def double_b(n: int) -> int:
    return n * 2


@tool
def half_b(x: float) -> float:
    return x / 2


@tool
def shout_b(s: str) -> str:
    return s.upper()


@tool
def scale_b(x: int, factor: int = 2) -> int:
    return x * factor


@tool
def load_b() -> pd.DataFrame:
    return pd.DataFrame({"d": [1, 2]})


def kernel():
    k = Kernel(Catalog(tools=[double_b, half_b, shout_b, scale_b, load_b]))
    k["r"] = pd.DataFrame({"name": ["a", "b"], "count": [1, 2]})
    return k


def test_the_one_column_whose_type_fits_is_bound_and_written():
    k = kernel()
    k["x"] = double_b[mod.map()](wf["r"])
    assert k.step("x").formula == 'double_b[mod.map()](wf["r"], n=wf["r"][cols["count"]])'
    k.run_all()
    assert k.step("x").data["x"].tolist() == [2, 4]


def test_an_int_column_fits_a_float():
    k = kernel()
    k["x"] = half_b[mod.map()](wf["r"])
    k.run_all()
    assert k.step("x").data["x"].tolist() == [0.5, 1.0]


def test_two_columns_that_fit_are_named_with_the_binding_to_write():
    k = kernel()
    k["two"] = pd.DataFrame({"a": [1], "b": [2]})
    k["x"] = double_b[mod.map()](wf["two"])
    st = k.step("x")
    assert st.state == "invalid" and [p.code for p in st.problems] == ["missing_column"]
    assert "2 columns are int, a, b: bind one, n=wf['two'][cols['a']]" in st.problems[0]


def test_no_column_that_fits_suggests_a_cast():
    k = kernel()
    k["nums"] = pd.DataFrame({"count": [1]})
    k["x"] = shout_b[mod.map()](wf["nums"])
    assert "No column of 'nums' is str (count: int): convert one, mod.cast(count='str')" \
        in k.step("x").problems[0]


def test_a_parameter_with_a_default_is_not_bound_by_name():
    k = kernel()
    k["xf"] = pd.DataFrame({"x": [1, 2], "factor": [10, 10]})
    k["kept"] = scale_b[mod.map()](wf["xf"])
    k["bound"] = scale_b[mod.map()](wf["xf"], factor=wf["xf"][cols["factor"]])
    k.run_all()
    assert k.step("kept").data["kept"].tolist() == [2, 4]       # factor's default
    assert k.step("bound").data["bound"].tolist() == [10, 20]    # bound on purpose


def test_a_name_match_is_not_written():
    k = kernel()
    k["c"] = pd.DataFrame({"n": [3]})
    k["x"] = double_b[mod.map()](wf["c"])
    assert k.step("x").formula == 'double_b[mod.map()](wf["c"])'


def test_binding_waits_until_the_input_is_planned():
    k = Kernel(Catalog(tools=[double_b, load_b]))
    k["s"] = load_b[mod.source()]()                  # its columns are unknown until it runs
    k["x"] = double_b[mod.map()](wf["s"])
    assert "n=" not in k.step("x").formula
    k.run("s")
    assert k.step("x").formula == 'double_b[mod.map()](wf["s"], n=wf["s"][cols["d"]])'
    k.run_all()
    assert k.step("x").data["x"].tolist() == [2, 4]
