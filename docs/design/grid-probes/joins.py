"""join together (stack, zip_, join) on the cases that usually go wrong,
beside pandas' concat and merge (expression-grammar/joins.md).

    .venv/bin/python docs/design/grid-probes/joins.py
"""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
from simple_steps_core import Catalog, Kernel, mod, wf, join, stack, zip_


def view(k, n):
    v = k.view(n)
    names = [c["name"] for c in v["columns"]]
    rows = [[(r["cells"][c].get("value") if r["cells"][c]["state"] == "known"
              else r["cells"][c]["state"]) for c in names] for r in v["rows"]]
    return names, rows, [r.get("lineage") for r in v["rows"]]


def core(a, b, make):
    k = Kernel(Catalog(tools=[]))
    k["a"], k["b"] = a, b
    try:
        k["j"] = make()
        k.run("j")
        names, rows, lin = view(k, "j")
        return f"{names} {rows} lineage {lin}"
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:110]}"


def panda(f):
    try:
        out = f()
        return f"{list(out.columns)} {out.astype(object).where(out.notna(), '<NA>').values.tolist()}"
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:90]}"


def case(label, a, b, make, pf):
    print(f"{label}\n   core:   {core(a, b, make)}\n   pandas: {panda(pf)}")


A = pd.DataFrame({"x": [1], "y": ["p"]})
B = pd.DataFrame({"x": [2], "z": [True]})
case("stack, different columns", A, B, lambda: stack(wf["a"], wf["b"]), lambda: pd.concat([A, B], ignore_index=True))
C = pd.DataFrame({"x": ["3"]})
case("stack, x int then str", A[["x"]], C, lambda: stack(wf["a"], wf["b"]), lambda: pd.concat([A[["x"]], C], ignore_index=True))

L = pd.DataFrame({"id": [1, 2, 2], "v": ["a", "b", "c"]})
R = pd.DataFrame({"id": [2, 2, 3], "w": ["x", "y", "z"]})
case("join inner, duplicate keys", L, R, lambda: join(wf["a"], wf["b"], on="id"), lambda: L.merge(R, on="id"))
case("join left", L, R, lambda: join(wf["a"], wf["b"], on="id", how="left"), lambda: L.merge(R, on="id", how="left"))
case("join outer", L, R, lambda: join(wf["a"], wf["b"], on="id", how="outer"), lambda: L.merge(R, on="id", how="outer"))
LN = pd.DataFrame({"id": [None, 1], "v": ["a", "b"]})
RN = pd.DataFrame({"id": [None, 1], "w": ["x", "y"]})
case("join, None keys on both sides", LN, RN, lambda: join(wf["a"], wf["b"], on="id"), lambda: LN.merge(RN, on="id"))
LS = pd.DataFrame({"id": ["1", "2"], "v": ["a", "b"]})
case("join, key str against int", LS, R, lambda: join(wf["a"], wf["b"], on="id"), lambda: LS.merge(R, on="id"))
L2 = pd.DataFrame({"id": [1], "v": ["a"], "n": [1]})
R2 = pd.DataFrame({"id": [1], "v": ["b"], "n": [2]})
case("join, shared non-key columns", L2, R2, lambda: join(wf["a"], wf["b"], on="id"), lambda: L2.merge(R2, on="id"))
case("join, no on=", L, R, lambda: join(wf["a"], wf["b"]), lambda: L.merge(R))
case("cross product", A, B, lambda: join(wf["a"], wf["b"], how="cross"), lambda: A.merge(B, how="cross"))
case("zip, two unrelated steps", A, B, lambda: zip_(wf["a"], wf["b"]), lambda: pd.concat([A, B], axis=1))
