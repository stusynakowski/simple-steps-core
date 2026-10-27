# Core probe (2026-10-26), see docs/core-proposals/011-core-handover.md. Run: .venv/bin/python scripts/core_probes/probe_colarg2.py
from simple_steps_core import grid
from simple_steps_core.grid import mod, op, tool, cols, zip_
import pandas as pd
@tool
def make():  return pd.DataFrame({"n": [3, 1, 2]})
@tool
def make_w(): return pd.DataFrame({"weight": [10, 20, 30]})
@tool
def scale(n: int, weight: int = 1) -> int: return n * weight
def go(label, build):
    try:
        wf = grid.Workflow(); wf["r"] = make[mod.source()](); wf["w"] = make_w[mod.source()](); build(wf); wf.run_all()
        st = wf.step("s"); print(f"OK   {label}\n     problems={st.problems}\n     -> {st.output.data.to_dict('list')}")
    except Exception as e:
        print(f"FAIL {label}: {type(e).__name__}: {str(e)[:200]}")
def zipped(wf):
    wf["z"] = zip_(wf["r"], wf["w"]); wf["s"] = scale[mod.map()](wf["z"])
go("today's route: zip_ then map (columns matched by name)", zipped)
