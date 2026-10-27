# Core probe (2026-10-26), see docs/core-proposals/011-core-handover.md. Run: .venv/bin/python scripts/core_probes/probe_colarg.py
from simple_steps_core import grid
from simple_steps_core.grid import mod, op, tool, cols, zip_
import pandas as pd

@tool
def make():
    return pd.DataFrame({"n": [3, 1, 2], "w": [10, 20, 30]})
@tool
def scale_untyped(n, weight=1): return n * weight
@tool
def scale_typed(n: int, weight: int = 1) -> int: return n * weight

def go(label, build):
    try:
        wf = grid.Workflow(); wf["r"] = make[mod.source()](); build(wf); wf.run_all()
        st = wf.step("s"); print(f"OK   {label}\n     problems={st.problems}\n     -> {st.output.data.to_dict('list')}")
    except Exception as e:
        print(f"FAIL {label}: {type(e).__name__}: {str(e)[:200]}")

go("untyped, column arg", lambda wf: wf.__setitem__("s", scale_untyped[mod.map()](wf["r"], weight=wf["r"][cols["w"]])))
go("typed int, column arg", lambda wf: wf.__setitem__("s", scale_typed[mod.map()](wf["r"], weight=wf["r"][cols["w"]])))
go("typed int, auto, column arg", lambda wf: wf.__setitem__("s", scale_typed[mod.auto()](wf["r"], weight=wf["r"][cols["w"]])))
