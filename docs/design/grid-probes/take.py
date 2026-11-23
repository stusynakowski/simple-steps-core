"""take (choose, reorder rows and columns; no value changed) on missing
values, mixed types, ties and out-of-range picks, beside pandas
(expression-grammar/take.md).

    .venv/bin/python docs/design/grid-probes/take.py
"""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
from simple_steps_core import Catalog, Kernel, mod, tool, wf, cols


@tool
def odd(x: float) -> bool:
    return int(x) % 2 == 1


@tool
def maybe(x: float) -> bool:
    return None if x == 2 else x > 1


def core(frame, make):
    k = Kernel(Catalog(tools=[odd, maybe]))
    k["d"] = frame
    try:
        k["t"] = make()
        problems = [p.message[:90] for p in k.step("t").problems]
        if problems:
            return f"refused: {problems}"
        k.run("t")
        v = k.view("t")
        names = [c["name"] for c in v["columns"]]
        rows = [[(r["cells"][c].get("value") if r["cells"][c]["state"] == "known"
                  else r["cells"][c]["state"]) for c in names] for r in v["rows"]]
        warn = [w.message[:60] for w in k.step("t").warnings]
        return f"{k.step('t').state:9} {names} {rows} {warn}"
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:100]}"


def panda(f):
    try:
        out = f()
        return f"{list(out.columns)} {out.astype(object).where(out.notna(), '<NA>').values.tolist()}"
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:80]}"


def case(label, frame, make, pf):
    print(f"{label}\n   core:   {core(frame, make)}\n   pandas: {panda(pf)}")


N = pd.DataFrame({"id": [0, 1, 2], "x": pd.array([3, None, 1], dtype="Int64")})
case("condition x > 1, a gap in x", N, lambda: wf["d"][cols["x"] > 1], lambda: N[N["x"] > 1])
M = pd.DataFrame({"id": [0, 1], "x": pd.Series([3, "a"], dtype=object)})
case("condition x > 1, mixed types", M, lambda: wf["d"][cols["x"] > 1], lambda: M[M["x"] > 1])
case("sort by x, a gap", N, lambda: mod.sort(by=["x"])(wf["d"]), lambda: N.sort_values("x"))
case("sort by x, mixed types", M, lambda: mod.sort(by=["x"])(wf["d"]), lambda: M.sort_values("x"))
T = pd.DataFrame({"id": [0, 1, 2, 3], "x": [2, 1, 2, 1]})
case("sort, ties keep their order?", T, lambda: mod.sort(by=["x"])(wf["d"]), lambda: T.sort_values("x"))
D = pd.DataFrame({"id": [0, 1, 2], "k": ["a", None, "a"]})
case("distinct on k, a None", D, lambda: mod.distinct(columns=["k"])(wf["d"]), lambda: D.drop_duplicates("k"))
L = pd.DataFrame({"id": [0, 1], "k": [[1], [1]]})
case("distinct on k, lists", L, lambda: mod.distinct(columns=["k"])(wf["d"]), lambda: L.drop_duplicates("k"))
case("pick row 10 of 3", T, lambda: wf["d"][10], lambda: T.iloc[[10]])
case("pick rows 2:10 of 4", T, lambda: wf["d"][2:10], lambda: T.iloc[2:10])
case("pick column 'nope'", T, lambda: wf["d"]["nope"], lambda: T[["nope"]])
case("drop column 'nope'", T, lambda: mod.drop(columns=["nope"])(wf["d"]), lambda: T.drop(columns=["nope"]))
case("filter, a tool's True/False", T, lambda: odd[mod.filter()](wf["d"]["x"]), lambda: T[T["x"] % 2 == 1])
case("filter, a tool returning None", T, lambda: maybe[mod.filter()](wf["d"]["x"]), lambda: T)
