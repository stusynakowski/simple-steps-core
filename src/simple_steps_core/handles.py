"""Bulky cells on disk, a ledger in memory (plan P7d, saving.md S-D6).

With ``Kernel(catalog, spill_over=n)``, when a step runs, each array, Pillow
image or Plotly figure in its output of ``n`` bytes or more is written once to
the kernel's store, a folder of files named by their content (the same files a
saved session's ``media/`` holds), and its cell holds a :class:`MediaHandle`:
the file's name, a summary (``"RGB image 64×64"``) and the value's data
version. Memory holds the ledger; the disk holds the bytes.

**A handle is never what a tool gets.** Where rows are made for a tool, a
``table`` tool's grid and a picked argument, a handle gives its value, loaded
then (:func:`values_of`). The view and :meth:`Kernel.cell` show its summary;
:meth:`Kernel.value` loads it. Its data version is its value's, so versions,
run keys and staleness are the same whether a value is in memory or on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


class MediaHandle:
    """A cell's value kept on disk: what the cell holds instead of it. *name*
    is its file's path under *folder*, the store's (or session's) root:
    ``data/<step>/files/<hash>.<ext>``."""

    __slots__ = ("name", "ref", "summary", "token", "folder")

    def __init__(self, name: str, ref: dict, summary: str, token: Any, folder: Path):
        self.name, self.ref, self.summary, self.token = name, ref, summary, token
        self.folder = Path(folder)

    def load(self) -> Any:
        """The value, read from its file."""
        from .saving import _decode_media
        return _decode_media(self.ref, (self.folder / self.name).read_bytes())

    @property
    def kind(self) -> str:
        return self.ref["kind"]

    def __repr__(self) -> str:
        return f"<{self.summary}, on disk>"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, MediaHandle) and other.name == self.name

    def __hash__(self) -> int:
        return hash(self.name)


class Spill:
    """A kernel's store and its threshold: values of *over* bytes or more go
    under *folder*, laid out as a session folder (``data/<step>/files/``), so
    a session saved into it copies nothing. One per kernel (no state at module
    level)."""

    def __init__(self, folder: Path, over: int):
        from .saving import Media
        self.over = int(over)
        self.media = Media(Path(folder))
        self._folders: dict[str, str] = {}       # step → data/<its folder>
        self._taken: set[str] = set()

    @property
    def folder(self) -> Path:
        return self.media.root

    def _step_folder(self, step: str) -> str:
        if step not in self._folders:
            from .saving import _file_stem
            self._folders[step] = f"data/{_file_stem(step, self._taken)}"
        return self._folders[step]

    def handle(self, value: Any, step: str = "_") -> Any:
        """*value*, or a handle to it when it is bulky media; a new file goes
        into *step*'s folder."""
        size = _size(value)
        if size is None or size < self.over:
            return value
        from .output import _stable
        token = _stable(value)
        self.media.at(self._step_folder(step))
        ref = self.media.put(value)
        return MediaHandle(ref["$media"], ref, _summary(value), token, self.folder)

    def spill(self, frame: pd.DataFrame, step: str = "_") -> pd.DataFrame:
        """*frame* with its bulky cells as handles: the same frame when none are."""
        out = None
        for position, column in enumerate(frame.columns):
            series = frame.iloc[:, position]
            if series.dtype != object:
                continue
            values = [self.handle(v, step) for v in series]
            if any(a is not b for a, b in zip(values, series)):
                out = frame.copy() if out is None else out
                out.isetitem(position, pd.Series(values, index=frame.index, dtype=object))
        return frame if out is None else out


def _size(value: Any) -> int | None:
    """A media value's size in bytes, roughly; None for anything else."""
    import sys
    np = sys.modules.get("numpy")
    if np is not None and isinstance(value, np.ndarray) and value.dtype.kind != "O":
        return int(value.nbytes)
    pil = sys.modules.get("PIL.Image")
    if pil is not None and isinstance(value, pil.Image):
        return value.width * value.height * len(value.getbands())
    figures = sys.modules.get("plotly.basedatatypes")
    if figures is not None and isinstance(value, figures.BaseFigure):
        return len(value.to_json())
    return None


def _summary(value: Any) -> str:
    import sys
    np = sys.modules.get("numpy")
    if np is not None and isinstance(value, np.ndarray):
        return f"{value.dtype} array {'×'.join(map(str, value.shape)) or 'scalar'}"
    pil = sys.modules.get("PIL.Image")
    if pil is not None and isinstance(value, pil.Image):
        return f"{value.mode} image {value.width}×{value.height}"
    traces = len(getattr(value, "data", ()) or ())
    return f"figure · {traces} trace{'s' if traces != 1 else ''}"


def values_of(obj: Any) -> Any:
    """*obj* with every handle in it as its value: a frame (only the object
    columns that hold one are copied), a list, a tuple, a dict, or a value."""
    if isinstance(obj, MediaHandle):
        return obj.load()
    if isinstance(obj, pd.DataFrame):
        out = None
        for position in range(obj.shape[1]):
            series = obj.iloc[:, position]
            if series.dtype == object and any(isinstance(v, MediaHandle) for v in series):
                out = obj.copy() if out is None else out
                out.isetitem(position, pd.Series([values_of(v) for v in series],
                                                 index=obj.index, dtype=object))
        return obj if out is None else out
    if isinstance(obj, pd.Series):
        if obj.dtype == object and any(isinstance(v, MediaHandle) for v in obj):
            return pd.Series([values_of(v) for v in obj], index=obj.index,
                             name=obj.name, dtype=object)
        return obj
    if isinstance(obj, list):
        return [values_of(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(values_of(v) for v in obj)
    if isinstance(obj, dict):
        return {k: values_of(v) for k, v in obj.items()}
    return obj
