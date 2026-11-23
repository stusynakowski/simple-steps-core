"""What a mapped tool's argument accepts today: every kind of argument against
every kind of parameter (docs/design/blocks.md §3).

    .venv/bin/python docs/design/grid-probes/blocks.py

Each cell is what the tool received (its type), "refused" (a problem when
declared) or "crash" (an exception when declared).
"""
import typing

import numpy as np
import pandas as pd

from simple_steps_core import Catalog, Kernel, mod, tool, wf

got: list[str] = []


def made(annotation, label):
    def t(x: float, y=None):
        shape = f"{list(y.shape)}" if hasattr(y, "shape") else \
            (f"[{len(y)}]" if isinstance(y, (list, dict)) else "")
        got.append(type(y).__name__ + shape)
        return 0.0
    t.__annotations__ = {"x": float, "y": annotation, "return": float}
    t.__name__ = f"takes_{label}"
    return tool(t)


PARAMETERS = {"float": float, "str": str, "list": list, "dict": dict,
              "Series": pd.Series, "DataFrame": pd.DataFrame, "ndarray": np.ndarray,
              "Any": typing.Any}
tools = {label: made(a, label) for label, a in PARAMETERS.items()}
k = Kernel(Catalog(tools=list(tools.values())))
k["d"] = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [10.0, 20.0, 30.0], "s": ["a", "b", "c"]})
k["o"] = pd.DataFrame({"y": [7.0, 8.0], "z": [1.0, 2.0]})       # rows not d's

ARGUMENTS = {
    "literal 5.0": 5.0,
    "literal 'hi'": "hi",
    "literal [1, 2]": [1, 2],
    "literal {'a': 1}": {"a": 1},
    "paired: column of d (float)": wf["d"]["y"],
    "paired: column of d (str)": wf["d"]["s"],
    "whole: cell of o": wf["o"][0]["y"],
    "whole: row of o": wf["o"][0],
    "whole: block of o": wf["o"],
    "column of o (rows not d's)": wf["o"]["y"],
}

print(f"{'argument y=':30}" + "".join(f"{p:>12}" for p in PARAMETERS))
for label, value in ARGUMENTS.items():
    line = f"{label:30}"
    for p, t in tools.items():
        got.clear()
        try:
            k["m"] = t[mod.map()](wf["d"]["x"], y=value)
            if k.step("m").problems:
                line += f"{'refused':>12}"
            else:
                k.run("m", force=True)
                line += f"{(got[0] if got else k.step('m').state)[:11]:>12}"
        except Exception:
            line += f"{'crash':>12}"
        finally:
            if "m" in k:
                del k["m"]
    print(line)

print()
for p, label in [("float", "column of o (rows not d's)"), ("list", "paired: column of d (float)"),
                 ("dict", "whole: cell of o"), ("Any", "literal 5.0")]:
    try:
        k["m"] = tools[p][mod.map()](wf["d"]["x"], y=ARGUMENTS[label])
        problems = k.step("m").problems
        print(f"{p} ← {label}: {problems[0].message if problems else 'accepted'}")
        del k["m"]
    except Exception as exc:
        print(f"{p} ← {label}: raised {type(exc).__name__}: {exc}")

# the input itself: a one-column pick that doesn't fit its parameter
@tool
def h(x: float) -> float:
    return 0.0


k2 = Kernel(Catalog(tools=[h]))
k2["d"] = pd.DataFrame({"s": ["a"]})
k2["p"] = h[mod.map()](wf["d"]["s"])
print(f"\ninput str column into x: float: problems when declared: "
      f"{[p.message for p in k2.step('p').problems] or 'none'}")
try:
    k2.run("p")
except Exception:
    pass
print(f"  after a run: {k2.step('p').state}, {k2.cell('p', 0).get('error')}")

# the same, when the step (not the pick) has a column named x
k3 = Kernel(Catalog(tools=[h]))
k3["d"] = pd.DataFrame({"x": [1.0], "s": ["a"]})
k3["p"] = h[mod.map()](wf["d"]["s"])
print(f"step has x, pick is s: problems when declared: "
      f"{[p.message for p in k3.step('p').problems] or 'none'}")
try:
    k3.run("p")
except Exception:
    pass
print(f"  after a run: {k3.step('p').state}, {k3.cell('p', 0).get('error')}")
