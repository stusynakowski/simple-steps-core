"""convert (the one primitive that changes a value): today's cast beside
pandas' astype and to_numeric (expression-grammar/convert.md).

    .venv/bin/python docs/design/grid-probes/convert.py
"""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
from simple_steps_core import Catalog, Kernel, mod, op, tool, wf


@tool
def seen(x) -> str:
    return f"{type(x).__name__}:{x!r}"


def core(values, to, column="x"):
    k = Kernel(Catalog(tools=[seen]))
    k["d"] = pd.DataFrame({"x": pd.Series(values, dtype=object)})
    try:
        k["c"] = seen[mod.cast(**{column: to}), mod.map()](wf["d"])
        p = [q.message[:70] for q in k.step("c").problems]
        if p:
            return f"refused {p}"
        k.run("c")
    except Exception as e:
        if "c" not in k:
            return f"ERR {type(e).__name__}: {str(e)[:80]}"
    out = []
    for r in k.view("c")["rows"]:
        cell = r["cells"]["c"]
        out.append(cell.get("value") if cell["state"] == "known" else f"{cell['state']}")
    return out


def panda(values, to):
    s = pd.Series(values, dtype=object)
    res = []
    for how, f in (("astype", lambda: s.astype(to).tolist()),
                   ("to_numeric(coerce)", lambda: pd.to_numeric(s, errors="coerce").tolist() if to in ("float", "int") else "—")):
        try:
            res.append(f"{how}: {f()}")
        except Exception as e:
            res.append(f"{how}: ERR {type(e).__name__}")
    return " | ".join(res)


cases = [
    ("text to float", ["1.5", " 3 ", "1e3", "1,000", "abc"], "float"),
    ("float to int", [2.0, 1.7], "int"),
    ("text to int", ["2", "2.0"], "int"),
    ("text to bool", ["True", "false", "False", "yes", "1"], "bool"),
    ("int to bool", [0, 1, 2], "bool"),
    ("bool to int", [True, False], "int"),
    ("a big int to float", [2 ** 60 + 1], "float"),
    ("a list to str", [[1, 2]], "str"),
    ("missing to int", [None, float("nan")], "int"),
]
for label, values, to in cases:
    print(f"{label}  {values!r} -> {to}\n   core:   {core(values, to)}\n   pandas: {panda(values, to)}")
print(f"an unsupported target  -> datetime\n   core:   {core(['2020-01-01'], 'datetime')}")
print(f"a column that isn't there  cast(nope='float')\n   core:   {core(['1'], 'float', column='nope')}")
