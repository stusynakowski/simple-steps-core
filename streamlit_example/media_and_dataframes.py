"""Every data kind the dashboard handles, in one pipeline.

Run it::

    python -m pip install -e ".[dashboard]"
    python streamlit_example/media_and_dataframes.py

Four kinds of value, each rendered by the component it deserves:

    scalars      int / float / str          a one-cell shaded table
    dataframes   pandas DataFrame           a table — and orchestrations keep it one
    media        MediaAsset (image/video)   the picture, or a contact sheet
    sources      Collection                 a window of items plus a version stamp

Two things are worth watching in the grid.

**A frame stays a frame.** ``filter`` over a DataFrame returns a DataFrame
(dtypes and index intact), and ``group`` returns one frame per bucket, shown as
tabs. Each row reaches your tool as a plain ``dict``, so no tool here imports
pandas to read a row.

**A fan-out over images shows the images.** ``map`` with ``thumbnail`` produces
a contact sheet rather than a column of file paths, because every successful
item is a :class:`MediaAsset`.

Images are held by *handle*: the bytes live in the media store (set below), and
a step holds a small record naming the file. Mapping over a folder of photos
costs a handle per photo, not a decoded image per photo.

Build a pipeline in the dashboard by picking a tool, then saying where its data
comes **from** and how to **apply** it (`once`, `map`, `filter`, `expand`,
`reduce`, `group`).
"""

from pathlib import Path

import pandas as pd
from PIL import Image

from simple_steps_core import (
    Collection,
    ListCollection,
    MediaAsset,
    MediaStore,
    Resource,
    ResourceSpec,
    register_tool,
    set_media_store,
)
from simple_steps_core.streamlit import Dashboard

HERE = Path(__file__).parent
PHOTOS = HERE / "sample_photos"

# Where produced images land. A durable directory means a reloaded session can
# still find its pictures; the default is a temp dir that the OS may clean.
set_media_store(MediaStore(HERE / "media_store"))


def _make_sample_photos() -> None:
    """Three solid-color images, so the example runs with no assets to download.

    Called at import time, because under ``streamlit run`` this module is
    imported rather than executed as ``__main__``.
    """
    PHOTOS.mkdir(exist_ok=True)
    for name, size, color in [
        ("wide.png", (240, 120), "#c0392b"),
        ("tall.png", (120, 240), "#27ae60"),
        ("square.png", (180, 180), "#2980b9"),
    ]:
        if not (PHOTOS / name).exists():
            Image.new("RGB", size, color).save(PHOTOS / name)


_make_sample_photos()


# ── 1. A standard resource: the photo directory, with its own tools ───────
# Bound tools are named `photos-<tool>` and may use this resource and no other.
photos = ResourceSpec(
    "photos",
    factory=lambda: PHOTOS,
    check=lambda directory: directory.exists(),
    description="A directory of images.",
)


@photos.tool("load", description="Every image in the directory (a lazy source).")
def load(pattern: str = "*.png", directory=Resource()) -> Collection:
    assets = [MediaAsset.from_path(p) for p in sorted(directory.glob(pattern))]
    # A version stamp lets a caller tell "nothing changed" from "not looked yet".
    newest = max((p.stat().st_mtime_ns for p in directory.glob(pattern)), default=0)
    return ListCollection(items=assets, version=f"mtime:{newest}")


@photos.tool("thumbnail", description="Shrink one image (use with map).")
def thumbnail(image: MediaAsset, size: int = 96, directory=Resource()) -> MediaAsset:
    picture = image.open()
    picture.thumbnail((size, size))
    return MediaAsset.from_image(picture, name=f"thumb-{image.name}")


# ── 2. Unbound tools: they need no resource ───────────────────────────────
@register_tool("orientation", description="landscape / portrait / square (use with group).")
def orientation(image: MediaAsset) -> str:
    picture = image.open()
    width, height = picture.size
    return "landscape" if width > height else "portrait" if height > width else "square"


@register_tool("pixel_count", description="How many pixels an image has (use with map).")
def pixel_count(image: MediaAsset) -> int:
    width, height = image.open().size
    return width * height


# ── 3. A dataframe, and the orchestrations that keep it one ───────────────
@register_tool("load_sales", description="A small sales table.", type="dataframe")
def load_sales(rows: int = 6) -> pd.DataFrame:
    data = {
        "region": ["east", "west", "east", "north", "west", "east"][:rows],
        "amount": [10, 20, 30, 40, 50, 60][:rows],
        "rep": ["ana", "bo", "cy", "di", "ed", "fay"][:rows],
    }
    return pd.DataFrame(data)


@register_tool("big_sale", description="Keep rows over a threshold (use with filter).")
def big_sale(row: dict, threshold: float = 25) -> bool:
    return row["amount"] > threshold


@register_tool("region_of", description="A row's region (use with group).")
def region_of(row: dict) -> str:
    return row["region"]


@register_tool("running_total", description="Sum the amounts (use with reduce).")
def running_total(accumulator, row: dict) -> float:
    running = accumulator["amount"] if isinstance(accumulator, dict) else accumulator
    return float(running) + float(row["amount"])


# ── 4. Plain scalars, to show the ordinary path still works ───────────────
@register_tool("describe", description="A one-line summary of any value.")
def describe(value: object) -> str:
    return f"{type(value).__name__}: {value!r}"[:200]


# The dashboard reads these two module-level names.
CONFIG = {"title": "Media & DataFrames"}
RESOURCES = [photos]          # a list of specs, or {name: factory | value}

if __name__ == "__main__":
    Dashboard().run()
