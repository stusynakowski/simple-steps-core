"""A frozen copy is a data step: does saving keep its values exactly?
(docs/design/blocks.md §2, Freezing). Then: an absent cell, and a whole-number
nullable float, written into a data step.

    .venv/bin/python docs/design/grid-probes/freezing.py
"""
import tempfile, numpy as np, pandas as pd
from simple_steps_core import Catalog, Kernel, mod, tool, wf
@tool
def dbl(x: float) -> float: return 2 * x
k = Kernel(Catalog(tools=[dbl]))
k["d"] = pd.DataFrame({
    "f": [1.5, 2.0, 3.0], "g": [1.5, None, 3.0], "s": ["a", "b", None], "L": [[1, 2], [], [3]],
    "D": [{"a": 1}, {}, {"b": [1, 2]}], "A": [np.ones(2), np.zeros(3), np.arange(2)],
    "n": pd.array([1, None, 3], dtype="Int64")})
k["m"] = dbl[mod.map()](wf["d"]["f"])
k.run_all()
for outputs in (False, True):
    folder = tempfile.mkdtemp()
    k.save(folder, outputs=outputs)
    k2 = Kernel.load(folder, Catalog(tools=[dbl]))
    a, b = k.step("d").output.data, k2.step("d").output.data
    print(f"outputs={outputs}: d state {k2.step('d').state}, m state {k2.step('m').state}")
    for c in a.columns:
        def eq(x, y):
            if isinstance(x, np.ndarray): return isinstance(y, np.ndarray) and np.array_equal(x, y) and x.dtype == y.dtype
            if isinstance(x, (list, dict)): return x == y
            if x is pd.NA or y is pd.NA or x is None or y is None: return (x is y) or (repr(x) == repr(y))
            if isinstance(x, float) and np.isnan(x): return isinstance(y, float) and np.isnan(y)
            return x == y and type(x) == type(y)
        bad = [(x, y) for x, y in zip(a[c], b[c]) if not eq(x, y)]
        same = not bad
        print(f"   {c}: {'same' if same else 'DIFFERENT ' + repr(bad[:2])}  types {type(b[c].iloc[0]).__name__}, dtype {a[c].dtype}→{b[c].dtype}")
    print("   d cell states same:", k.step("d").output.states.equals(k2.step("d").output.states))

from simple_steps_core import stack
k = Kernel(Catalog(tools=[]))
k["a"] = pd.DataFrame({"x": [1.0]}); k["b"] = pd.DataFrame({"y": [2.0]})
k["s"] = stack(wf["a"], wf["b"]); k.run_all()
out = k.step("s").output
print("\nstack's states:", out.states[["x", "y"]].to_dict())
k["copy"] = out.data[["x", "y"]].copy()
print("its values as a data step, states:", k.step("copy").output.states.to_dict())
k["f"] = pd.DataFrame({"x": pd.array([1.0, None], dtype="Float64")})
d = k.step("f").output.data
print("Float64 [1.0, <NA>] as a data step:", d["x"].dtype, list(map(repr, d["x"])))
