"""The tutorial: every source, pick, verb, modifier and combine, run and checked.

Run it with ``.venv/bin/python tutorial/tutorial.py``. Each lesson writes one
expression, runs it, and compares what core did with what we want
(docs/design/model.md). It prints one line per lesson:

    ✓  core does what we want
    ✗  core doesn't yet; the note names the decision or plan step
    ?  we haven't decided what we want; the note asks the question

The walkthrough that explains each lesson is tutorial/README.md. This file
changes no behaviour; it only reports.
"""

from __future__ import annotations

import warnings

import pandas as pd

from simple_steps_core import (Catalog, Kernel, bound_tool, cols, join, mod, op,
                               res, resource, row, rows, stack, tool, wf, zip_)

warnings.simplefilter("ignore")


# ── the tools: plain Python functions, typed ─────────────────────────────
@tool
def patients() -> pd.DataFrame:
    """Today's patients."""
    return pd.DataFrame({"name": ["Ada", "Ben", "Cy"], "ward": ["A", "B", "A"],
                         "temp": [37.0, 38.5, 36.9]})


@tool
def to_f(temp: float) -> float:
    return round(temp * 9 / 5 + 32, 1)


@tool
def hot(temp: float, limit: float = 38) -> bool:
    return temp >= limit


@tool
def two(temp: float) -> list:
    return [temp, temp + 1]


@tool
def mean_t(temp: list) -> float:
    return sum(temp) / len(temp)


@tool
def add(acc: float, temp: float) -> float:
    return acc + temp


@tool
def first_letter(name: str) -> str:
    return name[0]


@tool
def info(name: str) -> dict:
    return {"len": len(name), "up": name.upper()}


@tool
def describe(df: pd.DataFrame) -> pd.DataFrame:
    return df.describe().reset_index()


@tool
def label(a: int, b: str) -> str:
    return f"{a}{b}"


@tool
def flaky(temp: float) -> float:
    if temp > 38:
        raise ValueError("too hot")
    return temp


@tool
def add_xy(a: int, b: int) -> int:
    return a + b


@resource
class Lab:
    """A lab whose thermometers read high by a factor."""

    def __init__(self, scale: float = 1.0):
        self.scale = scale

    @bound_tool
    def adjust(self, temp: float) -> float:
        return temp * self.scale


CATALOG = Catalog(tools=[patients, to_f, hot, two, mean_t, add, first_letter, info,
                         describe, label, flaky, add_xy], resources=[Lab])


# ── the harness ───────────────────────────────────────────────────────────
RESULTS: list[tuple[str, str, str, str]] = []


def lesson(code: str, title: str, got, want, note: str = "", *, open_: bool = False):
    """Compare what core did with what we want, and record the verdict."""
    mark = "?" if open_ else ("✓" if got == want else "✗")
    RESULTS.append((mark, code, title, note))
    line = f"  {mark} {code:<5} {title}"
    if mark != "✓":
        line += f"\n          got:  {got!r}"
        if not open_:
            line += f"\n          want: {want!r}"
        if note:
            line += f"\n          note: {note}"
    print(line)


def chapter(title: str):
    print(f"\n── {title} " + "─" * max(0, 70 - len(title)))


class Later:
    """An expression built inside put(), for one refused while it's written."""

    def __init__(self, build):
        self.build = build


def put(k: Kernel, name: str, expression):
    """Declare a step and run it; return the step, or the exception raised."""
    try:
        k[name] = expression.build() if isinstance(expression, Later) else expression
    except Exception as e:                      # noqa: BLE001 – a refusal is a result
        return e
    try:
        k.run(name)
    except Exception:                           # noqa: BLE001 – the state says why
        pass
    return k.step(name)


def data(step, column=None):
    frame = step.data
    return frame[column].tolist() if column else frame.to_dict("list")


def problems(step) -> str:
    return " | ".join(p.message for p in step.problems)


def base() -> Kernel:
    k = Kernel(CATALOG)
    k["v"] = patients[mod.source()]()
    k.run_all()
    return k


# ── 1. the kernel and its catalog ────────────────────────────────────────
def ch1():
    chapter("1. The kernel and its catalog: the workbook and its function list")
    k = Kernel(Catalog(tools=[patients]))
    k["v"] = patients[mod.source()]()
    s = put(k, "f", to_f[mod.map()](wf["v"]))
    lesson("K1", "a tool not in the catalog makes the step invalid, never runs",
           (s.state, problems(s)), ("invalid", "'to_f' is not in this workflow's catalog"))
    s = put(k, "g", to_f[mod.map()](wf["later"]))
    lesson("K2", "a step reads only earlier steps", s.state, "invalid")


# ── 2. data in ───────────────────────────────────────────────────────────
def ch2():
    chapter("2. Data in: the ways a value enters a workflow")
    k = base()
    lesson("D1", "a source tool: its DataFrame becomes the rows",
           data(k.step("v"), "name"), ["Ada", "Ben", "Cy"])
    lesson("D2", "a literal is one cell (a control, like a typed-in cell)",
           data(put(k, "lim", 38.0)), {"value": [38.0]})
    lesson("D3", "a list is one cell until a verb says what its items mean",
           data(put(k, "lst", [1, 2, 3])), {"value": [[1, 2, 3]]})
    lesson("D4", "a dict is one cell too",
           data(put(k, "dct", {"x": 1, "y": 2})), {"value": [{"x": 1, "y": 2}]})
    lesson("D5", "a DataFrame assigned directly is rows",
           data(put(k, "df", pd.DataFrame({"name": ["Ada", "Zed"], "score": [1, 2]})), "name"),
           ["Ada", "Zed"])
    s = put(k, "empty", None)
    lesson("D6", "an empty step is one cell 'empty', staged",
           (s.state, data(s)), ("staged", {"value": ["empty"]}))
    s = put(k, "r", to_f[mod.map()](wf["empty"]))
    lesson("D7", "nothing can read an empty step", s.state, "invalid")
    s = put(k, "sw", label[mod.sweep(a=[1, 2], b=["x", "y"])]())
    lesson("D8", "sweep: one row per combination of settings",
           data(s, "value"), ["1x", "1y", "2x", "2y"])
    k.define("lab", Lab, scale=2.0)
    s = put(k, "adj", res["lab"].adjust[mod.map()](wf["v"]))
    lesson("D9", "a resource: a live object built from settings, its tool used per row",
           data(s)[s.data.columns[0]], [74.0, 77.0, 73.8])
    k.define("lab", Lab, scale=3.0)
    lesson("D10", "changing a resource's settings makes its readers stale",
           k.step("adj").state, "stale")
    s = put(k, "fn", lambda temp: temp)
    lesson("D11", "assigning a Python function stores it as a value", s.state, "completed",
           "should a bare function be refused, pointing to @tool and the catalog?", open_=True)


# ── 3. picks ─────────────────────────────────────────────────────────────
def ch3():
    chapter("3. Picks: part of an earlier step, like a cell range")
    k = base()
    k["e"] = two[mod.expand()](wf["v"])
    k.run_all()
    lesson("P1", "an integer is a row number", data(put(k, "a", wf["v"][1]), "name"), ["Ben"])
    lesson("P2", "negative numbers count from the end", data(put(k, "b", wf["v"][-1]), "name"), ["Cy"])
    lesson("P3", "a list of rows needs double brackets", data(put(k, "c", wf["v"][[0, 2]]), "name"), ["Ada", "Cy"])
    lesson("P4", "a range", data(put(k, "d", wf["v"][1:3]), "name"), ["Ben", "Cy"])
    s = put(k, "oob", wf["v"][7])
    lesson("P5", "a row out of range is refused, saying how many there are",
           problems(s), "select: 'v' has no row 7 (it has 3: 0–2)")
    lesson("P6", "a condition on data chooses rows",
           data(put(k, "hot", wf["v"][cols["temp"] > 37]), "name"), ["Ben"])
    s = put(k, "none", wf["v"][cols["temp"] > 99])
    lesson("P7", "a condition matching nothing: zero rows and a warning",
           (len(s.data), len(s.warnings)), (0, 1))
    s = put(k, "must", wf["v"][rows[cols["temp"] > 99]])
    lesson("P8", "rows[condition] names rows that must exist: none is a problem", s.state, "invalid")
    s = put(k, "kid", wf["e"][row["v"] == 1])
    lesson("P9", "a condition on lineage chooses the rows that came from row 1 of v",
           list(s.data["value"]), [38.5, 39.5])
    lesson("P9b", "…without a warning that it is positional", len(s.warnings), 0,
           "warns 'rows … are positions, and expand doesn't fix row order': a lineage "
           "condition isn't positional")
    lesson("P10", "columns are picked with cols[…]",
           data(put(k, "col", wf["v"][cols["temp"]])), {"temp": [37.0, 38.5, 36.9]})
    s = put(k, "str", Later(lambda: wf["v"]["temp"]))
    lesson("P11", "a string chooses a column: wf['v']['temp']", type(s).__name__, "Step",
           "refused today: 'temp' read as a row. Planned S3 (D2: an integer is a row, a string a key)")
    lesson("P12", "a row and a column: one cell",
           data(put(k, "cell", wf["v"][1][cols["temp"]])), {"temp": [38.5]})
    s = put(k, "lin", wf["hot"][cols["#v"]])
    lesson("P13", "lineage can't be picked; the refusal writes the copy",
           s.state, "invalid")
    k["srt"] = mod.sort(by="temp")(wf["v"])
    k.run_all()
    k["one"] = wf["srt"][1]
    k.run_all()
    lesson("P14", "a picked row is saved as the row it is, so it follows a re-sort",
           (data(k.step("one"), "name"), 'row["v"] == 0' in str(k)),
           (["Ada"], True))
    k["src"] = pd.DataFrame({"name": ["Ada", "Ben"]})
    k["pk"] = wf["src"][0]
    k.run_all()
    k["src"] = pd.DataFrame({"name": ["Zed", "Ada", "Ben"]})
    k.run_all()
    lesson("P15", "a pick into a source still gives Ada after a row is inserted above",
           data(k.step("pk"), "name"), ["Ada"],
           "gives Zed, completed, no warning: silent wrong answer. Decision D-picks")
    e = put(k, "sub", Later(lambda: to_f[mod.map()](wf["v"][cols["temp"] > 37])))
    lesson("P16", "a pick can be a tool's input", type(e).__name__, "Step",
           "refused: make the pick its own step. Planned S3 (D6)")


# ── 4. verbs: how a tool is applied ──────────────────────────────────────
def ch4():
    chapter("4. Verbs: how a function is applied (fill-down, filter, pivot…)")
    k = base()
    lesson("V1", "map: once per row, one row out per row in",
           data(put(k, "f", to_f[mod.map()](wf["v"])), "value"), [98.6, 101.3, 98.4])
    lesson("V1b", "map's one output column is named after its step",
           list(k.step("f").data.columns), ["f"], "named 'value'. Planned S4 (D9)")
    lesson("V2", "filter: keeps the rows the test approves, with all their columns",
           data(put(k, "h", hot[mod.filter()](wf["v"])), "name"), ["Ben"])
    s = put(k, "e", two[mod.expand()](wf["v"]))
    lesson("V3", "expand: one row per item, lineage #v and #v.idx",
           (list(s.data["value"]), list(s.data["#v"])),
           ([37.0, 38.0, 38.5, 39.5, 36.9, 37.9], [0, 0, 1, 1, 2, 2]))
    s = put(k, "c", mean_t[mod.collapse(by="ward")](wf["v"]))
    lesson("V4", "collapse(by=): one row per group, the key kept, lineage lists the members",
           (data(s, "ward"), data(s, "value"), data(s, "#v")),
           (["A", "B"], [36.95, 38.5], [[0, 2], [1]]))
    s = put(k, "acc", add[mod.collapse(initial=0.0)](wf["v"]))
    lesson("V5", "collapse with an accumulator (acc, x) and a starting value",
           [round(x, 1) for x in data(s, "value")], [112.4])
    s = put(k, "g", first_letter[mod.group()](wf["v"]))
    lesson("V6", "group: adds a key column, rows unchanged",
           data(s, "group"), ["A", "B", "C"])
    s = put(k, "t", describe[mod.table()](wf["v"]))
    lesson("V7", "table: the whole input to one call, its own rows (opaque)",
           len(s.data), 8)
    s = put(k, "auto", to_f(wf["v"]))
    lesson("V8", "no verb written: inferred from the types (here map)",
           data(s, "value"), [98.6, 101.3, 98.4])
    s = put(k, "auto_f", hot(wf["v"]))
    lesson("V8b", "no verb written, a -> bool tool: a map of bools, never a filter (D20b)",
           len(s.data), 3, "inferred as filter: a bare call drops rows. D20b decided 2026-11-02")
    s = put(k, "two", to_f[mod.map(), mod.filter()](wf["v"]))
    lesson("V9", "one verb per step: two is refused", s.state, "invalid")
    s = put(k, "ax", to_f[mod.map(axis="columns")](wf["v"]))
    lesson("V10", "a setting that does nothing is refused (map axis='columns')",
           s.state, "invalid", "accepted and ignored: runs by rows. Remove the setting?")
    s = put(k, "wh", to_f[mod.map(where=cols["temp"] > 37)](wf["v"]))
    lesson("V11", "map(where=…) takes a tool, not a condition", s.state, "invalid",
           "keep map(where=, replace=)? It overlaps filter + join", open_=True)


# ── 5. reshapes: no tool ─────────────────────────────────────────────────
def ch5():
    chapter("5. Reshapes: column and row moves with no function")
    k = base()
    k["h"] = hot[mod.filter()](wf["v"])
    k.run_all()
    lesson("R1", "select keeps columns", list(put(k, "s", mod.select(columns=["name"])(wf["v"])).data.columns), ["name"])
    lesson("R2", "drop removes columns", list(put(k, "d", mod.drop(columns=["ward"])(wf["v"])).data.columns), ["name", "temp"])
    lesson("R3", "rename", list(put(k, "r", mod.rename(columns={"temp": "t"})(wf["v"])).data.columns), ["name", "ward", "t"])
    lesson("R4", "copy lineage into data", data(put(k, "c", mod.copy(columns={"#v": "parent"})(wf["h"])), "parent"), [1])
    lesson("R5", "sort", data(put(k, "o", mod.sort(by="temp")(wf["v"])), "name"), ["Cy", "Ada", "Ben"])
    lesson("R6", "slice", data(put(k, "sl", mod.slice(stop=2)(wf["v"])), "name"), ["Ada", "Ben"])
    s = put(k, "u", mod.distinct(columns=["ward"])(wf["v"]))
    lesson("R7", "distinct: first of each, lineage lists the duplicates",
           (data(s, "ward"), data(s, "#v")), (["A", "B"], [[0, 2], [1]]))
    s = put(k, "p", op("identity")[mod.pack(columns=["name", "temp"]), mod.name("rec")](wf["v"]))
    lesson("R8", "pack: columns into one dict per row", data(s, "rec")[0], {"name": "Ada", "temp": 37.0})
    lesson("R9", "widen: a dict column back into columns",
           list(put(k, "w", mod.widen(column="rec")(wf["p"])).data.columns), ["ward", "name", "temp"])
    k["lst"] = [1, 2, 3]
    lesson("R10", "expand with no tool: a list cell into rows",
           data(put(k, "x", mod.expand()(wf["lst"])), "value"), [1, 2, 3])
    k["i"] = info[mod.map()](wf["v"])
    k.run_all()
    s = put(k, "wb", mod.widen(wf["i"]))
    lesson("R11", "a step passed where a setting belongs is refused: mod.widen(wf['i'])",
           type(s).__name__, "TypeError",
           "accepted; the step fails with None. Other reshapes refuse 'takes settings by keyword'")
    s = put(k, "pn", mod.pack(columns=["name"], name="rec")(wf["v"]))
    lesson("R12", "a retired setting is refused, naming the replacement", s.state, "invalid")


# ── 6. built-in tools ────────────────────────────────────────────────────
def ch6():
    chapter("6. Built-in tools: COUNT, SUM, the first and the last")
    k = base()
    by = mod.collapse(by="ward")
    lesson("B1", "count", data(put(k, "n", op("count")[by](wf["v"])), "value"), [2, 1])
    k["t"] = mod.select(columns=["temp"])(wf["v"])
    lesson("B2", "total", [round(x, 1) for x in data(put(k, "s", op("total")[mod.collapse()](wf["t"])), "temp")], [112.4])
    lesson("B3", "gather: each group's values into lists",
           data(put(k, "g", op("gather")[by](wf["v"])), "name"), [["Ada", "Cy"], ["Ben"]])
    lesson("B4", "first", data(put(k, "f", op("first")[by](wf["v"])), "name"), ["Ada", "Ben"])
    lesson("B5", "last", data(put(k, "l", op("last")[by](wf["v"])), "name"), ["Cy", "Ben"])


# ── 7. arguments and binding ─────────────────────────────────────────────
def ch7():
    chapter("7. Arguments: which column reaches which parameter")
    k = base()
    k["lim"] = 38.0
    k["srt"] = mod.sort(by="temp")(wf["v"])
    k["h"] = hot[mod.filter()](wf["v"])
    k["e"] = two[mod.expand()](wf["v"])
    k.run_all()
    lesson("A1", "a parameter binds to the input column of its name",
           data(put(k, "f", to_f[mod.map()](wf["v"])), "value"), [98.6, 101.3, 98.4])
    lesson("A2", "an argument from another step's value (a control)",
           data(put(k, "a", hot[mod.filter()](wf["v"], limit=wf["lim"])), "name"), ["Ben"])
    lesson("A3", "a cell pick is one value for every row",
           data(put(k, "b", hot[mod.filter()](wf["v"], limit=wf["v"][0][cols["temp"]])), "name"), ["Ada", "Ben"])
    s = put(k, "c", hot[mod.filter()](wf["v"], limit=wf["srt"][cols["temp"]]))
    lesson("A4", "a column from an aligned step pairs row with row", data(s, "name"), ["Ada", "Ben", "Cy"])
    lesson("A4b", "…and a filter's output keeps only its input's columns",
           list(s.data.columns), ["name", "ward", "temp"],
           "the argument 'limit' is added as a column")
    s = put(k, "d", hot[mod.filter()](wf["v"], limit=wf["h"][cols["temp"]]))
    lesson("A5", "a column from a subset is refused, writing the join", s.state, "invalid")
    s = put(k, "x", to_f[mod.map()](wf["e"], temp=wf["v"][cols["temp"]]))
    lesson("A6", "a parent's column into its child is refused, writing the join (D-child)", s.state, "invalid")
    s = put(k, "y", to_f[mod.map()](wf["v"], nope=1))
    lesson("A7", "an unknown argument names what the tool accepts",
           problems(s), "to_f() takes no argument 'nope'; it accepts temp",
           "says 'it accepts (none)'")
    k["xy"] = pd.DataFrame({"x": [1], "y": [2]})
    s = put(k, "z", add_xy[mod.map()](wf["xy"]))
    lesson("A8", "no column of the parameter's name: invalid, naming the fix",
           "a=wf" in problems(s), True, "names the gap, not the fix. Planned S3 (CA-A)")
    s = put(k, "z2", add_xy[mod.map()](wf["xy"], a=wf["xy"][cols["x"]], b=wf["xy"][cols["y"]]))
    lesson("A9", "binding written out", data(s, "value"), [3])
    k["f2"] = to_f[mod.map()](wf["v"])
    s = put(k, "chain", to_f[mod.map()](wf["f2"]))
    lesson("A10", "map after map reads the first map's output", s.state, "completed",
           "invalid: the first map's column is 'value', not 'temp'. Fixed by S4 naming + S3 binding")


# ── 8. combines ──────────────────────────────────────────────────────────
def ch8():
    chapter("8. Combines: putting two steps' rows side by side")
    k = base()
    k["f"] = to_f[mod.map()](wf["v"])
    k["srt"] = mod.sort(by="temp")(wf["v"])
    k["fs"] = to_f[mod.map(), mod.name("tf")](wf["srt"])
    k["h"] = hot[mod.filter()](wf["v"])
    k["e"] = two[mod.expand()](wf["v"])
    k["c"] = op("count")[mod.collapse(by="ward")](wf["v"])
    k["df"] = pd.DataFrame({"name": ["Ada", "Zed"], "score": [1, 2]})
    k["n"] = pd.DataFrame({"score": [1, 2, 3]})
    k.run_all()
    lesson("C1", "zip_: each row beside its own map",
           data(put(k, "z", zip_(wf["v"], wf["f"])), "value"), [98.6, 101.3, 98.4])
    lesson("C2", "zip_ pairs by identity, not position, after a sort",
           data(put(k, "z2", zip_(wf["v"], wf["fs"])), "tf"), [98.6, 101.3, 98.4])
    lesson("C3", "zip_ of a subset is refused, writing the join",
           put(k, "z3", zip_(wf["v"], wf["h"])).state, "invalid")
    lesson("C4", "zip_ of unrelated steps is refused", put(k, "z4", zip_(wf["v"], wf["n"])).state, "invalid")
    lesson("C5", "match_ids=True: you vouch they number the same samples",
           data(put(k, "z5", zip_(wf["v"], wf["n"], match_ids=True)), "score"), [1, 2, 3])
    s = put(k, "j", join(wf["v"], wf["df"], on="name", how="left"))
    lesson("C6", "join on a value, how='left'", data(s, "name"), ["Ada", "Ben", "Cy"])
    s = put(k, "jl", join(wf["e"], wf["v"], on="#v"))
    lesson("C7", "join on lineage: each child beside its parent", data(s, "name"),
           ["Ada", "Ada", "Ben", "Ben", "Cy", "Cy"])
    lesson("C8", "a group can't join on lineage: unpack first",
           put(k, "jg", join(wf["c"], wf["v"], on="#v")).state, "invalid")
    s = put(k, "cu", mod.expand(columns=["#v"])(wf["c"]))
    lesson("C9", "unpacking a group gives one row per member", len(s.data), 3)
    s = put(k, "st", stack(wf["v"], wf["df"]))
    lesson("C10", "stack: rows one after another, gaps absent", len(s.data), 5)
    e = put(k, "zi", zip_(wf["v"], to_f[mod.map()](wf["srt"])))
    lesson("C11", "an inline expression can be a combine's input",
           getattr(e, "state", type(e).__name__), "completed",
           "invalid: 'not an earlier step'. Make it its own step, or allow it? (S3)", open_=True)


# ── 9. wrappers: failures and promises ───────────────────────────────────
def ch9():
    chapter("9. Wrappers: failures stay per cell (like #VALUE!)")
    k = base()
    s = put(k, "a", flaky[mod.map()](wf["v"]))
    lesson("W1", "a failing row fails its cell; the others run",
           (s.state, data(s, "value")[0], data(s, "value")[2]), ("failed", 37.0, 36.9))
    k["after"] = to_f[mod.map()](wf["v"])
    try:
        k.run_all()
        stopped = False
    except Exception:                                   # noqa: BLE001
        stopped = True
    lesson("W2", "without try_except, run_all stops at the failure, naming the fix", stopped, True)
    s = put(k, "b", flaky[mod.map(), mod.try_except()](wf["v"]))
    lesson("W3", "try_except: the failure is a failed cell that doesn't stop run_all", s.state, "failed")
    s = put(k, "c", flaky[mod.map(), mod.try_except(default=-1.0)](wf["v"]))
    lesson("W4", "try_except(default=): the default, and a warning",
           (data(s, "value"), len(s.warnings)), ([37.0, -1.0, 36.9], 1))
    s = put(k, "d", flaky[mod.map(), mod.breaker(after=1)](wf["v"]))
    lesson("W5", "breaker: after n failures, the rest are blocked", s.state, "failed")
    s = put(k, "e", to_f[mod.map(), mod.retry(times=2), mod.timeout(seconds=2)](wf["v"]))
    lesson("W6", "retry and timeout wrap the call; order written is order applied", s.state, "completed")
    s = put(k, "f", two[mod.expand(), mod.expect(rows=6)](wf["v"]))
    lesson("W7", "expect: a promise about the shape, kept", s.state, "completed")
    s = put(k, "g", two[mod.expand(), mod.expect(rows=5)](wf["v"]))
    lesson("W8", "expect: a promise broken fails loudly", s.state, "failed")


# ── 10. plans ────────────────────────────────────────────────────────────
def ch10():
    chapter("10. Plans: the shape before anything runs")
    k = Kernel(CATALOG)
    k["v"] = patients[mod.source()]()
    k["f"] = to_f[mod.map()](wf["v"])
    k["e"] = two[mod.expand()](wf["v"])
    k.run("v")
    plan = k.step("f").output.plan
    lesson("L1", "map's plan: rows exact before it runs", plan["rows"]["certainty"], "exact")
    plan = k.step("e").output.plan
    lesson("L2", "expand's plan: rows unknown, saying why", plan["rows"]["certainty"], "unknown")


# ── 11. the session: edit, run, states ───────────────────────────────────
def ch11():
    chapter("11. The session: an edit is checked at once, a run is on request")

    def states(k):
        return {s.name: s.state for s in k.steps}

    k = Kernel(CATALOG)
    k["v"] = patients[mod.source()]()
    k["lim"] = 38.0
    k["h"] = hot[mod.filter()](wf["v"], limit=wf["lim"])
    k["f"] = to_f[mod.map()](wf["h"])
    lesson("S1", "declaring runs nothing: steps are staged",
           states(k), {"v": "staged", "lim": "completed", "h": "staged", "f": "staged"})
    k.run_all()
    k["lim"] = 38.0
    lesson("S2", "the same value again: nothing goes stale", k.step("f").state, "completed")
    k["lim"] = 37.0
    lesson("S3", "a change: readers keep their values, marked stale",
           (k.step("h").state, k.step("f").state), ("stale", "stale"))
    lesson("S4", "the stale reason is among the step's warnings", len(k.step("h").warnings) > 0, True,
           "only in needs_run() and output metadata. SS7")
    k.run("f")
    lesson("S5", "run('f') makes f current: runs h first",
           (k.step("h").state, k.step("f").data["value"].tolist()), ("completed", [98.6, 101.3]),
           "h stays stale; f computed from h's old rows and shown completed. Decision SM")
    k.run_all()
    k["lim"] = 38.0
    k["lim"] = 37.0
    lesson("S6", "a value changed and put back: completed, no re-run", k.step("f").state, "completed")
    k["f"] = to_f[mod.map(), mod.name("x")](wf["h"])
    k["f"] = to_f[mod.map()](wf["h"])
    lesson("S7", "an expression changed and put back: completed, no re-run",
           k.step("f").state, "completed", "stale ('updated args'). Decision SM")
    k["w"] = pd.DataFrame({"temp": [36.0, 39.0]})
    k["g"] = to_f[mod.map()](wf["w"])
    k.run_all()
    k["w"] = pd.DataFrame({"t": [36.0, 39.0]})
    lesson("S8", "a column removed upstream: invalid at once, still showing its last values",
           (k.step("g").state, data(k.step("g"))[k.step("g").data.columns[0]]),
           ("invalid", [96.8, 102.2]), "values dropped. Decision SM")
    k["w"] = pd.DataFrame({"temp": [36.0, 39.0]})
    lesson("S9", "the column put back: completed again, no re-run", k.step("g").state, "completed",
           "staged: must re-run. Decision SM")
    try:
        del k["h"]
        refused = False
    except ValueError:
        refused = True
    lesson("S10", "deleting a step something reads is refused, naming the reader", refused, True)
    k.rename("lim", "limit")
    lesson("S11", "rename rewrites every reference", 'wf["limit"]' in str(k), True)
    try:
        k.move("f", 0)
        refused = False
    except ValueError:
        refused = True
    lesson("S12", "a move that puts a reader before what it reads is refused", refused, True)
    lesson("S13", "check: a proposal's problems without adding it",
           k.check("zz", to_f[mod.map()](wf["nowhere"]))[0].code, "missing_step")


# ── 12. save, load, provenance ───────────────────────────────────────────
def ch12():
    chapter("12. Save and load: specs, never data")
    k = base()
    k["f"] = to_f[mod.map()](wf["v"])
    k.run_all()
    k.step("f").extras["simple_steps.ui"] = {"color": "red"}
    k2 = Kernel.from_json(k.to_json(), CATALOG)
    lesson("Y1", "loading runs nothing", sorted({s.state for s in k2.steps}), ["staged"])
    k2.run_all()
    lesson("Y2", "loaded and run: the same data, the same id",
           (k2.step("f").data["value"].tolist(), k2.id == k.id), ([98.6, 101.3, 98.4], True))
    lesson("Y3", "extras survive and aren't hashed", k2.step("f").extras, {"simple_steps.ui": {"color": "red"}})
    cell = k.cell("f", 1)
    lesson("Y4", "a cell says what it was computed from", cell["inputs"][0]["values"], {"temp": 38.5})


CHAPTERS = [ch1, ch2, ch3, ch4, ch5, ch6, ch7, ch8, ch9, ch10, ch11, ch12]


def main() -> None:
    for ch in CHAPTERS:
        ch()
    tally = {m: sum(1 for r in RESULTS if r[0] == m) for m in "✓✗?"}
    print(f"\n{len(RESULTS)} lessons: {tally['✓']} ✓  {tally['✗']} ✗  {tally['?']} ?")


if __name__ == "__main__":
    main()
