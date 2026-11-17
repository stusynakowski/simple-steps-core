"""Saving a session as a folder, and loading it back (plan P1c; docs/design/saving.md).

A session is a folder, one sub-folder per step::

    <folder>/
      workflow.json            the workflow; each step names its folder
      report.json              what the last save couldn't keep exactly
      data/
        <step>/
          table.parquet        its table: the data given to it, or its output
                               (lineage and row ids included)
          states.parquet       with outputs: a state per cell
          meta.json            with outputs: its record (run key, what it read…)
          files/<hash>.<ext>   the arrays (.npy), images (.png, .tiff) and
                               Plotly figures (.json) its cells hold, named by
                               their content

A file is stored once: a later step holding the same value (a filtered copy
carrying an image) names the earlier step's file. A kernel's store
(``Kernel(store=…)``) has the same layout, so saving into it copies nothing.

**A save is exact, or says where it isn't.** Each column is written the
plainest way that reads back exactly: a typed Parquet column when its values
round-trip through Arrow unchanged, else a text column of *tagged JSON*, which
names every value's type (a tuple apart from a list, ``1`` apart from ``1.0``
and ``True``, ``NaN`` apart from ``None``). A value neither can hold (an
arbitrary object) is not saved, and is reported. After writing, the step is
read back and its data version compared. **Loading runs no code**: nothing is
unpickled or imported, and a step whose data is missing, changed or wasn't
saved loads ``invalid``, naming why, instead of raising.
"""

from __future__ import annotations

import base64
import datetime as dt
import decimal
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

#: The file names Windows reserves, whatever the extension.
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
             *(f"lpt{i}" for i in range(1, 10))}


class NotSaved(Exception):
    """A value the tagged form can't hold: its type's name is the message."""


# ── values: tagged JSON, exact for every type core can name ──────────────
def tag(value: Any, media: "Media | None" = None) -> Any:
    """*value* as JSON that names its type, so :func:`untag` gives it back
    exactly. An array, an image or a figure goes to *media*, the JSON naming
    its file. Raises :class:`NotSaved` for a value it can't hold."""
    if media is not None:
        ref = media.put(value)
        if ref is not None:
            return ref
    if value is None:
        return None
    if value is pd.NA:
        return {"$na": 1}
    if value is pd.NaT:
        return {"$nat": 1}
    if isinstance(value, np.generic):
        if isinstance(value, (np.datetime64, np.timedelta64)):
            # its count of units (NaT included), which its text can't always give back
            return {"$np": value.dtype.str, "v": int(value.view("int64"))}
        if isinstance(value, np.void) or value.dtype.kind in "OSUV":
            raise NotSaved(f"numpy {value.dtype}")
        return {"$np": value.dtype.str, "v": tag(value.item(), media)}
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if abs(value) < 2 ** 53 else {"$int": str(value)}
    if isinstance(value, float):
        return value if math.isfinite(value) else {"$float": repr(value)}
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        out = {"$bytes": base64.b64encode(bytes(value)).decode("ascii")}
        return {**out, "mutable": 1} if isinstance(value, bytearray) else out
    if isinstance(value, complex):
        return {"$complex": [tag(value.real, media), tag(value.imag, media)]}
    if isinstance(value, decimal.Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, pd.Timestamp):
        return {"$timestamp": value.isoformat(), "unit": value.unit,
                "tz": str(value.tz) if value.tz is not None else None}
    if isinstance(value, pd.Timedelta):
        return {"$pdtimedelta": int(value.value), "unit": value.unit}
    if isinstance(value, dt.datetime):
        # fold: which of a repeated hour (a clock set back); isoformat drops it
        return {"$datetime": value.isoformat(), "tz": getattr(value.tzinfo, "key", None),
                "fold": value.fold}
    if isinstance(value, dt.date):
        return {"$date": value.isoformat()}
    if isinstance(value, dt.time):
        return {"$time": value.isoformat(), "fold": value.fold}
    if isinstance(value, dt.timedelta):
        return {"$timedelta": [value.days, value.seconds, value.microseconds]}
    if type(value) is tuple:
        return {"$tuple": [tag(v, media) for v in value]}
    if type(value) is list:
        return [tag(v, media) for v in value]
    if type(value) is dict:
        return {"$dict": [[tag(k, media), tag(v, media)] for k, v in value.items()]}
    if type(value) in (set, frozenset):
        return {f"${type(value).__name__}": [tag(v, media) for v in value]}
    raise NotSaved(type(value).__name__)


def untag(obj: Any, media: "Media | None" = None) -> Any:
    """The value :func:`tag` wrote; files from *media*."""
    if isinstance(obj, list):
        return [untag(v, media) for v in obj]
    if not isinstance(obj, dict):
        return obj
    (key, payload), = [(k, v) for k, v in obj.items() if k.startswith("$")]
    if key == "$media":
        if media is None:
            raise ValueError("a saved value names a media file, but no session folder was given")
        return media.get(obj)
    if key == "$na":
        return pd.NA
    if key == "$nat":
        return pd.NaT
    if key == "$np":
        dtype = np.dtype(payload)
        if dtype.kind in "mM":
            return np.array(obj["v"], dtype="int64").view(dtype)[()]
        return dtype.type(untag(obj["v"], media))
    if key == "$int":
        return int(payload)
    if key == "$float":
        return float(payload)
    if key == "$bytes":
        raw = base64.b64decode(payload)
        return bytearray(raw) if obj.get("mutable") else raw
    if key == "$complex":
        return complex(untag(payload[0], media), untag(payload[1], media))
    if key == "$decimal":
        return decimal.Decimal(payload)
    if key == "$timestamp":
        stamp = pd.Timestamp(payload)
        if obj.get("tz") is not None:
            stamp = stamp.tz_convert(obj["tz"])
        return stamp.as_unit(obj["unit"]) if obj.get("unit") else stamp
    if key == "$pdtimedelta":
        return pd.Timedelta(payload, unit="ns").as_unit(obj.get("unit") or "ns")
    if key == "$datetime":
        when = dt.datetime.fromisoformat(payload)
        if obj.get("tz"):
            from zoneinfo import ZoneInfo
            when = when.replace(tzinfo=ZoneInfo(obj["tz"]))
        return when.replace(fold=obj.get("fold", 0))
    if key == "$date":
        return dt.date.fromisoformat(payload)
    if key == "$time":
        return dt.time.fromisoformat(payload).replace(fold=obj.get("fold", 0))
    if key == "$timedelta":
        return dt.timedelta(days=payload[0], seconds=payload[1], microseconds=payload[2])
    if key == "$tuple":
        return tuple(untag(v, media) for v in payload)
    if key == "$dict":
        return {untag(k, media): untag(v, media) for k, v in payload}
    if key == "$set":
        return {untag(v, media) for v in payload}
    if key == "$frozenset":
        return frozenset(untag(v, media) for v in payload)
    raise ValueError(f"unknown tag {key!r} in a saved value")


def _same(a: list, b: list) -> bool:
    """Equal value for value, types included (``1`` is not ``1.0``)."""
    try:
        return json.dumps([tag(v) for v in a], sort_keys=True) == \
            json.dumps([tag(v) for v in b], sort_keys=True)
    except NotSaved:
        return False


# ── media: arrays, images and figures, each a file named by its content ──
_PNG_MODES = {"1", "L", "LA", "P", "RGB", "RGBA", "I;16"}


class Media:
    """The files of a session folder (or a kernel's store) under *root*: each
    array, Pillow image or Plotly figure written once, named by a hash of its
    bytes, in the folder of the step that first holds it,
    ``data/<step>/files/``; a later holder names that file. Arrays as ``.npy``
    (never pickled), images as PNG (TIFF for the modes PNG can't hold: ``I``,
    ``F``, ``CMYK``, …), figures as Plotly's JSON. An image is read back when
    written and must give the value back, or it isn't saved. A library is used
    only when the value is already one of its objects."""

    def __init__(self, root: Path, *, lazy: bool = False):
        # *lazy*: reading gives handles to the files, not the values (P7d)
        self.root = Path(root)
        self.lazy = lazy
        self.step = "data/_"                 # where new files go: data/<step>
        self.written: set[str] = set()       # files this save or store names
        self.by_name: dict[str, str] = {}    # a file's name → where it is

    def at(self, step_folder: str) -> None:
        """New files go into *step_folder* (``data/<step>``) from now on."""
        self.step = step_folder

    def _place(self, name: str) -> str:
        """Where the file *name* is, or goes: the first holder's folder."""
        if name not in self.by_name:
            self.by_name[name] = f"{self.step}/files/{name}"
        return self.by_name[name]

    def put(self, value: Any) -> dict | None:
        """The reference to *value*'s file, or None if it isn't a media value.
        A handle's file is copied as it is, unless it is here already; its
        value isn't loaded."""
        from .handles import MediaHandle
        if isinstance(value, MediaHandle):
            source = value.folder / value.name
            name = Path(value.name).name
            if value.folder.resolve() == self.root.resolve() and source.is_file() \
                    and name not in self.by_name:
                self.by_name[name] = value.name          # in place: nothing to copy
            path = self._place(name)
            target = self.root / path
            if not target.is_file():
                import shutil
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            self.written.add(path)
            return {**value.ref, "$media": path, "token": tag(value.token), "summary": value.summary}
        encoded = _encode_media(value)
        if encoded is None:
            return None
        kind, ext, raw, extra = encoded
        import hashlib
        path = self._place(f"{hashlib.sha256(raw).hexdigest()[:24]}.{ext}")
        target = self.root / path
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        self.written.add(path)
        return {"$media": path, "kind": kind, **extra}

    def path_of(self, ref: dict) -> Path:
        where = ref["$media"]
        # a bare name is a file of the earlier layout, media/<name>
        return self.root / (where if "/" in where else f"media/{where}")

    def get(self, ref: dict) -> Any:
        source = self.path_of(ref)
        if self.lazy and "token" in ref:
            from .handles import MediaHandle
            if not source.is_file():
                raise OSError(f"{ref['$media']} is missing")
            core = {k: v for k, v in ref.items() if k not in ("token", "summary")}
            return MediaHandle(str(source.relative_to(self.root)), core,
                               ref.get("summary") or ref["kind"], untag(ref["token"]), self.root)
        return _decode_media(ref, source.read_bytes())


def _encode_media(value: Any):
    """``(kind, extension, bytes, extra)`` for a media value, else None."""
    import io
    import sys
    if isinstance(value, np.ndarray):
        if value.dtype.kind == "O":
            raise NotSaved("ndarray of Python objects")
        buffer = io.BytesIO()
        np.save(buffer, value, allow_pickle=False)
        return "array", "npy", buffer.getvalue(), {}
    pil = sys.modules.get("PIL.Image")
    if pil is not None and isinstance(value, pil.Image):
        image_format = "PNG" if value.mode in _PNG_MODES else "TIFF"
        buffer = io.BytesIO()
        try:
            value.save(buffer, format=image_format)
        except (OSError, ValueError, KeyError):
            raise NotSaved(f"image of mode {value.mode}") from None
        extra = {"format": value.format, "info": tag(dict(value.info))}
        back = _decode_media({"kind": "image", **extra}, buffer.getvalue())
        if back.mode != value.mode or back.size != value.size or back.tobytes() != value.tobytes():
            raise NotSaved(f"image of mode {value.mode}")
        return "image", image_format.lower(), buffer.getvalue(), extra
    figures = sys.modules.get("plotly.basedatatypes")
    if figures is not None and isinstance(value, figures.BaseFigure):
        return "figure", "json", value.to_json().encode("utf-8"), {"class": type(value).__name__}
    return None


def _decode_media(ref: dict, raw: bytes) -> Any:
    import io
    kind = ref["kind"]
    if kind == "array":
        return np.load(io.BytesIO(raw), allow_pickle=False)
    if kind == "image":
        from PIL import Image
        opened = Image.open(io.BytesIO(raw))
        opened.load()
        image = opened.copy()                   # a plain Image, as a tool makes one
        image.info = untag(ref.get("info") or {"$dict": []})
        image.format = ref.get("format")
        return image
    if kind == "figure":
        import plotly.graph_objects as go
        blob = _arrays_back(json.loads(raw.decode("utf-8")))
        cls = go.FigureWidget if ref.get("class") == "FigureWidget" else go.Figure
        try:
            return cls(blob)
        except ImportError:                     # a widget needs ipywidgets
            return go.Figure(blob)
    raise ValueError(f"unknown media kind {kind!r}")


def _arrays_back(obj: Any) -> Any:
    """A figure's JSON with Plotly's encoded arrays (``{dtype, bdata}``) back
    as numpy arrays, as the figure held them (S-D3)."""
    if isinstance(obj, dict):
        if set(obj) <= {"dtype", "bdata", "shape"} and {"dtype", "bdata"} <= set(obj):
            array = np.frombuffer(base64.b64decode(obj["bdata"]), dtype=obj["dtype"]).copy()
            shape = obj.get("shape")
            if shape:
                array = array.reshape([int(s) for s in str(shape).split(",")])
            return array
        return {k: _arrays_back(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_arrays_back(v) for v in obj]
    return obj


# ── a table: one Parquet file, each column the plainest exact way ────────
def _pyarrow():
    try:
        import pyarrow
        import pyarrow.parquet
    except ImportError:                                # pragma: no cover
        raise ImportError("saving a session needs pyarrow: pip install pyarrow") from None
    return pyarrow, pyarrow.parquet


def _write_column(values: list, media: "Media | None" = None):
    """``(array, how, why)``: typed when Arrow gives *values* back unchanged,
    else tagged JSON text (media values as files); ``"not_saved"`` with the
    reason if neither can."""
    pa, pq = _pyarrow()
    try:
        array = pa.array(values)
        # through Parquet itself, not only Arrow: a type Parquet can't write
        # (a struct of no fields: a column of {}) or would change goes tagged
        import io
        buffer = io.BytesIO()
        pq.write_table(pa.table({"c": array}), buffer)
        back = pq.read_table(io.BytesIO(buffer.getvalue())).column(0)
        if _same(back.to_pylist(), values):
            return array, "typed", None
    except Exception:
        pass
    try:
        return pa.array([json.dumps(tag(v, media)) for v in values], pa.string()), "tagged", None
    except NotSaved as exc:
        return pa.nulls(len(values), pa.string()), "not_saved", f"a {exc} can't be saved"


def _read_column(array, how: str, media: "Media | None" = None) -> list:
    values = array.to_pylist()
    if how == "tagged":
        return [untag(json.loads(v), media) for v in values]
    return values


def _restore(values: list, dtype: str, index=None) -> pd.Series:
    try:
        return pd.Series(values, index=index, dtype=dtype)
    except (TypeError, ValueError):
        return pd.Series(values, index=index, dtype=object)


def write_frame(frame: pd.DataFrame, path: Path, media: "Media | None" = None) -> dict:
    """Write *frame* to *path*; the manifest that reads it back. Column names
    and the index travel in the manifest, tagged, so any name round-trips."""
    pa, pq = _pyarrow()
    if isinstance(frame.columns, pd.MultiIndex) or isinstance(frame.index, pd.MultiIndex):
        return {"not_saved": {"*": "a table with several header or index levels can't be saved"}}
    if not frame.columns.is_unique:
        return {"not_saved": {"*": "a table whose column names repeat can't be saved"}}
    arrays, names, columns, not_saved = [], [], [], {}
    for position, name in enumerate(frame.columns):
        series = frame.iloc[:, position]
        array, how, why = _write_column(series.tolist(), media)
        arrays.append(array)
        names.append(str(name) if isinstance(name, str) and how == "typed"
                     and not str(name).startswith("__") else f"__c{position}")
        columns.append({"name": tag(name), "dtype": str(series.dtype), "how": how})
        if why:
            not_saved[str(name)] = why
    index = frame.index
    range_index = isinstance(index, pd.RangeIndex) and index.start == 0 and index.step == 1
    entry = {"range": len(index)} if range_index else None
    if entry is None:
        array, how, why = _write_column(index.tolist(), media)
        arrays.append(array)
        names.append("__index__")
        entry = {"dtype": str(index.dtype), "how": how}
        if why:
            not_saved["(the index)"] = why
    entry["name"] = tag(index.name)
    # a typed column keeps its name in the file, so the file opens as itself
    if len(set(names)) != len(names):
        names = [f"__c{i}" for i in range(len(columns))] + names[len(columns):]
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(arrays, names=names), path)
    manifest = {"file_columns": names, "columns": columns, "index": entry}
    if not_saved:
        manifest["not_saved"] = not_saved
    return manifest


def read_frame(path: Path, manifest: dict, media: "Media | None" = None) -> pd.DataFrame:
    """The table :func:`write_frame` wrote."""
    _, pq = _pyarrow()
    table = pq.read_table(path)
    columns = manifest["columns"]
    index_entry = manifest["index"]
    if "range" in index_entry:
        index = pd.RangeIndex(index_entry["range"])
    else:
        values = _read_column(table.column(len(columns)), index_entry["how"], media)
        index = pd.Index(_restore(values, index_entry["dtype"]))
    index.name = untag(index_entry.get("name"))
    data = {}
    for position, column in enumerate(columns):
        values = _read_column(table.column(position), column["how"], media)
        data[position] = _restore(values, column["dtype"], index)
    frame = pd.DataFrame(data, index=index)
    frame.columns = [untag(c["name"]) for c in columns]
    return frame


# ── file names ────────────────────────────────────────────────────────────
def _file_stem(step: str, taken: set[str]) -> str:
    """A safe file name for *step*: letters, digits, ``_`` and ``-`` kept,
    anything else written ``%XX``; never a name Windows reserves; unique
    ignoring case. ``workflow.json`` maps each step to its file."""
    stem = re.sub(r"[^A-Za-z0-9_\-]", lambda m: "".join(
        f"%{b:02X}" for b in m.group(0).encode("utf-8")), step) or "%"
    if stem.split(".")[0].lower() in _RESERVED:
        stem = "_" + stem
    candidate, n = stem, 2
    while candidate.lower() in taken:
        candidate, n = f"{stem}~{n}", n + 1
    taken.add(candidate.lower())
    return candidate


def _write_json(path: Path, blob: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=1))
    os.replace(tmp, path)


# ── a kernel ──────────────────────────────────────────────────────────────
#: The files this core writes in a session folder, and only these, are
#: removed when nothing names them any more.
_OWN_FILE = re.compile(r"data/[^/]+/(table\.parquet|states\.parquet|meta\.json|"
                       r"files/[0-9a-f]{24}\.(npy|png|tiff|json))"
                       r"|data/[^/]+\.parquet|outputs/[^/]+/(data|states)\.parquet"
                       r"|outputs/[^/]+/meta\.json|media/[0-9a-f]{24}\.(npy|png|tiff|json)")


def save(kernel, folder, *, outputs: bool = False) -> dict:
    """Save *kernel* as a session folder; the report of what wasn't exact."""
    from .output import _data_version
    from .step import MISSING_DATA, NO_LITERAL
    from .values import _literal_problem

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    media = Media(folder)
    blob = kernel.spec.to_dict()
    entries = {entry["name"]: entry for entry in blob["steps"]}
    report: dict = {"exact": True, "steps": {}}
    taken: set[str] = set()
    for name, step in kernel.workflow.steps.items():
        value = step.literal
        step_folder = f"data/{_file_stem(name, taken)}"
        media.at(step_folder)
        if value is NO_LITERAL:
            if outputs:
                _save_output(folder, step_folder, name, step, entries[name], report, media)
            continue
        if value is None or _literal_problem(value) is None:
            continue
        entry, step_report = entries[name], {}
        if value is MISSING_DATA:
            # loaded without its data: still a data step, still without it
            data = {"in": None, "not_saved": {"*": "its data wasn't loaded, so there was none to save"}}
        elif isinstance(value, pd.DataFrame):
            relative = f"{step_folder}/table.parquet"
            manifest = write_frame(value, folder / relative, media)
            if "file_columns" in manifest:
                media.written.add(relative)
                back = read_frame(folder / relative, manifest, media)
                if _data_version(back) != _data_version(value) and "not_saved" not in manifest:
                    manifest["not_saved"] = {"*": "the table didn't read back exactly"}
            data = {"in": relative if "file_columns" in manifest else None,
                    "version": _data_version(value), **manifest}
            ids = list(step.output.data.index)
            if not step.output.meta.get("staged") and ids != list(value.index):
                # its rows' ids moved when its data was replaced (D-picks):
                # its readers' saved outputs and lineage name those ids
                try:
                    data["row_ids"] = tag(ids)
                except NotSaved:
                    pass
        else:
            try:
                data = {"in": "workflow.json", "value": tag(value, media)}
            except NotSaved as exc:
                data = {"in": None, "not_saved": {"*": f"a {exc} can't be saved"}}
        entry["data"] = data
        step_report["file"] = data["in"]
        if data.get("not_saved"):
            step_report["not_saved"] = data["not_saved"]
            report["exact"] = False
        report["steps"][name] = step_report
    _remove_unnamed(folder, media.written | _alive(kernel, folder))
    _write_json(folder / "workflow.json", blob)
    _write_json(folder / "report.json", report)
    return report


def _alive(kernel, folder: Path) -> set[str]:
    """The files under *folder* the kernel's own handles name: when the session
    folder is its store, a result it keeps (for undo) names files too."""
    from .handles import MediaHandle
    root, alive = folder.resolve(), set()
    outputs = [st.output for st in kernel.workflow.steps.values()]
    outputs += list(kernel.workflow.store.values())
    for output in outputs:
        for position in range(output.data.shape[1]):
            series = output.data.iloc[:, position]
            if series.dtype != object:
                continue
            for value in series:
                if isinstance(value, MediaHandle) and value.folder.resolve() == root:
                    alive.add(value.name)
    return alive


def _remove_unnamed(folder: Path, named: set[str]) -> None:
    """Remove the files this core wrote (:data:`_OWN_FILE`) that nothing names
    now, then the folders they leave empty. Nothing else is touched."""
    for sub in ("data", "outputs", "media"):
        top = folder / sub
        if not top.is_dir():
            continue
        for file in sorted(top.rglob("*")):
            relative = file.relative_to(folder).as_posix()
            if file.is_file() and relative not in named and _OWN_FILE.fullmatch(relative):
                file.unlink()
        for directory in sorted((d for d in top.rglob("*") if d.is_dir()), reverse=True):
            try:
                directory.rmdir()                       # only when empty
            except OSError:
                pass
        try:
            top.rmdir()
        except OSError:
            pass


def _meta_blob(output) -> dict:
    """An output's record, tagged: exact, or :class:`NotSaved`."""
    meta = {k: v for k, v in output.meta.items()
            if k not in ("problems", "notes", "column_types")}
    reads = meta.get("row_reads")
    if isinstance(reads, dict) and isinstance(reads.get("fp"), pd.Series):
        fp = reads["fp"]                            # a uint64 per row id: as pairs
        meta["row_reads"] = {**reads, "fp": [[i, int(h)] for i, h in zip(fp.index, fp.to_numpy())]}
    return {"meta": tag(meta), "notes": tag(dict(output.notes or {}))}


def _meta_from(blob: dict) -> dict:
    meta = untag(blob["meta"])
    reads = meta.get("row_reads")
    if isinstance(reads, dict) and isinstance(reads.get("fp"), list):
        pairs = reads["fp"]
        meta["row_reads"] = {**reads, "fp": pd.Series(
            [h for _, h in pairs], index=pd.Index([i for i, _ in pairs], dtype=object if any(
                isinstance(i, str) for i, _ in pairs) else None), dtype="uint64")}
    notes = untag(blob.get("notes") or {"$dict": []})
    if notes:
        meta["notes"] = notes
    return meta


def _save_output(folder: Path, step_folder: str, name: str, step, entry: dict,
                 report: dict, media: "Media") -> None:
    """Write *step*'s output to its folder, checked; else report why not."""
    from .output import _data_version

    output = step.output
    if output.meta.get("staged") or output.meta.get("empty"):
        return
    where = folder / step_folder
    why = None
    try:
        meta = _meta_blob(output)
    except NotSaved as exc:
        why = {"*": f"its record holds a {exc}, which can't be saved"}
    if why is None:
        data = write_frame(output.data, where / "table.parquet", media)
        states = write_frame(output.states.astype(str), where / "states.parquet")
        why = data.get("not_saved") or states.get("not_saved")
        if why is None:
            back = read_frame(where / "table.parquet", data, media)
            if _data_version(back) != _data_version(output.data):
                why = {"*": "its table didn't read back exactly"}
    if why:
        report["steps"].setdefault(name, {})["output"] = {"file": None, "not_saved": why}
        report["exact"] = False
        return                                  # its files, unnamed, go at the end
    _write_json(where / "meta.json", meta)
    media.written.update(f"{step_folder}/{f}" for f in ("table.parquet", "states.parquet", "meta.json"))
    entry["output"] = {"in": step_folder, "version": _data_version(output.data),
                       "data": data, "states": states}
    report["steps"].setdefault(name, {})["output"] = {"file": step_folder}


def _load_output(folder: Path, saved: dict, media: "Media | None" = None):
    """The output a save wrote, or None when it's missing or changed."""
    from .output import Output, _data_version, _state_column

    where = folder / saved["in"]
    table = where / "table.parquet"
    if not table.is_file() and (where / "data.parquet").is_file():
        table = where / "data.parquet"          # the earlier layout, outputs/<step>/
    try:
        data = read_frame(table, saved["data"], media)
        plain = read_frame(where / "states.parquet", saved["states"])
        # a state column is core's own type, built as core builds it
        states = pd.DataFrame({c: _state_column(plain[c].tolist(), data.index)
                               for c in plain.columns}, index=data.index)
        meta = _meta_from(json.loads((where / "meta.json").read_text()))
    except Exception:
        return None                            # missing or unreadable: it runs again
    if _data_version(data) != saved.get("version"):
        return None                            # changed since it was saved: it runs again
    return Output(data, states, meta)


def load(cls, folder, catalog, *, spill_over=None, store=None):
    """A kernel from the session folder *folder*, checked against *catalog*.
    With *spill_over*, media stay in the folder, as handles (P7d)."""
    from .output import _data_version

    folder = Path(folder)
    blob = json.loads((folder / "workflow.json").read_text())
    values, problems, ids, outputs = {}, {}, {}, {}
    media = Media(folder, lazy=spill_over is not None)
    for entry in blob.get("steps", []):
        data, name = entry.get("data"), entry["name"]
        if entry.get("output"):
            loaded = _load_output(folder, entry["output"], media)
            if loaded is not None:
                outputs[name] = loaded
        if not data:
            continue
        if data.get("row_ids") is not None:
            ids[name] = untag(data["row_ids"])
        if data.get("not_saved"):
            what = "; ".join(f"{c}: {why}" if c != "*" else why
                             for c, why in data["not_saved"].items())
            problems[name] = (f"{name!r}'s data wasn't saved exactly ({what}); "
                              f"assign it again: k[{name!r}] = …")
            continue
        where = data.get("in")
        if where == "workflow.json":
            try:
                values[name] = untag(data["value"], media)
            except (OSError, ValueError):
                problems[name] = (f"{name!r}'s data names a file that is missing from "
                                  f"{folder}; put it back, or assign it again: k[{name!r}] = …")
            continue
        if where is None or not (folder / where).is_file():
            problems[name] = (f"{name!r}'s data, {where}, is missing from {folder}; "
                              f"put the file back, or assign the data again: k[{name!r}] = …")
            continue
        try:
            frame = read_frame(folder / where, data, media)
        except (OSError, ValueError):
            problems[name] = (f"{name!r}'s data, {where}, names a file that is missing "
                              f"from {folder}; put it back, or assign it again: "
                              f"k[{name!r}] = …")
            continue
        if _data_version(frame) != data.get("version"):
            problems[name] = (f"{where} changed since it was saved, so {name!r} isn't "
                              f"the data the workflow was saved with; assign it again: "
                              f"k[{name!r}] = …")
            continue
        values[name] = frame
    return cls._load(blob, catalog, data=values, data_problems=problems,
                     data_ids=ids, outputs=outputs, spill_over=spill_over, store=store)
