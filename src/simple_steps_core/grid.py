"""
Grid — a working prototype of the target model (docs/shape-algebra.md)
======================================================================

Standalone and importable today. It does **not** touch the engine, the
registry or the existing orchestrators, so nothing that works now can break.
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
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

import pandas as pd

__all__ = [
    "Output", "grid", "rows", "map_", "filter_", "group_", "collapse_",
    "expand_", "sweep_", "source_", "identity", "BUILTIN_TOOLS",
    "op", "Modifier", "Operation",
    "tool", "ToolHandle", "StepRef", "Step", "Workflow", "check", "stage",
    "ROWS_RULE",
    "stack", "mod",
    "DECORATORS", "MODIFIERS", "ModifierKind", "SHAPE_VERBS", "is_shape",
    "compile_operation", "Pipeline", "Verb",
    "Map", "Filter", "Expand", "Group", "Collapse",
    "PAYLOAD", "LEDGER_COLUMNS",
]

#: Default name for the column holding whatever a tool returned.
PAYLOAD = "value"

#: Every ledger has exactly these columns, so the UI can rely on them.
LEDGER_COLUMNS = ("status", "error", "attempts", "seconds", "source")


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
    def shape(self) -> str:
        return self.meta.get("shape", "grid")

    def progress(self) -> str:
        done = int((self.ledger["status"] == "completed").sum())
        return f"{done}/{len(self.ledger)}"

    # ── chaining: the same verbs, left to right ──────────────────────────
    # These read in execution order, which nested calls cannot. Each returns a
    # new Output, so nothing mutates and any intermediate stays inspectable.
    def map(self, fn, **kw) -> "Output":
        return map_(self, fn, **kw)

    def filter(self, fn, **kw) -> "Output":
        return filter_(self, fn, **kw)

    def group(self, fn, **kw) -> "Output":
        return group_(self, fn, **kw)

    def collapse(self, fn, **kw) -> "Output":
        return collapse_(self, fn, **kw)

    def expand(self, fn, **kw) -> "Output":
        return expand_(self, fn, **kw)

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
def identity(row: Any, column: str | None = None) -> Any:
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
    if not isinstance(row, dict):
        return row
    if column is not None:
        return row[column]
    if PAYLOAD in row:
        return row[PAYLOAD]
    if len(row) == 1:
        return next(iter(row.values()))
    return row


#: Tools every Operation can name without being handed a registry. Keeping
#: identity here is what lets a reshape-only step stay a normal step.
BUILTIN_TOOLS: dict[str, Callable] = {"identity": identity}


# ─────────────────────────────────────────────────────────────────────────
# Input coercion — "what is a row?"
# ─────────────────────────────────────────────────────────────────────────
def rows(value: Any, *, axis: str = "rows") -> pd.DataFrame:
    """Coerce any step input into a frame of units of work.

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
                  meta={"verb": "map", "shape": "column", "payload": name,
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
                  meta={"verb": "filter", "shape": "column",
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
                  meta={"verb": "group", "shape": "column", "payload": name,
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
                        "source": list(chunk.index)})
        index.append(position)

    data = pd.DataFrame(out_rows, index=index)
    if by is not None:                       # key first reads better
        data = data[[by, name]]
    return Output(data=data, ledger=_ledger(records, index),
                  meta={"verb": "collapse", "shape": "scalar" if by is None
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
            records.append({**record, "source": index})
            out_rows.append({**arg, name: None})
            continue
        items = (list(produced)
                 if isinstance(produced, Iterable)
                 and not isinstance(produced, (str, bytes, dict))
                 else [produced])
        for item in items:
            out_rows.append({**arg, name: item})
            records.append({**record, "source": index})

    data = pd.DataFrame(out_rows).reset_index(drop=True)
    return Output(data=data, ledger=_ledger(records, data.index),
                  meta={"verb": "expand", "shape": "column", "payload": name,
                        "n_in": len(frame)})


def sweep_(fn: Callable, *, name: str = PAYLOAD, retries: int = 0,
           **params: Sequence[Any]) -> Output:
    """``expand_grid`` — run *fn* over the cross product of named parameters.

    Each swept parameter becomes a **column**, so the result is a tidy table
    you can group and filter by::

        sweep_(plot, model=["a", "b"], window=[7, 30])
        →  model | window | value
    """
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
                  meta={"verb": "sweep", "shape": "grid", "payload": name,
                        "params": names, "grid": grid_shape,
                        "n_in": len(combos)})


def grid(value: Any) -> Output:
    """Lift any value into an Output so a chain can start from it.

    ``grid(df).map(score).filter(big)`` — the source step of a pipeline.
    """
    frame = rows(value)
    return Output(
        data=frame,
        ledger=_ledger([{"status": "completed", "error": None, "attempts": 1,
                         "seconds": 0.0} for _ in range(len(frame))], frame.index),
        meta={"verb": "source", "shape": "column", "payload": None,
              "n_in": len(frame)},
    )


def source_(value: Any, fn: Callable = identity, **_params) -> Output:
    """``source`` — lift a literal into a grid. The verb a flow starts with.

    Making this a verb rather than a special case is what closes the algebra:
    every step is then (verb, tool, arguments), the first one included. Its
    tool is ``identity``, because a source step *holds* data rather than
    computing it — applying a real tool is a ``map``, and refusing it here
    keeps the two from blurring.
    """
    if fn is not identity:
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


def _d_bind(fn: Callable, **literals) -> Callable:
    """Innermost decoration: the literals bound when the step was wired.

    The row stays the single positional unit of work and the constants arrive
    as keywords — the same split as the engine's ``_run_item``, where the item
    fills one parameter and ``shared`` fills the rest. So a tool written
    ``def score(row, threshold=0)`` gets ``threshold`` from
    ``score(threshold=5)[...]``, and the two channels cannot collide.
    """
    def run(x):
        return fn(x, **literals)
    run.__name__ = f"bind({getattr(fn, '__name__', 'fn')})"
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


def _kind(name: str, cls: str, apply: Callable) -> ModifierKind:
    return ModifierKind(name, cls, apply)


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
    _kind("source",   "shape", _lift(source_)),
    _kind("map",      "shape", _lift(map_)),
    _kind("filter",   "shape", _lift(filter_)),
    _kind("group",    "shape", _lift(group_)),
    _kind("expand",   "shape", _lift(expand_)),
    _kind("collapse", "shape", _lift(collapse_)),
    _kind("sweep",    "shape", _lift_generated(sweep_)),
    # execution modifiers — shape-preserving
    _kind("retry",    "execution", _d_retry),
    _kind("timeout",  "execution", _d_timeout),
)}


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
@dataclass(frozen=True)
class Modifier:
    """One entry in an Operation's stack: what to apply, and with what."""

    kind: str
    params: dict = field(default_factory=dict)

    @property
    def cls(self) -> str:
        """``"shape"``, ``"execution"``, or ``"unknown"`` for an unregistered kind."""
        entry = MODIFIERS.get(self.kind)
        return entry.cls if entry else "unknown"

    @property
    def is_shape(self) -> bool:
        return self.cls == "shape"

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.params.items())
        return f"{self.kind}({args})"


@dataclass(frozen=True)
class Operation:
    """One tool plus an ordered stack of modifiers — **data, not closures**.

    Built by chaining, which reads in application order: the first modifier
    added sits closest to the tool. ``op("score").retry(2).map(over="step1")``
    is the same composition as ``map(retry(score))`` — retry runs per item.
    """

    tool: str
    modifiers: tuple[Modifier, ...] = ()
    arguments: dict = field(default_factory=dict)
    #: The undecorated function, when this came from a ``@tool`` handle — so a
    #: decorated tool can be applied to data without a registry lookup.
    #: ``compare=False``: it is a convenience, never part of the step's data,
    #: so two Operations built the same way stay equal whether or not they
    #: happen to be carrying it.
    fn: Callable | None = field(default=None, compare=False, repr=False)

    def _add(self, kind: str, **params) -> "Operation":
        # Dereference here rather than in each caller: this is the one place
        # every modifier passes through, so a StepRef can never survive into
        # stored data as an object.
        return Operation(self.tool,
                         self.modifiers + (Modifier(kind, _deref(params)),),
                         self.arguments,
                         self.fn)

    # execution modifiers (shape-preserving)
    def retry(self, times: int) -> "Operation": return self._add("retry", times=times)
    def timeout(self, seconds: float) -> "Operation": return self._add("timeout", seconds=seconds)
    def cache(self, on: bool = True) -> "Operation": return self._add("cache", on=on)

    # shape verbs (at most one — see docs/shape-algebra.md §1.1)
    def map(self, **kw) -> "Operation": return self._shape("map", **kw)
    def filter(self, **kw) -> "Operation": return self._shape("filter", **kw)
    def group(self, **kw) -> "Operation": return self._shape("group", **kw)
    def collapse(self, **kw) -> "Operation": return self._shape("collapse", **kw)
    def expand(self, **kw) -> "Operation": return self._shape("expand", **kw)
    def sweep(self, **kw) -> "Operation": return self._shape("sweep", **kw)

    def _shape(self, kind: str, **params) -> "Operation":
        # A step may chain several shape verbs. Like a spreadsheet formula
        # `=SUM(FILTER(...))`, the nesting lives inside one cell; the step's
        # shape is the fold of them all.
        return self._add(kind, **params)

    def __getitem__(self, modifiers: Any) -> "Operation":
        """``score[mod.map(over=videos), mod.retry(times=2)]`` — the bracket form.

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

    # ── the other half: hand the decorated tool some data ────────────────
    def __call__(self, source: Any) -> Any:
        """Apply the decorated tool to actual data — ``score[...](videos)``.

        The brackets decorated; this runs. Everything the stack describes is
        applied here, at call time, exactly as :func:`compile_operation` would
        — which is what it delegates to.
        """
        return self.run(source)

    def run(self, source: Any, tools: dict[str, Callable] | None = None) -> Any:
        """Compile the stack and apply it to *source*.

        Mirrors ``Tool.run()`` in the registry: the deferred form is the
        default and this is the immediate escape hatch. *tools* is needed only
        when this Operation names its tool by id (``op("score")``) rather than
        carrying it (``score[...]`` from a ``@tool`` handle).
        """
        table = {**BUILTIN_TOOLS, **(tools or {})}
        if self.fn is not None:
            table.setdefault(self.tool, self.fn)
        if self.tool not in table:
            raise KeyError(
                f"cannot run {self.tool!r}: this Operation names its tool by id, "
                f"so pass the function — run(source, tools={{{self.tool!r}: fn}}). "
                "Operations built from a @tool handle carry it already."
            )
        return compile_operation(self, table)(source)

    def __repr__(self) -> str:
        # Written order, outermost first — the order the brackets were typed in,
        # so a repr can be compared against the source that produced it. The
        # tool comes last because that is what the layers close over.
        stack = "".join(f"{m!r} ∘ " for m in self.layers)
        return f"<Operation {stack}{self.tool}>"


def op(tool: str, **arguments) -> Operation:
    """Start building an Operation for *tool*."""
    return Operation(tool=tool, arguments=arguments)


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

    def __str__(self) -> str:
        return self.id

    def __repr__(self) -> str:
        return f"<{self.id}>"


def _deref(value: Any) -> Any:
    """StepRefs become their ids; everything else passes through."""
    if isinstance(value, StepRef):
        return value.id
    if isinstance(value, dict):
        return {k: _deref(v) for k, v in value.items()}
    return value


class ToolHandle:
    """What ``@tool`` returns: the function, plus the chain constructors.

    ``transcribe.map(over=videos).retry(2)`` reads as one thought and builds an
    ``Operation`` — the same data ``op("transcribe")...`` would.
    """

    def __init__(self, fn: Callable, tool_id: str | None = None):
        self.fn = fn
        self.id = tool_id or fn.__name__
        self.__doc__ = fn.__doc__
        self.__name__ = self.id

    def __call__(self, **arguments) -> Operation:
        """Bind literals — the `single` case: run this tool once.

        Keyword-only, which is what keeps it distinct from applying the
        decorated tool to data: ``score(threshold=3)`` binds, ``score[...](df)``
        runs.
        """
        return Operation(tool=self.id, arguments=_deref(arguments), fn=self.fn)

    def _start(self) -> Operation:
        return Operation(tool=self.id, fn=self.fn)

    def __getitem__(self, modifiers: Any) -> Operation:
        """``transcribe[mod.map(over=videos), mod.retry(times=2)]``.

        The same composition as ``transcribe.retry(2).map(over=videos)``, read
        as a decorator stack instead of a chain. Arguments survive it:
        ``transcribe(model="large")[mod.map(over=videos)]``.
        """
        return self._start()[modifiers]

    # shape verbs
    def map(self, **kw) -> Operation: return self._start().map(**kw)
    def filter(self, **kw) -> Operation: return self._start().filter(**kw)
    def group(self, **kw) -> Operation: return self._start().group(**kw)
    def collapse(self, **kw) -> Operation: return self._start().collapse(**kw)
    def expand(self, **kw) -> Operation: return self._start().expand(**kw)
    def sweep(self, **kw) -> Operation: return self._start().sweep(**kw)

    # execution modifiers
    def retry(self, times: int) -> Operation: return self._start().retry(times)
    def timeout(self, seconds: float) -> Operation: return self._start().timeout(seconds)

    def __repr__(self) -> str:
        return f"<tool {self.id!r}>"


def tool(fn: Callable | None = None, *, id: str | None = None):
    """Mark a plain function as a tool. Usable bare or with an id."""
    if fn is not None:
        return ToolHandle(fn)
    return lambda f: ToolHandle(f, id)


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


def check(operation: Operation, workflow: "Workflow | None" = None) -> tuple[str, ...]:
    """Everything wrong with *operation* that is knowable without running it.

    Returns the problems, empty when there are none. This never raises: a
    reactive editor has to be able to *show* a bad step while you are still
    typing it, so validity is a property of the Step, not a precondition for
    building one.
    """
    problems: list[str] = []

    # 1. the tool has to exist
    fn = operation.fn or BUILTIN_TOOLS.get(operation.tool)
    if fn is None:
        problems.append(f"unknown tool {operation.tool!r}")

    # 2. every modifier kind has to be in the vocabulary
    for modifier in operation.modifiers:
        if modifier.kind not in MODIFIERS:
            problems.append(f"unknown modifier {modifier.kind!r}")

    # 3. `over` has to name a step that already exists
    for modifier in operation.modifiers:
        over = modifier.params.get("over")
        if over is None or workflow is None:
            continue
        if str(over) not in workflow.steps:
            problems.append(
                f"{modifier.kind} over {str(over)!r}, which is not an earlier step"
            )

    # 4. source applies no tool
    if any(m.kind == "source" for m in operation.modifiers) and fn is not identity:
        problems.append("source applies no tool; use map to compute")

    # 5. bound literals have to be parameters the tool accepts — the reactive
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
                        f"{operation.tool}() takes no argument {name!r}; "
                        f"it accepts {', '.join(list(parameters)[1:]) or '(none)'}"
                    )
    return tuple(problems)


#: §3's rows column, as data: what each verb does to the input's row count.
#: This is what staging folds, and it is why a staged claim can be honest —
#: ``filter`` can promise "at most n", never "n".
ROWS_RULE: dict[str, str] = {
    "source": "same", "map": "same", "group": "same",
    "filter": "at_most", "collapse": "one",
    "expand": "unknown", "sweep": "generated",
}


def stage(operation: Operation, workflow: "Workflow | None" = None,
          problems: tuple[str, ...] = (), step_id: str | None = None) -> Output:
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
            meta={"verb": kind, "shape": "scalar", "payload": PAYLOAD,
                  "staged": True, "problems": problems, "n_in": None,
                  "expected": None, "rows_rule": None},
        )

    known = (workflow._known_index(operation, step_id)
             if workflow is not None else None)
    n_in = None if known is None else len(known)
    rule = ROWS_RULE.get(kind)

    if kind is None:                       # no orchestration → a single value
        index, expected = [0], 1
    elif rule == "same" and known is not None:
        index, expected = list(known), n_in
    elif rule == "one":
        index, expected = [0], 1
    else:                                  # not addressable yet
        index, expected = [], None

    records = [{"status": "staged", "error": None, "attempts": 0, "seconds": 0.0}
               for _ in index]
    return Output(
        data=pd.DataFrame({PAYLOAD: [None] * len(index)}, index=index),
        ledger=_ledger(records, index),
        meta={"verb": kind, "shape": "scalar" if kind is None else "column",
              "payload": PAYLOAD, "staged": True, "problems": (),
              "n_in": n_in, "expected": expected, "rows_rule": rule},
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
        return "completed" if states else "staged"

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
        tool = self.operation.tool
        if not self.output.meta.get("staged"):
            n = len(self.output.data)
            return (f"{tool} · one cell" if verb is None
                    else f"{verb} {tool} · {n} cell{'' if n == 1 else 's'}")
        if verb is None:
            return f"{tool} · one cell"
        n_in, rule = self.output.meta.get("n_in"), self.output.meta.get("rows_rule")
        if rule == "one":
            return f"{verb} {tool} · 1 cell"
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
        #: Literal data a source step reads, keyed by step id. Kept **beside**
        #: the Operations, never inside them: that is what lets the light
        #: export be structure-only while the full export adds payloads.
        self.inputs: dict[str, Any] = {}

    # ── declaring ────────────────────────────────────────────────────────
    def __setitem__(self, step_id: str, operation: Any) -> None:
        if not isinstance(operation, Operation):
            # A bare value is a source step: store the payload, declare the
            # Operation that reads it. `wf["raw"] = df` is the common case.
            self.inputs[step_id] = operation
            operation = Operation(tool="identity", fn=identity)[mod.source()]
        problems = check(operation, self)
        self.steps[step_id] = Step(
            step_id, operation, stage(operation, self, problems, step_id), problems
        )

    def __getitem__(self, step_id: str) -> StepRef:
        if step_id not in self.steps:
            raise KeyError(f"no step {step_id!r}; defined so far: {list(self.steps)}")
        return StepRef(step_id)

    def __contains__(self, step_id: str) -> bool:
        return step_id in self.steps

    def step(self, step_id: str) -> Step:
        """The Step itself, rather than a reference to it."""
        return self.steps[step_id]

    # ── what a step reads ────────────────────────────────────────────────
    def _known_index(self, operation: Operation,
                     step_id: str | None = None) -> Sequence[Any] | None:
        """The input's index, when known — enough to stage, short of running.

        A source step's payload is known from declaration, and a staged step
        already carries an index, so cardinality propagates down the chain
        before anything has executed. That is §7's level 2/3 without a run.
        """
        if any(m.kind == "source" for m in operation.modifiers):
            payload = self.inputs.get(step_id) if step_id is not None else None
            return None if payload is None else rows(payload).index
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

    def _input_for(self, operation: Operation,
                   step_id: str | None = None) -> Any | None:
        """What this operation will read, when that is already known.

        A source step reads its stored payload — known from declaration, which
        is why a source step stages with its cardinality already filled in. Any
        other step reads an upstream Output, known only once that step has run.
        """
        if any(m.kind == "source" for m in operation.modifiers):
            if step_id is not None:
                return self.inputs.get(step_id)
            for sid, step in self.steps.items():
                if step.operation is operation:
                    return self.inputs.get(sid)
            return None
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
    def run(self, step_id: str, tools: dict[str, Callable] | None = None) -> Step:
        """Execute a step and replace its staged Output with the real one."""
        step = self.steps[step_id]
        if not step.valid:
            raise ValueError(
                f"step {step_id!r} is invalid and cannot run: {step.problems[0]}"
            )
        step.output = step.operation.run(
            self._input_for(step.operation, step_id), tools
        )
        self._restage_after(step_id)
        return step

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
                other.output = stage(other.operation, self, other.problems,
                                     other.step_id)
                if other.output.meta.get("expected") != before:
                    wave.add(other.step_id)
            changed = wave

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
            return Modifier(kind, _deref(params))
        make.__name__ = kind
        return make


#: ``mod.map(...)``, ``mod.retry(times=2)`` — descriptors for :func:`stack`.
mod = _Mods()


def stack(*layers: Any) -> Operation:
    """Build an Operation from a vertical stack, read like a decorator list.

    The **last** argument is the tool and the ones above it are modifiers,
    outermost first — exactly how ``@outer`` / ``@inner`` above a ``def``
    reads::

        stack(
            mod.map(over=videos),     # outermost
            mod.retry(times=2),
            transcribe,               # the tool
        )

    Applied bottom-up, so this is ``map(retry(transcribe))`` and the retry runs
    per item. Equivalent to ``transcribe.retry(2).map(over=videos)`` and to the
    bracket form ``transcribe[mod.map(over=videos), mod.retry(times=2)]``,
    which this delegates to — one code path, three ways to read it.
    """
    if not layers:
        raise ValueError("stack() needs at least a tool")
    *modifiers, target = layers
    tool_id = target.id if isinstance(target, ToolHandle) else str(target)
    return Operation(tool=tool_id)[tuple(modifiers)]


def compile_operation(operation: Operation, tools: dict[str, Callable]) -> Callable:
    """Apply an Operation's stack to its tool, innermost-first.

    This is the moment the data becomes behaviour: ``[retry, map]`` compiles to
    ``map(retry(tool))`` — the same object graph ``@map`` over ``@retry`` over
    the function would have produced at definition time.
    """
    table = {**BUILTIN_TOOLS, **tools}
    if operation.tool not in table:
        raise KeyError(f"unknown tool {operation.tool!r}; have {sorted(table)}")
    fn = table[operation.tool]
    if operation.arguments:
        # Bound literals sit closest to the tool — inside every modifier, so a
        # retry re-runs the same call and a map passes them to every item.
        fn = _d_bind(fn, **operation.arguments)
    for modifier in operation.modifiers:               # innermost first
        factory = DECORATORS.get(modifier.kind)
        if factory is None:
            raise KeyError(
                f"no decorator registered for modifier {modifier.kind!r}; "
                f"known: {sorted(DECORATORS)}"
            )
        fn = factory(fn, **modifier.params)
    return fn


# ─────────────────────────────────────────────────────────────────────────
# Pipelines: several verbs, each holding its own literals
# ─────────────────────────────────────────────────────────────────────────
# `filter(is_big).map(score).of(raw)` reads as one thought, and each verb keeps
# its arguments inside its own parentheses. It expands to **one step per
# shape verb**, so every intermediate keeps an address and stays inspectable
# — the compact syntax does not cost you the spreadsheet.


@dataclass(frozen=True)
class Verb:
    """One shape verb plus the tool and literals that belong to it."""

    kind: str
    tool: Any = None
    params: dict = field(default_factory=dict)

    @property
    def tool_id(self) -> str:
        """The function this verb applies — ``identity`` when none was given.

        A higher-order function is still a function, so ``expand(step1)`` is
        complete on its own: expand *something* over step1, and the something
        defaults to passing each item through unchanged.
        """
        if isinstance(self.tool, ToolHandle):
            return self.tool.id
        if isinstance(self.tool, str):
            return self.tool
        return "identity"

    def __repr__(self) -> str:
        name = getattr(self.tool, "id", self.tool)
        extra = "".join(f", {k}={v!r}" for k, v in self.params.items())
        return f"{self.kind}({name}{extra})"


class Pipeline:
    """A chain of verbs, bound to a source only at the end."""

    def __init__(self, verbs: tuple[Verb, ...] = ()):
        self.verbs = verbs

    def _then(self, kind: str, tool: Any = None, **params) -> "Pipeline":
        return Pipeline(self.verbs + (Verb(kind, tool, params),))

    def map(self, tool=None, **kw): return self._then("map", tool, **kw)
    def filter(self, tool=None, **kw): return self._then("filter", tool, **kw)
    def expand(self, tool=None, **kw): return self._then("expand", tool, **kw)
    def group(self, tool=None, **kw): return self._then("group", tool, **kw)
    def collapse(self, tool=None, **kw): return self._then("collapse", tool, **kw)

    def of(self, source: Any) -> Operation:
        """Bind the source, producing the single Operation for this step."""
        return _bind(self.verbs, source)

    __call__ = of

    def __repr__(self) -> str:
        return " -> ".join(repr(v) for v in self.verbs) or "<empty pipeline>"


def _bind(verbs: tuple[Verb, ...], source: Any) -> Operation:
    """Fold a chain of verbs into **one** Operation — one step.

    The innermost verb names the step's tool (the "one real function"); the
    rest stack on top of it as modifiers, innermost first. ``over`` is recorded
    once, on the innermost verb, because that is what reads the source.
    """
    if not verbs:
        raise ValueError("a pipeline needs at least one verb")
    first, *rest = verbs
    operation = Operation(tool=first.tool_id)._shape(
        first.kind, over=_deref(source), **first.params
    )
    for verb in rest:
        operation = operation._add(
            verb.kind, **({"op": verb.tool_id} if verb.tool is not None else {}),
            **verb.params,
        )
    return operation


def _verb_entry(kind: str):
    def make(tool=None, **kw) -> Any:
        # `Expand(step1)` — the argument is a source, not a tool, so the verb
        # is already complete and applies identity.
        if isinstance(tool, StepRef):
            return _bind((Verb(kind, None, kw),), tool)
        return Pipeline()._then(kind, tool, **kw)
    make.__name__ = kind
    return make


#: Top-level verb constructors, so a pipeline can start with any of them.
Map, Filter, Expand, Group, Collapse = (
    _verb_entry(k) for k in ("map", "filter", "expand", "group", "collapse")
)
