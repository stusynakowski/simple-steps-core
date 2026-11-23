"""nest (many cells into one) on uneven groups and rows: collapse with gather,
pack, beside pandas' groupby(...).agg(list) and to_dict
(expression-grammar/nest.md).

    .venv/bin/python docs/design/grid-probes/nest.py
"""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
from simple_steps_core import Catalog, Kernel, mod, op, wf


def view(k, name):
    v = k.view(name)
    names = [c["name"] for c in v["columns"]]
    rows = [[(r["cells"][c].get("value") if r["cells"][c]["state"] == "known"
              else r["cells"][c]["state"]) for c in names] for r in v["rows"]]
    return names, rows, [r.get("lineage") for r in v["rows"]]


def core(frame, expr):
    k = Kernel(Catalog(tools=[]))
    k["d"] = frame
    try:
        k["n"] = expr
        k.run("n")
        names, rows, lin = view(k, "n")
        warn = [w.message[:60] for w in k.step("n").warnings]
        return f"{k.step('n').state:9} {names} {rows} lineage {lin} {warn}"
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:100]}"


def panda(f):
    try:
        out = f()
        return out.to_dict() if hasattr(out, "to_dict") and not isinstance(out, list) else out
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:90]}"


def group(label, frame):
    print(label)
    print("   core:  ", core(frame, mod.collapse(by="k")(wf["d"])))
    print("   pandas:", panda(lambda: frame.groupby("k")["x"].agg(list)),
          "| sort=False, dropna=False:", panda(lambda: frame.groupby("k", sort=False, dropna=False)["x"].agg(list)))


group("groups, order of keys b, a", pd.DataFrame({"k": ["b", "a", "b"], "x": [1, 2, 3]}))
group("a None key", pd.DataFrame({"k": ["a", None, "a"], "x": [1, 2, 3]}))
group("None and absent values", pd.DataFrame({"k": ["a", "a", "a"], "x": pd.array([1, None, 3], dtype="Int64")}))
group("mixed value types", pd.DataFrame({"k": ["a", "a"], "x": pd.Series([1, "y"], dtype=object)}))
group("zero rows", pd.DataFrame({"k": pd.Series([], dtype=str), "x": pd.Series([], dtype=float)}))
group("unhashable key (lists)", pd.DataFrame({"k": [[1], [1]], "x": [1, 2]}))
print("two keys")
two = pd.DataFrame({"k": ["a", "a", "b"], "j": [1, 2, 1], "x": [1, 2, 3]})
print("   core:  ", core(two, mod.collapse(by=["k", "j"])(wf["d"])))
print("   pandas:", panda(lambda: two.groupby(["k", "j"])["x"].agg(list)))
print("everything into one list")
print("   core:  ", core(pd.DataFrame({"x": [1, 2, 3]}), op("gather")[mod.collapse()](wf["d"][["x"]])))
print("pack: a row's cells into a dict, a None and a gap")
pk = pd.DataFrame({"a": [1, None], "b": pd.array([2, None], dtype="Int64")})
print("   core:  ", core(pk, mod.pack(columns=["a", "b"])(wf["d"])))
print("   pandas:", panda(lambda: pk.to_dict(orient="records")))
