"""
Media components — images and video in the grid
===============================================

A step that produces a :class:`~simple_steps_core.MediaAsset` should *show the
picture*, and a fan-out over a folder of photos should show a contact sheet,
not a column of file paths.

Three renderers, following the package conventions (``st`` first, required
``key``, no session state, no mutation):

* :func:`render_media_asset` — one image or clip, with its name and size.
* :func:`render_media_grid`  — many assets as a wrapped thumbnail grid.
* :func:`render_missing_media` — the honest empty state for a handle whose
  file is gone, which happens when a snapshot is reloaded on another machine
  or the media store was a temp directory that has since been cleaned.

Assets are passed to Streamlit **by path**, never decoded here: ``st.image``
and ``st.video`` read the file themselves, so rendering 200 thumbnails does not
mean decoding 200 images in this process.
"""

from __future__ import annotations

from typing import Any, Sequence

from simple_steps_core import MediaAsset

__all__ = ["render_media_asset", "render_media_grid", "render_missing_media"]

#: Thumbnails per row in a contact sheet.
DEFAULT_GRID_COLUMNS = 4


def _caption(asset: MediaAsset) -> str:
    """A one-line label: name, then dimensions when the asset knows them."""
    label = asset.name or asset.path.rsplit("/", 1)[-1]
    if asset.width and asset.height:
        return f"{label} · {asset.width}×{asset.height}"
    return label


def render_missing_media(st, asset: MediaAsset, *, key: str) -> None:
    """Say plainly that the bytes are gone, and where they were expected."""
    st.warning(
        f":material/broken_image: `{asset.name or 'asset'}` — file not found at "
        f"`{asset.path}`. The media store may have been a temp directory; set a "
        f"durable one with `set_media_store(...)`."
    )


def render_media_asset(
    st, asset: MediaAsset, *, key: str, width: Any = "stretch"
) -> None:
    """One media asset: the image, the clip, or a caption for anything else."""
    if not asset.exists():
        render_missing_media(st, asset, key=key)
        return
    if asset.is_image:
        st.image(asset.path, caption=_caption(asset), width=width)
        return
    if asset.is_video:
        st.video(asset.path)
        st.caption(_caption(asset))
        return
    # A handle to something that is neither: name it rather than guess.
    size = asset.size_bytes
    suffix = f" · {size:,} bytes" if size is not None else ""
    st.caption(f":material/description: {_caption(asset)} · `{asset.media_type}`{suffix}")


def render_media_grid(
    st,
    assets: Sequence[MediaAsset],
    *,
    key: str,
    columns: int = DEFAULT_GRID_COLUMNS,
    limit: int = 48,
) -> None:
    """A contact sheet: the result of mapping an operation over many images.

    Shows at most *limit* assets and says how many were withheld, so a fan-out
    over a thousand photos stays a usable cell rather than an endless scroll.
    """
    assets = list(assets)
    if not assets:
        st.caption("no media")
        return

    shown = assets[:limit]
    per_row = max(1, int(columns))
    for start in range(0, len(shown), per_row):
        row = shown[start : start + per_row]
        cells = st.columns(per_row)
        for offset, (cell, asset) in enumerate(zip(cells, row)):
            with cell:
                render_media_asset(st_of(cell), asset, key=f"{key}_{start + offset}")

    withheld = len(assets) - len(shown)
    if withheld > 0:
        st.caption(f"… and {withheld} more ({len(assets)} total)")


def st_of(column: Any) -> Any:
    """The drawing surface for a column.

    ``st.columns`` returns objects that are themselves drawing surfaces, so
    this is the identity — it exists to name the intent at the call site and to
    give a fake ``st`` in tests one obvious place to hook.
    """
    return column
