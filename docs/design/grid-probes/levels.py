"""A list at either level: a block made into a list, or a cell whose value is
a list (docs/design/blocks.md §1, Two levels).

    .venv/bin/python docs/design/grid-probes/levels.py
"""
import pandas as pd
from simple_steps_core import Catalog, Kernel, mod, tool, wf
got = []
@tool
def per_list(x: float, y: list) -> float: got.append(repr(y)); return 0.0
@tool
def per_any(x: float, y=None) -> float: got.append(repr(y)); return 0.0
@tool
def grp(y: list) -> float: got.append(repr(y)); return 0.0
k = Kernel(Catalog(tools=[per_list, per_any, grp]))
k["d"] = pd.DataFrame({"x": [1.0, 2.0], "n": [5.0, 6.0], "L": [[1, 2], [3, 4, 5]], "k": ["a", "a"]})
k["o"] = pd.DataFrame({"L": [[7, 8]], "n": [9.0]})
cases = [
  ("map, y: list  ← paired column of lists d['L']   (each cell IS a list)", per_list[mod.map()](wf["d"]["x"], y=wf["d"]["L"])),
  ("map, y: list  ← paired column of numbers d['n'] (block → list?)", per_list[mod.map()](wf["d"]["x"], y=wf["d"]["n"])),
  ("map, y: list  ← whole cell holding a list o[0]['L']", per_list[mod.map()](wf["d"]["x"], y=wf["o"][0]["L"])),
  ("map, y: list  ← whole cell holding a number o[0]['n']", per_list[mod.map()](wf["d"]["x"], y=wf["o"][0]["n"])),
  ("map, y: untyped ← whole cell holding a list", per_any[mod.map()](wf["d"]["x"], y=wf["o"][0]["L"])),
  ("collapse, y: list ← group of number cells d['n']", grp[mod.collapse(by="k")](wf["d"], y=wf["d"]["n"])),
  ("collapse, y: list ← group of list cells d['L']", grp[mod.collapse(by="k")](wf["d"], y=wf["d"]["L"])),
]
for label, op in cases:
    got.clear()
    k["m"] = op
    p = k.step("m").problems
    if p:
        print(f"{label}\n    refused: {p[0].message[:120]}")
    else:
        try: k.run("m", force=True)
        except Exception as e: pass
        print(f"{label}\n    tool got: {got[:2]}")
    del k["m"]
