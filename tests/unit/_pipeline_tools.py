"""A four-step orchestration pipeline, as plain tools.

Exercises the engine end to end — ``single`` → ``expand`` → ``filter`` →
``collapse``, plus resource injection and an argument guardrail — with no
renderer involved. It lives beside the tests because what they cover is the
engine, not any particular host.

Leading underscore so pytest does not collect it as a test module.
"""

import statistics

from simple_steps_core import ArgGuardrail, Guardrails, Resource, register_tool


# ── 1. single: one cell holding a nested list ─────────────────────────────
@register_tool(
    "load_batches",
    description="Load sensor readings, grouped into batches. One cell, nested.",
)
def load_batches(batches: int = 3, per_batch: int = 4) -> list[list[float]]:
    return [
        [round(10 + batch * 7 + reading * 3.5, 1) for reading in range(per_batch)]
        for batch in range(batches)
    ]


# ── 2. expand: one cell per reading ───────────────────────────────────────
# `expand` flat-maps: each item's returned iterable is concatenated, so a list
# of batches becomes a flat list of readings.
@register_tool("unpack_batch",
               description="Yield each reading in a batch (use with expand).")
def unpack_batch(batch: list[float]) -> list[float]:
    return list(batch)


# ── 3. filter: keep the readings that pass ────────────────────────────────
# The item binds to the first required param (`value`); `cutoff` is a constant
# argument shared across every per-item call.
@register_tool("above_cutoff",
               description="Keep readings at or above a cutoff (use with filter).",
               guardrails=Guardrails(
                   arguments={"cutoff": ArgGuardrail(minimum=0, maximum=100)}))
def above_cutoff(value: float, cutoff: float = 20.0) -> bool:
    return value >= cutoff


# ── 4. collapse: reduce to one cell of statistics ─────────────────────────
# A 2-argument reducer: the first param is the accumulator, the second the next
# item. With no `initial`, the first reading seeds the accumulator — so the
# first call receives a float and every later call a dict.
@register_tool(
    "accumulate_stats",
    description="Reduce readings to count/mean/min/max (use with collapse).",
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
@register_tool("describe_sensor",
               description="Name the sensor from an injected service.")
def describe_sensor(sensors=Resource()) -> str:
    return sensors.current()


class _SensorService:
    def current(self) -> str:
        return "sensor-01"


RESOURCES = {"sensors": _SensorService}   # factory (callable) or instance
