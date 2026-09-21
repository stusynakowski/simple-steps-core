"""
Dashboard panels
================

The dashboard's own composite modules, one layer above
:mod:`~simple_steps_core.streamlit.components`:

* :mod:`.draft` — :class:`DraftStep` / :class:`DraftWorkflow`, the editing model
  that bridges half-finished UI state to the frozen domain objects. Pure Python.
* :mod:`.step_card` — one step's card: controls, Operation panel, Result panel.
* :mod:`.toolbar` — step selector, run controls, tool palette, import/export.

Where ``components`` renders *one library object*, a panel composes several into
a piece of the dashboard. Both follow the same rules: ``st`` is a parameter,
state arrives explicitly, and every action is a caller-supplied ``on_…``
callback, so no panel touches ``st.session_state``.
"""

from __future__ import annotations

from .draft import DraftStep, DraftWorkflow
from .step_card import (
    STEP_VIEWS,
    render_arguments,
    render_operation_panel,
    render_result_panel,
    render_staged,
    render_step_card,
    render_step_controls,
)
from .toolbar import (
    render_problems,
    render_run_controls,
    render_tool_palette,
    render_validation,
    render_workflow_io,
    render_workflow_toolbar,
)

__all__ = [
    # state
    "DraftStep", "DraftWorkflow",
    # step card
    "render_step_card", "render_step_controls", "render_operation_panel",
    "render_arguments", "render_result_panel", "render_staged",
    "STEP_VIEWS",
    # toolbar / sidebar
    "render_workflow_toolbar", "render_run_controls", "render_tool_palette",
    "render_workflow_io", "render_problems", "render_validation",
]
