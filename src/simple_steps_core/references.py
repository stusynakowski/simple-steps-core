"""References: steps, selections of rows and columns, resources and tools.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from typing import Any
import numbers
import pandas as pd


def _is_int(value: Any) -> bool:
    return isinstance(value, numbers.Integral) and not isinstance(value, bool)


def _row_part(key: Any, strings: bool = False) -> Any:
    """A row selector in saved form (K19, docs/design/row-ids.md): a row id or a
    list of row ids, or ``{start, stop}``, a range of positions.

    A plain bracket takes int ids; ``rows[…]`` (*strings*) also takes string
    ids, such as expand's ``"0.1"``, since a bare string reads like a column.
    """
    if isinstance(key, Rows):
        return key.sel
    if isinstance(key, Condition):
        return {"where": key.tree}            # S5c: rows chosen by a condition
    if isinstance(key, Cols) or isinstance(key, _Operand):
        raise SelectionError("a row part takes a condition, a comparison: "
                             "wf[…][cols['n'] > 15], not cols['n'] on its own")
    if isinstance(key, str):
        raise SelectionError(
            f"rows are row numbers, as shown in #: {key!r} isn't one. Pick the row "
            f"by its number (wf[…][0]) or by a condition (wf[…][cols['ward'] == {key!r}]); "
            f"columns use cols: wf[…][cols[{key!r}]]")
    if _is_int(key):
        return int(key)                       # a row number; -1 is the last (S5d)
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
        return [_row_part(k, strings) for k in key]
    raise SelectionError(
        f"rows are selected by row id, a list of row ids or a range of "
        f"positions; got {type(key).__name__}")


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
    """``cols["name":"price"]`` selects columns; ``cols["n"] > 15`` is a
    condition on one column's values (S5c)."""
    sel: Any = field(hash=False)

    def _operand(self) -> "_Operand":
        names = self.sel.get("names") if isinstance(self.sel, dict) else None
        if not names or len(names) != 1:
            raise SelectionError("a condition compares one column: cols['n'] > 15")
        return _Operand({"col": names[0]})

    def __eq__(self, other: Any) -> Any:
        if isinstance(other, Cols):
            return self.sel == other.sel
        return self._operand() == other

    def __ne__(self, other: Any) -> Any:
        if isinstance(other, Cols):
            return self.sel != other.sel
        return self._operand() != other

    __hash__ = object.__hash__

    def __lt__(self, other: Any) -> "Condition":
        return self._operand() < other

    def __le__(self, other: Any) -> "Condition":
        return self._operand() <= other

    def __gt__(self, other: Any) -> "Condition":
        return self._operand() > other

    def __ge__(self, other: Any) -> "Condition":
        return self._operand() >= other

    def isin(self, values: Any) -> "Condition":
        return self._operand().isin(values)


_LITERALS = (type(None), bool, int, float, str)


def _literal(value: Any) -> Any:
    """A condition's literal, as saved: a number, text, a bool, None, or a list of them."""
    if isinstance(value, _LITERALS) and not isinstance(value, Condition):
        return value
    if isinstance(value, (list, tuple)) and all(isinstance(v, _LITERALS) for v in value):
        return list(value)
    raise SelectionError(f"a condition compares with a literal (a number, text, True, None "
                         f"or a list of them), got {type(value).__name__}")


class _Operand:
    """One side of a test: ``cols["n"]`` (a value) or ``row["r"]`` (a row number)."""

    def __init__(self, on: dict):
        self.on = on

    def _test(self, op: str, other: Any) -> "Condition":
        return Condition({"test": op, "on": dict(self.on), "value": _literal(other)})

    def __eq__(self, other: Any) -> "Condition":           # type: ignore[override]
        return self._test("==", other)

    def __ne__(self, other: Any) -> "Condition":           # type: ignore[override]
        return self._test("!=", other)

    __hash__ = object.__hash__

    def __lt__(self, other: Any) -> "Condition":
        return self._test("<", other)

    def __le__(self, other: Any) -> "Condition":
        return self._test("<=", other)

    def __gt__(self, other: Any) -> "Condition":
        return self._test(">", other)

    def __ge__(self, other: Any) -> "Condition":
        return self._test(">=", other)

    def isin(self, values: Any) -> "Condition":
        return Condition({"test": "isin", "on": dict(self.on), "value": _literal(list(values))})

    @property
    def idx(self) -> "_Operand":
        """``row["r"].idx``: the item's place in r's cell, after an expand."""
        if "row" not in self.on or self.on.get("idx"):
            raise SelectionError(".idx follows row['step']: row['r'].idx")
        return _Operand({**self.on, "idx": True})

    def __repr__(self) -> str:
        return _operand_source(self.on)


class _RowIndexer:
    """``row["r"]``: this row's row number in step r, its own or its lineage's (S5c)."""

    def __getitem__(self, step_id: str) -> _Operand:
        if not isinstance(step_id, str) or not step_id:
            raise SelectionError(f"row[…] takes a step name, got {step_id!r}")
        return _Operand({"row": step_id})

    def __repr__(self) -> str:
        return "row"


class Condition:
    """Tests on one step's rows, joined by ``&``, ``|``, ``~``: plain data in
    ``tree``, read by core, never run as Python (S5c, core-asks rule 9)."""

    def __init__(self, tree: dict):
        self.tree = tree

    def __and__(self, other: "Condition") -> "Condition":
        return Condition({"and": [self.tree, _tree(other)]})

    def __or__(self, other: "Condition") -> "Condition":
        return Condition({"or": [self.tree, _tree(other)]})

    def __invert__(self) -> "Condition":
        return Condition({"not": self.tree})

    def __bool__(self) -> bool:
        raise TypeError("a condition joins with &, | and ~, each test in brackets: "
                        "(cols['n'] > 15) & (cols['ward'] == 'A')")

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Condition) and self.tree == other.tree

    __hash__ = object.__hash__

    def __repr__(self) -> str:
        return condition_source(self.tree)


def _tree(value: Any) -> dict:
    if not isinstance(value, Condition):
        raise SelectionError(f"&, | and ~ join conditions, got {type(value).__name__}")
    return value.tree


def _operand_source(on: dict) -> str:
    if "col" in on:
        return f'cols["{on["col"]}"]'
    return f'row["{on["row"]}"]' + (".idx" if on.get("idx") else "")


def condition_source(tree: dict, top: bool = True) -> str:
    """A condition as written: ``cols["n"] > 15``, ``(a) & (b)``, ``~(a)``."""
    if "test" in tree:
        literal = tree["value"]
        shown = repr(literal).replace("'", '"') if isinstance(literal, (str, list)) else repr(literal)
        if tree["test"] == "isin":
            text = f"{_operand_source(tree['on'])}.isin({shown})"
        else:
            text = f"{_operand_source(tree['on'])} {tree['test']} {shown}"
        return text if top else f"({text})"
    if "not" in tree:
        return f"~{condition_source(tree['not'], False)}"
    joiner, parts = ("&", tree["and"]) if "and" in tree else ("|", tree["or"])
    text = f" {joiner} ".join(condition_source(t, False) for t in parts)
    return text if top else f"({text})"


def _cell_test(op: str, value: Any, literal: Any, where: str) -> bool:
    """One test on one cell (CA-L3): a list cell is matched by membership; an
    empty cell fails every test."""
    empty = value is None or (isinstance(value, float) and value != value) or value is pd.NA
    if literal is None and op in ("==", "!="):
        return empty == (op == "==")          # row["other"] == None: an empty side (S5-D6)
    if empty:
        return False
    if isinstance(value, list):
        if op == "==":
            return literal in value
        if op == "!=":
            return literal not in value
        if op == "isin":
            return any(v in literal for v in value)
        raise SelectionError(f"{where}: {op} isn't defined on a list cell; use ==, != or .isin")
    if op == "isin":
        return value in literal
    try:
        return bool({"==": lambda: value == literal, "!=": lambda: value != literal,
                     "<": lambda: value < literal, "<=": lambda: value <= literal,
                     ">": lambda: value > literal, ">=": lambda: value >= literal}[op]())
    except TypeError:
        raise SelectionError(f"{where}: can't compare {value!r} {op} {literal!r}") from None


def _where(frame: pd.DataFrame, tree: dict, lineage: dict | None, step_id: str) -> list:
    """Which rows of *frame* *tree* keeps: a mask, in row order."""
    n = len(frame)

    def operand(on: dict) -> list:
        if "col" in on:
            if on["col"] not in frame.columns:
                raise SelectionError(f"the condition reads cols[{on['col']!r}], which "
                                     f"{step_id!r} doesn't have")
            return list(frame[on["col"]])
        if on["row"] == step_id and not on.get("idx"):
            return list(range(n))                  # its own row number
        name = f"{ROW_ID}{on['row']}" + (".idx" if on.get("idx") else "")
        if lineage is None or name not in lineage:
            have = ", ".join(lineage or {}) or "none"
            raise SelectionError(f"{step_id!r} has no lineage {name} to test "
                                 f"(its lineage: {have})")
        return list(lineage[name])

    def mask(t: dict) -> list:
        if "test" in t:
            where = condition_source(t)
            return [_cell_test(t["test"], v, t["value"], where) for v in operand(t["on"])]
        if "not" in t:
            return [not m for m in mask(t["not"])]
        parts = [mask(x) for x in (t["and"] if "and" in t else t["or"])]
        join = all if "and" in t else any
        return [join(ms) for ms in zip(*parts)]
    return mask(tree)


def _uses_lineage(tree: Any) -> bool:
    if not isinstance(tree, dict):
        return False
    if "test" in tree:
        return "row" in tree["on"]
    return any(_uses_lineage(t) for t in (tree.get("and") or tree.get("or") or [tree.get("not")]))


class _RowsIndexer:
    """``rows[…]`` selects rows; ``rows(value)`` is the old coercion to a frame."""

    def __getitem__(self, key: Any) -> Rows:
        if isinstance(key, Condition):
            # rows[condition]: these specific rows, which must exist (S5d)
            return Rows({"where": key.tree, "named": True})
        return Rows(_row_part(key, strings=True))

    def __call__(self, value: Any) -> pd.DataFrame:
        return _rows_frame(value)

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

#: ``row["r"]`` in a condition (S5c).
row = _RowIndexer()


#: Names a tool, bound tool or resource type can't take: the formula bar's own
#: vocabulary (008 C7).
RESERVED_NAMES = frozenset({"wf", "res", "mod", "rows", "cols", "row", "op", "join",
                            "stack", "zip_"})


def _reserved_problem(name: str, what: str) -> str | None:
    if name in RESERVED_NAMES:
        role = {"rows": "row selection", "cols": "column selection"}.get(
            name, "the formula language")
        return f"{name!r} is reserved for {role}; choose another {what} name"
    return None


def _check_caller_scope() -> None:
    """Refuse a declaration made where ``rows``/``cols`` mean something else.

    A script's own ``rows = [10, 20, 30]`` replaces the import, and Python
    evaluates ``rows[1:5]`` on it before core sees anything — a valid-looking,
    wrong row selection. So the names are checked in the declaring scope: the
    first frame outside this package, however many of core's own calls (a
    kernel, its change notices) are in between.
    """
    import sys
    frame = sys._getframe(1)
    while frame is not None and (frame.f_globals.get("__name__") or "").startswith(
            "simple_steps_core"):
        frame = frame.f_back
    if frame is None:
        return
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
    one_row = _is_int(ref.rows) or isinstance(ref.rows, str) or (
        isinstance(ref.rows, dict) and ref.rows.get("named") and "or" not in ref.rows["where"])
    columns = ref.columns or {}
    if columns.get("header"):
        return "column"
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
    """The column names a selection picks, in order, from *columns*.

    ``#`` (the row ids) can be named like a column; ``{"header": true}`` is
    the column names themselves, as one column called ``name``.
    """
    if sel is None:
        return list(columns)
    if isinstance(sel, dict) and sel.get("header"):
        return ["name"]
    columns = [ROW_ID, *[c for c in columns if c != ROW_ID]] if (
        (isinstance(sel, (list, tuple)) and ROW_ID in sel)
        or (isinstance(sel, dict) and (ROW_ID in (sel.get("names") or [])
                                       or ROW_ID in (sel.get("from"), sel.get("to"))))) else list(columns)
    if isinstance(sel, (list, tuple)):                  # select's plain list form
        sel = {"names": list(sel)}
    if "names" in sel:
        missing = [c for c in sel["names"] if c not in columns]
        if missing:
            raise SelectionError(
                f"{step_id!r} has no column {', '.join(map(repr, missing))} "
                f"(it has {', '.join(map(str, columns))})")
        return list(sel["names"])
    # Ranges and positions count variables only (reshaping.md §5.1, rule 1).
    columns = [c for c in columns if c == ROW_ID or not is_id_column(c)]
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
    if isinstance(col_sel, dict) and col_sel.get("header"):
        # The column names themselves (`wf["p"].header`): one per row.
        return pd.DataFrame({"name": [str(c) for c in frame.columns if not is_id_column(c)]})
    if col_sel is not None:
        wanted = _resolve_columns(list(out.columns), col_sel, step_id)
        if ROW_ID in wanted:
            out = out.assign(**{ROW_ID: list(out.index)})  # the row ids (R-D11)
        out = out[wanted]
    if isinstance(row_sel, dict) and "where" in row_sel:
        # S5c: rows a condition keeps; lineage comes with it when it tests row[…]
        lineage, owner = row_sel.get("lineage"), row_sel.get("step") or step_id
        if row_sel.get("named"):
            # named rows (a typed row number, saved as lineage): each must be there
            tree = row_sel["where"]
            for branch in (tree["or"] if "or" in tree else [tree]):
                if not any(_where(out, branch, lineage, owner)):
                    raise SelectionError(f"{step_id!r} no longer has the row "
                                         f"{condition_source(branch)}: it's gone")
        keep = _where(out, row_sel["where"], lineage, owner)
        out = out.iloc[[i for i, k in enumerate(keep) if k]]
        if not len(out):
            out.attrs["matched_nothing"] = (f"no row of {step_id!r} has "
                                            f"{condition_source(row_sel['where'])}")
        return out
    if row_sel is not None:
        n = len(out)
        if isinstance(row_sel, dict):
            # A range is positions: the first rows, as shown (owner, 2026-10-27).
            lo, hi = _bound(n, row_sel.get("start"), row_sel.get("stop"), "row", step_id)
            out = out.iloc[lo:hi]
        else:
            # A row number, or a list of them, as shown in # (S5d).
            wanted = row_sel if isinstance(row_sel, list) else [row_sel]
            missing = [i for i in wanted if not (_is_int(i) and -n <= i < n)]
            if missing:
                raise SelectionError(
                    f"{step_id!r} has no row {missing[0]!r}"
                    + (f" (it has {n}: 0–{n - 1})" if n else " (it has no rows)"))
            twice = [i % n for i in wanted]
            twice = next((i for i in twice if twice.count(i) > 1), None)
            if twice is not None:
                raise SelectionError(f"{list(wanted)} names row {twice} of {step_id!r} twice")
            out = out.iloc[list(wanted)]
    return out


@dataclass(frozen=True)
class StepRef:
    """A handle to a step, usable wherever a reference string was.

    ``wf["videos"]`` instead of ``"videos"``. It serializes to its id, so
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

    @property
    def header(self) -> "StepRef":
        """``wf["p"].header`` — the step's column names, as a value (a list).

        For a tool that works over all of a grid's columns, a schema check, or
        labels. As a step on its own, a grid with one column, ``name``.
        """
        if self.selected:
            raise SelectionError("header is the whole step's column names; "
                                 "take it from wf[…] before selecting")
        return replace(self, columns={"header": True})

    def __getitem__(self, key: Any) -> "StepRef":
        """``wf["p"][1:5]``, ``[cols["a":"c"]]``, ``[1:5, cols[…]]`` — in any order.

        A plain part is rows (an int, an int range or a list of ints, or
        ``rows[…]``); ``cols[…]`` is columns. At most one of each, in one
        bracket or two. Refused as written when it can't be a selection.
        """
        if isinstance(key, tuple) and key and all(isinstance(k, str) for k in key):
            key = Cols({"names": list(key)})          # ["ward", "n"]: several columns (D2)
        if isinstance(key, tuple) and len(key) > 1 and all(_is_int(k) for k in key):
            shown = ", ".join(str(int(k)) for k in key)
            raise SelectionError(
                f"[{shown}] is {len(key)} parts, not a list of rows: rows {shown} are "
                f"written as a list, wf[…][[{shown}]] (core-asks L49)")
        parts = key if isinstance(key, tuple) else (key,)
        if len(parts) > 2:
            raise SelectionError(
                "a selection has at most two parts: rows, then cols[…]")
        # D2: an integer is a row, a string a column (a key): wf["p"]["temp"]
        parts = tuple(Cols({"names": [p]}) if isinstance(p, str)
                      else Cols({"names": list(p)}) if isinstance(p, list) and p
                      and all(isinstance(x, str) for x in p) else p for p in parts)
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
    """StepRefs become their ids (with any selection); a tool becomes its id.

    Used for equality and reprs, where how a step or tool was *named* — a
    bound ``wf["x"]`` or ``grid.wf["x"]``, a handle or a saved ``$tool`` —
    must not matter.
    """
    if isinstance(value, StepRef):
        if value.selected:
            return f"{value.id}[rows={value.rows!r}, columns={value.columns!r}]"
        return value.id
    if isinstance(value, Tool):
        return ToolRef(value.id)
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


#: "Not known until run" — distinct from None, which is a value.
_UNKNOWN = object()


def _is_tool_value(value: Any) -> bool:
    """A tool given as a setting (008 C2): a registered tool or a reference to one."""
    return isinstance(value, (ToolRef, Tool)) or (
        callable(value) and not isinstance(value, (type, StepRef, ResRef)))


#: Settings that may hold a tool instead of column names (008 C2).
TOOL_SETTINGS: dict[str, tuple[str, ...]] = {
    "sort": ("by",), "collapse": ("by",),
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


@dataclass(frozen=True)
class ResRef:
    """A reference to a declared resource — ``res["db"]``, saved as ``{"$res": "db"}``.

    Like :class:`StepRef`, it is a name, never the object: the workflow stays
    portable and the live object is supplied at run. ``res["db"].lookup`` is
    the resource's bound tool ``lookup``, ready to decorate.
    """

    name: str

    def __getattr__(self, method: str) -> "BoundTool":
        if method.startswith("_"):
            raise AttributeError(method)
        return BoundTool(self, method)

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


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .catalog import BoundTool, Tool  # noqa: E402
from .errors import SelectionError  # noqa: E402
from .output import ROW_ID, is_id_column  # noqa: E402
from .verbs import _rows_frame  # noqa: E402
