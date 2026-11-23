"""Unnesting each kind of Python iterable a cell can hold: expand (into rows)
and widen (into columns) (docs/design/blocks.md §5).

    .venv/bin/python docs/design/grid-probes/iterables.py
"""
import numpy as np, pandas as pd
from simple_steps_core import Catalog, Kernel, mod, wf, op
kinds = {
    "list [1, 2]": [1, 2], "tuple (1, 2)": (1, 2), "set {1, 2}": {1, 2},
    "dict {'a': 1, 'b': 2}": {"a": 1, "b": 2}, "str 'ab'": "ab",
    "ndarray [1, 2]": np.array([1, 2]), "ndarray 2×2": np.ones((2, 2)),
    "range(2)": range(2), "DataFrame 2 rows": pd.DataFrame({"z": [1, 2]}),
    "empty list": [], "None": None,
}
for label, v in kinds.items():
    k = Kernel(Catalog(tools=[]))
    try:
        k["d"] = pd.DataFrame({"v": [v]})
    except Exception as e:
        print(f"{label:24} data step refused: {str(e)[:80]}"); continue
    out = {}
    for verb, made in [("expand", lambda: op("identity")[mod.expand(columns=["v"])](wf["d"])),
                       ("widen", lambda: mod.widen("v")(wf["d"]))]:
        try:
            k[verb] = made()
            if k.step(verb).problems:
                out[verb] = "refused: " + k.step(verb).problems[0].message[:60]; continue
            k.run(verb)
            vw = k.view(verb)
            names = [c["name"] for c in vw["columns"]]
            vals = [[r["cells"][c].get("value", r["cells"][c].get("state")) for c in names] for r in vw["rows"]]
            out[verb] = f"{k.step(verb).state}: {names} {vals}"[:70]
        except Exception as e:
            out[verb] = "raised: " + str(e)[:60]
    print(f"{label:24} expand → {out['expand']}\n{'':24} widen  → {out['widen']}")
