"""Formula text, read (decisions.md EX13): `formula(text)` gives the step the
text writes, the same spec as the line written in Python; it never runs the
text; a plain string assigned to a step stays a string value."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from simple_steps_core import (Catalog, FormulaError, Kernel, bound_tool, cols, formula,
                               join, mod, op, res, resource, row, rows, stack, tool, wf,
                               zip_)


@tool
def patients_x() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ann", "Ben"], "ward": ["A", "B"], "temp": [36.6, 38.2]})


@tool
def to_f_x(temp: float, digits: int = 1) -> float:
    return round(temp * 1.8 + 32, digits)


@tool
def hot_x(temp: float, limit: float = 38) -> bool:
    return temp >= limit


@tool
def two_x(temp: float) -> list:
    return [temp, temp + 1]


@tool
def label_x(a: int, b: str) -> str:
    return f"{a}{b}"


@resource
class Lab_x:
    def __init__(self, scale: float = 1.0):
        self.scale = scale

    @bound_tool
    def adjust(self, temp: float) -> float:
        return temp * self.scale


CAT = Catalog(tools=[patients_x, to_f_x, hot_x, two_x, label_x], resources=[Lab_x])


def written() -> dict:
    """One of each kind of expression, written in Python."""
    return {
        "p": patients_x[mod.source()](),
        "f": to_f_x[mod.map(), mod.name("temp_f")](wf["p"], digits=2),
        "h": hot_x[mod.filter()](wf["p"], limit=wf["lim"]),
        "a": hot_x(wf["p"]),
        "e": two_x[mod.expand(), mod.expect(rows=4), mod.retry(times=2)](wf["p"]),
        "c": op("count")[mod.collapse(by="ward")](wf["p"]),
        "s": mod.sort(by="temp", ascending=False)(wf["p"]),
        "w": mod.widen("rec")(wf["pk"]),
        "pk": op("identity")[mod.pack(columns=["name", "temp"]), mod.name("rec")](wf["p"]),
        "x": label_x[mod.sweep(a=[1, 2], b=["x"])](),
        "r": res["lab"].adjust[mod.map()](wf["p"]),
        "j": join(wf["p"], wf["s"], on="#p", how="left"),
        "z": zip_(wf["p"], wf["f"]),
        "st": stack(wf["p"], wf["s"]),
        "one": wf["p"][1],
        "range": wf["p"][0:2],
        "cond": wf["p"][(cols["temp"] > 37) & ~cols["ward"].isin(["C"])],
        "lin": wf["e"][row["p"] == 1],
        "must": wf["p"][rows[cols["temp"] > 30]][cols["name"]],
        "arg": hot_x[mod.filter()](wf["p"], limit=wf["p"][0][cols["temp"]]),
    }


def kernel(steps: dict) -> Kernel:
    k = Kernel(CAT)
    k["lim"] = 38.0
    k.define("lab", Lab_x, scale=2.0)
    for name, expression in steps.items():
        k[name] = expression
    return k


def test_every_kind_of_step_reads_back_as_the_same_spec():
    k = kernel(written())
    names = [s.name for s in k.steps if s.name not in ("lim",)]
    again = kernel({n: formula(k.step(n).formula) for n in names})
    for n in names:
        assert again.step(n).spec == k.step(n).spec, n
        assert again.step(n).formula == k.step(n).formula, n


def test_a_formula_runs_like_the_line_it_writes():
    k = Kernel(CAT)
    k["p"] = formula("patients_x[mod.source()]()")
    k["f"] = formula('= to_f_x[mod.map()](wf["p"])')           # the app's leading = is fine
    k.run_all()
    assert k.step("f").data["value"].tolist() == [97.9, 100.8]


def test_a_plain_string_stays_a_string_value():
    k = Kernel(CAT)
    k["g"] = "to_f_x[mod.map()](wf['p'])"
    assert k.step("g").data["value"].tolist() == ["to_f_x[mod.map()](wf['p'])"]


def test_a_tool_not_in_the_catalog_is_a_problem_when_assigned():
    k = Kernel(CAT)
    k["p"] = formula("patients_x[mod.source()]()")
    k["x"] = formula('os_remove[mod.map()](wf["p"])')
    assert k.step("x").state == "invalid"
    assert "'os_remove' is not in this workflow's catalog" in k.step("x").problems[0].message


@pytest.mark.parametrize("text", [
    "__import__('os').system('touch PWNED')",
    "to_f_x[mod.map()](wf['p'], x=__import__('os').system('touch PWNED'))",
    "to_f_x[mod.map()](wf['p'], x=open('/etc/passwd').read())",
    "to_f_x[mod.map()](wf['p'], x=(lambda: 1)())",
    "to_f_x.__class__.__subclasses__()",
    "[c for c in ().__class__.__bases__[0].__subclasses__()]",
    "mod.map.__globals__", "wf.__dict__", "_secret", "res['lab']._fn",
    "eval('1')", "exec('import os')", "identity('x')", "f'{1}'", "1 if True else 2",
    "wf['p'] + 1", "(x := 1)", "op('to_f_x').fn", "wf['p'][0]()", "to_f_x(**{'a': 1})",
])
def test_a_formula_never_runs_python(text, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FormulaError):
        formula(text)
    assert not Path("PWNED").exists()


def test_a_formula_that_isnt_python_says_so():
    with pytest.raises(FormulaError, match="not a formula"):
        formula("to_f_x[mod.map()](wf['p']")
