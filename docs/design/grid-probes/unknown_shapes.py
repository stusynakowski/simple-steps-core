import pandas as pd, numpy as np
from simple_steps_core import Kernel, Catalog, tool, mod, wf, op
from simple_steps_core.errors import StepFailed
@tool
def hot(am: float) -> bool: return am > 38
@tool
def words(name: str) -> list: return list(name)
@tool
def info(name: str) -> dict: return {"len": len(name)} if name != "Ben" else {"len": 3, "vowels": 1}
@tool
def maybe(name: str): return 1 if name == "Ada" else ("x" if name == "Ben" else [1])
@tool
def opt(name: str) -> list: return None if name == "Cy" else [1, 2]
@tool
def pair(name: str) -> dict: return {"a": list(name), "b": list(name)[:2]}
k = Kernel(Catalog(tools=[hot, words, info, maybe, opt, pair]))
k["v"] = pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "am": [37.0, 39.5, 38.2]})
k["pk"] = mod.pack(columns=["am"])(wf["v"]); k["long"] = mod.expand(columns=["pk"])(wf["pk"])
k["gd"] = op("gather_dict")[mod.collapse(by="name")](wf["long"], key=wf["long"]["key"], value=wf["long"]["pk"]); k["wide"] = mod.widen("gd")(wf["gd"])
try: k.run("wide"); print("pivot back:", k.step("wide").formula, "->", list(k.step("wide").output.data.columns), k.step("wide").output.data.iloc[0].to_dict())
except Exception as f: print("pivot:", str(f)[:160])
print("\n-- before a run (plans):")
steps = {"f": hot[mod.filter()](wf["v"]), "e": words[mod.expand()](wf["v"]), "d": info[mod.map()](wf["v"]), "m": maybe[mod.map()](wf["v"]), "o": opt[mod.expand()](wf["v"]), "p": pair[mod.map(), mod.name("p")](wf["v"])}
for n, e in steps.items():
    k[n] = e; pl = k.step(n).plan
    print(f"  {n}: rows {pl['rows']} | columns {pl['columns'].get('certainty')} {pl['columns'].get('names')} | types {pl.get('types')}")
k["ex"] = words[mod.expand(), mod.expect(min_rows=1, max_rows=20)](wf["v"]); print("  with expect(min_rows=1, max_rows=20):", k.step("ex").plan["rows"])
print("\n-- after the run:")
for n in list(steps) + ["ex"]:
    try: k.run(n)
    except StepFailed as f: print(f"  {n}: run stopped: {str(f)[:100]}"); continue
    s = k.step(n); d = s.output.data
    print(f"  {n}: {s.state} rows={len(d)} cols={[c for c in d.columns]} types={s.plan.get('types')} warnings={[w.message[:70] for w in s.warnings][:2]}")
k["p2"] = mod.expand(columns=["a", "b"])(wf["d"]) if False else None
k["pw"] = mod.widen("p")(wf["p"]); k["pe"] = mod.expand(columns=["a", "b"])(wf["pw"])
try: k.run("pe"); s = k.step("pe"); print("  two lists of different lengths expanded together:", s.state, str(s.output.notes)[:140])
except StepFailed as f: print("  two ragged lists expanded together: run stopped:", str(f)[:140])
