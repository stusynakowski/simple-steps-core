"""Example tools for the Streamlit dashboard — one coherent pipeline.

Run it::

    python -m pip install -e ".[dashboard]"
    python streamlit_example/example_tools_and_resources.py

The tools below are built to be chained into a single flow that exercises every
orchestration mode in turn:

    step1  load_batches            single    -> list[list[float]]   one cell
    step2  identity        expand  over=step1 -> list[float]        one cell per reading
    step3  above_cutoff    filter  over=step2 -> list[float]        the readings that pass
    step4  accumulate_stats collapse over=step3 -> dict             one cell of statistics

``identity`` is built in (registered alongside the orchestrators): it passes each
item through unchanged, so a fan-out can reshape data with no bespoke tool.
``expand`` + ``identity`` flattens one level. ``unpack_batch`` below does the same
thing explicitly, and is kept to show that a fan-out's per-item ``op`` can be any
tool you write.

Wire it in the dashboard by choosing the tool, then saying where its data comes
**from** and how to **apply** it (`once`, `map`, `filter`, `expand`, `reduce`).
`tests/unit/test_example_pipeline.py` and `test_dashboard_pipeline.py` run this
chain at both levels, so the example stays honest.

You only edit this file. Each tool can optionally provide Streamlit views via
``ui={"streamlit": ...}``; tools without one get a form auto-generated from the
tool contract (signature + ``input_schema`` + ``guardrails``). The
``Dashboard().run()`` call at the bottom launches the UI.

A tool's ``ui`` entry is either a single callable (the **input** view) or a dict
of lifecycle phases::

    ui={"streamlit": {"input": render_form, "result": render_result}}

  * ``input(st, *, key, defaults) -> dict``  — draw widgets, return arguments.
  * ``result(st, *, key, result)``           — draw a completed step's output;
    ``result`` is the ``StepOutput`` (``result.value`` plus timing fields).
"""

import statistics

from simple_steps_core import ArgGuardrail, Guardrails, Resource, register_tool
from simple_steps_core.streamlit import Dashboard


# ── 1. Source: one cell holding a list of batches ─────────────────────────
# A custom Streamlit input view — the auto-form would work too, but this shows
# the `ui=` hook. Sliders keep the numbers small enough to read in the grid.
def _load_batches_ui(st, *, key, defaults):
    """render(st, key, defaults) -> args dict. Draw widgets, return arguments."""
    batches = st.slider("How many batches?", 1, 8,
                        value=defaults.get("batches", 3), key=f"{key}_batches")
    per_batch = st.slider("Readings per batch", 1, 10,
                          value=defaults.get("per_batch", 4), key=f"{key}_per")
    return {"batches": batches, "per_batch": per_batch}


@register_tool(
    "load_batches",
    description="Load sensor readings, grouped into batches. One cell, nested.",
    ui={"streamlit": _load_batches_ui},
)
def load_batches(batches: int = 3, per_batch: int = 4) -> list[list[float]]:
    return [
        [round(10 + batch * 7 + reading * 3.5, 1) for reading in range(per_batch)]
        for batch in range(batches)
    ]


# ── 2. expand: one cell per reading ───────────────────────────────────────
# `expand` flat-maps: each item's returned iterable is concatenated, so a list
# of batches becomes a flat list of readings.
@register_tool("unpack_batch", description="Yield each reading in a batch (use with expand).")
def unpack_batch(batch: list[float]) -> list[float]:
    return list(batch)


# ── 3. filter: keep the readings that pass ────────────────────────────────
# The item binds to the first required param (`value`); `cutoff` is a constant
# argument shared across every per-item call.
@register_tool("above_cutoff", description="Keep readings at or above a cutoff (use with filter).",
               guardrails=Guardrails(arguments={"cutoff": ArgGuardrail(minimum=0, maximum=100)}))
def above_cutoff(value: float, cutoff: float = 20.0) -> bool:
    return value >= cutoff


# ── 4. collapse: reduce to one cell of statistics ─────────────────────────
# A 2-argument reducer: the first param is the accumulator, the second the next
# item. With no `initial`, the first reading seeds the accumulator — so the
# first call receives a float and every later call a dict.
def _stats_result_ui(st, *, key, result):
    """render(st, key, result) -> None. `result` is the step's StepOutput."""
    value = result.value
    if not isinstance(value, dict):
        st.write(value)
        return
    cols = st.columns(4)
    for col, field in zip(cols, ("count", "mean", "minimum", "maximum")):
        col.metric(field, value.get(field, "—"))


@register_tool(
    "accumulate_stats",
    description="Reduce readings to count/mean/min/max (use with collapse).",
    ui={"streamlit": {"input": lambda st, *, key, defaults: {}, "result": _stats_result_ui}},
)
def accumulate_stats(running: object, value: float) -> dict:
    seen = running["_seen"] if isinstance(running, dict) else [float(running)]
    seen = [*seen, float(value)]
    return {
        "count": len(seen),
        "mean": round(statistics.fmean(seen), 2),
        "minimum": min(seen),
        "maximum": max(seen),
        "_seen": seen,
    }


# ── A plain single-call summary, for comparison with the collapse ─────────
@register_tool("summarize", description="Count and total a list of numbers.")
def summarize(rows: list[float]) -> dict:
    return {"count": len(rows), "total": round(sum(rows), 2)}


# ── A tool that uses an injected resource ─────────────────────────────────
@register_tool("describe_sensor", description="Name the sensor from an injected service.")
def describe_sensor(sensors=Resource()) -> str:
    return sensors.current()


class _SensorService:
    def current(self) -> str:
        return "sensor-01"


# Optional dashboard config and injected resources.
CONFIG = {"title": "Readings Pipeline"}
RESOURCES = {"sensors": _SensorService}   # factory (callable) or instance


if __name__ == "__main__":
    Dashboard().run()
