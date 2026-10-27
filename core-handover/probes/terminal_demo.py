# Core probe (2026-10-26), see docs/core-proposals/011-core-handover.md. Run: .venv/bin/python scripts/core_probes/terminal_demo.py
import pandas as pd
from simple_steps_core import grid
from simple_steps_core.grid import mod, tool

@tool
def patients():
    return pd.DataFrame({"name": ["Ana", "Ben", "Cy"], "temp_c": [36.6, 38.2, 37.1]})
@tool
def to_f(temp_c: float) -> float:
    return temp_c * 9 / 5 + 32
@tool
def feverish(temp_c: float, limit: float = 38) -> bool:
    return temp_c >= limit

wf = grid.Workflow()
wf["p"] = patients[mod.source()]()
wf["sick"] = feverish[mod.filter()](wf["p"])
wf["f"] = to_f[mod.map()](wf["sick"])
wf.run_all()
print(wf.step("f").output.data)
wf["sick"] = feverish[mod.filter()](wf["p"], limit=37)
print({n: wf.step(n).status for n in wf.steps})
wf.run_all(); print(wf.step("f").output.data)
wf2 = grid.Workflow.from_json(wf.to_json(), tools={"patients": patients, "to_f": to_f, "feverish": feverish})
wf2.run_all(); print("reloaded", wf2.step("f").output.data.to_dict("list"))
