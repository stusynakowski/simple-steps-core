"""pandas' conventions for pivot, fill and one call per column, on the cases
that usually go wrong (expression-grammar/pivot-fill-columns.md).

    .venv/bin/python docs/design/grid-probes/pivot_fill_columns.py
"""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd


def show(label, f):
    try:
        out = f()
        if isinstance(out, pd.DataFrame):
            print(f"{label:42} cols {[str(c) for c in out.columns]} rows {out.astype(object).where(out.notna(), '<NA>').reset_index().values.tolist()}")
        else:
            print(f"{label:42} {out}")
    except Exception as e:
        print(f"{label:42} ERR {type(e).__name__}: {str(e)[:80]}")


long = pd.DataFrame({"who": ["Ada", "Ada", "Ben"], "when": ["pm", "am", "am"], "temp": [37.4, 37.0, 39.5]})
show("pivot", lambda: long.pivot(index="who", columns="when", values="temp"))
dup = pd.concat([long, pd.DataFrame({"who": ["Ada"], "when": ["am"], "temp": [36.0]})])
show("pivot, a duplicate (Ada, am)", lambda: dup.pivot(index="who", columns="when", values="temp"))
show("pivot_table, the same duplicate", lambda: dup.pivot_table(index="who", columns="when", values="temp"))
years = pd.DataFrame({"who": ["Ada", "Ada"], "year": [2020, 2021], "n": [1, 2]})
show("pivot, names from integers", lambda: years.pivot(index="who", columns="year", values="n"))
two = long.assign(pulse=[70, 72, 80])
show("pivot, two value columns", lambda: two.pivot(index="who", columns="when", values=["temp", "pulse"]))
nonename = pd.DataFrame({"who": ["Ada", "Ada"], "when": ["am", None], "temp": [1.0, 2.0]})
show("pivot, a None in the names column", lambda: nonename.pivot(index="who", columns="when", values="temp"))

gaps = pd.DataFrame({"g": ["a", "a", "b", "b"], "x": [None, 1.0, None, 3.0]})
show("ffill", lambda: gaps.ffill())
show("ffill within groups", lambda: gaps.assign(x=gaps.groupby("g")["x"].ffill()))
show("bfill", lambda: gaps.bfill())
run = pd.DataFrame({"x": [1.0, None, None, None]})
show("ffill, limit=1", lambda: run.ffill(limit=1))

num = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [10.0, 20.0, 30.0]})
show("apply per column, one value each", lambda: num.apply(lambda c: c.mean()))
show("apply per column, same length", lambda: num.apply(lambda c: (c - c.mean()).round(2)))
show("apply per column, other lengths", lambda: num.apply(lambda c: [1, 2]))
