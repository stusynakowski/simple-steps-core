"""
core_asks.py — check every open ask in docs/core-proposals/008-core-changes.md
against this checkout of simple-steps-core.

    python scripts/core_asks.py

Each ask prints OPEN (core still behaves as the proposal describes) or DONE
(the probe now gets the asked-for behaviour), with what it observed. Rerun it
after changing core: an ask is finished when its line says DONE.

Copied from the app's scripts/core_asks.py (2026-10-15). The only change is
where the commit is read from: this repo, not the app's external/ checkout.
Probes added in core for the C/N/O items are marked "(core)".
"""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Annotated, Callable, TypedDict

import pandas as pd
from simple_steps_core import grid
from simple_steps_core.grid import mod, op, tool

warnings.simplefilter("ignore")

I = op("identity")  # noqa: E741  (kept as in the app's copy)


# ── The example's tools, so probes read like the docs ─────────────────────────
@tool
def scale(n, weight=1):
    return n * 10 * weight


@tool
def add_n(acc, n):
    return (acc or 0) + n


@tool
def grid_cell(model, window):
    return f"{model}:{window}"


@tool
def to_rows(data: str) -> pd.DataFrame:
    return pd.DataFrame(json.loads(data))


@tool
def piv(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("city", as_index=False)["n"].sum()


@tool
def tag(city):
    return city


@tool
def dbl(n):
    return n * 2


def readings() -> pd.DataFrame:
    return pd.DataFrame({"city": ["SF", "NYC", "SF", "LA"], "n": [1, 2, 3, 2]})


DATA = json.dumps({"city": ["SF", "NYC", "SF", "LA"], "n": [1, 2, 3, 2]})


def _wf() -> grid.Workflow:
    wf = grid.Workflow()
    wf["readings"] = readings()
    return wf


def _input_of(operation) -> str:
    """The step an operation reads: the `input` slot (core c73f6f8+), else legacy `over`."""
    blob = operation.to_dict()
    ref = blob.get("input")
    if isinstance(ref, dict):
        return ref.get("$ref")
    return blob["modifiers"][-1]["params"].get("over")


def _try(fn: Callable):
    try:
        return fn(), None
    except Exception as exc:  # the probes report exceptions, never raise them
        return None, f"{type(exc).__name__}: {exc}"


# ── Probes: each returns (done, observed) ──────────────────────────────────────

def k1_unrun_source_columns():
    wf = grid.Workflow()
    wf["readings"] = to_rows.bind(data=DATA)[mod.source()]
    wf["scored"] = scale[mod.map(name="score")](wf["readings"])
    wf["picked"] = mod.select(over=wf["scored"], columns=["city", "score"])
    declared = wf.step("picked").status
    wf.run_all()
    got = wf.step("picked").output.data.to_dict("list")
    done = got == {"city": ["SF", "NYC", "SF", "LA"], "score": [10, 20, 30, 20]}
    return done, f"declared {declared}; after run_all -> {got}"


def k2_inference_run_state():
    a = _wf()
    a["x"] = add_n(a["readings"])
    b = grid.Workflow()
    b["readings"] = to_rows.bind(data=DATA)[mod.source()]
    b["x"] = add_n(b["readings"])
    va = a.steps["x"].operation.to_dict()["modifiers"][-1]["kind"]
    vb = b.steps["x"].operation.to_dict()["modifiers"][-1]["kind"]
    return va == vb, f"with data: {va}; before a tool-backed source runs: {vb}"


def k3_operation_as_input():
    wf = _wf()
    inner = I[mod.select(columns=["n"])](wf["readings"])
    built, err = _try(lambda: scale[mod.map()](inner))
    if err:
        return True, f"refused: {err[:120]}"
    wf["x"] = built
    wf.run("x")
    return False, (f"accepted; ran as {wf.steps['x'].operation.to_dict()['modifiers'][-1]['kind']}, "
                   f"status {wf.step('x').status}, data {wf.step('x').output.data.to_dict('list')}")


def k4_over_twice():
    wf = _wf()
    wf["other"] = pd.DataFrame({"n": [5]})
    built, err = _try(lambda: scale[mod.map(over=wf["readings"])](wf["other"]))
    if err:
        return True, f"refused: {err[:120]}"
    wf["x"] = built
    return False, f"accepted; input = {_input_of(wf.steps['x'].operation)!r} (the call won)"


def k5_string_over():
    wf = _wf()
    built, err = _try(lambda: mod.map(over="readings"))
    as_source = scale[mod.map()]("readings")
    source_kind = type(as_source).__name__
    if err:
        return True, f"mod.map(over='readings') refused: {err[:100]}"
    wf["x"] = scale[built]
    return False, (f"mod.map(over='readings') -> reference to step {_input_of(wf.steps['x'].operation)!r}; "
                   f"scale[mod.map()]('readings') -> {source_kind} (the string as data)")


def k6_source_call_form():
    built, err = _try(lambda: to_rows[mod.source()](data=DATA))
    if err:
        return False, f"to_rows[mod.source()](data=…) -> {err[:110]}"
    return isinstance(built, grid.Operation), f"-> {type(built).__name__}"


def k7_sweep_call_form():
    built, err = _try(lambda: grid_cell[mod.sweep(model=["a"], window=[7])]())
    if err:
        return False, f"grid_cell[mod.sweep(…)]() -> {err[:110]}"
    return isinstance(built, grid.Operation), f"-> {type(built).__name__} (a DataFrame means it ran instead of declaring)"


def k8_modifier_callable():
    wf = _wf()
    built, err = _try(lambda: mod.select(columns=["n"])(wf["readings"]))
    if err:
        return False, f"mod.select(columns=['n'])(wf['readings']) -> {err[:100]}"
    return True, f"-> {type(built).__name__}"


def k9_select_rows_and_columns():
    wf = _wf()
    built, err = _try(lambda: I[mod.select(columns=["n"], rows=[0, 2])](wf["readings"]))
    if err:
        return False, f"select(columns=…, rows=…) -> {err[:110]}"
    wf["x"] = built
    if wf.step("x").problems:
        return False, f"select(columns=…, rows=…) invalid: {wf.step('x').problems}"
    wf.run("x")
    got = wf.step("x").output.data.to_dict("list")
    return got == {"n": [1, 3]}, f"-> {got}"


def k10_value_from_step():
    wf = _wf()
    wf["params"] = 2
    built, err = _try(lambda: scale[mod.map()](wf["readings"], weight=wf["params"]))
    if err:
        return False, f"weight=wf['params'] -> {err[:110]}"
    wf["x"] = built
    wf.run_all()
    got = wf.step("x").output.data.get("value")
    return got is not None and list(got) == [20, 40, 60, 40], f"-> {None if got is None else list(got)}"


def k11_multi_input():
    wf = _wf()
    wf["other"] = pd.DataFrame({"n": [5]})
    built, err = _try(lambda: scale[mod.map(over=[wf["readings"], wf["other"]])])
    if err:
        # 008 K11's ask: refuse it with a message pointing at join/stack/zip_.
        return "join" in err, f"over=[a, b] -> {err[:110]}"
    _, err = _try(lambda: wf.__setitem__("x", built))
    if err:
        return False, f"over=[a, b] declared, then adding the step raised {err[:110]}"
    probs = wf.step("x").problems
    return not probs, f"over=[a, b] -> {probs or 'accepted'}"


def k12_whole_table_verb():
    verbs = set(grid.modifier_catalog())
    candidates = verbs & {"table", "apply", "frame", "whole", "pipe"}
    wf = _wf()
    wf["x"] = piv[mod.collapse(over=wf["readings"])]
    wf.run("x")
    err = wf.step("x").output.ledger["error"].iloc[0]
    return bool(candidates), (f"verbs: {sorted(verbs)}; piv[mod.collapse()] -> {str(err)[:90]}"
                              if not candidates else f"found {sorted(candidates)}")


def k13_catalog_takes_tool():
    entry = grid.modifier_catalog()["select"]
    keys = set(entry) - {"name", "class", "row_rule", "settings"}
    return bool(keys & {"takes_tool", "tool", "default_tool"}), f"modifier_catalog()['select'] keys: {sorted(entry)}"


def k14_progress_callback():
    params = inspect.signature(grid.Workflow.run).parameters
    return any(p not in ("self", "step_id", "tools", "resources") for p in params), f"Workflow.run{inspect.signature(grid.Workflow.run)}"


def k15_redrive():
    return hasattr(grid.Workflow, "redrive"), f"Workflow.redrive exists: {hasattr(grid.Workflow, 'redrive')}"


def k16_results_store():
    has = hasattr(grid.Output, "ref") or any("store" in n.lower() for n in dir(grid))
    return has, f"Output.ref: {hasattr(grid.Output, 'ref')}; store names in grid: {[n for n in dir(grid) if 'store' in n.lower()]}"


def k17_json_version():
    # (core) the app's probe could only say "check by hand"; this checks it:
    # the new format is written, v1 still loads, a newer file is refused.
    blob = json.loads(_wf().to_json())
    v1 = {"version": 1, "steps": [{"step_id": "r", "operation": {
        "tool_id": "scale", "input": None, "arguments": {"weight": 2},
        "modifiers": [{"kind": "map", "params": {}}]}}]}
    _, v1_err = _try(lambda: grid.Workflow.from_dict(v1))
    _, v3_err = _try(lambda: grid.Workflow.from_dict({**v1, "version": 99}))
    done = blob.get("version", 1) > 1 and v1_err is None and v3_err is not None
    return done, (f"to_json version = {blob.get('version')!r}; v1 loads: {v1_err is None}; "
                  f"newer refused: {v3_err is not None}")


def k18_timeout_enforced():
    import time

    @tool
    def slow(n):
        time.sleep(0.3)
        return n

    wf = _wf()
    wf["x"] = slow[mod.map(), mod.timeout(seconds=0.05)](wf["readings"])
    t0 = time.time()
    wf.run("x")
    took = time.time() - t0
    statuses = wf.step("x").output.ledger["status"].tolist()
    return "failed" in statuses or took < 0.3, f"4 units × 0.3s with timeout=0.05 took {took:.1f}s; statuses {statuses}"


# ── (core) probes for the 008 items the app's script does not cover ───────────

def n1_dict_or_none_setting():
    class DB:
        def __init__(self, table: dict | None = None):
            self.table = table
    _, e1 = _try(lambda: grid.Workflow().define("db", DB, table={"SF": "n"}))
    _, e2 = _try(lambda: grid.Workflow().define("db", DB, table=None))
    return not e1 and not e2, f"table={{…}} -> {e1 or 'ok'}; table=None -> {e2 or 'ok'}"


def n2_literal_beats_column():
    wf = _wf()
    built, err = _try(lambda: tag[mod.map()](wf["readings"], city="NYC"))
    if err:
        return True, f"refused: {err[:110]}"
    wf["x"] = built
    if wf.step("x").problems:
        return True, f"declaration problem: {wf.step('x').problems[0][:110]}"
    warned = any("overrides" in w for w in wf.step("x").warnings)
    wf.run("x")
    got = wf.step("x").output.values
    return got == ["NYC"] * 4 and warned, f"-> {got}; warned: {warned}"


def c13_output_replaces_input():
    wf = _wf()
    wf["x"] = dbl[mod.map(name="n")](wf["readings"])
    refused = bool(wf.step("x").problems)
    wf["y"] = dbl[mod.map(name="n", replace=True)](wf["readings"])
    ok = not wf.step("y").problems
    return refused and ok, (f"name='n' -> {wf.step('x').problems or 'accepted'}; "
                            f"replace=True -> {wf.step('y').problems or 'ok'}")


def o_missing_required_setting():
    blob = {"tool_id": "scale", "input": None, "arguments": {},
            "modifiers": [{"kind": "retry", "params": {}}, {"kind": "map", "params": {}}]}
    operation = grid.Operation.from_dict(blob)
    problems = grid.check(operation)
    return any("times" in p for p in problems), f"check(retry without times) -> {problems or '()'}"


def c6_unbound_wf():
    has = hasattr(grid, "wf")
    if not has:
        return False, "grid.wf does not exist"
    w1, w2 = grid.Workflow(), grid.Workflow()
    w1["r"] = pd.DataFrame({"n": [1, 2]})
    w2["r"] = pd.DataFrame({"n": [7, 8]})
    for w in (w1, w2):
        w["x"] = scale[mod.map()](grid.wf["r"])
        w.run("x")
    got = (w1.step("x").output.values, w2.step("x").output.values)
    return got == ([10, 20], [70, 80]), f"-> {got}"


def c10_failure_flows_downstream():
    calls = {"n": 0}

    @tool
    def risky(n: int) -> int:
        if n == 2:
            raise ValueError("boom")
        return n * 100

    @tool
    def plus1(value: int) -> int:
        calls["n"] += 1
        return value + 1

    wf = grid.Workflow()
    wf["r"] = pd.DataFrame({"n": [1, 2, 3]})
    built, err = _try(lambda: scale[mod.map()](wf["nope"]))
    if err:
        return False, f"wf['nope'] -> {err[:100]}"
    wf["bad"] = built
    # The owner's rule (2026-10-19): an uncaught failure stops run_all, so
    # the failure only flows downstream as state when the step lets it through.
    wf["a"] = risky[mod.map(), mod.try_except()](wf["r"]) if "try_except" in grid.MODIFIERS \
        else risky[mod.map()](wf["r"])
    wf["b"] = plus1[mod.map()](wf["a"])
    wf.run_all()
    cause = wf.step("b").output.ledger["cause"].iloc[1] if "cause" in wf.step("b").output.ledger else None
    dtype = str(wf.step("a").output.data["value"].dtype)
    done = (not wf.step("bad").valid and calls["n"] == 2 and dtype == "Int64"
            and cause == "a[1]: ValueError: boom")
    return done, f"bad ref -> {wf.step('bad').status}; a: {dtype}; plus1 calls {calls['n']}; cause {cause!r}"


def c14_missing_is_none():
    @tool
    def inc_opt(n: int | None) -> int:
        return 1 if n is None else n + 1

    @tool
    def inc(n: int) -> int:
        return n + 1

    wf = grid.Workflow()
    wf["r"] = pd.DataFrame({"n": [1, None, 3]})
    wf["o"] = inc_opt[mod.map()](wf["r"])
    wf["i"] = inc[mod.map()](wf["r"])
    wf.run_all()
    got = wf.step("o").output.values
    worded = any("can be None" in p for p in wf.step("i").problems)
    return got == [2, 1, 4] and worded, f"inc_opt -> {got}; inc problems -> {wf.step('i').problems}"


def r8_failed_rows_keep_int():
    @tool
    def risky(n: int) -> int:
        if n == 2:
            raise ValueError("boom")
        return n * 100

    wf = _wf()
    wf["out"] = risky[mod.map()](wf["readings"])
    wf.run("out")
    dtype = str(wf.step("out").output.data["value"].dtype)
    return dtype != "float64", f"out: {dtype} {wf.step('out').output.values}"


def c11_literals_round_trip():
    import datetime
    wf = _wf()
    values = [(1, 2), {1: "one"}, {1, 2}]
    wrong = []
    for v in values:
        wf["s"] = scale.bind(weight=v)[mod.map()](wf["readings"])
        back = grid.Workflow.from_json(wf.to_session_json(), grid.TOOLS).step("s").operation.arguments["weight"]
        if back != v or type(back) is not type(v):
            wrong.append(f"{v!r} -> {back!r}")
    wf["d"] = scale.bind(weight=datetime.date(2024, 1, 1))[mod.map()](wf["readings"])
    refused = bool(wf.step("d").problems)
    return not wrong and refused, f"lossy: {wrong or 'none'}; date refused at declaration: {refused}"


def c1_refs_in_every_slot():
    wf = _wf()
    wf["cols"] = ["city"]
    wf["w"] = 2
    built, err = _try(lambda: I[mod.select(columns=wf["cols"])](wf["readings"]))
    if err:
        return False, f"select(columns=wf['cols']) -> {err[:100]}"
    wf["s"] = built
    pos, err = _try(lambda: scale(wf["readings"], wf["w"]))
    if err:
        return False, f"scale(wf['r'], wf['w']) -> {err[:100]}"
    wf.run_all()
    got = wf.step("s").output.data.to_dict("list")
    same = pos == scale(wf["readings"], weight=wf["w"])
    return got == {"city": ["SF", "NYC", "SF", "LA"]} and same, f"select -> {got}; positional == keyword: {same}"


def c2_tool_settings():
    @tool
    def neg_n(n):
        return -n

    wf = _wf()
    built, err = _try(lambda: I[mod.sort(by=neg_n)](wf["readings"]))
    if err:
        return False, f"sort(by=tool) -> {err[:100]}"
    wf["s"] = built
    back = grid.Workflow.from_json(wf.to_session_json(), grid.TOOLS)
    back.run("s")
    got = list(back.step("s").output.data["n"])
    return got == [3, 2, 2, 1], f"sort(by=neg_n) after a round trip -> {got}"


def c7_selection():
    wf = grid.Workflow()
    wf["p"] = pd.DataFrame({"name": list("abcde"), "qty": [1, 2, 3, 4, 5],
                            "price": [10.0, 20.0, 30.0, 40.0, 50.0]})
    if not hasattr(grid, "cols"):
        return False, "grid.cols does not exist"
    c = grid.cols
    wf["block"] = wf["p"][1:3][c["name":"price"]]
    wf.run("block")
    got = wf.step("block").output.data.to_dict("list")
    _, err = _try(lambda: wf["p"]["price"])
    return (got == {"name": ["b", "c"], "qty": [2, 3], "price": [20.0, 30.0]} and err is not None,
            f"block -> {got}; wf['p']['price'] -> {(err or 'accepted')[:70]}")


class _C5Out(TypedDict):
    city: str
    n: int


@tool
def c5_load(path: str) -> Annotated[pd.DataFrame, _C5Out]:
    return pd.DataFrame({"city": ["SF"], "n": [1]})


def c5_typed_source_columns():
    # Module level on purpose: under `from __future__ import annotations` a
    # return annotation is a string, resolvable only from the module's names.
    wf = grid.Workflow()
    wf["r"] = c5_load[mod.source()](path="x")
    wf["typo"] = I[mod.select(columns=["cty"])](wf["r"])
    step = wf.step("r")
    plan = getattr(step, "plan", None) or {}
    cols_ = plan.get("columns", {}).get("names") if plan else grid.predicted_columns(step.output)
    caught = bool(wf.step("typo").problems)
    return cols_ == ["city", "n"] and caught, (
        f"unrun source columns -> {cols_}; select typo caught at declaration: {caught} "
        "(source half of C5; TypedDict-to-widen is still open)")


def c9_partial_plans():
    @tool
    def load_raw(path: str) -> pd.DataFrame:
        return pd.DataFrame({"city": ["SF"]})

    wf = grid.Workflow()
    wf["r"] = load_raw[mod.source()](path="x")
    plan = getattr(wf.step("r"), "plan", None)
    if not plan:
        return False, "Step.plan does not exist"
    rows_, cols_ = plan["rows"], plan["columns"]
    built, err = _try(lambda: I[mod.filter(), mod.expect(rows=10)](_wf()["readings"]))
    w2 = _wf()
    w2["k"] = I[mod.filter(), mod.expect(rows=10)](w2["readings"])
    contradiction = bool(w2.step("k").problems)
    done = (rows_["certainty"] == "unknown" and cols_["certainty"] == "unknown"
            and "resolve" in rows_ and contradiction)
    return done, (f"rows {rows_['certainty']}, columns {cols_['certainty']} (never []); "
                  f"filter+expect(rows=10) refused: {contradiction} "
                  "(tuple-length and join bounds still open)")


def stop_on_failure():
    @tool
    def risky(n: int) -> int:
        if n == 2:
            raise ValueError("boom")
        return n

    wf = _wf()
    wf["a"] = risky[mod.map()](wf["readings"])
    wf["b"] = scale[mod.map()](wf["a"])
    _, err = _try(wf.run_all)
    stopped = err is not None and "StepFailed" in err and wf.step("b").status == "staged"
    wf["a"] = risky[mod.map(), mod.try_except(default=0)](wf["readings"])
    _, err2 = _try(wf.run_all)
    return stopped and err2 is None, (f"uncaught -> {(err or 'no stop')[:70]}; "
                                      f"try_except(default=0) -> {err2 or 'ran'}")


ASKS = [
    ("K1", "Unrun source: columns unknown, re-check later", k1_unrun_source_columns),
    ("K2", "Verb inference independent of run state", k2_inference_run_state),
    ("K3", "Refuse an operation used as an input", k3_operation_as_input),
    ("K4", "Refuse `over` given twice", k4_over_twice),
    ("K5", "`over` takes a StepRef, not a string, in Python", k5_string_over),
    ("K6", "Declare a source in call form", k6_source_call_form),
    ("K7", "Declare a sweep in call form", k7_sweep_call_form),
    ("K8", "Tool-less modifiers callable on a reference", k8_modifier_callable),
    ("K9", "One select for rows and columns", k9_select_rows_and_columns),
    ("K10", "A value from another step as an argument (P5)", k10_value_from_step),
    ("K11", "Refuse over=[a, b] clearly", k11_multi_input),
    ("K12", "A whole-table verb", k12_whole_table_verb),
    ("K13", "modifier_catalog says which verbs take a tool", k13_catalog_takes_tool),
    ("K14", "Progress callback on run", k14_progress_callback),
    ("K15", "Re-run only the failed rows", k15_redrive),
    ("K16", "Pluggable results store", k16_results_store),
    ("K17", "Stable JSON version across P0", k17_json_version),
    ("K18", "timeout is enforced", k18_timeout_enforced),
    ("N1", "(core) dict | None resource setting accepts values", n1_dict_or_none_setting),
    ("N2", "(core) an explicit literal beats a same-named column, with a warning", n2_literal_beats_column),
    ("C13", "(core) an output never silently replaces an input column", c13_output_replaces_input),
    ("O", "(core) a missing required setting is a declaration problem", o_missing_required_setting),
    ("C6", "(core) grid.wf: an unbound step reference", c6_unbound_wf),
    ("C10", "(core) failure is a state that flows downstream", c10_failure_flows_downstream),
    ("C14", "(core) missing is None; nullability is checked", c14_missing_is_none),
    ("R8", "(core) failed rows keep an int column int", r8_failed_rows_keep_int),
    ("C11", "(core) literals round-trip exactly; others refused", c11_literals_round_trip),
    ("C1", "(core) a reference in every slot, positional args", c1_refs_in_every_slot),
    ("C2", "(core) a tool as a shape setting", c2_tool_settings),
    ("C7", "(core) Excel-style selection", c7_selection),
    ("C5", "(core) a source's declared columns stage before it runs", c5_typed_source_columns),
    ("C9", "(core) partial plans: certainty, because, resolve; mod.expect", c9_partial_plans),
    ("STOP", "(core) an uncaught failure stops run_all; try_except lets it through", stop_on_failure),
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or "?"
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "src"],
                           capture_output=True, text=True).stdout.strip()
    print(f"simple-steps-core at {commit}{' + uncommitted changes' if dirty else ''}\n")
    open_count = 0
    for ask_id, title, probe in ASKS:
        result, err = _try(probe)
        if err:
            done, observed = False, f"probe raised {err[:120]}"
        else:
            done, observed = result
        open_count += not done
        print(f"{ask_id:4} {'DONE' if done else 'OPEN':4}  {title}\n           {observed}")
    print(f"\n{len(ASKS) - open_count}/{len(ASKS)} done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
