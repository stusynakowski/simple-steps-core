import io, numpy as np, pandas as pd
from simple_steps_core import Kernel, Catalog, tool, mod, wf, join, op
class Thing:
    def __init__(s, v): s.v = v
@tool
def info(n: int) -> dict: return {"a": n, "b": str(n)}
@tool
def items(n: int) -> list: return list(range(n))
@tool
def img(n: int) -> object: return np.zeros((2, 2)) + n
@tool
def thing(n: int) -> object: return Thing(n)
k = Kernel(Catalog(tools=[info, items, img, thing]))
k["s"] = pd.DataFrame({"n": [1, 2, 3], "ward": ["A", "B", "A"], "x": [1.5, None, 2.0]})
k["w"] = pd.DataFrame({"ward": ["A", "C"], "beds": [4, 5]})
k["d"] = info[mod.map(), mod.name("d")](wf["s"])
k["g"] = op("gather")[mod.collapse(by="ward")](wf["s"])
k["e"] = items[mod.expand()](wf["s"])
k["j"] = join(wf["s"], wf["w"], on="ward", how="outer")
k["im"] = img[mod.map()](wf["s"])
k["th"] = thing[mod.map()](wf["s"])
k.run_all()
for name in ["s", "d", "g", "e", "j", "im", "th"]:
    out = k.step(name).output
    df = out.data
    b = io.BytesIO()
    try:
        df.to_parquet(b); back = pd.read_parquet(io.BytesIO(b.getvalue()))
        same = df.reset_index(drop=True).astype(object).equals(back.reset_index(drop=True).astype(object))
        diff = "" if same else f" | before {df.iloc[0].to_dict()} after {back.iloc[0].to_dict()} dtypes {dict(df.dtypes.astype(str))}->{dict(back.dtypes.astype(str))}"
        print(f"{name}: ok={same} bytes={len(b.getvalue())} index_kept={list(back.index)==list(df.index)}{diff}"[:330])
    except Exception as e:
        print(f"{name}: FAILS {type(e).__name__}: {str(e)[:120]}")
print("cell states kept in data?", [c for c in k.step("j").output.data.columns])
print("output attrs:", [a for a in vars(k.step("j").output)][:15])
