"""Identity and reproducibility (phase4-plan.md step C): tool hashes, ids,
diffs (K20), resource data versions (K25) and secret settings (R3)."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pandas as pd
import pytest

from simple_steps_core import Catalog, Kernel, Secret, mod, res, resource, tool, wf
from simple_steps_core.errors import ResourceNotLoaded


@tool
def patients_i() -> pd.DataFrame:
    return pd.DataFrame({"temp_c": [36.6, 38.2]})


@tool(tags=["temp"], extras={"simple_steps.ui": {"temp_c": "slider"}})
def to_f_i(temp_c: float) -> float:
    return round(temp_c * 1.8 + 32, 2)


@tool(id="to_f_i")
def to_f_i_v2(temp_c: float) -> float:
    return round(temp_c * 9 / 5 + 32, 1)


@resource
class Ward:
    """A ward whose list of beds changes: it says so with ``data_version``."""

    def __init__(self, name: str = "A"):
        self.name = name
        self.beds = [1, 2]

    def data_version(self) -> str:
        return str(len(self.beds))


@tool
def beds(ward: Ward) -> list[int]:
    return list(ward.beds)


@resource
class Db:
    def __init__(self, url: str, password: Secret[str]):
        self.url, self.password = url, password


@tool
def ping(db: Db) -> str:
    return f"{db.url} ok" if db.password else "no password"


def kernel(cat: Catalog | None = None) -> Kernel:
    k = Kernel(cat or Catalog(tools=[patients_i, to_f_i]))
    k["p"] = patients_i[mod.source()]()
    k["f"] = to_f_i[mod.map()](wf["p"])
    return k


# ── K20: tool hashes ─────────────────────────────────────────────────────
def test_a_tool_hash_is_its_code_never_its_tags_or_extras():
    plain = tool(to_f_i.fn)
    assert plain.hash == to_f_i.hash                 # tags and extras aren't code
    assert to_f_i_v2.hash != to_f_i.hash             # same name, other code
    assert len(to_f_i.hash) == 16


def test_the_catalog_spec_carries_each_tools_hash():
    spec = Catalog(tools=[to_f_i]).spec
    assert spec.tools["to_f_i"]["hash"] == to_f_i.hash


# ── K20: ids ─────────────────────────────────────────────────────────────
def test_extras_never_change_an_id():
    a, b = kernel(), kernel()
    b.step("f").extras["simple_steps.ui"] = {"color": "red"}
    b.extras["simple_steps.meta"] = {"title": "Fever"}
    assert a.id == b.id and a.step("f").id == b.step("f").id
    assert a.spec != b.spec                           # the spec still compares them
    assert a.diff(b) == {}


def test_an_id_survives_save_and_load():
    k = kernel()
    loaded = Kernel.from_json(k.to_json(), Catalog(tools=[patients_i, to_f_i]))
    assert loaded.id == k.id
    assert [s.id for s in loaded.steps] == [s.id for s in k.steps]


def test_an_id_is_the_same_in_another_process():
    """No memory addresses or process-local hashing in an id."""
    script = textwrap.dedent("""
        import sys; sys.path.insert(0, "tests/unit")
        from test_identity import kernel
        print(kernel().id)
    """)
    other = subprocess.run([sys.executable, "-c", script], capture_output=True,
                           text=True, check=True).stdout.strip()
    assert other == kernel().id


def test_a_change_upstream_changes_every_id_after_it():
    a, b = kernel(), kernel()
    a["p"], b["p"] = [36.6, 38.2], [36.6]
    assert a.step("p").id != b.step("p").id
    assert a.step("f").id != b.step("f").id          # f's input changed
    assert a.id != b.id
    assert a.diff(b) == {"steps": {"p": "recipe", "f": "input p"},
                         "data": ["p"]}               # a literal holds its data


def test_diff_says_which_step_and_why():
    a = kernel()
    b = kernel(Catalog(tools=[patients_i, to_f_i_v2]))
    b["t"] = 38
    assert a.diff(b) == {"steps": {"f": "tool", "t": "added"}}
    assert b.diff(a) == {"steps": {"f": "tool", "t": "removed"}}


def test_run_id_follows_the_data():
    a, b = kernel(), kernel()
    assert a.run_id == b.run_id                       # nothing run: same
    a.run_all()
    assert a.run_id != b.run_id and a.id == b.id      # same recipe, other data
    b.run_all()
    assert a.run_id == b.run_id and a.diff(b) == {}


def test_a_step_that_cant_be_saved_has_no_id():
    k = Kernel(Catalog())
    k["t"] = [1, 2]
    assert k.step("t").id is not None
    k["s"] = mod.select(columns=lambda c: True)(wf["t"])
    assert k.step("s").id is None
    with pytest.raises(Exception, match="has no id"):
        k.id


# ── K20: a changed tool marks its steps stale ────────────────────────────
def test_a_changed_tool_marks_its_steps_stale():
    """What a kernel whose outputs outlive its catalog sees (a store, step E,
    or a catalog swap): the code a step ran with is no longer the tool's."""
    k = kernel()
    k.run_all()
    ran_with = k.step("f").output.meta["tool_hash"]
    assert ran_with == to_f_i.hash
    k.workflow.catalog = Catalog(tools=[patients_i, to_f_i_v2])
    k.workflow._refresh_staleness()
    assert k.step("f").state == "stale"
    assert k.needs_run() == {"f": "stale: tool changed"}
    assert k.step("p").state == "completed"           # its tool didn't change


# ── K25: a resource's data version ───────────────────────────────────────
def test_a_resource_that_reports_new_data_makes_its_users_stale():
    k = Kernel(Catalog(tools=[beds], resources=[Ward]))
    k.define("ward", Ward)
    k["b"] = beds[mod.source()](ward=res["ward"])
    k.run_all()
    assert k.step("b").state == "completed"
    assert k.needs_run() == {}                        # asked again: nothing new
    k.resources["ward"].beds.append(3)
    assert k.needs_run() == {"b": "stale: resource ward changed"}
    k.run("b")
    assert k.step("b").output.data["value"].tolist() == [[1, 2, 3]]
    assert k.needs_run() == {}


def test_a_data_version_is_not_part_of_the_recipe():
    k = Kernel(Catalog(tools=[beds], resources=[Ward]))
    k.define("ward", Ward)
    k["b"] = beds[mod.source()](ward=res["ward"])
    before = k.id
    k.run_all()
    k.resources["ward"].beds.append(3)
    k.needs_run()
    assert k.id == before                             # same recipe…
    assert "ward" in k.workflow.data_versions         # …other data, in run_id


# ── R3: secrets ──────────────────────────────────────────────────────────
def secret_kernel() -> Kernel:
    k = Kernel(Catalog(tools=[ping], resources=[Db]))
    k.define("db", Db, url="sqlite://", password="hunter2")
    k["p"] = ping[mod.source()](db=res["db"])
    return k


def test_a_secret_is_never_saved_hashed_or_shown():
    k = secret_kernel()
    assert "hunter2" not in k.to_json()
    assert "hunter2" not in repr(k.workflow.resources["db"])
    assert "password=•••" in repr(k.workflow.resources["db"])
    other = Kernel(Catalog(tools=[ping], resources=[Db]))
    other.define("db", Db, url="sqlite://", password="something else")
    other["p"] = ping[mod.source()](db=res["db"])
    assert other.id == k.id                           # a secret isn't in the id
    k.run_all()
    assert k.step("p").output.data["value"].tolist() == ["sqlite:// ok"]


def test_a_new_secret_doesnt_make_anything_stale():
    k = secret_kernel()
    k.run_all()
    k.define("db", Db, url="sqlite://", password="rotated")
    assert k.step("p").state == "completed"


def test_a_loaded_kernel_asks_for_its_secret():
    cat = Catalog(tools=[ping], resources=[Db])
    loaded = Kernel.from_json(secret_kernel().to_json(), cat)
    assert json.loads(loaded.to_json())["resources"]["db"]["settings"] == {"url": "sqlite://"}
    with pytest.raises(ResourceNotLoaded, match="needs its secret 'password'"):
        loaded.run_all()                              # as a resource not loaded does
    loaded.define("db", Db, url="sqlite://", password="hunter2")
    loaded.run_all()
    assert loaded.step("p").state == "completed"


def test_a_secret_setting_is_shown_as_one():
    entry = Catalog(resources=[Db]).describe()["resource_types"]["Db"]
    assert {"name": "password", "type": "Secret[str]", "required": True,
            "default": None} in entry["settings"]


# ── a resource is an argument, by keyword or by position ─────────────────
def test_a_resource_passed_by_position_is_the_tools_argument():
    k = Kernel(Catalog(tools=[beds, patients_i, to_f_i], resources=[Ward]))
    k.define("ward", Ward)
    k["by_name"] = beds[mod.source()](ward=res["ward"])
    k["by_place"] = beds[mod.source()](res["ward"])
    assert k.step("by_place").operation.to_dict() == k.step("by_name").operation.to_dict()
    k.run_all()
    assert k.step("by_place").data["value"].tolist() == [[1, 2]]


def test_a_plain_call_with_a_resource_says_to_make_a_step():
    with pytest.raises(TypeError, match=r"has no object until the workflow runs"):
        beds(res["ward"])


# ── T2–T4 (app-migration.md §7): what the app reads from core ────────────
def test_the_app_imports_everything_from_the_package():
    import simple_steps_core as core
    for name in ("op", "StepFailed", "SelectionError", "ResourceNotLoaded",
                 "PayloadError", "Secret"):
        assert name in core.__all__ and hasattr(core, name)


def test_describe_gives_each_tools_hash():
    tools = Catalog(tools=[to_f_i]).describe()["tools"]
    assert tools["to_f_i"]["hash"] == to_f_i.hash
    assert len(tools["identity"]["hash"]) == 16      # built-ins: core's version


@tool
def hot_i(value: float) -> bool:
    return value > 37


def test_infer_verb_without_declaring_anything():
    k = Kernel(Catalog(tools=[hot_i, to_f_i]))
    k["p"] = [36.6, 38.2]
    k["e"] = mod.expand()(wf["p"])
    before = list(k.workflow.steps)
    assert k.infer_verb("hot_i", "e")[0] == "filter"
    assert k.infer_verb("hot_i") == ("source", "it reads no step")
    assert k.infer_verb("nope", "e") == ("map", "no tool named 'nope'")
    assert list(k.workflow.steps) == before


def test_formula_names_are_the_catalogs():
    names = Catalog(tools=[hot_i]).formula_names()
    assert {"wf", "res", "mod", "cols", "rows", "op", "join", "stack", "zip_",
            "hot_i", "identity"} <= set(names)
    assert "to_f_i" not in names
