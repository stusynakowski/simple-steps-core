"""Saving a session as a folder, and loading it back (plan P1c; docs/design/saving.md).

A session is a folder::

    <folder>/
      workflow.json          the kernel's spec; each data step names its file
      data/<step>.parquet    the data assigned to a step (a DataFrame)
      report.json            what the last save couldn't keep exactly

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
def tag(value: Any) -> Any:
    """*value* as JSON that names its type, so :func:`untag` gives it back
    exactly. Raises :class:`NotSaved` for a value it can't hold."""
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
        return {"$np": value.dtype.str, "v": tag(value.item())}
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
        return {"$complex": [tag(value.real), tag(value.imag)]}
    if isinstance(value, decimal.Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, pd.Timestamp):
        return {"$timestamp": value.isoformat(), "unit": value.unit,
                "tz": str(value.tz) if value.tz is not None else None}
    if isinstance(value, pd.Timedelta):
        return {"$pdtimedelta": int(value.value), "unit": value.unit}
    if isinstance(value, dt.datetime):
        return {"$datetime": value.isoformat(), "tz": getattr(value.tzinfo, "key", None)}
    if isinstance(value, dt.date):
        return {"$date": value.isoformat()}
    if isinstance(value, dt.time):
        return {"$time": value.isoformat()}
    if isinstance(value, dt.timedelta):
        return {"$timedelta": [value.days, value.seconds, value.microseconds]}
    if type(value) is tuple:
        return {"$tuple": [tag(v) for v in value]}
    if type(value) is list:
        return [tag(v) for v in value]
    if type(value) is dict:
        return {"$dict": [[tag(k), tag(v)] for k, v in value.items()]}
    if type(value) in (set, frozenset):
        return {f"${type(value).__name__}": [tag(v) for v in value]}
    raise NotSaved(type(value).__name__)


def untag(obj: Any) -> Any:
    """The value :func:`tag` wrote."""
    if isinstance(obj, list):
        return [untag(v) for v in obj]
    if not isinstance(obj, dict):
        return obj
    (key, payload), = [(k, v) for k, v in obj.items() if k.startswith("$")]
    if key == "$na":
        return pd.NA
    if key == "$nat":
        return pd.NaT
    if key == "$np":
        dtype = np.dtype(payload)
        if dtype.kind in "mM":
            return np.array(obj["v"], dtype="int64").view(dtype)[()]
        return dtype.type(untag(obj["v"]))
    if key == "$int":
        return int(payload)
    if key == "$float":
        return float(payload)
    if key == "$bytes":
        raw = base64.b64decode(payload)
        return bytearray(raw) if obj.get("mutable") else raw
    if key == "$complex":
        return complex(untag(payload[0]), untag(payload[1]))
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
        return when
    if key == "$date":
        return dt.date.fromisoformat(payload)
    if key == "$time":
        return dt.time.fromisoformat(payload)
    if key == "$timedelta":
        return dt.timedelta(days=payload[0], seconds=payload[1], microseconds=payload[2])
    if key == "$tuple":
        return tuple(untag(v) for v in payload)
    if key == "$dict":
        return {untag(k): untag(v) for k, v in payload}
    if key == "$set":
        return {untag(v) for v in payload}
    if key == "$frozenset":
        return frozenset(untag(v) for v in payload)
    raise ValueError(f"unknown tag {key!r} in a saved value")


def _same(a: list, b: list) -> bool:
    """Equal value for value, types included (``1`` is not ``1.0``)."""
    try:
        return json.dumps([tag(v) for v in a], sort_keys=True) == \
            json.dumps([tag(v) for v in b], sort_keys=True)
    except NotSaved:
        return False


# ── a table: one Parquet file, each column the plainest exact way ────────
def _pyarrow():
    try:
        import pyarrow
        import pyarrow.parquet
    except ImportError:                                # pragma: no cover
        raise ImportError("saving a session needs pyarrow: pip install pyarrow") from None
    return pyarrow, pyarrow.parquet


def _write_column(values: list):
    """``(array, how, why)``: typed when Arrow gives *values* back unchanged,
    else tagged JSON text; ``"not_saved"`` with the reason if neither can."""
    pa, _ = _pyarrow()
    try:
        array = pa.array(values)
        if _same(array.to_pylist(), values):
            return array, "typed", None
    except Exception:
        pass
    try:
        return pa.array([json.dumps(tag(v)) for v in values], pa.string()), "tagged", None
    except NotSaved as exc:
        return pa.nulls(len(values), pa.string()), "not_saved", f"a {exc} can't be saved"


def _read_column(array, how: str) -> list:
    values = array.to_pylist()
    if how == "tagged":
        return [untag(json.loads(v)) for v in values]
    return values


def _restore(values: list, dtype: str, index=None) -> pd.Series:
    try:
        return pd.Series(values, index=index, dtype=dtype)
    except (TypeError, ValueError):
        return pd.Series(values, index=index, dtype=object)


def write_frame(frame: pd.DataFrame, path: Path) -> dict:
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
        array, how, why = _write_column(series.tolist())
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
        array, how, why = _write_column(index.tolist())
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


def read_frame(path: Path, manifest: dict) -> pd.DataFrame:
    """The table :func:`write_frame` wrote."""
    _, pq = _pyarrow()
    table = pq.read_table(path)
    columns = manifest["columns"]
    index_entry = manifest["index"]
    if "range" in index_entry:
        index = pd.RangeIndex(index_entry["range"])
    else:
        values = _read_column(table.column(len(columns)), index_entry["how"])
        index = pd.Index(_restore(values, index_entry["dtype"]))
    index.name = untag(index_entry.get("name"))
    data = {}
    for position, column in enumerate(columns):
        values = _read_column(table.column(position), column["how"])
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
def save(kernel, folder) -> dict:
    """Save *kernel* as a session folder; the report of what wasn't exact."""
    from .output import _data_version
    from .step import MISSING_DATA, NO_LITERAL
    from .values import _literal_problem

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    previous = _previous_files(folder)
    blob = kernel.spec.to_dict()
    entries = {entry["name"]: entry for entry in blob["steps"]}
    report: dict = {"exact": True, "steps": {}}
    taken: set[str] = set()
    written: set[str] = set()
    for name, step in kernel.workflow.steps.items():
        value = step.literal
        if value is NO_LITERAL or value is None or _literal_problem(value) is None:
            continue
        entry, step_report = entries[name], {}
        if value is MISSING_DATA:
            # loaded without its data: still a data step, still without it
            data = {"in": None, "not_saved": {"*": "its data wasn't loaded, so there was none to save"}}
        elif isinstance(value, pd.DataFrame):
            relative = f"data/{_file_stem(name, taken)}.parquet"
            manifest = write_frame(value, folder / relative)
            if "file_columns" in manifest:
                written.add(relative)
                back = read_frame(folder / relative, manifest)
                if _data_version(back) != _data_version(value) and "not_saved" not in manifest:
                    manifest["not_saved"] = {"*": "the table didn't read back exactly"}
            data = {"in": relative if "file_columns" in manifest else None,
                    "version": _data_version(value), **manifest}
        else:
            try:
                data = {"in": "workflow.json", "value": tag(value)}
            except NotSaved as exc:
                data = {"in": None, "not_saved": {"*": f"a {exc} can't be saved"}}
        entry["data"] = data
        step_report["file"] = data["in"]
        if data.get("not_saved"):
            step_report["not_saved"] = data["not_saved"]
            report["exact"] = False
        report["steps"][name] = step_report
    for relative in previous - written:
        stale = folder / relative
        if stale.is_file() and stale.parent == folder / "data":
            stale.unlink()                     # a file this core wrote, no longer named
    _write_json(folder / "workflow.json", blob)
    _write_json(folder / "report.json", report)
    return report


def _previous_files(folder: Path) -> set[str]:
    try:
        blob = json.loads((folder / "workflow.json").read_text())
    except (OSError, ValueError):
        return set()
    return {(e.get("data") or {}).get("in") for e in blob.get("steps", [])
            if str((e.get("data") or {}).get("in") or "").startswith("data/")}


def load(cls, folder, catalog):
    """A kernel from the session folder *folder*, checked against *catalog*."""
    from .output import _data_version

    folder = Path(folder)
    blob = json.loads((folder / "workflow.json").read_text())
    values, problems = {}, {}
    for entry in blob.get("steps", []):
        data, name = entry.get("data"), entry["name"]
        if not data:
            continue
        if data.get("not_saved"):
            what = "; ".join(f"{c}: {why}" if c != "*" else why
                             for c, why in data["not_saved"].items())
            problems[name] = (f"{name!r}'s data wasn't saved exactly ({what}); "
                              f"assign it again: k[{name!r}] = …")
            continue
        where = data.get("in")
        if where == "workflow.json":
            values[name] = untag(data["value"])
            continue
        if where is None or not (folder / where).is_file():
            problems[name] = (f"{name!r}'s data, {where}, is missing from {folder}; "
                              f"put the file back, or assign the data again: k[{name!r}] = …")
            continue
        frame = read_frame(folder / where, data)
        if _data_version(frame) != data.get("version"):
            problems[name] = (f"{where} changed since it was saved, so {name!r} isn't "
                              f"the data the workflow was saved with; assign it again: "
                              f"k[{name!r}] = …")
            continue
        values[name] = frame
    return cls._load(blob, catalog, data=values, data_problems=problems)
