"""The shape verbs and reshapes, on DataFrames, and how a tool is called per row.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Sequence
import itertools
import pandas as pd
import time
import traceback

from .system_tools import identity
from .output import PAYLOAD


# ─────────────────────────────────────────────────────────────────────────
# Input coercion — "what is a row?"
# ─────────────────────────────────────────────────────────────────────────
def _rows_frame(value: Any, *, axis: str = "rows") -> pd.DataFrame:
    """Coerce a step input into a frame of rows.

    **Only a DataFrame carries its own row/column structure.** A ``Series``
    becomes a one-column frame. **Everything else — a list, a dict, a tuple, a
    scalar, a string — is one cell**, holding the value whole. Reshaping a
    collection into rows or columns is an explicit verb (``expand`` makes it
    longer, ``widen`` makes it wider), never something a source silently coerces:
    a tool that returns ``[1, 2, 3]`` for a default should stay one value until a
    verb says what its elements mean (docs/shape-algebra.md §2.1).

    An ``Output`` yields its payload grid (what an upstream step hands a verb).
    """
    if isinstance(value, Output):
        return value.data
    if isinstance(value, pd.DataFrame):
        if axis == "columns":
            # Transposing is the easy half and the wrong half. A column verb's
            # unit of work is a column, so its ledger is indexed by column name
            # while `data` is indexed by row — different index *spaces*, which
            # makes Output.view()'s join produce NaN rather than an error. That
            # needs an answer in §5 (and a column should arrive as a list, not
            # a dict keyed by the old index) before it can be switched on.
            raise NotImplementedError(
                "axis='columns' is not implemented yet: column verbs need a "
                "ledger indexed by column, which docs/shape-algebra.md §5 does "
                "not yet cover. Use axis='rows'."
            )
        return value
    if isinstance(value, pd.Series):
        return value.to_frame(name=PAYLOAD)
    # One cell. `[value]` wraps the whole value — a list lands in a single cell,
    # not one row per element — so `rows([1, 2, 3])` is a 1x1 grid holding the
    # list. `expand` is how you turn that cell into rows.
    return pd.DataFrame({PAYLOAD: [value]})


def _row_key(key: Callable) -> Callable:
    """A tool given as a setting, applied to one row by column binding (008 C2)."""
    apply = _d_apply(key)
    return lambda row: apply(row)


def _key_column(frame: pd.DataFrame, key: Callable) -> list:
    """The key a tool setting gives each row, in row order."""
    apply = _row_key(key)
    return [apply(row) for _index, row in _units(frame)]


def _child_id(parent: Any, k: int) -> str:
    """Row id of the *k*-th row derived from row *parent*: ``1`` → ``"1.0"``."""
    return f"{parent}.{k}"


def _ancestors(row_id: Any) -> list[str]:
    """``"1.0.2"`` → ``["1.0", "1"]`` — the rows a derived row came from."""
    parts = str(row_id).split(".")
    return [".".join(parts[:i]) for i in range(len(parts) - 1, 0, -1)]


def _units(frame: pd.DataFrame):
    """``(index, row dict)`` per row, each value as the tool should get it.

    Not ``iterrows``: that builds one Series per row with a single common dtype,
    so a nullable ``Int64`` row arrives as floats (``1.0``). ``to_dict`` keeps
    each column's own type; a missing value becomes ``None`` (008 C14).
    """
    for index, record in zip(frame.index, frame.to_dict("records")):
        yield index, {k: (None if _is_missing(v) else v) for k, v in record.items()}


def _as_arg(row: pd.Series) -> dict:
    """What a tool receives for one row: a plain dict, never a Series.

    A missing value arrives as ``None`` (008 C14) — never ``NaN`` or ``pd.NA``,
    so a tool written for ``int | None`` gets what it was written for.
    """
    return {k: (None if _is_missing(v) else v) for k, v in row.to_dict().items()}


@dataclass(frozen=True)
class _Caught:
    """What ``mod.try_except(default=…)`` returns for a unit whose tool raised."""
    value: Any
    error: str


class _Stopped(Exception):
    """A unit ``mod.breaker`` didn't run: the step stopped after a run of failures."""


class _Tolerated(Exception):
    """A failure ``mod.try_except()`` caught with no default: the row fails,
    and the run keeps going."""


def _unwrap(value: Any) -> tuple[Any, str | None]:
    """(value, caught error) — a fallback carries the error it replaced."""
    if isinstance(value, _Caught):
        return value.value, value.error
    return value, None


def _call(fn: Callable, arg: dict, retries: int) -> tuple[Any, dict]:
    """Run *fn* for one unit, returning (value, ledger record).

    A ``mod.try_except`` failure is recorded with ``caught: True``: completed
    with its fallback value (the error kept), or failed without stopping the run.
    """
    started = time.perf_counter()
    attempt = 0
    while True:
        try:
            value, caught = _unwrap(fn(arg))
            if caught is not None:
                return value, {"status": "completed",
                               "error": f"caught {caught}; used the default",
                               "attempts": attempt + 1, "caught": True,
                               "seconds": round(time.perf_counter() - started, 6)}
            return value, {"status": "completed", "error": None,
                           "attempts": attempt + 1,
                           "seconds": round(time.perf_counter() - started, 6)}
        except _Tolerated as exc:
            return None, {"status": "failed", "error": str(exc),
                          "attempts": attempt + 1, "caught": True,
                          "seconds": round(time.perf_counter() - started, 6)}
        except _Stopped as exc:
            # The breaker tripped earlier in this step: not run, nothing spent.
            return None, {"status": "failed", "error": str(exc), "attempts": 0,
                          "seconds": 0.0}
        except Exception as exc:
            if attempt >= retries:
                return None, {"status": "failed",
                              "error": f"{type(exc).__name__}: {exc}",
                              "attempts": attempt + 1,
                              "seconds": round(time.perf_counter() - started, 6),
                              "traceback": traceback.format_exc()}
            attempt += 1


# ─────────────────────────────────────────────────────────────────────────
# The verbs
# ─────────────────────────────────────────────────────────────────────────
def map_(source: Any, fn: Callable, *, name: str = PAYLOAD,
         retries: int = 0, axis: str = "rows", replace: bool = False) -> Output:
    """``map`` — n rows in, n rows out: **only** *fn*'s result, one column.

    The input columns are **not** carried (owner decision, 2026-10-20): a map
    step is its results. Each row keeps its input row's id, so the results stay
    aligned with the input — put them side by side with ``zip_(wf["in"],
    wf["out"])`` or ``join``.
    """
    frame = rows(source, axis=axis)
    blocked = _upstream_failures(source)
    values, records = [], []
    for index, row in _units(frame):
        if index in blocked:
            value, record = None, _blocked(*blocked[index])
        else:
            value, record = _call(fn, row, retries)
        values.append(value)
        records.append(record)

    data = pd.DataFrame(index=frame.index)
    data[name] = _typed(values, frame.index)
    return Output(data=data, records=records, index=frame.index,
                  meta={"verb": "map", "form": "column", "payload": name,
                        "n_in": len(frame)})


def filter_(source: Any, fn: Callable, *, retries: int = 0,
            axis: str = "rows") -> Output:
    """``filter`` — keep the rows where *fn* is truthy. Columns unchanged.

    Nothing is hidden: a row whose predicate **raised** stays, marked
    ``failed`` (and a row blocked upstream stays ``blocked``), so the failure is
    visible downstream. Rows the predicate rejected are listed by id in
    ``meta["excluded"]``.
    """
    frame = rows(source, axis=axis)
    blocked = _upstream_failures(source)
    keep, records = [], []
    for index, row in _units(frame):
        if index in blocked:
            # 008 C10: a failed row is carried through, still failed, so the
            # failure stays visible downstream instead of being filtered away.
            record = _blocked(*blocked[index])
            keep.append(True)
            records.append(record)
            continue
        value, record = _call(fn, row, retries)
        passed = record["status"] != "completed" or bool(value)
        keep.append(passed)
        records.append(record)

    data = frame[pd.Series(keep, index=frame.index)]
    excluded = [i for i, k in zip(frame.index, keep) if not k]
    return Output(data=data, records=records, index=frame.index,
                  meta={"verb": "filter", "form": "column",
                        "payload": None, "n_in": len(frame),
                        "n_dropped": len(excluded), "excluded": excluded})


def group_(source: Any, fn: Callable, *, name: str = "group",
           retries: int = 0, axis: str = "rows", replace: bool = False,
           by: Callable | None = None) -> Output:
    """``group_by`` — mark each row with a key. n rows in, n rows out.

    No nesting: reduction is :func:`collapse_` with ``by=name``. ``by=`` a
    registered tool computes the key instead of the step's own tool (008 C2).
    """
    if by is not None:
        fn = _d_apply(by)
    frame = rows(source, axis=axis)
    blocked = _upstream_failures(source)
    keys, records = [], []
    for index, row in _units(frame):
        if index in blocked:
            value, record = None, _blocked(*blocked[index])
        else:
            value, record = _call(fn, row, retries)
        keys.append(value)
        records.append(record)

    # Only the key, on the input's row ids (owner decision, 2026-10-20): pair
    # it with the rows it labels by `zip_(wf["in"], wf["keys"])`.
    data = pd.DataFrame(index=frame.index)
    data[name] = _typed(keys, frame.index)
    return Output(data=data, records=records, index=frame.index,
                  meta={"verb": "group", "form": "column", "payload": name,
                        "key": name, "n_in": len(frame)})


def collapse_(source: Any, fn: Callable, *, by: str | None = None,
              initial: Any = None, name: str = PAYLOAD) -> Output:
    """``summarise`` — reduce to one row, or one row per ``by`` group.

    *fn* takes ``(accumulator, row_dict)``. With ``by`` it runs per group and
    the result carries the group key as a column.
    """
    frame = rows(source)
    blocked = _upstream_failures(source)
    if callable(by):
        # 008 C2: group by a tool's value per row; the key column is named
        # after the tool.
        key_name = getattr(by, "__name__", "key")
        keyed = frame.assign(**{key_name: _key_column(frame, by)})
        groups = list(keyed.groupby(key_name, sort=False))
        groups = [(k, frame.loc[chunk.index]) for k, chunk in groups]
        by = key_name
    elif by is None:
        groups = [(None, frame)]
    else:
        if by not in frame.columns:
            # 010 C23: a step that fails, with the reason — not a bare KeyError.
            sid = (source.meta.get("step_id") if isinstance(source, Output) else None) or "the input"
            raise SelectionError(
                f"collapse groups by {by!r}, which {sid!r} does not have "
                f"(it has {', '.join(map(str, frame.columns)) or 'no columns'})")
        groups = list(frame.groupby(by, sort=False))

    results, keys, records, index = [], [], [], []
    for position, (key, chunk) in enumerate(groups):
        started = time.perf_counter()
        failed_in = [i for i in chunk.index if i in blocked]
        if failed_in:
            # 008 C10: one failed cell makes the summary a failed cell — a
            # total over rows that did not all arrive would be a wrong answer.
            accumulator = None
            records.append({**_blocked(*blocked[failed_in[0]]),
                            "unit": list(chunk.index)})
        else:
            accumulator, error, caught = initial, None, None
            try:
                for _index, row in _units(chunk):
                    accumulator, caught_now = _unwrap(fn(accumulator, row))
                    if caught_now is not None:
                        caught = True
                        error = f"caught {caught_now}; used the default"
                status = "completed"
            except _Tolerated as exc:
                status, accumulator, error, caught = "failed", None, str(exc), True
            except Exception as exc:
                status, accumulator = "failed", None
                error = f"{type(exc).__name__}: {exc}"
            records.append({"status": status, "error": error, "attempts": 1,
                            "seconds": round(time.perf_counter() - started, 6),
                            "unit": list(chunk.index), "caught": caught})
        results.append(accumulator)
        keys.append(key)
        index.append(position)

    data = pd.DataFrame(index=index)
    if by is not None:                       # key first reads better
        data[by] = keys
    data[name] = _typed(results, data.index)
    return Output(data=data, records=records, index=index,
                  meta={"verb": "collapse", "form": "scalar" if by is None
                        else "column", "payload": name, "by": by,
                        "n_in": len(frame)})


def expand_(source: Any, fn: Callable, *, name: str = PAYLOAD,
            retries: int = 0, axis: str = "rows", replace: bool = False) -> Output:
    """``unnest`` — each unit yields an iterable; results are concatenated.

    Output rows outnumber units, so they cannot share the input's index: each
    row records which unit produced it in the ledger's ``source`` column.
    """
    frame = rows(source, axis=axis)
    blocked = _upstream_failures(source)
    out_rows, records, ids = [], [], []
    for index, row in _units(frame):
        arg = row
        # 008 C16: each item's row id is derived from its parent's — `1.0`,
        # `1.1` — so `zip_` can line the items back up with the row they came
        # from. One placeholder row for a failed parent keeps `1.0` too.
        if index in blocked:
            records.append({**_blocked(*blocked[index]), "unit": index})
            out_rows.append({name: None})
            ids.append(_child_id(index, 0))
            continue
        produced, record = _call(fn, arg, retries)
        if record["status"] != "completed":
            records.append({**record, "unit": index})
            out_rows.append({name: None})
            ids.append(_child_id(index, 0))
            continue
        if isinstance(produced, pd.DataFrame):
            # Iterating a DataFrame yields its column names, so the old
            # behaviour was a silent wrong answer. A per-unit failure, like any
            # other unusable return, so it stays inspectable.
            records.append({**record, "status": "failed", "unit": index,
                            "error": "TypeError: expand received a DataFrame; "
                                     "iterating one yields its column names. "
                                     "Return a list of values, widen it into "
                                     "columns, or assign it as a source step."})
            out_rows.append({name: None})
            ids.append(_child_id(index, 0))
            continue
        items = (list(produced)
                 if isinstance(produced, Iterable)
                 and not isinstance(produced, (str, bytes, dict))
                 else [produced])
        for k, item in enumerate(items):
            # Only the item (owner decision, 2026-10-20), on an id derived from
            # its parent's; the ledger's `unit` names the parent too.
            out_rows.append({name: item})
            records.append({**record, "unit": index})
            ids.append(_child_id(index, k))

    # Column by column, so a carried int column and the payload both keep their
    # type when a failed unit leaves a gap (008 R8) — `DataFrame(rows)` would
    # turn every int column with a None into float64.
    data = pd.DataFrame(index=pd.Index(ids, dtype=object))
    for column in (list(out_rows[0]) if out_rows else []):
        data[column] = _typed([r.get(column) for r in out_rows], data.index)
    if not len(data.columns):
        # Every unit expanded to nothing. `DataFrame([])` has no columns at all,
        # which would make a downstream step report "it has no columns" rather
        # than "it is empty" — two different problems. `filter` keeps its columns
        # when it drops every row; expand has to agree.
        #
        # Sliced from the input rather than rebuilt, so the carried columns keep
        # their **dtypes** too: an empty column built from `[]` would come out
        # float64 and a downstream `n: int` would be reported as a mismatch. The
        # payload is object, which is the honest answer — nothing was produced,
        # so its type is unknown, and an empty column is undecidable anyway.
        data = pd.DataFrame({name: pd.Series([], dtype=object)})
    return Output(data=data, records=records, index=data.index,
                  meta={"verb": "expand", "form": "column", "payload": name,
                        "n_in": len(frame)})


def table_(source: Any, fn: Callable, *, retries: int = 0) -> Output:
    """``table`` — hand the tool the **whole grid**; what it returns is the step's grid.

    008 K12: the mirror of a tool-backed ``source``, for pivots, unpivots and
    anything that needs every row at once::

        @tool
        def piv(df: pd.DataFrame) -> pd.DataFrame:
            return df.groupby("city", as_index=False)["n"].sum()

        wf["per_city"] = piv[mod.table()](wf["r"])

    One unit of work: it runs once, and the ledger records that run on every
    output row. A failed cell in the input blocks it without calling the tool.
    """
    frame = _rows_frame(source)
    blocked = _upstream_failures(source)
    meta = {"verb": "table", "form": "grid", "payload": None, "n_in": len(frame)}
    if blocked:
        record = _blocked(*next(iter(blocked.values())))
        return Output(data=pd.DataFrame({PAYLOAD: [None]}, index=[0], dtype=object),
                      records=[record], index=[0], meta=meta)
    value, record = _call(fn, frame, retries)
    if record["status"] != "completed":
        return Output(data=pd.DataFrame({PAYLOAD: [None]}, index=[0], dtype=object),
                      records=[record], index=[0], meta=meta)
    if isinstance(value, pd.Series):
        value = value.to_frame()
    if not isinstance(value, pd.DataFrame):
        if record.get("caught"):
            value = _rows_frame(value)          # a try_except default
        else:
            record = {**record, "status": "failed",
                      "error": f"TypeError: table expects a DataFrame back, got "
                               f"{type(value).__name__}"}
            return Output(data=pd.DataFrame({PAYLOAD: [None]}, index=[0], dtype=object),
                          records=[record], index=[0], meta=meta)
    data = _normalize_missing(_own_index(_str_columns(value, "the table"), "the table"))
    records = [{**record, "unit": "table"} for _ in range(len(data))]
    return Output(data=data, records=records, index=data.index,
                  meta={**meta, "columns": list(data.columns)})


def auto_(source: Any, fn: Callable) -> Output:
    """``auto`` — pick the verb from the tool and the data, at run (008 N).

    Stored and saved as ``auto``; never run as itself. :func:`compile_operation`
    and ``Workflow.run`` resolve it with :func:`infer_verb` against the input
    the step actually gets, and staging shows the verb it would pick now,
    marked provisional.
    """
    raise RuntimeError("auto is resolved to a concrete verb before it runs")


def sweep_(fn: Callable, *, name: str = PAYLOAD, retries: int = 0,
           **params: Sequence[Any]) -> Output:
    """``expand_grid`` — run *fn* over the cross product of named parameters.

    Each swept parameter becomes a **column**, so the result is a tidy table
    you can group and filter by::

        sweep_(plot, model=["a", "b"], window=[7, 30])
        →  model | window | value
    """
    if not isinstance(name, str):
        raise ValueError(
            f"sweep's name= is the payload column and must be a string, got "
            f"{type(name).__name__}. A swept parameter cannot be called 'name' "
            f"— it collides with the verb's own. Rename the tool's parameter, "
            f"or sweep it under another name and bind it."
        )
    if not isinstance(retries, int) or isinstance(retries, bool):
        raise ValueError(
            f"sweep's retries= is a count and must be an int, got "
            f"{type(retries).__name__}. A swept parameter cannot be called "
            f"'retries' — it collides with the verb's own."
        )
    if not params:
        raise ValueError("sweep_ needs at least one parameter list")
    names = list(params)
    combos = list(itertools.product(*(list(params[k]) for k in names)))

    out_rows, records = [], []
    for combo in combos:
        arg = dict(zip(names, combo))
        value, record = _call(fn, arg, retries)
        out_rows.append({**arg, name: value})
        records.append(record)

    data = pd.DataFrame(out_rows)
    grid_shape = tuple(len(params[k]) for k in names)
    return Output(data=data, records=records, index=data.index,
                  meta={"verb": "sweep", "form": "grid", "payload": name,
                        "params": names, "grid": grid_shape,
                        "n_in": len(combos)})


def _own_index(frame: pd.DataFrame, where: str = "the table") -> pd.DataFrame:
    """A loaded table's rows get core's own ids, 0…n-1, in the ``#`` index.

    A column named ``#`` is refused: ``#`` is the row-id column. A
    predefined index (anything but the plain 0, 1, 2 …) becomes an ordinary
    column, keeping its name (``index`` when it has none), so nothing is lost.
    """
    if ROW_ID in [str(c) for c in frame.columns]:
        raise SelectionError(
            f"{where} has a column named {ROW_ID!r}, which is reserved for row "
            f"ids; rename or remove that column")
    index = frame.index
    plain = (isinstance(index, pd.RangeIndex) and index.start == 0 and index.step == 1
             and index.name in (None, ROW_ID))
    if plain:
        return frame
    names = [str(n) if n is not None else ("index" if index.nlevels == 1 else f"index_{i}")
             for i, n in enumerate(index.names)]
    for name in names:
        if name == ROW_ID or name in frame.columns:
            raise SelectionError(
                f"{where}'s index {name!r} would become a column, but "
                f"{'that name is reserved for row ids' if name == ROW_ID else 'a column already has that name'}; "
                f"rename the index or the column")
    out = frame.copy()
    out.index = out.index.set_names(names)
    out = out.reset_index()
    return out


def grid(value: Any) -> Output:
    """Lift any value into an Output so a chain can start from it.

    ``score[mod.map()](grid(df))`` — how a chain begins. A table's own index
    becomes a column; its rows get ids 0…n-1 (see :func:`_own_index`).
    """
    frame = _normalize_missing(_own_index(_str_columns(rows(value), "the source"),
                                          "the source"))
    return Output(
        data=frame,
        records=[{"status": "completed", "error": None, "attempts": 1,
                         "seconds": 0.0} for _ in range(len(frame))], index=frame.index,
        meta={"verb": "source", "form": "column", "payload": None,
              "n_in": len(frame)},
    )


def _no_tool(verb: str, fn: Callable) -> None:
    """Refuse a real tool on a verb that applies none (``source``, ``select``, ``drop``)."""
    if not is_identity(fn):
        raise ValueError(
            f"{verb} applies no tool, but got {getattr(fn, '__name__', fn)!r}. "
            f"It rearranges columns; to compute over them, use map."
        )


def _require_columns(verb: str, frame: pd.DataFrame, names: Sequence[str]) -> None:
    """Refuse a column the frame does not have — a typo must not pass silently."""
    missing = [c for c in names if c not in frame.columns]
    if missing:
        raise KeyError(
            f"{verb} names {', '.join(map(repr, missing))}, which the input does "
            f"not have (it has {', '.join(map(str, frame.columns))})"
        )


def select_(source: Any, fn: Callable = identity, *,
            columns: Any = None, rows: Any = None) -> Output:
    """``select`` — keep these columns, **in this order**. n rows in, n rows out.

    The column-axis mirror of :func:`filter_`: filter chooses rows, select
    chooses columns. Like ``source`` and :func:`drop_` it applies **no tool**,
    which is what makes it buildable while ``colmap`` is not — nothing executes,
    so nothing can fail, so there are no per-column ledger entries and none of
    §5's index-space problems arise.

    Reordering is half the reason to reach for it. To remove columns instead,
    use :func:`drop_` — a separate verb, because "select drop" never read right
    and a verb that does one thing needs no mutually-exclusive arguments.

    You rarely need this *before* a map: column binding already hands a tool only
    the values it declares. Its job is the grid you carry **forward** — ``map``
    passes every input column through, and this is how you narrow what
    downstream sees.
    """
    _no_tool("select", fn)
    row_sel = rows
    if not columns and row_sel is None:
        raise ValueError("select needs columns= or rows=")
    frame = _rows_frame(source)
    if callable(columns):
        # 008 C2: a tool is a predicate on column names.
        columns = [c for c in frame.columns if columns(c)]
    if isinstance(columns, (list, tuple)) and ROW_ID in columns:
        columns = {"names": list(columns)}
    if isinstance(columns, dict) or row_sel is not None:
        # 008 C7/K9: every selection form; kept rows keep their ids.
        data = _apply_selection(frame, row_sel, columns or None,
                                (source.meta.get("step_id") if isinstance(source, Output)
                                 else None) or "the input")
        return _column_output("select", frame, data, index=data.index, source=source)
    _require_columns("select", frame, columns)
    return _column_output("select", frame, frame[list(columns)], source=source)


def drop_(source: Any, fn: Callable = identity, *,
          columns: Sequence[str] | None = None) -> Output:
    """``drop`` — remove these columns, keeping the rest in place.

    The complement of :func:`select_`, and strict about it: dropping a column
    that is not there is a typo, not a no-op, so it raises rather than quietly
    doing nothing.
    """
    _no_tool("drop", fn)
    if not columns:
        raise ValueError("drop needs columns= — the columns to remove")
    frame = rows(source)
    _require_columns("drop", frame, columns)
    return _column_output("drop", frame, frame.drop(columns=list(columns)),
                          source=source)


def _widen_columns(cells: list[Any], records: list[dict]) -> list[str] | None:
    """Column names when none were declared.

    A **sequence** cell (tuple/list) has no field names, so it is named
    positionally ``c0, c1, …`` — the width is the longest completed row. A
    **mapping** cell's fields are *not* guessed: returning ``None`` makes the
    caller raise, because discovering a record's keys at run time is exactly the
    unvalidatable-until-run case ``columns=`` exists to rule out.
    """
    completed = [c for c, r in zip(cells, records) if r["status"] == "completed"]
    if completed and all(isinstance(c, (list, tuple)) for c in completed):
        width = max(len(c) for c in completed)
        return [f"c{i}" for i in range(width)]
    return None


def _widen_cell(cell: Any, wanted: Sequence[str], explicit: bool) -> tuple[dict, str | None]:
    """Lift one cell into the wanted columns, with a per-unit error or None.

    A **mapping** is matched by key, a **sequence** by position. Only an
    *explicitly declared* column that the cell cannot supply is a failure — an
    auto-named ragged row just gets ``None``, since its own width defined the
    columns.
    """
    if isinstance(cell, Mapping):
        values = {c: cell.get(c) for c in wanted}
        missing = [c for c in wanted if c not in cell]
        if explicit and missing:
            have = ", ".join(map(str, cell)) or "nothing"
            return values, (f"KeyError: the record has no "
                            f"{', '.join(map(repr, missing))} (it has {have})")
        return values, None
    if isinstance(cell, (list, tuple)):
        values = {c: (cell[i] if i < len(cell) else None)
                  for i, c in enumerate(wanted)}
        if explicit and len(cell) < len(wanted):
            return values, (f"IndexError: the sequence has {len(cell)} item(s), "
                            f"too few for {len(wanted)} column(s) "
                            f"({', '.join(map(repr, wanted))})")
        return values, None
    return ({c: None for c in wanted},
            f"TypeError: widen needs a mapping per row (or a sequence), "
            f"got {type(cell).__name__}")


def widen_(source: Any, fn: Callable = identity, *,
           columns: Sequence[str] | None = None, retries: int = 0,
           axis: str = "rows") -> Output:
    """``unnest_wider`` — one cell's fields become columns. n rows in, n rows out.

    The column-axis counterpart of :func:`expand_`, and the pair completes the
    unnesting story: ``expand`` makes a collection **longer** (one row per
    element), this makes a record **wider** (one column per field).

        value                          ->  city   temp
        {"city": "SF", "temp": 18}         SF     18

    Two kinds of cell widen, by two matching rules:

    - a **mapping** is matched **by key**, and ``columns=`` is **required** — a
      record's fields live in the data, so guessing them at run time would make
      this the one verb whose column set is unknowable before it runs, which
      `check` and staging both depend on knowing.
    - a **sequence** (tuple/list) is matched **by position**. With ``columns=``
      it names the positions; **without it the columns default to** ``c0, c1,
      …`` (width = the longest row), so a column of tuples widens instead of
      failing. Positional names are unambiguous where a record's keys are not,
      which is why only this case is auto-named.

    Applies **no tool** — ``identity`` resolves which cell holds the record
    (an explicit ``column=``, else ``value``, else the only column). It runs per
    row, so it has a real ledger: a cell that is neither a mapping nor a
    sequence, or an explicitly declared field a cell cannot supply, is a
    **per-unit failure** — inspectable and re-drivable like any other.
    """
    _no_tool("widen", fn)
    frame = rows(source, axis=axis)
    blocked = _upstream_failures(source)

    cells: list[Any] = []
    records: list[dict] = []
    for index, row in _units(frame):
        if index in blocked:
            cells.append(None)
            records.append(_blocked(*blocked[index]))
            continue
        cell, record = _call(fn, row, retries)
        cells.append(cell)
        records.append(record)

    explicit = bool(columns)
    wanted = list(columns) if explicit else _widen_columns(cells, records)
    if wanted is None:
        raise ValueError(
            "widen needs columns= — the fields to lift out of the record. A "
            "record's fields are not guessed; only a tuple/list cell is "
            "auto-named c0, c1, …. Declare the columns, or return a sequence."
        )

    lifted: list[dict] = []
    for cell, record in zip(cells, records):
        if record["status"] != "completed":
            lifted.append({column: None for column in wanted})
            continue
        values, error = _widen_cell(cell, wanted, explicit)
        lifted.append(values)
        if error:
            record["status"] = "failed"
            record["error"] = error

    # Carried columns first, then the fields — the order `map` uses, and the
    # order a reader sees. A field that shadows a carried column wins, because
    # naming it is what the step was asked to do.
    data = frame.copy()
    for column in wanted:
        data[column] = [row[column] for row in lifted]
    return Output(data=data, records=records, index=frame.index,
                  meta={"verb": "widen", "form": "column", "payload": None,
                        "n_in": len(frame), "columns": list(data.columns)})


def slice_(source: Any, fn: Callable = identity, *, start: int = 0,
           stop: int | None = None, at: Sequence[int] | None = None) -> Output:
    """``slice`` — rows **by position**. The one selection no tool can express.

    A tool never sees its row index — not even with ``**row`` — so positional
    selection is not merely verbose without this verb, it is impossible. The
    nearest workaround was to put the position in a column at the source
    (``df.reset_index(names="row_no")``) and ``filter`` on it.

    Two forms, and they are exclusive::

        mod.slice(stop=10)            the first ten rows
        mod.slice(start=5, stop=10)   a half-open range, like Python's
        mod.slice(at=[0, 2, 4])       exactly these positions, in this order

    Applies **no tool**: it chooses rows without computing anything, so nothing
    can fail and the ledger records no attempt — the same reasoning as
    ``select`` and ``drop``.

    **Positional selection is brittle on purpose-built pipelines**: position 2
    is a different row the moment upstream data changes. ``filter`` with a
    predicate survives that and says in its ledger which rows it kept. Reach
    for this for "the first N" and fixed offsets, not for picking records.
    """
    _no_tool("slice", fn)
    if at is not None and (start or stop is not None):
        raise ValueError(
            "slice takes at= or start=/stop=, not both: one names positions, "
            "the other a range."
        )
    frame = rows(source)
    if at is not None:
        out_of_range = [p for p in at if not -len(frame) <= p < len(frame)]
        if out_of_range:
            raise IndexError(
                f"slice at={list(at)} names position(s) {out_of_range}, but the "
                f"input has {len(frame)} row(s)."
            )
        data = frame.iloc[list(at)]
    else:
        data = frame.iloc[start:stop]
    return _column_output("slice", frame, data, index=data.index, source=source)


def rename_(source: Any, fn: Callable = identity, *,
            columns: dict[str, str] | None = None) -> Output:
    """``rename`` — change column names, keeping their order and values.

    The missing piece between a step's output and the next tool's parameter
    names: without it, matching a column to a differently-named parameter took
    a ``map`` over ``identity`` and then a ``select``, two steps of pure
    plumbing. Applies **no tool**.

    Strict about a name that is not there, for the same reason ``drop`` is: it
    is a typo, not a no-op.
    """
    _no_tool("rename", fn)
    if not columns:
        raise ValueError("rename needs columns={old: new}")
    frame = rows(source)
    if callable(columns):
        # 008 C2: a tool maps each column name to its new one.
        columns = {c: columns(c) for c in frame.columns if columns(c) != c}
        if not columns:
            return _column_output("rename", frame, frame, source=source)
    _require_columns("rename", frame, list(columns))
    clashes = [new for new in columns.values()
               if new in frame.columns and new not in columns]
    if clashes:
        raise ValueError(
            f"rename would overwrite existing column(s) "
            f"{', '.join(map(repr, clashes))}. Drop them first, or pick other "
            f"names — silently replacing a column loses it."
        )
    return _column_output("rename", frame, frame.rename(columns=dict(columns)),
                          source=source)


def sort_(source: Any, fn: Callable = identity, *, by: Sequence[str] | None = None,
          ascending: bool = True) -> Output:
    """``sort`` — reorder rows by one or more columns. Same rows, same columns.

    The index travels with its row, so a cell keeps its address and the ledger
    stays joinable — sorting moves rows about without renaming any of them.
    Applies **no tool**.
    """
    _no_tool("sort", fn)
    if not by:
        raise ValueError("sort needs by= — the column(s) to order on")
    frame = rows(source)
    if callable(by):
        # 008 C2: order by a tool's value per row.
        keys = pd.Series(_key_column(frame, by), index=frame.index)
        data = frame.loc[keys.sort_values(ascending=ascending, kind="stable").index]
        return _column_output("sort", frame, data, index=data.index, source=source)
    order = [by] if isinstance(by, str) else list(by)
    _require_columns("sort", frame, order)
    data = frame.sort_values(order, ascending=ascending, kind="stable")
    return _column_output("sort", frame, data, index=data.index, source=source)


def distinct_(source: Any, fn: Callable = identity, *,
              columns: Sequence[str] | None = None) -> Output:
    """``distinct`` — keep the first row of each duplicate group.

    With ``columns``, two rows are duplicates when those columns match; without
    it, when the whole row matches. Keeps the **first** occurrence and its
    index, so what survives is addressable. Applies **no tool**.
    """
    _no_tool("distinct", fn)
    frame = rows(source)
    if callable(columns):
        # 008 C2: two rows are duplicates when the tool gives them the same key.
        keys = pd.Series(_key_column(frame, columns), index=frame.index)
        data = frame.loc[~keys.duplicated(keep="first")]
        return _column_output("distinct", frame, data, index=data.index,
                              source=source)
    if columns:
        _require_columns("distinct", frame, list(columns))
    data = frame.drop_duplicates(subset=list(columns) if columns else None,
                                 keep="first")
    return _column_output("distinct", frame, data, index=data.index,
                          source=source)


def _column_output(verb: str, frame: pd.DataFrame, data: pd.DataFrame,
                   index: Any = None, source: Any = None) -> Output:
    """The Output shared by every verb that rearranges without computing.

    Nothing ran, so every unit is trivially complete and ``attempts: 0`` says
    so. The ledger stays row-aligned, which keeps ``view()`` a clean join.

    *index* is for the verbs that choose **rows** (``slice``, ``sort``,
    ``distinct``): their ledger covers the rows that survived, since a row that
    was never selected has no unit to record. The column verbs leave it alone
    and keep one entry per input row.
    """
    ledger_index = frame.index if index is None else index
    # 008 C10: a row that failed upstream is carried through still failed —
    # rearranging it does not make it a value.
    blocked = _upstream_failures(source)
    records = [_blocked(*blocked[i]) if i in blocked
               else {"status": "completed", "error": None, "attempts": 0,
                     "seconds": 0.0} for i in ledger_index]
    return Output(data=data, records=records, index=ledger_index,
                  meta={"verb": verb, "form": "column", "payload": None,
                        "n_in": len(frame), "columns": list(data.columns)})


def source_(value: Any, fn: Callable = identity, **_params) -> Output:
    """``source`` — start a flow, from a literal or a no-input tool.

    Making this a verb rather than a special case is what closes the algebra:
    every step is then (verb, tool, arguments), the first one included. With the
    default ``identity`` tool it **holds** a literal you assigned. With a real
    tool it **computes** the first grid from the tool's bound arguments and no
    input row — ``load_csv.bind(path=…)[mod.source()]`` — so loading data is a
    step in the workflow, saved and re-runnable, not something done outside it. A
    returned DataFrame becomes the step's rows and columns.
    """
    if is_identity(fn):
        return grid(value)
    # A no-input tool: an empty row lets `_d_apply` fill the bound arguments.
    # A tool that raises is a failed step, like any other unit — it no longer
    # escapes `run` (the run stops on it unless the step catches it).
    try:
        value, caught = _unwrap(fn({}))
    except _Tolerated as exc:
        return _source_failure(str(exc), caught=True)
    except Exception as exc:
        return _source_failure(f"{type(exc).__name__}: {exc}", caught=None)
    out = grid(value)
    if caught is not None:
        out.meta["notes"] = {i: {"error": f"caught {caught}; used the default",
                                 "caught": True} for i in out.data.index}
    return out


def _source_failure(error: str, caught: Any) -> Output:
    return Output(
        data=pd.DataFrame({PAYLOAD: [None]}, index=[0], dtype=object),
        records=[{"status": "failed", "error": error, "attempts": 1,
                         "seconds": 0.0, "caught": caught}], index=[0],
        meta={"verb": "source", "form": "scalar", "payload": None})


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .system_tools import is_identity  # noqa: E402
from .errors import SelectionError  # noqa: E402
from .modifiers import _d_apply  # noqa: E402
from .output import (  # noqa: E402
    Output,
    ROW_ID,
    _blocked,
    _is_missing,
    _normalize_missing,
    _str_columns,
    _typed,
    _upstream_failures,
)
from .references import _apply_selection, rows  # noqa: E402
