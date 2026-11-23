"""widen on uneven data: each kind of cell, ragged rows, declared fields, and
what the plan knows before the run (expression-grammar/primitives.md §7).
The integer-keys case is commented out: it crashes the view (W2).

    .venv/bin/python docs/design/grid-probes/widen.py
"""
import pandas as pd
from typing import NamedTuple
from simple_steps_core import Catalog, Kernel, mod, tool, wf

class RGB(NamedTuple):
    r: int; g: int; b: int

@tool
def rec(x: float) -> RGB: return RGB(1, 2, 3)

def show(label, values, **kw):
    k = Kernel(Catalog(tools=[rec]))
    k["d"] = pd.DataFrame({"id": list(range(len(values))), "v": values})
    k["w"] = mod.widen("v", **kw)(wf["d"])
    plan = k.step("w").plan
    try:
        k.run("w")
    except Exception as e:
        print(f"{label:28} RUN ERR {str(e)[:100]}"); return
    v = k.view("w")
    names = [c["name"] for c in v["columns"]]
    rows = [[(r["cells"][c].get("value") if r["cells"][c]["state"] == "known" else r["cells"][c]["state"]) for c in names] for r in v["rows"]]
    planned = [c for c in (plan.get("columns", {}).get("names") or [])] if isinstance(plan.get("columns"), dict) else plan.get("columns")
    warn = [w.message[:60] for w in k.step("w").warnings]
    print(f"{label:28} {k.step('w').state:9} cols {names} rows {rows} | planned {planned} {warn}")

show("list [1,2],[3]", [[1, 2], [3]])
show("tuple (1,2),(3,4)", [(1, 2), (3, 4)])
show("dict ragged", [{"a": 1}, {"a": 2, "b": 3}])
show("dict + None", [{"a": 1}, None])
show("dict + str", [{"a": 1}, "oops"])
show("nested dict", [{"a": {"z": 1}}])
# show("int keys", [{1: "x", 2: "y"}])
show("declared columns=", [{"a": 1, "b": 2}], columns=["a"])
show("declared, missing key", [{"a": 1}], columns=["a", "b"])
show("NamedTuple cells", [RGB(1, 2, 3), RGB(4, 5, 6)])
show("str", ["ab", "cd"])

# More cases (2026-11-23): empty mappings and sequences, None values, a
# clash with a kept column, zero rows, mixed types, '#' keys, names that
# collide once made strings.
print()
show("empty dict {}", [{}, {"a": 1}])
show("key present, value None", [{"a": None}, {"a": 1}])
show("mixed value types per key", [{"a": 1}, {"a": "x"}])
show("key with a #", [{"#a": 1}])
show("keys 1 and '1'", [{1: "x", "1": "y"}])
show("empty tuple ()", [(), (1,)])
show("all None", [None, None])
