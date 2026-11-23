"""pandas' conventions for widening uneven data, on the same cases as widen.py
(expression-grammar/primitives.md §8).

    .venv/bin/python docs/design/grid-probes/pandas_widen.py
"""
import warnings; warnings.filterwarnings("ignore")
from dataclasses import dataclass
from typing import NamedTuple
import numpy as np, pandas as pd
print("pandas", pd.__version__)
class RGB(NamedTuple):
    r: int; g: int; b: int
@dataclass
class P:
    x: int; y: int
def show(label, f):
    try:
        out = f()
        print(f"{label:38} cols {list(out.columns)}  rows {out.astype(object).where(out.notna(), '<NA>').values.tolist()}  dtypes {[str(t) for t in out.dtypes]}")
    except Exception as e:
        print(f"{label:38} ERR {type(e).__name__}: {str(e)[:90]}")
S = lambda vals: pd.Series(vals, index=[10, 11][:len(vals)])
show("DataFrame(ragged dicts)",          lambda: pd.DataFrame([{"a": 1}, {"a": 2, "b": 3}]))
show("DataFrame(ragged lists)",          lambda: pd.DataFrame([[1, 2], [3]]))
show("DataFrame(ragged tuples)",         lambda: pd.DataFrame([(1, 2, 3), (4,)]))
show("DataFrame(int-key dicts)",         lambda: pd.DataFrame([{1: "x", 2: "y"}]))
show("DataFrame(NamedTuples)",           lambda: pd.DataFrame([RGB(1, 2, 3), RGB(4, 5, 6)]))
show("DataFrame(dataclasses)",           lambda: pd.DataFrame([P(1, 2)]))
show("DataFrame(dict, None)",            lambda: pd.DataFrame([{"a": 1}, None]))
show("DataFrame(dict, 'oops')",          lambda: pd.DataFrame([{"a": 1}, "oops"]))
show("DataFrame(strings)",               lambda: pd.DataFrame(["ab", "cd"]))
show("json_normalize(nested)",           lambda: pd.json_normalize([{"a": {"z": 1}, "b": 2}]))
show("json_normalize(nested, max_level=0)", lambda: pd.json_normalize([{"a": {"z": 1}}], max_level=0))
show("json_normalize(dict, None)",       lambda: pd.json_normalize([{"a": 1}, None]))
show("Series(dicts).apply(pd.Series)",   lambda: S([{"a": 1}, {"b": 2}]).apply(pd.Series))
show("Series(dict, None).apply(Series)", lambda: S([{"a": 1}, None]).apply(pd.Series))
show("Series(dict, 'oops').apply(Series)", lambda: S([{"a": 1}, "oops"]).apply(pd.Series))
show("Series(arrays).apply(Series)",     lambda: S([np.array([1, 2]), np.array([3])]).apply(pd.Series))
show("str.split(expand=True) ragged",    lambda: S(["a-b", "c"]).str.split("-", expand=True))
show("DataFrame(s.tolist(), index=s.index)", lambda: pd.DataFrame(S([{"a": 1}, {"a": 2}]).tolist(), index=S([1, 2]).index))
e = pd.Series([[1, 2], [], None, 5], index=[0, 1, 2, 3]).explode()
print(f"{'explode([1,2], [], None, 5)':38} index {list(e.index)} values {[None if pd.isna(v) else v for v in e]}")
