import pandas as pd
from simple_steps_core import Kernel, Catalog, tool, mod, wf, op, join, zip_, stack, cols
from simple_steps_core.errors import StepFailed
@tool
def cumsum(xs: list) -> list:
    out, s = [], 0
    for x in xs: s += x; out.append(s)
    return out
@tool
def mean(temp: list) -> float: return sum(temp) / len(temp)
@tool
def minus(temp: float, m: float) -> float: return round(temp - m, 2)
@tool
def transpose(df: pd.DataFrame) -> pd.DataFrame: return df.set_index("name").T.reset_index()
k = Kernel(Catalog(tools=[cumsum, mean, minus, transpose]))
k["v"] = pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "ward": ["A", "B", "A"], "am": [37.0, 39.5, 38.2], "pm": [37.4, 39.0, 38.0]})
def run(label, steps):
    try:
        for n, e in steps: k[n] = e
        k.run(steps[-1][0]); s = k.step(steps[-1][0]); d = s.output.data
        prob = [p.message[:100] for p in s.problems]
        print(f"{label}: {s.state} {prob[:1] if prob else ''} cols={list(d.columns)} rows={len(d)} first={str(d.iloc[0].to_dict())[:110] if len(d) else '-'}")
        print(f"    {' ; '.join(k.step(n).formula for n, _ in steps)}")
    except StepFailed as f: print(f"{label}: run stopped: {str(f)[:120]}")
    except Exception as f: print(f"{label}: {type(f).__name__}: {str(f)[:140]}")
run("wide -> long (melt)", [("pk", mod.pack(columns=["am", "pm"])(wf["v"])), ("long", mod.expand(columns=["pk"])(wf["pk"]))])
run("long -> wide (pivot)", [("gd", op("gather_dict")[mod.collapse(by="name")](wf["long"])), ("wide", mod.widen("gd")(wf["gd"]))])
run("group stat back on each row", [("wm", mean[mod.collapse(by="ward")](wf["v"]["ward", "am"]) if False else mean[mod.collapse(by="ward")](wf["v"], temp=wf["v"]["am"]) ), ("back", join(wf["v"], wf["wm"], on="ward"))])
run("  then centred value per row", [("ctr", minus[mod.map()](wf["back"], temp=wf["back"]["am"], m=wf["back"]["wm"]))])
run("window: running total over rows", [("g", op("gather")[mod.collapse()](wf["v"]["am"])), ("cs", cumsum[mod.map()](wf["g"], xs=wf["g"]["am"])), ("csr", mod.expand(columns=["cs"])(wf["cs"]))])
run("  running total beside its rows (zip with v)", [("z", zip_(wf["v"], wf["csr"]))])
run("transpose (a table tool)", [("tr", transpose[mod.table()](wf["v"]["name", "am", "pm"]))])
run("cross product of two tables", [("w", pd.DataFrame({"dose": [1, 2]})), ("x", join(wf["v"], wf["w"], how="cross"))])
