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
import math
import numbers
import warnings
import time
import traceback
import types
import typing
from dataclasses import dataclass, field, replace
from collections.abc import Mapping
from typing import Any, Callable, Iterable, Sequence

import pandas as pd

__all__ = [
    "Output", "grid", "rows", "map_", "filter_", "group_", "collapse_",
    "expand_", "sweep_", "source_", "select_", "drop_", "widen_",
    "slice_", "rename_", "sort_", "distinct_",
    "identity", "gather", "count", "total", "first", "last",
    "BUILTIN_TOOLS", "DEFAULT_TOOL", "catalog", "tool_entry",
    "modifier_catalog",
    "TOOLS",
    "op", "Modifier", "Operation",
    "join", "stack", "zip_", "COMBINE", "is_combine",
    "tool", "ToolHandle", "StepRef", "Step", "Workflow", "check", "warn", "stage",
    "wf", "res", "ResRef", "bound_tool", "cols", "Rows", "Cols", "SelectionError",
    "RESERVED_NAMES", "FORMAT_VERSION", "ToolRef", "StepFailed", "resource", "RESOURCE_TYPES",
    "resource_entry", "resource_catalog", "ResourceNotLoaded",
    "STRICT_TYPES", "annotation_problems", "declaration_problems",
    "PARAM_TYPES", "PARAM_TYPES_BY_VERB",
    "ROWS_RULE", "DEFAULT_PAYLOAD", "CARRIES_COLUMNS", "PayloadError",
    "is_identity", "infer_verb",
    "predicted_columns", "columns_unknown",

    "mod",
    "DECORATORS", "MODIFIERS", "ModifierKind", "SHAPE_VERBS", "is_shape",
    "compile_operation",
    "PAYLOAD", "LEDGER_COLUMNS",
]

#: Default name for the column holding whatever a tool returned.
PAYLOAD = "value"

#: Every ledger has exactly these columns, so the UI can rely on them.
LEDGER_COLUMNS = ("status", "error", "attempts", "seconds", "unit", "cause", "caught")


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
        done = int((self.ledger["status"] == "completed").sum())
        return f"{done}/{len(self.ledger)}"

    def __repr__(self) -> str:
        verb = self.meta.get("verb", "?")
        failed = len(self.failed)
        tail = f", {failed} failed" if failed else ""
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


class StepFailed(RuntimeError):
    """``run_all`` stopped: a step has a failed cell it didn't catch.

    Steps that already ran keep their results; ``not_run`` lists the rest. Put
    ``mod.try_except(…)`` on a step to let its failures through.
    """

    def __init__(self, step_id: str, cell: Any, error: str, not_run: list[str]):
        self.step_id, self.cell, self.error, self.not_run = step_id, cell, error, not_run
        later = f" Not run: {', '.join(not_run)}." if not_run else ""
        super().__init__(
            f"step {step_id!r} failed at {step_id}[{cell}]: {error}. The run "
            f"stopped.{later} Add mod.try_except(…) to the step to let this "
            "failure through.")


def _uncaught_failure(output: "Output") -> tuple[Any, str] | None:
    """The first failed cell that should stop the run: its own failure, not
    caught by ``mod.try_except``. A row blocked by an upstream failure has a
    ``cause`` — its root already stopped the run, or was caught."""
    ledger = output.ledger
    if not len(ledger) or "status" not in ledger.columns:
        return None
    for index, record in ledger[ledger["status"] == "failed"].iterrows():
        if record.get("caught") is True:
            continue
        cause = record.get("cause")
        if isinstance(cause, str) and cause:
            continue
        return index, record.get("error")
    return None


def _failed_output(operation: Any, error: str) -> "Output":
    """A step that could not produce a grid: one failed cell saying why."""
    kind = operation.shape_verb.kind if operation.shape_verb else None
    return Output(
        data=pd.DataFrame({PAYLOAD: [None]}, index=[0], dtype=object),
        ledger=_ledger([{"status": "failed", "error": error, "attempts": 0,
                         "seconds": 0.0}], [0]),
        meta={"verb": kind, "form": "scalar", "payload": PAYLOAD})


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
    ledger = source.ledger
    if not len(ledger) or "status" not in ledger.columns:
        return {}
    sid = source.meta.get("step_id") or "input"
    out = {}
    failed = ledger[ledger["status"] == "failed"]
    for index, record in failed.iterrows():
        if index not in source.data.index:
            continue                         # e.g. a filtered-out unit
        cause = record.get("cause") if "cause" in failed.columns else None
        out[index] = (f"upstream cell {sid}[{index}] failed",
                      cause if isinstance(cause, str) and cause
                      else f"{sid}[{index}]: {record.get('error')}")
    return out


def _blocked(error: str, cause: str) -> dict:
    """The ledger record of a unit that was not run because its input failed."""
    return {"status": "failed", "error": error, "attempts": 0, "seconds": 0.0,
            "cause": cause}


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
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        # `dict | None` is a types.UnionType — itself a class, so the generic
        # isinstance below used to refuse every value (008 N1). A union fits
        # when any member does.
        answers = [_value_fits(value, a) for a in typing.get_args(annotation)]
        if any(a is True for a in answers):
            return True
        return False if all(a is False for a in answers) else None
    origin = typing.get_origin(annotation) or annotation
    if not isinstance(origin, type) or origin is object:
        return None                                  # Any, unions, protocols…
    if origin is float and isinstance(value, int) and not isinstance(value, bool):
        return True                                  # an int is a fine float
    return isinstance(value, origin)


def _shape_kind(frame: pd.DataFrame) -> str:
    """``cell``, ``column``, ``row`` or ``block`` — what a referenced grid is."""
    n_rows, n_cols = frame.shape
    if (n_rows, n_cols) == (1, 1):
        return "cell"
    if n_cols == 1:
        return "column"
    if n_rows == 1:
        return "row"
    return "block"


def _wants(annotation: Any) -> str | None:
    """Which form a parameter asks for: list, dict, series, frame, scalar, or None (untyped)."""
    if annotation is inspect.Parameter.empty or annotation is Any \
            or isinstance(annotation, str):
        return None
    _, base = _optional_parts(annotation)
    origin = typing.get_origin(base) or base
    if origin in (list, tuple, set):
        return "list"
    if origin is dict:
        return "dict"
    if origin is pd.Series:
        return "series"
    if origin is pd.DataFrame:
        return "frame"
    if isinstance(origin, type):
        return "scalar"
    return None


#: 008 C1/C7's conversion table: (shape, wanted form) → allowed.
_CONVERTS = {
    ("cell", "scalar"), ("cell", "list"),
    ("column", "list"), ("column", "series"), ("column", "frame"),
    ("row", "list"), ("row", "series"), ("row", "dict"), ("row", "frame"),
    ("block", "frame"), ("cell", "frame"),
}


def _shape_problem(kind: str, annotation: Any, name: str, step_id: str) -> str | None:
    """Why a *kind* of grid can't be passed as *annotation*, or None when it can."""
    wanted = _wants(annotation)
    if wanted is None or (kind, wanted) in _CONVERTS:
        return None
    if kind == "column" and wanted == "scalar":
        why = "a column; to pair its rows with the input's, join first"
    else:
        why = f"a {kind}"
    return (f"{name}: {_type_name(annotation)}, but {step_id!r} is {why} "
            f"— an argument is passed whole, not one value per row")


def _ref_value(frame: pd.DataFrame, annotation: Any, step_id: str) -> Any:
    """What a ``$ref`` argument or setting receives, by the parameter's type (008 C1).

    A cell gives its value; a column a list (or Series); a row a dict (or
    list/Series); anything else the DataFrame. Untyped, the natural form.
    """
    kind = _shape_kind(frame)
    problem = _shape_problem(kind, annotation, "argument", step_id)
    if problem:
        raise TypeError(problem)
    wanted = _wants(annotation)
    clean = lambda values: [None if _is_missing(v) else v for v in values]  # noqa: E731
    if wanted == "frame":
        return frame
    if kind == "cell" and wanted != "list":
        value = frame.iloc[0, 0]
        return None if _is_missing(value) else value
    if kind == "cell":
        return clean([frame.iloc[0, 0]])
    if kind == "column":
        return frame.iloc[:, 0] if wanted == "series" else clean(frame.iloc[:, 0])
    if kind == "row":
        row = frame.iloc[0]
        if wanted == "series":
            return row
        if wanted == "list":
            return clean(row)
        return {k: (None if _is_missing(v) else v) for k, v in row.items()}
    return frame


#: Type names a plan or `mod.expect` may use, and the types they mean.
_TYPE_NAMES: dict[str, Any] = {"str": str, "int": int, "float": float,
                               "bool": bool, "list": list, "dict": dict,
                               "tuple": tuple, "any": Any}


def _type_label(t: Any) -> str:
    """A type as the short name a plan shows: ``int``, ``float | None``, ``any``."""
    if t is None or t is Any or t is inspect.Parameter.empty:
        return "any"
    if isinstance(t, str):
        return t
    admits_none, base = _optional_parts(t)
    name = _type_name(base) or "any"
    return f"{name} | None" if admits_none and base is not t else name


def _dtype_type(series: pd.Series) -> Any:
    """The Python type a column of real data holds, or None when mixed/unknown."""
    kind = getattr(series.dtype, "kind", None)
    if kind == "b":
        return bool
    if kind in "iu":
        return int
    if kind == "f":
        return float
    present = series.dropna() if kind == "O" else series
    types_ = {type(v) for v in present}
    return types_.pop() if len(types_) == 1 else None


def _return_hint(fn: Any) -> Any:
    """A tool's resolved return annotation, or None."""
    if fn is None:
        return None
    try:
        return typing.get_type_hints(fn, include_extras=True).get("return")
    except Exception:
        try:
            ann = _signature(fn).return_annotation
        except (TypeError, ValueError):
            return None
        return None if ann is inspect.Parameter.empty else ann


def _record_fields(cls: Any) -> dict | None:
    """Field name → type for a TypedDict or dataclass, else None."""
    import dataclasses
    if isinstance(cls, type) and (dataclasses.is_dataclass(cls)
                                  or (issubclass(cls, dict) and hasattr(cls, "__annotations__"))):
        try:
            return dict(typing.get_type_hints(cls))
        except Exception:
            return dict(getattr(cls, "__annotations__", {}))
    return None


def _declared_schema(fn: Any) -> dict | None:
    """The columns a tool-backed source declares (008 C5), or None.

    ``-> Annotated[pd.DataFrame, Readings]``, where ``Readings`` is a TypedDict
    or dataclass, names every column and its type.
    """
    hint = _return_hint(fn)
    if typing.get_origin(hint) is typing.Annotated:
        base, *extras = typing.get_args(hint)
        if base is pd.DataFrame:
            for extra in extras:
                fields = _record_fields(extra)
                if fields is not None:
                    return fields
    return None


def _payload_type(kind: str | None, fn: Any) -> Any:
    """The type a verb's payload column will hold, from the tool's return."""
    hint = _return_hint(fn)
    if hint is None or kind in (None, "filter", "source", "widen"):
        return None
    if typing.get_origin(hint) is typing.Annotated:
        hint = typing.get_args(hint)[0]
    if kind == "expand":
        args = typing.get_args(hint)
        if typing.get_origin(hint) in (list, set, frozenset) and args:
            return args[0]
        if typing.get_origin(hint) is tuple and args:
            return args[0] if len(set(args) - {Ellipsis}) == 1 else None
        return None
    return hint


def _expectation(operation: "Operation") -> dict:
    """The settings of a step's ``mod.expect(…)`` layers, merged."""
    out: dict = {}
    for m in operation.modifiers:
        if m.kind == "expect":
            out.update(m.params)
    return out


def _expected_columns(expect: dict) -> tuple[list, dict]:
    """(names, {name: type}) from an expectation's ``columns``."""
    columns = expect.get("columns")
    if isinstance(columns, dict):
        return list(columns), {k: _TYPE_NAMES.get(v, v) for k, v in columns.items()}
    return list(columns or []), {}


def _rows_plan(kind, rule, expected, n_in, expect, label) -> dict:
    """The row axis of a plan (008 C9): exact, stated, bounded or unknown."""
    if any(k in expect for k in ("rows", "min_rows", "max_rows")):
        plan = {"certainty": "stated"}
        for key in ("rows", "min_rows", "max_rows"):
            if key in expect:
                plan[{"rows": "count", "min_rows": "min", "max_rows": "max"}[key]] = expect[key]
        return plan
    if expected is not None:
        return {"certainty": "exact", "count": expected}
    if rule == "at_most" and n_in is not None:
        return {"certainty": "bounded", "min": 0, "max": n_in,
                "because": f"{kind} keeps at most the {n_in} rows it reads",
                "resolve": [f"run {label}"]}
    if rule == "per_group" and n_in is not None:
        return {"certainty": "bounded", "min": 1 if n_in else 0, "max": n_in,
                "because": "one row per group; the groups come from the data",
                "resolve": [f"run {label}"]}
    because = {
        "source": f"{label} is a source that hasn't run; its rows come from its data",
        "expand": f"expand: how many items {label} returns per row is only known by running",
    }.get(kind, "its input's row count isn't known yet")
    resolve = [f"run {label}" if kind in ("source", "expand") else "run the steps before it"]
    if kind == "expand":
        resolve.append("annotate a fixed length: -> tuple[T, T]")
    resolve.append("state it on the step: mod.expect(rows=…)")
    return {"certainty": "unknown", "because": because, "resolve": resolve}


def _columns_plan(kind, names, columns_open, expect, label, upstream) -> dict:
    """The column axis of a plan: exact, stated, bounded (these + more) or unknown."""
    if expect.get("columns") is not None:
        return {"certainty": "stated", "names": list(names),
                "more": bool(expect.get("more_columns"))}
    if not columns_open:
        return {"certainty": "exact", "names": list(names)}
    if kind == "source":
        because = f"{label} returns a DataFrame with no declared columns"
        resolve = [f"run {label}",
                   "annotate the return: -> Annotated[pd.DataFrame, YourTypedDict]",
                   "state them on the step: mod.expect(columns=[…], more_columns=True)"]
    else:
        because = f"its input {upstream!r} doesn't know all its columns yet"
        resolve = [f"run {upstream!r}", f"declare {upstream!r}'s columns"]
    return {"certainty": "bounded" if names else "unknown", "names": list(names),
            "more": True, "because": because, "resolve": resolve}


def _declared_fits(column_type: Any, annotation: Any) -> bool | None:
    """Does a column declared as *column_type* fit a parameter? None when unsure."""
    _, base = _optional_parts(annotation)
    origin = typing.get_origin(base) or base
    col_origin = typing.get_origin(column_type) or column_type
    if not isinstance(origin, type) or origin is object or not isinstance(col_origin, type):
        return None
    if origin is float and col_origin is int:
        return True                                   # an int fits a float
    return issubclass(col_origin, origin)


def _output_mismatch(operation: "Operation", data: pd.DataFrame) -> str | None:
    """How a real output breaks what its step declared or stated, or None.

    008 C5/C9: a source's declared schema and ``mod.expect`` are promises the
    plan was built on — when the data breaks one, the step fails, never
    silently.
    """
    expect = _expectation(operation)
    verb = operation.shape_verb
    if verb is not None and verb.kind == "source":
        fn = operation.fn or TOOLS.get(operation.tool_id)
        schema = _declared_schema(fn) if fn is not None else None
        if schema is not None and list(schema) != list(data.columns):
            return (f"{operation.tool_id} declares columns {', '.join(schema)}; "
                    f"it returned {', '.join(map(str, data.columns)) or 'none'}")
    n = len(data)
    if isinstance(expect.get("rows"), int) and n != expect["rows"]:
        return f"expected {expect['rows']} rows, got {n}"
    if isinstance(expect.get("min_rows"), int) and n < expect["min_rows"]:
        return f"expected at least {expect['min_rows']} rows, got {n}"
    if isinstance(expect.get("max_rows"), int) and n > expect["max_rows"]:
        return f"expected at most {expect['max_rows']} rows, got {n}"
    if expect.get("columns") is not None:
        names, _ = _expected_columns(expect)
        have = list(data.columns)
        missing = [c for c in names if c not in have]
        extra = [c for c in have if c not in names]
        if missing or (extra and not expect.get("more_columns")):
            return (f"expected columns {', '.join(names)}"
                    f"{' (and maybe more)' if expect.get('more_columns') else ''}; "
                    f"got {', '.join(map(str, have)) or 'none'}")
    return None


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


def _optional_parts(annotation: Any) -> tuple[bool, Any]:
    """(does it admit None?, the annotation without None) — ``int | None`` → (True, int)."""
    if annotation is Any or isinstance(annotation, str):
        return True, annotation
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        members = [a for a in typing.get_args(annotation) if a is not type(None)]
        admits = len(members) < len(typing.get_args(annotation))
        if len(members) == 1:
            return admits, members[0]
        return admits, typing.Union[tuple(members)] if members else annotation
    return annotation is type(None), annotation


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


def _arg_docs(fn: Callable) -> dict[str, str]:
    """Per-parameter text from a Google-style ``Args:`` docstring section.

    A form shows this as the field's help; the summary line stays the tool's
    own description. Continuation lines are folded into the parameter above them.
    """
    doc = inspect.getdoc(fn) or ""
    sections = {"args", "arguments", "parameters", "returns", "return", "raises",
                "yields", "examples", "example", "note", "notes", "attributes"}
    out: dict[str, str] = {}
    current, in_args = None, False
    for raw in doc.splitlines():
        stripped = raw.strip()
        if stripped.rstrip(":").lower() in sections:
            in_args = stripped.rstrip(":").lower() in ("args", "arguments", "parameters")
            current = None
            continue
        if not in_args or not stripped:
            continue
        name_part, sep, desc = stripped.partition(":")
        name = name_part.split("(")[0].strip().lstrip("*")
        if sep and name.isidentifier():
            out[name] = desc.strip()
            current = name
        elif current:                                # a wrapped continuation line
            out[current] = f"{out[current]} {stripped}".strip()
    return out


def _param_type_info(annotation: Any) -> tuple[str | None, list | None, bool]:
    """``(type_name, choices, nullable)`` for a parameter annotation.

    Keeps the inner type of ``Optional[X]`` (and sets ``nullable``) and the
    options of ``Literal[...]`` (with their own type as ``type_name``), so a form
    renders a dropdown or a typed field instead of a bare "Optional"/"Literal".
    """
    if annotation is inspect.Parameter.empty:
        return None, None, False
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = typing.get_args(annotation)
        nullable = type(None) in args
        inner = [a for a in args if a is not type(None)]
        if len(inner) == 1:
            name, choices, _ = _param_type_info(inner[0])
            return name, choices, nullable
        names = [n for n in (_type_name(a) for a in inner) if n]
        return (" | ".join(names) or None), None, nullable
    if origin is typing.Literal:
        choices = list(typing.get_args(annotation))
        element = _type_name(type(choices[0])) if choices else None
        return element, choices, False
    return _type_name(annotation), None, False


def tool_entry(tool_id: str, fn: Callable, origin: str) -> dict:
    """One tool as a palette entry: what it is, where it came from, what it takes.

    ``description`` is the docstring's first line, which is why those first
    lines are written as user-facing sentences rather than developer notes.
    ``origin`` lets a client separate the system's tools from the user's — the
    builtins are always available and rarely what someone is looking for, so a
    palette usually groups or hides them.

    Each parameter carries enough to render a form field: ``type`` (the inner
    type of an ``Optional``, not the word "Optional"), ``choices`` (a
    ``Literal``'s options), ``nullable``, and ``description`` (its ``Args:`` text).
    """
    doc = (inspect.getdoc(fn) or "").strip()
    try:
        signature = inspect.signature(fn)
        parameters = list(signature.parameters.values())
    except (TypeError, ValueError):
        signature, parameters = None, []
    # Resolve string annotations (PEP 563) to real types so Literal/Optional stay
    # inspectable; fall back to the raw annotation when a forward ref won't resolve.
    try:
        hints = typing.get_type_hints(fn, include_extras=True)
    except Exception:
        hints = {}
    arg_docs = _arg_docs(fn)
    return_ann = hints.get("return")
    if return_ann is None and signature is not None:
        return_ann = signature.return_annotation
    returns = _type_name(return_ann if return_ann is not None
                         else inspect.Parameter.empty)

    params, takes_row = [], False
    for parameter in parameters:
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            takes_row = True
            continue
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        required = parameter.default is inspect.Parameter.empty
        annotation = hints.get(parameter.name, parameter.annotation)
        type_name, choices, nullable = _param_type_info(annotation)
        params.append({
            "name": parameter.name,
            "required": required,
            "default": None if required else parameter.default,
            "type": type_name,
            "choices": choices,
            "nullable": nullable,
            "description": arg_docs.get(parameter.name),
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
    """``mutate`` — n rows in, n rows out, with *fn*'s result as a new column.

    The input columns are **kept**, which is the point: mapping a score over a
    table gives you the table plus a score, not a bare list of scores.
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

    data = frame.copy()
    data[name] = _typed(values, frame.index)
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
    blocked = _upstream_failures(source)
    keep, records = [], []
    for index, row in _units(frame):
        if index in blocked:
            # 008 C10: a failed row is carried through, still failed, so the
            # failure stays visible downstream instead of being filtered away.
            record = {**_blocked(*blocked[index]), "kept": True}
            keep.append(True)
            records.append(record)
            continue
        value, record = _call(fn, row, retries)
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

    data = frame.copy()
    data[name] = _typed(keys, frame.index)
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
    return Output(data=data, ledger=_ledger(records, index),
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
    out_rows, records = [], []
    for index, row in _units(frame):
        arg = row
        if index in blocked:
            records.append({**_blocked(*blocked[index]), "unit": index})
            out_rows.append({**arg, name: None})
            continue
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

    # Column by column, so a carried int column and the payload both keep their
    # type when a failed unit leaves a gap (008 R8) — `DataFrame(rows)` would
    # turn every int column with a None into float64.
    data = pd.DataFrame(index=range(len(out_rows)))
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
    frame = _normalize_missing(_str_columns(rows(value), "the source"))
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
    return Output(data=data, ledger=_ledger(records, ledger_index),
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
        out.ledger["error"] = f"caught {caught}; used the default"
        out.ledger["caught"] = True
    return out


def _source_failure(error: str, caught: Any) -> Output:
    return Output(
        data=pd.DataFrame({PAYLOAD: [None]}, index=[0], dtype=object),
        ledger=_ledger([{"status": "failed", "error": error, "attempts": 1,
                         "seconds": 0.0, "caught": caught}], [0]),
        meta={"verb": "source", "form": "scalar", "payload": None})


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


#: "No default given" to `mod.try_except` — distinct from `default=None`.
_NO_DEFAULT = object()


def _caught_by(exc: BaseException, on: Sequence[str] | None) -> bool:
    """Is *exc* one of the exception types named in ``on=`` (any, when None)?"""
    if not on:
        return True
    names = {on} if isinstance(on, str) else set(on)
    return any(k.__name__ in names for k in type(exc).__mro__)


def _d_try_except(fn: Callable, *, default: Any = _NO_DEFAULT,
                  on: Sequence[str] | None = None) -> Callable:
    """``mod.try_except(default=0, on=[ValueError])`` — let a unit's failure through.

    Without it, a failed row stops ``run_all``. With it, a caught failure
    either becomes ``default`` (the row completes; the error stays in the
    ledger) or, with no default, the row stays failed and the run carries on —
    rows that read it downstream are blocked, not run. ``on=`` limits which
    exceptions are caught; others still stop the run. Order is semantics:
    ``[mod.try_except(…), mod.retry(times=2)]`` retries first.
    """
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _Tolerated:
            raise
        except Exception as exc:
            if not _caught_by(exc, on):
                raise
            error = f"{type(exc).__name__}: {exc}"
            if default is not _NO_DEFAULT:
                return _Caught(default, error)
            raise _Tolerated(error) from exc
    run.__name__ = f"try_except({getattr(fn, '__name__', 'fn')})"
    return run


def _d_expect(fn: Callable, *, rows: int | None = None, min_rows: int | None = None,
              max_rows: int | None = None, columns: Any = None,
              more_columns: bool = False) -> Callable:
    """``mod.expect(…)`` — what the author knows the step's output will be (008 C9).

    It changes nothing about how the tool runs. Staging uses it as the plan
    (marked ``stated``), declaration refuses it when it contradicts what core
    already knows, and the run fails the step when the output doesn't match.
    ``columns`` is a list of names, or ``{name: type}``; ``more_columns=True``
    says those are some of the columns, not all.
    """
    return fn


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
    * bound arguments fill the rest, and an explicit argument **wins** a name
      collision with a column (008 N2): the step says ``city="NYC"``, so the
      tool gets ``"NYC"`` whether or not the input happens to have a ``city``;
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
        merged = {**row, **literals}
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
    #: The raw verb/decorator function, kept for introspection only
    #: (:func:`modifier_catalog` reads its defaults). Never serialized.
    verb: Callable | None = None


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
    # `over` is authoring sugar for the input and is hoisted out of the
    # modifier, so it is never a stored modifier parameter.
    extra = ()
    return ModifierKind(name, cls, apply,
                        _accepted_params(verb, extra) if verb else None,
                        verb)


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
    _kind("expect",   "execution", _d_expect, _d_expect),
    _kind("try_except", "execution", _d_try_except, _d_try_except),
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
    "replace": (bool,),
    "rows": (int, list, dict),
}

#: Where one verb means something different by the same parameter name.
#: ``collapse(by=)`` is a single grouping column — it becomes a column name in
#: the output, so it must be hashable. ``sort(by=)`` is an ordering, which is
#: naturally several columns.
PARAM_TYPES_BY_VERB: dict[str, dict[str, tuple[type, ...]]] = {
    "sort": {"by": (str, list, tuple)},
    "try_except": {"on": (list, tuple, str)},
    "expect": {"rows": (int,), "min_rows": (int,), "max_rows": (int,),
               "columns": (list, tuple, dict), "more_columns": (bool,)},
}

#: Shape verbs whose literal setting is mandatory — caught at declaration (005
#: A2) instead of raised at run. ``widen`` is absent on purpose: a tuple cell
#: auto-names, so ``columns=`` is optional there.
REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "select": (),                      # columns= or rows= — checked in `check`
    "drop": ("columns",),
    "rename": ("columns",),
    "sort": ("by",),
}






def _required_settings(kind: str) -> tuple[str, ...]:
    """Settings a modifier cannot run without (008 O).

    :data:`REQUIRED_PARAMS` for the shape verbs that default theirs to ``None``,
    plus every keyword the modifier's own function takes with no default —
    ``retry(times=)``, ``timeout(seconds=)`` — so a new modifier is covered
    without a second list.
    """
    names = list(REQUIRED_PARAMS.get(kind, ()))
    entry = MODIFIERS.get(kind)
    if entry is not None and entry.verb is not None:
        try:
            parameters = inspect.signature(entry.verb).parameters.values()
        except (TypeError, ValueError):
            parameters = ()
        names += [p.name for p in parameters
                  if p.name not in ("source", "fn", "_source")
                  and p.kind is inspect.Parameter.KEYWORD_ONLY
                  and p.default is inspect.Parameter.empty
                  and p.name not in names]
    return tuple(names)


#: The shape verbs, derived — never written out a second time.
SHAPE_VERBS: tuple[str, ...] = tuple(
    name for name, kind in MODIFIERS.items() if kind.cls == "shape"
)


def is_shape(kind: str) -> bool:
    """Does this modifier kind change the grid's shape?"""
    return kind in MODIFIERS and MODIFIERS[kind].cls == "shape"


#: kind -> decorator factory, derived from :data:`MODIFIERS`.
DECORATORS: dict[str, Callable] = {n: k.apply for n, k in MODIFIERS.items()}


def _setting_type(verb: str, param: str) -> str | None:
    """A readable type name for a verb's setting, from the PARAM_TYPES tables."""
    types = PARAM_TYPES_BY_VERB.get(verb, {}).get(param) or PARAM_TYPES.get(param)
    takes_tool = param in TOOL_SETTINGS.get(verb, ())
    if types:
        return " | ".join(t.__name__ for t in types) + (" | tool" if takes_tool else "")
    return "tool" if takes_tool else None


def _modifier_settings(name: str, kind: ModifierKind) -> list[dict]:
    """The settings a verb form shows, each with type, required and default."""
    if name == "source":                 # a source holds a literal — no settings
        return []
    settings: list[dict] = []
    takes_extra = False
    try:
        for p in inspect.signature(kind.verb).parameters.values():
            if p.name in ("source", "fn"):
                continue
            if p.kind is inspect.Parameter.VAR_KEYWORD:
                takes_extra = True
                continue
            if p.kind is inspect.Parameter.VAR_POSITIONAL:
                continue
            required = p.default is inspect.Parameter.empty
            settings.append({"name": p.name, "type": _setting_type(name, p.name),
                             "required": required,
                             "default": None if required or p.default is _NO_DEFAULT
                             else p.default})
    except (TypeError, ValueError):
        pass
    if takes_extra:                       # sweep: extra named params are the data
        settings.append({"name": "<swept>", "type": "list", "required": False,
                         "default": None,
                         "description": "any extra named parameter is swept; "
                                        "its value is a list of values"})
    return settings


#: Which verbs apply a tool (008 K13). The column verbs apply none — `check`
#: refuses one; `source`, `expand` and `collapse` fall back to a builtin.
_TAKES_TOOL: dict[str, Any] = {
    "map": True, "filter": True, "group": True, "sweep": True,
    "select": False, "drop": False, "widen": False, "slice": False,
    "rename": False, "sort": False, "distinct": False,
    "source": "optional", "expand": "optional", "collapse": "optional",
    "retry": None, "timeout": None, "expect": None, "try_except": None,
}


def modifier_catalog() -> dict[str, dict]:
    """Every modifier kind as JSON — class, row rule, and settings per verb.

    Feeds ``GET /modifiers`` (docs/react-api.md): a client builds each verb's
    form from this instead of hard-coding the fields. Unlike :data:`MODIFIERS`
    — which holds the appliers and so cannot be serialized — this is plain data.
    """
    return {
        name: {
            "name": name,
            "class": kind.cls,                                   # shape | execution
            "row_rule": ROWS_RULE.get(name) if kind.cls == "shape" else None,
            "settings": _modifier_settings(name, kind),
            # 008 K13: whether the verb applies a tool — true (needs one),
            # false (refuses one), "optional" (has a default) — and the
            # default it uses. Execution modifiers wrap the step's tool
            # rather than choosing one, so theirs is null.
            "takes_tool": _TAKES_TOOL.get(name),
            "default_tool": (DEFAULT_TOOL.get(name)
                             if _TAKES_TOOL.get(name) not in (True, None) else None),
        }
        for name, kind in MODIFIERS.items()
    }

# ─────────────────────────────────────────────────────────────────────────
# The deferred half: a stack of modifiers, as data
# ─────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, eq=False)
class Modifier:
    """One entry in an Operation's stack: what to apply, and with what.

    ``params`` are **literals only** — how to orchestrate, never what data. A
    reference to another step is not a modifier setting: the data input lives in
    :attr:`Operation.input` and a value reference lives in
    :attr:`Operation.arguments`. ``over=`` is accepted as authoring sugar but is
    hoisted out of the modifier into the input slot, so it never lands here.
    """

    kind: str
    params: dict = field(default_factory=dict)

    def __call__(self, source: Any, /, **literals) -> "Operation":
        """``mod.select(columns=["n"])(wf["r"])`` — a verb that needs no tool, applied.

        008 K8: the same Operation as ``op("identity")[mod.select(…)](wf["r"])``,
        using the verb's default tool (``identity``, or ``gather`` for
        ``collapse``). Verbs that need a tool of their own refuse.
        """
        default = DEFAULT_TOOL.get(self.kind)
        if default is None or self.kind in ("map", "filter", "group"):
            raise TypeError(
                f"{self.kind!r} needs a tool: write <tool>[mod.{self.kind}(...)](…)")
        return Operation(tool_id=default, fn=BUILTIN_TOOLS[default])[self](
            source, **literals)

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


#: Marks "no input given" to ``Operation.__call__``, distinct from ``None``.
_NO_SOURCE = object()

#: 008 C7: a selection as a tool's input is two reshapes in one step.
_SELECTION_INPUT = ("a selection can't be a tool's input: make it its own step "
                    "(wf[\"part\"] = wf[\"p\"][…]) and pass wf[\"part\"]")

#: 008 K3: an Operation passed where a step's data belongs used to run as a
#: one-cell source and report `completed` with `{'value': [None]}`.
_NESTED_OPERATION = ("an operation can't be an input yet; make it its own step "
                     "and pass wf[…]: wf[\"inner\"] = <operation>, then "
                     "<tool>[…](wf[\"inner\"])")


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
    #: The step whose grid this reads — the DATA, taken from the call position.
    #: Its own slot so no reference ever hides inside a modifier: modifiers say
    #: only *how* to orchestrate, never *what* data. A StepRef, or None (source).
    input: Any = None
    #: Every grid a **combine** verb reads (`join`/`stack`/`zip`), primary first
    #: — `()` for an ordinary single-input step, where :attr:`input` is the one
    #: grid. A combine sets both: ``inputs`` holds them all, ``input`` the first.
    inputs: tuple = ()
    #: For a **bound tool** (a ``@bound_tool`` method), the resource whose
    #: instance it runs on — a :class:`ResRef`, resolved at run like any other
    #: ``$res``. ``None`` for an ordinary tool. The method's name is the last
    #: segment of :attr:`tool_id` (``"FakeDB.lookup"``).
    bound_to: Any = None

    @property
    def grids(self) -> tuple:
        """The grid inputs, primary first — `inputs` for a combine, else `input`."""
        if self.inputs:
            return self.inputs
        return (self.input,) if self.input is not None else ()

    @property
    def reads(self) -> list[str]:
        """Every step id this reads — the grid input(s) plus any reference arguments."""
        ids = [str(g) for g in self.grids]
        ids += [str(v) for v in self.arguments.values() if isinstance(v, StepRef)]
        # 008 C1: a setting may read a step too — `select(columns=wf["cols"])`.
        ids += [str(v) for m in self.modifiers for v in m.params.values()
                if isinstance(v, StepRef)]
        return ids

    @property
    def resources(self) -> list[str]:
        """Every resource this uses — the instance it is bound to, then arguments."""
        names = [self.bound_to.name] if isinstance(self.bound_to, ResRef) else []
        names += [v.name for v in self.arguments.values() if isinstance(v, ResRef)]
        return names

    def _add(self, kind: str, **params) -> "Operation":
        # `over=` is accepted as authoring sugar but never stored in a modifier:
        # it is the data input, so it is hoisted to its own slot. Modifiers stay
        # literal-only and the data stays explicit.
        over = params.pop("over", None)
        if isinstance(over, StepRef) and over.selected:
            raise TypeError(_SELECTION_INPUT)
        if over is not None and not isinstance(over, (StepRef, str)):
            if isinstance(over, Operation):
                raise TypeError(_NESTED_OPERATION)
            raise TypeError(
                "one step reads one input; to combine steps use join, stack or "
                f"zip_ (over= got a {type(over).__name__})")
        new_input = self.input if over is None else (
            over if isinstance(over, StepRef) else StepRef(over))
        return Operation(self.tool_id,
                         self.modifiers + (Modifier(kind, params),),
                         self.arguments, self.fn, new_input,
                         bound_to=self.bound_to)

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
        """Add bound arguments — literals, or a StepRef to read another step's value."""
        return Operation(self.tool_id, self.modifiers,
                         {**self.arguments, **literals}, self.fn, self.input,
                         bound_to=self.bound_to)

    # ── as plain data (what the light export carries) ────────────────────
    def to_dict(self) -> dict:
        """The Operation as JSON-safe data. The carried function is **not** in it.

        This is the whole point of storing modifiers as descriptors: a step's
        definition is a few strings and numbers, so exporting a workflow costs
        nothing and does not drag payloads along.
        """
        blob = {
            "tool_id": self.tool_id,
            "input": _encode_ref(self.input),          # {"$ref": id} or null — the data
            "arguments": {k: _encode_argument(v) for k, v in self.arguments.items()},
            "modifiers": [{"kind": m.kind,
                           "params": {k: _encode_argument(v) for k, v in m.params.items()}}
                          for m in self.modifiers],     # literal-only
        }
        if self.inputs:                                 # a combine reads many grids
            blob["inputs"] = [_encode_ref(g) for g in self.inputs]
        if self.bound_to is not None:                   # a bound tool's instance
            blob["bound_to"] = _encode_argument(self.bound_to)
        return blob

    @classmethod
    def from_dict(cls, blob: dict, tools: dict[str, Callable] | None = None
                  ) -> "Operation":
        """Rebuild an Operation from :meth:`to_dict`, re-attaching its function."""
        table = {**BUILTIN_TOOLS, **TOOLS, **(tools or {})}
        fn = table.get(blob["tool_id"])
        # Legacy (v1) stored the input as `over` inside a modifier; hoist it.
        modifiers, hoisted = [], None
        for m in blob["modifiers"]:
            params = dict(m["params"])
            over = params.pop("over", None)
            if over is not None:
                hoisted = over
            modifiers.append(Modifier(m["kind"], {k: _decode_argument(v)
                                                  for k, v in params.items()}))
        arguments = {k: _decode_argument(v)
                     for k, v in (blob.get("arguments") or {}).items()}
        inputs = tuple(_decode_ref(g) for g in blob.get("inputs") or ())
        bound_to = _decode_argument(blob.get("bound_to"))
        return cls(
            tool_id=blob["tool_id"],
            modifiers=tuple(modifiers),
            arguments=arguments,
            # A bound tool's function comes from its resource type, never from
            # TOOLS; the workflow attaches it once it knows the type.
            fn=None if bound_to is not None
            else (fn.fn if isinstance(fn, ToolHandle) else fn),
            input=_decode_ref(blob.get("input", hoisted)),
            inputs=inputs,
            bound_to=bound_to,
        )

    # ── the other half: hand the decorated tool some data ────────────────
    def __call__(self, source: Any = _NO_SOURCE, /, *more: Any, **literals) -> Any:
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
        if more:
            # 008 C1: positional arguments after the input bind like keywords.
            literals = {**literals, **_bind_positional(self, source, more, literals)}
        operation = self.bind(**literals) if literals else self
        if isinstance(source, Operation) or any(isinstance(v, Operation) for v in more):
            raise TypeError(_NESTED_OPERATION)
        if isinstance(source, StepRef):
            return operation._wire(source)
        if source is _NO_SOURCE:
            if operation.shape_verb is not None \
                    and operation.shape_verb.kind in ("source", "sweep"):
                # Nothing to read: `tool[mod.source()](prompt="hi")` only binds.
                return operation
            raise TypeError(f"{self.tool_id}: pass the data to apply it to, "
                            "or a step reference to wire it")
        return operation.run(source)

    def _wire(self, ref: "StepRef") -> "Operation":
        """Record that this step reads *ref* as its input, inferring a verb if none is set."""
        if ref.selected:
            raise TypeError(_SELECTION_INPUT)
        if self.input is not None:
            # 008 K4: the call used to win silently over `over=`.
            raise TypeError(
                f"this step already reads {str(self.input)!r} (over=), and the "
                f"call passes {ref.id!r} too. Give the input once: in the call, "
                f"or as over=, not both.")
        based = Operation(self.tool_id, self.modifiers,
                          self.arguments, self.fn, ref, bound_to=self.bound_to)
        if based.bound_to is not None and based.fn is None \
                and ref.workflow is not None:
            # The reference knows its workflow, which knows the resource's
            # declared type — enough to find the method and infer from it.
            based = _attach_bound(based, ref.workflow.resources)
        if based.shape_verb is not None:
            return based
        upstream = None
        if ref.workflow is not None:
            step = ref.workflow.steps.get(ref.id)
            # A staged upstream still predicts its payload column, which is what
            # lets `total(acc, value)` read as a reducer before anything runs.
            upstream = None if step is None else step.output
        fn = self.fn or TOOLS.get(self.tool_id) \
            or BUILTIN_TOOLS.get(self.tool_id)
        kind = ("map" if fn is None
                else infer_verb(fn, upstream, self.arguments)[0])
        return based._add(kind)               # _add carries based.input forward

    def run(self, source: Any, tools: dict[str, Callable] | None = None) -> Any:
        """Compile the stack and apply it to *source*.

        Mirrors ``Tool.run()`` in the registry: the deferred form is the
        default and this is the immediate escape hatch. *tools* is needed only
        when this Operation names its tool by id (``op("score")``) rather than
        carrying it (``score[...]`` from a ``@tool`` handle).
        """
        if self.resources:
            raise TypeError(
                f"{self.tool_id} uses resource(s) "
                f"{', '.join(map(repr, self.resources))}, which only a workflow "
                "can supply: wf.run(step_id, resources={name: object})."
            )
        if isinstance(source, StepRef):
            raise TypeError(
                f"cannot run against the reference {source.id!r} — a reference "
                "names a step, it is not data. Wire it as the step's input via "
                f"the call position: wf[...] = <tool>[mod...](wf[{source.id!r}]). "
                "Calling an Operation directly is for data you already hold."
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
        # tool comes last because that is what the layers close over. The input
        # is flattened to its id, so a repr does not depend on how a step was
        # named (same reason __eq__ flattens it).
        stack = "".join(f"{m!r} ∘ " for m in self.layers)
        src = f" over={self.input.id!r}" if isinstance(self.input, StepRef) else ""
        return f"<Operation {stack}{self.tool_id}{src}>"


def op(tool_id: str, **arguments) -> Operation:
    """Start building an Operation for the tool named *tool_id*."""
    return Operation(tool_id=tool_id, arguments=arguments)


# ─────────────────────────────────────────────────────────────────────────
# The authoring surface: objects instead of strings
# ─────────────────────────────────────────────────────────────────────────
# Everything here is sugar that produces the exact same `Operation` data. The
# gain is that a typo becomes a NameError at import rather than a silent
# literal at run time, and an editor can autocomplete.


# ─────────────────────────────────────────────────────────────────────────
# Selection — wf["p"][1:5][cols["name":"price"]] (008 C7)
# ─────────────────────────────────────────────────────────────────────────
# Two type rules: column names are strings, row selectors are integers. And one
# syntax rule: a plain bracket selects rows, `cols[…]` selects columns. Each
# part normalizes to its saved form at once, so every spelling of the same
# selection is the same value — and saves identically.


class SelectionError(ValueError):
    """A selection that can't be made — refused when written, or failed at run."""


def _is_int(value: Any) -> bool:
    return isinstance(value, numbers.Integral) and not isinstance(value, bool)


def _row_part(key: Any) -> Any:
    """A row selector in saved form: an int, a list of ints, or {start, stop}."""
    if isinstance(key, Rows):
        return key.sel
    if isinstance(key, str):
        raise SelectionError(
            f"columns are selected with cols: wf[…][cols[{key!r}]] — a plain "
            "bracket selects rows, by position")
    if _is_int(key):
        return int(key)
    if isinstance(key, slice):
        if key.step is not None:
            raise SelectionError("a row range can't have a step (start:stop only)")
        for end in (key.start, key.stop):
            if end is not None and not _is_int(end):
                raise SelectionError(
                    f"a row range takes int positions, got {type(end).__name__}")
        return {"start": key.start, "stop": key.stop}
    if isinstance(key, list):
        if not key:
            raise SelectionError("an empty row selection selects nothing")
        if not all(_is_int(k) for k in key):
            raise SelectionError("a list of rows takes int positions only")
        return [int(k) for k in key]
    raise SelectionError(
        f"rows are selected by int position, an int range or a list of ints; "
        f"got {type(key).__name__}")


def _col_part(key: Any) -> dict:
    """A column selector in saved form: {names}, {from, to} or {positions}."""
    if isinstance(key, str):
        return {"names": [key]}
    if _is_int(key):
        return {"positions": [int(key)]}
    if isinstance(key, slice):
        if key.step is not None:
            raise SelectionError("a column range can't have a step")
        ends = [e for e in (key.start, key.stop) if e is not None]
        if all(isinstance(e, str) for e in ends) and ends:
            return {"from": key.start, "to": key.stop}
        if all(_is_int(e) for e in ends):
            return {"positions": {"start": key.start, "stop": key.stop}}
        raise SelectionError(
            "a column range is by name (cols['a':'c']) or by position "
            "(cols[0:3]), not both")
    if isinstance(key, list):
        if not key:
            raise SelectionError("an empty column selection selects nothing")
        if all(isinstance(k, str) for k in key):
            return {"names": list(key)}
        if all(_is_int(k) for k in key):
            return {"positions": [int(k) for k in key]}
        raise SelectionError(
            "cols[…] takes names or positions, not both in one selection")
    raise SelectionError(
        f"cols[…] takes a name, a name range, a list of names, a position, a "
        f"position range or a list of positions; got {type(key).__name__}")


@dataclass(frozen=True)
class Rows:
    """``rows[1:5]`` — an explicit row part. Optional: a bare int is rows anyway."""
    sel: Any = field(hash=False)


@dataclass(frozen=True)
class Cols:
    """``cols["name":"price"]`` — the only way to select columns."""
    sel: Any = field(hash=False)


class _RowsIndexer:
    """``rows[…]`` selects rows; ``rows(value)`` is the old coercion to a frame."""

    def __getitem__(self, key: Any) -> Rows:
        return Rows(_row_part(key))

    def __call__(self, value: Any, *, axis: str = "rows") -> pd.DataFrame:
        return _rows_frame(value, axis=axis)

    def __repr__(self) -> str:
        return "rows"


class _ColsIndexer:
    def __getitem__(self, key: Any) -> Cols:
        return Cols(_col_part(key))

    def __repr__(self) -> str:
        return "cols"


#: ``rows[…]`` and ``cols[…]`` (008 C7). Also callable as before: ``rows(df)``.
rows = _RowsIndexer()
cols = _ColsIndexer()

#: Names a tool, bound tool or resource type can't take: the formula bar's own
#: vocabulary (008 C7).
RESERVED_NAMES = frozenset({"wf", "res", "mod", "rows", "cols", "op", "join",
                            "stack", "zip_"})


def _reserved_problem(name: str, what: str) -> str | None:
    if name in RESERVED_NAMES:
        role = {"rows": "row selection", "cols": "column selection"}.get(
            name, "the formula language")
        return f"{name!r} is reserved for {role}; choose another {what} name"
    return None


def _check_caller_scope(depth: int = 2) -> None:
    """Refuse a declaration made where ``rows``/``cols`` mean something else.

    A script's own ``rows = [10, 20, 30]`` replaces the import, and Python
    evaluates ``rows[1:5]`` on it before core sees anything — a valid-looking,
    wrong row selection. So the names are checked in the declaring scope.
    """
    import sys
    frame = sys._getframe(depth)
    for name, core in (("rows", rows), ("cols", cols)):
        if name in frame.f_locals:
            value = frame.f_locals[name]
        elif name in frame.f_globals:
            value = frame.f_globals[name]
        else:
            continue
        if value is not core and not isinstance(value, (_RowsIndexer, _ColsIndexer)):
            role = "row" if name == "rows" else "column"
            raise TypeError(
                f"{name!r} is reserved for {role} selection, but here it's a "
                f"{type(value).__name__}. Rename your variable")


def _selection_kind(ref: "StepRef") -> str | None:
    """cell / column / row / block for a selection, known without running."""
    if ref.rows is None and ref.columns is None:
        return None
    one_row = _is_int(ref.rows)
    columns = ref.columns or {}
    one_col = (len(columns.get("names") or []) == 1
               or (isinstance(columns.get("positions"), list)
                   and len(columns["positions"]) == 1))
    if one_row and one_col:
        return "cell"
    if one_col:
        return "column"
    if one_row:
        return "row"
    return "block"


def _bound(n: int, start: Any, stop: Any, what: str, step_id: str) -> tuple[int, int]:
    """A half-open range over n items. Past the end fails; it is not trimmed."""
    lo = 0 if start is None else (start + n if start < 0 else start)
    hi = n if stop is None else (stop + n if stop < 0 else stop)
    if not 0 <= lo <= n or not 0 <= hi <= n:
        last = f" ({0}–{n - 1})" if n else ""
        raise SelectionError(
            f"{what} range {start}:{stop} of {step_id!r} goes past the end; it "
            f"has {n} {what}s{last}. For 'up to n', use a slice step")
    return lo, max(lo, hi)


def _position(n: int, i: int, what: str, step_id: str) -> int:
    if not -n <= i < n:
        last = f" (0–{n - 1})" if n else ""
        raise SelectionError(f"{what} {i} of {step_id!r}, which has {n} {what}s{last}")
    return i + n if i < 0 else i


def _resolve_columns(columns: list, sel: Any, step_id: str) -> list:
    """The column names a selection picks, in order, from *columns*."""
    if sel is None:
        return list(columns)
    if isinstance(sel, (list, tuple)):                  # select's plain list form
        sel = {"names": list(sel)}
    if "names" in sel:
        missing = [c for c in sel["names"] if c not in columns]
        if missing:
            raise SelectionError(
                f"{step_id!r} has no column {', '.join(map(repr, missing))} "
                f"(it has {', '.join(map(str, columns))})")
        return list(sel["names"])
    if "from" in sel or "to" in sel:
        for end in (sel.get("from"), sel.get("to")):
            if end is not None and end not in columns:
                raise SelectionError(
                    f"{step_id!r} has no column {end!r} (it has "
                    f"{', '.join(map(str, columns))})")
        lo = 0 if sel.get("from") is None else columns.index(sel["from"])
        hi = len(columns) - 1 if sel.get("to") is None else columns.index(sel["to"])
        if lo > hi:
            raise SelectionError(
                f"cols[{sel.get('from')!r}:{sel.get('to')!r}] runs backwards: "
                f"{sel.get('to')!r} comes before {sel.get('from')!r} in {step_id!r}")
        return list(columns[lo:hi + 1])                # names are inclusive
    positions = sel["positions"]
    if isinstance(positions, dict):
        lo, hi = _bound(len(columns), positions.get("start"), positions.get("stop"),
                        "column", step_id)
        return list(columns[lo:hi])                    # positions are half-open
    return [columns[_position(len(columns), i, "column", step_id)] for i in positions]


def _apply_selection(frame: pd.DataFrame, row_sel: Any, col_sel: Any,
                     step_id: str) -> pd.DataFrame:
    """The block a selection names. Rows keep their ids, so cells stay addressable."""
    out = frame
    if col_sel is not None:
        out = out[_resolve_columns(list(out.columns), col_sel, step_id)]
    if row_sel is not None:
        n = len(out)
        if _is_int(row_sel):
            out = out.iloc[[_position(n, row_sel, "row", step_id)]]
        elif isinstance(row_sel, dict):
            lo, hi = _bound(n, row_sel.get("start"), row_sel.get("stop"), "row", step_id)
            out = out.iloc[lo:hi]
        else:
            out = out.iloc[[_position(n, i, "row", step_id) for i in row_sel]]
    return out


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
    #: A selection of this step (008 C7), in saved form: the row part (an int,
    #: a list of ints or {start, stop}) and the column part ({names},
    #: {from, to} or {positions}). None when the whole step is meant.
    rows: Any = field(default=None, hash=False)
    columns: Any = field(default=None, hash=False)

    def __str__(self) -> str:
        return self.id

    def __repr__(self) -> str:
        parts = "".join(f" {k}={v!r}" for k, v in (("rows", self.rows),
                                                     ("columns", self.columns))
                        if v is not None)
        return f"<{self.id}{parts}>"

    @property
    def selected(self) -> bool:
        return self.rows is not None or self.columns is not None

    def __getitem__(self, key: Any) -> "StepRef":
        """``wf["p"][1:5]``, ``[cols["a":"c"]]``, ``[1:5, cols[…]]`` — in any order.

        A plain part is rows (an int, an int range or a list of ints, or
        ``rows[…]``); ``cols[…]`` is columns. At most one of each, in one
        bracket or two. Refused as written when it can't be a selection.
        """
        parts = key if isinstance(key, tuple) else (key,)
        if len(parts) > 2:
            raise SelectionError(
                "a selection has at most two parts: rows, then cols[…]")
        row_sel, col_sel = self.rows, self.columns
        seen: set[str] = set()
        for part in parts:
            kind = "columns" if isinstance(part, Cols) else "rows"
            if kind in seen or (kind == "rows" and row_sel is not None) or \
                    (kind == "columns" and col_sel is not None):
                raise SelectionError(
                    f"this selection already has its {kind}; a selection has "
                    "one row part and one cols[…] part")
            seen.add(kind)
            if kind == "columns":
                col_sel = part.sel
            else:
                row_sel = _row_part(part)
        return replace(self, rows=row_sel, columns=col_sel)


class _Wf:
    """``wf["orders"]`` — a step in *whichever* workflow the formula is assigned into.

    008 C6: the formula language is two words — ``wf["…"]`` is a step in this
    workflow, ``res["…"]`` is a resource — and a formula must read the same
    whatever the workflow variable is called. This ``wf`` returns an
    **unbound** :class:`StepRef`, which resolves against the workflow it is
    assigned into. A workflow that is itself named ``wf`` shadows it
    harmlessly: its own ``wf["…"]`` names the same step.
    """

    def __getitem__(self, step_id: str) -> StepRef:
        if not isinstance(step_id, str) or not step_id:
            raise KeyError(f"a step reference takes a step id (a string), got {step_id!r}")
        return StepRef(step_id)

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        raise AttributeError(
            f"grid.wf is the step reference, not a workflow — wf.{name} does "
            "not exist. Call it on your Workflow object; write wf[\"step\"] to "
            "name a step in a formula.")

    def __repr__(self) -> str:
        return "wf"


#: ``wf["orders"]`` names a step of the workflow a formula is assigned into.
wf = _Wf()


def _deref(value: Any) -> Any:
    """StepRefs become their ids; everything else passes through."""
    if isinstance(value, StepRef):
        return value.id
    if isinstance(value, dict):
        return {k: _deref(v) for k, v in value.items()}
    return value


def _encode_ref(ref: Any) -> dict | None:
    """A step reference as JSON — ``{"$ref": id}``, distinct from a literal string."""
    if ref is None:
        return None
    blob = {"$ref": str(ref)}
    if isinstance(ref, StepRef):
        if ref.rows is not None:
            blob["rows"] = ref.rows
        if ref.columns is not None:
            blob["columns"] = ref.columns
    return blob


def _is_ref(value: Any) -> bool:
    """True for a ``{"$ref": id}`` reference envelope."""
    return (isinstance(value, dict) and "$ref" in value
            and set(value) <= {"$ref", "rows", "columns"})


def _decode_ref(value: Any) -> Any:
    """JSON back to a StepRef. A bare id string (legacy ``over``) decodes too."""
    if value is None:
        return None
    if _is_ref(value):
        return StepRef(value["$ref"], rows=value.get("rows"),
                       columns=value.get("columns"))
    if isinstance(value, str):
        return StepRef(value)
    return value


#: Version of the saved operation format. 2 added tagged literals (C11),
#: references in settings (C1), tools in settings (C2) and selections (C7).
#: Version 1 files still load (008 K17).
FORMAT_VERSION = 2

#: The tags a saved value can carry. A literal dict that happens to use one of
#: these keys (or any `$` key, or a non-string key) is saved as `$dict`, so a
#: literal can never be read back as a reference.
_TAGS = ("$ref", "$res", "$tool", "$tuple", "$set", "$dict")


def _literal_problem(value: Any) -> str | None:
    """Why *value* is not a literal (008 C11), or None when it is one.

    A literal is what Python's literal syntax writes: ``int``, ``float``,
    ``str``, ``bool``, ``None``, and ``list``/``tuple``/``dict``/``set`` of
    those — ``ast.literal_eval`` minus ``bytes`` and ``complex``. Anything else
    is refused when the step is declared, not when it is saved.
    """
    if value is None or isinstance(value, (bool, str)):
        return None
    if isinstance(value, numbers.Real):          # int, float, numpy numbers; not complex
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            problem = _literal_problem(item)
            if problem:
                return problem
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            problem = _literal_problem(key) or _literal_problem(item)
            if problem:
                return problem
        return None
    kind = type(value).__name__
    if hasattr(value, "isoformat"):
        hint = f"pass a str ({value.isoformat()!r})"
    elif kind == "Decimal":
        hint = f"pass a float or a str ({str(value)!r})"
    elif isinstance(value, (bytes, bytearray)):
        hint = "pass a str"
    elif callable(value):
        hint = "a function belongs in a setting that takes a tool, as a registered @tool"
    else:
        hint = "pass a str, number, bool, None, list, tuple, dict or set"
    article = "an" if kind[:1].lower() in "aeiou" else "a"
    return f"{article} {kind} isn't a literal; {hint}, or make it a step"


def _bind_positional(operation: "Operation", source: Any, values: tuple,
                     given: dict) -> dict:
    """Name the positional arguments after the input (008 C1).

    ``scale(wf["r"], wf["w"])`` is ``scale(wf["r"], weight=wf["w"])``. Each value
    takes the tool's next parameter that is still free: not given by keyword,
    and not supplied by the input — a known input column, or, when the input's
    columns are not known, the first parameter (the row's own value). A
    ``res[…]`` takes the first free parameter its declared type fits.
    """
    fn = operation.fn or TOOLS.get(operation.tool_id) or BUILTIN_TOOLS.get(operation.tool_id)
    if fn is None:
        raise TypeError(f"{operation.tool_id}: pass these arguments by keyword "
                        "— its parameters are not known here")
    parameters = [p for p in _signature(fn).parameters.values()
                  if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                inspect.Parameter.KEYWORD_ONLY)]
    free = [p for p in parameters
            if p.name not in given and p.name not in operation.arguments]
    workflow = getattr(source, "workflow", None)
    step = workflow.steps.get(source.id) if workflow is not None and isinstance(source, StepRef) else None
    if step is not None:
        columns = set(predicted_columns(step.output))
        free_for_values = [p for p in free if p.name not in columns]
        if columns_unknown(step.output) and free_for_values == free and free:
            free_for_values = free[1:]
    else:
        free_for_values = free[1:]
    bound: dict = {}
    for value in values:
        if isinstance(value, ResRef):
            decl = workflow.resources.get(value.name) if workflow is not None else None
            fits = [p for p in free if decl is not None and decl.type is not None
                    and _type_fits(decl.type, p.annotation)]
            target = fits[0] if fits else None
            if target is None:
                raise TypeError(
                    f"{operation.tool_id}: no free parameter fits res[{value.name!r}]"
                    + ("" if decl else " (declare it first with wf.define)")
                    + "; pass it by keyword")
        else:
            target = next((p for p in free_for_values if p in free), None)
            if target is None:
                names = ", ".join(p.name for p in parameters) or "(none)"
                raise TypeError(
                    f"{operation.tool_id}() has no free parameter left for "
                    f"{value!r}; it takes {names}. Pass it by keyword.")
        bound[target.name] = value
        free.remove(target)
    return bound


def _encode_argument(value: Any) -> Any:
    """A bound value as JSON, exactly: a reference, a tool, or a tagged literal.

    ``{"$ref": step}``, ``{"$res": name}``, ``{"$tool": id}``; a literal saves
    as itself where plain JSON keeps its type, and tagged where it would not
    (008 C11): ``{"$tuple": [...]}``, ``{"$set": [...]}``, and ``{"$dict":
    [[k, v], ...]}`` for a dict with non-string (or ``$``) keys.
    """
    if isinstance(value, StepRef):
        return _encode_ref(value)
    if isinstance(value, ResRef):
        return {"$res": value.name}
    if isinstance(value, ToolRef):
        return {"$tool": value.id}
    if isinstance(value, ToolHandle):
        return {"$tool": value.id}
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    if isinstance(value, tuple):
        return {"$tuple": [_encode_argument(v) for v in value]}
    if isinstance(value, (set, frozenset)):
        items = list(value)
        try:
            items = sorted(items)
        except TypeError:
            pass
        return {"$set": [_encode_argument(v) for v in items]}
    if isinstance(value, list):
        return [_encode_argument(v) for v in value]
    if isinstance(value, dict):
        if all(isinstance(k, str) and not k.startswith("$") for k in value):
            return {k: _encode_argument(v) for k, v in value.items()}
        return {"$dict": [[_encode_argument(k), _encode_argument(v)]
                          for k, v in value.items()]}
    if callable(value):
        raise PayloadError(
            f"cannot save {getattr(value, '__name__', value)!r}: a function "
            "is saved by its tool id, so register it with @tool (a lambda "
            "can't be saved)")
    raise PayloadError(f"cannot save a {type(value).__name__}: "
                       f"{_literal_problem(value)}")


def _decode_argument(value: Any) -> Any:
    """The inverse of :func:`_encode_argument` — the same value and type back."""
    if isinstance(value, list):
        return [_decode_argument(v) for v in value]
    if not isinstance(value, dict):
        return value
    if _is_ref(value):
        return _decode_ref(value)
    if set(value) == {"$res"}:
        return ResRef(value["$res"])
    if set(value) == {"$tool"}:
        return ToolRef(value["$tool"])
    if set(value) == {"$tuple"}:
        return tuple(_decode_argument(v) for v in value["$tuple"])
    if set(value) == {"$set"}:
        return {_decode_argument(v) for v in value["$set"]}
    if set(value) == {"$dict"}:
        return {_freeze(_decode_argument(k)): _decode_argument(v)
                for k, v in value["$dict"]}
    return {k: _decode_argument(v) for k, v in value.items()}


def _freeze(key: Any) -> Any:
    """A decoded dict key must be hashable: a list key can only have been a tuple."""
    return tuple(key) if isinstance(key, list) else key


#: "Not known until run" — distinct from None, which is a value.
_UNKNOWN = object()


def _is_tool_value(value: Any) -> bool:
    """A tool given as a setting (008 C2): a registered tool or a reference to one."""
    return isinstance(value, (ToolRef, ToolHandle)) or (
        callable(value) and not isinstance(value, (type, StepRef, ResRef)))


#: Settings that may hold a tool instead of column names (008 C2).
TOOL_SETTINGS: dict[str, tuple[str, ...]] = {
    "sort": ("by",), "group": ("by",), "collapse": ("by",),
    "distinct": ("columns",), "select": ("columns",), "rename": ("columns",),
}


@dataclass(frozen=True)
class ToolRef:
    """A registered tool named in a **setting** — ``{"$tool": "first_letter"}`` (008 C2).

    Resolved at run from the same tool table the step's own tool comes from.
    """

    id: str

    def __repr__(self) -> str:
        return f"<tool {self.id!r}>"


# ─────────────────────────────────────────────────────────────────────────
# Resources — objects a workflow uses that are not data (core-proposals/007)
# ─────────────────────────────────────────────────────────────────────────
# `wf["…"]` is a table, `res["…"]` is a resource, everything else is a literal.
# A resource is declared on the workflow (`wf.define`) from literal settings
# only, saved as that declaration, and supplied live by the caller at run
# (`wf.run(..., resources={name: object})`). Two ways a tool uses one:
#
#   * an **unbound** tool is an ordinary ``@tool`` function with a parameter
#     typed as the resource: ``enrich(city, db: FakeDB)``, bound per step as
#     ``db=res["db"]``;
#   * a **bound** tool is a method of the resource class marked
#     ``@bound_tool``, used on one named instance: ``res["db"].lookup``.


class ResourceNotLoaded(LookupError):
    """A step needs a resource the caller did not pass to ``run``."""


@dataclass(frozen=True)
class ResRef:
    """A reference to a declared resource — ``res["db"]``, saved as ``{"$res": "db"}``.

    Like :class:`StepRef`, it is a name, never the object: the workflow stays
    portable and the live object is supplied at run. ``res["db"].lookup`` is
    the resource's bound tool ``lookup``, ready to decorate.
    """

    name: str

    def __getattr__(self, method: str) -> "BoundToolHandle":
        if method.startswith("_"):
            raise AttributeError(method)
        return BoundToolHandle(self, method)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"res[{self.name!r}]"


class _Res:
    """``res["db"]`` — the resource counterpart of ``wf["step"]``."""

    def __getitem__(self, name: str) -> ResRef:
        if not isinstance(name, str) or not name.isidentifier():
            raise KeyError(f"a resource name must be an identifier, got {name!r}")
        return ResRef(name)

    def __repr__(self) -> str:
        return "res"


#: ``res["db"]`` names a resource declared with ``wf.define("db", …)``.
res = _Res()


class BoundToolHandle:
    """``res["db"].lookup`` — a bound tool waiting for its brackets.

    The method is found on the resource's **declared type** once the step is in
    a workflow; until then its tool id is ``"?.lookup"``. Brackets and parens
    work exactly as on a :class:`ToolHandle`.
    """

    def __init__(self, ref: ResRef, method: str):
        self.ref, self.method = ref, method
        self.id = f"?.{method}"

    def _start(self) -> "Operation":
        return Operation(tool_id=self.id, bound_to=self.ref)

    def bind(self, **literals) -> "Operation":
        return self._start().bind(**literals)

    def __getitem__(self, modifiers: Any) -> "Operation":
        return self._start()[modifiers]

    def __call__(self, *args, **kwargs) -> Any:
        if args and isinstance(args[0], StepRef):
            return self._start()(*args, **kwargs)
        raise TypeError(
            f"res[{self.ref.name!r}].{self.method} has no instance until the "
            "workflow runs. Wire it into a step: "
            f"wf[...] = res[{self.ref.name!r}].{self.method}[mod.map()](wf[...])."
        )

    def __repr__(self) -> str:
        return f"<bound tool {self.ref!r}.{self.method}>"


#: The attribute ``@bound_tool`` sets on a method. The method is otherwise untouched.
_BOUND_MARK = "__simple_steps_bound_tool__"


def bound_tool(fn: Callable) -> Callable:
    """Mark a **method** of a resource class as a tool that runs on one instance.

    The method stays an ordinary method — ``FakeDB().lookup("SF")`` still works —
    and nothing is registered in :data:`TOOLS`. The mark only records that the
    type offers it, so ``res["db"].lookup[mod.map()](…)`` can use it and the
    catalog can list it. Unmarked methods are never tools, though tool code may
    still call them::

        class FakeDB:
            @bound_tool
            def lookup(self, key: str) -> str | None: ...

            def reset(self) -> None: ...      # not a tool
    """
    try:
        first = next(iter(inspect.signature(fn).parameters), None)
    except (TypeError, ValueError):
        first = None
    if first != "self":
        raise TypeError(
            f"@bound_tool marks a method (first parameter `self`); "
            f"{getattr(fn, '__qualname__', fn)!r} is not one. "
            "Use @tool for a free function."
        )
    reserved = _reserved_problem(getattr(fn, "__name__", ""), "bound tool")
    if reserved:
        raise ValueError(reserved)
    setattr(fn, _BOUND_MARK, True)
    return fn


def _looks_like_method(fn: Callable) -> bool:
    """A function defined in a class body whose first parameter is ``self``."""
    parts = getattr(fn, "__qualname__", "").split(".")
    if len(parts) < 2 or parts[-2] == "<locals>":
        return False
    try:
        return next(iter(inspect.signature(fn).parameters), None) == "self"
    except (TypeError, ValueError):
        return False


def _signature(fn: Callable) -> inspect.Signature:
    """The signature with string annotations (PEP 563) resolved where possible."""
    try:
        return inspect.signature(fn, eval_str=True)
    except Exception:
        return inspect.signature(fn)


#: Every resource type a workflow has declared or ``@resource`` registered, by name.
#: ``Workflow.from_dict`` resolves a saved ``"type"`` through it.
RESOURCE_TYPES: dict[str, type] = {}

_LITERAL_TYPES = (str, int, float, bool, type(None), list, dict, tuple)


def _literal_annotation(annotation: Any) -> bool:
    """Can a setting with this annotation hold only literals?"""
    if annotation is inspect.Parameter.empty or annotation is Any \
            or isinstance(annotation, str):
        return True                       # undeclared or unresolvable: allowed
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return all(_literal_annotation(a) for a in typing.get_args(annotation))
    if origin is typing.Literal:
        return True
    base = origin or annotation
    return isinstance(base, type) and issubclass(base, _LITERAL_TYPES)


def _settings(cls: type) -> list[inspect.Parameter]:
    """A resource type's settings: its constructor's named parameters."""
    try:
        parameters = list(_signature(cls.__init__).parameters.values())[1:]
    except (TypeError, ValueError):
        return []
    return [p for p in parameters
            if p.kind not in (inspect.Parameter.VAR_POSITIONAL,
                              inspect.Parameter.VAR_KEYWORD)]


def _bound_tools(cls: type) -> dict[str, Callable]:
    """The ``@bound_tool`` methods of *cls*, by name, base classes included.

    An unmarked override of a marked method is not a tool: the subclass chose
    to withdraw it.
    """
    found: dict[str, Callable] = {}
    for klass in reversed(cls.__mro__):
        for name, value in vars(klass).items():
            if callable(value) and getattr(value, _BOUND_MARK, False):
                found[name] = value
            elif name in found:
                del found[name]
    return found


_VIEWS: dict[tuple[type, str], Callable] = {}


def _method_view(cls: type, name: str) -> Callable:
    """The bound tool *name* of *cls*, as a function **without** ``self``.

    It carries the signature and docstring, which is everything ``check``,
    staging, verb inference and the catalog read. It cannot run — the real
    instance's method replaces it at run time.
    """
    key = (cls, name)
    if key not in _VIEWS:
        method = _bound_tools(cls)[name]
        signature = _signature(method)

        def view(*args, **kwargs):
            raise TypeError(f"{cls.__name__}.{name} is a bound tool; it runs on "
                            "a resource instance supplied to Workflow.run")
        view.__signature__ = signature.replace(
            parameters=list(signature.parameters.values())[1:])
        view.__name__ = name
        view.__qualname__ = f"{cls.__name__}.{name}"
        view.__doc__ = method.__doc__
        view.__module__ = getattr(method, "__module__", None)
        _VIEWS[key] = view
    return _VIEWS[key]


def resource_problems(cls: type) -> list[str]:
    """Why *cls* cannot be a resource type — empty when it can."""
    problems = []
    for parameter in _settings(cls):
        if not _literal_annotation(parameter.annotation):
            problems.append(
                f"setting {parameter.name!r} is {_type_name(parameter.annotation)}; "
                "a resource is built from literal settings only (str, number, "
                "bool, list, dict), so it can always be rebuilt from its declaration"
            )
    return problems


def resource(cls: type) -> type:
    """Register a class as a resource type, checking its settings are literals.

    Optional — ``wf.define`` registers a type the first time it is used — but
    declaring it puts the type and its bound tools in :func:`resource_catalog`
    at import, before any workflow exists.
    """
    problems = resource_problems(cls)
    reserved = _reserved_problem(cls.__name__, "resource type")
    if reserved:
        problems.append(reserved)
    if problems:
        raise TypeError(f"cannot declare resource type {cls.__name__!r}: "
                        + "; ".join(problems) + ".")
    existing = RESOURCE_TYPES.get(cls.__name__)
    if existing is not None and existing is not cls \
            and existing.__qualname__ != cls.__qualname__:
        warnings.warn(
            f"resource type {cls.__name__!r} is already declared and is being "
            "replaced — a workflow loaded from JSON resolves the name to "
            "whichever was declared last.", stacklevel=2)
    RESOURCE_TYPES[cls.__name__] = cls
    return cls


def resource_entry(cls: type) -> dict:
    """One resource type for a palette: its settings, bound tools and bases."""
    doc = (inspect.getdoc(cls) or "").strip()
    settings = []
    for parameter in _settings(cls):
        required = parameter.default is inspect.Parameter.empty
        settings.append({
            "name": parameter.name,
            "type": _type_name(parameter.annotation),
            "required": required,
            "default": None if required else parameter.default,
        })
    return {
        "type": cls.__name__,
        "description": doc.split("\n", 1)[0] if doc else "",
        "settings": settings,
        "tools": {f"{cls.__name__}.{name}":
                  tool_entry(f"{cls.__name__}.{name}", _method_view(cls, name), "bound")
                  for name in sorted(_bound_tools(cls))},
        #: Every type this one is, so a client can show which resources fit a
        #: parameter declared as a base (`llm: LLM`).
        "bases": [k.__name__ for k in cls.__mro__ if k is not object],
    }


def resource_catalog(types_: dict[str, type] | None = None) -> dict[str, dict]:
    """Every registered resource type, name → :func:`resource_entry`."""
    return {name: resource_entry(cls)
            for name, cls in sorted({**RESOURCE_TYPES, **(types_ or {})}.items())}


@dataclass
class ResourceDecl:
    """How a workflow declared a resource — what is saved, never the object."""

    name: str
    #: The class, or ``None`` when a loaded workflow names a type this process
    #: does not have. Declaring still works; type checks are skipped.
    type: type | None
    settings: dict
    type_name: str
    source: str = "defined"

    def to_dict(self) -> dict:
        return {"source": self.source, "type": self.type_name,
                "settings": dict(self.settings)}


def _type_fits(cls: type, annotation: Any) -> bool | None:
    """Does an instance of *cls* fit *annotation*? ``None`` when undecidable."""
    if annotation is inspect.Parameter.empty or isinstance(annotation, str):
        return None
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        answers = [_type_fits(cls, a) for a in typing.get_args(annotation)]
        if any(a is True for a in answers):
            return True
        return False if all(a is False for a in answers) else None
    base = origin or annotation
    if not isinstance(base, type) or base is object:
        return None
    return issubclass(cls, base)


def _attach_bound(operation: "Operation", resources: dict) -> "Operation":
    """Give a bound-tool Operation its type-qualified id and its method view.

    Left as is when the resource or the method cannot be found — :func:`check`
    then says which.
    """
    if operation.bound_to is None:
        return operation
    decl = resources.get(operation.bound_to.name)
    method = operation.tool_id.rsplit(".", 1)[-1]
    if decl is None or decl.type is None or method not in _bound_tools(decl.type):
        return replace(operation, fn=None)
    return replace(operation, tool_id=f"{decl.type.__name__}.{method}",
                   fn=_method_view(decl.type, method))


def _no_resource(name: str, workflow: "Workflow") -> str:
    declared = ", ".join(map(repr, workflow.resources)) or "none"
    return (f"no resource named {name!r} (declared: {declared}). "
            f"Declare it first: wf.define({name!r}, <Type>, ...)")


def _bound_problem(operation: "Operation", workflow: "Workflow | None") -> str:
    """Why a bound tool's method could not be found."""
    name = operation.bound_to.name
    method = operation.tool_id.rsplit(".", 1)[-1]
    if workflow is None:
        return (f"{method} is bound to resource {name!r}, which only a workflow "
                "can declare")
    decl = workflow.resources.get(name)
    if decl is None:
        return _no_resource(name, workflow)
    if decl.type is None:
        return (f"resource {name!r} has type {decl.type_name!r}, which is not "
                "available here — pass resource_types= when loading")
    tools = ", ".join(sorted(_bound_tools(decl.type))) or "(none)"
    return f"{method} is not a tool of {decl.type.__name__}; its tools are: {tools}"



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
            # Anything after the input binds by position (008 C1).
            return self._start()(*args, **kwargs)
        if any(isinstance(a, Operation) for a in (*args, *kwargs.values())):
            raise TypeError(_NESTED_OPERATION)
        return self.fn(*args, **kwargs)

    def bind(self, **literals) -> Operation:
        """Fix some arguments now, leaving the rest to arrive with each row.

        ``score.bind(threshold=5)[mod.map(over=rows)]`` — the literals become
        the Operation's ``arguments`` and are applied innermost, inside every
        modifier, so a retry re-runs the same call and a map passes them to
        every item. A value may be a :class:`StepRef`: a *value reference*
        (K10), kept as the ref and resolved to that step's value at run.
        """
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
        if _looks_like_method(f):
            # @tool on a method used to replace it with a handle that never
            # receives `self`, breaking the method and registering a global
            # tool `lookup(self, key)`. A method belongs to a resource.
            raise TypeError(
                f"{f.__qualname__} is a method. Mark it @bound_tool so it runs "
                "on a resource instance (res[\"name\"]." + f.__name__ + "); "
                "@tool is for free functions."
            )
        handle = ToolHandle(f, tool_id)
        reserved = _reserved_problem(handle.id, "tool")
        if reserved:
            raise ValueError(f"cannot declare tool {handle.id!r}: {reserved}")
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

    # 1. the tool has to exist — unless this is a combine verb, which names no
    #    tool (join/stack/zip apply none; their id is the verb itself). A bound
    #    tool comes from its resource's declared type, never from TOOLS.
    if operation.bound_to is not None:
        fn = operation.fn
        if fn is None:
            problems.append(_bound_problem(operation, workflow))
    else:
        fn = operation.fn or TOOLS.get(operation.tool_id) \
            or BUILTIN_TOOLS.get(operation.tool_id)
        if fn is None and not is_combine(operation):
            problems.append(f"unknown tool {operation.tool_id!r}")

    # 1b. every resource argument has to name a declared resource. Whether it
    #     is *loaded* is a run-time question: a workflow is portable, its
    #     resources are environment.
    if workflow is not None:
        for value in operation.arguments.values():
            if isinstance(value, ResRef) and value.name not in workflow.resources:
                problems.append(_no_resource(value.name, workflow))

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
            if isinstance(value, StepRef):
                # 008 C1: checked against the value once the step holds one;
                # until then the reference is resolved at run.
                known = workflow._value_if_known(value) if workflow else _UNKNOWN
                if known is _UNKNOWN:
                    continue
                if isinstance(known, expected) and (
                        bool in expected or not isinstance(known, bool)):
                    continue
                problems.append(
                    f"{modifier.kind}'s {parameter}= reads {value.id!r}, which "
                    f"holds {type(known).__name__}; it must be "
                    f"{' or '.join(t.__name__ for t in expected)}")
                continue
            if _is_tool_value(value) and parameter in TOOL_SETTINGS.get(modifier.kind, ()):
                continue                           # 008 C2: a tool in a setting
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

    # 2d. a verb whose literal setting is mandatory must carry it at
    #     declaration, not discover it missing at run. select/drop/sort/rename
    #     each raise from their verb without their one required setting; catch
    #     it here instead, like every other declaration check.
    for modifier in operation.modifiers:
        for required in _required_settings(modifier.kind):
            if not modifier.params.get(required) and modifier.params.get(required) != 0:
                problems.append(
                    f"{modifier.kind} needs {required}= — it has no default, "
                    f"so a step without it cannot run"
                )

    # 2d'. select chooses rows, columns or both — it needs at least one.
    for modifier in operation.modifiers:
        if modifier.kind == "select" and not modifier.params.get("columns") \
                and modifier.params.get("rows") is None:
            problems.append("select needs columns= or rows= — what to keep")

    # 2d''. mod.expect states something, and never what core knows is false
    #       (008 C9.4) — "filter gives at most 3 rows; expect(rows=10) can't hold".
    expect = _expectation(operation)
    if any(m.kind == "expect" for m in operation.modifiers):
        if not any(k in expect for k in ("rows", "min_rows", "max_rows", "columns")):
            problems.append("expect needs rows=, min_rows=, max_rows= or columns= "
                            "— what the step will produce")
        verb_ = operation.shape_verb
        index = workflow._known_index(operation) if workflow is not None else None
        n = None if index is None else len(index)
        rule = ROWS_RULE.get(verb_.kind) if verb_ is not None else None
        stated = expect.get("rows")
        if isinstance(stated, int) and verb_ is not None:
            if rule == "one" and not verb_.params.get("by") and stated != 1:
                problems.append(f"{verb_.kind} gives exactly 1 row; "
                                f"expect(rows={stated}) can't hold")
            elif n is not None and rule == "same" and stated != n:
                problems.append(f"{verb_.kind} gives exactly {n} rows; "
                                f"expect(rows={stated}) can't hold")
            elif n is not None and rule == "at_most" and stated > n:
                problems.append(f"{verb_.kind} gives at most {n} rows; "
                                f"expect(rows={stated}) can't hold")

    # 2e. a combine (join/stack/zip) reads several grids and merges on literal
    #     config; it has no tool, so its only extra declaration checks are its
    #     arity and, for a join, its key.
    if is_combine(operation):
        spec = COMBINE[operation.tool_id]
        if len(operation.grids) < spec["min_inputs"]:
            problems.append(
                f"{operation.tool_id} needs at least {spec['min_inputs']} grids "
                f"to combine, got {len(operation.grids)}"
            )
        if operation.tool_id == "join" and not operation.arguments.get("on"):
            problems.append("join needs on= — the key column(s) to merge on")

    # The references this operation reads: the grid input(s), plus any argument
    # bound to a step. All are validated the same way.
    references: list[tuple[str, Any]] = []
    grids = operation.grids
    for i, g in enumerate(grids):
        references.append(("input" if len(grids) <= 1 else f"input {i + 1}", g))
    references += [(f"argument {name!r}", value)
                   for name, value in operation.arguments.items()
                   if isinstance(value, StepRef)]
    references += [(f"{m.kind}'s {name}=", value)
                   for m in operation.modifiers
                   for name, value in m.params.items()
                   if isinstance(value, StepRef)]

    # 3. a reference has to have been read from *this* workflow. A step is
    #    named by its id, so a ref borrowed from another workflow would resolve
    #    against a same-named local step — silently running the wrong data when
    #    both happen to have one. A StepRef knows which workflow it came from.
    for label, ref in references:
        if workflow is None or not isinstance(ref, StepRef):
            continue
        if ref.workflow is None or ref.workflow is workflow:
            continue
        name = ref.id
        problems.append(
            f"{label} {name!r} reads a different Workflow. A step is named by "
            f"its id, so this would resolve to *this* workflow's {name!r} — not "
            f"the step you pointed at. Read it from this workflow."
        )

    # 4. a reference has to name an existing, valid, non-circular step
    for label, ref in references:
        if workflow is None:
            continue
        name = str(ref)
        if name == step_id:
            problems.append(f"{label} is itself ({name!r})")
        elif name not in workflow.steps:
            problems.append(f"{label} {name!r}, which is not an earlier step")
        elif not workflow.steps[name].valid:
            root, why = workflow.root_cause(name)
            problems.append(f"{label} {name!r}, which is invalid "
                            f"(root cause: {root}: {why})")
        elif step_id is not None and step_id in workflow._upstream_ids(name):
            problems.append(f"{label} {name!r} is circular")
        elif (step_id is not None and step_id in workflow.steps
              and list(workflow.steps).index(name) > list(workflow.steps).index(step_id)):
            # 008 C10: re-declaring a step keeps its position, so it could
            # quietly start reading a step defined after it.
            problems.append(f"{label} {name!r} comes after {step_id!r}; a step "
                            "can only read earlier steps")

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

    # 6. the column verbs apply no tool (source may: it can compute its grid)
    for kind in ("select", "drop", "widen", "slice", "rename",
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
            and (verb.params.get("columns") or verb.params.get("by"))
            and not any(isinstance(verb.params.get(k), StepRef)
                        or (verb.kind == "select" and isinstance(verb.params.get(k), dict))
                        or _is_tool_value(verb.params.get(k))
                        for k in ("columns", "by"))
            # 008 K1: while the input's columns are not known yet (a tool-backed
            # source that has not run, or anything downstream of one), a name
            # missing from the prediction may still arrive. Defer, don't fail;
            # the step is re-checked when its input runs.
            and not workflow._columns_open(operation)):
        available = workflow._known_columns(operation)
        by = verb.params.get("by")
        named = list(verb.params.get("columns") or
                     ([by] if isinstance(by, str) else by) or ())
        if available:
            missing = [c for c in named if c not in available]
            if missing:
                problems.append(
                    f"{verb.kind} names {', '.join(map(repr, missing))}, which "
                    f"the input does not have (it has {', '.join(map(str, available))})"
                )

    # 6c. a payload column must not silently replace an input column (008
    #     C13). Checked against the columns predicted *present*, which is sound
    #     even while the full set is still open. Only an explicit `name=` is
    #     refused: the default payload overwriting the previous step's default
    #     payload is how `map` over `map` chains, so that is a warning instead
    #     (see `warn`).
    if (verb is not None and verb.kind in ("map", "group", "expand")
            and workflow is not None and not verb.params.get("replace")
            and "name" in verb.params):
        written = verb.params["name"]
        upstream_name = str(operation.input) if operation.input is not None else "the input"
        if written in workflow._known_columns(operation):
            problems.append(
                f"{verb.kind} writes {written!r}, which {upstream_name} already "
                f"has; choose another name (name=…), or say replace=True")

    # 6e. a tool in a setting (008 C2): only where the verb takes one, and it
    #     must be registered, so the saved `{"$tool": id}` resolves on load.
    for modifier in operation.modifiers:
        for name, value in modifier.params.items():
            if not _is_tool_value(value) or isinstance(value, StepRef):
                continue
            if name not in TOOL_SETTINGS.get(modifier.kind, ()):
                problems.append(f"{modifier.kind}'s {name}= doesn't take a tool")
            elif isinstance(value, ToolRef) and value.id not in TOOLS \
                    and value.id not in BUILTIN_TOOLS:
                problems.append(f"{modifier.kind}'s {name}= names tool "
                                f"{value.id!r}, which is not registered")

    # 6c'. a reference argument arrives whole, shaped by the parameter's type
    #      (008 C1) — a shape that can't convert is refused here, not on every row.
    if fn is not None and workflow is not None:
        try:
            annotations = {k: p.annotation for k, p in _signature(fn).parameters.items()}
        except (TypeError, ValueError):
            annotations = {}
        for name, value in operation.arguments.items():
            if not isinstance(value, StepRef) or name not in annotations:
                continue
            # 008 C7: a selection's shape is known from how it is written; a
            # whole step's only once it holds data.
            kind = _selection_kind(value)
            step = workflow.steps.get(value.id)
            if kind is None and (step is None or step.output.meta.get("staged")):
                continue
            if kind is None:
                kind = _shape_kind(step.output.data)
            problem = _shape_problem(kind, annotations[name], name, value.id)
            if problem:
                problems.append(problem)

    # 6f. a selection is checked against what is already known about its step
    #     (008 C7.7, C7.11): a column name it lacks, a position past the end.
    if workflow is not None:
        selections = [(f"argument {n!r}", v) for n, v in operation.arguments.items()
                      if isinstance(v, StepRef) and v.selected]
        if verb is not None and verb.kind == "select" and operation.input is not None \
                and (isinstance(verb.params.get("columns"), dict)
                     or verb.params.get("rows") is not None):
            selections.append(("select", StepRef(
                str(operation.input), rows=verb.params.get("rows"),
                columns=verb.params.get("columns"))))
        for label, ref in selections:
            step = workflow.steps.get(ref.id)
            if step is None or not step.valid:
                continue                      # reported as a reference problem
            if step.output.meta.get("staged"):
                if columns_unknown(step.output) or ref.columns is None:
                    continue
                frame = pd.DataFrame(columns=predicted_columns(step.output))
                row_sel = None                # row count not known yet
            else:
                frame, row_sel = step.output.data, ref.rows
            try:
                _apply_selection(frame, row_sel, ref.columns, ref.id)
            except SelectionError as exc:
                problems.append(f"{label}: {exc}")

    # 6d. a bound value is a literal or a reference — anything else is refused
    #     here, not when the workflow is saved (008 C11).
    for name, value in operation.arguments.items():
        if isinstance(value, (StepRef, ResRef, ToolRef, ToolHandle)):
            continue
        problem = _literal_problem(value)
        if problem:
            problems.append(f"{name}: {problem}")
    for modifier in operation.modifiers:
        for name, value in modifier.params.items():
            if isinstance(value, (StepRef, ResRef, ToolRef, ToolHandle)) or callable(value):
                continue                   # tools in settings: C2's check
            problem = _literal_problem(value)
            if problem:
                problems.append(f"{modifier.kind}'s {name}=: {problem}")

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


def warn(operation: Operation, workflow: "Workflow | None" = None) -> tuple[str, ...]:
    """Non-blocking column expectations, before the upstream has run (005 C).

    The hard column check (:func:`_missing_columns`) only fires once the upstream
    is real, so a step declared ahead of its inputs says nothing. But staging
    already *predicts* the upstream's columns, so we can surface what a step
    **expects** without blocking it: a column predicted present is 🟡
    unconfirmed, one predicted absent is 🟠 likely-missing. Both clear (or harden
    into a problem) when the upstream runs. Warnings never stop a run.
    """
    if workflow is None or operation.input is None:
        return ()
    verb = operation.shape_verb
    if verb is None or verb.kind in ("source", "sweep"):
        return ()
    notes: list[str] = []
    # 008 C7: a row position reads a different row next run when the step it
    # reads doesn't fix its row order.
    for ref in [*operation.arguments.values(),
                *(StepRef(str(operation.input), rows=verb.params.get("rows"))
                  if verb.kind == "select" and verb.params.get("rows") is not None
                  else None,)]:
        if not isinstance(ref, StepRef) or ref.rows is None:
            continue
        read = workflow.steps.get(ref.id)
        made_by = read.operation.shape_verb.kind if read and read.operation.shape_verb else None
        if made_by in ("filter", "expand", "group", "distinct", "collapse"):
            notes.append(f"rows {ref.rows!r} of {ref.id!r} are positions, and "
                         f"{made_by} doesn't fix row order: they may be "
                         "different rows next run")
    # 008 N2: an argument bound on the step beats a same-named input column —
    # allowed, since pinning a value can be deliberate, but never silent.
    upstream_columns = workflow._known_columns(operation)
    for name, value in operation.arguments.items():
        if name in upstream_columns:
            shown = (f"wf[{value.id!r}]" if isinstance(value, StepRef)
                     else repr(value))
            notes.append(
                f"{name}={shown} overrides the {name!r} column of "
                f"{str(operation.input)!r} for every row; drop the argument "
                f"to use the column")
    if (verb.kind in ("map", "group", "expand") and "name" not in verb.params
            and not verb.params.get("replace")):
        written = DEFAULT_PAYLOAD.get(verb.kind)
        if written in workflow._known_columns(operation):
            # 008 C13, the default-name case: allowed, but said out loud.
            notes.append(
                f"{verb.kind} writes {written!r} over the {written!r} column "
                f"{str(operation.input)!r} already has; name the output "
                f"(name=…) to keep both, or say replace=True to silence this")
    upstream = workflow.steps.get(str(operation.input))
    # Only predict while the upstream is staged; once it runs, `check` is exact.
    if upstream is None or not upstream.output.meta.get("staged"):
        return tuple(notes)
    fn = operation.fn or TOOLS.get(operation.tool_id) \
        or BUILTIN_TOOLS.get(operation.tool_id)
    if isinstance(fn, ToolHandle):
        fn = fn.fn
    if fn is None:
        return tuple(notes)
    try:
        parameters = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return tuple(notes)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return tuple(notes)                       # takes the whole row; nothing to expect
    if verb.kind == "collapse":
        parameters = parameters[1:]     # the verb supplies the accumulator
    predicted = set(rows(upstream.output).columns) | set(operation.arguments)
    required = [p.name for p in parameters
                if p.default is inspect.Parameter.empty
                and p.kind is not inspect.Parameter.VAR_POSITIONAL]
    up = str(operation.input)
    shown = ", ".join(sorted(predicted)) or "no columns"
    warnings: list[str] = []
    absent = [r for r in required if r not in predicted]
    present = [r for r in required if r in predicted]
    if absent:
        warnings.append(
            f"expects {', '.join(map(repr, absent))} from {up!r}, which is "
            f"predicted to produce ({shown}) — likely missing once it runs"
        )
    if present:
        warnings.append(
            f"expects {', '.join(map(repr, present))} from {up!r}, "
            f"unconfirmed until it runs"
        )
    return tuple(notes + warnings)


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
    # A parameter typed as a resource is never a column — say how to bind it.
    hint = ""
    try:
        annotations = {k: p.annotation for k, p in _signature(fn).parameters.items()}
    except (TypeError, ValueError):
        annotations = {}
    for name in missing:
        kind = annotations.get(name)
        if isinstance(kind, type) and any(isinstance(t, type) and issubclass(t, kind)
                                          for t in RESOURCE_TYPES.values()):
            hint = (f". {name!r} is a resource ({kind.__name__}), not a column: "
                    f"bind it with {name}=res[\"<name>\"]")
            break
    return [
        f"{operation.tool_id}() needs {', '.join(repr(m) for m in missing)}, "
        f"which {str(operation.input) if operation.input is not None else 'the input'!r} does not have "
        f"(it has {', '.join(sorted(available)) or 'no columns'}){hint}"
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
        # Resolved, so `from __future__ import annotations` (a string
        # "FakeLLM") is checked like the real type rather than skipped.
        parameters = _signature(fn).parameters
    except (TypeError, ValueError):
        return []

    problems: list[str] = []
    for name, value in operation.arguments.items():
        parameter = parameters.get(name)
        if parameter is None or parameter.annotation is inspect.Parameter.empty:
            continue
        if isinstance(value, StepRef):
            continue                     # a value reference, resolved at run
        if isinstance(value, ResRef):
            # Checked against the *declared* type, so it works before anything
            # is loaded. A subclass fits its base.
            decl = workflow.resources.get(value.name) if workflow else None
            if decl is not None and decl.type is not None and \
                    _type_fits(decl.type, parameter.annotation) is False:
                problems.append(
                    f"{operation.tool_id}() declares {name}: "
                    f"{_type_name(parameter.annotation)}, but it is bound to "
                    f"resource {value.name!r} ({decl.type.__name__})"
                )
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
        # 008 C5: before the input runs, check against the types it declares
        # (a source's schema, mod.expect, or a tool's return annotation).
        declared_types = workflow._column_types(operation)
        params = list(parameters.values())
        if verb.kind == "collapse":
            params = params[1:]
        for parameter in params:
            if parameter.name in operation.arguments:
                continue
            column_type = declared_types.get(parameter.name)
            if column_type is None or parameter.annotation is inspect.Parameter.empty:
                continue
            if _declared_fits(column_type, parameter.annotation) is False:
                problems.append(
                    f"{operation.tool_id}() declares {parameter.name}: "
                    f"{_type_name(parameter.annotation)}, but "
                    f"{str(operation.input)!r} will have {parameter.name} as "
                    f"{_type_label(column_type)}")
        return problems

    frame = rows(upstream)
    # Only rows that completed count: a failed cell is a failure, not a
    # missing value, and its row is blocked downstream anyway (008 C10).
    completed = upstream.ledger.index[upstream.ledger["status"] == "completed"] \
        if len(upstream.ledger) else frame.index
    declared = list(parameters.values())
    if verb.kind == "collapse":
        declared = declared[1:]          # the verb supplies the accumulator
    upstream_name = (str(operation.input) if operation.input is not None
                     else "the input")
    for parameter in declared:
        if parameter.name in operation.arguments:
            continue                     # a literal, checked above
        if parameter.name not in frame.columns:
            continue                     # missing columns are rule 7's job
        if parameter.annotation is inspect.Parameter.empty:
            continue
        admits_none, base = _optional_parts(parameter.annotation)
        series = frame[parameter.name]
        try:
            has_none = bool(series.loc[series.index.intersection(completed)].isna().any())
        except (TypeError, ValueError):
            has_none = False
        if has_none and not admits_none:
            # 008 C14: said in terms of None, not of the float64 that NaN
            # used to force.
            problems.append(
                f"{upstream_name}.{parameter.name} can be None, but "
                f"{operation.tool_id}() takes {parameter.name}: "
                f"{_type_name(parameter.annotation)}; accept "
                f"{_type_name(parameter.annotation)} | None, or filter the "
                "Nones first")
            continue
        if _column_fits(series, base) is False:
            problems.append(
                f"{operation.tool_id}() declares {parameter.name}: "
                f"{_type_name(parameter.annotation)}, but "
                f"{str(operation.input) if operation.input is not None else 'the input'!r} has "
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


def columns_unknown(output: Output) -> bool:
    """True while an output's columns may include more than :func:`predicted_columns`.

    Only a staged output can be open: once a step has run, its columns are
    exactly its data's. 008 K1 — an unknown set is never treated as empty.
    """
    return bool(output.meta.get("staged") and output.meta.get("columns_open"))


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


#: First-parameter names that mark a two-argument tool as a reducer by
#: signature alone (008 K2). Matches the builtin reducers' `acc`.
_ACCUMULATOR_NAMES = frozenset({"acc", "accumulator", "memo", "carry"})


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

    # 008 K2: decide from the signature first, so the verb never depends on
    # whether the input has run. A first parameter named like an accumulator
    # is a reducer, whatever the columns are.
    if len(needed) >= 2 and needed[0] in _ACCUMULATOR_NAMES:
        return "collapse", (f"{needed[0]!r} names an accumulator, so this reads "
                            "as a reducer")

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


# ─────────────────────────────────────────────────────────────────────────
# Combine verbs — join / stack / zip, operations in their own right (005 B)
# ─────────────────────────────────────────────────────────────────────────
# A combine reads more than one grid and applies no tool, so it is not a
# modifier: it is built by a constructor (`join(a, b, on=...)`) and stored as
# its own tool_id with the grids in `Operation.inputs`. The config is literal;
# the grids are references in `inputs`, never in modifiers.

def _combine_stack(frames: list[pd.DataFrame], config: dict) -> pd.DataFrame:
    return pd.concat(frames, axis=0, join=config.get("join", "outer"),
                     ignore_index=True)


def _combine_zip(frames: list[pd.DataFrame], config: dict) -> pd.DataFrame:
    sizes = [len(f) for f in frames]
    if len(set(sizes)) > 1:
        raise ValueError(f"zip needs grids of equal length, got {sizes}")
    data = pd.concat([f.reset_index(drop=True) for f in frames], axis=1)
    # A shared column name would appear twice; keep the first (union, first
    # wins) so the result matches the staged prediction.
    return data.loc[:, ~data.columns.duplicated()]


def _combine_join(frames: list[pd.DataFrame], config: dict) -> pd.DataFrame:
    left, right = frames
    suffixes = tuple(config.get("suffixes") or ("_left", "_right"))
    return pd.merge(left, right, on=config.get("on"),
                    how=config.get("how", "inner"),
                    suffixes=suffixes).reset_index(drop=True)


#: Each combine verb: how it folds row counts (for staging), the minimum grids
#: it reads, and the function that performs it. Keyed by the tool_id a combine
#: Operation carries.
COMBINE: dict[str, dict] = {
    "stack": {"rows": "sum", "min_inputs": 1, "apply": _combine_stack},
    "zip":   {"rows": "same", "min_inputs": 2, "apply": _combine_zip},
    "join":  {"rows": "unknown", "min_inputs": 2, "apply": _combine_join},
}


def is_combine(operation: Operation) -> bool:
    """True for a ``join``/``stack``/``zip`` — a multi-grid operation."""
    return operation.tool_id in COMBINE


def _combine_op(kind: str, grids: tuple, config: dict) -> Operation:
    refs = tuple(g if isinstance(g, StepRef) else StepRef(str(g)) for g in grids)
    return Operation(tool_id=kind, arguments=config,
                     input=refs[0] if refs else None, inputs=refs)


def stack(*grids: Any, join: str = "outer") -> Operation:
    """Append the rows of several grids — a vertical concat. The row count is the
    **sum**; columns are the union (``join="inner"`` keeps only shared ones)."""
    return _combine_op("stack", grids, {"join": join})


def zip_(*grids: Any) -> Operation:
    """Join grids **by position**, row *i* with row *i* — a horizontal concat.
    Refuses grids of unequal length. Named ``zip_`` so it does not shadow the
    builtin ``zip``."""
    return _combine_op("zip", grids, {})


def join(left: Any, right: Any, *, on: Any = None, how: str = "inner",
         suffixes: Any = ("_left", "_right")) -> Operation:
    """Merge two grids on a shared key, like ``pd.merge``. The row count is
    **unknown** until it runs (1:1, 1:many, many:many); columns are the union,
    with ``suffixes`` applied to any non-key collision."""
    return _combine_op("join", (left, right),
                       {"on": on, "how": how, "suffixes": list(suffixes)})


def _combine_columns(operation: Operation, schemas: list[list[str]]) -> list[str]:
    """Predicted output columns of a combine, folded from its inputs' schemas."""
    if operation.tool_id == "join":
        on = operation.arguments.get("on")
        keys = [on] if isinstance(on, str) else list(on or [])
        suffixes = operation.arguments.get("suffixes") or ["_left", "_right"]
        left, right = schemas
        out = list(left)
        for c in right:
            if c in keys:
                continue
            if c in left:                       # collision — pandas suffixes both
                if c in out:
                    out[out.index(c)] = f"{c}{suffixes[0]}"
                out.append(f"{c}{suffixes[1]}")
            else:
                out.append(c)
        return out
    out: list[str] = []                         # stack / zip: union, first wins
    for schema in schemas:
        for c in schema:
            if c not in out:
                out.append(c)
    return out


def _stage_combine(operation: Operation, workflow: "Workflow | None") -> Output:
    """Stage a combine from its inputs' predicted schemas and row counts."""
    spec = COMBINE[operation.tool_id]
    steps = ([] if workflow is None
             else [workflow.steps.get(str(g)) for g in operation.inputs])
    schemas: list[list[str]] = []
    counts: list[Any] = []
    for st in steps:
        if st is None:
            schemas.append([]); counts.append(None); continue
        schemas.append(predicted_columns(st.output))
        counts.append(st.output.meta.get("expected")
                      if st.output.meta.get("staged") else len(st.output.data))
    columns = _combine_columns(operation, schemas)
    columns_open = any(st is None or columns_unknown(st.output) for st in steps)
    rule, expected = spec["rows"], None
    known = bool(counts) and all(c is not None for c in counts)
    if rule == "sum" and known:
        expected = sum(counts)
    elif rule == "same" and known and len(set(counts)) == 1:
        expected = counts[0]
    index = list(range(expected)) if expected is not None else []
    records = [{"status": "staged", "error": None, "attempts": 0, "seconds": 0.0}
               for _ in index]
    return Output(
        data=pd.DataFrame({c: [None] * len(index) for c in columns or [PAYLOAD]},
                          index=index),
        ledger=_ledger(records, index),
        meta={"verb": operation.tool_id, "form": "column", "payload": None,
              "staged": True, "problems": (), "n_in": None, "expected": expected,
              "rows_rule": rule, "columns": columns, "columns_open": columns_open},
    )


def _run_combine(operation: Operation, frames: list[pd.DataFrame]) -> Output:
    """Apply a combine to its (already-run) input grids — no tool, so every
    output row is trivially complete."""
    data = COMBINE[operation.tool_id]["apply"](frames, operation.arguments)
    records = [{"status": "completed", "error": None, "attempts": 0,
                "seconds": 0.0} for _ in range(len(data))]
    return Output(data=data, ledger=_ledger(records, data.index),
                  meta={"verb": operation.tool_id, "form": "column",
                        "payload": None, "n_in": None,
                        "columns": list(data.columns)})


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
    if problems:
        kind = operation.shape_verb.kind if operation.shape_verb else None
        return Output(
            data=pd.DataFrame({PAYLOAD: [None]}, index=[0]),
            ledger=_ledger([{"status": "invalid", "error": problems[0],
                             "attempts": 0, "seconds": 0.0}], [0]),
            meta={"verb": kind, "form": "scalar", "payload": PAYLOAD,
                  "staged": True, "problems": problems, "n_in": None,
                  "expected": None, "rows_rule": None, "columns": [PAYLOAD]},
        )
    if is_combine(operation):
        return _stage_combine(operation, workflow)
    verb = operation.shape_verb
    kind = verb.kind if verb else None
    # 008 C1/C2: a setting that reads a step, or is a tool, has no value until
    # run. Stage as though it were absent, and say the columns are not known.
    unsettled = verb is not None and any(
        isinstance(v, StepRef) or _is_tool_value(v) for v in verb.params.values())
    if unsettled:
        verb = Modifier(verb.kind, {k: v for k, v in verb.params.items()
                                    if not isinstance(v, StepRef) and not _is_tool_value(v)})

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
        chosen = verb.params.get("columns")
        if isinstance(chosen, dict) or chosen is None:
            try:
                ordered = _resolve_columns(list(upstream_columns), chosen, "the input")
            except SelectionError:
                ordered = []
        else:
            ordered = list(chosen)
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

    # 008 K1: are these all the columns, or only the ones known so far? A
    # source computed by a tool cannot know its columns before it runs, and a
    # verb that carries its input's columns through inherits that.
    if unsettled and kind in ("select", "drop", "rename", "widen"):
        columns_open = True
    elif kind == "select" and not isinstance(verb.params.get("columns"), (list, tuple)):
        # a range or position selection over columns not known yet
        columns_open = workflow._columns_open(operation) if workflow is not None else False
    elif kind == "source":
        fn = operation.fn or TOOLS.get(operation.tool_id) \
            or BUILTIN_TOOLS.get(operation.tool_id)
        columns_open = not is_identity(fn)
    elif kind in ("sweep", "select") or (kind == "collapse"):
        columns_open = False
    else:
        columns_open = (workflow._columns_open(operation)
                        if workflow is not None else False)

    # 008 C5/C9: what a step will produce, as far as is known — and how sure.
    # Column types come from the input (carried), the tool's return (payload),
    # a source's declared schema, or `mod.expect`.
    fn = operation.fn or TOOLS.get(operation.tool_id) or BUILTIN_TOOLS.get(operation.tool_id)
    label = operation.tool_id
    upstream_types = workflow._column_types(operation) if workflow is not None else {}
    types: dict = {c: upstream_types.get(c) for c in ordered}
    if kind == "rename":
        mapping = verb.params.get("columns") or {}
        if isinstance(mapping, dict):
            for old, new in mapping.items():
                types[new] = upstream_types.get(old)
    if payload and kind not in ("source",):
        types[payload] = _payload_type(kind, fn)
    if kind == "source" and not is_identity(fn):
        schema = _declared_schema(fn)
        if schema is not None:
            ordered, types, columns_open = list(schema), dict(schema), False
    expect = _expectation(operation)
    if expect.get("columns") is not None:
        names, stated_types = _expected_columns(expect)
        known = [c for c in ordered if c not in names] if kind != "source" else []
        ordered = list(dict.fromkeys(names + known))
        types = {c: stated_types.get(c, types.get(c)) for c in ordered}
        columns_open = bool(expect.get("more_columns"))
    if isinstance(expect.get("rows"), int) and expected is None:
        index, expected = list(range(expect["rows"])), expect["rows"]
    upstream_name = str(operation.input) if operation.input is not None else None
    plan = {
        "rows": _rows_plan(kind, rule, expected if "rows" not in expect else None,
                           n_in, expect, label),
        "columns": _columns_plan(kind, ordered, columns_open, expect, label, upstream_name),
        "types": {c: _type_label(types.get(c)) for c in ordered},
    }

    records = [{"status": "staged", "error": None, "attempts": 0, "seconds": 0.0}
               for _ in index]
    index_names = ordered
    return Output(
        data=pd.DataFrame({c: pd.Series([None] * len(index), index=index, dtype=object)
                           for c in index_names or [PAYLOAD]}, index=index),
        ledger=_ledger(records, index),
        meta={"verb": kind, "form": "scalar" if kind is None else "column",
              "payload": payload, "staged": True, "problems": (),
              "n_in": n_in, "expected": expected, "rows_rule": rule,
              "columns": ordered, "columns_open": columns_open,
              "plan": plan, "column_types": types},
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
    #: Non-blocking column expectations (005 C) — what this step predicts it
    #: will need from an upstream that has not run yet. Never stops a run.
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.problems

    @property
    def status(self) -> str:
        """A rollup of the ledger — a step is only as done as its rows."""
        states = set(self.output.ledger["status"])
        if "invalid" in states:
            return "invalid"
        # Ran, but an upstream changed (or re-ran) since: the data — failed
        # cells included — is outdated until it is re-run (008 C10.5: fixing a
        # root makes what it blocked stale). Nothing recomputes on its own.
        if self.output.meta.get("stale"):
            return "stale"
        for state in ("failed", "running", "staged"):
            if state in states:
                return state
        if states:
            return "completed"
        # No ledger rows at all is ambiguous, and the ledger cannot settle it:
        # either this step is staged and its addresses are not yet knowable, or
        # it ran and legitimately produced nothing (every unit filtered out, or
        # expanded to zero rows). `meta["staged"]` is what distinguishes them.
        return "staged" if self.output.meta.get("staged") else "completed"

    @property
    def plan(self) -> dict:
        """What this step will produce — rows, columns, types — and how sure (008 C9).

        Each axis has a ``certainty``: ``exact`` (core derived it), ``stated``
        (``mod.expect``), ``bounded`` (a range, or these columns plus more) or
        ``unknown``. Anything short of exact says ``because`` and how to
        ``resolve`` it. A step that has run is exact on every axis.
        """
        if not self.output.meta.get("staged"):
            data = self.output.data
            return {"rows": {"certainty": "exact", "count": len(data)},
                    "columns": {"certainty": "exact", "names": list(data.columns)},
                    "types": {c: _type_label(_dtype_type(data[c])) for c in data.columns}}
        return self.output.meta.get("plan") or {}

    def describe(self) -> str:
        """What this step is, in words.

        Two different questions, and they must not be blurred: a **staged**
        step reports what staging can *promise* (§7's three levels), while a
        step that has run reports what it actually *holds*. Only the first is a
        prediction.
        """
        if not self.valid:
            return f"invalid · {self.problems[0]}"
        if is_combine(self.operation):
            kind = self.operation.tool_id
            if not self.output.meta.get("staged"):
                n = len(self.output.data)
                return f"{kind} · {n} cell{'' if n == 1 else 's'}"
            expected = self.output.meta.get("expected")
            if expected is not None:
                return f"{kind} · {expected} cells"
            return f"{kind} · unknown count from {len(self.operation.inputs)} grids"
        verb = self.output.meta.get("verb")
        tool = self.operation.tool_id
        if verb == "source" and self.output.meta.get("staged"):
            return f"source {tool} · {_plan_words(self.plan)}"
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
        #: Declared resources, by name — the declarations, never the objects.
        self.resources: dict[str, ResourceDecl] = {}

    # ── resources ────────────────────────────────────────────────────────
    def define(self, name: str, type_: type, /, **settings: Any) -> ResRef:
        """Declare resource *name*: an instance of *type_* built from *settings*.

        ``wf.define("llm", FakeLLM, model="fake-1")``. Nothing is built here — the
        caller owns the live object and passes it to :meth:`run`. What is
        recorded is enough to check every step that uses it and to save it.
        Settings must be literals the constructor accepts. Redefining a
        resource re-checks the steps that use it and marks the ones that ran
        ``stale``. Returns ``res[name]``.
        """
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError(f"a resource name must be an identifier, got {name!r}")
        if not isinstance(type_, type):
            raise TypeError(f"define({name!r}, …) needs a class, got {type_!r}")
        problems = resource_problems(type_)
        accepted = {p.name: p for p in _settings(type_)}
        for key, value in settings.items():
            if key not in accepted:
                problems.append(
                    f"{type_.__name__} has no setting {key!r}; its settings are: "
                    f"{', '.join(accepted) or '(none)'}")
            elif not _json_safe(value):
                problems.append(
                    f"setting {key!r} must be a literal (str, number, bool, list, "
                    f"dict), got {type(value).__name__}")
            elif _value_fits(value, accepted[key].annotation) is False:
                problems.append(
                    f"setting {key!r} is declared "
                    f"{_type_name(accepted[key].annotation)}, got {value!r}")
        missing = [k for k, p in accepted.items()
                   if p.default is inspect.Parameter.empty and k not in settings]
        if missing:
            problems.append(f"{type_.__name__} needs {', '.join(map(repr, missing))}")
        if problems:
            raise TypeError(f"cannot define resource {name!r}: "
                            + "; ".join(problems) + ".")
        resource(type_)
        existed = name in self.resources
        self.resources[name] = ResourceDecl(name, type_, dict(settings),
                                            type_.__name__)
        self._recheck_users(name, stale=existed)
        return ResRef(name)

    def _recheck_users(self, name: str, *, stale: bool) -> None:
        """Re-check every step that uses resource *name* after it (re)declared."""
        for sid, st in self.steps.items():
            if name not in st.operation.resources:
                continue
            operation = _attach_bound(st.operation, self.resources)
            problems = check(operation, self, sid)
            ran = not st.output.meta.get("staged")
            st.operation = operation
            if problems != st.problems or not ran:
                st.problems = problems
                st.output = stage(operation, self, problems)
                st.warnings = warn(operation, self)
                self._restage_after(sid)
            elif stale:
                # Same as a changed `$ref` upstream: the data is now outdated.
                st.output.meta["stale"] = True
                self._mark_stale_dependents(sid)

    def _live(self, name: str, resources: Mapping[str, Any] | None) -> Any:
        """The caller's object for resource *name*, checked against its declaration."""
        if resources is None or name not in resources:
            decl = self.resources.get(name)
            kind = decl.type_name if decl else "object"
            raise ResourceNotLoaded(
                f"resource {name!r} is not loaded. Pass it to run: "
                f"wf.run(..., resources={{{name!r}: <{kind}>}})")
        live = resources[name]
        decl = self.resources.get(name)
        if decl is not None and decl.type is not None \
                and not isinstance(live, decl.type):
            raise TypeError(
                f"resource {name!r} is declared {decl.type.__name__}, but the "
                f"object passed for it is {type(live).__name__}")
        return live

    # ── declaring ────────────────────────────────────────────────────────
    def __setitem__(self, step_id: str, operation: Any) -> None:
        _check_caller_scope()
        existed = step_id in self.steps
        if isinstance(operation, StepRef):
            # 008 C7 (K9): `wf["block"] = wf["p"][1:5][cols["a":"c"]]` is a
            # select step — visible, saved and re-runnable. A plain reference
            # copies the step.
            selection = {}
            if operation.rows is not None:
                selection["rows"] = operation.rows
            columns = operation.columns
            if columns is not None:
                selection["columns"] = (columns["names"] if set(columns) == {"names"}
                                        else columns)
            if not selection:
                selection["columns"] = {"positions": {"start": None, "stop": None}}
            operation = Operation(tool_id="identity", fn=identity)[
                mod.select(**selection)](replace(operation, rows=None, columns=None))
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
            if existed:
                self._mark_stale_dependents(step_id)
            else:
                self._recheck_readers(step_id)
            return
        operation = _attach_bound(operation, self.resources)
        problems = check(operation, self, step_id)
        self.steps[step_id] = Step(
            step_id, operation, stage(operation, self, problems), problems,
            warn(operation, self),
        )
        if existed:
            self._mark_stale_dependents(step_id)
        else:
            self._recheck_readers(step_id)

    def _recheck_readers(self, step_id: str) -> None:
        """Re-check earlier steps that named *step_id* before it existed.

        008 C10: their "not an earlier step" becomes "comes after", which says
        what to fix — reorder, don't create.
        """
        for sid, st in self.steps.items():
            if sid == step_id or step_id not in st.operation.reads:
                continue
            problems = check(st.operation, self, sid)
            if problems != st.problems:
                st.problems = problems
                st.output = stage(st.operation, self, problems)
                st.warnings = warn(st.operation, self)

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
        # 008 C10: an unknown name is a reference that does not resolve — the
        # step that reads it declares with a problem ("not an earlier step")
        # instead of the line raising, so a workflow with a deleted step can
        # still be declared, loaded and shown.
        return StepRef(step_id, self)

    def __contains__(self, step_id: str) -> bool:
        return step_id in self.steps

    def step(self, step_id: str) -> Step:
        """The Step itself, rather than a reference to it."""
        return self.steps[step_id]

    # ── editing: delete, rename, and staleness ───────────────────────
    def _dependents(self, step_id: str) -> list[str]:
        """Steps that read *step_id* — as input or as a reference argument."""
        return [sid for sid, st in self.steps.items()
                if step_id in st.operation.reads]

    def __delitem__(self, step_id: str) -> None:
        self.remove(step_id)

    def remove(self, step_id: str) -> None:
        """Delete a step, refusing when later steps still read it.

        The error names the readers so an editor can show exactly what breaks;
        remove or rename them first.
        """
        if step_id not in self.steps:
            raise KeyError(f"no step {step_id!r}; have {list(self.steps)}")
        readers = self._dependents(step_id)
        if readers:
            raise ValueError(
                f"cannot remove {step_id!r}: {', '.join(map(repr, readers))} "
                f"read it. Remove or rename {'it' if len(readers) == 1 else 'them'} "
                "first."
            )
        del self.steps[step_id]

    def rename(self, old: str, new: str) -> None:
        """Rename a step, rewriting every ``over=`` that pointed at it.

        Outputs are kept — a rename is not a recompute — and insertion order is
        preserved so positions do not shift.
        """
        if old not in self.steps:
            raise KeyError(f"no step {old!r}; have {list(self.steps)}")
        if not isinstance(new, str) or not new:
            raise ValueError("a step id must be a non-empty string")
        if new == old:
            return
        if new in self.steps:
            raise ValueError(f"step {new!r} already exists")
        self.steps = {(new if sid == old else sid): st
                      for sid, st in self.steps.items()}
        self.steps[new].step_id = new
        for st in self.steps.values():
            op = st.operation
            changed = False
            new_input = op.input
            if op.input is not None and str(op.input) == old:
                new_input, changed = StepRef(new, self), True
            new_args = {}
            for key, value in op.arguments.items():
                if isinstance(value, StepRef) and str(value) == old:
                    new_args[key], changed = replace(value, id=new, workflow=self), True
                else:
                    new_args[key] = value
            new_mods = []
            for m in op.modifiers:
                params = {}
                for key, value in m.params.items():
                    if isinstance(value, StepRef) and str(value) == old:
                        params[key], changed = replace(value, id=new, workflow=self), True
                    else:
                        params[key] = value
                new_mods.append(Modifier(m.kind, params))
            if changed:
                st.operation = Operation(op.tool_id, tuple(new_mods), new_args,
                                         op.fn, new_input, bound_to=op.bound_to)

    def _mark_stale_dependents(self, step_id: str) -> None:
        """Mark every transitive reader that has already run as ``stale``.

        Changing an upstream recomputes nothing (§7's push/pull), but a dependent
        that ran now holds outdated data — ``status`` says ``stale`` until it is
        re-run. Staged dependents are left alone: they have no data to be stale.
        """
        frontier, seen = [step_id], set()
        while frontier:
            for sid in self._dependents(frontier.pop()):
                if sid in seen:
                    continue
                seen.add(sid)
                output = self.steps[sid].output
                if not output.meta.get("staged"):
                    output.meta["stale"] = True
                frontier.append(sid)

    # ── what a step reads ────────────────────────────────────────────────
    def _known_columns(self, operation: Operation) -> list[str]:
        """The columns this operation's input will have, in order, as far as known."""
        if operation.input is None:
            return []
        step = self.steps.get(str(operation.input))
        return [] if step is None else predicted_columns(step.output)

    def _columns_open(self, operation: Operation) -> bool:
        """Might this operation's input have columns not predicted yet? (008 K1)"""
        if operation.input is None:
            return False
        step = self.steps.get(str(operation.input))
        return step is not None and columns_unknown(step.output)

    def _column_types(self, operation: Operation) -> dict:
        """Column → Python type of this operation's input, as far as known."""
        if operation.input is None:
            return {}
        step = self.steps.get(str(operation.input))
        if step is None:
            return {}
        if not step.output.meta.get("staged"):
            return {c: _dtype_type(step.output.data[c]) for c in step.output.data.columns}
        return dict(step.output.meta.get("column_types") or {})

    def _known_index(self, operation: Operation) -> Sequence[Any] | None:
        """The input's index, when known — enough to stage, short of running.

        A staged step already carries an index when its own input was known, so
        cardinality propagates down the chain before anything has executed.
        That is §7's level 2/3 without a run.
        """
        if operation.input is None:
            return None
        step = self.steps.get(str(operation.input))
        if step is None or not step.valid:
            return None
        index = step.output.data.index
        return index if len(index) or not step.output.meta.get("staged") else None

    def _input_for(self, operation: Operation) -> Any | None:
        """The upstream Output this operation reads, once that step has run."""
        if operation.input is None:
            return None
        step = self.steps.get(str(operation.input))
        if step is None or step.output.meta.get("staged"):
            return None
        # So a failure downstream can name the cell it came from (`a[1]`).
        step.output.meta["step_id"] = step.step_id
        return step.output

    def _value_if_known(self, ref: StepRef) -> Any:
        """The value a reference will resolve to, if its step holds data now."""
        step = self.steps.get(ref.id)
        if step is None or step.output.meta.get("staged"):
            return _UNKNOWN
        return _ref_value(step.output.data, None, ref.id)

    def root_cause(self, step_id: str) -> tuple[str, str] | None:
        """Where an invalid step's problem starts: ``(step_id, problem)``.

        008 C10: following invalid upstreams to the first step that is invalid
        for its own reason, so the UI can jump there. ``None`` for a valid step.
        """
        seen: set[str] = set()
        current = step_id
        while current not in seen:
            seen.add(current)
            step = self.steps.get(current)
            if step is None or step.valid:
                return None if current == step_id else (current, "")
            upstream = next((r for r in step.operation.reads
                             if r in self.steps and not self.steps[r].valid), None)
            if upstream is None:
                return current, step.problems[0]
            current = upstream
        return current, self.steps[current].problems[0]

    def _failed_argument(self, operation: Operation) -> tuple[str, str] | None:
        """An argument that reads a step with a failed cell: (error, root cause).

        008 C10: an argument is passed whole, so one failed cell in it fails
        every row that would receive it — without calling the tool.
        """
        for name, value in operation.arguments.items():
            if not isinstance(value, StepRef):
                continue
            step = self.steps.get(str(value))
            if step is None or step.output.meta.get("staged"):
                continue
            ledger = step.output.ledger
            failed = ledger[ledger["status"] == "failed"] if len(ledger) else ledger
            if len(failed):
                index = failed.index[0]
                cause = failed.iloc[0].get("cause")
                return (f"argument {name!r} reads {step.step_id}, which has a failed "
                        f"cell {step.step_id}[{index}]",
                        cause if isinstance(cause, str) and cause
                        else f"{step.step_id}[{index}]: {failed.iloc[0]['error']}")
        return None

    # ── running ──────────────────────────────────────────────────────────
    def pending(self, step_id: str) -> list[str]:
        """The steps *step_id* reads that have not run yet, nearest first."""
        waiting: list[str] = []
        for name in self.steps[step_id].operation.reads:
            upstream = self.steps.get(name)
            if upstream is not None and upstream.output.meta.get("staged"):
                waiting.extend(self.pending(name))
                waiting.append(name)
        return waiting

    def _resolve_arguments(self, operation: Operation,
                           resources: Mapping[str, Any] | None = None) -> Operation:
        """Replace each reference argument with its value, and each resource with its object.

        A ``$ref`` to a one-cell step gives the cell; anything else gives the
        whole grid. A ``$res`` gives the caller's live object, and a bound tool
        gets that instance's method. A missing resource raises
        :class:`ResourceNotLoaded` before anything runs. A plain Operation is
        returned unchanged.
        """
        settings_refs = any(isinstance(v, StepRef)
                            for m in operation.modifiers for v in m.params.values())
        if operation.bound_to is None and not settings_refs and not any(
                isinstance(v, (StepRef, ResRef)) for v in operation.arguments.values()):
            return operation
        fn_for_types = operation.fn or TOOLS.get(operation.tool_id) \
            or BUILTIN_TOOLS.get(operation.tool_id)
        try:
            annotations = {k: p.annotation
                           for k, p in _signature(fn_for_types).parameters.items()}
        except (TypeError, ValueError):
            annotations = {}
        resolved = {}
        for name, value in operation.arguments.items():
            if isinstance(value, StepRef):
                data = _apply_selection(self.steps[str(value)].output.data,
                                        value.rows, value.columns, value.id)
                # 008 C1: the parameter's type decides the shape that arrives.
                try:
                    resolved[name] = _ref_value(data, annotations.get(name), value.id)
                except TypeError as exc:
                    raise SelectionError(str(exc)) from None
            elif isinstance(value, ResRef):
                resolved[name] = self._live(value.name, resources)
            else:
                resolved[name] = value
        fn = operation.fn
        if operation.bound_to is not None:
            instance = self._live(operation.bound_to.name, resources)
            fn = getattr(instance, operation.tool_id.rsplit(".", 1)[-1])
        modifiers = tuple(
            Modifier(m.kind, {k: (_ref_value(_apply_selection(
                                      self.steps[v.id].output.data, v.rows,
                                      v.columns, v.id), None, v.id)
                                  if isinstance(v, StepRef) else v)
                              for k, v in m.params.items()})
            for m in operation.modifiers)
        return Operation(operation.tool_id, modifiers, resolved,
                         fn, operation.input)

    def run(self, step_id: str, tools: dict[str, Callable] | None = None,
            resources: Mapping[str, Any] | None = None) -> Step:
        """Execute one step and replace its staged Output with the real one.

        *resources* is the caller's live objects, name → object, for every
        ``res["…"]`` the step uses. A step that needs one that is missing
        raises :class:`ResourceNotLoaded` and does not run.

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
            tool = (step.operation.fn or TOOLS.get(step.operation.tool_id)
                    or BUILTIN_TOOLS.get(step.operation.tool_id))
            if not is_identity(tool):
                # A tool source computes its grid from a no-input tool.
                step.output = self._resolve_arguments(
                    step.operation, resources).run(None, tools)
                mismatch = _output_mismatch(step.operation, step.output.data)
                if mismatch:
                    step.output = _failed_output(step.operation, mismatch)
                self._restage_after(step_id)
                return step
            # A literal source holds its data, so running one is a no-op — unless
            # it was reloaded without payloads and has nothing to hold.
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
        if is_combine(step.operation):
            frames = [rows(self.steps[str(g)].output)
                      for g in step.operation.inputs]
            step.output = _run_combine(step.operation, frames)
            self._restage_after(step_id)
            return step
        try:
            resolved = self._resolve_arguments(step.operation, resources)
        except SelectionError as exc:
            step.output = _failed_output(step.operation, str(exc))
            self._restage_after(step_id)
            return step
        source = self._input_for(resolved)
        bad_argument = self._failed_argument(step.operation)
        if bad_argument is not None and source is not None:
            # Every row is blocked: hand the verb an input that says so.
            source = Output(source.data, source.ledger,
                            {**source.meta, "blocked_all": bad_argument})
        try:
            step.output = resolved.run(source, tools)
            step.output.data = _str_columns(step.output.data, step_id)
            mismatch = _output_mismatch(step.operation, step.output.data)
            if mismatch:
                raise SelectionError(mismatch)
        except SelectionError as exc:
            # 008 C7: a position out of range, a column that is gone — the step
            # fails with the reason, never None, NaN or an empty grid.
            step.output = _failed_output(step.operation, str(exc))
        self._restage_after(step_id)
        # 008 C10.5: re-running a step makes everything that already read it
        # stale — fixing a root clears what it blocked, by re-running it.
        self._mark_stale_dependents(step_id)
        return step

    def run_all(self, tools: dict[str, Callable] | None = None,
                resources: Mapping[str, Any] | None = None) -> "Workflow":
        """Run every valid step, each after the steps it reads.

        Still explicit — nothing recomputes on its own (§7's push/pull rule).
        This only saves you from ordering the calls by hand.

        **Stops at the first failure a step didn't catch**, raising
        :class:`StepFailed`; what already ran keeps its results. A step with
        ``mod.try_except(…)`` lets its failures through: a fallback value, or
        a failed row the steps after it are blocked on.
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
                # A check deferred at declaration (008 K1) is decided when its
                # input runs; a step that fails it is left reporting the
                # problem, not run, and does not stop the rest.
                if self.steps[step_id].valid:
                    self.run(step_id, tools, resources)
                    failure = _uncaught_failure(self.steps[step_id].output)
                    if failure is not None:
                        # A failure the step didn't catch stops the run.
                        not_run = [sid for sid in remaining
                                   if sid not in done and sid != step_id]
                        raise StepFailed(step_id, failure[0], failure[1], not_run)
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
                if other.step_id in changed:
                    continue
                if not other.output.meta.get("staged"):
                    continue                       # already has real data
                if not any(name in changed for name in other.operation.reads):
                    continue
                # Re-check too (008 K1): a column check that was deferred, or
                # one that failed against a guess, is decided now that the
                # input is real. Invalid steps are included — they may be
                # valid now.
                before = (other.output.meta.get("expected"), other.problems,
                          predicted_columns(other.output),
                          columns_unknown(other.output))
                other.problems = check(other.operation, self, other.step_id)
                other.output = stage(other.operation, self, other.problems)
                other.warnings = warn(other.operation, self)
                after = (other.output.meta.get("expected"), other.problems,
                         predicted_columns(other.output),
                         columns_unknown(other.output))
                if after != before:
                    wave.add(other.step_id)
            changed = wave

    def _upstream_ids(self, step_id: str, _seen: set[str] | None = None) -> set[str]:
        """Every step *step_id* transitively reads. Used to refuse cycles."""
        seen = set() if _seen is None else _seen
        step = self.steps.get(step_id)
        if step is None:
            return seen
        for name in step.operation.reads:
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
        blob = {"version": FORMAT_VERSION,
                "steps": [{"step_id": sid, "operation": st.operation.to_dict()}
                          for sid, st in self.steps.items()]}
        if self.resources:
            # The declarations, never the objects — the caller supplies those.
            blob["resources"] = {name: decl.to_dict()
                                 for name, decl in self.resources.items()}
        return blob

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
    def from_dict(cls, blob: dict, tools: dict[str, Callable] | None = None,
                  resource_types: dict[str, type] | None = None) -> "Workflow":
        """Rebuild a Workflow from either export — all at once.

        Every step goes through the same :func:`check` and :func:`stage` the
        incremental path uses, so loading cannot smuggle in a step that
        declaring would have rejected. *resource_types* maps a saved resource
        type name to its class, as *tools* does for tools; types registered with
        :func:`resource` (or used by ``define``) are found without it.
        """
        version = blob.get("version", 1)
        if not isinstance(version, int) or version > FORMAT_VERSION:
            # 008 K17: an older core must refuse a newer file, never strip it.
            raise ValueError(
                f"this workflow was saved in format version {version!r}; this "
                f"core reads versions 1 to {FORMAT_VERSION}. Upgrade "
                "simple-steps-core to load it.")
        workflow = cls()
        known = {**RESOURCE_TYPES, **(resource_types or {})}
        for name, entry in (blob.get("resources") or {}).items():
            workflow.resources[name] = ResourceDecl(
                name, known.get(entry["type"]), dict(entry.get("settings") or {}),
                entry["type"], entry.get("source", "defined"))
        for entry in blob["steps"]:
            sid = entry["step_id"]
            operation = _attach_bound(
                Operation.from_dict(entry["operation"], tools), workflow.resources)
            problems = check(operation, workflow, sid)
            workflow.steps[sid] = Step(sid, operation,
                                       stage(operation, workflow, problems),
                                       problems, warn(operation, workflow))
            # Restore this step's payload before checking the steps after it,
            # as declaring does: a later `select` is checked against the real
            # columns, not a staged guess that would refuse a valid step.
            encoded = (blob.get("outputs") or {}).get(sid)
            if encoded is not None:
                workflow.steps[sid].output = _decode_output(encoded)
        for sid in (blob.get("outputs") or {}):
            workflow._restage_after(sid)
        return workflow

    @classmethod
    def from_json(cls, data: str, tools: dict[str, Callable] | None = None,
                  resource_types: dict[str, type] | None = None) -> "Workflow":
        import json
        return cls.from_dict(json.loads(data), tools, resource_types)

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
            if kind == "try_except" and params.get("on") is not None:
                # Exception classes are written as classes and saved by name.
                on = params["on"]
                on = [on] if isinstance(on, (str, type)) else list(on)
                params["on"] = [o.__name__ if isinstance(o, type) else o for o in on]
            if kind == "expect" and isinstance(params.get("columns"), dict):
                # Types are written as Python types and saved as their names.
                params["columns"] = {k: _type_label(v)
                                     for k, v in params["columns"].items()}
            if isinstance(params.get("over"), str):
                # 008 K5: in Python a string is data everywhere else
                # (`scale[mod.map()]("readings")`), so it must not be a
                # reference here. JSON keeps string ids: from_dict reads them.
                raise TypeError(
                    f"over= takes a step reference, not a string: pass "
                    f"wf[{params['over']!r}] (grid.wf, or your Workflow)")
            return Modifier(kind, params)
        make.__name__ = kind
        return make


#: ``mod.map(...)``, ``mod.retry(times=2)`` — descriptors for :func:`stack`.
mod = _Mods()


def _resolve_tool_setting(value: Any, table: dict) -> Any:
    """A ``$tool`` setting as its function; anything else unchanged."""
    if isinstance(value, ToolHandle):
        return value.fn
    if isinstance(value, ToolRef):
        if value.id not in table:
            raise KeyError(f"setting names tool {value.id!r}, which is not registered")
        found = table[value.id]
        return found.fn if isinstance(found, ToolHandle) else found
    return value


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
        # 008 C2: a tool named in a setting is resolved from the same table.
        modifier = Modifier(modifier.kind, {
            k: _resolve_tool_setting(v, table) for k, v in modifier.params.items()})
        factory = DECORATORS.get(modifier.kind)
        if factory is None:
            raise KeyError(
                f"no decorator registered for modifier {modifier.kind!r}; "
                f"known: {sorted(DECORATORS)}"
            )
        fn = factory(fn, **modifier.params)
    return fn
