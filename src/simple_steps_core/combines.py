"""Combines: join, stack and zip_, the operations that read several steps.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from typing import Any
import pandas as pd


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


def _row_lookup(frame: pd.DataFrame) -> dict:
    """str(row id) → row id, to match ids across grids whatever their type."""
    return {str(i): i for i in frame.index}


def _combine_zip(frames: list[pd.DataFrame], config: dict) -> pd.DataFrame:
    """Put grids side by side, **row id to row id** — strictly (009 decision 2).

    Each row of the finest grid (the one whose ids are derived from the
    others', e.g. ``expand`` items ``1.0``, ``1.1``) is paired with the row of
    the same id in every other grid, or with the row it was derived from. The
    result keeps the finest grid's rows and ids; with no finer grid, the first.

    **No row is ever dropped silently.** A row with no match fails the step,
    and so does a row of a same-level grid that nothing matched — use ``join``
    for partial matches. Only a parent grid may have rows nothing points to (a
    row that expanded to nothing). Grids whose ids are unrelated are paired by
    position when their lengths agree, and refused when they don't.
    """
    names = [f.attrs.get("name") or f"input {i + 1}" for i, f in enumerate(frames)]
    depth = [max((len(_ancestors(i)) for i in f.index), default=0) for f in frames]
    primary = max(range(len(frames)), key=lambda i: (depth[i], -i))
    target = frames[primary].index
    keys = [str(t) for t in target]
    aligned, picked_ids = [], []
    for i, frame in enumerate(frames):
        if i == primary:
            aligned.append(frame)
            picked_ids.append(list(frame.index))
            continue
        lookup = _row_lookup(frame)
        related = any(k in lookup or any(a in lookup for a in _ancestors(k)) for k in keys)
        if not related and len(frame):
            if len(frame) != len(target):
                raise ValueError(
                    f"zip_ can't line up {names[primary]!r} ({len(target)} rows) and "
                    f"{names[i]!r} ({len(frame)} rows): their row ids are unrelated "
                    f"and their lengths differ. Use join to match them on a column")
            aligned.append(frame.set_axis(target))     # unrelated ids: by position
            picked_ids.append(list(frame.index))
            continue
        picked, unmatched, used = [], [], set()
        for key in keys:
            match = key if key in lookup else next(
                (a for a in _ancestors(key) if a in lookup), None)
            if match is None:
                unmatched.append(key)
                continue
            picked.append(lookup[match])
            used.add(match)
        if unmatched:
            raise ValueError(
                f"zip_ pairs rows by id: {_rows_text(unmatched)} of {names[primary]!r} "
                f"{'has' if len(unmatched) == 1 else 'have'} no matching row in "
                f"{names[i]!r}. For a partial match, use join")
        if depth[i] == depth[primary]:
            extra = [k for k in lookup if k not in used]
            if extra:
                raise ValueError(
                    f"zip_ pairs rows by id: {_rows_text(extra)} of {names[i]!r} "
                    f"{'has' if len(extra) == 1 else 'have'} no matching row in "
                    f"{names[primary]!r}. For a partial match, use join")
        out = frame.loc[picked]
        out.index = target
        aligned.append(out)
        picked_ids.append(picked)
    clash = _zip_clash([(names[i], list(f.columns)) for i, f in enumerate(frames)])
    if clash:
        raise ValueError(clash)                  # 010 C22: never keep one silently
    data = pd.concat(aligned, axis=1)
    data.attrs["zip_picked"] = picked_ids        # for carrying each cell's state
    return data


def _zip_clash(named: list[tuple[str, list]]) -> str | None:
    """The first column two zipped grids share, as a problem — or None (010 C22)."""
    owner: dict = {}
    for name, columns in named:
        for c in columns:
            if c in owner and owner[c] != name:
                return (f"zip_: {c!r} is in both {owner[c]!r} and {name!r}; rename "
                        f"one (mod.map(name=…) or mod.rename)")
            owner.setdefault(c, name)
    return None


def _rows_text(keys: list[str]) -> str:
    shown = ", ".join(keys[:5]) + ("…" if len(keys) > 5 else "")
    return f"row{'s' if len(keys) > 1 else ''} {shown}"


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
    return operation.tool in COMBINE


def _combine_op(kind: str, grids: tuple, config: dict) -> Operation:
    refs = tuple(g if isinstance(g, StepRef) else StepRef(str(g)) for g in grids)
    return Operation(tool=kind, arguments=config,
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
    if operation.tool == "join":
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
    spec = COMBINE[operation.tool]
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
        data=pd.DataFrame({c: [None] * len(index) for c in columns or [VALUE_COLUMN]},
                          index=index),
        records=records, index=index,
        meta={"verb": operation.tool, "form": "column", "value_column": None,
              "staged": True, "problems": (), "n_in": None, "expected": expected,
              "rows_rule": rule, "columns": columns, "columns_open": columns_open},
    )


def _run_combine(operation: Operation, frames: list[pd.DataFrame]) -> Output:
    """Apply a combine to its (already-run) input grids — no tool, so every
    output row is trivially complete."""
    data = COMBINE[operation.tool]["apply"](frames, operation.arguments)
    records = [{"status": "completed", "error": None, "attempts": 0,
                "seconds": 0.0} for _ in range(len(data))]
    return Output(data=data, records=records, index=data.index,
                  meta={"verb": operation.tool, "form": "column",
                        "value_column": None, "n_in": None,
                        "columns": list(data.columns)})


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .checks import columns_unknown, predicted_columns  # noqa: E402
from .operation import Operation  # noqa: E402
from .output import Output, VALUE_COLUMN  # noqa: E402
from .references import StepRef  # noqa: E402
from .verbs import _ancestors  # noqa: E402
from .workflow import Workflow  # noqa: E402
