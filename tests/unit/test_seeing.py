"""Seeing the data truthfully (docs/design/phase4-plan.md, step B): an unrun
source's columns (K1), sizes and pages (K26), column types (K27), and reading
a stale step (K29)."""

from __future__ import annotations

from typing import Annotated, TypedDict

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, mod, tool, wf


class Row(TypedDict):
    city: str
    n: int


@tool
def load() -> Annotated[pd.DataFrame, Row]:
    return pd.DataFrame({"city": ["SF", "LA"], "n": [1, 2]})


@tool
def mixed(n: int):
    return n if n % 2 else str(n)


@tool
def doubled(n: int) -> int:
    return n * 2


@tool
def doubled_value(value: int) -> int:
    return value * 2


@pytest.fixture
def k():
    k = Kernel(Catalog(tools=[load, mixed, doubled, doubled_value]))
    k["x"] = pd.DataFrame({"n": list(range(120))})
    return k


def test_K1_an_unrun_source_plans_its_declared_columns(k):
    k["s"] = load[mod.source()]()
    assert k.step("s").plan["columns"] == {"certainty": "exact", "names": ["city", "n"]}


def test_K27_a_type_is_declared_else_unknown_then_observed_or_the_union(k):
    k["d"] = doubled[mod.map()](wf["x"])
    k["m"] = mixed[mod.map()](wf["x"])
    assert k.step("d").plan["types"] == {"value": "int"}            # declared
    assert k.step("m").plan["types"] == {"value": "unknown"}        # not until it runs
    k.run_all()
    assert k.step("m").plan["types"] == {"value": "int | str"}      # observed: a mix


def test_K26_a_plan_says_its_size_and_a_view_is_a_page(k):
    k["d"] = doubled[mod.map()](wf["x"])
    assert k.step("d").plan["size"]["certainty"] == "unknown"
    assert "hasn't run" in k.step("d").plan["size"]["because"]
    k.run_all()
    size = k.step("d").plan["size"]
    assert size["certainty"] == "exact" and size["rows"] == 120 and size["bytes"] > 0
    assert k.view("d")["window"] == {"start": 0, "stop": 50, "of": 120}
    assert k.view("d", rows=(100, 150))["window"] == {"start": 100, "stop": 120, "of": 120}


def test_K29_reading_a_stale_step_warns_naming_it_and_its_version(k):
    k["d"] = doubled[mod.map()](wf["x"])
    k.run_all()
    version = k.step("d").output.version
    k["x"] = pd.DataFrame({"n": [5]})                               # d is stale now
    k["e"] = doubled_value[mod.map()](wf["d"])
    k.run("e")
    warning = " ".join(str(w) for w in k.step("e").warnings)
    assert "read 'd' while it's stale" in warning and version in warning
