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
def _variables_only(frames: list[pd.DataFrame]) -> list[pd.DataFrame]:
    """`join` and `stack` make new rows, so their inputs' `#` columns don't
    describe them. They will write their own (reshaping.md §5.1, step 4)."""
    return [f[[c for c in f.columns if not is_id_column(c)]] for f in frames]


def _combine_stack(frames: list[pd.DataFrame], config: dict) -> pd.DataFrame:
    return pd.concat(_variables_only(frames), axis=0, join=config.get("join", "outer"),
                     ignore_index=True)


def _row_lookup(frame: pd.DataFrame) -> dict:
    """row id → row id. Ids match exactly: ``1`` is not ``"1"`` (reshaping.md §6)."""
    return {i: i for i in frame.index}


def _combine_zip(frames: list[pd.DataFrame], config: dict) -> pd.DataFrame:
    """Put grids side by side, **row id to row id** — strictly (009 decision 2).

    Each row of the finest grid (the one whose ids are derived from the
    others', e.g. ``expand`` items ``1.0``, ``1.1``) is paired with the row of
    the same id in every other grid, or with the row it was derived from. The
    result keeps the finest grid's rows and ids; with no finer grid, the first.

    **No row is ever dropped silently.** A row with no match fails the step,
    and so does a row of a same-level grid that nothing matched — use ``join``
    for partial matches. Only a parent grid may have rows nothing points to (a
    row that expanded to nothing). Grids that share no row ids are refused:
    rows are never paired by position (K19).
    """
    names = [f.attrs.get("name") or f"input {i + 1}" for i, f in enumerate(frames)]
    traces = [{} if config.get("match_ids") else (f.attrs.get("traces") or {}) for f in frames]

    def finer(i: int, j: int) -> bool:
        """Do *i*'s rows come from *j*'s, and not the other way round?"""
        return traces[i].get(j) is not None and traces[j].get(i) is None

    # The finest grid (an expand's items, say) leads: each of its rows is
    # paired with the row of every other grid it came from, found through its
    # `#` columns. With none finer, the first leads and rows pair by id.
    primary = max(range(len(frames)),
                  key=lambda i: (sum(finer(i, j) for j in range(len(frames))), -i))
    target = frames[primary].index
    keys = list(target)
    aligned, picked_ids = [], []
    for i, frame in enumerate(frames):
        if i == primary:
            aligned.append(frame)
            picked_ids.append(list(frame.index))
            continue
        lookup = _row_lookup(frame)
        traced = traces[primary].get(i)
        wanted = list(traced) if traced is not None else keys
        related = any(k in lookup for k in wanted if k is not None)
        if not related and len(frame):
            # K19: rows pair by id, never by position (docs/design/row-ids.md §5).
            raise ValueError(
                f"zip_ pairs rows by id, and {names[primary]!r} and {names[i]!r} "
                f"share none ({_rows_text([str(x) for x in list(target)[:3]])} … vs "
                f"{_rows_text([str(x) for x in list(frame.index)[:3]])} …). "
                "Use join to match them on a column")
        picked, unmatched, used = [], [], set()
        for key, want in zip(keys, wanted):
            if want is None or want not in lookup:
                unmatched.append(key)
                continue
            picked.append(lookup[want])
            used.add(want)
        if unmatched:
            raise ValueError(
                f"zip_ pairs rows by id: {_rows_text(unmatched)} of {names[primary]!r} "
                f"{'has' if len(unmatched) == 1 else 'have'} no matching row in "
                f"{names[i]!r}. For a partial match, use join")
        if not finer(primary, i):         # a coarser grid may have rows nothing points to
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
    # Grids of one origin share their `#` columns: keep one of each (§5.1).
    data = data.loc[:, ~(data.columns.duplicated() & [is_id_column(c) for c in data.columns])]
    data.attrs["zip_picked"] = picked_ids        # for carrying each cell's state
    return data


def _zip_clash(named: list[tuple[str, list]]) -> str | None:
    """The first column two zipped grids share, as a problem — or None (010 C22)."""
    owner: dict = {}
    for name, columns in named:
        for c in columns:
            if is_id_column(c):
                continue                         # merged, not collided (§5.1)
            if c in owner and owner[c] != name:
                return (f"zip_: {c!r} is in both {owner[c]!r} and {name!r}; rename "
                        f"one (mod.name(…) or mod.rename)")
            owner.setdefault(c, name)
    return None


def _rows_text(keys: list) -> str:
    keys = [str(k) for k in keys]
    shown = ", ".join(keys[:5]) + ("…" if len(keys) > 5 else "")
    return f"row{'s' if len(keys) > 1 else ''} {shown}"


def _combine_join(frames: list[pd.DataFrame], config: dict) -> pd.DataFrame:
    left, right = _variables_only(frames)
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


def zip_(*grids: Any, match_ids: bool = False) -> Operation:
    """Put grids side by side, each row beside the rows it matches.

    Rows match only as core recorded it (docs/design/reshaping.md §6): the
    same rows (one origin), or a row and the one it came from. Anything else
    is refused when the step is declared. ``match_ids=True`` is you vouching
    that the grids number the same samples the same way: their ids must then
    be the same set, of the same type. Named ``zip_`` so it does not shadow
    the builtin ``zip``."""
    return _combine_op("zip", grids, {"match_ids": True} if match_ids else {})


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
from .output import is_id_column  # noqa: E402
from .workflow import Workflow  # noqa: E402
