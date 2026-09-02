"""Example tools file for the Streamlit dashboard.

Run it::

    python -m pip install -e ".[dashboard]"
    simple-steps-core-dashboard streamlit_example/example_tools_and_resources.py

You only edit this file. Each tool can optionally provide a Streamlit view via
``ui={"streamlit": fn}``; tools without one get an auto-generated form.
"""

from simple_steps_core import ArgGuardrail, Guardrails, Resource, register_tool


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
