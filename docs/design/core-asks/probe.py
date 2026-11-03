"""
probe.py — the tests of plan.md (this folder), run against core alone.

    python probe.py          # every milestone
    python probe.py M0 M2    # some of them

PASS  core does what 012 asks.
FAIL  it doesn't yet; the line says what it did instead.
SKIP  the test needs something a Python call can't show (it's noted why).

Exits 0 always: this is a report, not a gate. No app code is imported.
"""

from __future__ import annotations

import re
import sys

import pandas as pd

import simple_steps_core as core
from simple_steps_core import Catalog, Kernel, cols, join, mod, op, rows, stack, tool, wf, zip_

identity = op("identity")
row = getattr(core, "row", None)          # L30: doesn't exist yet


# ── The shared fixture (012 §3) ──────────────────────────────────────────

R = {"ward": ["A", "B", "A", "C"], "n": [10, 20, 30, 40]}
OTHER = {"ward": ["A", "C", "D"], "pop": [1, 2, 3]}
THIRD = {"ward": ["A", "B", "C"], "area": [5, 6, 7]}


@tool
def double(n: int) -> int:
    return n * 2


@tool
def is_big(n: int) -> bool:
    return n >= 20


@tool
def split_in_two(n: int) -> list:
    return [n, n + 1]


@tool
def add_up(n: list) -> int:
    return sum(n)


@tool
def add_k(n: int, k: int) -> int:
    return n + k


@tool
def add_all(n: int, k: list) -> int:
    return n + sum(k)


@tool
def total_of(k: list) -> int:
    return sum(k)


@tool
def pair(n: int) -> dict:
    return {"a": n, "b": n + 1}


@tool
def shout(s: str) -> str:
    return s.upper()


@tool
def half(x: float) -> float:
    return x / 2


@tool
def scale(x: int, factor: int = 2) -> int:
    return x * factor


@tool
def rows_of(n: int, t: pd.DataFrame) -> int:
    return len(t)


TOOLS = [double, is_big, split_in_two, add_up, add_k, add_all, total_of, pair, shout, half, scale, rows_of]


def kernel() -> Kernel:
    k = Kernel(Catalog(TOOLS))
    k["r"] = pd.DataFrame(R)
    k["other"] = pd.DataFrame(OTHER)
    k["third"] = pd.DataFrame(THIRD)
    k["filtered"] = is_big[mod.filter()](wf["r"])
    k["sorted_"] = identity[mod.sort(by="n", ascending=False)](wf["r"])
    k["expanded"] = split_in_two[mod.expand()](wf["r"])
    k["per_ward"] = add_up[mod.collapse(by="ward")](wf["r"])
    k["doubled"] = double[mod.map()](wf["r"])
    k.run_all()
    return k


# ── Helpers ──────────────────────────────────────────────────────────────

class Fail(Exception):
    pass


class Skip(Exception):
    pass


class Refused(Exception):
    pass


def put(k: Kernel, name: str, make):
    """Declare and run a step; its view, or Refused with core's reason."""
    try:
        k[name] = make()
        problems = k.step(name).problems
        if problems:
            raise Refused("; ".join(map(str, problems)))
        k.run(name)
    except Refused:
        raise
    except Exception as e:
        raise Refused(f"{type(e).__name__}: {e}") from None
    return k.view(name)


def names(v) -> list:
    return [c["name"] for c in v["columns"]]


def data_names(v) -> list:
    return [n for n in names(v) if not str(n).startswith("#")]


def lineage_names(v) -> set:
    found = {n for n in names(v) if str(n).startswith("#")}
    for item in v.get("lineage") or []:
        found.add(item["name"] if isinstance(item, dict) else item)
    return found


def data(v, col=None) -> list:
    if col is None:
        cs = data_names(v)
        if len(cs) != 1:
            raise Fail(f"expected one data column, got {cs}")
        col = cs[0]
    return [r["cells"].get(col, {}).get("value") for r in v["rows"]]


def lin(v, name) -> list:
    out = []
    for r in v["rows"]:
        source = r.get("lineage") or r["cells"]
        cell = source.get(name)
        out.append(cell.get("value") if isinstance(cell, dict) else cell)
    return out


def nums(v) -> list:
    return [r["#"] for r in v["rows"]]


def short(v) -> str:
    cells = [{c: x.get("value") for c, x in r["cells"].items()} for r in v["rows"][:4]]
    return f"# {nums(v)[:6]}, cells {cells}"


def state(v, col) -> list:
    return [r["cells"].get(col, {}).get("state") for r in v["rows"]]


def expect(got, wanted, what="") -> None:
    if got != wanted:
        raise Fail(f"{what}got {got!r}, want {wanted!r}")


def expect_refused(k, make, mention: str | None = None) -> None:
    try:
        v = put(k, "x", make)
    except Refused as e:
        if mention and mention.lower() not in str(e).lower():
            raise Fail(f"refused, but not for the right reason: {e}") from None
        return
    raise Fail(f"accepted: {short(v)}")


def out_col(k, step) -> str:
    """The single data column a tool step produced (`value` today; D2: the step's name)."""
    cs = data_names(k.view(step))
    if len(cs) != 1:
        raise Fail(f"{step} has data columns {cs}")
    return cs[0]


TESTS: list = []


def test(milestone: str, tid: str, title: str):
    def register(fn):
        TESTS.append((milestone, tid, title, fn))
        return fn
    return register


# ── M0: stop silent wrong results ────────────────────────────────────────

@test("M0", "TEST-L1", "column argument from an unaligned step is refused")
def _():
    expect_refused(kernel(), lambda: add_k[mod.map()](wf["r"], k=wf["filtered"][cols["n"]]), mention="join")


@test("M0", "TEST-L2", "zip_ of steps that don't line up is refused")
def _():
    expect_refused(kernel(), lambda: zip_(wf["doubled"], wf["filtered"]))


@test("M0", "TEST-L3a", "map: k: list given each row's int cell is refused")
def _():
    expect_refused(kernel(), lambda: add_all[mod.map()](wf["r"], k=wf["r"][cols["n"]]))


@test("M0", "TEST-L3b", "map: own column as argument, one value per row")
def _():
    expect(data(put(kernel(), "x", lambda: add_k[mod.map()](wf["r"], k=wf["r"][cols["n"]]))), [20, 40, 60, 80])


@test("M0", "TEST-L3c", "one call: a column arrives whole, as a list")
def _():
    expect(data(put(kernel(), "x", lambda: total_of[mod.source()](k=wf["r"][cols["n"]]))), [100])


@test("M0", "TEST-L3d", "map over list cells: each row's own list")
def _():
    k = kernel()
    put(k, "g", lambda: op("gather")[mod.collapse(by="ward")](wf["r"]))
    expect(data(put(k, "x", lambda: total_of[mod.map()](wf["g"], k=wf["g"][cols["n"]]))), [40, 20, 40])


@test("M0", "TEST-L3e", "map over list cells bound by name")
def _():
    k = kernel()
    put(k, "g", lambda: op("gather")[mod.collapse(by="ward")](wf["r"]))
    put(k, "g2", lambda: identity[mod.rename(columns={"n": "k"})](wf["g"]))
    expect(data(put(k, "x", lambda: total_of[mod.map()](wf["g2"]))), [40, 20, 40])


@test("M0", "TEST-L4", "a source with a '#' key is refused")
def _():
    expect_refused(kernel(), lambda: pd.DataFrame({"ward": ["A"], "#n": [1]}))


@test("M0", "TEST-L5", "total over mixed columns: sums what it can, fails the rest")
def _():
    k = kernel()
    put(k, "m", lambda: pd.DataFrame({"t": ["x", "y"], "a": [1, 2], "b": [10, 20]}))
    v = put(k, "x", lambda: op("total")[mod.collapse()](wf["m"]))
    expect(data(v, "a") + data(v, "b"), [3, 30], "a, b: ")
    expect(v["rows"][0]["cells"].get("t", {}).get("state"), "failed", "t: ")


@test("M0", "TEST-L5b", "total(numeric_only=True) leaves out what isn't numbers")
def _():
    k = kernel()
    put(k, "m", lambda: pd.DataFrame({"t": ["x", "y"], "a": [1, 2], "b": [10, 20]}))
    v = put(k, "x", lambda: op("total")[mod.collapse()](wf["m"], numeric_only=True))
    expect(data_names(v), ["a", "b"], "columns: ")
    expect(data(v, "a") + data(v, "b"), [3, 30], "a, b: ")


# ── M1: rows are placements ──────────────────────────────────────────────

for _step, _want in [("filtered", [0, 1, 2]), ("sorted_", [0, 1, 2, 3]),
                     ("expanded", list(range(8))), ("per_ward", [0, 1, 2])]:
    @test("M1", f"TEST-L6 {_step}", f"# of {_step} is 0..n-1")
    def _(step=_step, want=_want):
        expect(nums(kernel().view(step)), want)


@test("M1", "TEST-L7a", "[1] on sorted is the second row (n=30)")
def _():
    expect(data(put(kernel(), "x", lambda: wf["sorted_"][1]), "n"), [30])


@test("M1", "TEST-L7b", "[[0, 1]] on sorted is the first two rows")
def _():
    expect(data(put(kernel(), "x", lambda: wf["sorted_"][[0, 1]]), "n"), [40, 30])


@test("M1", "TEST-L7c", "[1:3] on sorted (keep green)")
def _():
    expect(data(put(kernel(), "x", lambda: wf["sorted_"][1:3]), "n"), [30, 20])


@test("M1", "TEST-L7d", "[-1] and rows[-1] are the last row")
def _():
    k = kernel()
    expect(data(put(k, "x", lambda: wf["sorted_"][-1]), "n"), [10], "[-1]: ")
    expect(data(put(k, "y", lambda: wf["sorted_"][rows[-1]]), "n"), [10], "rows[-1]: ")


@test("M1", "TEST-L7e", "[0] after a collapse is the first group")
def _():
    expect(data(put(kernel(), "x", lambda: wf["per_ward"][0]), "ward"), ["A"])


@test("M1", "TEST-L7f", "a row number is saved as the row's lineage")
def _():
    k = kernel()
    want = {"a": (lambda: wf["sorted_"][1], ['row["r"] == 2']),
            "b": (lambda: wf["expanded"][2], ['row["r"] == 1', 'row["r"].idx == 0']),
            "c": (lambda: wf["per_ward"][0], ['cols["ward"] == "A"']),
            "d": (lambda: wf["r"][3], ['wf["r"][3]'])}
    wrong = {}
    for name, (make, parts) in want.items():
        try:
            put(k, name, make)
            saved = str(k.step(name).formula)
        except Refused as e:
            saved = f"refused ({str(e)[:40]})"
        if not all(part in saved for part in parts):
            wrong[name] = saved
    if wrong:
        raise Fail(f"saved as {wrong}")


@test("M1", "TEST-L8", "text row ids are refused")
def _():
    expect_refused(kernel(), lambda: wf["per_ward"][rows["A"]])


# ── M2: lineage ──────────────────────────────────────────────────────────

@test("M2", "TEST-L10", "#r of filtered holds r's placements")
def _():
    expect(lin(kernel().view("filtered"), "#r"), [1, 2, 3])


@test("M2", "TEST-L11a", "#r of sorted")
def _():
    expect(lin(kernel().view("sorted_"), "#r"), [3, 2, 1, 0])


@test("M2", "TEST-L11b", "#r of per_ward is a list per group")
def _():
    expect(lin(kernel().view("per_ward"), "#r"), [[0, 2], [1], [3]])


@test("M2", "TEST-L12", "expand: #r and #r.idx, integers")
def _():
    v = kernel().view("expanded")
    expect(lin(v, "#r"), [0, 0, 1, 1, 2, 2, 3, 3], "#r: ")
    expect(lin(v, "#r.idx"), [0, 1] * 4, "#r.idx: ")


@test("M2", "TEST-L12b", "expand of a filter: #filtered, and r's lineage carried")
def _():
    v = put(kernel(), "x", lambda: split_in_two[mod.expand()](wf["filtered"]))
    expect(lin(v, "#filtered"), [0, 0, 1, 1, 2, 2], "#filtered: ")
    expect(lin(v, "#r"), [1, 1, 2, 2, 3, 3], "#r (carried): ")


@test("M2", "TEST-L13", "one-to-one steps add no lineage, and carry their input's")
def _():
    k = kernel()
    expect(lineage_names(k.view("doubled")), set(), "doubled: ")
    col = out_col(k, "expanded")
    expect(lineage_names(put(k, "x", lambda: identity[mod.rename(columns={col: "n"})](wf["expanded"]))),
           {"#r", "#r.idx"}, "rename of expanded: ")


@test("M2", "TEST-L14a", "stack: #filtered holds filtered's placements")
def _():
    expect(lin(put(kernel(), "x", lambda: stack(wf["r"], wf["filtered"])), "#filtered"),
           [None] * 4 + [0, 1, 2])


@test("M2", "TEST-L14b", "a join of a join carries every source")
def _():
    k = kernel()
    put(k, "j2", lambda: join(wf["r"], wf["other"], on="ward"))
    expect(lineage_names(put(k, "x", lambda: join(wf["j2"], wf["third"], on="ward"))),
           {"#j2", "#third", "#r", "#other"})


@test("M2", "TEST-L14c", "stack of three keeps three (keep green)")
def _():
    expect(lineage_names(put(kernel(), "x", lambda: stack(wf["r"], wf["other"], wf["third"]))),
           {"#r", "#other", "#third"})


@test("M2", "TEST-L15", "the same parent twice: #r and #r.2")
def _():
    got = lineage_names(put(kernel(), "x", lambda: join(wf["r"], wf["r"], on="ward")))
    if not {"#r", "#r.2"} <= got:
        raise Fail(f"lineage {sorted(got)}")


@test("M2", "TEST-L16a", "view: lineage is not among the data columns")
def _():
    hashed = [n for n in names(kernel().view("per_ward")) if str(n).startswith("#")]
    expect(hashed, [], "columns starting with '#': ")


@test("M2", "TEST-L16b", "selecting a lineage column is refused")
def _():
    expect_refused(kernel(), lambda: identity[mod.select(columns=["#r"])](wf["expanded"]))


@test("M2", "TEST-L17", "join a child to its parent on #r")
def _():
    v = put(kernel(), "x", lambda: join(wf["expanded"], wf["r"], on="#r"))
    expect(len(v["rows"]), 8, "rows: ")
    if not {"ward", "n"} <= set(data_names(v)):
        raise Fail(f"data columns {data_names(v)}")


@test("M2", "TEST-L18a", "mod.copy copies lineage into data; lineage unchanged")
def _():
    if not hasattr(mod, "copy"):
        raise Fail("core has no mod.copy")
    v = put(kernel(), "x", lambda: identity[mod.copy(columns={"#r": "parent"})](wf["expanded"]))
    expect(data(v, "parent"), [0, 0, 1, 1, 2, 2, 3, 3], "parent: ")
    expect(lin(v, "#r"), [0, 0, 1, 1, 2, 2, 3, 3], "#r: ")


@test("M2", "TEST-L18b", "renaming lineage copies it, saved as mod.copy")
def _():
    k = kernel()
    v = put(k, "x", lambda: identity[mod.rename(columns={"#r": "parent"})](wf["expanded"]))
    expect(data(v, "parent"), [0, 0, 1, 1, 2, 2, 3, 3], "parent: ")
    expect(lin(v, "#r"), [0, 0, 1, 1, 2, 2, 3, 3], "#r: ")
    if "copy" not in str(k.step("x").formula):
        raise Fail(f"saved as {k.step('x').formula}")


@test("M2", "TEST-L19", "collapse(by='#r') undoes an expand (keep green)")
def _():
    k = kernel()
    col = out_col(k, "expanded")
    put(k, "en", lambda: identity[mod.rename(columns={col: "n"})](wf["expanded"]))
    expect(data(put(k, "x", lambda: add_up[mod.collapse(by="#r")](wf["en"]))), [21, 41, 61, 81])


@test("M2", "TEST-L45a", "join a filter to its parent on #r: shared columns merge")
def _():
    v = put(kernel(), "x", lambda: join(wf["filtered"], wf["r"], on="#r"))
    expect(sorted(data_names(v)), ["n", "ward"], "data columns: ")
    expect(data(v, "n"), [20, 30, 40], "n: ")


@test("M2", "TEST-L45b", "left join back onto the parent: every row, absent where filtered out")
def _():
    k = kernel()
    put(k, "fd", lambda: double[mod.map()](wf["filtered"]))
    v = put(k, "x", lambda: join(wf["r"], wf["fd"], on="#r", how="left"))
    col = out_col(k, "fd")
    expect(len(v["rows"]), 4, "rows: ")
    expect(state(v, col)[0], "absent", f"{col} on row 0: ")


# ── M3: column names and output naming ───────────────────────────────────

@test("M3", "TEST-L20", "renaming a data column to '#x' is refused (keep green)")
def _():
    expect_refused(kernel(), lambda: identity[mod.rename(columns={"ward": "#x"})](wf["r"]))


@test("M3", "TEST-L21a", "numeric names become var0, var1")
def _():
    expect(data_names(put(kernel(), "x", lambda: pd.DataFrame({"0": [1, 2], "1": [3, 4]}))),
           ["var0", "var1"])


@test("M3", "TEST-L21b", "0 and var0 together are refused")
def _():
    expect_refused(kernel(), lambda: pd.DataFrame({"0": [1], "var0": [2]}))


@test("M3", "TEST-L22", "a dict result gives one column per key")
def _():
    expect(data_names(put(kernel(), "x", lambda: pair[mod.map()](wf["r"]))), ["a", "b"])


@test("M3", "TEST-L23", "one output column takes the step's name, and follows a rename")
def _():
    k = kernel()
    expect(data_names(k.view("doubled")), ["doubled"], "before rename: ")
    k.rename("doubled", "twice")
    expect(data_names(k.view("twice")), ["twice"], "after rename: ")


@test("M3", "TEST-L24", "a left join keeps pop an int")
def _():
    v = put(kernel(), "x", lambda: join(wf["r"], wf["other"], on="ward", how="left"))
    kind = next(c.get("type") for c in v["columns"] if c["name"] == "pop")
    if not str(kind).startswith("int"):
        raise Fail(f"pop is {kind}")


@test("M3", "TEST-L46", "a name that isn't an identifier is kept and picked by string")
def _():
    k = kernel()
    v = put(k, "p", lambda: pd.DataFrame({"Patient ID": ["a", "b"], "temp f": [98, 99]}))
    expect(data_names(v), ["Patient ID", "temp f"], "names: ")
    expect(data(put(k, "x", lambda: wf["p"]["temp f"])), [98, 99], "pick: ")


@test("M3", "TEST-L47", "a step name with a '.' is refused")
def _():
    k = kernel()
    try:
        k["a.b"] = double[mod.map()](wf["r"])
    except Exception:
        return
    if not k.step("a.b").problems:
        raise Fail("accepted")


# ── M4: selection grammar ────────────────────────────────────────────────

@test("M4", "TEST-L25a", "a plain string selects a column")
def _():
    expect(data(put(kernel(), "x", lambda: wf["r"]["n"])), [10, 20, 30, 40])


@test("M4", "TEST-L25b", "rows then several columns, list/dict style")
def _():
    v = put(kernel(), "x", lambda: wf["r"][0:2]["ward", "n"])
    expect([data(v, "ward"), data(v, "n")], [["A", "B"], [10, 20]])


@test("M4", "TEST-L26", "five spellings of one block agree")
def _():
    k = kernel()
    spellings = {
        '[1:3]["n"]': lambda: wf["r"][1:3]["n"],
        '["n"][1:3]': lambda: wf["r"]["n"][1:3],
        '[1:3, "n"]': lambda: wf["r"][1:3, "n"],
        "[rows, cols]": lambda: wf["r"][rows[1:3], cols["n"]],
        "select(rows=, cols=)": lambda: identity[mod.select(rows=slice(1, 3), cols=["n"])](wf["r"]),
    }
    wrong = {}
    for i, (label, make) in enumerate(spellings.items()):
        try:
            got = data(put(k, f"x{i}", make))
        except (Refused, Fail) as e:
            got = f"refused ({str(e)[:50]})"
        if got != [20, 30]:
            wrong[label] = got
    if wrong:
        raise Fail(f"{len(wrong)}/5 differ: {wrong}")


@test("M4", "TEST-L27", "columns by position, data columns only")
def _():
    expect(data_names(put(kernel(), "x", lambda: wf["r"][cols[1]])), ["n"])


@test("M4", "TEST-L28", "a list mixing integers and strings is refused")
def _():
    expect_refused(kernel(), lambda: wf["r"][[0, "n"]])


@test("M4", "TEST-L29a", "a condition on data")
def _():
    expect(data(put(kernel(), "x", lambda: wf["r"][cols["n"] > 15]), "n"), [20, 30, 40])


@test("M4", "TEST-L29b", "a combined condition")
def _():
    expect(data(put(kernel(), "x", lambda: wf["r"][(cols["n"] > 15) & (cols["ward"] == "A")]), "n"), [30])


@test("M4", "TEST-L29c", "a condition with a function call is refused, never run")
def _():
    raise Skip("formula-level: Python evaluates the call before core sees it; needs core's formula parser")


@test("M4", "TEST-L30a", "row['r'] picks the items of r row 3")
def _():
    if row is None:
        raise Fail("core has no `row`")
    expect(data(put(kernel(), "x", lambda: wf["expanded"][row["r"] == 3])), [40, 41])


@test("M4", "TEST-L30b", "row['r'] after a collapse matches the group holding it")
def _():
    if row is None:
        raise Fail("core has no `row`")
    expect(data(put(kernel(), "x", lambda: wf["per_ward"][row["r"] == 0]), "ward"), ["A"])


@test("M4", "TEST-L31", "a condition matching nothing: zero rows and a warning")
def _():
    k = kernel()
    v = put(k, "x", lambda: wf["r"][cols["n"] > 100])
    st = k.step("x")
    expect((st.state, len(v["rows"])), ("completed", 0), "state, rows: ")
    if not any("100" in str(w) for w in st.warnings):
        raise Fail(f"warnings {[str(w) for w in st.warnings]}")


@test("M4", "TEST-L31b", "a row number out of range fails")
def _():
    k = kernel()
    try:
        put(k, "x", lambda: wf["r"][9])
    except Refused:
        return
    if k.step("x").state != "failed":
        raise Fail(f"state {k.step('x').state}")


@test("M4", "TEST-L33", "a picker before map in one step")
def _():
    v = put(kernel(), "x", lambda: double[mod.select(rows=cols["n"] > 15), mod.map()](wf["r"]))
    expect(data(v), [40, 60, 80], "values: ")
    expect(lin(v, "#r"), [1, 2, 3], "#r: ")


@test("M4", "TEST-L34", "a pick as a tool's input")
def _():
    v = put(kernel(), "x", lambda: double[mod.map()](wf["r"][0:2]))
    expect(data(v), [20, 40], "values: ")
    expect(lin(v, "#r"), [0, 1], "#r: ")


@test("M4", "TEST-L35", "a tool named `row` is refused")
def _():
    def named(n: int) -> int:
        return n
    try:
        Catalog([tool(named, id="row")])
    except Exception as e:
        if "row" in str(e) and "reserved" in str(e).lower():
            return
        raise Fail(f"refused for another reason: {e}") from None
    raise Fail("registered")


@test("M4", "TEST-L36", "row['r'].idx picks the second item of every split")
def _():
    if row is None:
        raise Fail("core has no `row`")
    expect(data(put(kernel(), "x", lambda: wf["expanded"][row["r"].idx == 1])), [11, 21, 31, 41])


@test("M4", "TEST-L48a", "a list cell: != is 'doesn't contain'")
def _():
    if row is None:
        raise Fail("core has no `row`")
    expect(data(put(kernel(), "x", lambda: wf["per_ward"][row["r"] != 0]), "ward"), ["B", "C"])


@test("M4", "TEST-L48b", "a list cell: < is refused")
def _():
    if row is None:
        raise Fail("core has no `row`")
    expect_refused(kernel(), lambda: wf["per_ward"][row["r"] < 1])


@test("M4", "TEST-L49", "[0, 2] is refused, pointing to [[0, 2]]")
def _():
    expect_refused(kernel(), lambda: wf["r"][0, 2], mention="[[0, 2]]")


# ── M5: arguments and pairing ────────────────────────────────────────────

@test("M5", "TEST-L37", "column argument from an aligned step pairs by row")
def _():
    expect(data(put(kernel(), "x", lambda: add_k[mod.map()](wf["r"], k=wf["doubled"]))), [30, 60, 90, 120])


@test("M5", "TEST-L37b", "one cell by placement as a constant")
def _():
    expect(data(put(kernel(), "x", lambda: add_k[mod.map()](wf["r"], k=wf["sorted_"][0][cols["n"]]))),
           [50, 60, 70, 80])


@test("M5", "TEST-L38", "a whole step to a DataFrame parameter")
def _():
    expect(data(put(kernel(), "x", lambda: rows_of[mod.map()](wf["r"], t=wf["other"]))), [3, 3, 3, 3])


@test("M5", "TEST-L39", "right and outer joins")
def _():
    k = kernel()
    got = {how: len(put(k, f"j_{how}", lambda how=how: join(wf["r"], wf["other"], on="ward", how=how))["rows"])
           for how in ("right", "outer")}
    expect(got, {"right": 4, "outer": 5})


@test("M5", "TEST-L50a", "binding by the one column whose type fits, saved explicitly")
def _():
    k = kernel()
    expect(data(put(k, "x", lambda: double[mod.map()](wf["doubled"]))), [40, 80, 120, 160], "values: ")
    if "n=" not in str(k.step("x").formula):
        raise Fail(f"saved as {k.step('x').formula}")


@test("M5", "TEST-L50b", "two columns of the type: invalid at staging, naming both")
def _():
    k = kernel()
    k["two"] = pd.DataFrame({"a": [1], "b": [2]})
    k["x"] = double[mod.map()](wf["two"])
    st = k.step("x")
    said = " ".join(map(str, st.problems))
    if st.state != "invalid" or "int" not in said or not re.search(r"\ba\b.*\bb\b", said):
        raise Fail(f"state {st.state!r}, problems {said!r}")


@test("M5", "TEST-L50c", "a parameter with a default isn't bound by name")
def _():
    k = kernel()
    k["xf"] = pd.DataFrame({"x": [1, 2], "factor": [10, 10]})
    expect(data(put(k, "x", lambda: scale[mod.map()](wf["xf"]))), [2, 4])


@test("M5", "TEST-L51a", "a type that doesn't fit: invalid, suggesting mod.cast")
def _():
    k = kernel()
    k["x"] = shout[mod.map()](wf["doubled"])
    st = k.step("x")
    if st.state != "invalid" or not any("cast" in str(p) for p in st.problems):
        raise Fail(f"state {st.state!r}, problems {[str(p) for p in st.problems]}")


@test("M5", "TEST-L51b", "mod.cast converts before binding")
def _():
    if not hasattr(mod, "cast"):
        raise Fail("core has no mod.cast")
    k = kernel()
    col = out_col(k, "doubled")
    expect(data(put(k, "x", lambda: shout[mod.cast(**{col: "str"}), mod.map()](wf["doubled"]))),
           ["20", "40", "60", "80"])


@test("M5", "TEST-L51c", "int to float is automatic (lossless)")
def _():
    k = kernel()
    expect(data(put(k, "x", lambda: half[mod.map()](wf["doubled"]))), [10.0, 20.0, 30.0, 40.0])


# ── M6: editing in a live session ────────────────────────────────────────

@test("M6", "TEST-L40", "a reader whose column disappeared is invalid at once")
def _():
    k = kernel()
    k["r"] = pd.DataFrame({"m": [5]})
    st = k.step("doubled")
    if st.state != "invalid" and not any("n" in str(p) for p in st.problems):
        raise Fail(f"state {st.state!r}, problems {list(st.problems)}")


@test("M6", "TEST-L41a", "a pick follows its row after an upstream change")
def _():
    k = kernel()
    put(k, "first", lambda: wf["filtered"][0])            # r's row 1, n 20
    k["r"] = pd.DataFrame({"ward": ["A", "B", "A", "C"], "n": [10, 25, 30, 40]})
    k.run("filtered")
    k.run("first")
    expect(data(k.view("first"), "n"), [25])


@test("M6", "TEST-L41b", "a pick whose row is gone fails, saying so")
def _():
    k = kernel()
    put(k, "first", lambda: wf["filtered"][0])            # r's row 1
    k["r"] = pd.DataFrame({"ward": ["A", "B", "A", "C"], "n": [50, 10, 20, 30]})
    k.run("filtered")
    try:
        k.run("first")
    except Exception as e:
        said = str(e)
    else:
        st = k.step("first")
        said = " ".join([*map(str, st.problems)] + [str(n) for n in st.output.notes.values()])
        if st.state not in ("failed", "invalid"):
            raise Fail(f"state {st.state!r}, {short(k.view('first'))}")
    if "1" not in said:
        raise Fail(f"didn't name r's row 1: {said[:120]}")


@test("M6", "TEST-L42", "a stale step says which step made it stale")
def _():
    k = kernel()
    k["r"] = pd.DataFrame({"ward": ["A"], "n": [1]})
    st = k.step("doubled")
    reasons = [str(x) for x in (*st.problems, *st.warnings)]
    if st.state != "stale" or not any(re.search(r"\br\b", x) for x in reasons):
        raise Fail(f"state {st.state!r}, reasons {reasons}")


@test("M6", "TEST-L43a", "a rename keeps outputs and rewrites references")
def _():
    k = kernel()
    k.rename("r", "readings")
    expect(k.step("doubled").state, "completed", "doubled: ")
    if "readings" not in str(k.step("filtered").formula):
        raise Fail(f"filtered's formula: {k.step('filtered').formula}")


@test("M6", "TEST-L43b", "deleting a step that's read is refused, naming the reader (keep green)")
def _():
    k = kernel()
    put(k, "after", lambda: double[mod.map()](wf["filtered"]))
    try:
        del k["filtered"]
    except Exception as e:
        if "after" in str(e):
            return
        raise Fail(f"refused without naming the reader: {e}") from None
    raise Fail("deleted")


@test("M6", "TEST-L43d", "delete anyway: each reader invalid, naming the deleted step")
def _():
    k = kernel()
    put(k, "after", lambda: double[mod.map()](wf["filtered"]))
    if not hasattr(k, "remove"):
        raise Fail("core has no k.remove(name, force=True)")
    k.remove("filtered", force=True)
    st = k.step("after")
    if st.state != "invalid" or not any("filtered" in str(p) for p in st.problems):
        raise Fail(f"after: state {st.state!r}, problems {[str(p) for p in st.problems]}")


@test("M6", "TEST-L43c", "moving a step before what it reads is refused")
def _():
    k = kernel()
    try:
        k.move("doubled", 0)
    except Exception:
        return
    if not k.step("doubled").problems:
        raise Fail("moved, no problem reported")


@test("M6", "TEST-L52", "renaming a step renames its lineage downstream")
def _():
    k = kernel()
    k.rename("r", "readings")
    expect(lineage_names(k.view("filtered")), {"#readings"})


# ── Run ──────────────────────────────────────────────────────────────────

def main(selected: list) -> None:
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    current = None
    for milestone, tid, title, fn in TESTS:
        if selected and milestone not in selected:
            continue
        if milestone != current:
            current = milestone
            print(f"\n{milestone}")
        try:
            fn()
            verdict, detail = "PASS", ""
        except Skip as e:
            verdict, detail = "SKIP", str(e)
        except Fail as e:
            verdict, detail = "FAIL", str(e)
        except Refused as e:
            verdict, detail = "FAIL", f"refused: {e}"
        except Exception as e:
            verdict, detail = "FAIL", f"{type(e).__name__}: {e}"
        counts[verdict] += 1
        line = f"  {verdict}  {tid:16} {title}"
        print(line if not detail else f"{line}\n{'':24}{detail[:160]}")
    print(f"\n{counts['PASS']} pass, {counts['FAIL']} fail, {counts['SKIP']} skip. "
          "Plan: plan.md, beside this script")


if __name__ == "__main__":
    main([a.upper() for a in sys.argv[1:]])
