"""The property tests (L40, docs/design/reshaping.md §10): reshaping is closed.

Generated grids that meet V1-V9, and generated chains of every verb,
modifier and combine over them. On every example:

1. core never crashes: declaring may refuse a step (a problem on it), running
   may fail a row (StepFailed), and nothing else is raised;
2. every step that ran keeps the airtight checks A1, A3-A6, against the plan
   it had before it ran;
3. every cell's lineage names rows that exist;
4. every ``rebuild`` formula, run on its step's output, gives back the input;
5. (L40b) a saved workflow, loaded and run, gives the same data;
6. (L40c) changing the source and running again gives what a fresh kernel
   gives from the new source: staleness never leaves an old value behind.

When one breaks, hypothesis shrinks it to the smallest grid and chain that
still does. ``STRESS=1`` runs many more examples.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from simple_steps_core import Catalog, Kernel, cols, join, mod, row, stack, tool, wf, zip_
from simple_steps_core.errors import SelectionError, StepFailed
from simple_steps_core.operation import op
from simple_steps_core.output import is_id_column, variables
from simple_steps_core.step import NO_LITERAL

# STRESS=1 runs 500 examples (owner, 2026-11-04: 2,000 took too long for now);
# STRESS=<n> runs n, so STRESS=2000 is the full run
_STRESS = os.environ.get("STRESS")
EXAMPLES = (int(_STRESS) if _STRESS and _STRESS.isdigit() and int(_STRESS) > 1
            else 500 if _STRESS else 100)
SETTINGS = settings(max_examples=EXAMPLES, deadline=None,
                    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])


# ── tools the chains use: total over None and absent, some raise ─────────────

@tool
def positive_pp(n: int | None = None) -> bool:
    return n is not None and n > 0


@tool
def doubled_pp(n: int | None = None) -> int | None:
    return None if n is None else n * 2


@tool
def size_pp(tags: list | None = None) -> int:
    return len(tags or [])


@tool
def risky_pp(n: int | None = None) -> int:
    if n == 3:
        raise ValueError("three is unlucky")
    return 0 if n is None else n


@tool
def key_pp(k: str) -> str:
    return k.lower()


@tool
def mean_pp(n: list) -> float | None:
    present = [v for v in n if v is not None]
    return sum(present) / len(present) if present else None


@tool
def fold_pp(acc, n: int | None = None) -> int:
    return (acc or 0) + (n or 0)


@tool
def top_pp(df: pd.DataFrame) -> pd.DataFrame:
    return df.head(2)


@tool
def grid_pp(a: int, b: str) -> str:
    return f"{a}{b}"


@tool
def explode_pp(n: int | None = None) -> list | dict | None:
    if n is None:
        return None
    return {"x": n} if n % 4 == 0 else [n] * (abs(n) % 3)


@tool
def scale_pp(n: int | None = None, w: int | None = None) -> int | None:
    return None if n is None or w is None else n * w


@tool
def named_pp() -> pd.DataFrame:
    return pd.DataFrame({"k": ["A", "B"], "n": [1, 2]}, index=["p", "p.1"])


TOOLS = [positive_pp, doubled_pp, size_pp, risky_pp, key_pp, mean_pp, fold_pp, top_pp,
         grid_pp, explode_pp, scale_pp, named_pp]


# ── grids that meet V1-V9 ────────────────────────────────────────────────────

child_like = ["a", "a.1", "0.1", "1", "b.0.2", "x", "0", "a.1.0"]


@st.composite
def grids(draw):
    n = draw(st.integers(min_value=0, max_value=5))
    keys = draw(st.lists(st.sampled_from(["A", "B", "C"]), min_size=n, max_size=n))
    nums = draw(st.lists(st.one_of(st.none(), st.integers(-3, 9)), min_size=n, max_size=n))
    tags = draw(st.lists(st.one_of(st.none(), st.lists(st.integers(0, 5), max_size=3)),
                         min_size=n, max_size=n))                       # V1, V7
    recs = draw(st.lists(st.dictionaries(st.sampled_from(["a", "b"]),
                                         st.one_of(st.none(), st.integers(0, 9)), max_size=2),
                         min_size=n, max_size=n))                       # V3
    frame = pd.DataFrame({"k": keys, "n": pd.array(nums, dtype="Int64"),
                          "tags": pd.Series(tags, dtype=object),
                          "rec": pd.Series(recs, dtype=object)})
    if draw(st.booleans()) and n:
        frame.index = draw(st.lists(st.sampled_from(child_like), min_size=n, max_size=n,
                                    unique=True))                       # V4
    return frame


# ── every move ───────────────────────────────────────────────────────────────

def _moves(k: Kernel, name: str, src: str, other: str, ancestor: str):
    """(name, a function declaring it): *src* is its input, *other* another
    step (for an argument or a second input), *ancestor* an earlier step. A
    move that needs a helper step (a selection, a renamed partner) declares
    it first, as its own step: an operation can't be another's input."""
    g = op("gather")

    def part(columns, rename=None):
        """A helper step: *src*'s (or *other*'s) columns, renamed if asked."""
        step = f"{name}_p"
        base = other if rename else src
        k[step] = wf[base][cols[columns]]
        if rename:
            k[f"{name}_r"] = mod.rename(columns=rename)(wf[step])
            step = f"{name}_r"
        return wf[step]

    def own_id_column():
        found = [c for c in k.workflow._predicted_of(src) if is_id_column(c) and c != "#"]
        return found[0] if found else f"#{ancestor}"

    return [
        ("sort", lambda: mod.sort(by="k")(wf[src])),
        ("filter", lambda: positive_pp[mod.filter()](wf[src])),
        ("select", lambda: mod.select(columns=["k", "n"])(wf[src])),
        ("drop", lambda: mod.drop(columns=["rec"])(wf[src])),
        ("rename", lambda: mod.rename(columns={"n": "m"})(wf[src])),
        ("map", lambda: doubled_pp[mod.map()](wf[src])),
        ("auto", lambda: doubled_pp(wf[src])),
        ("name", lambda: doubled_pp[mod.map(), mod.name("d")](wf[src])),
        ("group", lambda: key_pp[mod.group(), mod.name("g")](wf[src])),
        ("distinct", lambda: mod.distinct(columns=["k"])(wf[src])),
        ("slice", lambda: mod.slice(stop=2)(wf[src])),
        ("where_value", lambda: wf[src][cols["k"] == "A"]),                     # S5c
        ("pick_row", lambda: wf[src][0]),                                       # S5d
        ("pick_rows", lambda: wf[src][[0, -1]]),
        ("where_own", lambda: wf[src][row[src].isin([0, 2])]),
        ("where_lineage", lambda: wf[src][(row[ancestor] == 0) | ~(cols["k"] == "A")]),
        ("expand", lambda: mod.expand(columns=["tags"])(wf[src])),
        ("expand_one", lambda: op("identity")[mod.expand()](part(["tags"]))),
        ("expand_tool", lambda: explode_pp[mod.expand()](wf[src])),
        ("expand_rec", lambda: op("identity")[mod.expand()](part(["rec"]))),
        ("as_list", lambda: op("as_list")[mod.map()](part(["n"]))),
        ("gather_by", lambda: g[mod.collapse(by="k")](wf[src])),
        ("gather", lambda: g[mod.collapse()](wf[src])),
        ("count_by", lambda: op("count")[mod.collapse(by="k")](wf[src])),
        ("total_by", lambda: op("total")[mod.collapse(by="k")](part(["k", "n"]))),
        ("mean_by", lambda: mean_pp[mod.collapse(by="k")](wf[src])),
        ("fold_by", lambda: fold_pp[mod.collapse(by="k")](wf[src])),
        ("by_ancestor", lambda: op("count")[mod.collapse(by=f"#{ancestor}")](wf[src])),
        ("gather_dict", lambda: op("gather_dict")[mod.collapse(by=own_id_column())](wf[src])),
        ("widen", lambda: mod.widen()(part(["rec"]))),
        ("widen_cols", lambda: mod.widen(columns=["a", "b"])(part(["rec"]))),
        ("pack", lambda: mod.pack(columns=["k", "n"])(wf[src])),
        ("size", lambda: size_pp[mod.map()](wf[src])),
        ("risky", lambda: risky_pp[mod.map()](wf[src])),
        ("caught", lambda: risky_pp[mod.map(), mod.try_except(default=-1)](wf[src])),
        ("retried", lambda: risky_pp[mod.map(), mod.retry(times=1), mod.try_except()](wf[src])),
        ("table", lambda: top_pp[mod.table()](wf[src])),
        ("drop_trace", lambda: mod.drop(columns=[own_id_column()])(wf[src])),
        ("argument", lambda: scale_pp[mod.map()](wf[src], w=wf[other][cols["n"]])),
        ("zip", lambda: zip_(wf[src], part(["n"], rename={"n": "n2"}))),
        ("zip_vouched", lambda: zip_(wf[src], part(["n"], rename={"n": "n3"}), match_ids=True)),
        ("stack", lambda: stack(wf[src], wf[other])),
        ("join", lambda: join(wf[src], wf[other], on="k")),
        ("join_left", lambda: join(wf[src], wf[other], on="k", how="left")),
        ("join_lineage", lambda: join(wf[src], wf[ancestor], on=f"#{ancestor}")),    # S5e
        ("join_back", lambda: join(wf[ancestor], wf[src], on=f"#{ancestor}", how="left")),
        ("sweep", lambda: grid_pp[mod.sweep(a=[1, 2], b=["x", "y"])]()),
        ("source", lambda: named_pp[mod.source()]()),
        ("empty", lambda: None),
    ]


MOVES = len(_moves(None, "s", "s0", "s0", "s0"))


@st.composite
def chains(draw):
    length = draw(st.integers(min_value=1, max_value=7))
    return [tuple(draw(st.integers(0, 999)) for _ in range(4)) for _ in range(length)]


# ── building, running, comparing ─────────────────────────────────────────────

def _catalog(frame: pd.DataFrame) -> Catalog:
    data = frame.copy()

    @tool
    def origin_pp() -> pd.DataFrame:
        return data.copy()

    return Catalog(tools=[origin_pp, *TOOLS])


def _build(catalog: Catalog, chain: list) -> tuple[Kernel, list[str]]:
    k = Kernel(catalog)
    k["s0"] = catalog.tools["origin_pp"][mod.source()]()
    names = ["s0"]
    for n, (pick, a, b, c) in enumerate(chain, start=1):
        src, other, ancestor = (names[x % len(names)] for x in (a, b, c))
        label, make = _moves(k, f"s{n}", src, other, ancestor)[pick % MOVES]
        before = set(k.workflow.steps)
        try:
            k[f"s{n}"] = make()
        except (SelectionError, ValueError, TypeError):
            pass                                 # refused when declared: allowed
        # the move's helper steps, then the move itself
        names += [s for s in k.workflow.steps if s not in before]
    return k, names


def _run(k: Kernel) -> None:
    for _ in range(3):                           # a failed row stops a run; go on past it
        try:
            k.run_all()
            return
        except StepFailed:
            pass


def _same(a: Kernel, b: Kernel, names: list[str], why: str) -> None:
    for s in names:
        x, y = a.workflow.steps[s], b.workflow.steps[s]
        assert x.state == y.state, (why, s, x.formula, x.state, y.state)
        if x.state != "completed":
            continue
        pd.testing.assert_frame_equal(x.output.data, y.output.data, check_dtype=False,
                                      check_index_type=False, obj=f"{why}: {s} {x.formula}")
        assert x.output.states.astype(str).equals(y.output.states.astype(str)), (why, s)


@pytest.mark.no_invariants                       # checked here, so hypothesis can shrink
@SETTINGS
@given(grids(), chains())
# a sort of a zip_ whose `#` columns sit between its data columns: the plan
# put them in front, the run kept them in place (found at STRESS=1)
@example(frame=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         chain=[(93, 0, 0, 0), (121, 0, 0, 0), (824, 38, 1, 0), (921, 0, 0, 0),
                (0, 0, 0, 0), (0, 65, 0, 0)])
# a self-join on lineage of a step whose columns already had join suffixes:
# merging shared columns made two columns with one name (found at STRESS=1)
@example(frame=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         chain=[(42, 0, 0, 0), (139, 1, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0),
                (44, 2, 0, 2)])
def test_L40_reshaping_is_closed(frame, chain):
    k, names = _build(_catalog(frame), chain)
    plans = {s: k.workflow.steps[s].output.meta.get("plan") for s in names
             if k.workflow.steps[s].output.meta.get("staged")}
    _run(k)                                      # 1. no crash: failed rows are allowed
    wf_ = k.workflow
    for s in names:
        step = wf_.steps[s]
        # 2. the airtight checks
        assert wf_.check_invariants(s, plans.get(s)) == [], (s, step.formula)
        if step.state != "completed":
            continue
        # 3. lineage names rows that exist
        for row in range(min(3, len(step.output.data))):
            for column in variables(step.output.data.columns)[:2]:
                for entry in k.cell(s, row, column).get("inputs", []):
                    if entry.get("row") is not None and entry.get("step") in wf_.steps:
                        assert 0 <= entry["row"] < len(wf_.steps[entry["step"]].output.data), \
                            (s, row, column, entry)
        # 4. a rebuild gives the input back
        inverse = step.plan.get("inverse") or {}
        if inverse.get("kind") != "rebuild" or not inverse.get("formula"):
            continue
        formulas = inverse["formula"] if isinstance(inverse["formula"], list) else [inverse["formula"]]
        inputs = [str(g) for g in step.operation.inputs] if step.operation.inputs else []
        for n, (formula, original) in enumerate(zip(formulas, inputs)):
            back_name = f"back_{s}_{n}"
            k[back_name] = eval(formula, {"mod": mod, "wf": wf, "op": op})
            try:
                k.run(back_name)
            except StepFailed:
                pass
            back, want = wf_.steps[back_name], wf_.steps[original]
            if back.state != "completed" or want.state != "completed":
                continue
            names_ = [c for c in want.output.data.columns if not is_id_column(c)]
            assert sorted(map(repr, back.output.data.index)) == \
                sorted(map(repr, want.output.data.index)), (s, formula)
            got = back.output.data.loc[list(want.output.data.index), names_]
            pd.testing.assert_frame_equal(got, want.output.data[names_], check_dtype=False,
                                          check_index_type=False,   # ids compared above, by value
                                          obj=f"{s}: {formula}")


@pytest.mark.no_invariants
@SETTINGS
@given(grids(), chains())
def test_L40b_a_saved_workflow_runs_the_same(frame, chain):
    catalog = _catalog(frame)
    k, names = _build(catalog, chain)
    _run(k)
    back = Kernel.from_json(k.to_json(), catalog)
    _run(back)
    _same(k, back, names, "saved and loaded")


@pytest.mark.no_invariants
@SETTINGS
@given(grids(), grids(), chains())
# a pick that had no rows yet, and a collapse grouped by it: after the edit the
# pick stayed invalid and the collapse ran anyway (found at STRESS=1)
@example(frame=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         changed=pd.DataFrame({"k": ["A", "A"], "n": [pd.NA, pd.NA], "tags": [None, None],
                               "rec": [{}, {}]}),
         chain=[(993, 0, 0, 0), (811, 0, 0, 1)])
def test_L40c_an_edit_then_a_rerun_matches_a_fresh_run(frame, changed, chain):
    k, names = _build(_catalog(frame), chain)
    _run(k)
    # A fresh kernel of the same saved workflow on the new source… (saved, not
    # rebuilt: a typed row number is saved as its row's lineage, S5d)
    k2 = Kernel.from_json(k.to_json(), _catalog(changed))
    _run(k2)
    # …and the old one, its source edited in place, run again
    k["s0"] = changed
    _run(k)
    for s in names[1:]:
        x, y = k.workflow.steps[s], k2.workflow.steps[s]
        if x.state == "completed" and y.state == "completed":
            pd.testing.assert_frame_equal(x.output.data, y.output.data, check_dtype=False,
                                          check_index_type=False, obj=f"edited: {s} {x.formula}")


# ── ST8: the session's laws, read off the result store (decisions.md SM) ─────

#: The states in which a step holds a result, one the store keeps.
HOLDING = ("completed", "failed", "stale")


def _snapshot(k: Kernel, names: list[str]) -> dict:
    return {s: (k.workflow.steps[s].state, k.workflow.steps[s].output) for s in names}


def _is_value(k: Kernel, name: str) -> bool:
    """A step declared as a value: its expression is "a source", its data the
    value, so copying its expression to another step means nothing."""
    return k.workflow.steps[name].literal is not NO_LITERAL


def _redeclare(k: Kernel, name: str, expression) -> bool:
    try:
        k[name] = expression
        return True
    except (SelectionError, ValueError, TypeError):
        return False


@pytest.mark.no_invariants
@SETTINGS
@given(grids(), grids(), chains(), st.integers(0, 999), st.integers(0, 999))
# a pick turned invalid at run left a collapse grouped by its rows completed:
# re-checks after a run followed only direct inputs (found by ST8)
@example(frame=pd.DataFrame(columns=["k", "n", "tags", "rec"]), changed=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         chain=[(0, 0, 0, 0), (600, 1, 0, 0), (997, 0, 0, 0), (860, 0, 0, 552)], which=0, other=0)
# after an undo, a pick was re-checked against its input's blank plan, before
# the input's stored result came back (found by ST8)
@example(frame=pd.DataFrame(columns=["k", "n", "tags", "rec"]), changed=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         chain=[(0, 0, 0, 0), (600, 1, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)], which=0, other=1)
# a reader's type check waited on planned types the re-check after a run
# didn't compare (found by ST8 at STRESS=1)
@example(frame=pd.DataFrame({"k": ["A", "A"], "n": [pd.NA, pd.NA], "tags": [None, None], "rec": [{}, {}]}), changed=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         chain=[(413, 0, 0, 0), (367, 1, 0, 0), (1, 3, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (73, 0, 0, 0)],
         which=0, other=0)
# a collapse(by="#s1") was filed under a key that stamped s1, and looked up
# under one that didn't: its expression put back stayed stale (found by ST8)
@example(frame=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         changed=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         chain=[(0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (419, 0, 0, 1), (0, 0, 0, 0)],
         which=600, other=0)
def test_L40d_undo_is_free(frame, changed, chain, which, other):
    """An edit put back leaves every step as it was, holding the very same
    result: nothing re-runs."""
    catalog = _catalog(frame)
    k, names = _build(catalog, chain)
    _run(k)
    before = _snapshot(k, names)
    k["s0"] = changed                                    # the source, edited…
    k["s0"] = catalog.tools["origin_pp"][mod.source()]()   # …and put back
    after = _snapshot(k, names)
    for s in names:
        assert after[s][0] == before[s][0], ("source put back", s, before[s][0], after[s][0])
        if before[s][0] in HOLDING:                        # a plan, or a refusal, isn't a result
            assert after[s][1] is before[s][1], ("source put back, re-ran", s)
    # a step's expression, edited to another step's, and put back
    step, by = names[which % len(names)], names[other % len(names)]
    original = k.workflow.steps[step].operation
    if step == by or _is_value(k, by) or _is_value(k, step) \
            or not _redeclare(k, step, k.workflow.steps[by].operation):
        return
    if not _redeclare(k, step, original):
        return
    after = _snapshot(k, names)
    for s in names:
        assert after[s][0] == before[s][0], ("expression put back", step, s, before[s][0], after[s][0])
        if before[s][0] in HOLDING:
            assert after[s][1] is before[s][1], ("expression put back, re-ran", step, s)


@pytest.mark.no_invariants
@SETTINGS
@given(grids(), grids(), chains(), st.integers(0, 999), st.integers(0, 999))
# a step given a new expression showed its last result, stale, in one order,
# and a blank plan in the other (found by ST8 at STRESS=1)
@example(frame=pd.DataFrame(columns=["k", "n", "tags", "rec"]), changed=pd.DataFrame({"k": ["A"], "n": [pd.NA], "tags": [None], "rec": [{}]}),
         chain=[(0, 0, 0, 0), (257, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)], which=1, other=142)
# a step given an expression naming a later step, and that step, re-checked
# each other forever after a run: it hung (found by ST8 at STRESS=1)
@example(frame=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         changed=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         chain=[(0, 0, 0, 0), (0, 0, 0, 0), (186, 1, 0, 0), (0, 0, 0, 0)], which=94, other=495)
# a value assigned left a reader's old plan (columns unknown), so a bare
# expand on it was refused in one order and not the other (found by ST8)
@example(frame=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         changed=pd.DataFrame({"k": ["A", "A"], "n": [pd.NA, pd.NA], "tags": [None, []],
                               "rec": [{}, {}]}),
         chain=[(2, 0, 0, 0), (556, 1, 0, 0), (212, 0, 0, 0), (0, 0, 0, 0)], which=452, other=166)
# a step showing its last result (a new expression not run) had its readers
# checked against it in one order, against a blank plan in the other (ST8)
@example(frame=pd.DataFrame(columns=["k", "n", "tags", "rec"]),
         changed=pd.DataFrame({"k": ["A"], "n": [pd.NA], "tags": [None], "rec": [{}]}),
         chain=[(5, 0, 0, 0), (0, 0, 0, 0), (0, 1, 0, 0), (208, 0, 0, 0)], which=1, other=254)
def test_L40e_the_order_of_edits_doesnt_matter(frame, changed, chain, which, other):
    """Two edits, made in either order, give the same states and data."""
    catalog = _catalog(frame)
    a, names = _build(catalog, chain)
    b, _ = _build(catalog, chain)
    _run(a), _run(b)
    step, by = names[which % len(names)], names[other % len(names)]
    if step == "s0" or step == by or _is_value(a, by) or _is_value(a, step):
        return
    expression = a.workflow.steps[by].operation
    a["s0"] = changed
    ok_a = _redeclare(a, step, expression)
    ok_b = _redeclare(b, step, expression)
    b["s0"] = changed
    if not (ok_a and ok_b):
        return
    for s in names:
        x, y = a.workflow.steps[s], b.workflow.steps[s]
        assert x.state == y.state, ("order", step, s, x.state, y.state)
        if x.state in ("completed", "stale", "failed"):
            assert a.workflow.version(s) == b.workflow.version(s), ("order", step, s)
    _run(a), _run(b)
    _same(a, b, names, f"edits in either order, then a run ({step})")


@pytest.mark.no_invariants
@SETTINGS
@given(grids(), grids(), chains(), st.integers(0, 999))
def test_L40f_run_makes_a_step_current(frame, changed, chain, which):
    """After the source changes, run(x) leaves x and all it reads current,
    and x is what a fresh kernel on the new source computes."""
    k, names = _build(_catalog(frame), chain)
    _run(k)
    saved = k.to_json()            # saved before the edit: a DataFrame isn't saved (L40c)
    k["s0"] = changed
    x = names[which % len(names)]
    if k.workflow.steps[x].output.meta.get("empty") or k.workflow.steps[x].problems:
        return                                           # an empty step, or one that can't run
    try:
        k.run(x)
    except (StepFailed, ValueError):
        return                                           # a failed row, or x can't run
    for s in [*k.workflow.not_current(x), x]:
        assert k.workflow.steps[s].state not in ("stale", "staged"), (x, s, k.workflow.steps[s].state)
    fresh = Kernel.from_json(saved, _catalog(changed))
    _run(fresh)
    mine, theirs = k.workflow.steps[x], fresh.workflow.steps[x]
    if mine.state == "completed" and theirs.state == "completed":
        pd.testing.assert_frame_equal(mine.output.data, theirs.output.data, check_dtype=False,
                                      check_index_type=False, obj=f"run({x}) {mine.formula}")
