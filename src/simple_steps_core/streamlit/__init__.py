"""Optional Streamlit surface for building and running workflows.

Two layers:

* :mod:`~simple_steps_core.streamlit.components` — one component per object in
  the core library. Thin adapters over ``info()`` / ``validate()`` / ``preview()``
  that take ``st`` as a parameter, own no state, and take caller-supplied
  ``on_…`` callbacks for actions. Use these to build your own surface.
* :class:`Dashboard` — the ready-made Step Manager app, itself just a caller of
  those components.

Import stays cheap: Streamlit itself is only imported when the dashboard runs.
"""

from . import components
from .components import render, render_tool_form
from .dashboard import Dashboard

__all__ = ["Dashboard", "components", "render", "render_tool_form"]
