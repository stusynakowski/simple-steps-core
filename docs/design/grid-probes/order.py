"""Does the order modifiers are written in change what a step does?
(docs/design/blocks.md §0, the ordered components; finding O1.)

    .venv/bin/python docs/design/grid-probes/order.py
"""
import pandas as pd

from simple_steps_core import Catalog, Kernel, mod, tool, wf

calls: list[float] = []
tried: set[float] = set()


@tool
def flaky(x: float) -> float:
    calls.append(x)
    if x == 2.0 and x not in tried:          # row 1 fails on its first try only
        tried.add(x)
        raise ValueError("first try fails")
    return x * 10


k = Kernel(Catalog(tools=[flaky]))
k["p"] = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
for label, mods in [("[map, retry]", (mod.map(), mod.retry(times=2))),
                    ("[retry, map]", (mod.retry(times=2), mod.map()))]:
    calls.clear()
    tried.clear()
    k["s"] = flaky[mods](wf["p"])
    try:
        k.run("s", force=True)
    except Exception:
        pass
    values = [r["cells"]["s"].get("value", r["cells"]["s"]["state"]) for r in k.view("s")["rows"]]
    print(f"{label}: written {k.step('s').formula} | tool calls {calls} | "
          f"{k.step('s').state} {values}")
    del k["s"]
