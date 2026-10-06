"""One consolidated example: every grid-model orchestration over one registry.

This is the single canonical example for the library. It defines **one** set of
tools (the registry below) and one small tabular dataset, then wires a workflow
that exercises **every shape verb**, both fan-out chains, the execution
modifiers, serialization, staging/validation and per-row failure.

Run it directly to print each step:

    python examples/all_orchestrations/pipeline.py

The same builders are asserted end to end in
``tests/integration/test_all_orchestrations.py`` — that test is what keeps this
example honest.

The grid model is imported as a module on purpose: ``Workflow``, ``Operation``
and ``Step`` also exist in the engine and mean different things there
(docs/grid-model.md §0).
"""

from __future__ import annotations

import pandas as pd

from simple_steps_core import grid
from simple_steps_core.grid import join, mod, op, stack, tool, zip_


# ─────────────────────────────────────────────────────────────────────────
# The registry — the one set of tools every case below shares.
# A tool declares the *values* it needs by name; supplying rows is the
# modifier's job, so none of these mentions a row or a grid.
# ─────────────────────────────────────────────────────────────────────────
@tool
def scale(n, weight=1):
    """map: a value per row — the score."""
    return n * 10 * weight


@tool
def is_big(n) -> bool:
    """filter: a predicate — keep rows whose n is greater than one."""
    return n > 1


@tool
def label_city(city):
    """group: a key function — the bucket a row belongs to."""
    return city


@tool
def add_n(acc, n):
    """collapse: a two-argument reducer — running sum of n."""
    return (acc or 0) + n


@tool
def fan_out(n) -> list:
    """expand: each row yields a list — n copies of n."""
    return [n] * n


@tool
def make_coords(n):
    """expand -> widen: each row yields a list of records to be spread wide."""
    return [{"axis": "x", "val": n}, {"axis": "y", "val": n * 2}]


@tool
def grid_cell(model, window):
    """sweep: run over the cross product of named parameter lists."""
    return f"{model}:{window}"


@tool
def risky(n):
    """failure: raises on a specific value so some rows fail and some pass."""
    if n == 2:
        raise ValueError("twos are not allowed")
    return n * 100


@tool
def make_pair(n):
    """tuple return — widen auto-names the positions c0, c1."""
    return (n * 10, n * n)


# ─────────────────────────────────────────────────────────────────────────
# The data — deliberately tiny and tabular.
# ─────────────────────────────────────────────────────────────────────────
def readings() -> pd.DataFrame:
    """Four observations of two variables: a city and a reading n."""
    return pd.DataFrame({"city": ["SF", "NYC", "SF", "LA"], "n": [1, 2, 3, 2]})


def records() -> pd.DataFrame:
    """A column of records — one dict cell per row, for `widen` to spread."""
    return pd.DataFrame({"value": [{"city": "SF", "temp": 18.0},
                                   {"city": "NYC", "temp": 31.0}]})


# ─────────────────────────────────────────────────────────────────────────
# The one workflow — every valid orchestration, wired over the shared registry.
# ─────────────────────────────────────────────────────────────────────────
def build() -> grid.Workflow:
    """Declare (but do not run) the comprehensive workflow.

    Each assignment is one step. Reading top to bottom is the whole grammar:
    a tool, a shape verb in brackets, the step it reads via ``over=``.
    """
    wf = grid.Workflow()

    # ── sources — a value is one cell until a verb fans out over it ──────
    wf["readings"] = readings()                      # source: 4 rows, 2 cols
    wf["records"] = records()                        # source: dict cells

    # ── map — n rows in, n rows out, plus one payload column ────────────
    wf["scored"] = scale[mod.map(over=wf["readings"], name="score")]

    # ── the row-axis reshapers (no tool runs) ───────────────────────────
    wf["kept"] = is_big[mod.filter(over=wf["scored"])]          # filter: rows
    wf["head2"] = mod.slice(over=wf["scored"], stop=2)          # slice: first 2
    wf["ranked"] = mod.sort(over=wf["scored"], by="score", ascending=False)
    wf["unique_city"] = mod.distinct(over=wf["scored"], columns=["city"])

    # ── the column-axis reshapers (no tool runs) ────────────────────────
    wf["picked"] = mod.select(over=wf["scored"], columns=["city", "score"])
    wf["dropped"] = mod.drop(over=wf["scored"], columns=["score"])
    wf["renamed"] = mod.rename(over=wf["scored"], columns={"n": "count"})

    # ── group -> collapse: the stratified-summary chain ─────────────────
    wf["bucketed"] = label_city[mod.group(over=wf["scored"], name="bucket")]
    wf["per_city"] = add_n[mod.collapse(by="bucket", over=wf["bucketed"], initial=0)]

    # ── collapse to one row — a builtin reducer and a registry reducer ──
    wf["n_rows"] = op("count")[mod.collapse(over=wf["readings"])]
    wf["sum_n"] = add_n[mod.collapse(over=wf["readings"], initial=0)]

    # ── expand (unnest longer) and the expand -> widen chain ────────────
    wf["bursts"] = fan_out[mod.expand(over=wf["readings"], name="item")]
    wf["coords"] = make_coords[mod.expand(over=wf["readings"], name="value")]
    wf["spread"] = mod.widen(over=wf["coords"], columns=["axis", "val"])

    # ── widen (unnest wider) straight off a column of records ───────────
    wf["wide"] = mod.widen(over=wf["records"], columns=["city", "temp"])

    # ── sweep — a grid from the cross product of parameters (no input) ──
    wf["grid_search"] = grid_cell[mod.sweep(model=["a", "b"], window=[7, 30])]

    # ── execution modifiers — shape-preserving, order is semantics ──────
    wf["robust"] = scale[mod.map(over=wf["readings"], name="score"),
                         mod.retry(times=2), mod.timeout(seconds=5)]

    # ── verb inference — pass a reference, no verb; the shape is chosen ──
    # The stored verb is concrete and replaceable, not hidden (see infer_verb).
    wf["auto_map"] = scale(wf["readings"])          # ordinary tool    → map
    wf["auto_filter"] = is_big(wf["readings"])      # returns bool     → filter
    wf["auto_collapse"] = add_n(wf["readings"])     # (acc, x) reducer → collapse
    wf["auto_expand"] = fan_out(wf["readings"])     # returns list     → expand

    # ── standard Python types as sources — each is ONE cell, then reshaped ──
    wf["a_list"] = [1, 2, 3, 4]                     # list   → one cell
    wf["a_dict"] = {"x": 10, "y": 20}              # dict   → one cell
    wf["a_scalar"] = 7                              # scalar → one cell
    wf["from_list"] = mod.expand(over=wf["a_list"])            # list cell → rows
    wf["from_dict"] = mod.widen(over=wf["a_dict"], columns=["x", "y"])  # dict → cols

    # ── a column of tuples widens positionally (auto c0, c1) ──
    wf["pairs"] = make_pair[mod.map(over=wf["readings"], name="value")]
    wf["split"] = mod.widen(over=wf["pairs"])       # no columns= → c0, c1

    # ── builtin reducers over a single-column grid ──
    wf["ns"] = mod.select(over=wf["readings"], columns=["n"])
    wf["gathered"] = op("gather")[mod.collapse(over=wf["ns"])]   # [1, 2, 3, 2]
    wf["total_n"] = op("total")[mod.collapse(over=wf["ns"])]     # 8
    wf["first_n"] = op("first")[mod.collapse(over=wf["ns"])]     # 1
    wf["last_n"] = op("last")[mod.collapse(over=wf["ns"])]       # 2

    # ── chained fan-out: map over a map step ──
    wf["again"] = scale[mod.map(over=wf["scored"], name="again")]

    # ── combine verbs — read more than one grid (operation constructors) ──
    # These are not modifiers: a combine is a function of its grids, so it is
    # written `join(a, b, ...)`, not `op[mod.join(...)]`. Each applies no tool.
    wf["city_info"] = pd.DataFrame({"city": ["SF", "NYC", "LA"],
                                    "region": ["west", "east", "west"]})
    wf["more"] = pd.DataFrame({"city": ["BOS", "SEA"], "n": [5, 6]})
    wf["enriched"] = join(wf["readings"], wf["city_info"], on="city", how="left")
    wf["all_readings"] = stack(wf["readings"], wf["more"])       # 4 + 2 = 6 rows
    wf["scores_only"] = mod.select(over=wf["scored"], columns=["score"])
    wf["zipped"] = zip_(wf["ns"], wf["scores_only"])            # n + score, by position

    return wf


def run() -> grid.Workflow:
    """Build and run the whole workflow, every step after the ones it reads."""
    return build().run_all()


# ─────────────────────────────────────────────────────────────────────────
# The components around the verbs: failure, staging/validation, round-trip.
# ─────────────────────────────────────────────────────────────────────────
def failure() -> grid.Workflow:
    """A tool that fails on some rows: the ledger keeps every unit.

    `risky` raises on n == 2. Two of the four readings are 2, so two rows fail
    and two complete — and `.failed` is the exact re-drive set.
    """
    wf = grid.Workflow()
    wf["readings"] = readings()
    wf["out"] = risky[mod.map(over=wf["readings"], name="out"), mod.retry(times=1)]
    return wf.run_all()


def validation() -> grid.Workflow:
    """Staging and declaration-time checks — both before anything runs.

    One good step (staged, its cell count predicted) and two bad ones (an
    unknown bound argument, and a reference to a step that does not exist).
    `wf.validate()` returns every step's problems without executing.
    """
    wf = grid.Workflow()
    wf["readings"] = readings()
    wf["scored"] = scale[mod.map(over=wf["readings"], name="score")]   # valid, staged
    wf["bad_arg"] = scale.bind(nope=1)[mod.map(over=wf["readings"])]   # unknown param
    wf["dangling"] = scale[mod.map(over="nowhere")]                    # missing upstream
    return wf


def roundtrip() -> tuple[grid.Workflow, grid.Workflow]:
    """Serialize a run workflow and rebuild it — payloads and all.

    The full session export carries every payload; rebuilding through the same
    registry reproduces the exact outputs. Returns (original, reloaded).
    """
    original = run()
    reloaded = grid.Workflow.from_json(original.to_session_json(), grid.TOOLS)
    return original, reloaded


# ─────────────────────────────────────────────────────────────────────────
def main() -> None:
    wf = run()
    print(wf, "\n")
    for sid, step in wf.steps.items():
        print(f"  {sid:12} {step.describe()}")

    print("\nmap (scored):")
    print(wf.step("scored").output.view().to_string(index=False))

    print("\ngroup -> collapse (per_city):")
    print(wf.step("per_city").output.data.to_string(index=False))

    print("\nexpand -> widen (spread):")
    print(wf.step("spread").output.data.to_string(index=False))

    print("\nsweep (grid_search):")
    print(wf.step("grid_search").output.data.to_string(index=False))

    print("\nverb inference (pass a reference, no verb — the shape is chosen):")
    for sid in ("auto_map", "auto_filter", "auto_collapse", "auto_expand"):
        kind = wf.step(sid).operation.to_dict()["modifiers"][0]["kind"]
        print(f"  {sid:14} → {kind}")

    print("\nstandard types as sources (each one cell):")
    for sid in ("a_list", "a_dict", "a_scalar"):
        print(f"  {sid:10} {wf.step(sid).output.data.iloc[0, 0]!r}")
    print("  from_list (expand) →", wf.step("from_list").output.values)
    print("  split tuple (widen) →", list(wf.step("split").output.data.columns))

    print("\ntool palette (catalog):", ", ".join(sorted(grid.catalog())))

    fail = failure()
    print("\nfailure (out) — the failed re-drive set:")
    print(fail.step("out").output.failed.to_string())

    checks = validation()
    print("\nvalidation — problems per step (empty = valid):")
    for sid, problems in checks.validate().items():
        print(f"  {sid:12} {problems or 'ok'}")


if __name__ == "__main__":
    main()
