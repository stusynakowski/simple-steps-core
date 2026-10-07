"""One consolidated example: every grid-model orchestration over one registry.

This is the single canonical example for the library. It defines **one** set of
tools (the registry below) and one small tabular dataset, then wires a workflow
that exercises **every shape verb**, both fan-out chains, the execution
modifiers, serialization, staging/validation and per-row failure — and a second
workflow that uses **resources**: a dummy database and a dummy LLM, each with
bound and unbound tools.

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
from simple_steps_core.grid import (bound_tool, join, mod, op, res, resource,
                                    stack, tool, zip_)


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
# Resources — objects a workflow uses that are not data (core-proposals/007).
#
# The notation, three marks:
#
#   @resource      on a class: a resource type, built from literal settings.
#   @bound_tool    on a method: a BOUND tool — it runs on one named instance,
#                  written  res["db"].lookup[mod.map()](wf["keys"]).
#                  The method stays an ordinary method.
#   @tool          on a free function with a resource-typed parameter: an
#                  UNBOUND tool — it needs a resource but does not belong to
#                  one, written  enrich[mod.map()](wf["readings"], db=res["db"]).
#
# An unmarked method (FakeDB.reset) is never a tool, though tool code may call it.
# Both dummies are deterministic and count their calls, so a test can check
# that one instance served every row.
# ─────────────────────────────────────────────────────────────────────────
@resource
class FakeDB:
    """An in-memory table: city -> region."""

    def __init__(self, table: dict | None = None):
        self.table = dict(table or {"SF": "west", "NYC": "east", "LA": "west"})
        self.reads = 0

    @bound_tool
    def lookup(self, key: str) -> str | None:
        """The region stored for a key, or None."""
        self.reads += 1
        return self.table.get(key)

    def reset(self) -> None:                      # unmarked: never a tool
        self.reads = 0


@resource
class FakeLLM:
    """Answers deterministically: the model name, then the prompt upper-cased."""

    def __init__(self, model: str = "fake-1"):
        self.model = model
        self.calls = 0

    @bound_tool
    def complete(self, prompt: str) -> str:
        """One completion for a prompt."""
        self.calls += 1
        return f"[{self.model}] {prompt.upper()}"


@resource
class TinyLLM(FakeLLM):
    """A smaller FakeLLM — fits anywhere a FakeLLM is asked for."""


@tool
def enrich(city: str, db: FakeDB) -> str:
    """unbound: the region for a city, read from the database."""
    return db.lookup(city) or "unknown"


@tool
def summarize(text: str, llm: FakeLLM) -> str:
    """unbound: one line from the model."""
    return llm.complete(text)


@tool
def lookup_fresh(city: str, db: FakeDB) -> str:
    """unbound: resets the read counter, then looks up — tool code may call anything."""
    db.reset()
    return db.lookup(city) or "unknown"


def notes() -> pd.DataFrame:
    """Two short texts for the LLM to summarize."""
    return pd.DataFrame({"text": ["a", "b"]})


def live_resources() -> dict:
    """What the caller owns and passes to ``run`` — the workflow never builds these."""
    return {"db": FakeDB(), "llm": FakeLLM(model="fake-1"),
            "tiny": TinyLLM(model="tiny-1")}


def build_resources() -> grid.Workflow:
    """Declare (but do not run) the resource workflow.

    Resources are declared once with ``wf.define`` — a type and literal
    settings, no object — and every step names the one it uses with ``res[…]``.
    Declaring needs only the declared types, so every step validates here.
    """
    wf = grid.Workflow()
    wf.define("db", FakeDB)
    wf.define("llm", FakeLLM, model="fake-1")
    wf.define("tiny", TinyLLM, model="tiny-1")

    wf["readings"] = readings()
    wf["notes"] = notes()
    wf["keys"] = mod.rename(over=wf["readings"], columns={"city": "key"})

    # ── unbound tools: a resource is an argument, chosen per step ────────
    wf["regions"] = enrich[mod.map()](wf["readings"], db=res["db"])
    wf["summaries"] = summarize[mod.map()](wf["notes"], llm=res["llm"])
    wf["tiny_summaries"] = summarize[mod.map()](wf["notes"], llm=res["tiny"])  # subclass fits

    # ── bound tools: a marked method of one named instance ───────────────
    wf["regions_bound"] = res["db"].lookup[mod.map()](wf["keys"])
    wf["hello"] = res["llm"].complete[mod.source()](prompt="hi")
    wf["inferred"] = res["db"].lookup(wf["keys"])           # verb inferred: map

    # ── a resource step's output feeds later steps like any other ────────
    wf["region_table"] = mod.select(over=wf["regions"], columns=["city", "value"])
    return wf


def run_resources() -> tuple[grid.Workflow, dict]:
    """Build and run the resource workflow against the caller's objects."""
    live = live_resources()
    return build_resources().run_all(resources=live), live


def resource_problems() -> grid.Workflow:
    """Every way a resource step is refused at declaration — nothing runs."""
    wf = grid.Workflow()
    wf.define("db", FakeDB)
    wf.define("llm", FakeLLM)
    wf["notes"] = notes()
    wf["wrong_type"] = summarize[mod.map()](wf["notes"], llm=res["db"])
    wf["unknown"] = summarize[mod.map()](wf["notes"], llm=res["nope"])
    wf["unmarked"] = res["db"].reset[mod.source()]()
    wf["not_a_column"] = summarize[mod.map()](wf["notes"])   # llm left unbound
    return wf


def resource_roundtrip() -> tuple[grid.Workflow, grid.Workflow]:
    """Save the resource workflow and reload it — declarations only, no objects.

    The session export, like :func:`roundtrip`, so the source tables come
    along. The resources section is the same in either export: a type and its
    settings, never the live object.
    """
    original = build_resources()
    reloaded = grid.Workflow.from_json(original.to_session_json(), grid.TOOLS,
                                       resource_types={"FakeDB": FakeDB,
                                                       "FakeLLM": FakeLLM,
                                                       "TinyLLM": TinyLLM})
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

    res_wf, live = run_resources()
    print("\nresources — FakeDB and FakeLLM, bound and unbound tools:")
    for name, decl in res_wf.resources.items():
        print(f"  res[{name!r}] = {decl.type_name}({decl.settings})")
    for sid in ("regions", "summaries", "tiny_summaries", "regions_bound",
                "inferred"):
        print(f"  {sid:15} {res_wf.step(sid).operation.tool_id:14} "
              f"{res_wf.step(sid).output.values}")
    print(f"  {'hello':15} {'FakeLLM.complete':14} "
          f"{res_wf.step('hello').output.data.iloc[0, 0]!r}  (a source: one cell)")
    print(f"  one instance each: db.reads={live['db'].reads}, "
          f"llm.calls={live['llm'].calls}, tiny.calls={live['tiny'].calls}")
    blob = res_wf.to_dict()
    saved = {e["step_id"]: e["operation"] for e in blob["steps"]}
    print("  saved: summaries →", saved["summaries"]["arguments"],
          "| regions_bound →", saved["regions_bound"]["tool_id"],
          saved["regions_bound"]["bound_to"],
          "| res['llm'] →", blob["resources"]["llm"])

    print("\nresource problems — refused at declaration:")
    for sid, problems in resource_problems().validate().items():
        print(f"  {sid:13} {problems[0] if problems else 'ok'}")

if __name__ == "__main__":
    main()
