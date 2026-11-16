import pandas as pd
from simple_steps_core import Kernel, Catalog, tool, mod, wf, join, stack, zip_, op, cols, row
seen = {}
def spy(name):
    def deco(f):
        def g(*a, **kw):
            seen.setdefault(name, []).append({k: (type(v).__name__ + ":" + repr(v)[:40]) for k, v in kw.items()} or [repr(x)[:40] for x in a])
            return f(*a, **kw)
        g.__name__ = f.__name__; g.__annotations__ = f.__annotations__; g.__doc__ = f.__doc__
        import inspect; g.__signature__ = inspect.signature(f)
        return g
    return deco
@tool
@spy("dbl")
def dbl(n: int) -> int: return 2 * n
@tool
@spy("hot")
def hot(temp: float) -> bool: return temp > 38
@tool
@spy("split")
def split(name: str) -> list: return list(name[:2])
@tool
@spy("mean")
def mean(temp: list) -> float: return sum(temp) / len(temp)
@tool
@spy("ward_of")
def ward_of(name: str) -> str: return name[0]
@tool
@spy("summary")
def summary(df: pd.DataFrame) -> pd.DataFrame: return df.describe().reset_index()
k = Kernel(Catalog(tools=[dbl, hot, split, mean, ward_of, summary]))
k["v"] = pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "ward": ["A", "B", "A"], "temp": [37.0, 39.5, 38.2], "n": [1, 2, 3]})
k["w"] = pd.DataFrame({"ward": ["A", "B"], "beds": [4, 5]})
steps = {
 "d": dbl[mod.map()](wf["v"]),
 "h": hot[mod.filter()](wf["v"]),
 "e": split[mod.expand()](wf["v"]),
 "c": mean[mod.collapse(by="ward")](wf["v"]),
 "g": ward_of[mod.group()](wf["v"]),
 "srt": mod.sort(by="temp")(wf["v"]),
 "sel": mod.select(columns=["name"])(wf["v"]),
 "z": zip_(wf["v"], wf["d"]),
 "j": join(wf["v"], wf["w"], on="ward"),
 "st": stack(wf["v"], wf["w"]),
 "t": summary[mod.table()](wf["v"]),
 "p": wf["srt"][0],
 "q": wf["v"][cols["temp"] > 38],
}
for n, e in steps.items(): k[n] = e
k.run_all()
for n in steps:
    s = k.step(n); o = s.output; d = o.data
    lin = [c for c in d.columns if str(c).startswith("#")]; data = [c for c in d.columns if not str(c).startswith("#")]
    print(f"{n:4} {s.state:9} verb={o.meta.get('verb')!s:8} ids={list(d.index)[:6]} data={data} lineage={ {c: list(d[c])[:5] for c in lin} } back={o.meta.get('inverse',{}).get('kind')} rows={s.plan['rows'].get('certainty')}")
    print(f"      formula: {s.formula}")
print("\nwhat each tool received per call:")
for n, calls in seen.items(): print(f"  {n}: {len(calls)} call(s), first: {calls[0]}")
v = k.view("e"); print("\nview of e: keys", sorted(v), "| lineage", v["lineage"], "| row0", {x: v["rows"][0][x] for x in ("#", "lineage")})
print("cell e[1] inputs:", k.cell("e", 1)["inputs"])
print("\nlineage as the view shows it (derived from row ids where not stored):")
for n in ["d", "h", "srt", "g", "sel", "z", "p", "q", "e", "c", "j", "t"]:
    v = k.view(n); print(f"  {n:4} lineage cols={v['lineage']} rows={[r['lineage'] for r in v['rows']][:4]}")
print("\nhow the data columns of a step reach the next: does d carry v's columns?", list(k.step("d").output.data.columns), "| a pick of d's input:", k.step("d").operation.input)
