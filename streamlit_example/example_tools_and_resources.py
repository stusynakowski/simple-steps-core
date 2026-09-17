"""Example tools file for the Streamlit dashboard.

Run it::

    python -m pip install -e ".[dashboard]"
    python streamlit_example/example_tools_and_resources.py

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

from simple_steps_core import ArgGuardrail, Guardrails, Resource, register_tool
from simple_steps_core.streamlit import Dashboard


# ── A tool with a custom Streamlit UI ────────────────────────────────────
def _make_list_ui(st, *, key, defaults):
    """render(st, key, defaults) -> args dict. Draw widgets, return arguments."""
    n = st.slider("How many numbers?", 1, 20, value=defaults.get("n", 5), key=f"{key}_n")
    return {"n": n}


@register_tool("make_list", description="Create the list [0, 1, ..., n-1].", ui={"streamlit": _make_list_ui})
def make_list(n: int) -> list[int]:
    return list(range(n))


# ── A tool with an auto-generated form (no Streamlit view) ────────────────
@register_tool("scale", description="Multiply a number by a factor.")
def scale(x: int, factor: int = 2) -> int:
    return x * factor


# ── A tool that maps *several* render targets in one ``ui=`` ──────────────
# ``ui`` is a {target: renderer} map. Here we ship both a hand-written prefab
# view (for a React frontend) and a Streamlit view; each surface picks its own.
def _pick_region_streamlit(st, *, key, defaults):
    region = st.selectbox("Region", ["EMEA", "APAC", "AMER"], key=f"{key}_region")
    return {"region": region}


_pick_region_prefab = {
    "view": {
        "type": "Card",
        "children": [
            {"type": "CardTitle", "content": "Pick region"},
            {"type": "Combobox", "bind": "region",
             "children": [{"type": "Option", "value": r} for r in ("EMEA", "APAC", "AMER")]},
        ],
    },
    "state": {"region": "EMEA"},
}


@register_tool("pick_region", description="Choose a sales region.", ui={
    "prefab": _pick_region_prefab,        # React frontend
    "streamlit": _pick_region_streamlit,  # this dashboard
})
def pick_region(region: str) -> str:
    return region


# ── A tool with guardrails (shape the form + gate the run) ────────────────
@register_tool("charge", description="Charge an amount.", guardrails=Guardrails(
    usage="Only after the user confirms.",
    destructive=True,
    requires_confirmation=True,
    arguments={"amount": ArgGuardrail(minimum=1, maximum=1000)},
))
def charge(amount: int) -> str:
    return f"charged ${amount}"


# ── A tool with both lifecycle views: a form AND a result view ────────────
# The library requires a composed UI to define an ``input`` view, so a tool that
# wants a custom ``result`` view supplies both. Note the trade-off: a tool that
# renders its own form owns it completely, so the Step Manager can't offer the
# "bind this argument to an earlier step's output" picker for it. Leave ``ui``
# off (like ``summarize`` below) to keep the auto-form and that picker.
def _total_input_ui(st, *, key, defaults):
    text = st.text_input(
        "Numbers (comma-separated)",
        value=", ".join(str(v) for v in defaults.get("rows", [1, 2, 3])),
        key=f"{key}_rows",
    )
    rows = [int(part) for part in text.replace(",", " ").split() if part.strip("-").isdigit()]
    return {"rows": rows}


def _total_result_ui(st, *, key, result):
    """render(st, key, result) -> None. `result` is the step's StepOutput."""
    value = result.value
    left, right = st.columns(2)
    left.metric("count", value["count"])
    right.metric("total", value["total"])
    st.caption(f"computed in {result.duration:.3f}s")


@register_tool("total", description="Count and total a hand-typed list.", ui={
    "streamlit": {"input": _total_input_ui, "result": _total_result_ui},
})
def total(rows: list[int]) -> dict:
    return {"count": len(rows), "total": sum(rows)}


# ── An auto-form tool taking a list ───────────────────────────────────────
# `rows: list[int]` gets a JSON text area from the auto-form, and in the Step
# Manager it can instead be bound to an earlier step's output.
@register_tool("summarize", description="Count and total a list of numbers.")
def summarize(rows: list[int]) -> dict:
    return {"count": len(rows), "total": sum(rows)}


# ── A tool whose enum guardrail drives the widget ─────────────────────────
@register_tool("set_mode", description="Pick a run mode.", guardrails=Guardrails(
    arguments={"mode": ArgGuardrail(enum=["fast", "balanced", "thorough"])},
))
def set_mode(mode: str = "balanced") -> str:
    return mode


# ── A tool that uses an injected resource ─────────────────────────────────
@register_tool("greet", description="Greet using an injected name service.")
def greet(names=Resource()) -> str:
    return f"hello, {names.current()}"


class _NameService:
    def current(self) -> str:
        return "world"


# Optional dashboard config and injected resources.
CONFIG = {"title": "My Tools Dashboard"}
RESOURCES = {"names": _NameService}   # factory (callable) or instance


if __name__ == "__main__":
    Dashboard().run()
