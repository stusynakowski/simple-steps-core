"""Step: one named entry in a workflow, its operation and its output.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import hashlib
import pandas as pd


def _ran_with(operation: Any) -> dict:
    """What an output is computed with: its formula and each argument as text."""
    return {"formula": operation.to_source(),
            "arguments": {k: _src(v) for k, v in operation.arguments.items()}}


def _changes_text(changes: list[dict]) -> str:
    """``weight=1.5 (now 2.0)`` — what a stale output used, against what's set now."""
    parts = []
    for c in changes:
        if c["name"] == "formula":
            parts.append(f"{c['was']} (now {c['now']})")
        elif c.get("was_default"):
            parts.append(f"{c['name']}={c['was']}, the default (now {c['now']})")
        elif c.get("now_default"):
            parts.append(f"{c['name']}={c['was']} (now the default, {c['now']})")
        elif c["was"] is None:
            parts.append(f"{c['name']} unset (now {c['now']})")
        elif c["now"] is None:
            parts.append(f"{c['name']}={c['was']} (now unset)")
        else:
            parts.append(f"{c['name']}={c['was']} (now {c['now']})")
    return ", ".join(parts)


def _row_fps(frame: pd.DataFrame, columns: list) -> dict:
    """A short hash of each row's values in *columns*, by row id."""
    if not columns:
        return {i: "" for i in frame.index}
    try:
        hashes = pd.util.hash_pandas_object(frame[columns], index=False)
        return {i: format(int(h), "x")[:12] for i, h in zip(frame.index, hashes)}
    except TypeError:
        return {i: hashlib.sha1(repr(row).encode()).hexdigest()[:12]
                for i, row in zip(frame.index, frame[columns].itertuples(index=False))}



@dataclass(frozen=True)
class StepStatus:
    """What is live about a step: its output, its state, its problems and
    warnings, and what its values were computed with."""

    output: "Output"
    state: str
    problems: tuple = ()
    warnings: tuple = ()
    ran_with: dict = field(default_factory=dict)


class _NoLiteral:
    """The :attr:`Step.literal` of a step that wasn't declared as a literal."""

    def __repr__(self) -> str:
        return "NO_LITERAL"


NO_LITERAL = _NoLiteral()


@dataclass
class Step:
    """One node of a workflow: **an Operation and an Output**, always both.

    The Output exists from declaration (staged) and is *replaced* — never
    mutated in place — when the step runs. See docs/shape-algebra.md §8.5:
    writing a ledger row by row is 69x slower than building it once.
    """

    name: str
    operation: Operation
    output: Output
    problems: tuple[str, ...] = ()
    #: Non-blocking column expectations (005 C) — what this step predicts it
    #: will need from an upstream that has not run yet. Never stops a run.
    warnings: tuple[str, ...] = ()
    #: The app's additions, by namespace (``{"simple_steps.ui": {"color": …}}``).
    #: Saved with the step, never read by core, never a reason to re-run.
    extras: dict = field(default_factory=dict)
    #: The value a literal step was declared with (``k["x"] = [3, 1, 2]``), or
    #: :data:`NO_LITERAL`. Kept so the step's spec can save it.
    literal: Any = field(default=NO_LITERAL, repr=False, compare=False)
    #: Its id (K20): a hash of its recipe, its tool's code, the resources it
    #: uses and its inputs' ids. Set by ``k.step`` and ``k.steps``.
    id: str | None = field(default=None, repr=False, compare=False)

    @property
    def spec(self) -> "StepSpec":
        """The step's saved form: its name and operation, never its output.
        A literal step's value is its recipe, so a literal is saved."""
        saved = None
        if self.literal is not NO_LITERAL and _literal_problem(self.literal) is None:
            saved = {"value": _encode_argument(self.literal)}
        return StepSpec(self.name, self.operation.to_dict(),
                        _checked_extras(self.extras), saved)

    @property
    def valid(self) -> bool:
        return not self.problems

    @property
    def formula(self) -> str:
        """How the step is written: the value a literal step was declared
        with, or its operation's formula (``op.to_source()``). A DataFrame
        assigned in Python is data, shown as ``<DataFrame 3×2>``."""
        if self.literal is not NO_LITERAL:
            value = self.literal
            if isinstance(value, pd.DataFrame):
                return f"<DataFrame {value.shape[0]}×{value.shape[1]}>"
            return repr(value)
        return self.operation.to_source()

    @property
    def data(self) -> "pd.DataFrame":
        """The step's values: ``output.data``."""
        return self.output.data

    @property
    def status(self) -> "StepStatus":
        """The step's live part: what running its spec produced
        (docs/design/object-model.md §3). A live step is its spec plus this."""
        return StepStatus(self.output, self.state, tuple(self.problems),
                          tuple(self.warnings), self.output.ran_with)

    @property
    def state(self) -> str:
        """``staged``, ``completed``, ``stale``, ``failed`` or ``invalid``: a
        rollup of the cells' states — a step is only as done as its rows."""
        if self.problems:
            return "invalid"
        if self.output.meta.get("staged"):
            return "staged"
        states = set(self.output.row_states.astype(str))
        if "invalid" in states:
            return "invalid"
        # Ran, but an upstream changed (or re-ran) since: the data — failed
        # cells included — is outdated until it is re-run (008 C10.5: fixing a
        # root makes what it blocked stale). Nothing recomputes on its own.
        if self.output.meta.get("stale"):
            return "stale"
        if states & {"failed", "blocked"}:
            return "failed"
        return "completed"            # including a step that ran to zero rows

    @property
    def plan(self) -> dict:
        """What this step will produce — rows, columns, types — and how sure (008 C9).

        Each axis has a ``certainty``: ``exact`` (core derived it), ``stated``
        (``mod.expect``), ``bounded`` (a range, or these columns plus more) or
        ``unknown``. Anything short of exact says ``because`` and how to
        ``resolve`` it. A step that has run is exact on every axis.
        """
        inverse = self.output.meta.get("inverse")
        if not self.output.meta.get("staged"):
            data = self.output.data
            plan = {"rows": {"certainty": "exact", "count": len(data)},
                    "columns": {"certainty": "exact", "names": list(data.columns)},
                    # what was observed; a mix is the union (K27)
                    "types": {c: _observed_label(data[c]) for c in data.columns},
                    "size": {"certainty": "exact", "rows": len(data),     # K26
                             "bytes": int(data.memory_usage(deep=True).sum())}}
        else:
            plan = dict(self.output.meta.get("plan") or {})
            plan.setdefault("size", {"certainty": "unknown", "because":
                                     f"{self.name} hasn't run: its size is known when it does",
                                     "resolve": [f"run {self.name!r}"]})
        if inverse is not None:
            plan["inverse"] = inverse             # how to go back (reshaping.md §7)
        return plan

    def describe(self) -> str:
        """What this step is, in words — and, for ``auto``, which verb it picked."""
        text = self._describe()
        picked = self.output.meta.get("auto")
        if picked and self.valid:
            when = "for now" if picked.get("provisional") else "from the data"
            text += f" (auto, {when}: {picked['reason']})"
        return text

    def _describe(self) -> str:
        """What this step is, in words.

        Two different questions, and they must not be blurred: a **staged**
        step reports what staging can *promise* (§7's three levels), while a
        step that has run reports what it actually *holds*. Only the first is a
        prediction.
        """
        if not self.valid:
            return f"invalid · {self.problems[0]}"
        if is_combine(self.operation):
            kind = self.operation.tool
            if not self.output.meta.get("staged"):
                n = len(self.output.data)
                return f"{kind} · {n} cell{'' if n == 1 else 's'}"
            expected = self.output.meta.get("expected")
            if expected is not None:
                return f"{kind} · {expected} cells"
            return f"{kind} · unknown count from {len(self.operation.inputs)} grids"
        verb = self.output.meta.get("verb")
        tool = self.operation.tool
        if verb in ("source", "table") and self.output.meta.get("staged"):
            return f"{verb} {tool} · {_plan_words(self.plan)}"
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
        return f"<Step {self.name!r} {self.state} · {self.describe()}>"


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .catalog import _checked_extras  # noqa: E402
from .combines import is_combine  # noqa: E402
from .operation import Operation, _src  # noqa: E402
from .output import Output, _plan_words  # noqa: E402
from .specs import StepSpec  # noqa: E402
from .values import _dtype_type, _encode_argument, _literal_problem, _type_label  # noqa: E402


def _observed_label(series: "pd.Series") -> str:
    """A column's observed type; ``unknown`` when there's nothing to observe."""
    observed = _dtype_type(series)
    return "unknown" if observed is None and not len(series.dropna()) else _type_label(observed)
