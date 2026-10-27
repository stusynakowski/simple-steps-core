# Core probe (2026-10-26), see docs/core-proposals/011-core-handover.md. Run: .venv/bin/python scripts/core_probes/probe_refs2.py
from simple_steps_core import grid
from simple_steps_core.grid import mod, op, tool
import simple_steps_core.grid as g
import pandas as pd
cols = getattr(g, "cols", None)
print("grid.cols exists:", cols is not None)

@tool
def make():
    return pd.DataFrame({"n": [3, 1, 2], "w": [10, 20, 30]})

@tool
def scale(n, weight=1):
    return n * weight

def attempt(label, build, target="s"):
    try:
        wf = build()
        wf.run_all()
        st = wf.step(target)
        probs = getattr(st, "problems", None)
        data = st.output.data
        print(f"OK   {label}  problems={probs}\n     -> {data.to_dict('list') if hasattr(data,'to_dict') else data}")
    except Exception as e:
        print(f"FAIL {label}: {type(e).__name__}: {str(e)[:170]}")

def base():
    wf = grid.Workflow(); wf["r"] = make[mod.source()](); return wf
def sel_step():                     # a selection as its own step
    wf = base(); wf["s"] = wf["r"][0:2]; return wf
def col_step():
    wf = base(); wf["s"] = wf["r"][cols["n"]]; return wf
def cell_as_arg():                  # one cell as an argument
    wf = base(); wf["s"] = scale[mod.map()](wf["r"], weight=wf["r"][0][cols["w"]]); return wf
def col_as_arg():
    wf = base(); wf["s"] = scale[mod.map()](wf["r"], weight=wf["r"][cols["w"]]); return wf
def mod_from_step():
    wf = base(); wf["s"] = op("identity")[mod.sort(by=wf["r"])](wf["r"]); return wf
def computed_arg():
    wf = base(); wf["s"] = scale[mod.map()](wf["r"], weight=len("abc")); return wf
def later_ref():
    wf = grid.Workflow(); wf["s"] = scale[mod.map()](wf["later"]); wf["later"] = make[mod.source()](); return wf
def sorted_then_cell():             # does a cell selection follow the row when upstream is re-sorted?
    wf = base(); wf["srt"] = op("identity")[mod.sort(by="n")](wf["r"]); wf["s"] = wf["srt"][0][cols["w"]]; return wf

for label, b in [("selection as its own step  wf['r'][0:2]", sel_step), ("column as its own step  wf['r'][cols['n']]", col_step),
                 ("one cell as an argument  weight=wf['r'][0][cols['w']]", cell_as_arg), ("a column as an argument", col_as_arg),
                 ("step as a modifier setting  mod.sort(by=wf['r'])", mod_from_step), ("computed argument (Python)  weight=len('abc')", computed_arg),
                 ("reference to a later step", later_ref), ("cell of a sorted step: position 0", sorted_then_cell)]:
    attempt(label, b)
