"""
Grid — a working prototype of the target model (docs/shape-algebra.md)
======================================================================

Standalone and importable today. It does **not** touch the engine, the
registry or the existing orchestrators, so nothing that works now can break.

**Three names here shadow the engine's**: ``Workflow``, ``Operation`` and
``Step``. Import the module, not the names — ``from simple_steps_core import
grid`` then ``grid.Workflow()`` — so every call site says which model it means.
The point is to have something you can actually call::

    from simple_steps_core.grid import rows, map_, filter_, group_, collapse_, sweep_

    src = rows(pd.DataFrame({"n": [1, 2, 3]}))
    out = map_(src, lambda r: r["n"] * 10, name="score")
    out.view()

Every verb returns an :class:`Output`: a payload grid, a row-aligned ledger,
and some metadata. A tool is a plain function taking one row (a ``dict``) and
returning anything — a number, a DataFrame, a plotly Figure, a MediaAsset.

Deliberately simple where the spec allows it: the ledger is materialized in
full rather than sparse, and nothing is cached. Correctness and legibility
first; both are easy to optimize later and neither is the bottleneck now.
"""

from __future__ import annotations

import inspect
import itertools
import warnings
import time
import traceback
import typing
from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any, Callable, Iterable, Sequence

import pandas as pd

__all__ = [
    "Output", "grid", "rows", "map_", "filter_", "group_", "collapse_",
    "expand_", "sweep_", "source_", "select_", "drop_", "widen_",
    "slice_", "rename_", "sort_", "distinct_",
    "identity", "gather", "count", "total", "first", "last",
    "BUILTIN_TOOLS", "DEFAULT_TOOL", "catalog", "tool_entry",
    "TOOLS",
    "op", "Modifier", "Operation",
    "tool", "ToolHandle", "StepRef", "Step", "Workflow", "check", "stage",
    "STRICT_TYPES", "annotation_problems", "declaration_problems",
    "PARAM_TYPES", "PARAM_TYPES_BY_VERB",
    "ROWS_RULE", "DEFAULT_PAYLOAD", "CARRIES_COLUMNS", "PayloadError",
    "is_identity", "infer_verb",
    "predicted_columns",

    "mod",
    "DECORATORS", "MODIFIERS", "ModifierKind", "SHAPE_VERBS", "is_shape",
    "compile_operation",
    "PAYLOAD", "LEDGER_COLUMNS",
]

#: Default name for the column holding whatever a tool returned.
PAYLOAD = "value"

#: Every ledger has exactly these columns, so the UI can rely on them.
LEDGER_COLUMNS = ("status", "error", "attempts", "seconds", "unit")


# ─────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class Output:
    """What a step produced: a payload grid plus a row-aligned ledger.

    ``data`` holds values and is what downstream steps consume. ``ledger``
    holds execution state and is never consumed as data. They share an index,
    so :meth:`view` is a clean join — see docs/shape-algebra.md §5.
    """

    data: pd.DataFrame
    ledger: pd.DataFrame
    meta: dict = field(default_factory=dict)

    # ── the merged view (the only thing a user needs to look at) ─────────
    def view(self) -> pd.DataFrame:
        """``data`` joined with its ledger — the one table to render."""
        return self.data.join(self.ledger, rsuffix="_run")

    # ── the two halves ───────────────────────────────────────────────────
    @property
    def ok(self) -> pd.DataFrame:
        """Rows that completed."""
        good = self.ledger.index[self.ledger["status"] == "completed"]
        return self.data.loc[self.data.index.intersection(good)]

    @property
    def failed(self) -> pd.DataFrame:
        """Ledger rows that failed — the re-drive set, with their errors."""
        return self.ledger[self.ledger["status"] == "failed"]

    @property
    def values(self) -> list[Any]:
        """The payload column as a plain list, for the common case."""
        column = self.meta.get("payload")
        return [] if column is None else list(self.data[column])

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
        done = int((self.ledger["status"] == "completed").sum())
        return f"{done}/{len(self.ledger)}"

    def __repr__(self) -> str:
        verb = self.meta.get("verb", "?")
        failed = len(self.failed)
        tail = f", {failed} failed" if failed else ""
        return (f"<Output {verb} · {len(self.data)} row(s) × "
                f"{len(self.data.columns)} col(s){tail}>")


def _ledger(records: list[dict], index: Sequence[Any]) -> pd.DataFrame:
    """Build a ledger with the standard columns, even when empty."""
    frame = pd.DataFrame(records, index=pd.Index(index, name=None))
    for column in LEDGER_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    return frame[list(LEDGER_COLUMNS)]


# ─────────────────────────────────────────────────────────────────────────
# identity — the tool that closes the algebra
# ─────────────────────────────────────────────────────────────────────────
def is_identity(fn: Callable) -> bool:
    """True when *fn* is :func:`identity`, through any adapter wrapping it."""
    seen = 0
    while fn is not None and seen < 10:
        if fn is identity:
            return True
        fn, seen = getattr(fn, "__wrapped__", None), seen + 1
    return False


def identity(**row: Any) -> Any:
    """Return what the previous step produced — the default tool.

    Every step is a verb applied to a tool, with no special case for the steps
    that only *reshape*: those apply a verb to ``identity``. ``expand`` over it
    flattens a level, ``filter`` over it keeps what is already truthy, and
    ``source`` over it lifts a literal.

    **It returns the payload, not the row.** A tool here receives a whole row
    (``{"n": 1, "value": [2, 3]}``), but the reshaping verbs need the *cell*
    the previous step produced — returning the row would make
    ``filter``+identity keep everything (a non-empty dict is truthy) and
    ``expand``+identity flatten nothing (a dict is not unpacked). So the
    payload is resolved by convention:

    1. an explicit ``column``, when the step named one;
    2. the ``value`` column, which is what the verbs write by default;
    3. the only column, when the row has exactly one;
    4. otherwise the whole row — nothing else is well defined.

    Case 4 is the honest limit: after ``map(name="score")`` the payload is
    ``score`` and no convention can know it, so bind it —
    ``op("identity", column="score")``.

    ``collapse`` is the exception to all of this: it needs a two-argument
    reducer, so there is nothing for identity to mean there.
    """
    column = row.pop("column", None)
    if column is not None:
        return row[column]
    if PAYLOAD in row:
        return row[PAYLOAD]
    if len(row) == 1:
        return next(iter(row.values()))
    return row


def gather(acc: Any = None, **row: Any) -> list:
    """Collect every payload into one list.

    The default tool for ``collapse``. Where ``identity`` is the map that
    discards nothing, this is the **reduction** that discards nothing — so
    ``collapse`` needs no bespoke tool just to bring a column together, and it
    becomes the exact inverse of ``expand``: a cell holding ``[1, 2, 3]``
    expands to three rows, and three rows gather back into that cell.

    Takes the accumulator first, like every reducer, and resolves each row's
    payload the same way :func:`identity` does — so it works on any grid, not
    only one whose payload column happens to be called ``value``.
    """
    return [*(acc or []), identity(**row)]


def count(acc: Any = None, **row: Any) -> int:
    """How many rows reached this step. Ignores the values entirely."""
    return (acc or 0) + 1


def total(acc: Any = None, **row: Any) -> float:
    """Sum of the payloads. Raises on a payload that will not add."""
    return (acc or 0) + identity(**row)


def first(acc: Any = None, **row: Any) -> Any:
    """The first payload, in row order. Later rows are ignored."""
    return identity(**row) if acc is None else acc


def last(acc: Any = None, **row: Any) -> Any:
    """The last payload, in row order."""
    return identity(**row)


#: Tools every Operation can name without being handed a registry, and the
#: defaults a bare modifier resolves to. A user may name any of these by id in
#: place of their own function — they are the reductions and pass-throughs that
#: would otherwise be written by hand in every workflow.
BUILTIN_TOOLS: dict[str, Callable] = {
    "identity": identity,
    "gather": gather,
    "count": count,
    "total": total,
    "first": first,
    "last": last,
}


#: The tool a shape verb applies when none is named — *the one that discards
#: nothing*. For every verb that maps, that is ``identity``; for ``collapse``,
#: whose tool takes an accumulator first, it is ``gather``. The arity is why one
#: cannot stand in for the other.
DEFAULT_TOOL: dict[str, str] = {
    "source": "identity", "select": "identity", "drop": "identity",
    "widen": "identity", "slice": "identity", "rename": "identity",
    "sort": "identity", "distinct": "identity",
    "map": "identity", "filter": "identity", "group": "identity",
    "expand": "identity", "collapse": "gather",
}


#: Whether ``@tool`` requires a type annotation on every parameter and on the
#: return. Off by default so tools written before the rule existed keep working;
#: a project that wants the guarantee everywhere sets this once, at import time,
#: before declaring anything. ``@tool(strict=True)`` opts in one tool at a time.
#:
#: What the annotations buy, and why it is worth the keystrokes: they are the
#: only description of a step's boundary that both a human and the machine read.
#: ``check`` compares them against the upstream's real dtypes
#: (:func:`_dtype_problems`), and ``catalog`` publishes them, so a palette can
#: say what a tool takes and returns instead of only naming its parameters.
STRICT_TYPES: bool = False


def _type_name(annotation: Any) -> str | None:
    """A readable name for an annotation — ``None`` when there is not one."""
    if annotation is inspect.Parameter.empty:
        return None
    if isinstance(annotation, str):                  # from __future__ annotations
        return annotation
    return (getattr(annotation, "__name__", None)
            or str(annotation).replace("typing.", ""))


def annotation_problems(fn: Callable) -> list[str]:
    """What is unannotated about *fn*. Empty when it is fully typed.

    ``**kwargs`` and ``*args`` are exempt: a tool that takes the whole row has
    no per-column parameter to type, and the row's columns are not knowable from
    the signature.
    """
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):                  # builtins have no signature
        return ["its signature cannot be read"]

    untyped = [p.name for p in signature.parameters.values()
               if p.kind not in (inspect.Parameter.VAR_KEYWORD,
                                 inspect.Parameter.VAR_POSITIONAL)
               and p.annotation is inspect.Parameter.empty]
    problems = []
    if untyped:
        plural = "s" if len(untyped) > 1 else ""
        problems.append(
            f"parameter{plural} {', '.join(map(repr, untyped))} "
            f"{'have' if plural else 'has'} no type annotation"
        )
    if signature.return_annotation is inspect.Signature.empty:
        problems.append("it has no return annotation")
    return problems


def declaration_problems(fn: Callable, tool_id: str) -> list[str]:
    """What makes *fn* undrivable as a tool. Empty when it is well formed.

    Every rule here catches something that currently fails **late** — three of
    them with a wrong answer and no error — and none of them rejects a tool
    anyone would write on purpose. See writing-tools.md §2.2.
    """
    problems: list[str] = []
    if not tool_id.isidentifier():
        problems.append(
            f"{tool_id!r} is not a valid identifier, so it cannot be a stable "
            f"id in a palette, a JSON key, or a dropdown label"
            + (" (every lambda would collide on '<lambda>')"
               if tool_id == "<lambda>" else "")
            + ". Pass id= to name it"
        )
    try:
        parameters = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return problems + ["its signature cannot be read, so columns cannot bind"]

    positional_only = [p.name for p in parameters
                       if p.kind is inspect.Parameter.POSITIONAL_ONLY]
    if positional_only:
        problems.append(
            f"parameter{'s' if len(positional_only) > 1 else ''} "
            f"{', '.join(map(repr, positional_only))} "
            f"{'are' if len(positional_only) > 1 else 'is'} positional-only, "
            "and columns bind by name — nothing could ever fill them"
        )
    var_positional = [p.name for p in parameters
                      if p.kind is inspect.Parameter.VAR_POSITIONAL]
    if var_positional:
        problems.append(
            f"*{var_positional[0]} declares no names, so the tool would be "
            "called with no arguments at all and return a plausible wrong "
            "answer. Declare the values it needs, or take **kwargs for the "
            "whole row"
        )
    mutable = [p.name for p in parameters
               if isinstance(p.default, (list, dict, set, bytearray))]
    if mutable:
        problems.append(
            f"parameter{'s' if len(mutable) > 1 else ''} "
            f"{', '.join(map(repr, mutable))} "
            f"{'have' if len(mutable) > 1 else 'has'} a mutable default, which "
            "makes the tool stateful across runs — a step has to be re-runnable"
        )
    return problems


def _value_fits(value: Any, annotation: Any) -> bool | None:
    """Does one literal fit an annotation? ``None`` when it cannot be decided."""
    origin = typing.get_origin(annotation) or annotation
    if not isinstance(origin, type) or origin is object:
        return None                                  # Any, unions, protocols…
    if origin is float and isinstance(value, int) and not isinstance(value, bool):
        return True                                  # an int is a fine float
    return isinstance(value, origin)


def _column_fits(series: pd.Series, annotation: Any) -> bool | None:
    """Does a column's dtype fit an annotation? ``None`` when undecidable.

    Deliberately asymmetric: it returns ``False`` only when the mismatch is
    certain, because a false positive here would refuse a step that works. A
    numeric dtype answers exactly; an object column is decided by its first
    non-null value, which is the most an unparameterized ``object`` dtype can
    tell us.
    """
    origin = typing.get_origin(annotation) or annotation
    if not isinstance(origin, type) or origin is object:
        return None
    kind = getattr(series.dtype, "kind", None)
    if kind is None:
        return None
    if origin is bool:
        return kind == "b"
    if origin is int:
        return kind in "iu"
    if origin is float:
        return kind in "iufc"                        # an int column fits a float
    if kind != "O":                                  # a real dtype, a non-numeric annotation
        return False if origin in (str, list, tuple, dict, set) else None
    present = series.dropna()
    if present.empty:
        return None
    return isinstance(present.iloc[0], origin)


def tool_entry(tool_id: str, fn: Callable, origin: str) -> dict:
    """One tool as a palette entry: what it is, where it came from, what it takes.

    ``description`` is the docstring's first line, which is why those first
    lines are written as user-facing sentences rather than developer notes.
    ``origin`` lets a client separate the system's tools from the user's — the
    builtins are always available and rarely what someone is looking for, so a
    palette usually groups or hides them.
    """
    doc = (inspect.getdoc(fn) or "").strip()
    try:
        signature = inspect.signature(fn)
        parameters = list(signature.parameters.values())
        returns = _type_name(signature.return_annotation)
    except (TypeError, ValueError):
        parameters, returns = [], None

    params, takes_row = [], False
    for parameter in parameters:
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            takes_row = True
            continue
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        required = parameter.default is inspect.Parameter.empty
        params.append({
            "name": parameter.name,
            "required": required,
            "default": None if required else parameter.default,
            # The declared type, or None when the tool left it off. A palette
            # shows this so a user knows what a step consumes before wiring it.
            "type": _type_name(parameter.annotation),
        })

    return {
        "tool_id": tool_id,
        "description": doc.split("\n", 1)[0] if doc else "",
        "origin": origin,
        "params": params,
        #: The declared return type, or None. With `params` above, this is the
        #: tool's whole boundary: what goes in, what comes out.
        "returns": returns,
        #: True when every parameter and the return are annotated.
        "typed": not annotation_problems(fn),
        # True when the tool declares **kwargs, so it receives every column and
        # `check` cannot verify its inputs against the upstream (§4).
        "takes_whole_row": takes_row,
    }


def catalog(tools: dict[str, Callable] | None = None) -> dict[str, dict]:
    """Every callable tool, id → :func:`tool_entry`, for a palette.

    Feeds the ``GET /tools`` response (docs/react-api.md §2). A user tool cannot
    shadow a builtin, so an id appears exactly once and ``origin`` is
    unambiguous.
    """
    entries = {}
    for name, fn in sorted(BUILTIN_TOOLS.items()):
        entries[name] = tool_entry(name, fn, "builtin")
    for name, fn in sorted({**TOOLS, **(tools or {})}.items()):
        entries[name] = tool_entry(name, fn, "declared")
    return entries


# ─────────────────────────────────────────────────────────────────────────
# Input coercion — "what is a row?"
# ─────────────────────────────────────────────────────────────────────────
def rows(value: Any, *, axis: str = "rows") -> pd.DataFrame:
    """Coerce any step input into a frame of rows.

    Rows, specifically — not "units of work". Which slice serves as the unit is
    the verb's choice (docs/shape-algebra.md §1.0); every verb built so far
    picks the row, but the coercion here is only about producing a frame.

    A DataFrame yields its rows (or its columns with ``axis="columns"``);
    an Output yields its payload grid; a mapping yields one row per entry with
    the key kept; anything else iterable yields one row per element.
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
    if isinstance(value, dict):
        # Keys are kept as the index — a named set of tables stays named.
        return pd.DataFrame({PAYLOAD: list(value.values())},
                            index=list(value.keys()))
    if isinstance(value, (str, bytes)):
        raise TypeError(
            f"Cannot fan out over the string {value!r}: a string is not a "
            "collection."
        )
    if isinstance(value, Iterable):
        return pd.DataFrame({PAYLOAD: list(value)})
    return pd.DataFrame({PAYLOAD: [value]})


def _as_arg(row: pd.Series) -> dict:
    """What a tool receives for one row: a plain dict, never a Series."""
    return row.to_dict()


def _call(fn: Callable, arg: dict, retries: int) -> tuple[Any, dict]:
    """Run *fn* for one unit, returning (value, ledger record)."""
    started = time.perf_counter()
    attempt = 0
    while True:
        try:
            value = fn(arg)
            return value, {"status": "completed", "error": None,
                           "attempts": attempt + 1,
                           "seconds": round(time.perf_counter() - started, 6)}
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
         retries: int = 0, axis: str = "rows") -> Output:
    """``mutate`` — n rows in, n rows out, with *fn*'s result as a new column.

    The input columns are **kept**, which is the point: mapping a score over a
    table gives you the table plus a score, not a bare list of scores.
    """
    frame = rows(source, axis=axis)
    values, records = [], []
    for _index, row in frame.iterrows():
        value, record = _call(fn, _as_arg(row), retries)
        values.append(value)
        records.append(record)

    data = frame.copy()
    data[name] = values
    return Output(data=data, ledger=_ledger(records, frame.index),
                  meta={"verb": "map", "form": "column", "payload": name,
                        "n_in": len(frame)})


def filter_(source: Any, fn: Callable, *, retries: int = 0,
            axis: str = "rows") -> Output:
    """``filter`` — keep the rows where *fn* is truthy. Columns unchanged.

    The ledger keeps **all** units, so a row that was excluded (or whose
    predicate raised) is still visible and re-drivable; ``kept`` says which.
    """
    frame = rows(source, axis=axis)
    keep, records = [], []
    for _index, row in frame.iterrows():
        value, record = _call(fn, _as_arg(row), retries)
        passed = bool(value) and record["status"] == "completed"
        record["kept"] = passed
        keep.append(passed)
        records.append(record)

    ledger = _ledger(records, frame.index)
    ledger["kept"] = keep
    data = frame[pd.Series(keep, index=frame.index)]
    return Output(data=data, ledger=ledger,
                  meta={"verb": "filter", "form": "column",
                        "payload": None, "n_in": len(frame),
                        "n_dropped": len(frame) - len(data)})


def group_(source: Any, fn: Callable, *, name: str = "group",
           retries: int = 0, axis: str = "rows") -> Output:
    """``group_by`` — mark each row with a key. n rows in, n rows out.

    No nesting: reduction is :func:`collapse_` with ``by=name``.
    """
    frame = rows(source, axis=axis)
    keys, records = [], []
    for _index, row in frame.iterrows():
        value, record = _call(fn, _as_arg(row), retries)
        keys.append(value)
        records.append(record)

    data = frame.copy()
    data[name] = keys
    return Output(data=data, ledger=_ledger(records, frame.index),
                  meta={"verb": "group", "form": "column", "payload": name,
                        "key": name, "n_in": len(frame)})


def collapse_(source: Any, fn: Callable, *, by: str | None = None,
              initial: Any = None, name: str = PAYLOAD) -> Output:
    """``summarise`` — reduce to one row, or one row per ``by`` group.

    *fn* takes ``(accumulator, row_dict)``. With ``by`` it runs per group and
    the result carries the group key as a column.
    """
    frame = rows(source)
    groups = ([(None, frame)] if by is None
              else list(frame.groupby(by, sort=False)))

    out_rows, records, index = [], [], []
    for position, (key, chunk) in enumerate(groups):
        started = time.perf_counter()
        accumulator, error = initial, None
        try:
            for _index, row in chunk.iterrows():
                accumulator = fn(accumulator, _as_arg(row))
            status = "completed"
        except Exception as exc:
            status, accumulator = "failed", None
            error = f"{type(exc).__name__}: {exc}"

        row_out = {name: accumulator}
        if by is not None:
            row_out[by] = key
        out_rows.append(row_out)
        records.append({"status": status, "error": error, "attempts": 1,
                        "seconds": round(time.perf_counter() - started, 6),
                        "unit": list(chunk.index)})
        index.append(position)

    data = pd.DataFrame(out_rows, index=index)
    if by is not None:                       # key first reads better
        data = data[[by, name]]
    return Output(data=data, ledger=_ledger(records, index),
                  meta={"verb": "collapse", "form": "scalar" if by is None
                        else "column", "payload": name, "by": by,
                        "n_in": len(frame)})


def expand_(source: Any, fn: Callable, *, name: str = PAYLOAD,
            retries: int = 0, axis: str = "rows") -> Output:
    """``unnest`` — each unit yields an iterable; results are concatenated.

    Output rows outnumber units, so they cannot share the input's index: each
    row records which unit produced it in the ledger's ``source`` column.
    """
    frame = rows(source, axis=axis)
    out_rows, records = [], []
    for index, row in frame.iterrows():
        arg = _as_arg(row)
        produced, record = _call(fn, arg, retries)
        if record["status"] != "completed":
            records.append({**record, "unit": index})
            out_rows.append({**arg, name: None})
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
            out_rows.append({**arg, name: None})
            continue
        items = (list(produced)
                 if isinstance(produced, Iterable)
                 and not isinstance(produced, (str, bytes, dict))
                 else [produced])
        for item in items:
            out_rows.append({**arg, name: item})
            records.append({**record, "unit": index})

    data = pd.DataFrame(out_rows).reset_index(drop=True)
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
        data = frame.iloc[:0].copy().reset_index(drop=True)
        data[name] = pd.Series([], dtype=object)
    return Output(data=data, ledger=_ledger(records, data.index),
                  meta={"verb": "expand", "form": "column", "payload": name,
                        "n_in": len(frame)})


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
    return Output(data=data, ledger=_ledger(records, data.index),
                  meta={"verb": "sweep", "form": "grid", "payload": name,
                        "params": names, "grid": grid_shape,
                        "n_in": len(combos)})


def grid(value: Any) -> Output:
    """Lift any value into an Output so a chain can start from it.

    ``score[mod.map()](grid(df))`` — how a chain begins.
    """
    frame = rows(value)
    return Output(
        data=frame,
        ledger=_ledger([{"status": "completed", "error": None, "attempts": 1,
                         "seconds": 0.0} for _ in range(len(frame))], frame.index),
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
            columns: Sequence[str] | None = None) -> Output:
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
    if not columns:
        raise ValueError("select needs columns= — the columns to keep")
    frame = rows(source)
    _require_columns("select", frame, columns)
    return _column_output("select", frame, frame[list(columns)])


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
    return _column_output("drop", frame, frame.drop(columns=list(columns)))


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

    cells: list[Any] = []
    records: list[dict] = []
    for _index, row in frame.iterrows():
        cell, record = _call(fn, _as_arg(row), retries)
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
    return Output(data=data, ledger=_ledger(records, frame.index),
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
    return _column_output("slice", frame, data, index=data.index)


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
    _require_columns("rename", frame, list(columns))
    clashes = [new for new in columns.values()
               if new in frame.columns and new not in columns]
    if clashes:
        raise ValueError(
            f"rename would overwrite existing column(s) "
            f"{', '.join(map(repr, clashes))}. Drop them first, or pick other "
            f"names — silently replacing a column loses it."
        )
    return _column_output("rename", frame, frame.rename(columns=dict(columns)))


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
    order = [by] if isinstance(by, str) else list(by)
    frame = rows(source)
    _require_columns("sort", frame, order)
    data = frame.sort_values(order, ascending=ascending, kind="stable")
    return _column_output("sort", frame, data, index=data.index)


def distinct_(source: Any, fn: Callable = identity, *,
              columns: Sequence[str] | None = None) -> Output:
    """``distinct`` — keep the first row of each duplicate group.

    With ``columns``, two rows are duplicates when those columns match; without
    it, when the whole row matches. Keeps the **first** occurrence and its
    index, so what survives is addressable. Applies **no tool**.
    """
    _no_tool("distinct", fn)
    frame = rows(source)
    if columns:
        _require_columns("distinct", frame, list(columns))
    data = frame.drop_duplicates(subset=list(columns) if columns else None,
                                 keep="first")
    return _column_output("distinct", frame, data, index=data.index)


def _column_output(verb: str, frame: pd.DataFrame, data: pd.DataFrame,
                   index: Any = None) -> Output:
    """The Output shared by every verb that rearranges without computing.

    Nothing ran, so every unit is trivially complete and ``attempts: 0`` says
    so. The ledger stays row-aligned, which keeps ``view()`` a clean join.

    *index* is for the verbs that choose **rows** (``slice``, ``sort``,
    ``distinct``): their ledger covers the rows that survived, since a row that
    was never selected has no unit to record. The column verbs leave it alone
    and keep one entry per input row.
    """
    ledger_index = frame.index if index is None else index
    records = [{"status": "completed", "error": None, "attempts": 0,
                "seconds": 0.0} for _ in range(len(ledger_index))]
    return Output(data=data, ledger=_ledger(records, ledger_index),
                  meta={"verb": verb, "form": "column", "payload": None,
                        "n_in": len(frame), "columns": list(data.columns)})


def source_(value: Any, fn: Callable = identity, **_params) -> Output:
    """``source`` — lift a literal into a grid. The verb a flow starts with.

    Making this a verb rather than a special case is what closes the algebra:
    every step is then (verb, tool, arguments), the first one included. Its
    tool is ``identity``, because a source step *holds* data rather than
    computing it — applying a real tool is a ``map``, and refusing it here
    keeps the two from blurring.
    """
    if not is_identity(fn):
        raise ValueError(
            f"source applies no tool, but got {getattr(fn, '__name__', fn)!r}. "
            "A source step holds its data; to compute over it, use map."
        )
    return grid(value)


# ─────────────────────────────────────────────────────────────────────────
# Compiling a stack into real runtime decorators
# ─────────────────────────────────────────────────────────────────────────
# The stack is stored as data so staging and serialization work. At run time
# it is *applied* — each modifier is a genuine higher-order function, wrapped
# innermost-first, exactly as `@` would have done at definition time.
#
# Two kinds, distinguished by what they do to the signature:
#   shape verbs       lift it:      (a -> b)  becomes  ([a] -> Output)
#   execution mods    preserve it:  (a -> b)  stays    (a -> b)


def _d_retry(fn: Callable, *, times: int) -> Callable:
    """Preserves the signature; retries whatever it wraps."""
    def run(x):
        last = None
        for _ in range(times + 1):
            try:
                return fn(x)
            except Exception as exc:
                last = exc
        raise last
    run.__name__ = f"retry({getattr(fn, '__name__', 'fn')})"
    return run


def _d_timeout(fn: Callable, *, seconds: float) -> Callable:
    """Placeholder: records intent. Real enforcement needs the async engine."""
    def run(x):
        return fn(x)
    run.__name__ = f"timeout({getattr(fn, '__name__', 'fn')})"
    return run


def _d_apply(fn: Callable, **literals) -> Callable:
    """Innermost decoration: hand the tool the columns it actually asked for.

    **Supplying rows is the modifier's job, not the tool's.** A tool declares
    the values it needs and nothing else::

        @tool
        def score(n, weight=1):        # not  def score(row): row["n"] * 10
            return n * 10 * weight

    ``map`` then binds each row's columns to those parameters by name — the
    same thing the engine's ``_run_item`` does when it sets ``kwargs[arg] =
    item``. Without this a tool has to name the row twice, once as a parameter
    and once as a lookup, which makes it unusable unmapped and hard-codes the
    column name in the body.

    Rules:

    * columns bind to parameters **by name**; anything the tool does not
      declare is simply not passed;
    * a tool with ``**kwargs`` receives the whole row, for the cases that
      genuinely want it (``identity``);
    * bound literals fill the rest, and a column **wins** a name collision,
      because the unit is the row here and the unit wins — the engine's rule;
    * a non-dict input (an unorchestrated step over a bare value) is passed
      positionally, since there are no columns to bind.

    ``*leading`` carries ``collapse``'s accumulator, the one verb whose tool
    takes something before the row.
    """
    try:
        parameters = inspect.signature(fn).parameters
    except (TypeError, ValueError):                  # builtins have no signature
        parameters = {}
    wants_everything = any(p.kind is inspect.Parameter.VAR_KEYWORD
                           for p in parameters.values())
    declared = set(parameters)

    def run(*args):
        *leading, row = args
        if not isinstance(row, dict):
            return fn(*leading, row, **literals)
        merged = {**literals, **row}
        bound = merged if wants_everything else {
            k: v for k, v in merged.items() if k in declared
        }
        return fn(*leading, **bound)

    run.__name__ = f"apply({getattr(fn, '__name__', 'fn')})"
    # The verbs that apply no tool (source, select) need to recognize identity
    # through this wrapper — compile_operation always applies it, so comparing
    # against the bare function would never match.
    run.__wrapped__ = fn
    return run


def _lift(verb: Callable) -> Callable:
    """Turn a verb into a decorator that lifts (a -> b) into (source -> Output)."""
    def make(fn: Callable, **params) -> Callable:
        params.pop("over", None)          # `over` names the source, not a param
        def run(source):
            return verb(source, fn, **params)
        run.__name__ = f"{verb.__name__.rstrip('_')}({getattr(fn, '__name__', 'fn')})"
        return run
    return make


@dataclass(frozen=True)
class ModifierKind:
    """One entry in the modifier vocabulary: its class, and how it applies.

    ``cls`` is not taxonomy — it says what the modifier does to the signature
    it wraps, which is what lets staging fold shape *without running*:

    ``"shape"``
        lifts it — ``(row -> b)`` becomes ``(source -> Output)``. Changes rows
        or columns, so staging must fold it.
    ``"execution"``
        preserves it — ``(row -> b)`` stays ``(row -> b)``. Shape-preserving,
        so staging ignores it entirely.
    """

    name: str
    cls: str                     # "shape" | "execution"
    apply: Callable              # (fn, **params) -> fn
    #: The parameter names this kind accepts, derived from the underlying verb
    #: or decorator. ``None`` means "anything" — only ``sweep``, whose
    #: parameters *are* the user's own names.
    accepts: frozenset[str] | None = None


def _accepted_params(fn: Callable, extra: Sequence[str] = ()) -> frozenset[str] | None:
    """Keyword names *fn* takes, or None when it takes arbitrary ones."""
    try:
        parameters = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return None
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return None                              # sweep: the params are the data
    names = {p.name for p in parameters
             if p.kind in (inspect.Parameter.KEYWORD_ONLY,
                           inspect.Parameter.POSITIONAL_OR_KEYWORD)}
    return frozenset(names - {"source", "fn"} | set(extra))


def _kind(name: str, cls: str, apply: Callable,
          verb: Callable | None = None) -> ModifierKind:
    # `over` names the step this modifier reads; every shape verb takes it even
    # though the verb function itself never sees it (`_lift` pops it).
    extra = ("over",) if cls == "shape" else ()
    return ModifierKind(name, cls, apply,
                        _accepted_params(verb, extra) if verb else None)


def _lift_generated(verb: Callable) -> Callable:
    """Like :func:`_lift`, for a verb that *generates* its rows.

    ``sweep`` builds its grid from parameter lists, so it has no input to
    coerce — it still takes a source argument, and still ignores it, so that
    every compiled stack has one uniform signature.
    """
    def make(fn: Callable, **params) -> Callable:
        params.pop("over", None)
        def run(_source: Any = None):
            return verb(fn, **params)
        run.__name__ = f"{verb.__name__.rstrip('_')}({getattr(fn, '__name__', 'fn')})"
        return run
    return make


#: **The modifier vocabulary — the one place a modifier kind is declared.**
#: Adding a verb means adding one entry here; the classification, the
#: validation in ``mod``, and the runtime decorators all derive from it, so
#: there is no second list to keep in step.
MODIFIERS: dict[str, ModifierKind] = {k.name: k for k in (
    # shape verbs — at most one decides the step's final shape (§1.1)
    _kind("source",   "shape", _lift(source_), source_),
    _kind("map",      "shape", _lift(map_), map_),
    _kind("filter",   "shape", _lift(filter_), filter_),
    _kind("select",   "shape", _lift(select_), select_),
    _kind("drop",     "shape", _lift(drop_), drop_),
    _kind("widen",    "shape", _lift(widen_), widen_),
    _kind("slice",    "shape", _lift(slice_), slice_),
    _kind("rename",   "shape", _lift(rename_), rename_),
    _kind("sort",     "shape", _lift(sort_), sort_),
    _kind("distinct", "shape", _lift(distinct_), distinct_),
    _kind("group",    "shape", _lift(group_), group_),
    _kind("expand",   "shape", _lift(expand_), expand_),
    _kind("collapse", "shape", _lift(collapse_), collapse_),
    _kind("sweep",    "shape", _lift_generated(sweep_), sweep_),
    # execution modifiers — shape-preserving
    _kind("retry",    "execution", _d_retry, _d_retry),
    _kind("timeout",  "execution", _d_timeout, _d_timeout),
)}


#: What type each modifier parameter must be. Checked at declaration, because
#: staging reads several of them to predict columns — a list where a column
#: *name* belongs used to crash inside `stage()` with `unhashable type: 'list'`,
#: which named neither the parameter nor the verb.
PARAM_TYPES: dict[str, tuple[type, ...]] = {
    "name": (str,),
    "by": (str,),
    "axis": (str,),
    "retries": (int,),
    "times": (int,),
    "seconds": (int, float),
    "columns": (list, tuple, dict),
    "start": (int,),
    "stop": (int,),
    "at": (list, tuple),
    "ascending": (bool,),
}

#: Where one verb means something different by the same parameter name.
#: ``collapse(by=)`` is a single grouping column — it becomes a column name in
#: the output, so it must be hashable. ``sort(by=)`` is an ordering, which is
#: naturally several columns.
PARAM_TYPES_BY_VERB: dict[str, dict[str, tuple[type, ...]]] = {
    "sort": {"by": (str, list, tuple)},
}





#: The shape verbs, derived — never written out a second time.
SHAPE_VERBS: tuple[str, ...] = tuple(
    name for name, kind in MODIFIERS.items() if kind.cls == "shape"
)


def is_shape(kind: str) -> bool:
    """Does this modifier kind change the grid's shape?"""
    return kind in MODIFIERS and MODIFIERS[kind].cls == "shape"


#: kind -> decorator factory, derived from :data:`MODIFIERS`.
DECORATORS: dict[str, Callable] = {n: k.apply for n, k in MODIFIERS.items()}

# ─────────────────────────────────────────────────────────────────────────
# The deferred half: a stack of modifiers, as data
# ─────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, eq=False)
class Modifier:
    """One entry in an Operation's stack: what to apply, and with what.

    ``params`` may hold a :class:`StepRef` wherever a step id goes. The ref is
    kept **as the ref** — it is flattened to its id only at the JSON boundary
    (:meth:`Operation.to_dict`) — because a ref knows which `Workflow` it was
    read from and a bare id does not. That is the whole provenance mechanism:
    not a second field to carry, just information this class declines to throw
    away. Everything that reads a step id does so through ``str()``, which is
    why holding the richer object costs nothing.
    """

    kind: str
    params: dict = field(default_factory=dict)

    def __eq__(self, other: Any) -> bool:
        """Equal when they name the same step — however it was named.

        ``mod.map(over=wf["raw"])`` and ``mod.map(over="raw")`` are the same
        modifier, so equality compares the flattened params. Hand-written
        because the dataclass default would call a `StepRef` different from its
        own id and break every round-trip comparison.
        """
        if not isinstance(other, Modifier):
            return NotImplemented
        return (self.kind == other.kind
                and _deref(self.params) == _deref(other.params))

    @property
    def cls(self) -> str:
        """``"shape"``, ``"execution"``, or ``"unknown"`` for an unregistered kind."""
        entry = MODIFIERS.get(self.kind)
        return entry.cls if entry else "unknown"

    @property
    def is_shape(self) -> bool:
        return self.cls == "shape"

    def __repr__(self) -> str:
        # Flattened, for the same reason __eq__ is: how a step was named is not
        # part of what this modifier says, so a repr must not depend on it.
        args = ", ".join(f"{k}={v!r}" for k, v in _deref(self.params).items())
        return f"{self.kind}({args})"


@dataclass(frozen=True)
class Operation:
    """One tool plus an ordered stack of modifiers — **data, not closures**.

    Built by decorating: ``score[mod.map(over="step1"), mod.retry(times=2)]``
    is ``map(retry(score))`` — retry runs per item. The list reads outermost
    first, like stacked ``@`` lines; :attr:`modifiers` stores it innermost
    first (§1.1), and :attr:`layers` gives it back in written order.
    """

    tool_id: str
    modifiers: tuple[Modifier, ...] = ()
    arguments: dict = field(default_factory=dict)
    #: The undecorated function, when this came from a ``@tool`` handle — so a
    #: decorated tool can be applied to data without a registry lookup.
    #: ``compare=False``: it is a convenience, never part of the step's data,
    #: so two Operations built the same way stay equal whether or not they
    #: happen to be carrying it.
    fn: Callable | None = field(default=None, compare=False, repr=False)

    def _add(self, kind: str, **params) -> "Operation":
        return Operation(self.tool_id,
                         self.modifiers + (Modifier(kind, params),),
                         self.arguments,
                         self.fn)

    def __getitem__(self, modifiers: Any) -> "Operation":
        """``score[mod.map(over=videos), mod.retry(times=2)]`` — decorate.

        Reads top-to-bottom like stacked ``@`` lines (outermost first) and is
        applied bottom-up, so the **last** layer listed sits closest to the
        tool. Unlike ``@``, nothing is attached to the function and nothing is
        applied: the result is the same :class:`Operation` *data* the chained
        form builds, so the same tool stays usable bare in one step and mapped
        in another. See docs/shape-algebra.md §6.
        """
        # `x[m]` passes the modifier itself; `x[m1, m2]` passes a tuple.
        if not isinstance(modifiers, tuple):
            modifiers = (modifiers,)
        operation = self
        for modifier in reversed(modifiers):          # bottom-up, like decorators
            if not isinstance(modifier, Modifier):
                raise TypeError(
                    "a bracket layer must be a Modifier — mod.map(over=...), "
                    f"mod.retry(times=...); got {type(modifier).__name__}. "
                    "Modifiers are data; a plain decorator would not serialize."
                )
            operation = operation._add(modifier.kind, **modifier.params)
        return operation

    @property
    def layers(self) -> tuple[Modifier, ...]:
        """The stack in **written** order — outermost first, as the brackets read.

        The exact reverse of :attr:`modifiers`, which is stored innermost-first
        (§1.1). Anything that shows a user their own stack — a repr, a list
        editor, a diff of two steps — wants this one; the engine wants the
        other. Keeping both named stops the two from being confused silently.
        """
        return tuple(reversed(self.modifiers))

    @property
    def shape_verbs(self) -> tuple[Modifier, ...]:
        """Every modifier that changes shape, innermost first."""
        return tuple(m for m in self.modifiers if m.is_shape)

    @property
    def shape_verb(self) -> Modifier | None:
        """The outermost shape verb — the one that decides the final shape."""
        verbs = self.shape_verbs
        return verbs[-1] if verbs else None

    def bind(self, **literals) -> "Operation":
        """Add bound literals, returning a new Operation — closed, like the rest."""
        _no_step_refs(self.tool_id, literals)
        return Operation(self.tool_id, self.modifiers,
                         {**self.arguments, **literals}, self.fn)

    # ── as plain data (what the light export carries) ────────────────────
    def to_dict(self) -> dict:
        """The Operation as JSON-safe data. The carried function is **not** in it.

        This is the whole point of storing modifiers as descriptors: a step's
        definition is a few strings and numbers, so exporting a workflow costs
        nothing and does not drag payloads along.
        """
        return {
            "tool_id": self.tool_id,
            "arguments": _deref(self.arguments),
            # The one place a StepRef flattens to its id: JSON starts here.
            "modifiers": [{"kind": m.kind, "params": _deref(m.params)}
                          for m in self.modifiers],
        }

    @classmethod
    def from_dict(cls, blob: dict, tools: dict[str, Callable] | None = None
                  ) -> "Operation":
        """Rebuild an Operation from :meth:`to_dict`, re-attaching its function."""
        table = {**BUILTIN_TOOLS, **TOOLS, **(tools or {})}
        fn = table.get(blob["tool_id"])
        return cls(
            tool_id=blob["tool_id"],
            modifiers=tuple(Modifier(m["kind"], dict(m["params"]))
                            for m in blob["modifiers"]),
            arguments=dict(blob.get("arguments") or {}),
            fn=fn.fn if isinstance(fn, ToolHandle) else fn,
        )

    # ── the other half: hand the decorated tool some data ────────────────
    def __call__(self, source: Any, /, **literals) -> Any:
        """Apply the decorated tool to its input.

        Keyword arguments here are **bound literals**, exactly as
        :meth:`bind` would set them — ``score[mod.map()](ref, weight=2)`` and
        ``score.bind(weight=2)[mod.map()](ref)`` are the same Operation.
        ``ToolHandle.__call__`` already accepted them; this is the other half.
        *source* is positional-only so a tool may still have a parameter of its
        own called ``source``.

        **Parens apply; a reference is an input you do not have yet.** So one
        rule covers both times:

        * given **data**, this runs — `compile_operation` and away;
        * given a **StepRef**, there is nothing to run yet, so it *wires*:
          returns a new Operation that records what this step reads.

        Wiring writes ``over`` into the stack, so the stored data is exactly
        what the long form produces. These are the same Operation::

            score[mod.map()](wf["raw"])
            score[mod.map(over=wf["raw"])]

        With no shape verb, wiring infers one (:func:`infer_verb`) and stores
        it concretely — so ``wf["scored"] = score(wf["raw"])`` is the whole
        step, and the verb it chose is visible and replaceable.
        """
        operation = self.bind(**literals) if literals else self
        if isinstance(source, StepRef):
            return operation._wire(source)
        return operation.run(source)

    def _wire(self, ref: "StepRef") -> "Operation":
        """Record that this step reads *ref*, inferring a verb if none is set."""
        verb = self.shape_verb
        if verb is not None:
            return Operation(
                self.tool_id,
                tuple(Modifier(m.kind, {**m.params, "over": ref})
                      if m is verb else m for m in self.modifiers),
                self.arguments, self.fn,
            )
        upstream = None
        if ref.workflow is not None:
            step = ref.workflow.steps.get(ref.id)
            # A staged upstream still predicts its payload column, which is
            # what lets `total(acc, value)` read as a reducer before anything
            # has run — the build-it-all-at-once case.
            upstream = None if step is None else step.output
        fn = self.fn or TOOLS.get(self.tool_id) \
            or BUILTIN_TOOLS.get(self.tool_id)
        kind = ("map" if fn is None
                else infer_verb(fn, upstream, self.arguments)[0])
        return self._add(kind, over=ref)      # the ref, not ref.id — it knows its workflow

    def run(self, source: Any, tools: dict[str, Callable] | None = None) -> Any:
        """Compile the stack and apply it to *source*.

        Mirrors ``Tool.run()`` in the registry: the deferred form is the
        default and this is the immediate escape hatch. *tools* is needed only
        when this Operation names its tool by id (``op("score")``) rather than
        carrying it (``score[...]`` from a ``@tool`` handle).
        """
        if isinstance(source, StepRef):
            raise TypeError(
                f"cannot run against the reference {source.id!r} — a reference "
                "names a step, it is not data. A step's input is part of its "
                "definition, so it belongs in the modifier: "
                f"wf[...] = <tool>[mod.map(over=wf[{source.id!r}])]. "
                "Calling an Operation is for data you already hold."
            )
        table = {**BUILTIN_TOOLS, **TOOLS, **(tools or {})}
        if self.fn is not None:
            table.setdefault(self.tool_id, self.fn)
        if self.tool_id not in table:
            raise KeyError(
                f"cannot run {self.tool_id!r}: this Operation names its tool "
                f"by id, so pass the function — "
                f"run(source, tools={{{self.tool_id!r}: fn}}). "
                "Operations built from a @tool handle carry it already."
            )
        return compile_operation(self, table)(source)

    def __repr__(self) -> str:
        # Written order, outermost first — the order the brackets were typed in,
        # so a repr can be compared against the source that produced it. The
        # tool comes last because that is what the layers close over.
        stack = "".join(f"{m!r} ∘ " for m in self.layers)
        return f"<Operation {stack}{self.tool_id}>"


def op(tool_id: str, **arguments) -> Operation:
    """Start building an Operation for the tool named *tool_id*."""
    return Operation(tool_id=tool_id, arguments=arguments)


# ─────────────────────────────────────────────────────────────────────────
# The authoring surface: objects instead of strings
# ─────────────────────────────────────────────────────────────────────────
# Everything here is sugar that produces the exact same `Operation` data. The
# gain is that a typo becomes a NameError at import rather than a silent
# literal at run time, and an editor can autocomplete.


@dataclass(frozen=True)
class StepRef:
    """A handle to a step, usable wherever a reference string was.

    ``over=videos`` instead of ``over="videos"``. It serializes to its id, so
    the stored Operation is unchanged — this only removes the chance to
    mistype it.
    """

    id: str
    #: The Workflow this names a step in, so ``score(wf["raw"])`` can inspect
    #: the upstream. ``compare=False``: a reference is its id, and two refs to
    #: the same step are equal whether or not either is carrying a workflow.
    workflow: Any = field(default=None, compare=False, repr=False)

    def __str__(self) -> str:
        return self.id

    def __repr__(self) -> str:
        return f"<{self.id}>"


def _no_step_refs(tool_id: str, literals: dict) -> None:
    """Refuse a :class:`StepRef` bound as a constant.

    A bound literal is a **value**, so a reference is never what was meant —
    and dereferencing it would store the step's *id string*, which then reaches
    the tool as text. That used to pass declaration silently and fail per row
    with a type error about a ``str``. ``over=`` is where a reference belongs.
    """
    refs = [name for name, value in literals.items() if isinstance(value, StepRef)]
    if refs:
        names = ", ".join(map(repr, refs))
        raise TypeError(
            f"cannot bind {names} to a step reference: a bound literal is a "
            f"constant, and a reference names a step rather than its value. "
            f"{tool_id}() would have received the id as a string. A step's "
            f"input is `over=` (or the call position), not an argument — and "
            f"one step reads one input, so combining two needs a merge verb."
        )


def _deref(value: Any) -> Any:
    """StepRefs become their ids; everything else passes through."""
    if isinstance(value, StepRef):
        return value.id
    if isinstance(value, dict):
        return {k: _deref(v) for k, v in value.items()}
    return value



class ToolHandle:
    """What ``@tool`` returns: the plain function, plus a name and brackets.

    **Parens run, brackets decorate** — the same contract a bracket-decorator
    has outside this system, and the only calling rule in it::

        transcribe({"path": "a.mp4"})              # a plain call, undecorated
        transcribe[mod.map(over=videos)](videos)   # decorated, then run

    Decorating a tool never touches the function, so the same tool is bare in
    one step and mapped in another.
    """

    def __init__(self, fn: Callable, tool_id: str | None = None):
        self.fn = fn
        self.id = tool_id or fn.__name__
        self.__doc__ = fn.__doc__
        self.__name__ = self.id

    def __call__(self, *args, **kwargs) -> Any:
        """Apply the tool to its input — running it, or wiring it into a step.

        ``score(3)`` runs the plain function. ``score(wf["raw"])`` has no data
        to run on, so it builds the step instead, inferring how to iterate::

            wf["scored"] = score(wf["raw"])      # -> map(over='raw') ∘ score

        The two cannot be confused: a :class:`StepRef` is never data.
        """
        if args and isinstance(args[0], StepRef):
            if len(args) > 1:
                raise TypeError(
                    "wire one reference at a time: a step reads one input."
                )
            return self._start().bind(**kwargs)(args[0])
        return self.fn(*args, **kwargs)

    def bind(self, **literals) -> Operation:
        """Fix some arguments now, leaving the rest to arrive with each row.

        ``score.bind(threshold=5)[mod.map(over=rows)]`` — the literals become
        the Operation's ``arguments`` and are applied innermost, inside every
        modifier, so a retry re-runs the same call and a map passes them to
        every item.
        """
        _no_step_refs(self.id, literals)
        return Operation(tool_id=self.id, arguments=dict(literals), fn=self.fn)

    def _start(self) -> Operation:
        return Operation(tool_id=self.id, fn=self.fn)

    def __getitem__(self, modifiers: Any) -> Operation:
        """``transcribe[mod.map(over=videos), mod.retry(times=2)]`` — decorate.

        Returns an :class:`Operation` (data), never a wrapped function. Bound
        literals survive it: ``transcribe.bind(model="large")[mod.map(...)]``.
        """
        return self._start()[modifiers]

    def __repr__(self) -> str:
        return f"<tool {self.id!r}>"


#: Every tool declared with ``@tool``, by id. A server needs this: a workflow
#: arrives as ids and modifiers, so something has to turn ``"to_fahrenheit"``
#: back into a function. Import the module that declares your tools and they
#: are here.
TOOLS: dict[str, Callable] = {}


def tool(fn: Callable | None = None, *, id: str | None = None,
         strict: bool | None = None):
    """Mark a plain function as a tool. Usable bare or with an id.

    Registers it in :data:`TOOLS` so a workflow loaded from JSON can find it
    without the caller assembling a name→function map by hand.

    *strict* requires a type annotation on every parameter and on the return,
    refusing the declaration at import when one is missing. It defaults to
    :data:`STRICT_TYPES`, so a project turns the rule on once rather than
    repeating it per tool. The annotations are not decoration: ``check``
    compares them against the upstream's real dtypes, and ``catalog`` publishes
    them as the tool's boundary.
    """
    def make(f: Callable, tool_id: str | None) -> ToolHandle:
        handle = ToolHandle(f, tool_id)
        found = declaration_problems(f, handle.id)
        if found:
            raise TypeError(
                f"cannot declare tool {handle.id!r}: " + "; ".join(found) + "."
            )
        if handle.id in TOOLS and TOOLS[handle.id] is not f:
            # A warning, not an error: re-running a notebook cell and declaring
            # a throwaway tool per test are both legitimate. Silently replacing
            # a *different* function is the case worth surfacing — two modules
            # claiming one id in a server is a real hazard.
            warnings.warn(
                f"tool {handle.id!r} is already declared and is being replaced. "
                f"If these are two different tools, give one another name or "
                f"pass id= — a workflow loaded from JSON resolves the id to "
                f"whichever was declared last.",
                stacklevel=3,
            )
        if STRICT_TYPES if strict is None else strict:
            found = annotation_problems(f)
            if found:
                raise TypeError(
                    f"tool {handle.id!r} is not fully typed: {'; '.join(found)}. "
                    "A step's boundary is its annotations — they are what "
                    "`check` compares against the upstream's dtypes and what a "
                    "palette shows a user. Annotate it, or declare it with "
                    "strict=False."
                )
        if handle.id in BUILTIN_TOOLS:
            # Shadowing a builtin is never intended and never harmless: the
            # shape verbs resolve `identity` and `gather` by name, so a
            # same-named user tool would quietly change what `select` or a bare
            # `collapse` does. Refused at import, where it is cheap to rename.
            raise ValueError(
                f"{handle.id!r} is a builtin tool ({BUILTIN_TOOLS[handle.id].__doc__ or ''}"
                f"). Give yours another name, or pass id= to rename it."
            )
        TOOLS[handle.id] = f
        return handle

    if fn is not None:
        return make(fn, None)
    return lambda f: make(f, id)


# ─────────────────────────────────────────────────────────────────────────
# Payload codecs — only the full export needs these
# ─────────────────────────────────────────────────────────────────────────
# The light export is strings and numbers, so it needs nothing. Payloads are
# where serialization gets hard: an object column is not Arrow-serializable
# (docs/shape-algebra.md §8.8), so these handle frames and JSON-safe values and
# say so plainly when they meet anything else, rather than writing a `repr`
# that silently will not load back.


class PayloadError(TypeError):
    """Raised when a payload cannot be represented in a session export."""


#: Distinguishes "absent" from a legitimately stored ``None``.
_MISSING = object()

_JSON_SCALARS = (type(None), bool, int, float, str)


def _json_safe(value: Any) -> bool:
    """Can this survive a JSON round-trip as itself?

    Worth checking rather than trusting: ``DataFrame.to_json`` does **not**
    fail on an object column, it writes ``{}`` and reads back an empty dict.
    Silent loss is worse than a refusal, so object columns are vetted per
    value before the frame is handed to pandas.
    """
    if isinstance(value, _JSON_SCALARS):
        return True
    if hasattr(value, "item") and hasattr(value, "dtype"):    # numpy scalar
        return _json_safe(value.item())
    if isinstance(value, (list, tuple)):
        return all(_json_safe(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _json_safe(v) for k, v in value.items())
    return False


def _encode(value: Any) -> dict:
    """One payload as JSON-safe data."""
    if isinstance(value, pd.DataFrame):
        for column in value.columns:
            if value[column].dtype != object:
                continue
            bad = next((v for v in value[column] if not _json_safe(v)), _MISSING)
            if bad is not _MISSING:
                raise PayloadError(
                    f"cannot export column {column!r}: it holds a "
                    f"{type(bad).__name__}, which to_json would silently write "
                    "as {} and read back as an empty dict. Object payloads "
                    "persist only as handles or as something with a to_json "
                    "(§8.8); the light export (to_json) carries no payloads."
                )
        # Dtypes travel beside the data: JSON has no type information, so
        # `read_json` re-infers, and a float column of whole numbers comes back
        # int64. That used to be cosmetic; now that annotations are checked
        # against real dtypes, a round trip could change a step's verdict.
        # Stored positionally — a column name need not be a string.
        return {"kind": "frame",
                "data": value.to_json(orient="split"),
                "dtypes": [str(dtype) for dtype in value.dtypes],
                # `orient="split"` writes the index as a plain list, so a
                # RangeIndex comes back as an Index of the same values. The
                # values align either way; recording it keeps a round trip
                # byte-identical rather than merely equivalent.
                "range_index": isinstance(value.index, pd.RangeIndex)}
    if value is None or isinstance(value, (bool, int, float, str)):
        return {"kind": "scalar", "data": value}
    if isinstance(value, (list, tuple)):
        return {"kind": "list", "data": [_encode(v) for v in value]}
    raise PayloadError(
        f"cannot export a {type(value).__name__} payload. Object payloads "
        "persist only as handles or as something with a to_json (§8.8); the "
        "light export (to_json) carries no payloads at all."
    )


def _decode(blob: dict) -> Any:
    kind = blob["kind"]
    if kind == "frame":
        import io
        frame = pd.read_json(io.StringIO(blob["data"]), orient="split")
        # Restore what JSON could not carry. Absent on exports written before
        # dtypes were recorded, which then behave as they always did.
        dtypes = blob.get("dtypes")
        if dtypes and len(dtypes) == len(frame.columns):
            for column, dtype in zip(frame.columns, dtypes):
                if str(frame[column].dtype) == dtype:
                    continue
                try:
                    frame[column] = frame[column].astype(dtype)
                except (TypeError, ValueError):
                    pass          # an object column that cannot be re-cast
        if blob.get("range_index") and list(frame.index) == list(range(len(frame))):
            frame.index = pd.RangeIndex(len(frame))
        return frame
    if kind == "list":
        return [_decode(v) for v in blob["data"]]
    return blob["data"]


def _encode_output(output: Output) -> dict:
    return {"data": _encode(output.data),
            "ledger": _encode(output.ledger),
            "meta": {k: v for k, v in output.meta.items() if k != "problems"}}


def _decode_output(blob: dict) -> Output:
    return Output(data=_decode(blob["data"]),
                  ledger=_decode(blob["ledger"]),
                  meta=dict(blob["meta"]))


# ─────────────────────────────────────────────────────────────────────────
# Declaring: a Step is born staged
# ─────────────────────────────────────────────────────────────────────────
# Declaring a step *is* staging (docs/shape-algebra.md §7). A Step therefore
# always has both halves from the moment it exists: the Operation (what to run)
# and an Output (the slot). Running does not create the Output — it replaces it
# with the real one.
#
# Staging sharpens in three levels, and which one you get depends only on what
# the upstream already holds:
#   shape        always      — read off the outermost shape verb
#   cardinality  upstream has an Output      — "4 cells"
#   addresses    upstream has an index       — a staged ledger, one row per cell


def check(operation: Operation, workflow: "Workflow | None" = None,
          step_id: str | None = None) -> tuple[str, ...]:
    """Everything wrong with *operation* that is knowable without running it.

    Returns the problems, empty when there are none. This never raises: a
    reactive editor has to be able to *show* a bad step while you are still
    typing it, so validity is a property of the Step, not a precondition for
    building one.
    """
    problems: list[str] = []

    # 1. the tool has to exist
    fn = operation.fn or TOOLS.get(operation.tool_id) \
        or BUILTIN_TOOLS.get(operation.tool_id)
    if fn is None:
        problems.append(f"unknown tool {operation.tool_id!r}")

    # 2. every modifier kind has to be in the vocabulary
    for modifier in operation.modifiers:
        if modifier.kind not in MODIFIERS:
            problems.append(f"unknown modifier {modifier.kind!r}")

    # 2b. a modifier's own parameters have to be ones its verb accepts. A typo
    #     here used to pass declaration and surface at run time as a TypeError
    #     from `map_()`, which is the one validation gap `arguments` did not
    #     have. `sweep` accepts anything, because its parameters are the data.
    for modifier in operation.modifiers:
        entry = MODIFIERS.get(modifier.kind)
        if entry is None or entry.accepts is None:
            continue
        unknown = [name for name in modifier.params if name not in entry.accepts]
        if unknown:
            problems.append(
                f"{modifier.kind} takes no parameter "
                f"{', '.join(map(repr, unknown))}; it accepts "
                f"{', '.join(sorted(entry.accepts))}"
            )

    # 2c. and they have to be the right *type*. `sweep` is why this matters:
    #     a swept parameter called `name` lands in the verb's own `name=`, and
    #     a list there is not a usable column name.
    for modifier in operation.modifiers:
        overrides = PARAM_TYPES_BY_VERB.get(modifier.kind, {})
        for parameter, expected in {**PARAM_TYPES, **overrides}.items():
            if parameter not in modifier.params:
                continue
            value = modifier.params[parameter]
            # bool is a subclass of int, so it must not satisfy an int-typed
            # parameter — unless bool is what was asked for.
            if isinstance(value, expected) and (
                    bool in expected or not isinstance(value, bool)):
                continue
            names = " or ".join(t.__name__ for t in expected)
            extra = ""
            if modifier.kind == "sweep" and parameter in ("name", "retries"):
                extra = (f". A swept parameter cannot be called {parameter!r} — "
                         f"it collides with the verb's own")
            problems.append(
                f"{modifier.kind}'s {parameter}= must be {names}, got "
                f"{type(value).__name__}{extra}"
            )

    # 3. a reference has to have been read from *this* workflow. A step is
    #    named by its id, so a ref borrowed from another workflow would resolve
    #    against a same-named local step — silently running the wrong data when
    #    both happen to have one. A StepRef knows which workflow it came from,
    #    which is the whole reason `params` keeps the ref instead of its id.
    for modifier in operation.modifiers:
        over = modifier.params.get("over")
        if workflow is None or not isinstance(over, StepRef):
            continue
        if over.workflow is None or over.workflow is workflow:
            continue
        name = over.id
        problems.append(
            f"{modifier.kind} over {name!r} reads a different Workflow. A step "
            f"is named by its id, so this would resolve to *this* workflow's "
            f"{name!r} — not the step you pointed at. Read it from this "
            f"workflow, or pass {name!r} as a plain string to say you mean "
            f"whatever {name!r} is here."
        )

    # 4. `over` has to name an existing, valid, non-circular step
    for modifier in operation.modifiers:
        over = modifier.params.get("over")
        if over is None or workflow is None:
            continue
        name = str(over)
        if name == step_id:
            problems.append(f"{modifier.kind} over itself ({name!r})")
        elif name not in workflow.steps:
            problems.append(
                f"{modifier.kind} over {name!r}, which is not an earlier step"
            )
        elif not workflow.steps[name].valid:
            problems.append(f"{modifier.kind} over {name!r}, which is invalid")
        elif step_id is not None and step_id in workflow._upstream_ids(name):
            problems.append(f"{modifier.kind} over {name!r} is circular")

    # 5. at most one shape verb per step (§11). Two shape changes inside one
    #    step make an intermediate grid with no cell address, so a unit that
    #    fails there cannot be inspected or re-run.
    verbs = operation.shape_verbs
    if len(verbs) > 1:
        names = ", ".join(v.kind for v in verbs)
        problems.append(
            f"{len(verbs)} shape verbs in one step ({names}); at most one is "
            "allowed. Split them into separate steps so every shape change "
            "keeps a cell address you can re-drive."
        )

    # 6. the column verbs apply no tool
    for kind in ("source", "select", "drop", "widen", "slice", "rename",
                 "sort", "distinct"):
        if any(m.kind == kind for m in operation.modifiers) and not is_identity(fn):
            problems.append(f"{kind} applies no tool; use map to compute")

    # 6b. select and drop must name columns the input will actually have
    verb = operation.shape_verb
    # Deliberately not `widen`: its columns are the record's fields, which do
    # not exist upstream — that is the whole point of the verb.
    if (verb is not None and verb.kind in ("select", "drop", "rename", "sort",
                                           "distinct")
            and workflow is not None
            and (verb.params.get("columns") or verb.params.get("by"))):
        available = workflow._known_columns(operation)
        by = verb.params.get("by")
        named = list(verb.params.get("columns") or
                     ([by] if isinstance(by, str) else by) or ())
        if available:
            missing = [c for c in named if c not in available]
            if missing:
                problems.append(
                    f"{verb.kind} names {', '.join(map(repr, missing))}, which "
                    f"the input does not have (it has {', '.join(available)})"
                )

    # 7. bound literals have to be parameters the tool accepts — the reactive
    #    argument check, done against the signature rather than at run time.
    if fn is not None and operation.arguments:
        try:
            parameters = inspect.signature(fn).parameters
        except (TypeError, ValueError):          # builtins have no signature
            parameters = {}
        if parameters and not any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
        ):
            for name in operation.arguments:
                if name not in parameters:
                    problems.append(
                        f"{operation.tool_id}() takes no argument {name!r}; "
                        f"it accepts {', '.join(list(parameters)[1:]) or '(none)'}"
                    )
    # 8. the values the tool requires have to exist as columns upstream.
    #    This is only possible because a tool declares what it needs by name —
    #    with a `def score(row)` convention there is nothing to check against.
    if fn is not None and workflow is not None and not problems:
        problems.extend(_missing_columns(operation, fn, workflow))

    # 9. declared types have to match what is actually there — the bound
    #    literals always, the upstream's dtypes once it has run. This is what
    #    the annotations are *for*; without it they would be documentation.
    if fn is not None and not problems:
        problems.extend(_type_mismatches(operation, fn, workflow))

    return tuple(problems)


def _missing_columns(operation: Operation, fn: Callable,
                     workflow: "Workflow") -> list[str]:
    """Required parameters the upstream grid cannot supply.

    Checked only against an upstream that has **run**: a staged Output holds
    placeholder rows, not real columns, so checking one would invent errors.
    The check therefore sharpens as the workflow runs, the same way staging
    does — and a source step is born completed, so the common case is covered
    from declaration.
    """
    verb = operation.shape_verb
    if verb is None or verb.kind in ("source", "sweep"):
        return []                       # nothing upstream, or rows it generates

    upstream = workflow._input_for(operation)
    if upstream is None:
        return []

    try:
        parameters = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return []
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return []                       # takes the whole row; nothing to miss
    if verb.kind == "collapse":
        parameters = parameters[1:]     # the verb supplies the accumulator

    available = set(rows(upstream).columns) | set(operation.arguments)
    missing = [p.name for p in parameters
               if p.default is inspect.Parameter.empty
               and p.kind is not inspect.Parameter.VAR_POSITIONAL
               and p.name not in available]
    if not missing:
        return []
    return [
        f"{operation.tool_id}() needs {', '.join(repr(m) for m in missing)}, "
        f"which {str(verb.params.get('over', 'the input'))!r} does not have "
        f"(it has {', '.join(sorted(available)) or 'no columns'})"
    ]


def _type_mismatches(operation: Operation, fn: Callable,
                     workflow: "Workflow | None") -> list[str]:
    """Where the tool's declared types disagree with what will reach it.

    Two sources, checked on the same terms as everything else in :func:`check`:
    a **bound literal** is in hand at declaration, so it is always checkable; an
    **upstream column** needs that step to have run, exactly like
    :func:`_missing_columns`, because a staged Output holds placeholder rows.

    Only certain mismatches are reported. ``_column_fits`` answers ``None`` for
    anything it cannot decide, and an undecidable type is not an error — a false
    positive here would refuse a step that runs.
    """
    try:
        parameters = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return []

    problems: list[str] = []
    for name, value in operation.arguments.items():
        parameter = parameters.get(name)
        if parameter is None or parameter.annotation is inspect.Parameter.empty:
            continue
        if _value_fits(value, parameter.annotation) is False:
            problems.append(
                f"{operation.tool_id}() declares {name}: "
                f"{_type_name(parameter.annotation)}, but it is bound to "
                f"{value!r} ({type(value).__name__})"
            )

    verb = operation.shape_verb
    if workflow is None or verb is None or verb.kind in ("source", "sweep",
                                                         "select", "drop"):
        return problems
    upstream = workflow._input_for(operation)
    if upstream is None:
        return problems

    frame = rows(upstream)
    declared = list(parameters.values())
    if verb.kind == "collapse":
        declared = declared[1:]          # the verb supplies the accumulator
    for parameter in declared:
        if parameter.name in operation.arguments:
            continue                     # a literal, checked above
        if parameter.name not in frame.columns:
            continue                     # missing columns are rule 7's job
        if parameter.annotation is inspect.Parameter.empty:
            continue
        if _column_fits(frame[parameter.name], parameter.annotation) is False:
            problems.append(
                f"{operation.tool_id}() declares {parameter.name}: "
                f"{_type_name(parameter.annotation)}, but "
                f"{str(verb.params.get('over', 'the input'))!r} has "
                f"{parameter.name} as {frame[parameter.name].dtype}"
            )
    return problems


#: The payload column each verb writes when ``name=`` is not given. ``None``
#: means the verb writes no new column at all. Staging reads this so a staged
#: step predicts the *right* column name — which is what lets a downstream
#: reducer be recognized before anything has run.
DEFAULT_PAYLOAD: dict[str, str | None] = {
    "source": None, "filter": None, "select": None, "drop": None,
    # widen writes several *named* columns, so it has no single payload.
    "widen": None,
    # the rearranging verbs write nothing new at all.
    "slice": None, "rename": None, "sort": None, "distinct": None,
    "group": "group",
    "map": PAYLOAD, "collapse": PAYLOAD, "expand": PAYLOAD, "sweep": PAYLOAD,
}


#: Verbs whose output keeps **all** the input's columns (§3's columns column).
#: ``collapse`` and ``sweep`` build their rows from scratch; ``select`` keeps a
#: chosen subset, so it predicts its columns exactly and gets its own branch in
#: :func:`stage`.
CARRIES_COLUMNS: frozenset[str] = frozenset({"map", "filter", "group", "expand"})


#: §3's rows column, as data: what each verb does to the input's row count.
#: This is what staging folds, and it is why a staged claim can be honest —
#: ``filter`` can promise "at most n", never "n".
ROWS_RULE: dict[str, str] = {
    "source": "same", "map": "same", "group": "same",
    "filter": "at_most", "select": "same", "drop": "same", "widen": "same",
    "rename": "same", "sort": "same",
    "slice": "at_most", "distinct": "at_most",
    "collapse": "one",
    "expand": "unknown", "sweep": "generated",
}


def predicted_columns(output: Output) -> list[str]:
    """The column names a step's output will have, **in order**, as far as known.

    Ordered, not a set: column order is real information — ``select`` reorders
    deliberately, and ``map`` appends its payload after the columns it carried
    through. Returning a set once let a prediction come out in hash order, which
    matched the actual columns only by luck.

    A step that has run knows them exactly. A **staged** one knows only the
    name of the payload column it is going to write — but that single name is
    often enough to recognize a pattern, which is why inference may use it.

    Validation may **not**: the prediction is a subset (a ``map`` also carries
    its input's columns through), so rejecting against it would invent errors.
    Inference uses predicted columns to *recognize*; ``check`` uses real ones
    to *refuse*.
    """
    if not output.meta.get("staged"):
        return list(output.data.columns)
    recorded = output.meta.get("columns")
    if recorded is not None:
        return list(recorded)
    payload = output.meta.get("payload")
    return [payload] if payload else []


def infer_verb(fn: Callable, upstream: Any, literals: dict) -> tuple[str, str]:
    """Pick the shape verb a tool most likely wants, and say why.

    This is the "configure the iteration for me" behaviour, and it resolves
    **at wiring time into a concrete verb** — never into a stored ``auto``
    modifier. An `auto` that stayed in the data would be the one modifier whose
    shape is unknowable before running, which is exactly the property staging,
    serialization and the round-trip invariant all depend on. What gets stored
    is an ordinary ``map`` or ``collapse``, indistinguishable from one you
    typed, so the UI shows it selected and you can change it.

    Resolving once also sidesteps the clobbering problem: an inferred verb is
    never silently re-inferred later, so an edit cannot be overwritten.
    """
    columns: set[str] = set()
    n_rows: int | None = None
    if isinstance(upstream, Output):
        columns = set(predicted_columns(upstream))
        n_rows = upstream.meta.get("expected") if upstream.meta.get("staged") \
            else len(upstream.data)
    elif upstream is not None:
        frame = rows(upstream)
        columns, n_rows = set(frame.columns), len(frame)

    try:
        parameters = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return "map", "could not read the tool's signature; assuming per row"

    positional = [p for p in parameters
                  if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    needed = [p.name for p in positional
              if p.default is inspect.Parameter.empty
              and p.name not in literals]

    # (acc, x) where the first value is not a column: that is a reducer.
    if len(needed) >= 2 and needed[0] not in columns and needed[1] in columns:
        return "collapse", (f"{needed[0]!r} is not a column but {needed[1]!r} is, "
                            "so this reads as a reducer")

    returns = inspect.signature(fn).return_annotation
    # Normalize to a bare type name so a string annotation (PEP 563 /
    # ``from __future__ import annotations``) infers the same verb a real type
    # does — otherwise a tools file with future annotations silently loses
    # filter/expand inference and everything falls back to map.
    returns_name = (returns if isinstance(returns, str)
                    else getattr(returns, "__name__", "")) or ""
    base = returns_name.split("[", 1)[0]          # "list[int]" -> "list"
    if returns is bool or base == "bool":
        return "filter", "it returns a bool per row, so keep the rows that pass"
    sequence = {"list", "tuple", "set"}
    if (returns in (list, tuple, set)
            or typing.get_origin(returns) in (list, tuple, set)
            or base in sequence):
        return "expand", ("it returns many values per row, so unnest them into "
                          "their own rows")

    if n_rows == 1:
        return "map", "the input is a single row"

    if needed and columns and not set(needed) & columns:
        return "map", (f"none of {', '.join(map(repr, needed))} is a column yet — "
                       "check the input")

    if columns:
        return "map", (f"{', '.join(repr(n) for n in needed) or 'the tool'} "
                       f"comes from the input's columns, so apply it per row")
    return "map", "applying it per row"


def stage(operation: Operation, workflow: "Workflow | None" = None,
          problems: tuple[str, ...] = ()) -> Output:
    """The Output a step has before it runs — the slot, with what we know in it.

    An **invalid** operation stages as a single cell: it has no shape, because
    the thing that would have given it one is what is broken.

    Otherwise staging folds :data:`ROWS_RULE` over the input's index. Only the
    1:1 verbs can name their cells in advance; ``filter`` bounds them,
    ``collapse`` knows there is one, and ``expand`` cannot know at all. The
    ledger is materialized only when the addresses are actually known (§7's
    level 3) — an empty ledger is the honest answer for the rest.
    """
    verb = operation.shape_verb
    kind = verb.kind if verb else None

    if problems:
        return Output(
            data=pd.DataFrame({PAYLOAD: [None]}, index=[0]),
            ledger=_ledger([{"status": "invalid", "error": problems[0],
                             "attempts": 0, "seconds": 0.0}], [0]),
            meta={"verb": kind, "form": "scalar", "payload": PAYLOAD,
                  "staged": True, "problems": problems, "n_in": None,
                  "expected": None, "rows_rule": None, "columns": [PAYLOAD]},
        )

    known = workflow._known_index(operation) if workflow is not None else None
    n_in = None if known is None else len(known)
    rule = ROWS_RULE.get(kind)

    # F6: `collapse(by=)` makes one row per *group*, and the group count comes
    #     from the data — so it is unknowable, not "one". F7: `sweep` is the
    #     opposite case: its count is fully determined by its own parameter
    #     lists, with no upstream involved at all.
    swept = 0
    if kind == "collapse" and verb.params.get("by"):
        rule = "per_group"
    elif kind == "sweep":
        lists = [v for k, v in verb.params.items()
                 if k not in ("name", "over", "retries")]
        if lists and all(isinstance(v, (list, tuple)) for v in lists):
            swept = 1
            for values in lists:
                swept *= len(values)
            rule = "generated"

    if kind is None:                       # no orchestration → a single value
        index, expected = [0], 1
    elif rule == "same" and known is not None:
        index, expected = list(known), n_in
    elif rule == "one":
        index, expected = [0], 1
    elif rule == "generated" and swept:
        index, expected = list(range(swept)), swept
    else:                                  # not addressable yet
        index, expected = [], None

    # The column this step is going to write, honouring an explicit `name=`.
    payload = (PAYLOAD if kind is None
               else verb.params.get("name", DEFAULT_PAYLOAD.get(kind, PAYLOAD)))

    # The full column set this step will produce, as far as is knowable —
    # carried-through columns plus whatever it writes. This is what a
    # downstream step reads to recognize what it is looking at, so predicting
    # only the payload would lose every column that simply passes through.
    upstream_columns = (workflow._known_columns(operation)
                        if workflow is not None else set())
    # Predicted in order, because order is what a reader and a downstream tool
    # both see. Each verb contributes its own columns and then the payload is
    # appended, which is exactly what the verbs do to the frame.
    ordered: list[str] = []
    if kind == "select":
        ordered = list(verb.params.get("columns") or [])
    elif kind == "drop":
        removed = set(verb.params.get("columns") or [])
        ordered = [c for c in upstream_columns if c not in removed]
    elif kind == "rename":
        mapping = verb.params.get("columns") or {}
        ordered = [mapping.get(c, c) for c in upstream_columns]
    elif kind in ("slice", "sort", "distinct"):
        ordered = list(upstream_columns)
    elif kind == "widen":
        ordered = list(upstream_columns)
        ordered += [c for c in (verb.params.get("columns") or [])
                    if c not in ordered]
    elif kind in CARRIES_COLUMNS:
        ordered = list(upstream_columns)
    elif kind == "sweep":
        ordered = [k for k in verb.params if k not in ("name", "over", "retries")]
    elif kind == "collapse" and verb.params.get("by"):
        ordered = [verb.params["by"]]
    if payload and payload not in ordered:
        ordered.append(payload)
    index_names = ordered

    records = [{"status": "staged", "error": None, "attempts": 0, "seconds": 0.0}
               for _ in index]
    return Output(
        data=pd.DataFrame({c: [None] * len(index) for c in index_names or [PAYLOAD]},
                          index=index),
        ledger=_ledger(records, index),
        meta={"verb": kind, "form": "scalar" if kind is None else "column",
              "payload": payload, "staged": True, "problems": (),
              "n_in": n_in, "expected": expected, "rows_rule": rule,
              "columns": ordered},
    )


@dataclass
class Step:
    """One node of a workflow: **an Operation and an Output**, always both.

    The Output exists from declaration (staged) and is *replaced* — never
    mutated in place — when the step runs. See docs/shape-algebra.md §8.5:
    writing a ledger row by row is 69x slower than building it once.
    """

    step_id: str
    operation: Operation
    output: Output
    problems: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.problems

    @property
    def status(self) -> str:
        """A rollup of the ledger — a step is only as done as its rows."""
        states = set(self.output.ledger["status"])
        for state in ("invalid", "failed", "running", "staged"):
            if state in states:
                return state
        if states:
            return "completed"
        # No ledger rows at all is ambiguous, and the ledger cannot settle it:
        # either this step is staged and its addresses are not yet knowable, or
        # it ran and legitimately produced nothing (every unit filtered out, or
        # expanded to zero rows). `meta["staged"]` is what distinguishes them.
        return "staged" if self.output.meta.get("staged") else "completed"

    def describe(self) -> str:
        """What this step is, in words.

        Two different questions, and they must not be blurred: a **staged**
        step reports what staging can *promise* (§7's three levels), while a
        step that has run reports what it actually *holds*. Only the first is a
        prediction.
        """
        if not self.valid:
            return f"invalid · {self.problems[0]}"
        verb = self.output.meta.get("verb")
        tool = self.operation.tool_id
        if not self.output.meta.get("staged"):
            n = len(self.output.data)
            return (f"{tool} · one cell" if verb is None
                    else f"{verb} {tool} · {n} cell{'' if n == 1 else 's'}")
        if verb is None:
            return f"{tool} · one cell"
        n_in, rule = self.output.meta.get("n_in"), self.output.meta.get("rows_rule")
        if rule == "one":
            return f"{verb} {tool} · 1 cell"
        if rule == "generated":
            expected = self.output.meta.get("expected")
            return (f"{verb} {tool} · {expected} cells" if expected
                    else f"{verb} {tool} · one cell per parameter combination")
        if rule == "per_group":
            return (f"{verb} {tool} · one cell per group"
                    + (f", from {n_in} rows" if n_in is not None else ""))
        if n_in is None:
            return f"{verb} {tool} · one cell per upstream row"
        if rule == "same":
            return f"{verb} {tool} · {n_in} cells"
        if rule == "at_most":
            return f"{verb} {tool} · at most {n_in} cells"
        return f"{verb} {tool} · unknown count from {n_in} rows"

    def __repr__(self) -> str:
        return f"<Step {self.step_id!r} {self.status} · {self.describe()}>"


class Workflow:
    """Ordered Steps. Assign an Operation, get a Step that is already staged.

    ``wf["scored"] = score[mod.map(over=wf["videos"])]`` — declaring stages;
    ``wf.run("scored")`` is what actually computes.
    """

    def __init__(self) -> None:
        self.steps: dict[str, Step] = {}

    # ── declaring ────────────────────────────────────────────────────────
    def __setitem__(self, step_id: str, operation: Any) -> None:
        if isinstance(operation, Modifier):
            # A bare shape verb is a complete step: it applies the tool that
            # discards nothing, so `wf["flat"] = mod.expand(over=ref)` needs no
            # tool of its own. Execution modifiers are refused — a pass-through
            # that retries is inert, and silently accepting it would hide a
            # half-written step.
            default = DEFAULT_TOOL.get(operation.kind)
            if default is None:
                # Three different reasons, and they used to collapse into one
                # wrong sentence: a bare `mod.sweep()` was called an execution
                # modifier, which it is not.
                if operation.kind not in MODIFIERS:
                    why = "not a modifier at all"
                elif is_shape(operation.kind):
                    why = ("a shape verb with no default tool — it generates "
                           "rows by calling something, so there is nothing for "
                           "it to apply on its own")
                else:
                    why = "an execution modifier, which changes nothing on its own"
                raise TypeError(
                    f"{operation.kind!r} needs a tool: it is {why}. "
                    f"Write <tool>[mod.{operation.kind}(...)] instead."
                )
            operation = Operation(tool_id=default,
                                  fn=BUILTIN_TOOLS[default])[operation]

        if not isinstance(operation, Operation):
            # A bare value is a source step, and a source step's data **is its
            # output** — it arrived with the declaration, so there is nothing
            # to stage and nothing to compute. It is born completed. This is
            # why a Workflow is only a list of Steps: literals have no separate
            # home, because they were never anything but a step's output.
            self.steps[step_id] = Step(
                step_id,
                Operation(tool_id="identity", fn=identity)[mod.source()],
                source_(operation),
            )
            return
        problems = check(operation, self, step_id)
        self.steps[step_id] = Step(
            step_id, operation, stage(operation, self, problems), problems
        )

    def __getitem__(self, step_id: str | int) -> StepRef:
        """A reference to a step, by **name** or by **position**.

        ``wf["raw"]`` names it; ``wf[0]`` and ``wf[-1]`` count. A ``str`` is
        always a name and an ``int`` always a position, so a step called
        ``"0"`` stays reachable as ``wf["0"]``.

        The position is resolved to the step's **id** right here, and that is
        the whole of why it is safe: positions shift when a step is inserted
        earlier, so a stored position would silently rewire the graph. Same
        rule as verb inference — resolve once, store something concrete.
        """
        if isinstance(step_id, int) and not isinstance(step_id, bool):
            ids = list(self.steps)
            try:
                return StepRef(ids[step_id], self)
            except IndexError:
                raise KeyError(
                    f"no step at position {step_id}; the workflow has "
                    f"{len(ids)} step(s): {ids}"
                ) from None
        if step_id not in self.steps:
            raise KeyError(f"no step {step_id!r}; defined so far: {list(self.steps)}")
        return StepRef(step_id, self)

    def __contains__(self, step_id: str) -> bool:
        return step_id in self.steps

    def step(self, step_id: str) -> Step:
        """The Step itself, rather than a reference to it."""
        return self.steps[step_id]

    # ── what a step reads ────────────────────────────────────────────────
    def _known_columns(self, operation: Operation) -> list[str]:
        """The columns this operation's input will have, in order, as far as known."""
        for modifier in operation.modifiers:
            over = modifier.params.get("over")
            if over is None:
                continue
            step = self.steps.get(str(over))
            return [] if step is None else predicted_columns(step.output)
        return []

    def _known_index(self, operation: Operation) -> Sequence[Any] | None:
        """The input's index, when known — enough to stage, short of running.

        A staged step already carries an index when its own input was known, so
        cardinality propagates down the chain before anything has executed.
        That is §7's level 2/3 without a run.
        """
        for modifier in operation.modifiers:
            over = modifier.params.get("over")
            if over is None:
                continue
            step = self.steps.get(str(over))
            if step is None or not step.valid:
                return None
            index = step.output.data.index
            return index if len(index) or not step.output.meta.get("staged") else None
        return None

    def _input_for(self, operation: Operation) -> Any | None:
        """The upstream Output this operation reads, once that step has run."""
        for modifier in operation.modifiers:
            over = modifier.params.get("over")
            if over is None:
                continue
            step = self.steps.get(str(over))
            if step is None or step.output.meta.get("staged"):
                return None
            return step.output
        return None

    # ── running ──────────────────────────────────────────────────────────
    def pending(self, step_id: str) -> list[str]:
        """The steps *step_id* reads that have not run yet, nearest first."""
        waiting: list[str] = []
        for modifier in self.steps[step_id].operation.modifiers:
            over = modifier.params.get("over")
            if over is None:
                continue
            name = str(over)
            upstream = self.steps.get(name)
            if upstream is not None and upstream.output.meta.get("staged"):
                waiting.extend(self.pending(name))
                waiting.append(name)
        return waiting

    def run(self, step_id: str, tools: dict[str, Callable] | None = None) -> Step:
        """Execute one step and replace its staged Output with the real one.

        Refuses a step whose inputs are not there yet. Silently running against
        a staged upstream produced a grid of ``None`` — plausible-looking and
        wrong, which is the one outcome worth ruling out by construction. Use
        :meth:`run_all` to compute a chain.
        """
        step = self.steps[step_id]
        if not step.valid:
            raise ValueError(
                f"step {step_id!r} is invalid and cannot run: {step.problems[0]}"
            )
        if step.operation.shape_verb and step.operation.shape_verb.kind == "source":
            # A source step holds its data rather than computing it, so running
            # one is either a no-op or a mistake — never a computation.
            if step.output.meta.get("staged"):
                raise ValueError(
                    f"source step {step_id!r} has no data. Assign it: "
                    f"wf[{step_id!r}] = <a frame, list or value>. (A light "
                    "export carries no payloads, so a reloaded source step "
                    "needs its data supplied again.)"
                )
            return step
        waiting = self.pending(step_id)
        if waiting:
            raise ValueError(
                f"step {step_id!r} reads {waiting[-1]!r}, which has not run. "
                f"Run {' then '.join(repr(w) for w in dict.fromkeys(waiting))} "
                f"first, or call run_all()."
            )
        step.output = step.operation.run(self._input_for(step.operation), tools)
        self._restage_after(step_id)
        return step

    def run_all(self, tools: dict[str, Callable] | None = None) -> "Workflow":
        """Run every valid step, each after the steps it reads.

        Still explicit — nothing recomputes on its own (§7's push/pull rule).
        This only saves you from ordering the calls by hand.
        """
        done: set[str] = set()
        remaining = [sid for sid, st in self.steps.items() if st.valid]
        while remaining:
            ready = [sid for sid in remaining
                     if all(w in done for w in self.pending(sid))]
            if not ready:                    # only reachable if a cycle slipped through
                raise ValueError(
                    f"cannot order {remaining!r}: something reads a step that never runs"
                )
            for step_id in ready:
                self.run(step_id, tools)
                done.add(step_id)
            remaining = [sid for sid in remaining if sid not in done]
        return self

    def _restage_after(self, step_id: str) -> None:
        """Re-stage everything downstream of *step_id* — cardinality sharpened.

        Transitively: a chain ``a → b → c`` learns its counts all the way down,
        because ``b``'s freshly staged index is what lets ``c`` stage. Repeats
        until nothing changes rather than assuming declaration order is
        topological.
        """
        changed = {step_id}
        while changed:
            wave: set[str] = set()
            for other in self.steps.values():
                if other.step_id in changed or not other.valid:
                    continue
                if not other.output.meta.get("staged"):
                    continue                       # already has real data
                if not any(str(m.params.get("over")) in changed
                           for m in other.operation.modifiers):
                    continue
                before = other.output.meta.get("expected")
                other.output = stage(other.operation, self, other.problems)
                if other.output.meta.get("expected") != before:
                    wave.add(other.step_id)
            changed = wave

    def _upstream_ids(self, step_id: str, _seen: set[str] | None = None) -> set[str]:
        """Every step *step_id* transitively reads. Used to refuse cycles."""
        seen = set() if _seen is None else _seen
        step = self.steps.get(step_id)
        if step is None:
            return seen
        for modifier in step.operation.modifiers:
            over = modifier.params.get("over")
            if over is None:
                continue
            name = str(over)
            if name in seen:
                continue
            seen.add(name)
            self._upstream_ids(name, seen)
        return seen

    # ── exporting: two modes, and the difference is only payloads ────────
    def to_dict(self) -> dict:
        """**Light**: the chain of Operations and nothing else.

        No outputs, no payloads — a few strings per step. Staging is derived,
        so it is not stored; re-declaring from this reproduces it. What it
        cannot reproduce is *cardinality*, which came from the data: a light
        round-trip lands at §7's level 1 (shape known, counts not), by design.
        """
        return {"version": 1,
                "steps": [{"step_id": sid, "operation": st.operation.to_dict()}
                          for sid, st in self.steps.items()]}

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict())

    def to_session_dict(self) -> dict:
        """**Full**: the light export plus every payload.

        There is one payload map, not two. A source step's literal is simply
        its own output, so it serializes through the same path as a computed
        one — the steps define the inputs.
        """
        blob = self.to_dict()
        blob["outputs"] = {
            sid: _encode_output(st.output)
            for sid, st in self.steps.items()
            if not st.output.meta.get("staged")
        }
        return blob

    def to_session_json(self) -> str:
        import json
        return json.dumps(self.to_session_dict())

    @classmethod
    def from_dict(cls, blob: dict, tools: dict[str, Callable] | None = None
                  ) -> "Workflow":
        """Rebuild a Workflow from either export — all at once.

        Every step goes through the same :func:`check` and :func:`stage` the
        incremental path uses, so loading cannot smuggle in a step that
        declaring would have rejected.
        """
        workflow = cls()
        for entry in blob["steps"]:
            sid = entry["step_id"]
            operation = Operation.from_dict(entry["operation"], tools)
            problems = check(operation, workflow, sid)
            workflow.steps[sid] = Step(sid, operation,
                                       stage(operation, workflow, problems),
                                       problems)
        for sid, encoded in (blob.get("outputs") or {}).items():
            if sid in workflow.steps:
                workflow.steps[sid].output = _decode_output(encoded)
        for sid in (blob.get("outputs") or {}):
            workflow._restage_after(sid)
        return workflow

    @classmethod
    def from_json(cls, data: str, tools: dict[str, Callable] | None = None
                  ) -> "Workflow":
        import json
        return cls.from_dict(json.loads(data), tools)

    def validate(self) -> dict[str, tuple[str, ...]]:
        """Every step's problems, keyed by step id — empty tuples for the good ones."""
        return {sid: step.problems for sid, step in self.steps.items()}

    def __repr__(self) -> str:
        return f"<Workflow {len(self.steps)} step(s): {list(self.steps)}>"


class _Mods:
    """Modifier constructors, for the vertical :func:`stack` form.

    ``mod.map(over=videos)`` just builds a :class:`Modifier`; nothing is
    applied until :func:`stack` assembles them.
    """

    def __getattr__(self, kind: str):
        if kind not in MODIFIERS:
            raise AttributeError(
                f"no modifier {kind!r}. Known: {', '.join(sorted(MODIFIERS))}. "
                "Modifier kinds are declared in MODIFIERS; add one there."
            )

        def make(**params) -> Modifier:
            return Modifier(kind, params)
        make.__name__ = kind
        return make


#: ``mod.map(...)``, ``mod.retry(times=2)`` — descriptors for :func:`stack`.
mod = _Mods()


def compile_operation(operation: Operation, tools: dict[str, Callable]) -> Callable:
    """Apply an Operation's stack to its tool, innermost-first.

    This is the moment the data becomes behaviour: ``[retry, map]`` compiles to
    ``map(retry(tool))`` — the same object graph ``@map`` over ``@retry`` over
    the function would have produced at definition time.
    """
    table = {**BUILTIN_TOOLS, **TOOLS, **tools}
    if operation.tool_id not in table:
        raise KeyError(f"unknown tool {operation.tool_id!r}; have {sorted(table)}")
    # The adapter is always innermost: it is what turns a plain function into
    # something a verb can drive, and it carries the bound literals inside
    # every modifier, so a retry re-runs the same call and a map passes them to
    # every item.
    fn = _d_apply(table[operation.tool_id], **operation.arguments)
    for modifier in operation.modifiers:               # innermost first
        factory = DECORATORS.get(modifier.kind)
        if factory is None:
            raise KeyError(
                f"no decorator registered for modifier {modifier.kind!r}; "
                f"known: {sorted(DECORATORS)}"
            )
        fn = factory(fn, **modifier.params)
    return fn
