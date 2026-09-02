"""Optional Streamlit dashboard for building and running workflows.

Import stays cheap: Streamlit itself is only imported when the dashboard runs.
"""

from .dashboard import main, render_tool_form

__all__ = ["main", "render_tool_form"]
