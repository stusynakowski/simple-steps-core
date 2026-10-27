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
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from simple_steps_core import Catalog, Kernel, cols, join, mod, stack, tool, wf, zip_
from simple_steps_core.errors import SelectionError, StepFailed
from simple_steps_core.operation import op
from simple_steps_core.output import is_id_column, variables

EXAMPLES = 2000 if os.environ.get("STRESS") else 100
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
        for row in list(step.output.data.index)[:3]:
            for column in variables(step.output.data.columns)[:2]:
                for entry in k.cell(s, row, column).get("inputs", []):
                    if entry.get("id") is not None and entry.get("step") in wf_.steps:
                        assert entry["id"] in wf_.steps[entry["step"]].output.data.index, \
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
def test_L40c_an_edit_then_a_rerun_matches_a_fresh_run(frame, changed, chain):
    k, names = _build(_catalog(frame), chain)
    _run(k)
    new_catalog = _catalog(changed)
    k2, _ = _build(new_catalog, chain)           # a fresh kernel on the new source…
    _run(k2)
    # …and the old one, its source edited in place, run again
    k["s0"] = changed
    _run(k)
    for s in names[1:]:
        x, y = k.workflow.steps[s], k2.workflow.steps[s]
        if x.state == "completed" and y.state == "completed":
            pd.testing.assert_frame_equal(x.output.data, y.output.data, check_dtype=False,
                                          check_index_type=False, obj=f"edited: {s} {x.formula}")
