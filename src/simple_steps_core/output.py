"""Output: what a step produced. Data, a state per cell, notes and versions.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from typing import Any
from typing import Sequence
import hashlib
import math
import numbers
import pandas as pd


#: Default name for the column holding whatever a tool returned.
VALUE_COLUMN = "value"


#: The row-id column, ``#``: each row's id, the DataFrame index, shown and
#: referenced as a column (``cols["#"]``; docs/design/reshaping.md R-D11).
#: Reserved: a table can't bring its own. The row *number*, a row's position
#: on screen, has no name.
ROW_ID = "#"


def is_id_column(name: Any) -> bool:
    """A `#` column: `#` (the row id) or `#v` (the row of input `v` a row came
    from). Ids, not variables: positions, tools and "all columns" skip them
    (docs/design/reshaping.md §5.1)."""
    return isinstance(name, str) and name.startswith(ROW_ID)


def variables(columns: Sequence[Any]) -> list:
    """The columns that are variables: all but the `#` columns."""
    return [c for c in columns if not is_id_column(c)]


#: Every ledger has exactly these columns, so the UI can rely on them.


# ─────────────────────────────────────────────────────────────────────────
# Output — data, states, meta (009)
# ─────────────────────────────────────────────────────────────────────────
#: Every state a cell can be in, mildest first, so a row's state is its
#: worst cell's. ``stale`` is not stored: it's a step-level fact (meta) shown
#: over known cells.
STATES = ("absent", "known", "maybe", "pending", "blocked", "failed", "invalid")


class _Absent:
    """The marker a tool's row holds for an ``absent`` cell: no value here at
    all (reshaping.md §9.1). Turned into the parameter's default, or None."""

    def __repr__(self) -> str:
        return "ABSENT"

    def __bool__(self) -> bool:
        return False


ABSENT = _Absent()


#: Which state a verb's per-unit record maps to.
_RECORD_STATE = {"completed": "known", "staged": "pending", "invalid": "invalid"}


def _state_column(values: Sequence[str], index: Any) -> pd.Series:
    return pd.Series(pd.Categorical(values, categories=STATES, ordered=True), index=index)


def _states_frame(row_states: Sequence[str], data: pd.DataFrame) -> pd.DataFrame:
    """One state per cell, same shape as *data*: each row's state in every column."""
    return pd.DataFrame({c: _state_column(row_states, data.index) for c in data.columns},
                        index=data.index)


def _from_records(records: Sequence[dict], index: Sequence[Any], data: pd.DataFrame,
                  meta: dict) -> tuple[pd.DataFrame, dict]:
    """Turn a verb's per-unit records into per-cell states and sparse notes.

    Records are how a verb reports its units while it runs. They are not kept:
    a row that completed normally costs one state code per cell, nothing more.
    Only rows with something to say — an error, a cause, a caught failure,
    retries, an unusual lineage — get a note in ``meta["notes"]``.
    """
    by_id: dict = {}
    notes: dict = dict(meta.get("notes") or {})
    for row_id, record in zip(index, records):
        status = record.get("status")
        if status == "failed":
            state = "blocked" if record.get("cause") else "failed"
        else:
            state = _RECORD_STATE.get(status, "known")
        by_id[row_id] = state
        note = {k: record[k] for k in ("error", "cause") if record.get(k)}
        if record.get("caught"):
            note["caught"] = True
        if record.get("attempts") not in (None, 0, 1):
            note["attempts"] = record["attempts"]
        unit = record.get("unit")
        if unit is not None and (note or isinstance(unit, list)):
            note["unit"] = unit            # lineage that the row id doesn't already say
        if note:
            notes[row_id] = note
    row_states = [by_id.get(i, "known") for i in data.index]
    if notes:
        meta["notes"] = notes
    return _states_frame(row_states, data), meta


class Output:
    """What a step produced: **data, states, meta** (009).

    - ``data``: the step's results, typed, indexed by row id. What downstream
      steps consume.
    - ``states``: the same shape as ``data``; one state per cell, from
      :data:`STATES` (``known``, ``maybe``, ``pending``, ``blocked``,
      ``failed``, ``invalid``). Compact: one byte per cell.
    - ``meta``: everything else, open-ended. ``notes`` (row id → error, cause,
      caught, attempts, unit — only for rows that have something to say),
      ``plan``, ``auto``, ``version``, ``read``, ``stale``, ``excluded`` …

    ``print(output)`` shows it all as one grid.
    """

    def __init__(self, data: pd.DataFrame, states: pd.DataFrame | None = None,
                 meta: dict | None = None, *, records: Sequence[dict] | None = None,
                 index: Sequence[Any] | None = None):
        self.data = data
        self.meta = dict(meta) if meta else {}
        if states is None:
            records = records if records is not None else []
            index = data.index if index is None else index
            if records:
                states, self.meta = _from_records(records, index, data, self.meta)
            else:
                states = _states_frame(["known"] * len(data), data)
        self.states = states

    def mark_absent(self, cells: dict) -> None:
        """Put the cells ``{column: [row ids]}`` in state ``absent``: their
        source had no value there (a missing key, a stack or join gap)."""
        for column, ids in (cells or {}).items():
            if column in self.states.columns:
                for i in ids:
                    if i in self.states.index:
                        self.states.at[i, column] = "absent"

    def absent_cells(self) -> set:
        """``{(row id, column)}`` of the cells in state ``absent``."""
        if not len(self.states.columns):
            return set()
        hit = self.states.eq("absent")
        return {(i, c) for c in hit.columns for i in hit.index[hit[c]]}

    def add_id_columns(self, columns: dict[str, pd.Series]) -> None:
        """Put `#` columns in front of the data, each cell `known`."""
        for position, (name, values) in enumerate(columns.items()):
            # As objects, so an id stays an int and a missing one stays None
            # (found by the property test: a list insert made them floats and NaN).
            ids = [None if _is_missing(v) else v for v in values.reindex(self.data.index).tolist()]
            self.data.insert(position, name, pd.Series(ids, index=self.data.index, dtype=object))
            self.states.insert(position, name, _state_column(
                ["known"] * len(self.data), self.data.index))

    # ── named fields (read from meta until phase 3e) ─────────────────────
    @property
    def version(self) -> str | None:
        """A hash of the data, once the step has run. Equal data, equal version."""
        return self.meta.get("version")

    @property
    def read(self) -> dict:
        """``{step or "res:name": version}`` this output was computed from."""
        return dict(self.meta.get("read") or {})

    @property
    def plan(self) -> dict:
        """Before running: rows, columns and types, each with its certainty."""
        return dict(self.meta.get("plan") or {})

    @property
    def value_column(self) -> str | None:
        """The column the tool's results were written to, or None."""
        return self.meta.get("value_column")

    @property
    def staged(self) -> bool:
        """True until the step has run."""
        return bool(self.meta.get("staged"))

    @property
    def stale(self) -> bool:
        """True when what this was computed from has changed since."""
        return bool(self.meta.get("stale"))

    @property
    def stale_reason(self) -> str | None:
        """Why it is stale: ``updated args``, ``input sick changed``, …"""
        return self.meta.get("stale_reason") if self.stale else None

    @property
    def ran_with(self) -> dict:
        """What the values were computed with: the formula and each argument."""
        return dict(self.meta.get("ran_with") or {})

    # ── reading states ───────────────────────────────────────────────────
    @property
    def notes(self) -> dict:
        """Row id → what there is to say about that row (error, cause, …)."""
        return self.meta.get("notes") or {}

    @property
    def row_states(self) -> pd.Series:
        """Each row's state: its worst cell's (a row with one failed cell is failed)."""
        if not len(self.states.columns):
            return _state_column(["known"] * len(self.data), self.data.index)
        codes = self.states.apply(lambda col: col.cat.codes).max(axis=1)
        return _state_column([STATES[c] for c in codes], self.data.index)

    def ids_in(self, *states: str) -> list:
        """Row ids whose state is one of *states*."""
        rs = self.row_states
        return list(rs.index[rs.isin(states)])

    @property
    def uncaught(self) -> list:
        """Row ids whose failure would stop ``run_all`` (010 C21).

        A row stops the run when its own tool failed (state ``failed``), the
        step didn't let it through (no ``caught``), and it isn't merely
        blocked by an earlier failure (``blocked``, which has a ``cause``). A
        breaker stop counts.
        """
        return [i for i in self.ids_in("failed")
                if not (self.notes.get(i) or {}).get("caught")]

    @property
    def stops_run(self) -> bool:
        """Would this output stop ``run_all``? (010 C21)"""
        return bool(self.uncaught)

    def view(self) -> pd.DataFrame:
        """The grid as a user sees it: ``#`` (0…n-1), the data, each row's
        ``state`` and, where there is one, its note."""
        out = self.data.copy()
        out["state"] = self.row_states.astype(str)
        if self.meta.get("stale"):
            rows_ = self.meta.get("stale_rows")
            which = out["state"] == "known"
            if rows_ is not None:
                which &= out.index.isin(rows_)
            out.loc[which, "state"] = "stale"
        if self.notes:
            out["note"] = [_note_text(self.notes.get(i)) for i in out.index]
        out.insert(0, ROW_ID, list(out.index))
        return out.reset_index(drop=True)

    # ── the two halves ───────────────────────────────────────────────────
    @property
    def ok(self) -> pd.DataFrame:
        """Rows whose every cell is known."""
        return self.data.loc[self.ids_in("known")]

    @property
    def failed(self) -> pd.DataFrame:
        """Rows that failed or were blocked — the re-drive set, with their notes."""
        ids = self.ids_in("failed", "blocked")
        rows_ = {i: {"state": self.row_states[i], **self.notes.get(i, {})} for i in ids}
        return pd.DataFrame.from_dict(rows_, orient="index",
                                      columns=None) if rows_ else pd.DataFrame(
            columns=["state", "error"])

    @property
    def values(self) -> list[Any]:
        """The payload column as a plain list, for the common case."""
        column = self.meta.get("value_column")
        if column is None:
            return []
        # 008 C14: a missing value reads back as None — never NaN or pd.NA.
        return [None if _is_missing(v) else v for v in self.data[column]]

    def item(self) -> Any:
        """The single payload of a one-row grid (``collapse`` and friends)."""
        if len(self.data) != 1:
            raise ValueError(
                f"item() needs exactly one row; this grid has {len(self.data)}."
            )
        return self.values[0]

    # ── shape ────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return len(self.data)

    @property
    def shape(self) -> tuple[int, int]:
        """Rows x columns — the same thing ``DataFrame.shape`` means."""
        return self.data.shape

    @property
    def form(self) -> str:
        """``"scalar"``, ``"column"`` or ``"grid"`` — the cardinality class.

        Distinct from :attr:`shape`, which is the actual (rows, columns). The
        form is what a step's mode *promises*; the shape is what it holds.
        """
        return self.meta.get("form", "grid")

    def progress(self) -> str:
        return f"{len(self.ids_in('known'))}/{len(self.data)}"

    def __str__(self) -> str:
        """The output as one grid: a caption, then values with their states."""
        caption = repr(self)
        if self.meta.get("staged"):
            plan = self.meta.get("plan") or {}
            return f"{caption}\n{_plan_words(plan)}" if plan else caption
        return f"{caption}\n{self.view().to_string(index=False)}"

    def __repr__(self) -> str:
        verb = self.meta.get("verb", "?")
        if self.meta.get("staged"):
            return f"<Output {verb} · staged>"
        failed = len(self.ids_in("failed", "blocked"))
        tail = f", {failed} failed" if failed else ""
        if self.meta.get("stale"):
            tail += f", stale output ({self.meta.get('stale_reason') or 'an earlier step changed'})"
        return (f"<Output {verb} · {len(self.data)} row(s) × "
                f"{len(self.data.columns)} col(s){tail}>")


def _is_missing(value: Any) -> bool:
    """None, pandas' NA, or a float NaN — every spelling of "no value" (008 C14)."""
    if value is None or value is pd.NA:
        return True
    return isinstance(value, float) and math.isnan(value)


def _typed(values: list, index: Any) -> Any:
    """A payload column that keeps its type when some cells have no value.

    008 R8/C14: a failed or missing cell used to land as ``NaN``, turning an
    ``int`` column into ``float64`` (``100.0, NaN, 300.0``) and refusing every
    ``n: int`` tool downstream. With a missing cell, ints become nullable
    ``Int64``, floats ``Float64``, bools ``boolean``, anything else ``object``
    holding ``None``. A column with no missing cell is left to pandas, as before.
    """
    present = [v for v in values if not _is_missing(v)]
    if len(present) == len(values):
        return values
    cleaned = [None if _is_missing(v) else v for v in values]
    if present and all(isinstance(v, bool) for v in present):
        dtype = "boolean"
    elif present and all(isinstance(v, numbers.Integral) and not isinstance(v, bool)
                         for v in present):
        dtype = "Int64"
    elif present and all(isinstance(v, numbers.Real) and not isinstance(v, bool)
                         for v in present):
        dtype = "Float64"
    else:
        return pd.Series(cleaned, index=index, dtype=object)
    return pd.array(cleaned, dtype=dtype)


def _normalize_missing(frame: pd.DataFrame) -> pd.DataFrame:
    """Give a source's columns with missing values a type that can hold None.

    ``pd.DataFrame({"n": [1, None, 3]})`` is ``float64`` with ``NaN`` — pandas'
    spelling of "ints with a gap". It becomes nullable ``Int64`` (the rule
    pandas' own ``convert_dtypes`` uses: every present value is whole), so a
    tool reading it gets ``None`` and ints (008 C14). Columns with no missing
    value are untouched.
    """
    out = None
    for column in frame.columns:
        series = frame[column]
        try:
            missing = series.isna()
        except (TypeError, ValueError):
            continue
        if not missing.any():
            continue
        out = frame.copy() if out is None else out
        present = series[~missing]
        if series.dtype.kind == "f" and len(present) and (present % 1 == 0).all():
            out[column] = series.astype("Int64")
        elif series.dtype == object:
            out[column] = series.where(~missing, None)
    return frame if out is None else out


def _str_columns(frame: pd.DataFrame, step_id: str = "the step") -> pd.DataFrame:
    """Every column name a string (008 C7: names are str, rows are int).

    ``2023`` becomes ``"2023"``. Two names that collide once converted fail.
    """
    if all(isinstance(c, str) for c in frame.columns):
        return frame
    names = [str(c) for c in frame.columns]
    seen: dict[str, Any] = {}
    for original, name in zip(frame.columns, names):
        if name in seen:
            raise SelectionError(
                f"columns {seen[name]!r} and {original!r} of {step_id!r} both "
                f"become {name!r}; rename one")
        seen[name] = original
    out = frame.copy()
    out.columns = names
    return out


def _uncaught_failure(output: "Output") -> tuple[Any, str] | None:
    """The first failed cell that should stop the run: its own failure, not
    caught by ``mod.try_except``. A row blocked by an upstream failure has a
    ``cause`` — its root already stopped the run, or was caught."""
    if not output.uncaught:
        return None
    row_id = output.uncaught[0]
    return row_id, (output.notes.get(row_id) or {}).get("error")


def _data_version(data: pd.DataFrame) -> str:
    """A short hash of a grid's contents — row ids, columns and values (009 §5).

    Equal data, equal version: a step re-run with the same result leaves the
    steps that read it fresh. Cells pandas can't hash (lists, dicts) are hashed
    from their JSON.
    """
    columns = repr([str(c) for c in data.columns]).encode()
    try:
        values = pd.util.hash_pandas_object(data, index=True).values.tobytes()
    except TypeError:
        values = data.to_json(orient="split", default_handler=repr).encode()
    return hashlib.sha1(columns + values).hexdigest()[:12]


def _failed_output(operation: Any, error: str) -> "Output":
    """A step that could not produce a grid: one failed cell saying why."""
    kind = operation.shape_verb.kind if operation.shape_verb else None
    return Output(
        data=pd.DataFrame({VALUE_COLUMN: [None]}, index=[0], dtype=object),
        records=[{"status": "failed", "error": error, "attempts": 0,
                         "seconds": 0.0}], index=[0],
        meta={"verb": kind, "form": "scalar", "value_column": VALUE_COLUMN})


def _upstream_failures(source: Any) -> dict:
    """Rows of *source* that failed upstream: index → (error, root cause).

    008 C10: such a row is failed again **without calling the tool**. The root
    cause is carried from the upstream ledger's ``cause``, or is the upstream
    cell itself (``a[1]: ValueError: boom``). ``meta["blocked_all"]`` marks
    every row — set when an *argument* the step reads holds a failed cell.
    """
    if not isinstance(source, Output):
        return {}
    if source.meta.get("blocked_all"):
        return {index: source.meta["blocked_all"] for index in source.data.index}
    sid = source.meta.get("name") or "input"
    # K19: rows a column argument has no row for: (error, cause) each.
    out = dict(source.meta.get("blocked_rows") or {})
    for row_id in source.ids_in("failed", "blocked"):
        note = source.notes.get(row_id, {})
        out[row_id] = (f"upstream cell {sid}[{row_id}] failed",
                       note.get("cause") or f"{sid}[{row_id}]: {note.get('error')}")
    return out


def _blocked(error: str, cause: str) -> dict:
    """The record of a unit that was not run because its input failed."""
    return {"status": "failed", "error": error, "attempts": 0, "seconds": 0.0,
            "cause": cause}


def _note_text(note: dict | None) -> str:
    """A row's note in a few words, for printing."""
    if not note:
        return ""
    if note.get("cause"):
        return f"blocked by {note['cause']}"
    text = note.get("error") or ""
    return f"{text} (caught)" if note.get("caught") and "caught" not in text else text


def _plan_words(plan: dict) -> str:
    """A plan in one line: ``columns city (str), n (int) + maybe more · rows unknown …``."""
    columns, rows_ = plan.get("columns", {}), plan.get("rows", {})
    types_ = plan.get("types", {})
    names = ", ".join(f"{c} ({types_.get(c, 'any')})" for c in columns.get("names", []))
    if not names:
        col_text = "columns unknown until it runs"
    else:
        col_text = f"columns {names}" + (" + maybe more" if columns.get("more") else "")
        if columns.get("certainty") == "stated":
            col_text += " (stated)"
    certainty = rows_.get("certainty")
    if certainty in ("exact", "stated") and "count" in rows_:
        row_text = f"{rows_['count']} rows" + (" (stated)" if certainty == "stated" else "")
    elif "min" in rows_ or "max" in rows_:
        row_text = f"{rows_.get('min', 0)}–{rows_.get('max', '?')} rows"
    else:
        row_text = "rows unknown until it runs"
    return f"{col_text} · {row_text}"


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .errors import SelectionError  # noqa: E402
