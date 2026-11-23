"""expand (unnest into rows) on every kind of cell and uneven rows, beside
pandas' explode on the same cases (expression-grammar/expand.md).

    .venv/bin/python docs/design/grid-probes/expand.py
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from simple_steps_core import Catalog, Kernel, mod, op, wf


def core(label, frame, columns=("v",), **kw):
    k = Kernel(Catalog(tools=[]))
    k["d"] = frame
    try:
        k["e"] = op("identity")[mod.expand(columns=list(columns), **kw)](wf["d"])
        plan = k.step("e").plan.get("rows", {})
        k.run("e")
        v = k.view("e")
        names = [c["name"] for c in v["columns"]]
        rows = [[(r["cells"][c].get("value") if r["cells"][c]["state"] == "known"
                  else r["cells"][c]["state"]) for c in names] for r in v["rows"]]
        lin = [r.get("lineage") for r in v["rows"]]
        warn = [w.message[:50] for w in k.step("e").warnings]
        return f"{k.step('e').state:9} {names} {rows} lineage {lin} plan-rows {plan.get('certainty')} {warn}"
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:90]}"


def panda(frame, columns=("v",)):
    try:
        out = frame.explode(list(columns))
        return f"index {list(out.index)} rows {out.astype(object).where(out.notna(), '<NA>').values.tolist()}"
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:90]}"


def both(label, values, **kw):
    frame = pd.DataFrame({"id": list(range(len(values))), "v": pd.Series(values, dtype=object)})
    print(f"{label}\n   core:   {core(label, frame, **kw)}\n   pandas: {panda(frame)}")


both("ragged lists", [[1, 2, 3], [4]])
both("[] and None", [[1, 2], [], None])
both("tuple", [(1, 2)])
both("dict", [{"a": 1, "b": 2}])
both("set", [{1, 2}])
both("str", ["ab"])
both("scalar among lists", [[1, 2], 5])
both("ndarray", [np.array([1, 2])])
both("range", [range(2)])
both("nested lists", [[[1, 2], [3]]])
both("mixed item types", [[1, "x"]])

two = pd.DataFrame({"id": [0, 1], "a": [[1, 2], [3]], "b": [["x", "y"], ["z", "w"]]})
print(f"two columns, lengths differ\n   core:   {core('two', two, columns=('a', 'b'))}\n   pandas: {panda(two, ('a', 'b'))}")
same = pd.DataFrame({"id": [0], "a": [[1, 2]], "b": [["x", "y"]]})
print(f"two columns, same lengths\n   core:   {core('same', same, columns=('a', 'b'))}\n   pandas: {panda(same, ('a', 'b'))}")
clash = pd.DataFrame({"key": [9], "v": [{"a": 1}]})
print(f"dict, a column already named key\n   core:   {core('clash', clash)}")
