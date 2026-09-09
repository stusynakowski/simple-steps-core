from __future__ import annotations

import contextlib
import os
from typing import Iterator

import streamlit as st
import streamlit.components.v1 as components
from streamlit.delta_generator import DeltaGenerator

# Set to False while developing the frontend against `npm start` (localhost:3001).
_RELEASE = True

_COMPONENT_NAME = "right_sidebar_toggle"

if not _RELEASE:
    _toggle_component = components.declare_component(
        _COMPONENT_NAME,
        url="http://localhost:3001",
    )
else:
    _parent_dir = os.path.dirname(os.path.abspath(__file__))
    _build_dir = os.path.join(_parent_dir, "frontend", "build")
    _toggle_component = components.declare_component(_COMPONENT_NAME, path=_build_dir)


def _toggle_handle(
    collapsed: bool,
    key: str,
    icon: str | None = None,
    collapse_icon: str | None = None,
    expand_icon: str | None = None,
) -> bool:
    """Renders the collapse/expand handle and returns the resulting collapsed state."""
    return _toggle_component(
        collapsed=collapsed,
        icon=icon,
        collapseIcon=collapse_icon,
        expandIcon=expand_icon,
        key=key,
        default=collapsed,
    )


def _inject_css(container_key: str, toggle_key: str, width: int, collapsed: bool) -> None:
    panel_offset = f"{width}px" if collapsed else "0px"
    toggle_offset = "0px" if collapsed else f"{width}px"
    st.markdown(
        f"""
        <style>
        .st-key-{container_key} {{
            position: fixed;
            top: 0;
            right: 0;
            height: 100vh;
            width: {width}px;
            transform: translateX({panel_offset});
            transition: transform 300ms ease-in-out;
            background-color: var(--right-sidebar-bg, #f0f2f6);
            border-left: 1px solid rgba(128, 128, 128, 0.35);
            padding: 3.5rem 1rem 1rem 1rem;
            overflow-y: auto;
            z-index: 999990;
        }}
        /* Kept outside the collapsing panel so it stays reachable in both states.
           Streamlit sets an inline width on this block for layout purposes; without
           overriding it here, the fixed-position wrapper stretches across most of
           the page and invisibly blocks clicks/hover on everything beneath it
           (including the native left sidebar's own collapse button). */
        .st-key-{toggle_key} {{
            position: fixed;
            top: 3rem;
            right: {toggle_offset};
            width: 40px !important;
            overflow: hidden;
            transition: right 300ms ease-in-out;
            z-index: 999991;
        }}
        /* Streamlit sizes nested blocks/iframes with inline pixel widths that would
           otherwise overflow the 40px wrapper above. */
        .st-key-{toggle_key} [data-testid="stElementContainer"],
        .st-key-{toggle_key} iframe {{
            width: 40px !important;
        }}
        /* Compatible with both the legacy `.main` layout and the newer `stMain` testid. */
        div[data-testid="stAppViewContainer"] > .main,
        section[data-testid="stMain"] {{
            margin-right: {"0px" if collapsed else f"{width}px"} !important;
            transition: margin-right 300ms ease-in-out;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


@contextlib.contextmanager
def right_sidebar(
    key: str = "right_sidebar",
    width: int = 300,
    icon: str | None = None,
    collapse_icon: str | None = None,
    expand_icon: str | None = None,
    initial_collapsed: bool = False,
) -> Iterator[DeltaGenerator]:
    """A collapsible sidebar docked to the right edge of the app.

    Mirrors the usage of ``st.sidebar``::

        with right_sidebar():
            st.header("Notes")
            st.text_area("Write something")

    Args:
        key: Unique key for the sidebar. Use a different key if you render
            more than one right sidebar in the same app.
        width: Width of the sidebar in pixels.
        icon: Icon shown on the toggle handle. Accepts an emoji (``"🤖"``),
            a short text string, or a Streamlit-style Material icon shortcode
            (``":material/smart_toy:"``). Overrides the default chevron.
            Ignored per-state where ``collapse_icon``/``expand_icon`` are set.
        collapse_icon: Icon shown when the sidebar is expanded (i.e. the icon
            that collapses it). Falls back to ``icon``.
        expand_icon: Icon shown when the sidebar is collapsed (i.e. the icon
            that expands it). Falls back to ``icon``.
        initial_collapsed: Whether the sidebar starts collapsed on first
            render. After the first render, the collapsed state is tracked in
            ``st.session_state`` under ``f"_{key}_collapsed"``.
    """
    state_key = f"_{key}_collapsed"
    toggle_key = f"{key}_toggle"
    collapsed = st.session_state.setdefault(state_key, initial_collapsed)

    _inject_css(key, toggle_key, width, collapsed)

    with st.container(key=toggle_key):
        new_collapsed = _toggle_handle(
            collapsed,
            key=f"{key}_toggle_component",
            icon=icon,
            collapse_icon=collapse_icon,
            expand_icon=expand_icon,
        )
    if new_collapsed != collapsed:
        st.session_state[state_key] = new_collapsed
        st.rerun()

    container = st.container(key=key)
    with container:
        yield container
