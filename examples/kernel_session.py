"""A kernel session, start to finish: what docs/design/kernel-session.md shows.

Run it with ``python examples/kernel_session.py``. Each part prints what a
terminal shows; tests/integration/test_kernel_session_example.py runs it and
checks the answers, so the guide can't drift from what core does.
"""

from __future__ import annotations

import pandas as pd

from simple_steps_core import (Catalog, Kernel, bound_tool, mod, res, resource,
                               tool, wf, zip_)


# ── 1. tools and resource types: plain Python, described ─────────────────
@tool
def patients() -> pd.DataFrame:
    """The ward's patients today."""
    return pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "temp_c": [36.6, 38.2, 37.1]})


@tool(extras={"simple_steps.ui": {"temp_c": "slider"}})
def to_f(temp_c: float) -> float:
    """Celsius to Fahrenheit."""
    return round(temp_c * 9 / 5 + 32, 2)


@tool
def feverish(temp_c: float, limit: float = 38) -> bool:
    """Whether a temperature is a fever."""
    return temp_c >= limit


@resource
class Ward:
    """A ward, built from literal settings."""

    def __init__(self, name: str = "A"):
        self.name = name

    @bound_tool
    def bed(self, name: str) -> str:
        return f"{self.name}-{name[0]}"


CATALOG = Catalog(tools=[patients, to_f, feverish], resources=[Ward])


def build() -> Kernel:
    """2. Construct a workflow: each line is checked and planned at once."""
    k = Kernel(CATALOG)
    k["p"] = patients[mod.source()]()                         # a source tool
    k["limit"] = 38.0                                         # a value: a control
    k["sick"] = feverish[mod.filter()](wf["p"], limit=wf["limit"])
    k["f"] = to_f[mod.map()](wf["sick"])                      # one value per row
    k["side"] = zip_(wf["sick"], wf["f"])                     # results beside inputs
    k.define("ward", Ward, name="B")
    k["beds"] = res["ward"].bed[mod.map()](wf["sick"])        # a resource's tool
    return k


def main() -> None:
    k = build()
    print("── declared: nothing has run ──")
    print(k)
    print("needs_run:", k.needs_run())
    print("plan of f:", k.step("f").output.plan["rows"]["certainty"])

    print("\n── 3. run it and see the data ──")
    k.run_all()
    print(k)
    print(k.step("side").data)
    print("cell f[1] came from:", k.cell("f", 1)["inputs"][0]["values"])   # row id 1: Ben

    print("\n── 4. change it ──")
    k["limit"] = 37.0                                         # move the control
    print("needs_run:", k.needs_run())
    k.run("f")                                                # sick is stale: it passes through
    print("after run('f'):", k.needs_run())
    k.run_all()
    print("after run_all:", k.needs_run(), "| sick:", k.step("sick").data["name"].tolist())
    print("a proposal, checked without adding it:",
          k.check("g", to_f[mod.map()](wf["nowhere"]))[0].code)

    print("\n── 5. save, load, run ──")
    k.step("f").extras["simple_steps.ui"] = {"color": "red"}
    text = k.to_json()
    k2 = Kernel.from_json(text, CATALOG)
    print("same spec:", k2.spec == k.spec, "| states:", sorted({s.state for s in k2.steps}))
    k2.run_all()
    print("reloaded f:", k2.step("f").data["value"].tolist(),
          "| extras kept:", k2.step("f").extras)


if __name__ == "__main__":
    main()
