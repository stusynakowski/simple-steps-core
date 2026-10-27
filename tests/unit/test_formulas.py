"""A step's formula prints as written, and declaring it gives back the same
step (G4)."""

from __future__ import annotations

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, Operation, cols, mod, tool, wf
from simple_steps_core.catalog import formula_names


@tool
def double_f(n: int) -> int:
    return n * 2


#: The names a formula may use (formula_names gives wf, mod, op, cols, rows,
#: the combines and the tools).
NAMES = formula_names({"double_f": double_f})

WRITTEN = [
    'wf["p"][0:2]', 'wf["p"][1]', 'wf["p"][cols["temp_c"]]', 'wf["p"][cols["name":"temp_c"]]',
    'wf["p"][cols[["name", "ward"]]]', 'wf["p"][1][cols["temp_c"]]',
    'wf["p"][0:2][cols["name":"temp_c"]]', 'wf["p"].header', 'wf["p"]', 'wf["p"][cols[0:2]]',
    'mod.sort(by="temp_c")(wf["p"])', 'mod.sort(by=["ward", "name"], ascending=False)(wf["p"])',
    'mod.drop(columns=["ward"])(wf["p"])', 'mod.rename(columns={"name": "who"})(wf["p"])',
    'mod.slice(start=0, stop=1)(wf["p"])', 'mod.distinct(columns=["ward"])(wf["p"])',
]


def kernel() -> Kernel:
    k = Kernel(Catalog(tools=[double_f]))
    k["p"] = pd.DataFrame({"name": ["a", "b"], "temp_c": [1.0, 2.0], "ward": ["A", "B"], "n": [1, 2]})
    return k


@pytest.mark.parametrize("text", WRITTEN)
def test_a_selection_or_reshape_prints_as_written(text):
    k = kernel()
    k["s"] = eval(text, {"__builtins__": {}}, NAMES)
    assert k.step("s").formula == text


@pytest.mark.parametrize("text", WRITTEN + [
    'mod.select(columns=["name"])(wf["p"])', 'wf["p"][rows[[0, 1]]]', 'wf["p"].header[1]',
    'double_f[mod.map(), mod.retry(times=2)](wf["p"])'])
def test_declaring_the_printed_formula_gives_the_same_step(text):
    k = kernel()
    k["s"] = eval(text, {"__builtins__": {}}, NAMES)
    printed = k.step("s").formula
    again = kernel()
    again["s"] = eval(printed, {"__builtins__": {}}, NAMES)
    assert again.step("s").spec.operation == k.step("s").spec.operation


def test_one_step_has_one_printed_form():
    k = kernel()
    k["a"] = mod.select(columns=["name"])(wf["p"])
    k["b"] = wf["p"][cols["name"]]
    assert k.step("a").formula == k.step("b").formula == 'wf["p"][cols["name"]]'


def test_a_reference_as_a_setting_keeps_the_select_form():
    k = kernel()
    k["which"] = ["name"]
    k["s"] = Operation(tool="identity")[mod.select(columns=wf["which"])](wf["p"])
    assert k.step("s").formula == 'mod.select(columns=wf["which"])(wf["p"])'
    k.run_all()
    assert k.step("s").data.to_dict("list") == {"name": ["a", "b"]}


def test_header_with_a_row_says_so_explicitly_until_c28():
    k = kernel()
    k["h"] = wf["p"].header[1]
    assert k.step("h").formula == 'mod.select(rows=1, columns={"header": True})(wf["p"])'


def test_a_literal_steps_formula_is_its_value():
    k = kernel()
    k["x"] = [3, 1, 2]
    assert k.step("x").formula == "[3, 1, 2]"
    assert k.step("p").formula == "<DataFrame 2×4>"
