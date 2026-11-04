"""Workflow: the ordered steps and the resources they use.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any
from typing import Callable
from typing import Sequence
import hashlib
import inspect
import json
import re
import typing

import pandas as pd


_GONE = object()          # a picked row that is gone (D-picks)


def _name_problem(name: Any) -> str | None:
    """Why *name* can't name a step (core-asks L47), or None. A `.` separates
    a lineage column's parts (`#r.2`) and `#` starts core's own columns."""
    if not isinstance(name, str) or not name:
        return f"a step name must be a non-empty string, got {name!r}"
    if "." in name:
        return (f"a step name can't contain '.', which separates a lineage column's "
                f"parts (#r.2): write {name.replace('.', '_')!r}")
    if name.startswith("#"):
        return f"a step name can't start with '#', which starts core's row columns: write {name.lstrip('#')!r}"
    return None


class Workflow:
    """Ordered Steps. Assign an Operation, get a Step that is already staged.

    ``wf["scored"] = score[mod.map()](wf["videos"])`` — declaring stages;
    ``wf.run("scored")`` is what actually computes.
    """

    def __init__(self, catalog: "Catalog | None" = None, naming: Any = None) -> None:
        self.steps: dict[str, Step] = {}
        #: Declared resources, by name — the declarations, never the objects.
        self.resources: dict[str, Resource] = {}
        #: What this workflow may use. With a catalog, every step is checked
        #: against it and runs the catalog's functions; without one, the
        #: process-wide registry is used (until phase 3 removes it).
        self.catalog = catalog
        #: The app's additions to the workflow, by namespace. Saved, never read.
        self.extras: dict = {}
        #: The data version each resource last reported (K25), by name: asked
        #: of resources whose type defines ``data_version()``, before a run.
        self.data_versions: dict[str, str] = {}
        #: The kernel's naming conventions (outputs-and-reshaping.md §10), or None.
        self.naming = naming
        #: Every result kept, by run key (ST7): this step, this code, on this
        #: data. Results are never changed once filed (A9).
        self.store: dict[str, Output] = {}
        #: Each step's keys in the store, oldest first; the last is its newest.
        self.kept: dict[str, list[str]] = {}
        #: The plan of each step with a new, unrun expression (PL), with what
        #: it was made from; made again when any of that is another object.
        self._plans: dict[str, tuple] = {}
        #: Each step whose picked row of a source is gone (D-picks): why. It
        #: is a problem on the step until the step is given a new expression.
        self._gone: dict[str, str] = {}

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
        if self.catalog is not None \
                and self.catalog.resource_types.get(type_.__name__) is not type_:
            raise ValueError(
                f"cannot define resource {name!r}: {type_.__name__} is not in this "
                "workflow's catalog. Add it: Catalog(resources=[...])")
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
        self.resources[name] = Resource(name, type_, dict(settings),
                                            type_.__name__)
        self._recheck_users(name, stale=existed)
        self._refresh_staleness()
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
                st.output = stage(operation, self, problems, sid)
                st.warnings = warn(operation, self, sid)
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
    @staticmethod
    def _literal_step(step_id: str, value: Any, extras: dict) -> Step:
        """A step declared as a value: a source whose data is its output,
        completed as soon as it exists. ``None`` declares an **empty step**
        (G17, the project rule): a step with no expression yet, a 1×1 grid
        holding ``"empty"``, staged, that nothing can read until it has one."""
        if value is None:
            plan = {"rows": {"certainty": "exact", "count": 1},
                    "columns": {"certainty": "exact", "names": [VALUE_COLUMN]}, "types": {},
                    "inverse": {"kind": "generated"}}
            empty = Output(pd.DataFrame({VALUE_COLUMN: ["empty"]}, index=[0]),
                           meta={"staged": True, "empty": True, "plan": plan,
                                 "inverse": {"kind": "generated"}})
            return Step(step_id, Operation(tool="identity", fn=identity)[mod.source()],
                        empty, extras=extras, literal=None)
        step = Step(step_id, Operation(tool="identity", fn=identity)[mod.source()],
                    source_(value), extras=extras, literal=value)
        step.output.meta["version"] = _data_version(step.output.data)
        step.output.meta["read"] = {}
        step.output.meta["inverse"] = {"kind": "generated"}
        return step

    def _keep_row_ids(self, step_id: str, before: Output) -> None:
        """Give a source's rows the ids they had before its data was replaced
        (D-picks): a row whose values it has seen takes that row's id back,
        duplicates in order, even a row seen earlier and gone since (undo is
        free); rows left over on both sides, as many each, are values edited in
        place and keep their ids, in order (C25); any other row gets an id never
        used. Then each pick of a row number into it follows its row. Only a
        source with core's ids, a default 0…n-1 index: an index of its own is
        the user's identity."""
        out = self.steps[step_id].output
        data = out.data
        if out.meta.get("empty") or before.meta.get("staged") or before.meta.get("empty"):
            return
        old = before.data
        if not isinstance(data.index, pd.RangeIndex) or data.index.start != 0 \
                or data.index.step != 1 or not pd.api.types.is_integer_dtype(old.index):
            self._follow_rows(step_id, old, data)       # an index of its own: by its labels
            return
        columns = list(data.columns)
        memory = before.meta.get("rows_seen") or {}
        if memory.get("columns") != columns:
            memory = {"columns": columns, "ids": {}}        # other columns: start again
        known: dict = {}                               # hash -> ids: shown now, then seen before
        if list(old.columns) == columns:
            for row_id, h in zip(old.index, _row_fps(old, columns).to_numpy()):
                known.setdefault(int(h), []).append(_plain(row_id))
                seen = memory["ids"].setdefault(int(h), [])
                if _plain(row_id) not in seen:      # remembered, so it can come back
                    seen.append(_plain(row_id))
        for h, ids_ in memory["ids"].items():
            known.setdefault(int(h), []).extend(i for i in ids_ if i not in old.index)
        hashes = [int(h) for h in _row_fps(data, columns).to_numpy()] if columns else [0] * len(data)
        ids: list = [known[h].pop(0) if known.get(h) else None for h in hashes]
        same = {i for i in ids if i is not None}         # rows it has seen, values unchanged
        left = [_plain(i) for i in old.index if _plain(i) not in same]
        if left and len(left) == ids.count(None):     # values edited in place: picks follow (L41a)
            ids = [left.pop(0) if i is None else i for i in ids]
            same = set(ids)
        fresh = before.meta.get("next_row_id", max(old.index, default=-1) + 1)
        for n, i in enumerate(ids):
            if i is None:
                ids[n], fresh = fresh, fresh + 1
        if ids != list(range(len(data))):
            data.index = pd.Index(ids, dtype="int64")
            out.states.index = data.index
        for h, i in zip(hashes, ids):
            seen = memory["ids"].setdefault(h, [])
            if i not in seen:
                seen.append(i)
        out.meta["rows_seen"] = memory
        out.meta["next_row_id"] = fresh               # never given again, even after a delete
        out.meta["version"] = _data_version(data)
        self._follow_rows(step_id, old, data, same)

    def _follow_rows(self, source: str, old: pd.DataFrame, new: pd.DataFrame,
                     same: set | None = None) -> None:
        """*source* shows *new* where it showed *old*: each row number a step
        names into it follows its row, by id (D-picks), however the rows came:
        data assigned, its tool run again, or a result back from the store (an
        undo). *same*: the ids whose rows are unchanged, if not every id kept."""
        if old.index.equals(new.index) or \
                pd.api.types.is_integer_dtype(old.index) != pd.api.types.is_integer_dtype(new.index):
            # the same rows; or core's ids against labels of the user's own,
            # which can't be compared: picks stay as written (W3)
            if self._gone:
                self._restore_picks(source)
            return
        after = new.index

        def number(n: int) -> Any:                     # its row number before -> now
            row_id = _plain(old.index[n])
            kept = row_id in after if same is None else row_id in same
            return after.get_loc(row_id) if kept else _GONE
        self._follow_picks(source, len(old), number, old)
        if self._gone:
            self._restore_picks(source)

    def _restore_picks(self, source: str) -> None:
        """A pick whose row of *source* is back (an undo, or the row given
        again) follows it once more, and is checked again (D-picks)."""
        out = self.steps[source].output
        if out.meta.get("staged"):
            return
        after = out.data.index
        for sid, note in list(self._gone.items()):
            if note["source"] != source or not all(i in after for i in note["lost"].values()):
                continue
            del self._gone[sid]
            lost = note["lost"]
            self._follow_picks(source, None, lambda n: after.get_loc(lost[n]) if n in lost else n,
                               out.data, only=sid)
            st = self.steps[sid]
            st.problems = check(st.operation, self, sid)
            st.warnings = warn(st.operation, self, sid)
            self._restage_after(sid)            # what read it, invalid through it, too

    def _follow_picks(self, source: str, count: int | None, number: Callable,
                      shown: pd.DataFrame, only: str | None = None) -> None:
        """Rewrite each row number of *source* a step names with *number*: its
        row's number now (D-picks), for a pick straight into it
        (``wf["p"][1]``) and a pick core saved as its rows' lineage anywhere
        later (``rows[row["p"] == 1]``). A row that is gone (deleted, or edited while rows
        were added or deleted too, so it can't be told apart) can't be written:
        the step is ``invalid``, naming it, until it is given a new pick or the
        row comes back. A negative number, a range or a comparison picks
        positions, and stays as written. *count* bounds the numbers (None: any)."""
        def one(n: Any) -> Any:
            if not (isinstance(n, int) and not isinstance(n, bool) and n >= 0
                    and (count is None or n < count)):
                return n
            return number(n)

        gone: list = []

        def numbers(value: Any) -> Any:
            ints = value if isinstance(value, list) else [value]
            now = [one(v) for v in ints]
            gone.extend(v for v, w in zip(ints, now) if w is _GONE)
            if _GONE in now or now == ints:
                return value
            return now if isinstance(value, list) else now[0]

        def follow(value: Any, direct: bool, picked: bool = False) -> Any:
            # *picked*: inside a pick core saved as its rows' lineage (`named`),
            # which names rows; a condition someone wrote tests positions
            if direct and (isinstance(value, int) and not isinstance(value, bool)
                           or isinstance(value, list) and value
                           and all(isinstance(v, int) and not isinstance(v, bool) for v in value)):
                return numbers(value)
            if isinstance(value, dict):
                on = value.get("on")
                if picked and isinstance(on, dict) and on.get("row") == source \
                        and not on.get("idx") and value.get("test") in ("==", "in"):
                    now = numbers(value.get("value"))
                    return value if now is value.get("value") else {**value, "value": now}
                inner = picked or value.get("named") is True
                out = {k: follow(v, False, inner) for k, v in value.items()}
                return value if all(out[k] is value[k] for k in value) else out
            if isinstance(value, (list, tuple)):
                out = [follow(v, False, picked) for v in value]
                return value if all(a is b for a, b in zip(out, value)) else type(value)(out)
            return value

        touched: list = []
        for sid, st in self.steps.items():
            if sid == source or (only is not None and sid != only):
                continue
            if only is None and (self._gone.get(sid) or {}).get("source") == source:
                continue          # its numbers name rows of the data it lost them in
            op_ = st.operation
            gone.clear()
            modifiers = []
            for m in op_.modifiers:
                direct = m.kind == "select" and op_.input is not None and str(op_.input) == source
                settings = {k: follow(v, direct and k == "rows") for k, v in m.settings.items()}
                modifiers.append(m if all(settings[k] is m.settings[k] for k in settings)
                                 else Modifier(m.kind, settings))
            arguments = {}
            for name, value in op_.arguments.items():
                if isinstance(value, StepRef) and value.rows is not None:
                    rows_ = follow(value.rows, value.id == source)
                    value = value if rows_ is value.rows else replace(value, rows=rows_)
                arguments[name] = value
            if any(a is not b for a, b in zip(modifiers, op_.modifiers)) \
                    or any(arguments[k] is not op_.arguments[k] for k in arguments):
                st.operation = replace(op_, modifiers=tuple(modifiers), arguments=arguments)
                touched.append(sid)
            if gone:
                touched.append(sid)
                rows_ = sorted(set(gone))
                was = "; ".join(", ".join(f"{c}={_plain(v)!r}" for c, v in shown.iloc[n].items())
                                for n in rows_[:3])
                self._gone[sid] = {
                    "source": source,
                    "lost": {n: _plain(shown.index[n]) for n in rows_},
                    "text": (f"{source!r} row {', '.join(map(str, rows_))} is gone "
                             f"(it was {was}): deleted, or edited while rows were "
                             f"added or deleted. Pick the row again")}
        # checked again here: a step may name the source's rows without reading
        # it any more, so no re-check after the source would reach it
        for sid in dict.fromkeys(touched):
            st = self.steps[sid]
            before = st.problems
            st.problems = check(st.operation, self, sid)
            st.warnings = warn(st.operation, self, sid)
            if st.problems != before:
                self._restage_after(sid)        # what reads it hears it too

    def _as_operation(self, operation: Any) -> Any:
        """What declaring *operation* means, before it is checked: a selection
        becomes a select step, a bare shape verb gets its default tool. Anything
        else is returned as it is (an Operation, or a literal value)."""
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
            operation = Operation(tool="identity", fn=identity)[
                mod.select(**selection)](replace(operation, rows=None, columns=None))
        if isinstance(operation, Modifier):
            # A modifier alone is not a step: it has no input (over= is
            # retired, EX3), and it used to run on nothing, a `map` giving
            # [None] and a `filter` zero rows, both `completed`. Execution
            # modifiers and sweeps say why they need a tool.
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
            kind = operation.kind
            how = (f"<tool>[mod.{kind}(…)](wf[\"…\"])" if kind in ("map", "filter", "group")
                   else f"<tool>[mod.source()]()" if kind == "source"
                   else f"mod.{kind}(…)(wf[\"…\"])")
            raise TypeError(f"mod.{kind}(…) on its own is not a step: it has no "
                            f"{'tool' if kind == 'source' else 'input'}. Write {how}")

        return operation

    def __setitem__(self, step_id: str, operation: Any) -> None:
        _check_caller_scope()
        existed = step_id in self.steps
        if not existed and _name_problem(step_id):
            raise ValueError(_name_problem(step_id))
        # The app's additions stay with the step when it is re-declared.
        kept_extras = self.steps[step_id].extras if existed else {}
        operation = self._as_operation(operation)
        if not isinstance(operation, Operation):
            # A bare value is a source step, and a source step's data **is its
            # output** — it arrived with the declaration, so there is nothing
            # to stage and nothing to compute. It is born completed. This is
            # why a Workflow is only a list of Steps: literals have no separate
            # home, because they were never anything but a step's output.
            was_empty = existed and self.steps[step_id].output.meta.get("empty")
            before = self.steps[step_id].output if existed else None
            self.steps[step_id] = self._literal_step(step_id, operation, kept_extras)
            if before is not None:
                self._keep_row_ids(step_id, before)          # D-picks
            self._file(step_id)
            if existed:
                self._mark_stale_dependents(step_id)
                self._recheck_downstream(step_id)
                # new data, as after a run: readers not yet run are planned
                # again on it, so what they decide doesn't hang on the order
                # of the edits before (L40e)
                self._restage_after(step_id)
            if not existed or was_empty or self.steps[step_id].output.meta.get("empty"):
                self._recheck_readers(step_id)    # an empty step written, or emptied (G17)
            return
        operation = _attach_bound(operation, self.resources)
        if self.catalog is not None:
            operation = self.catalog.admit(operation)
        operation = self._resolve_picks(operation)       # S5d: row numbers saved as lineage
        operation = bind_by_type(operation, self, step_id)   # S3: the binding, written
        self._gone.pop(step_id, None)                    # a new pick (D-picks)
        problems = check(operation, self, step_id)
        previous = self.steps.get(step_id)
        was_empty = previous is not None and previous.output.meta.get("empty")
        staged = stage(operation, self, problems, step_id)
        output = staged
        if previous is not None and not previous.output.meta.get("staged"):
            if previous.operation == operation:
                output = previous.output            # same formula: nothing changed
            else:
                # 009: an edited step keeps its old output, shown as
                # "stale output (updated args)" until it re-runs. The new
                # formula is still checked; its plan is kept for display.
                output = Output(previous.output.data, previous.output.states,
                                {**previous.output.meta, "edited": True,
                                 "next_plan": staged.meta.get("plan")})
        output.meta["inverse"] = self.inverse(step_id, operation)
        self.steps[step_id] = Step(step_id, operation, output, problems,
                                   warn(operation, self, step_id), kept_extras)
        cased = self._case_problems(step_id, staged)
        if cased:
            step_ = self.steps[step_id]
            severity = "error" if getattr(self.catalog, "strict", False) else "warning"
            found = tuple(Problem(c, "naming_case", step=step_id, severity=severity) for c in cased)
            if severity == "error":
                step_.problems = tuple(step_.problems) + found
            else:
                step_.warnings = tuple(step_.warnings) + found
        if existed:
            self._mark_stale_dependents(step_id)
            self._recheck_downstream(step_id)
            # its readers are checked against its new plan (PL), and a reader
            # not yet run is planned again on it, whatever the order of edits
            self._restage_after(step_id)
            # What reads this step may need what its new formula won't give.
            for sid, st in self.steps.items():
                if step_id in st.operation.reads:
                    st.warnings = warn(st.operation, self, sid)
            if was_empty:
                self._recheck_readers(step_id)    # an empty step got its expression (G17)
        else:
            self._recheck_readers(step_id)

    def check(self, step_id: str, operation: Any) -> tuple:
        """The problems *operation* would have as step *step_id*, without
        declaring it: nothing in the workflow changes. A literal value has none."""
        operation = self._as_operation(operation)
        if not isinstance(operation, Operation):
            return ()
        operation = _attach_bound(operation, self.resources)
        if self.catalog is not None:
            operation = self.catalog.admit(operation)
        return check(bind_by_type(operation, self, step_id), self, step_id)

    def move(self, step_id: str, index: int) -> None:
        """Move step *step_id* to position *index* (a position in the new
        order; negative counts from the end).

        Refused when a step that is valid now would read a step after it. A
        move that fixes an order is allowed, and every step is re-checked.
        """
        names = list(self.steps)
        if step_id not in self.steps:
            raise KeyError(f"no step {step_id!r}")
        if not -len(names) <= index < len(names):
            raise IndexError(f"no position {index}: the workflow has {len(names)} steps")
        names.remove(step_id)
        names.insert(index % (len(names) + 1), step_id)
        position = {n: i for i, n in enumerate(names)}
        for name in names:
            st = self.steps[name]
            if not st.valid:
                continue
            for read in st.operation.reads:
                if read in position and position[read] > position[name]:
                    raise ValueError(
                        f"cannot move {step_id!r} to position {index}: {name!r} "
                        f"reads {read!r}, which would come after it")
        self.steps = {n: self.steps[n] for n in names}
        for sid, st in self.steps.items():
            problems = check(st.operation, self, sid)
            if problems != st.problems:
                st.problems = problems
                st.output = stage(st.operation, self, problems, sid)
                st.warnings = warn(st.operation, self, sid)

    def insert(self, index: int, step_id: str, operation: Any) -> None:
        """Declare a new step *step_id* at position *index*."""
        if step_id in self.steps:
            raise ValueError(f"step {step_id!r} already exists: assign to "
                             "replace it, or move it")
        position = index if index >= 0 else len(self.steps) + 1 + index
        if not 0 <= position <= len(self.steps):
            raise IndexError(f"no position {index}: the workflow has {len(self.steps)} steps")
        before = set(list(self.steps)[:position])
        found = self._as_operation(operation)
        reads = found.reads if isinstance(found, Operation) else []
        after = [r for r in reads if r in self.steps and r not in before]
        if after:
            raise ValueError(f"cannot insert {step_id!r} at position {index}: it "
                             f"reads {after[0]!r}, which would come after it")
        self[step_id] = operation
        if position < len(self.steps) - 1:
            self.move(step_id, position)

    def _recheck_readers(self, step_id: str) -> None:
        """Re-check earlier steps that named *step_id* before it existed.

        008 C10: their "not an earlier step" becomes "comes after", which says
        what to fix — reorder, don't create.
        """
        moved = False
        for sid, st in self.steps.items():
            if sid == step_id or step_id not in st.operation.reads:
                continue
            problems = check(st.operation, self, sid)
            if problems != st.problems:
                st.problems = problems
                st.output = stage(st.operation, self, problems, sid)
                st.warnings = warn(st.operation, self, sid)
                moved = True
        if moved:
            self._refresh_staleness()           # settles: what the store holds comes back

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
        """Steps that read *step_id* — as input, as a reference argument, or as
        the step a ``collapse(by="#s")`` groups by."""
        return [sid for sid in self.steps if step_id in self._depends_on(sid)]

    def _recheck_downstream(self, step_id: str) -> None:
        """Re-check, in workflow order, every step that depends on *step_id*,
        directly or not, after it changed (M7 rule 3): a step invalid because
        of what it read is re-decided, and one whose input became invalid is
        invalid, saying which. Nothing runs; a step whose problems are the same
        keeps its output."""
        changed, moved = {step_id}, False
        for sid, st in self.steps.items():
            if sid in changed or not changed & set(self._depends_on(sid)):
                continue
            changed.add(sid)
            problems = check(st.operation, self, sid)
            if problems != st.problems:
                st.problems = problems
                st.output = stage(st.operation, self, problems, sid)
                st.warnings = warn(st.operation, self, sid)
                moved = True
        if moved:
            self._refresh_staleness()           # settles: what the store holds comes back

    def __delitem__(self, step_id: str) -> None:
        self.remove(step_id)

    def remove(self, step_id: str, *, force: bool = False) -> None:
        """Delete a step, refusing when later steps still read it.

        The error names the readers so an editor can show exactly what breaks;
        remove or rename them first. ``force=True`` deletes it anyway: each
        reader is then ``invalid``, naming it (SS7).
        """
        if step_id not in self.steps:
            raise KeyError(f"no step {step_id!r}; have {list(self.steps)}")
        readers = self._dependents(step_id)
        if readers and force:
            del self.steps[step_id]
            self._gone.pop(step_id, None)
            for key in self.kept.pop(step_id, []):
                self.store.pop(key, None)
            self._recheck_readers(step_id)          # "… which is not an earlier step"
            self._recheck_downstream(readers[0])
            for reader in readers[1:]:
                self._recheck_downstream(reader)
            self._refresh_staleness()
            return
        if readers:
            raise ValueError(
                f"cannot remove {step_id!r}: {', '.join(map(repr, readers))} "
                f"read it. Remove or rename {'it' if len(readers) == 1 else 'them'} "
                "first."
            )
        del self.steps[step_id]
        self._gone.pop(step_id, None)
        for key in self.kept.pop(step_id, []):
            self.store.pop(key, None)

    def rename(self, old: str, new: str) -> None:
        """Rename a step, rewriting every reference that pointed at it.

        Outputs are kept — a rename is not a recompute — and insertion order is
        preserved so positions do not shift.
        """
        if old not in self.steps:
            raise KeyError(f"no step {old!r}; have {list(self.steps)}")
        if _name_problem(new):
            raise ValueError(_name_problem(new))
        if new == old:
            return
        if new in self.steps:
            raise ValueError(f"step {new!r} already exists")
        carriers = self._carrying_own_column(old)        # D9: its column is named old
        self.steps = {(new if sid == old else sid): st
                      for sid, st in self.steps.items()}
        self.steps[new].name = new
        if old in self.kept:                  # its results; their keys follow in SM
            self.kept[new] = self.kept.pop(old)
        if old in self._gone:
            self._gone[new] = self._gone.pop(old)
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
                for key, value in m.settings.items():
                    if isinstance(value, StepRef) and str(value) == old:
                        params[key], changed = replace(value, id=new, workflow=self), True
                    else:
                        params[key] = value
                new_mods.append(Modifier(m.kind, params))
            if changed:
                st.operation = Operation(op.tool, tuple(new_mods), new_args,
                                         op.fn, new_input, bound_to=op.bound_to)
        if carriers:
            self._rename_own_column(new, old, {new if c == old else c for c in carriers})

    def _carrying_own_column(self, step_id: str) -> set[str]:
        """*step_id* and the steps after it that carry its column unchanged,
        when that column is named after it (D9); empty when it isn't."""
        st = self.steps[step_id]
        out = st.output
        if out.meta.get("staged") or out.meta.get("value_column") != step_id \
                or step_id not in out.data.columns or st.operation.name_rule is not None:
            return set()
        carriers = {step_id}
        for sid, other in self.steps.items():
            op_ = other.operation
            if sid in carriers or op_.input is None or str(op_.input) not in carriers:
                continue
            if step_id in predicted_columns(other.output) \
                    and other.output.meta.get("value_column") != step_id:
                carriers.add(sid)
        return carriers

    def _rename_own_column(self, step_id: str, old: str, carriers: set[str]) -> None:
        """A step renamed from *old*: the column it named after itself takes its
        new name, with no re-run (a copy, filed under its new key: a filed
        result never changes), and every step that names that column, reading
        it from *step_id* or a step that carries it, names it so too (D9,
        core-asks L23). Steps that carry it hold it under *old* until they
        re-run, so they show stale."""
        st = self.steps[step_id]
        out = st.output
        copy = Output(out.data.rename(columns={old: step_id}),
                      out.states.rename(columns={old: step_id}),
                      {k: v for k, v in out.meta.items() if k not in ("run_key", "version")})
        copy.meta["value_column"] = step_id
        copy.meta["version"] = _data_version(copy.data)
        st.output = copy
        self._file(step_id)

        def renamed(value: Any) -> Any:
            if isinstance(value, str):
                return step_id if value == old else value
            if isinstance(value, list):
                return [renamed(v) for v in value]
            if isinstance(value, tuple):
                return tuple(renamed(v) for v in value)
            if isinstance(value, dict):
                out_ = {renamed(k) if isinstance(k, str) else k: v for k, v in value.items()}
                if "col" in out_:
                    out_["col"] = renamed(out_["col"])
                for key in ("names", "on", "and", "or", "not", "where", "test"):
                    if key in out_ and not isinstance(out_[key], str):
                        out_[key] = renamed(out_[key])
                return out_
            return value

        for sid, other in self.steps.items():
            if sid == step_id:
                continue
            op_ = other.operation
            changed = False
            modifiers = op_.modifiers
            if op_.input is not None and str(op_.input) in carriers:
                modifiers = tuple(Modifier(m.kind, {k: renamed(v) if k != "name" else v
                                                    for k, v in m.settings.items()})
                                  for m in op_.modifiers)
                changed = modifiers != op_.modifiers
            arguments = {}
            for key, value in op_.arguments.items():
                if isinstance(value, StepRef) and value.id in carriers \
                        and (value.columns is not None or value.rows is not None):
                    moved = replace(value, columns=renamed(value.columns), rows=renamed(value.rows))
                    changed = changed or moved != value
                    value = moved
                arguments[key] = value
            if changed:
                other.operation = replace(op_, modifiers=modifiers, arguments=arguments)
            if sid in carriers and not other.output.meta.get("staged"):
                # it shows the column under its old name: what reads it is
                # checked against what it will produce once it re-runs (PL)
                other.output.meta["edited"] = True
        self._mark_stale_dependents(step_id)
        self._recheck_downstream(step_id)
        self._restage_after(step_id)

    def _mark_stale_dependents(self, step_id: str) -> None:
        """Re-decide staleness after *step_id* changed (009 §5–§6).

        Changing an upstream recomputes nothing (§7's push/pull), but a step
        that ran may now hold outdated data — ``status`` says ``stale`` until it
        is re-run. A step with ``read`` stamps is stale when a step it read has
        a different version now (its data really changed), or is stale itself.
        An output saved before stamps existed keeps the old rule: any change
        upstream marks it stale.
        """
        frontier, seen = [step_id], set()
        while frontier:
            for sid in self._dependents(frontier.pop()):
                if sid in seen:
                    continue
                seen.add(sid)
                output = self.steps[sid].output
                if not output.meta.get("staged") and "read" not in output.meta:
                    output.meta["stale"] = True
                frontier.append(sid)
        self._refresh_staleness()

    def version(self, step_id: str) -> str | None:
        """The version of *step_id*'s data — a hash; None until it holds data."""
        step = self.steps.get(step_id)
        if step is None or step.output.meta.get("staged"):
            return None
        if "version" not in step.output.meta:
            step.output.meta["version"] = _data_version(step.output.data)
        return step.output.meta["version"]

    def _resource_version(self, name: str, data: bool = True) -> str | None:
        """Its spec (never its secrets or extras), its type's code, and the data
        version it last reported (K25): a change in any makes its users stale."""
        decl = self.resources.get(name)
        if decl is None:
            return None
        spec = {k: v for k, v in decl.to_dict().items() if k != "extras"}
        if self.catalog is not None:
            spec["code"] = self.catalog.type_hash(decl.type_name)
        if data and name in self.data_versions:
            spec["data"] = self.data_versions[name]
        return hashlib.sha1(json.dumps(spec, sort_keys=True,
                                       default=repr).encode()).hexdigest()[:12]

    # ── identity (K20) ───────────────────────────────────────────────
    def identity(self) -> dict[str, dict]:
        """What each step is made of, for its id: ``{name: {"recipe", "tool",
        "resources", "inputs", "id"}}``, in order. Extras are never in it.

        ``recipe`` hashes the step's operation (or literal); ``tool`` is its
        tool's code hash; ``resources`` the specs of those it uses, never their
        secrets; ``inputs`` the ids of the steps it reads, so a step's id
        changes when anything upstream of it does.
        """
        out: dict[str, dict] = {}
        for name, st in self.steps.items():
            try:
                parts = self._own_parts(st)
            except Exception as error:
                # A step that can't be saved (a lambda) can't be reproduced: no
                # id, for it or for anything that reads it.
                out[name] = {"id": None, "why": str(error)}
                continue
            upstream = [r for r in st.operation.reads if r in out and out[r]["id"] is None]
            if upstream:
                out[name] = {"id": None, "why": f"it reads {upstream[0]!r}, which has no id"}
                continue
            parts["inputs"] = {r: out[r]["id"] if r in out else None
                               for r in sorted(st.operation.reads)}
            parts["id"] = _short_hash(parts)
            out[name] = parts
        return out

    def _own_parts(self, st: Step) -> dict:
        """What a step is made of by itself: its recipe (operation, or literal),
        its tool's code and its resources' specs. Raises when it can't be saved."""
        recipe = {"operation": st.operation.to_dict()}
        if st.literal is not NO_LITERAL and _literal_problem(st.literal) is None:
            recipe["literal"] = _encode_argument(st.literal)
        return {"recipe": _short_hash(recipe),
                "tool": self._tool_hash(st.operation),
                "resources": {r: self._resource_version(r, data=False)
                              for r in sorted(st.operation.resources)}}

    def _run_reads(self, step_id: str) -> dict:
        """The versions of all a run of *step_id* reads, now: its inputs,
        references and resources, and the step a ``collapse(by="#s")``
        groups by. A run stamps these; :meth:`run_key` is made of the same."""
        read = self._read_stamps(self.steps[step_id].operation)
        grouped = self._groups_by_step(step_id)
        if grouped is not None and grouped[1] in self.steps:
            read.setdefault(grouped[1], self.version(grouped[1]))   # collapse(by="#s") reads s
        return read

    def run_key(self, step_id: str, read: dict | None = None) -> str | None:
        """The key a result of *step_id* is filed under (ST2): this step, with
        this tool code and these resources, on exactly this data. Its name,
        its own parts (:meth:`_own_parts`) and the data version of each step
        and resource it reads: the stamps a run records, or now's. Another
        recipe upstream that gives the same data gives the same key. None
        when it can't be saved, or reads something that holds no data."""
        st = self.steps[step_id]
        try:
            parts = self._own_parts(st)
        except Exception:
            return None
        read = self._run_reads(step_id) if read is None else read
        if any(v is None for v in read.values()):
            return None
        if st.literal is not NO_LITERAL:
            # A value's data is its recipe: a DataFrame isn't in the recipe
            # hash (it's data, not saved), so two would share a key.
            parts["data"] = self.version(step_id)
        return _short_hash({"name": step_id, **parts, "read": dict(sorted(read.items()))})

    #: How many results the store keeps for each step: its newest and the ones
    #: before it (ST7). Dropping one only costs a re-run, never a wrong answer.
    KEEP = 4

    def _file(self, step_id: str) -> None:
        """File *step_id*'s result in the store under its run key."""
        output = self.steps[step_id].output
        if output.meta.get("staged"):
            return
        key = output.meta.get("run_key") or self.run_key(step_id)
        if key is None:
            return
        output.meta["run_key"] = key
        self.store[key] = output
        keys = [k for k in self.kept.get(step_id, []) if k != key] + [key]
        while len(keys) > self.KEEP:
            self.store.pop(keys.pop(0), None)
        self.kept[step_id] = keys

    def results(self, step_id: str) -> list[Output]:
        """The results the store keeps for *step_id*, newest first."""
        return [self.store[k] for k in reversed(self.kept.get(step_id, [])) if k in self.store]

    def recipe_id(self) -> str:
        """The workflow's id: its steps' ids, its resources and its naming."""
        ids = self.identity()
        missing = [(n, p["why"]) for n, p in ids.items() if p["id"] is None]
        if missing:
            raise PayloadError(f"step {missing[0][0]!r} has no id: {missing[0][1]}")
        return _short_hash({
            "steps": [[n, p["id"]] for n, p in ids.items()],
            "resources": {r: self._resource_version(r, data=False) for r in sorted(self.resources)},
            "naming": self.naming.to_dict() if self.naming is not None else None})

    @staticmethod
    def _source_records(step: Step) -> str | None:
        """A source tool that declares records (``-> LoHi``, ``-> list[LoHi]``)
        gives a row per record, a column per field (outputs-and-reshaping.md
        §3). Returns why when what it returned doesn't fit; None otherwise.
        ``mod.name`` keeps the value in one cell, and a failed or caught call
        is left as it is."""
        output = step.output
        if step.operation.naming is not None or source_record(step.operation.fn) is None:
            return None
        column = output.meta.get("value_column") or VALUE_COLUMN
        if len(output.failed) or output.meta.get("notes") or column not in output.data.columns \
                or len(output.data) != 1:
            return None
        try:
            frame = source_rows(step.operation.fn, output.data[column].iloc[0])
        except ValueError as exc:
            return f"{step.operation.tool} {exc}"
        step.output = grid(frame)
        step.output.meta["verb"] = "source"
        return None

    def _ask_data_versions(self, operation: Operation,
                           resources: Mapping[str, Any] | None) -> None:
        """K25: ask the resources *operation* uses for their data version, just
        before it runs (building them, as the run would). One that can't be
        built is left to the run to report."""
        from .catalog import data_version
        for name in operation.resources:
            try:
                obj = resources[name] if resources is not None else None
            except Exception:
                continue
            version = data_version(obj) if obj is not None else None
            if version is not None:
                self.data_versions[name] = version

    def _tool_hash(self, operation: Operation) -> str | None:
        """The hash of the tool *operation* runs, from the catalog (K20)."""
        if self.catalog is None or is_identity(operation.fn):
            return None
        return self.catalog.hash_of(operation.tool)

    def _read_stamps(self, operation: Operation) -> dict:
        """The versions of everything *operation* reads, as of now."""
        stamps: dict = {name: self.version(name) for name in operation.reads}
        for name in operation.resources:
            stamps[f"res:{name}"] = self._resource_version(name)
        return stamps

    def _row_reads(self, step: Step) -> dict | None:
        """``{"step", "columns", "fp": a uint64 hash a row, by row id}`` for a row-aligned step."""
        op_ = step.operation
        if is_combine(op_) or op_.input is None or op_.shape_verb is None:
            return None
        kind = op_.shape_verb.kind
        if kind == "auto":
            kind = (step.output.meta.get("auto") or {}).get("verb")
        grouped = kind == "collapse" and step.output.meta.get("groups") is not None
        if kind not in ROW_ALIGNED and not grouped:
            return None
        source = str(op_.input)
        upstream = self.steps.get(source)
        if upstream is None or upstream.output.meta.get("staged"):
            return None
        if _is_tool_verb(kind, op_):
            # what the tool binds, and what the output carries through (B11):
            # a carried column that changes is out of date in the output too
            columns = [*self._columns_bound(op_, source, kind),
                       *(_source_column(op_, c) for c in step.output.data.columns)]
            columns = list(dict.fromkeys(columns))
        else:
            columns = list(dict.fromkeys(_source_column(op_, c) for c in step.output.data.columns))
        if grouped:
            # A group's value reads what the tool takes, and its key: a row may
            # change group.
            columns = self._columns_bound(op_, source, kind)
            if step.output.meta.get("by"):
                columns = list(dict.fromkeys([*columns, step.output.meta["by"]]))
        columns = [c for c in columns if c in upstream.output.data.columns]
        return {"step": source, "columns": columns,
                "fp": _row_fps(upstream.output.data, columns)}

    def stale_rows(self, step_id: str) -> list | None:
        """The rows of a stale step that are out of date — None when all of them are."""
        meta = self.steps[step_id].output.meta
        if not meta.get("stale"):
            return []
        rows_ = meta.get("stale_rows")
        return None if rows_ is None else list(rows_)

    def _settle(self) -> None:
        """Put back what the store already holds (SM, ST5), upstream first.

        A step whose run key the store holds shows that result: an expression
        put back, or a column restored upstream, is ``completed`` again with no
        re-run (S7, S9). A step that is ``invalid`` shows its newest result
        rather than a blank plan (S8): its problems still decide its state.
        Whether its inputs are current is :meth:`_refresh_staleness`'s, next."""
        for sid, st in self.steps.items():
            if st.problems:
                kept = self.results(sid)
                if kept and st.output.meta.get("staged"):
                    st.output = kept[0]
                continue
            key = self.run_key(sid)
            found = self.store.get(key) if key is not None else None
            if found is None:
                # no result for its key now, but earlier ones: it shows the
                # newest, stale, never a blank plan (SM), whatever the order
                # of the edits that led here. An emptied step stays empty.
                kept = self.results(sid)
                if kept and st.output.meta.get("staged") and not st.output.meta.get("empty"):
                    st.output = kept[0]
                    if (kept[0].meta.get("ran_with") or {}).get("formula") \
                            != _ran_with(st.operation)["formula"]:
                        kept[0].meta["edited"] = True          # "updated args"
                    self._restage_after(sid)    # readers checked against what it shows
                continue
            restored = found is not st.output
            shown = st.output
            st.output = found
            found.meta.pop("edited", None)
            if restored and self._kind(sid) == "source" and not shown.meta.get("staged") \
                    and not shown.meta.get("empty"):
                self._follow_rows(sid, shown.data, found.data)     # D-picks, on an undo
            if restored:
                # its readers were re-checked against what it showed before:
                # check them again against the result it holds now
                self._restage_after(sid)
            if self._gone:
                self._restore_picks(sid)        # its readers come later in the loop

    def _refresh_staleness(self) -> None:
        """Set every run step's ``stale``, and a short ``stale_reason``, from its stamps.

        Reasons, shown as *"stale output (<reason>)"*: ``updated args`` (its own
        formula changed), ``input r changed`` / ``w changed`` (a step it read
        has new data), ``resource llm changed``, ``r is stale`` (a step it read
        is itself stale).
        """
        self._settle()
        memo: dict[str, str | None] = {}
        partial: dict[str, set | None] = {}         # stale rows; None means all

        def reason(sid: str) -> str | None:
            if sid in memo:
                return memo[sid]
            memo[sid] = None                        # a cycle can't make itself stale
            partial[sid] = None
            step = self.steps[sid]
            output = step.output
            if output.meta.get("staged"):
                return None
            if output.meta.get("edited"):
                memo[sid] = "updated args"
                return memo[sid]
            ran_tool = output.meta.get("tool_hash")
            if ran_tool is not None and ran_tool != self._tool_hash(step.operation):
                memo[sid] = "tool changed"
                return memo[sid]
            read = output.meta.get("read")
            if read is None:                       # saved before stamps: keep its flag
                memo[sid] = "an earlier step changed" if output.meta.get("stale") else None
                return memo[sid]
            inputs = {str(g) for g in step.operation.grids}
            row_reads = output.meta.get("row_reads")
            found, rows_, everything = None, set(), False
            for name, seen in read.items():
                if name.startswith("res:"):
                    if self._resource_version(name[4:]) != seen:
                        found, everything = found or f"resource {name[4:]} changed", True
                    continue
                current = self.version(name) if name in self.steps else None
                tracked = row_reads is not None and row_reads.get("step") == name
                if current != seen:
                    if tracked:
                        changed = self._changed_rows(row_reads)
                        if changed and output.meta.get("groups") is not None:
                            changed = self._groups_of(output, changed, name)
                        if changed is None:
                            found, everything = found or f"input {name} changed", True
                        elif changed:
                            found = found or f"input {name} changed"
                            rows_ |= changed
                        continue                    # unread columns changed: not stale
                    found = found or (f"input {name} changed" if name in inputs
                                      else f"{name} changed")
                    everything = True
                # An input that is stale itself, its data unchanged, doesn't
                # make this step stale (owner, 2026-11-04): staleness isn't
                # passed down the chain. needs_run() names it, "read stale".
            memo[sid] = found
            if found and not everything:
                ids = set(output.data.index)
                partial[sid] = {i for i in rows_ if i in ids}
                if not partial[sid] and not rows_ <= ids:
                    partial[sid] = None
            return found

        for sid, st in self.steps.items():
            meta = st.output.meta
            if meta.get("staged"):
                continue
            if meta.get("read") is not None or meta.get("edited"):
                why = reason(sid)
                meta["stale"] = why is not None
                if why:
                    meta["stale_reason"] = why
                else:
                    meta.pop("stale_reason", None)
                rows_ = partial.get(sid) if why else None
                if rows_ is not None:
                    meta["stale_rows"] = [_plain(i) for i in st.output.data.index if i in rows_]
                else:
                    meta.pop("stale_rows", None)
        self._stale_notes()

    def _stale_notes(self) -> None:
        """Each step's stale warnings (SS7, core-asks L42): its own reason when
        it is stale; else each step it read that is stale now, which run(x)
        runs first. Staleness isn't passed down; this says which input is."""
        for sid, st in self.steps.items():
            notes = []
            state = st.state
            if state == "stale":
                why = st.output.meta.get("stale_reason") or "an input changed"
                notes.append(Problem(f"stale: {why}. Run it to bring it up to date",
                                     "stale", step=sid, severity="warning"))
            elif state in ("completed", "failed"):
                for name in dict.fromkeys(str(r) for r in st.operation.reads):
                    if name in self.steps and name != sid and self.steps[name].state == "stale":
                        why = self.steps[name].output.meta.get("stale_reason") or "an input changed"
                        notes.append(Problem(
                            f"read {name!r}, which is stale ({why}); run({sid!r}) runs it first",
                            "read_stale", step=sid, severity="warning"))
            st.__dict__["stale_notes"] = tuple(notes)

    def _groups_of(self, output: Output, rows_in: set, source: str) -> set | None:
        """The output rows of a grouped step made from *rows_in* (D3): the
        groups they were in, and the groups their key puts them in now. None
        when a key now names a group the output doesn't have."""
        groups = output.meta.get("groups") or []
        out = {out_id for out_id, members in groups
               if any(m in rows_in for m in members)}
        by = output.meta.get("by")
        upstream = self.steps.get(source)
        if by and upstream is not None and by in upstream.output.data.columns:
            ids = set(output.data.index)
            for row in rows_in:
                if row in upstream.output.data.index:
                    key = upstream.output.data.loc[row, by]
                    # a group's id is its key only for an int or str key (K19 D3);
                    # any other key (a list) can't be looked up: all of it changes
                    if not isinstance(key, (int, str)) or key not in ids:
                        return None            # a new group: the whole output changes
                    out.add(key)
        return out

    def _changed_rows(self, row_reads: dict) -> set | None:
        """Input rows whose read columns changed since the run; None if rows came or went."""
        upstream = self.steps.get(row_reads["step"])
        if upstream is None or upstream.output.meta.get("staged"):
            return None
        before = row_reads["fp"]
        columns = [c for c in row_reads["columns"] if c in upstream.output.data.columns]
        if len(columns) != len(row_reads["columns"]):
            return None
        now = _row_fps(upstream.output.data, columns)
        if now.index.equals(before.index):          # the usual case: compare as arrays
            return set(now.index[now.to_numpy() != before.to_numpy()])
        if {str(k) for k in now.index} != {str(k) for k in before.index}:
            return None
        by_str = dict(zip(map(str, before.index), before.to_numpy()))
        return {k for k, h in zip(now.index, now.to_numpy()) if by_str[str(k)] != h}

    # ── what a step reads ────────────────────────────────────────────────
    def basis(self, step_id: str) -> Output | None:
        """What a reader of *step_id* is checked against: its plan (PL).

        A step whose expression ran shows that result, and the result is its
        plan made exact. A step with a new expression not yet run shows its
        last result, for display only: readers are checked against what the
        new expression will produce, so a state never hangs on the order of
        the edits (L40e). None when there is no such step."""
        step = self.steps.get(step_id)
        if step is None or not step.output.meta.get("edited"):
            return None if step is None else step.output
        # Made once: planning a step asks for its inputs' plans many times,
        # and a chain of edited steps would plan each again for every ask.
        place = list(self.steps).index(step_id)
        made_from = (step.operation, step.problems, self.catalog,
                     *self.resources.values(),
                     *(self.basis(d) for d in self._depends_on(step_id)
                       if d in self.steps and list(self.steps).index(d) < place))
        kept = self._plans.get(step_id)
        if kept is not None and len(kept[0]) == len(made_from) \
                and all(a is b for a, b in zip(kept[0], made_from)):
            return kept[1]
        plan = stage(step.operation, self, step.problems, step_id)
        self._plans[step_id] = (made_from, plan)
        return plan

    def _basis_of_input(self, operation: Operation) -> Output | None:
        return None if operation.input is None else self.basis(str(operation.input))

    def _known_columns(self, operation: Operation) -> list[str]:
        """The columns this operation's input will have, in order, as far as known."""
        basis = self._basis_of_input(operation)
        return [] if basis is None else predicted_columns(basis)

    def _columns_open(self, operation: Operation) -> bool:
        """Might this operation's input have columns not predicted yet? (008 K1)"""
        basis = self._basis_of_input(operation)
        return basis is not None and columns_unknown(basis)

    def _predicted_of(self, step_id: str) -> list:
        """The columns a step is known to have (or will have), [] when it doesn't exist."""
        step = self.steps.get(step_id)
        return [] if step is None or not step.valid else predicted_columns(self.basis(step_id))

    def _column_types(self, operation: Operation) -> dict:
        """Column → Python type of this operation's input, as far as known."""
        basis = self._basis_of_input(operation)
        if basis is None:
            return {}
        if not basis.meta.get("staged"):
            return {c: _dtype_type(basis.data[c]) for c in basis.data.columns}
        return dict(basis.meta.get("column_types") or {})

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
        basis = self.basis(step.name)
        index = basis.data.index
        return index if len(index) or not basis.meta.get("staged") else None

    def _with_paired_columns(self, source: Output, paired: dict) -> Output:
        """*source* with each paired argument as a column, row by row by id
        (K19). A row the argument has no value for is blocked, saying so."""
        data = source.data.copy()
        states = source.states.copy()
        blocked = {}
        here = source.meta.get("name")
        for name, ref in paired.items():
            column = _apply_selection(self.steps[ref.id].output.data, ref.rows,
                                      ref.columns, ref.id).iloc[:, 0]
            # Each row's partner: the same row, or the row it came from (a
            # parent's value reaches each of its children), by following `#`
            # columns. Ids match exactly.
            partners = (self.trace(here, list(data.index), ref.id) if here else None) \
                or list(data.index)
            data[name] = [column[p] if p is not None and p in column.index else None
                          for p in partners]
            # an absent cell stays absent, so the tool gets its default (C6)
            gone = self.steps[ref.id].output.absent_cells()
            states[name] = _state_column(["absent" if (p, column.name) in gone else "known"
                                          for p in partners], data.index)
            failed = set(self.steps[ref.id].output.ids_in("failed", "blocked"))
            notes = self.steps[ref.id].output.notes
            for row, p in zip(data.index, partners):
                if (p is None or p not in column.index) and row not in blocked:
                    why = f"{name}: {ref.id!r} has no row {_plain(row if p is None else p)!r}"
                    blocked[row] = (why, why)
                elif p in failed and row not in blocked:
                    # a failed partner blocks its row only, as a column does
                    note = notes.get(p, {})
                    blocked[row] = (f"argument {name!r} reads {ref.id}[{_plain(p)}], which failed",
                                    note.get("cause") or f"{ref.id}[{_plain(p)}]: {note.get('error')}")
        return Output(data, states, {**source.meta, "blocked_rows": blocked})

    def _input_for(self, operation: Operation) -> Any | None:
        """The upstream Output this operation reads, once that step has run."""
        if operation.input is None:
            return None
        step = self.steps.get(str(operation.input))
        if step is None or step.output.meta.get("staged"):
            return None
        # So a failure downstream can name the cell it came from (`a[1]`).
        step.output.meta["name"] = step.name
        return step.output

    def _checked_input(self, operation: Operation) -> Output | None:
        """The input's result a check reads: its plan made exact, once it has
        run its expression; None while that is only planned (PL)."""
        basis = self._basis_of_input(operation)
        if basis is None or basis.meta.get("staged"):
            return None
        return self._input_for(operation)

    def _value_if_known(self, ref: StepRef) -> Any:
        """The value a reference will resolve to, if its step holds data now."""
        basis = self.basis(ref.id)
        if basis is None or basis.meta.get("staged"):
            return _UNKNOWN
        return _ref_value(basis.data, None, ref.id)

    # ── what the UI draws: a step's grid, known unknowns included (009 §4) ──
    def preview(self, step_id: str, rows: tuple[int, int] | None = None) -> dict:
        """A step as something to draw: what is known, and what isn't, and why.

        Works whether or not the step has run. Returns plain data:

        - ``columns``: the known columns, each with its ``type``;
        - ``rows``: the rows that exist (or are planned), each with a ``state``
          and its ``cells`` (``value`` when there is one, else ``type``);
        - ``row_count``: the plan's row axis — ``exact`` with a count, or
          ``bounded`` / ``stated`` / ``unknown`` with ``because``/``resolve``;
        - ``markers``: the **known unknowns** to draw in place — a trailing
          row such as *"‹rows unknown — load hasn't run…›"*, a trailing column
          *"‹+ maybe more columns›"* — each with its ``because`` and ``resolve``.

        *rows* is a ``(start, stop)`` window of positions, for paging.
        """
        step = self.steps[step_id]
        out, plan = step.output, step.plan
        staged = bool(out.meta.get("staged"))
        summary = {"step": step_id, "state": step.state, "summary": step.describe(),
                   "formula": step.operation.to_source()}
        if not step.valid:
            root, why = self.root_cause(step_id) or (step_id, step.problems[0])
            return {**summary, "columns": [], "lineage": [], "rows": [], "row_count": None,
                    "problems": list(step.problems),
                    "markers": [{"kind": "invalid", "text": f"‹can't run — {step.problems[0]}›",
                                 "root": root, "because": why}]}
        types = plan.get("types", {})
        # data columns only: lineage is listed apart (S5a, rule 28)
        names = [c for c in plan.get("columns", {}).get("names", []) if not is_id_column(c)]
        # Each column's number, 0…m-1 left to right: the counterpart of a row's
        # "#", for showing and clicking by position (cols[0], cols[0:3]).
        columns = [{"name": c, "type": types.get(c, "any"), ROW_ID: i}
                   for i, c in enumerate(names)]
        markers = _plan_markers(plan, step_id)
        if out.meta.get("stale"):
            label = f"stale output ({out.meta.get('stale_reason') or 'an earlier step changed'})"
            summary["stale"] = label
            changes = self.arg_changes(step_id)
            if changes:
                summary["computed_with"] = f"values below were computed with {_changes_text(changes)}"
                summary["changed"] = changes
            markers.insert(0, {"kind": "stale", "text": label,
                               "because": label, "resolve": [f"run {step_id!r}"]})
        all_rows = self._preview_rows(step, staged, names, types)
        lo, hi = (rows if rows is not None else (0, len(all_rows)))
        lineage = {} if staged else self.lineage(step_id)
        for n, row in enumerate(all_rows):
            row["lineage"] = {name: cells[n] for name, cells in lineage.items()}
        return {**summary, "columns": columns, "lineage": list(lineage), "rows": all_rows[lo:hi],
                "row_count": plan.get("rows"), "markers": markers,
                "window": {"start": lo, "stop": min(hi, len(all_rows)),
                           "of": len(all_rows)}}

    def _preview_rows(self, step: Step, staged: bool, names: list, types: dict) -> list[dict]:
        out = step.output
        if not staged:
            step_stale = bool(out.meta.get("stale"))
            stale_rows = out.meta.get("stale_rows")
            stale_set = set(map(str, stale_rows)) if stale_rows is not None else None
            row_states = out.row_states
            result = []
            for position, row_id in enumerate(out.data.index):
                stale = step_stale and (stale_set is None or str(row_id) in stale_set)
                note = out.notes.get(row_id, {})
                cells = {}
                for c in out.data.columns:
                    if is_id_column(c):
                        continue                    # lineage: listed apart
                    state = str(out.states.at[row_id, c])
                    if state == "known" and stale:
                        state = "stale"
                    cell = {"state": state, "type": types.get(c, "any")}
                    if state in ("known", "stale"):
                        cell["value"] = _plain(out.data.at[row_id, c])
                    if state in ("failed", "blocked"):
                        cell.update({k: v for k, v in note.items() if k in ("error", "cause")})
                        if str(c) in (note.get("cells") or {}):
                            cell["error"] = note["cells"][str(c)]
                    cells[str(c)] = cell
                row_state = str(row_states[row_id])
                result.append({ROW_ID: position, "position": position,
                               "state": "stale" if stale and row_state == "known" else row_state,
                               "cells": cells})
            return result
        # Staged: rows exist only where staging knows them. A 1:1 verb over a
        # known input has its ids; a filter may drop any of its input's rows.
        verb = step.operation.shape_verb.kind if step.operation.shape_verb else None
        index, state = list(out.data.index), "pending"
        if not index and ROWS_RULE.get(verb) == "at_most":
            known = self._known_index(step.operation)
            index, state = (list(known) if known is not None else []), "maybe"
        return [{ROW_ID: i, "position": i, "state": state,
                 "cells": {c: {"state": state, "type": types.get(c, "any")} for c in names}}
                for i, _row_id in enumerate(index)]

    def cell(self, step_id: str, row: int, column: str) -> dict:
        """One cell, for a click: its value or what is expected there (009 §4).

        *row* is a position (negative counts from the end), *column* a name.
        The ``state`` is one of ``known``, ``stale`` (an old value, still
        shown), ``failed``, ``blocked`` (an input cell failed), ``pending`` (not
        run; the row exists), ``maybe`` (not run; the row may be dropped),
        ``unknown`` (not run; whether the row exists isn't known — "row 2, if
        it exists"), or ``missing`` (no such row or column). Anything short of
        known carries ``because`` (and ``resolve`` where there is a way).
        """
        view = self.preview(step_id)
        base = {"step": step_id, "row": row, "column": column}
        if not isinstance(row, int) or isinstance(row, bool):
            return {**base, "state": "missing",
                    "because": f"a row is a row number, as shown in #: {row!r} isn't one"}
        if view["state"] == "invalid":
            return {**base, "state": "missing", "because": view["problems"][0]}
        names = [c["name"] for c in view["columns"]]
        plan = self.steps[step_id].plan
        col_plan = plan.get("columns", {})
        if column not in names:
            if col_plan.get("more") or col_plan.get("certainty") in ("bounded", "unknown"):
                return {**base, "state": "unknown", "type": "any",
                        "because": col_plan.get("because", "its columns aren't all known yet"),
                        "resolve": col_plan.get("resolve", [])}
            return {**base, "state": "missing",
                    "because": f"{step_id!r} has no column {column!r} "
                               f"(it has {', '.join(names) or 'none'})"}
        type_ = next(c["type"] for c in view["columns"] if c["name"] == column)
        base["column_number"] = names.index(column)
        rows_ = view["rows"]
        n = len(rows_)
        if -n <= row < n:
            entry = rows_[row]
            row_id = self.steps[step_id].output.data.index[row] \
                if row < len(self.steps[step_id].output.data.index) else None
            cell = {**base, **entry["cells"].get(column, {"state": entry["state"]}),
                    "type": type_, "lineage": entry.get("lineage", {})}
            cell["inputs"] = [self._shown_input(e) for e in self._cell_inputs(step_id, row_id, column)]
            if cell["state"] == "stale":
                out_meta = self.steps[step_id].output.meta
                changes = self.arg_changes(step_id)
                if changes:
                    # The value was computed with the old arguments, not the
                    # ones the formula shows now — say which.
                    cell["computed_with"] = dict(out_meta["ran_with"].get("arguments", {}))
                    cell["changed"] = changes
                    cell["because"] = f"stale output · computed with {_changes_text(changes)}"
                else:
                    cell["because"] = (f"stale output "
                                       f"({out_meta.get('stale_reason') or 'an earlier step changed'})")
            return cell
        row_plan = view["row_count"] or {}
        if row_plan.get("certainty") == "exact" or not self.steps[step_id].output.meta.get("staged"):
            last = f" (0–{n - 1})" if n else ""
            return {**base, "state": "missing",
                    "because": f"row {row} of {step_id!r}, which has {n} rows{last}"}
        return {**base, "state": "unknown", "type": type_,
                "because": row_plan.get("because", "its row count isn't known yet"),
                "resolve": row_plan.get("resolve", [])}

    def arg_changes(self, step_id: str) -> list[dict]:
        """How a step's arguments differ from the ones its output was computed with.

        ``[{"name": "weight", "was": "1.5", "now": "2.0"}]`` — empty when the
        output is current. A change to the orchestration rather than an
        argument comes back as ``{"name": "formula", "was": …, "now": …}``. An
        argument that wasn't given shows the tool's default it ran with
        (``was_default``); one removed since shows the default it now gets.
        """
        step = self.steps[step_id]
        ran = step.output.meta.get("ran_with")
        if not ran or not step.output.meta.get("edited"):
            return []
        now = _ran_with(step.operation)
        was_args, now_args = ran.get("arguments", {}), now["arguments"]
        fn = step.operation.fn
        try:
            defaults = {k: p.default for k, p in _signature(fn).parameters.items()
                        if p.default is not inspect.Parameter.empty} if fn else {}
        except (TypeError, ValueError):
            defaults = {}
        changes = []
        for k in dict.fromkeys([*was_args, *now_args]):
            if was_args.get(k) == now_args.get(k):
                continue
            change = {"name": k, "was": was_args.get(k), "now": now_args.get(k)}
            # An argument that wasn't given ran with the tool's default: say so.
            if change["was"] is None and k in defaults:
                change["was"], change["was_default"] = _src(defaults[k]), True
            if change["now"] is None and k in defaults:
                change["now"], change["now_default"] = _src(defaults[k]), True
            changes.append(change)
        if not changes and ran.get("formula") != now["formula"]:
            changes = [{"name": "formula", "was": ran.get("formula"), "now": now["formula"]}]
        return changes

    #: How many of an input row's values a cell click shows; the rest are counted.
    INPUT_VALUES_SHOWN = 6

    def _shown_input(self, entry: dict) -> dict:
        """An input entry as shown: its rows as row numbers, never ids (S5-D5)."""
        entry = dict(entry)
        source = self.steps.get(entry.get("step"))
        index = [str(i) for i in source.output.data.index] if source is not None else []

        def number(v: Any) -> Any:
            return index.index(str(v)) if str(v) in index else None
        if "id" in entry:
            row_id = entry.pop("id")
            entry["row"] = None if row_id is None else number(row_id)
        if isinstance(entry.get("rows"), list):
            entry["rows"] = [number(v) for v in entry["rows"]]
        return entry

    def _cell_inputs(self, step_id: str, row_id: Any, column: str | None = None) -> list[dict]:
        """Every input cell a result cell came from, one entry per binding (010 C27).

        Each entry: ``step``, ``id`` (or ``rows`` for several), ``columns`` read,
        the ``argument`` they were bound to (``None`` when a step copies the
        cell without a tool), their cell ``state`` (``known``, ``failed``,
        ``pending``, ``stale`` … — 010 C24) and their ``values``. Nothing is
        stored for this: it's worked out from row ids and the step's formula.
        """
        step = self.steps[step_id]
        op_ = step.operation
        kind = op_.shape_verb.kind if op_.shape_verb else None
        if kind == "auto":
            kind = (step.output.meta.get("auto") or {}).get("verb", "map")
        entries: list[dict] = []

        if is_combine(op_):
            if op_.tool == "zip":
                for g in op_.grids:
                    if column in self._predicted_of(str(g)):
                        entries.append(self._input_entry(
                            str(g), self._trace_one(step_id, row_id, str(g)), [column], None))
                        break
            else:
                data = step.output.data
                own = own_id_columns([str(g) for g in op_.grids])
                keys = op_.arguments.get("on")
                keys = {keys} if isinstance(keys, str) else set(keys or [])
                for g, idc in zip((str(g) for g in op_.grids), own):
                    partner = data.at[row_id, idc] if idc in data.columns and row_id in data.index else None
                    if partner is None:
                        continue                          # no row on this side
                    have = self._predicted_of(g)
                    read = [c for c in (column, *(column[:-len(s)] for s in
                            (op_.arguments.get("suffixes") or []) if column.endswith(s)))
                            if c in have]
                    if read or column in keys or column == idc:
                        entries.append(self._input_entry(g, partner, read[:1] or [column], None))
            return entries

        if op_.input is not None:
            source = str(op_.input)
            listed = step.output.data.at[row_id, f"{ROW_ID}{source}"] \
                if f"{ROW_ID}{source}" in step.output.data.columns and row_id in step.output.data.index \
                else None
            if kind == "distinct" and isinstance(listed, list):
                entries.append(self._input_entry(source, None, [_source_column(op_, column)],
                                                 None, rows_=listed))
            elif kind == "collapse":
                members = listed if isinstance(listed, list) else \
                    (step.output.notes.get(row_id) or {}).get("unit")
                rows_ = members if isinstance(members, list) else None
                for param in self._columns_bound(op_, source, kind):
                    entries.append(self._input_entry(source, None, [param], param, rows_=rows_))
            elif kind == "table":
                entries.append({"step": source, "id": None, "rows": "all", "columns": [],
                                "argument": self._first_param(op_), "state":
                                self._grid_state(source), "values": {}})
            elif _is_tool_verb(kind, op_):
                traced = self._trace_one(step_id, row_id, source)
                for param in self._columns_bound(op_, source, kind):
                    entries.append(self._input_entry(source, traced, [param], param))
            else:
                # No tool: the cell is a copy of the input's (renamed, perhaps).
                entries.append(self._input_entry(source, self._trace_one(step_id, row_id, source),
                                                 [_source_column(op_, column)], None))

        for name, value in op_.arguments.items():
            if isinstance(value, StepRef):
                entries.append(self._reference_entry(value, name))
            elif isinstance(value, ResRef):
                entries.append({"resource": value.name, "argument": name,
                                "state": "loaded at run"})
        for m in op_.modifiers:
            for name, value in m.settings.items():
                if isinstance(value, StepRef):
                    entries.append(self._reference_entry(value, f"{m.kind}.{name}"))
        return entries

    # ── following a row back (reshaping.md §5.1: ids are never parsed) ────
    def _same_ids(self, step_id: str) -> set[str]:
        """*step_id* and the steps whose rows it keeps, with the same ids."""
        names, seen = {step_id}, step_id
        while seen in self.steps:
            op_ = self.steps[seen].operation
            restored = self._restore_column(seen)
            grouped = self._groups_by_step(seen)
            if restored is not None:             # its items are the packed rows again
                seen = self._id_source(restored)
            elif grouped is not None:            # one row per row of s, with s's ids
                seen = grouped[1]
            elif not keeps_ids(self._kind(seen), op_.shape_verb) or op_.input is None:
                break
            else:
                seen = str(op_.input)
            if seen is None or seen in names:
                break
            names.add(seen)
        return names

    def _id_source(self, column: Any) -> str | None:
        """The step a `#` column names: `#v` → `v`; `#v_2` (a step read twice) → `v`."""
        if not is_id_column(column) or column == ROW_ID:
            return None
        name = column[len(ROW_ID):]
        if name in self.steps:
            return name
        base, _, n = name.rpartition("_")
        return base if n.isdigit() and base in self.steps else None

    def trace(self, step_id: str, ids: list, target: str) -> list | None:
        """The ids, in step *target*, of the rows *ids* of *step_id* came from.

        Follows the `#` columns back, step by step, and the steps that keep
        ids; never reads anything out of an id. ``None`` when *step_id*'s rows
        don't come from *target*'s; an entry is ``None`` for a row that
        doesn't."""
        return self._trace(step_id, list(ids), self._same_ids(target), 0)

    def _trace(self, step_id: str, ids: list, target: set, depth: int,
               dropped: frozenset = frozenset()) -> list | None:
        if step_id in target:
            return ids
        step = self.steps.get(step_id)
        if step is None or depth > len(self.steps):
            return None
        data = step.output.data
        for c in data.columns:
            parent = self._id_source(c)
            if c in dropped:
                continue                  # dropped further on: the trace stops (§5.1, rule 5)
            if parent is not None and self._lists_rows(step_id, c):
                continue                  # each row came from several: no one partner
            if parent is not None:
                mapped = [data.at[i, c] if i in data.index else None for i in ids]
                if any(isinstance(m, list) for m in mapped):
                    continue              # these rows came from several: no one partner
                found = self._trace(parent, mapped, target, depth + 1, dropped)
                if found is not None:
                    return found
        op_ = step.operation
        restored = self._restore_column(step_id)
        if restored is not None and self._id_source(restored) is not None:
            return self._trace(self._id_source(restored), ids, target, depth + 1, dropped)
        grouped = self._groups_by_step(step_id)
        if grouped is not None:
            return self._trace(grouped[1], ids, target, depth + 1, dropped)
        if keeps_ids(self._kind(step_id), op_.shape_verb) and op_.input is not None:
            verb = op_.shape_verb
            if verb.kind in ("drop", "rename"):
                dropped = dropped | {c for c in (verb.settings.get("columns") or ()) if is_id_column(c)}
            return self._trace(str(op_.input), ids, target, depth + 1, dropped)
        if is_combine(op_) and op_.tool == "zip":
            for g in op_.grids:           # a zip's rows are its finest input's
                inner = self.steps.get(str(g))
                if inner is not None and all(i in inner.output.data.index for i in ids):
                    found = self._trace(str(g), ids, target, depth + 1)
                    if found is not None:
                        return found
        return None

    # ── lineage, as a user sees it (S5a, S5b; core-asks §M3) ───────────────
    def lineage(self, step_id: str) -> dict:
        """A step's lineage columns, as shown: ``{"#r": [cell per row], …}``.

        Every step carries its input's lineage; one that isn't one-to-one adds
        ``#<parent>`` (``.idx`` after an expand, ``.2`` for a parent read
        twice). A cell is the ancestor row's **current** row number, a list of
        them after a collapse, or None where there is none (S5-D4). Computed
        from core's row ids, which already are lineage: nothing is stored.
        """
        step = self.steps.get(step_id)
        if step is None or step.output.meta.get("staged"):
            return {}
        positions: dict = {}

        def number(ancestor: str, value: Any) -> Any:
            if ancestor not in positions:
                index = self.steps[ancestor].output.data.index if ancestor in self.steps else []
                positions[ancestor] = {**{str(i): n for n, i in enumerate(index)},
                                       **{i: n for n, i in enumerate(index) if _hashable(i)}}
            found = positions[ancestor]
            if isinstance(value, list):
                return [found.get(v, found.get(str(v))) for v in value]
            return None if value is None else found.get(value, found.get(str(value)))

        shown = {}
        for name, (ancestor, kind, cells) in self._lineage_ids(step_id, {}).items():
            shown[name] = list(cells) if kind == "idx" else [number(ancestor, v) for v in cells]
        return shown

    def _lineage_ids(self, step_id: str, memo: dict) -> dict:
        """``{name: (ancestor, "rows" | "idx", [cell per row])}``, cells in the
        ancestor's row ids (an id, a list of ids, or None)."""
        if step_id in memo:
            return memo[step_id]
        memo[step_id] = {}                          # a cycle can't feed itself
        step = self.steps.get(step_id)
        if step is None or step.output.meta.get("staged"):
            return {}
        data, op_ = step.output.data, step.operation
        index = list(data.index)
        kind = self._kind(step_id)
        out: dict = {}

        def add(name: str, entry: tuple) -> None:
            base, n = name, 2
            while name in out:                      # the same ancestor twice: #r, #r.2
                name, n = f"{base}.{n}", n + 1
            out[name] = entry

        # Its own parents, and for each, the parent's id of every row.
        parents: list = []                          # [(parent, [id per row], writes idx)]
        writes = is_combine(op_) and op_.tool in ("join", "stack") \
            or kind in ("expand", "collapse", "distinct")
        if writes:
            # only the column it writes for each input: a `#` column it carries,
            # or groups by, isn't a new parent
            if is_combine(op_):
                written = own_id_columns([str(g) for g in op_.grids])
            else:
                written = [f"{ROW_ID}{op_.input}"] if op_.input is not None else []
            for c in written:
                parent = self._id_source(c)
                if c in data.columns and parent in self.steps:
                    parents.append((parent, [_plain(data.at[i, c]) for i in index], kind == "expand"))
        elif is_combine(op_) and op_.tool == "zip":
            for g in op_.grids:
                found = self.trace(step_id, index, str(g)) if str(g) in self.steps else None
                if found is not None:
                    parents.append((str(g), list(found), False))
        elif op_.input is not None and keeps_ids(kind, op_.shape_verb):
            source = str(op_.input)
            columns_only = kind == "select" and op_.shape_verb.settings.get("rows") is None
            if kind in _ONE_TO_ONE or columns_only or kind is None:
                # one-to-one: its rows are its input's; it carries, adds nothing
                for name, (ancestor, k_, cells) in self._lineage_ids(source, memo).items():
                    by_id = dict(zip(map(str, self.steps[source].output.data.index), cells))
                    add(name, (ancestor, k_, [by_id.get(str(i)) for i in index]))
                memo[step_id] = out
                return out
            parents.append((source, [_plain(i) for i in index], False))

        counts: dict = {}
        for parent, ids, idx in parents:
            name = f"{ROW_ID}{parent}"
            add(name, (parent, "rows", ids))
            if idx:                                 # an item's place in its parent's cell
                seen: dict = {}
                places = []
                for v in ids:
                    places.append(seen.get(str(v), 0))
                    seen[str(v)] = places[-1] + 1
                add(f"{name}.idx", (parent, "idx", places))
            counts[parent] = counts.get(parent, 0) + 1
        # ... then everything its parents carry, looked up through those ids
        for parent, ids, _idx in parents:
            carried = self._lineage_ids(parent, memo)
            if not carried:
                continue
            parent_ids = list(map(str, self.steps[parent].output.data.index))
            for name, (ancestor, k_, cells) in carried.items():
                by_id = dict(zip(parent_ids, cells))

                def through(v: Any) -> Any:
                    if isinstance(v, list):
                        hits = [through(x) for x in v]
                        flat = [y for h in hits for y in (h if isinstance(h, list) else [h])
                                if y is not None]
                        return list(dict.fromkeys(flat)) if k_ == "rows" else flat
                    return None if v is None else by_id.get(str(v))
                add(name, (ancestor, k_, [through(v) for v in ids]))
        # packed rows given back (R-D3) are the source's own rows, each one of
        # them, not the group it was packed in: its lineage, by their ids
        restored = self._restore_column(step_id) if kind == "expand" else None
        source = self._id_source(restored) if restored else None
        if source in self.steps:
            out[f"{ROW_ID}{source}"] = (source, "rows", [_plain(i) for i in index])
            source_ids = list(map(str, self.steps[source].output.data.index))
            for name, (ancestor, k_, cells) in self._lineage_ids(source, memo).items():
                by_id = dict(zip(source_ids, cells))
                out[name] = (ancestor, k_, [by_id.get(str(i)) for i in index])
        memo[step_id] = out
        return out

    def aligned(self, a: str, b: str) -> bool:
        """Are steps *a* and *b* the same rows, in any order: one step, or
        connected only through steps that keep every row (one-to-one steps, a
        sort, core-asks model §M3)? Rows pair by id, never by position. A
        filter or slice makes other rows; a row pick does too."""
        return self._aligned_root(a) == self._aligned_root(b)

    def _join_hint(self, a: str, b: str) -> str:
        """The join that brings steps *a* and *b* together: on the lineage of
        their nearest shared ancestor (S5e), else on a column."""
        def meets(side: str, s: str) -> bool:
            # the join reads side's rows as s's: it is s, aligned with it, or carries #s
            return side == s or self.aligned(side, s) or f"{ROW_ID}{s}" in self.lineage(side)
        for s in dict.fromkeys(self._matchable(a) + self._matchable(b)):
            if meets(a, s) and meets(b, s):
                return f"join(wf[{a!r}], wf[{b!r}], on={ROW_ID + s!r})"
        return f"join(wf[{a!r}], wf[{b!r}], on=…)"

    def _matchable(self, step_id: str) -> list[str]:
        """The steps a join on lineage can match *step_id*'s rows to, nearest
        first: itself, the step it's aligned with, its ancestors."""
        if step_id not in self.steps:
            return []
        found = [step_id, self._aligned_root(step_id)]
        found += [n[len(ROW_ID):].split(".")[0] for n in self.lineage(step_id)]
        return list(dict.fromkeys(found))

    def _aligned_root(self, step_id: str) -> str:
        """The furthest step back that *step_id* reaches through steps that keep
        every row, in any order."""
        seen, names = step_id, {step_id}
        while seen in self.steps:
            op_ = self.steps[seen].operation
            kind = self._kind(seen)
            # one row per row of s (R-D5), or packed rows given back (R-D3)
            grouped, restored = self._groups_by_step(seen), self._restore_column(seen)
            nxt = grouped[1] if grouped else (self._id_source(restored) if restored else None)
            if is_combine(op_) and op_.tool == "zip" and op_.grids:
                nxt = str(op_.grids[0])          # a zip_ of aligned steps is their rows
            if nxt is not None and nxt not in names:
                names.add(nxt)
                seen = nxt
                continue
            columns_only = kind == "select" and op_.shape_verb.settings.get("rows") is None
            if op_.input is None or is_combine(op_) or getattr(op_.input, "rows", None) is not None \
                    or not (kind in _ONE_TO_ONE or kind == "sort" or columns_only):
                break
            seen = str(op_.input)
            if seen in names:
                break
            names.add(seen)
        return seen

    def _step_column_type(self, step_id: str, column: str) -> Any:
        """The Python type of *column* of step *step_id*, as far as known, or None."""
        step = self.steps.get(step_id)
        if step is None:
            return None
        if not step.output.meta.get("staged"):
            return _dtype_type(step.output.data[column]) if column in step.output.data.columns else None
        return (step.output.meta.get("column_types") or {}).get(column)

    def _kind(self, step_id: str) -> str | None:
        """The verb a step runs as: an `auto` step's, once it has resolved."""
        step = self.steps[step_id]
        verb = step.operation.shape_verb
        kind = verb.kind if verb is not None else None
        if kind == "auto":
            kind = (step.output.meta.get("auto") or {}).get("verb", "map")
        return kind

    # ── the invariants (reshaping.md §2.1) ─────────────────────────────────
    def check_invariants(self, step_id: str, plan: dict | None = None) -> list[str]:
        """What breaks the airtight checks in a step that has run, or ``[]``.

        A1 row ids are unique; A3 every ``#v`` value is a row of step ``v``;
        A4 a step that keeps ids keeps its input's; A5 rows of two grids met
        only through a match core recorded; A6 an exact *plan* (the step's,
        taken before it ran) was kept. A2 (no tool sees a ``#`` column) and A7
        (every loss is a step) can't be seen after a run: laws test them.
        """
        step = self.steps.get(step_id)
        if step is None or step.output.meta.get("staged") or step.state != "completed":
            return []
        data, found = step.output.data, []
        if not data.index.is_unique:
            dup = sorted({str(i) for i in data.index[data.index.duplicated()]})
            found.append(f"A1 {step_id}: row ids not unique ({', '.join(dup[:3])})")
        if ROW_ID in data.columns and list(data[ROW_ID]) != list(data.index):
            found.append(f"A1 {step_id}: its {ROW_ID!r} column isn't its row ids")
        op_ = step.operation
        # None only where a row has no partner on that side (reshaping.md §5).
        def may_be_none(column: str, start: str = step_id) -> bool:
            """A `#` column a stack or an outer join wrote, here or carried
            (through a zip_ too: an empty lineage cell is allowed, CA-L2)."""
            seen = start
            while seen in self.steps:
                o = self.steps[seen].operation
                if is_combine(o) and o.tool == "zip":
                    return any(column in self.steps[str(g)].output.data.columns
                               and may_be_none(column, str(g))
                               for g in o.grids if str(g) in self.steps)
                if is_combine(o):
                    return o.tool == "stack" or (o.tool == "join" and o.arguments.get("how", "inner") != "inner")
                if not keeps_ids(self._kind(seen), o.shape_verb) or o.input is None:
                    return False
                seen = str(o.input)
            return False
        for c in data.columns:
            if not is_id_column(c) or c == ROW_ID:
                continue
            name = self._id_source(c)
            source = self.steps.get(name) if name else None
            if source is None:
                found.append(f"A3 {step_id}: {c!r} names no step")
                continue
            if source.output.meta.get("staged"):
                continue
            ids = set(source.output.data.index)
            bad = [v for cell in data[c] for v in (cell if isinstance(cell, list) else [cell])
                   if (v is None and not may_be_none(c)) or (v is not None and v not in ids)]
            if bad:
                found.append(f"A3 {step_id}: {c!r} holds {_plain(bad[0])!r}, not a row of {name!r}")
        if keeps_ids(self._kind(step_id), op_.shape_verb) and op_.input is not None:
            inp = self.steps.get(str(op_.input))
            if inp is not None and not inp.output.meta.get("staged"):
                kept = set(inp.output.data.index)
                extra = [i for i in data.index if i not in kept]
                if extra:
                    found.append(f"A4 {step_id}: row {_plain(extra[0])!r} isn't a row of {str(op_.input)!r}")
        meeting = []
        if is_combine(op_) and op_.tool == "zip" and not op_.arguments.get("match_ids"):
            grids = [str(g) for g in op_.grids]   # (match_ids=True: the user vouched)
            meeting = [(a, b) for n, a in enumerate(grids) for b in grids[n + 1:]]
        elif op_.input is not None:
            meeting = [(str(op_.input), ref.id) for ref in _paired_arguments(op_, self).values()]
        for a, b in meeting:
            if not self._matched(a, b):
                found.append(f"A5 {step_id}: rows of {a!r} and {b!r} met with no recorded match")
        on = op_.arguments.get("on") if is_combine(op_) and op_.tool == "join" else None
        if isinstance(on, str) and is_id_column(on):
            found += self._lineage_join_breaks(step_id, on)
        columns, rows_ = (plan or {}).get("columns") or {}, (plan or {}).get("rows") or {}
        if columns.get("certainty") == "exact" and list(columns.get("names") or []) != list(data.columns):
            found.append(f"A6 {step_id}: planned columns {columns.get('names')}, got {list(data.columns)}")
        if rows_.get("certainty") == "exact" and rows_.get("count") is not None \
                and rows_["count"] != len(data):
            found.append(f"A6 {step_id}: planned {rows_['count']} rows, got {len(data)}")
        return found

    def filed_unchanged(self) -> list[str]:
        """A9 (ST4): a result is never changed once it's filed. Each step's
        data still hashes to the version it was given when it ran (or was
        declared); a later run, edit or view that changed it breaks this.
        Values with no stable version (ST1) can't be checked, and aren't."""
        found = []
        for name, st in self.steps.items():
            filed = st.output.meta.get("version")
            if filed is None or st.output.meta.get("staged") or _unversioned(st.output.data):
                continue
            now = _data_version(st.output.data)
            if now != filed:
                found.append(f"A9 {name}: its data changed after it was filed ({filed} -> {now})")
        return found

    def _lineage_join_breaks(self, step_id: str, on: str) -> list[str]:
        """A5 for a join on lineage: each row's two sides come from the same
        row of the step *on* names. Followed back by id, step by step (a
        trace), never through the row numbers the join matched on."""
        data, grids = self.steps[step_id].output.data, [str(g) for g in self.steps[step_id].operation.grids]
        target = self._id_source(on) or on[len(ROW_ID):]
        written = own_id_columns(grids)
        if target not in self.steps or len(grids) != 2 or any(c not in data.columns for c in written):
            return []

        def origin(side: str, row_id: Any) -> str | None:
            """The row of *target* that row *row_id* of *side* came from."""
            traced = self.trace(side, [row_id], target)
            return None if traced is None or traced[0] is None else str(traced[0])

        for i in data.index:
            ends = [data.at[i, c] for c in written]
            if any(e is None or (not isinstance(e, list) and pd.isna(e)) for e in ends):
                continue                                         # an outer join's gap
            found = [origin(side, e) for side, e in zip(grids, ends)]
            if None in found:
                continue                                         # nothing to follow back
            if found[0] != found[1]:
                return [f"A5 {step_id}: row {_plain(i)!r} joins row {_plain(ends[0])!r} of "
                        f"{grids[0]!r} with row {_plain(ends[1])!r} of {grids[1]!r}, which come "
                        f"from different rows of {target!r}"]
        return []

    def _reaches(self, a: str, b: str) -> bool:
        """Does each row of step *a* have one row of step *b* it came from, or is
        it that row? (A child reaches its parent; a parent doesn't reach its
        children: it has several.)"""
        if self._same_ids(a) & self._same_ids(b):
            return True
        return a in self.steps and self.trace(a, list(self.steps[a].output.data.index), b) is not None

    def _matched(self, a: str, b: str) -> bool:
        """Did core record how rows of steps *a* and *b* match (reshaping.md §6)?"""
        if self._same_ids(a) & self._same_ids(b):
            return True                   # one origin: the same rows
        for x, y in ((a, b), (b, a)):
            if x in self.steps and self.trace(x, list(self.steps[x].output.data.index), y) is not None:
                return True               # a child and the step its rows came from
        return False

    def _packed_by(self, step_id: str, column: str, depth: int = 0) -> str | None:
        """The `#` list that lines up with list *column* of *step_id*, when core
        packed it and no tool has touched it since; else None (reshaping.md
        §6.2). Decided from the verbs, so the plan knows before anything runs."""
        step = self.steps.get(step_id)
        if step is None or depth > len(self.steps):
            return None
        if is_id_column(column):                 # unpacking a `#` list itself
            return column if self._lists_rows(step_id, column) else None
        op_ = step.operation
        kind = self._kind(step_id)
        found = None
        if kind == "collapse" and op_.input is not None:
            fn = op_.fn or BUILTIN_TOOLS.get(op_.tool)
            if _base(fn) is BUILTIN_TOOLS["gather"] and column != op_.shape_verb.settings.get("by"):
                found = f"{ROW_ID}{op_.input}"
        elif is_combine(op_) and op_.tool == "zip":
            for g in op_.grids:
                if column in self._predicted_of(str(g)):
                    found = self._packed_by(str(g), column, depth + 1)
                    break
        elif kind == "rename" and op_.input is not None:
            mapping = op_.shape_verb.settings.get("columns") or {}
            old = next((o for o, n in mapping.items() if n == column), column) \
                if isinstance(mapping, dict) else None
            found = self._packed_by(str(op_.input), old, depth + 1) if old else None
        elif kind == "widen" and op_.input is not None:
            # a field of a dict `pack` made is that column again, unchanged
            inner = self.steps.get(str(op_.input))
            if inner is not None and self._kind(str(op_.input)) == "pack" and \
                    column not in variables(self._predicted_of(str(op_.input))):
                found = self._packed_by(str(inner.operation.input), column, depth + 2)
            else:
                found = self._packed_by(str(op_.input), column, depth + 1)
        elif kind in ("select", "drop", "sort", "slice", "filter", "distinct", "group", "pack") \
                and op_.input is not None:     # carried unchanged: no tool rewrites it
            found = self._packed_by(str(op_.input), column, depth + 1)
        return found if found is not None and found in self._predicted_of(step_id) else None

    # ── how to go back (reshaping.md §7, R-D8) ────────────────────────────
    def inverse(self, step_id: str, operation: Operation | None = None) -> dict:
        """How to go back from *step_id*'s output to its input, decided by the
        verb, never the data: ``rebuild`` (with the inverse step's formula,
        which gives the input back exactly), ``trace`` (the values are lost
        here, but `#` columns lead to the input rows), ``opaque`` (a table
        tool: the trace leads to the whole input), or ``generated`` (no input:
        nothing to go back to)."""
        op_ = operation if operation is not None else self.steps[step_id].operation
        me = f'wf["{step_id}"]'
        if is_combine(op_):
            if op_.tool == "zip" and not op_.arguments.get("match_ids"):
                grids = [str(g) for g in op_.grids]
                one_origin = all(self._same_ids(a) & self._same_ids(b)
                                 for n, a in enumerate(grids) for b in grids[n + 1:])
                each_has = all(variables(self._predicted_of(g)) for g in grids)
                if one_origin and each_has:      # (a select of nothing isn't a step: L40)
                    return {"kind": "rebuild", "formula": [
                        f"mod.select(columns={variables(self._predicted_of(g))!r})({me})"
                        for g in grids]}
            return {"kind": "trace"}
        verb = op_.shape_verb
        kind = verb.kind if verb is not None else None
        if kind == "auto":
            kind = (self.steps[step_id].output.meta.get("auto") or {}).get("verb") \
                if step_id in self.steps else None
        if op_.input is None or kind in ("source", "sweep"):
            return {"kind": "generated"}
        if kind == "table":
            return {"kind": "opaque"}
        source = str(op_.input)
        settings = verb.settings
        if kind == "rename" and isinstance(settings.get("columns"), dict):
            back = {new: old for old, new in settings["columns"].items()}
            return {"kind": "rebuild", "formula": f"mod.rename(columns={back!r})({me})"}
        if kind == "pack" and op_.name_rule is None:
            chosen = list(settings.get("columns") or variables(self._predicted_of(source)))
            return {"kind": "rebuild", "formula": f"mod.widen(columns={chosen!r})({me})"}
        if kind == "widen":
            names_ = variables(self._predicted_of(source))
            # the column a pack made: named after that pack (D9), or `value`
            packed = (source if source in self.steps and self._kind(source) == "pack"
                      and self.steps[source].operation.name_rule is None else VALUE_COLUMN)
            spread = packed if packed in names_ else (names_[0] if len(names_) == 1 else None)
            fields = list(settings.get("columns") or [])
            if not fields and step_id in self.steps and not self.steps[step_id].output.meta.get("staged"):
                fields = [c for c in variables(self.steps[step_id].output.data.columns) if c not in names_]
            if spread == packed and fields:
                # packed back under its own name, whatever the step that packs it is called
                return {"kind": "rebuild",
                        "formula": f"op(\"identity\")[mod.pack(columns={fields!r}), "
                                   f"mod.name({spread!r})]({me})"}
            if spread == packed:
                return {"kind": "rebuild", "formula": None}
            return {"kind": "trace"}
        if kind == "collapse" and _base(op_.fn or BUILTIN_TOOLS.get(op_.tool)) is BUILTIN_TOOLS["gather"] \
                and self._groups_by_step_of(op_) is None:
            by = settings.get("by")
            lists = [c for c in variables(self._predicted_of(source)) if c != by]
            return {"kind": "rebuild", "formula": f"mod.expand(columns={lists!r})({me})"}
        return {"kind": "trace"}

    def default_name_rule(self, operation: Operation) -> dict | None:
        """The kernel's naming pattern, for a step that writes values and has no
        ``mod.name`` of its own (outputs-and-reshaping.md §10)."""
        pattern = getattr(self.naming, "pattern", "{field}")
        verb = operation.shape_verb
        if pattern == "{field}" or verb is None or operation.name_rule is not None or \
                (verb.kind not in NAMED_VERBS and verb.kind != "auto"):
            return None
        return {"pattern": pattern}

    def _case_problems(self, step_id: str, output: Output) -> list[str]:
        """Columns a step writes that don't follow the kernel's case (§10)."""
        case = getattr(self.naming, "case", None)
        if case is None:
            return []
        op_ = self.steps[step_id].operation if step_id in self.steps else None
        source = str(op_.input) if op_ is not None and op_.input is not None else None
        before = set(self._predicted_of(source)) if source in self.steps else set()
        rule = _SNAKE if case == "snake" else _CAMEL
        return [f"{c!r} isn't {case} case, as this kernel's naming asks"
                for c in variables(predicted_columns(output))
                if c not in before and not rule.match(str(c))]

    def _declared_fields(self, operation: Operation) -> list[str] | None:
        """For ``widen`` with no ``columns=``: the fields of the record type the
        column it spreads is declared to hold (G9), so its plan is exact."""
        verb = operation.shape_verb
        if verb is None or verb.kind != "widen" or operation.input is None:
            return None
        names_ = variables(self._predicted_of(str(operation.input)))
        spread = VALUE_COLUMN if VALUE_COLUMN in names_ else (names_[0] if len(names_) == 1 else None)
        hint = self._column_types(operation).get(spread) if spread else None
        args = typing.get_args(hint)
        if type(None) in args and len(args) == 2:
            hint = next(a for a in args if a is not type(None))
        fields = _record_fields(hint) if hint is not None else None
        return list(fields) if fields else None

    def _groups_by_step_of(self, operation: Operation) -> tuple[str, str] | None:
        """``(by, s)`` for an operation that is ``collapse(by="#s")``."""
        verb = operation.shape_verb
        if verb is None or verb.kind != "collapse" or operation.input is None:
            return None
        by = verb.settings.get("by")
        s = self._id_source(by) if isinstance(by, str) else None
        return (by, s) if s is not None else None

    def _groups_by_step(self, step_id: str) -> tuple[str, str] | None:
        """For ``collapse(by="#s")``: ``(by, s)``, the step whose rows it groups by."""
        step = self.steps.get(step_id)
        if step is None or self._kind(step_id) != "collapse":
            return None
        by = step.operation.shape_verb.settings.get("by")
        s = self._id_source(by) if isinstance(by, str) else None
        return (by, s) if s is not None else None

    def _restore_column(self, step_id: str) -> str | None:
        """For an expand: the `#` list whose ids its items get back, if all it
        unpacks is one pack core made (R-D3)."""
        step = self.steps.get(step_id)
        if step is None or self._kind(step_id) != "expand" or step.operation.input is None:
            return None
        op_ = step.operation
        source = str(op_.input)
        unpacked = op_.shape_verb.settings.get("columns")
        if not unpacked:
            if not is_identity(op_.fn or BUILTIN_TOOLS.get(op_.tool)):
                return None                      # a tool made the list: its items are new
            have = variables(self._predicted_of(source))
            unpacked = [VALUE_COLUMN] if VALUE_COLUMN in have else have
            if len(unpacked) != 1:
                return None
        found = {self._packed_by(source, c) for c in unpacked}
        return found.pop() if len(found) == 1 and None not in found else None

    def _dropped_at(self, step_id: str, column: str) -> str | None:
        """The step at or before *step_id* that dropped or renamed `#` *column*,
        if that's why it's missing (reshaping.md §5: dropping a trace is a step)."""
        seen = step_id
        while seen in self.steps:
            op_ = self.steps[seen].operation
            verb = op_.shape_verb
            if verb is not None and verb.kind in ("drop", "rename") and \
                    column in (verb.settings.get("columns") or ()):
                return seen
            if not keeps_ids(self._kind(seen), verb) or op_.input is None:
                return None
            seen = str(op_.input)
        return None

    def _lists_rows(self, step_id: str, column: str) -> bool:
        """Does *column* of *step_id* hold a list of rows per row? Known from the
        verbs, so it holds before anything runs: a collapse's own `#` column, and
        distinct's, and the same column wherever it is carried (reshaping.md §5)."""
        seen = 0
        while step_id in self.steps and seen <= len(self.steps):
            op_ = self.steps[step_id].operation
            kind = self._kind(step_id)
            if op_.input is None:
                return False
            if kind in ("collapse", "distinct") and column == f"{ROW_ID}{op_.input}":
                return True
            if not keeps_ids(kind, op_.shape_verb):
                return False
            step_id, seen = str(op_.input), seen + 1   # carried: as it was where it came from
        return False

    def _trace_one(self, step_id: str, row_id: Any, target: str) -> Any:
        found = self.trace(step_id, [row_id], target)
        return found[0] if found else None

    def _columns_bound(self, op_: Operation, source: str, kind: str) -> list[str]:
        """The input columns a tool reads: its parameters the input supplies by name."""
        fn = op_.fn or BUILTIN_TOOLS.get(op_.tool)
        columns = self._predicted_of(source)
        try:
            parameters = list(_signature(fn).parameters.values()) if fn else []
        except (TypeError, ValueError):
            parameters = []
        parameters = _tool_parameters(kind, fn, parameters)   # not an accumulator or grid
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
            return [c for c in columns if c not in op_.arguments]      # the whole row
        bound = [p.name for p in parameters
                 if p.name in columns and p.name not in op_.arguments]
        return bound

    @staticmethod
    def _first_param(op_: Operation) -> str | None:
        fn = op_.fn
        try:
            return next(iter(_signature(fn).parameters), None) if fn else None
        except (TypeError, ValueError):
            return None

    def _grid_state(self, step_id: str) -> str:
        step = self.steps.get(step_id)
        if step is None:
            return "missing"
        if step.output.meta.get("staged"):
            return "pending"
        worst = str(step.output.row_states.max()) if len(step.output.data) else "known"
        return "stale" if worst == "known" and step.output.meta.get("stale") else worst

    def _input_entry(self, source: str, row_id: Any, columns: list, argument: Any,
                     rows_: list | None = None) -> dict:
        """One binding to rows of *source*: the row (or its parent), its state, its values."""
        entry = {"step": source, "id": None, "columns": [c for c in columns if c is not None],
                 "argument": argument}
        upstream = self.steps.get(source)
        if upstream is None or upstream.output.meta.get("staged"):
            return {**entry, "state": "pending", "values": {}}
        out = upstream.output
        if rows_ is not None:
            ids = [i for i in rows_ if i in out.data.index]
            entry["row_numbers"] = [int(out.data.index.get_loc(i)) for i in ids]
            states = {str(out.states.at[i, c]) for i in ids for c in entry["columns"]
                      if c in out.states.columns}
            return {**entry, "rows": [_plain(i) for i in ids],
                    "state": _worst(states, out.meta.get("stale")), "values": {}}
        lookup = _row_lookup(out.data)           # exact: 1 is not "1"
        match = row_id if row_id is not None and row_id in lookup else None
        if match is None:
            return {**entry, "state": "missing", "values": {}}
        input_id = lookup[match]
        entry["row"] = int(out.data.index.get_loc(input_id))   # its "#" in that step
        cols_ = [c for c in entry["columns"] if c in out.data.columns]
        states = {str(out.states.at[input_id, c]) for c in cols_} or {str(out.row_states[input_id])}
        shown = cols_[:self.INPUT_VALUES_SHOWN]
        return {**entry, "id": _plain(input_id), "state": _worst(states, out.meta.get("stale")),
                "values": {str(c): _plain(out.data.at[input_id, c]) for c in shown},
                "more": len(cols_) - len(shown)}

    def _reference_entry(self, ref: StepRef, argument: str) -> dict:
        """A ``$ref`` argument or setting: the cells it selects from its step."""
        upstream = self.steps.get(ref.id)
        if upstream is None or upstream.output.meta.get("staged"):
            return {"step": ref.id, "id": None, "columns": [], "argument": argument,
                    "state": "pending", "values": {}}
        out = upstream.output
        try:
            block = _apply_selection(out.data, ref.rows, ref.columns, ref.id)
        except SelectionError as exc:
            return {"step": ref.id, "id": None, "columns": [], "argument": argument,
                    "state": "missing", "values": {}, "because": str(exc)}
        ids, cols_ = list(block.index), [str(c) for c in block.columns]
        states = {str(out.states.at[i, c]) for i in ids for c in cols_}
        entry = {"step": ref.id, "columns": cols_, "argument": argument,
                 "state": _worst(states, out.meta.get("stale"))}
        positions = [int(out.data.index.get_loc(i)) for i in ids]
        if len(ids) == 1:
            row = ids[0]
            entry.update({"id": _plain(row), "row": positions[0],
                          "values": {c: _plain(block.at[row, c]) for c in cols_[:self.INPUT_VALUES_SHOWN]}})
        else:
            entry.update({"id": None, "rows": [_plain(i) for i in ids],
                          "row_numbers": positions, "values": {}})
        return entry

    def _carry_zip_states(self, step: Step) -> None:
        """Give a zip's cells the states of the cells they came from (009 §2).

        A cell that failed (or was blocked) in its own step is ``blocked`` here,
        with that cell as its cause: the zip didn't fail, its input did, so it
        never stops the run a second time.
        """
        out = step.output
        picked = out.data.attrs.get("zip_picked")
        if not picked:
            return
        states = out.states.copy()
        notes: dict = {}
        seen: set = set()
        for g, ids in zip(step.operation.inputs, picked):
            source = self.steps[str(g)].output
            for column in source.data.columns:
                if column in seen or column not in states.columns:
                    continue
                seen.add(column)
                for row_id, from_id in zip(out.data.index, ids):
                    state = str(source.states.at[from_id, column])
                    if state == "absent":
                        states.at[row_id, column] = "absent"
                    if state in ("failed", "blocked"):
                        states.at[row_id, column] = "blocked"
                        note = source.notes.get(from_id, {})
                        notes.setdefault(row_id, {
                            "error": f"upstream cell {g}[{from_id}] failed",
                            "cause": note.get("cause") or f"{g}[{from_id}]: {note.get('error')}"})
        out.states = states
        if notes:
            out.meta["notes"] = notes
        out.data.attrs.pop("zip_picked", None)

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

    def _failed_argument(self, operation: Operation,
                         paired: Any = ()) -> tuple[str, str] | None:
        """An argument that reads a step with a failed cell: (error, root cause).

        008 C10: an argument is passed whole, so one failed cell in it fails
        every row that would receive it — without calling the tool. A column
        paired row by row (*paired*) blocks only the rows its failed cells meet.
        """
        for name, value in operation.arguments.items():
            if not isinstance(value, StepRef) or name in paired:
                continue
            step = self.steps.get(str(value))
            if step is None or step.output.meta.get("staged"):
                continue
            failed = step.output.ids_in("failed", "blocked")
            if failed:
                index = failed[0]
                note = step.output.notes.get(index, {})
                return (f"argument {name!r} reads {step.name}, which has a failed "
                        f"cell {step.name}[{index}]",
                        note.get("cause") or f"{step.name}[{index}]: {note.get('error')}")
        return None

    # ── running ──────────────────────────────────────────────────────────
    def pending(self, step_id: str) -> list[str]:
        """The steps *step_id* reads that have not run yet, nearest first."""
        waiting: list[str] = []
        for name in dict.fromkeys(str(r) for r in self.steps[step_id].operation.reads):
            upstream = self.steps.get(name)
            if upstream is not None and upstream.output.meta.get("staged"):
                waiting.extend(self.pending(name))
                waiting.append(name)
        return list(dict.fromkeys(waiting))   # once each: an input and a column of it

    def upstream(self, step_id: str) -> list[str]:
        """Every step *step_id* depends on, directly or not, in workflow order."""
        seen: set[str] = set()
        frontier = [step_id]
        while frontier:
            for name in self._depends_on(frontier.pop()):
                if name in self.steps and name not in seen:
                    seen.add(name)
                    frontier.append(name)
        return [name for name in self.steps if name in seen]

    def not_current(self, step_id: str) -> list[str]:
        """The steps *step_id* depends on, directly or not, that aren't
        current now: never run, or stale. In workflow order. Staleness isn't
        passed down the chain, so a step can turn stale once a step before it
        re-runs: :meth:`Kernel.run` asks each in turn (C9)."""
        return [name for name in self.upstream(step_id)
                if self.steps[name].state in ("staged", "stale")]

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
                            for m in operation.modifiers for v in m.settings.values())
        conditions = any(_uses_lineage((m.settings.get("rows") or {}).get("where"))
                         for m in operation.modifiers if isinstance(m.settings.get("rows"), dict)) \
            or any(m.kind == "copy" for m in operation.modifiers)
        if operation.bound_to is None and not settings_refs and not conditions and not any(
                isinstance(v, (StepRef, ResRef)) for v in operation.arguments.values()):
            return operation
        fn_for_types = operation.fn \
            or BUILTIN_TOOLS.get(operation.tool)
        try:
            annotations = {k: p.annotation
                           for k, p in _signature(fn_for_types).parameters.items()}
        except (TypeError, ValueError):
            annotations = {}
        resolved = {}
        for name, value in operation.arguments.items():
            if isinstance(value, StepRef):
                data = _apply_selection(self.steps[str(value)].output.data,
                                        self._with_lineage(value.rows, value.id),
                                        value.columns, value.id)
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
            fn = getattr(instance, operation.tool.rsplit(".", 1)[-1])
        modifiers = tuple(
            Modifier(m.kind, {**{k: (_ref_value(_apply_selection(
                                      self.steps[v.id].output.data, v.rows,
                                      v.columns, v.id), None, v.id)
                                  if isinstance(v, StepRef) else
                                  self._with_lineage(v, str(operation.input))
                                  if k == "rows" and operation.input is not None else v)
                              for k, v in m.settings.items()},
                           # copy reads lineage as shown (CA-D): the input's
                           **({"lineage": self.lineage(str(operation.input))}
                              if m.kind == "copy" and operation.input is not None else {})})
            for m in operation.modifiers)
        return Operation(operation.tool, modifiers, resolved,
                         fn, operation.input)

    # ── a typed row number, saved as the row's lineage (S5d, CA-B1) ───────
    def _resolve_picks(self, operation: Operation) -> Operation:
        """*operation* with each typed row number (or list of them) written as
        the rows' lineage, where the picked step has run (S5-D3: else later)."""
        changed = False
        modifiers = []
        for m in operation.modifiers:
            rows_ = m.settings.get("rows")
            if m.kind == "select" and operation.input is not None and rows_ is not None:
                named = self._as_lineage(rows_, str(operation.input))
                if named is not rows_:
                    m, changed = Modifier(m.kind, {**m.settings, "rows": named}), True
            modifiers.append(m)
        arguments = {}
        for name, value in operation.arguments.items():
            if isinstance(value, StepRef) and value.rows is not None:
                named = self._as_lineage(value.rows, value.id)
                if named is not value.rows:
                    value, changed = replace(value, rows=named), True
            arguments[name] = value
        if not changed:
            return operation
        return replace(operation, modifiers=tuple(modifiers), arguments=arguments)

    def _as_lineage(self, row_sel: Any, step_id: str) -> Any:
        """``{"where": …, "named": True}`` for a row number or a list of them in
        *step_id*; *row_sel* itself when it can't be (not run yet, a source, a
        row out of range, no lineage that names it alone)."""
        ints = row_sel if isinstance(row_sel, list) else [row_sel]
        if not ints or not all(isinstance(i, int) and not isinstance(i, bool) for i in ints):
            return row_sel
        step = self.steps.get(step_id)
        if step is None or step.output.meta.get("staged") or not step.valid:
            return row_sel
        data = step.output.data
        n = len(data)
        if not all(-n <= i < n for i in ints) or len({i % n for i in ints}) < len(ints):
            return row_sel                       # out of range, or a row twice: refused, saying so
        lineage = self.lineage(step_id)
        trees = []
        for i in ints:
            tree = self._identity(step_id, i % n, data, lineage)
            if tree is None:
                return row_sel
            trees.append(tree)
        return {"where": trees[0] if len(trees) == 1 else {"or": trees}, "named": True}

    def _identity(self, step_id: str, position: int, data: pd.DataFrame, lineage: dict) -> dict | None:
        """A condition that picks row *position* of *step_id* alone: a group's
        key, else its lineage to the steps rows start in (with ``.idx``)."""
        candidates = []
        groups = [s for s in (step_id, *(n[len(ROW_ID):].split(".")[0] for n in lineage))
                  if s in self.steps and self._kind(s) == "collapse"]
        for s in groups:
            by = self.steps[s].output.meta.get("by")
            if by and by in data.columns and not is_id_column(by):
                value = _plain(data[by].iloc[position])
                if isinstance(value, (str, int, float, bool)):
                    candidates.append({"test": "==", "on": {"col": by}, "value": value})
                    break
        tests = []
        for name, cells in lineage.items():
            ancestor, _, rest = name[len(ROW_ID):].partition(".")
            value = cells[position]
            if rest == "idx":
                tests.append({"test": "==", "on": {"row": ancestor, "idx": True}, "value": value})
            elif not rest and not self.lineage(ancestor) and (value is None or isinstance(value, int)):
                tests.append({"test": "==", "on": {"row": ancestor}, "value": value})
        if tests:
            candidates.append(tests[0] if len(tests) == 1 else {"and": tests})
        for tree in candidates:
            try:
                keep = _where(data, tree, lineage, step_id)
            except SelectionError:
                continue
            if keep.count(True) == 1 and keep[position]:
                return tree
        return None

    def _with_lineage(self, row_sel: Any, step_id: str) -> Any:
        """A condition that tests ``row[…]``, with the lineage of the step it
        picks from (S5c); anything else unchanged."""
        if not (isinstance(row_sel, dict) and _uses_lineage(row_sel.get("where"))):
            return row_sel
        return {**row_sel, "lineage": self.lineage(step_id), "step": step_id}

    def run(self, step_id: str, tools: dict[str, Callable] | None = None,
            resources: Mapping[str, Any] | None = None) -> Step:
        """Execute one step; record its version and the versions it read (009 §5).

        See :meth:`_run_step` for how a step runs. Afterwards its output carries
        ``version`` (a hash of its data) and ``read`` (``{step: version}`` for
        every step it read, ``{"res:name": …}`` for resources), and every step
        is re-checked for staleness from those stamps.
        """
        if tools is None and self.catalog is not None:
            tools = self.catalog.functions
        step = self.steps[step_id]
        self._ask_data_versions(step.operation, resources)
        read = self._run_reads(step_id) if step_id in self.steps else {}
        # Inputs that are stale as this runs pass through as they are; this
        # output is then up to date with them, and says it read them stale.
        read_stale = {name: self.steps[name].output.meta.get("stale_reason")
                      for name in read if name in self.steps
                      and self.steps[name].output.meta.get("stale")}
        before = step.output
        result = self._run_step(step_id, tools, resources)
        out = self.steps[step_id].output
        if out is not before and self._kind(step_id) == "source":
            self._keep_row_ids(step_id, before)           # its tool gave new rows: D-picks
        if not out.meta.get("staged"):
            out.meta["version"] = _data_version(out.data)
            out.meta["run_key"] = self.run_key(step_id, read)
            self._file(step_id)
            unversioned = _unversioned(out.data)
            if unversioned:                       # D57: said, with the fix
                names = ", ".join(unversioned)
                self.steps[step_id].warnings = tuple(dict.fromkeys([
                    *self.steps[step_id].warnings,
                    Problem(f"{names} {'has' if len(unversioned) == 1 else 'have'} no stable "
                            f"version: the steps that read {step_id!r} re-run each time; "
                            f"give {unversioned[0]} a data_version()", "run_warning",
                            step=step_id, severity="warning")]))
            if not (step.operation.shape_verb and step.operation.shape_verb.kind == "source"
                    and is_identity(step.operation.fn)):
                out.meta["read"] = read
            # What these values were computed with, so a stale value can say so
            # once the arguments are edited (009): one record per step.
            out.meta["ran_with"] = _ran_with(step.operation)
            tool_hash = self._tool_hash(step.operation)
            if tool_hash is not None:
                out.meta["tool_hash"] = tool_hash
            if read_stale:
                out.meta["read_stale"] = read_stale
            else:
                out.meta.pop("read_stale", None)
            # 010 C25: for row-aligned steps, a hash of each input row's read
            # columns, so editing one row makes only its cells stale.
            row_reads = self._row_reads(step)
            if row_reads is not None:
                out.meta["row_reads"] = row_reads
            out.meta.pop("stale", None)
        self._mark_stale_dependents(step_id)
        return result

    def _run_step(self, step_id: str, tools: dict[str, Callable] | None = None,
                  resources: Mapping[str, Any] | None = None) -> Step:
        """Run one step (:meth:`_run_step_body`), then say how to go back from
        what it produced (reshaping.md §7): every branch passes here."""
        step = self._run_step_body(step_id, tools, resources)
        if not step.output.meta.get("empty"):
            step.output.meta["inverse"] = self.inverse(step_id)
        return step

    def _run_step_body(self, step_id: str, tools: dict[str, Callable] | None = None,
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
            tool = (step.operation.fn
                    or BUILTIN_TOOLS.get(step.operation.tool))
            if not is_identity(tool):
                # A tool source computes its grid from a no-input tool.
                try:
                    step.output = self._resolve_arguments(
                        step.operation, resources).run(None, tools)
                except SelectionError as exc:
                    # A table it can't take (a `#` column): the step fails with
                    # the reason, like every other failure; it never raises.
                    step.output = _failed_output(step.operation, str(exc))
                    self._restage_after(step_id)
                    return step
                failure = self._source_records(step)
                if failure:
                    step.output = _failed_output(step.operation, failure, "declared")
                    self._restage_after(step_id)
                    return step
                mismatch = _output_mismatch(step.operation, step.output.data)
                if mismatch:
                    step.output = _failed_output(step.operation, mismatch,
                                                 mismatch_where(mismatch))
                self._restage_after(step_id)
                return step
            # A literal source holds its data, so running one is a no-op — unless
            # it was reloaded without payloads and has nothing to hold.
            if step.output.meta.get("empty"):
                return step                       # nothing to run yet (G17)
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
            frames = []
            for g in step.operation.inputs:
                frame = rows(self.steps[str(g)].output).copy(deep=False)
                frame.attrs["name"] = str(g)        # so an error can name it
                frames.append(frame)
            if step.operation.tool == "zip":
                # Which rows of each input the others' rows came from, by
                # following `#` columns: never by reading the ids (§5.1).
                for frame in frames:
                    frame.attrs["traces"] = {
                        j: self.trace(frame.attrs["name"], list(frame.index), other.attrs["name"])
                        for j, other in enumerate(frames) if other is not frame}
            on = step.operation.arguments.get("on") if step.operation.tool == "join" else None
            if isinstance(on, str) and is_id_column(on):
                # a join on lineage (S5e): each side's row numbers in the step it names
                target = self._id_source(on) or on[len(ROW_ID):]
                for frame in frames:
                    name = frame.attrs["name"]
                    if name == target:
                        values = list(range(len(frame)))
                    elif self.aligned(name, target):
                        # its rows are target's, in any order: their numbers there, by id
                        at = {str(i): n for n, i in enumerate(self.steps[target].output.data.index)}
                        values = [at.get(str(i)) for i in frame.index]
                    else:
                        values = self.lineage(name).get(on)
                    if values is None or any(isinstance(v, list) for v in values):
                        frame.attrs["on_problem"] = (     # the step fails with it, below
                            f"join on {on!r}: {name!r} has no lineage {on}" if values is None
                            else _group_join_refusal(on, name))
                        break
                    frame.attrs["on_values"] = values
            try:
                step.output = _run_combine(step.operation, frames)
                if step.operation.tool == "zip":
                    self._carry_zip_states(step)
            except (ValueError, TypeError, KeyError) as exc:
                # A zip_ that would drop rows, a join on a missing key, a key
                # holding lists (V6): the step fails with the reason, never raises.
                why = str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)
                if isinstance(exc, KeyError):
                    why = f"{step.operation.tool} needs a column {why} that an input doesn't have"
                if isinstance(exc, TypeError) and "unhashable" in why:
                    why = (f"{step.operation.tool}: a key column holds values that can't "
                           f"be matched, such as lists ({why}); keys are single values (V6)")
                step.output = _failed_output(step.operation, why)
            self._restage_after(step_id)
            return step
        # K19: a column argument a row-wise verb takes one value from is
        # paired with the input by row id: it joins the input as a column.
        paired = _paired_arguments(step.operation, self)
        to_resolve = step.operation
        if paired:
            to_resolve = replace(step.operation, arguments={
                k: v for k, v in step.operation.arguments.items() if k not in paired})
        try:
            resolved = self._resolve_arguments(to_resolve, resources)
            source = self._input_for(resolved)
            unpaired = source
            if paired and source is not None:
                source = self._with_paired_columns(source, paired)
        except SelectionError as exc:
            step.output = _failed_output(step.operation, str(exc))
            self._restage_after(step_id)
            return step
        chosen = None
        if _is_auto(resolved):
            # 008 N: the verb is picked from the data the step really gets.
            resolved, kind, why = _resolve_auto(resolved, source)
            chosen = {"verb": kind, "reason": why, "provisional": False}
        bad_argument = self._failed_argument(step.operation, paired)
        if bad_argument is not None and source is not None:
            # Every row is blocked: hand the verb an input that says so.
            source = Output(source.data, source.states,
                            {**source.meta, "blocked_all": bad_argument})
        declared = self._declared_fields(step.operation) if not (
            step.operation.shape_verb and step.operation.shape_verb.settings.get("columns")) else None
        if declared and source is not None:                # G9: widen the declared fields
            resolved = replace(resolved, modifiers=tuple(
                Modifier(m.kind, {**m.settings, "columns": declared}) if m.kind == "widen" else m
                for m in resolved.modifiers))
        restore = self._restore_column(step_id)
        if restore is not None and source is not None:
            source = Output(source.data, source.states, {**source.meta, "restore": restore})
        group_by = self._groups_by_step(step_id)
        if group_by is not None and source is not None:
            by, s = group_by
            keys = self.trace(str(step.operation.input), list(source.data.index), s) or []
            source = Output(source.data, source.states, {**source.meta, "group": {
                "by": by, "keys": keys, "all": list(self.steps[s].output.data.index)}})
        if paired:
            # bound to a column on purpose: the tool gets it even where the
            # parameter has a default, which no column fills by name (L50c)
            resolved = replace(resolved, arguments={**resolved.arguments,
                                                    **{name: FROM_ROW for name in paired}})
        unnamed = resolved
        resolved = named_after_step(resolved, self, step_id)            # D9
        try:
            step.output = resolved.run(source, tools)
            if resolved is not unnamed:
                _mapping_keeps_value(step.output, step_id, source)
            if paired and unpaired is not None:
                _unpair(step.output, unpaired, paired)
            step.output.data = _str_columns(step.output.data, step_id)
            _spread_record(resolved, step.output)
            _spread_dict(resolved, step.output)
            _apply_naming(resolved, step.output, step_id, self.default_name_rule(resolved))
            _carry_id_columns(resolved, source, step.output)
            found = step.output.meta.pop("warnings", None) or []
            for read in dict.fromkeys(str(g) for g in step.operation.reads):
                upstream = self.steps.get(read)
                if upstream is not None and upstream.output.meta.get("stale"):
                    found.append(f"read {read!r} while it's stale (version "
                                 f"{upstream.output.version}): an earlier step changed since "
                                 f"{read!r} ran; run it first for current values")
            if step.output.meta.get("matched_nothing"):     # CA-5: zero rows, said
                found.append(step.output.meta["matched_nothing"])
            defaulted = [i for i, n in step.output.notes.items()
                         if n.get("caught") and str(step.output.row_states.get(i)) == "known"]
            if defaulted:                         # G7: a default stood in for a result
                found.append(f"{len(defaulted)} row{'s' if len(defaulted) != 1 else ''} "
                             f"used try_except's default; the notes keep the errors")
            if found:                             # said while running (J-D3)
                step.warnings = tuple(dict.fromkeys(
                    [*step.warnings, *(Problem(w, "run_warning", step=step_id, severity="warning")
                                        for w in found)]))
            mismatch = _output_mismatch(step.operation, step.output.data)
            if mismatch:
                raise _PlanBroken(mismatch)
        except (SelectionError, KeyError, TypeError, ValueError) as exc:
            where = mismatch_where(str(exc)) if isinstance(exc, _PlanBroken) else None
            # 008 C7: a position out of range, a column that is gone — the step
            # fails with the reason, never None, NaN or an empty grid. A TypeError
            # here is core's own reshaping (a tool's is caught per row): a sort,
            # group or match key holding lists or dicts (V6).
            why = str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)
            if isinstance(exc, TypeError):
                why = (f"{step.operation.shape_verb.kind if step.operation.shape_verb else 'step'}: "
                       f"{why}. A column used to sort, group or match must hold single "
                       f"values, not lists or dicts (V6)")
            step.output = _failed_output(step.operation, why, where)
        if chosen is not None:
            step.output.meta["auto"] = chosen
        self._restage_after(step_id)
        # 008 C10.5 / 009 §6: what already read this step is re-checked for
        # staleness by `run`, from the versions it read.
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
            due = set(remaining) - done
            ready = [sid for sid in remaining
                     if all(w in done for w in self.pending(sid))
                     # after every step it depends on that is still to run this
                     # time, including collapse(by="#s")'s s: a reader never
                     # runs on an output about to change
                     and not any(d in due for d in self._depends_on(sid))]
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

    def _depends_on(self, step_id: str) -> list[str]:
        """The steps *step_id* reads, and for ``collapse(by="#s")`` its ``s``."""
        found = [str(r) for r in self.steps[step_id].operation.reads]
        grouped = self._groups_by_step(step_id)
        if grouped is not None:
            found.append(grouped[1])
        return [d for d in found if d != step_id]

    def _restage_after(self, step_id: str) -> None:
        """Re-stage everything downstream of *step_id* — cardinality sharpened.

        Transitively: a chain ``a → b → c`` learns its counts all the way down,
        because ``b``'s freshly staged index is what lets ``c`` stage. Repeats
        until nothing changes rather than assuming declaration order is
        topological.
        """
        changed, waves = {step_id}, 0
        place = {name: n for n, name in enumerate(self.steps)}
        while changed:
            waves += 1
            if waves > len(self.steps) + 1:
                # forward only, so each wave reaches later steps than the last:
                # more waves than steps means a loop, a bug, said, not a hang
                raise RuntimeError(f"re-checking after {step_id!r} doesn't settle: "
                                   f"{', '.join(sorted(changed))} keep changing")
            wave: set[str] = set()
            for other in self.steps.values():
                if other.name in changed:
                    continue
                # everything it depends on: inputs, references, and the step a
                # collapse(by="#s") groups by (a by-step turned invalid at run).
                # Earlier steps only: a step reads only earlier steps, and one
                # that names a later step (a problem on it) mustn't be re-checked
                # by it, or the two re-check each other forever.
                if not any(name in changed and place.get(name, -1) < place[other.name]
                           for name in self._depends_on(other.name)):
                    continue
                if not other.output.meta.get("staged"):
                    # G13: a step that has run keeps its output (shown, stale
                    # if its input's data changed), but is re-checked against
                    # the input as it is now: a column it needs may be gone.
                    problems = check(other.operation, self, other.name)
                    if problems != other.problems:
                        other.problems = problems
                        wave.add(other.name)
                    other.warnings = warn(other.operation, self, other.name)
                    continue
                # Re-check too (008 K1): a column check that was deferred, or
                # one that failed against a guess, is decided now that the
                # input is real. Invalid steps are included — they may be
                # valid now.
                before = (other.output.meta.get("expected"), other.problems,
                          predicted_columns(other.output),
                          columns_unknown(other.output),
                          (other.output.meta.get("plan") or {}).get("types"))
                other.operation = self._resolve_picks(other.operation)   # S5-D3
                other.operation = bind_by_type(other.operation, self, other.name)   # S3, its input planned
                other.problems = check(other.operation, self, other.name)
                other.output = stage(other.operation, self, other.problems, other.name)
                other.warnings = warn(other.operation, self, other.name)
                after = (other.output.meta.get("expected"), other.problems,
                         predicted_columns(other.output),
                         columns_unknown(other.output),
                         (other.output.meta.get("plan") or {}).get("types"))
                # planned types too: a reader's type check depends on them
                if after != before:
                    wave.add(other.name)
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
        return self.spec.to_dict()

    @property
    def spec(self) -> "WorkflowSpec":
        """The workflow's saved form: step specs in order, resource specs and
        extras. The declarations, never the objects or the outputs."""
        return WorkflowSpec(tuple(st.spec for st in self.steps.values()),
                            tuple(decl.spec for decl in self.resources.values()),
                            _checked_extras(self.extras))

    @classmethod
    def from_spec(cls, spec: "WorkflowSpec", catalog: "Catalog | None" = None) -> "Workflow":
        """A workflow built from *spec*, checked against *catalog*."""
        return cls.from_dict(spec.to_dict(), catalog=catalog)

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
                  resource_types: dict[str, type] | None = None, *,
                  catalog: "Catalog | None" = None, naming: Any = None) -> "Workflow":
        """Rebuild a Workflow from either export — all at once.

        Every step goes through the same :func:`check` and :func:`stage` the
        incremental path uses, so loading cannot smuggle in a step that
        declaring would have rejected. *resource_types* maps a saved resource
        type name to its class, as *tools* does for tools; types registered with
        :func:`resource` (or used by ``define``) are found without it.

        With *catalog*, tools and resource types come from it alone, and every
        step is checked against it.
        """
        version = blob.get("version")
        if not isinstance(version, int) or version > FORMAT_VERSION:
            # 008 K17: an older core must refuse a newer file, never strip it.
            raise ValueError(
                f"this workflow was saved in format version {version!r}; this "
                f"core reads version {FORMAT_VERSION}. Upgrade "
                "simple-steps-core to load it.")
        if version < FORMAT_VERSION:
            # Decided 2026-10-26: files from before the redesign aren't loaded.
            raise ValueError(
                f"this workflow was saved in format version {version}, before "
                f"the redesign; this core reads version {FORMAT_VERSION} only. "
                "Rebuild it and save it again.")
        workflow = cls(catalog=catalog, naming=naming)
        if catalog is not None:
            tools, known = catalog.functions, catalog.resource_types
        else:
            known = dict(resource_types or {})
        for name, entry in (blob.get("resources") or {}).items():
            workflow.resources[name] = Resource(
                name, known.get(entry["type"]), dict(entry.get("settings") or {}),
                entry["type"], entry.get("source", "defined"),
                dict(entry.get("extras") or {}))
        workflow.extras = dict(blob.get("extras") or {})
        for entry in blob["steps"]:
            sid = entry["name"]
            if "literal" in entry:
                # A literal is the step's recipe: the step comes back with it.
                workflow.steps[sid] = cls._literal_step(
                    sid, _decode_argument(entry["literal"]["value"]),
                    dict(entry.get("extras") or {}))
                continue
            operation = _attach_bound(
                Operation.from_dict(entry["operation"], tools), workflow.resources)
            if catalog is not None:
                operation = catalog.admit(operation)
            problems = check(operation, workflow, sid)
            workflow.steps[sid] = Step(sid, operation,
                                       stage(operation, workflow, problems, sid),
                                       problems, warn(operation, workflow, sid),
                                       dict(entry.get("extras") or {}))
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
                  resource_types: dict[str, type] | None = None, *,
                  catalog: "Catalog | None" = None) -> "Workflow":
        import json
        return cls.from_dict(json.loads(data), tools, resource_types, catalog=catalog)

    def validate(self) -> dict[str, tuple[str, ...]]:
        """Every step's problems, keyed by step id — empty tuples for the good ones."""
        return {sid: step.problems for sid, step in self.steps.items()}

    def __repr__(self) -> str:
        return f"<Workflow {len(self.steps)} step(s): {list(self.steps)}>"


def _short_hash(value: Any) -> str:
    """A 16-digit hash of plain data, the same in every process."""
    text = json.dumps(value, sort_keys=True, default=repr)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _carry_id_columns(operation: Operation, source: Any, output: Output) -> None:
    """Give a step that keeps ids its input's `#` columns (reshaping.md §5.1).

    In one place, so no verb has to remember. A `#` column the step names
    itself (dropped, or renamed into a variable) is the step's choice and
    isn't put back.
    """
    verb = operation.shape_verb
    if verb is None or not keeps_ids(verb.kind, verb) or not isinstance(source, Output):
        return
    named = set(verb.settings.get("columns") or ()) if verb.kind in ("drop", "rename") else set()
    frame = source.data
    carried = {c: frame[c] for c in frame.columns
               if is_id_column(c) and c != ROW_ID and c not in output.data.columns
               and c not in named}
    if carried:
        output.add_id_columns(carried)
    # Absent cells stay absent in the columns a step carries (reshaping.md §9.1).
    rename = verb.settings.get("columns") if verb.kind == "rename" else None
    back = {new: old for old, new in rename.items()} if isinstance(rename, dict) else {}
    gaps: dict = {}
    for i, c in source.absent_cells():
        name = next((n for n, o in back.items() if o == c), c) if back else c
        if name in output.data.columns and i in output.data.index and not (
                verb.kind in ("map", "group") and name not in source.data.columns):
            gaps.setdefault(name, []).append(i)
    output.mark_absent(gaps)



def _unpair(output: Output, unpaired: Output, paired: dict) -> None:
    """Take a verb's paired arguments back out of its output (C3).

    A column argument joins the input as a column so the tool gets one value a
    row (K19); a verb that carries its input's columns (``filter``, ``group``)
    would hand it on. A column it added goes; an input column it covered gets
    its own values back, so ``filter(v, temp=wf["f"][cols["value"]])`` keeps
    ``v``'s temperatures."""
    data, states = output.data, output.states
    for name in paired:
        if name not in data.columns:
            continue
        if name in unpaired.data.columns:
            rows_ = [i for i in data.index if i in unpaired.data.index]
            if len(rows_) == len(data.index):
                data[name] = unpaired.data[name].reindex(data.index)
                if name in states.columns and name in unpaired.states.columns:
                    states[name] = unpaired.states[name].reindex(data.index)
        elif name != output.meta.get("value_column"):
            data.drop(columns=[name], inplace=True)
            if name in states.columns:
                states.drop(columns=[name], inplace=True)

# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .system_tools import (  # noqa: E402
    BUILTIN_TOOLS,
    DEFAULT_TOOL,
    _base,
    identity,
    is_identity,
)
from .catalog import (  # noqa: E402
    Catalog,
    _checked_extras,
    Resource,
    _attach_bound,
    _settings,
    _signature,
    resource,
    resource_problems,
)
from .checks import (  # noqa: E402
    _group_join_refusal,
    _paired_arguments,
    ROWS_RULE,
    ROW_ALIGNED,
    _is_tool_verb,
    _output_mismatch,
    mismatch_where,
    _plan_markers,
    _source_column,
    _worst,
    check,
    columns_unknown,
    predicted_columns,
    stage,
    bind_by_type,
    named_after_step,
    spreads_dict,
    warn,
    keeps_ids,
    _tool_parameters,
)
from .combines import _row_lookup, _run_combine, is_combine, own_id_columns  # noqa: E402
from .errors import PayloadError, PlanBroken as _PlanBroken, ResourceNotLoaded, SelectionError, StepFailed  # noqa: E402
from .problems import Problem  # noqa: E402
from .values import _record_fields, named_columns, record_return, source_record, source_rows  # noqa: E402
from .modifiers import (  # noqa: E402
    FROM_ROW,
    MODIFIERS,
    NAMED_VERBS,
    Modifier,
    is_shape,
    mod,
)
from .operation import Operation, _src  # noqa: E402
from .output import (  # noqa: E402
    _state_column,
    Output,
    ROW_ID,
    _data_version,
    _unversioned,
    _failed_output,
    _str_columns,
    _uncaught_failure,
    is_id_column,
    VALUE_COLUMN,
    variables,
    _typed,
)
from .references import (  # noqa: E402
    ResRef,
    StepRef,
    ToolRef,
    _UNKNOWN,
    _apply_selection,
    _check_caller_scope,
    _uses_lineage,
    _where,
    rows,
)
from .run import _is_auto, _resolve_auto  # noqa: E402
from .specs import WorkflowSpec  # noqa: E402
from .step import (  # noqa: E402
    NO_LITERAL,
    Step,
    _changes_text,
    _ran_with,
    _row_fps,
)
from .values import (  # noqa: E402
    _decode_argument,
    _encode_argument,
    _literal_problem,
    FORMAT_VERSION,
    _decode_output,
    _dtype_type,
    _encode_output,
    _json_safe,
    _plain,
    _ref_value,
    _type_name,
    _value_fits,
)
from .verbs import grid, source_  # noqa: E402


def _spread_record(operation: Operation, output: Output) -> None:
    """A declared record type spreads into one column per field, in declared
    order (G8, outputs-and-reshaping.md §3, §5). One name (``mod.name("b")``)
    keeps it in one cell. Each row is held to the declaration cell by cell."""
    verb = operation.shape_verb
    kind = verb.kind if verb is not None else None
    if kind == "auto":
        kind = (output.meta.get("auto") or {}).get("verb")
    declared = record_return(kind, operation.fn)
    column = output.meta.get("value_column")
    if declared is None or column not in output.data.columns or operation.naming is not None:
        return                                   # one name keeps the record in one cell
    cls, optional = declared
    fields = list(_record_fields(cls))
    data, states = output.data, output.states
    notes = dict(output.meta.get("notes") or {})
    values = {f: [] for f in fields}
    failed: dict = {f: [] for f in fields}
    extra: dict = {}
    for i in data.index:
        record, state = data.at[i, column], str(states.at[i, column])
        if state != "known":
            for f in fields:
                values[f].append(None)
            continue
        if record is None:
            for f in fields:
                values[f].append(None)
                if not optional:
                    failed[f].append(i)
            if not optional:
                notes[i] = {**notes.get(i, {}), "error": f"returned None; declared {cls.__name__}"}
            continue
        get = (record.get if isinstance(record, dict) else lambda f, r=record: getattr(r, f, _MISSING))
        have = record if isinstance(record, dict) else {}
        for k_ in have:
            if k_ not in fields:
                extra[k_] = extra.get(k_, 0) + 1
        missing = []
        for f in fields:
            v = get(f, _MISSING) if isinstance(record, dict) else get(f)
            if v is _MISSING:
                values[f].append(None)
                failed[f].append(i)
                missing.append(f)
            else:
                values[f].append(v)
        if missing:
            notes[i] = {**notes.get(i, {}), "error": f"missing field {', '.join(map(repr, missing))}"}
    at = list(data.columns).index(column)
    left, right = list(data.columns)[:at], list(data.columns)[at + 1:]
    new = data[left].copy()
    new_states = states[left].copy()
    for f in fields:
        new[f] = _typed(values[f], data.index)
        new_states[f] = states[column]
    for c in right:
        new[c], new_states[c] = data[c], states[c]
    for f, ids in failed.items():
        for i in ids:
            new_states.at[i, f] = "failed"
    output.data, output.states = new, new_states
    output.meta["notes"] = notes
    output.meta["value_column"] = fields[0] if len(fields) == 1 else None
    if extra:
        output.meta.setdefault("warnings", []).extend(
            f"{n} row{'s' if n != 1 else ''} returned a field {f!r} that {cls.__name__} "
            f"doesn't declare: dropped" for f, n in extra.items())


_MISSING = object()


def _hashable(value: Any) -> bool:
    try:
        hash(value)
    except TypeError:
        return False
    return True

#: Verbs whose output rows are their input's rows, in order (core-asks §M3, aligned).
_ONE_TO_ONE = frozenset({"map", "group", "rename", "copy", "drop", "widen", "pack"})
_SNAKE = re.compile(r'^[a-z0-9]+(_[a-z0-9]+)*$')
_CAMEL = re.compile(r'^[a-z][a-zA-Z0-9]*$')


def _apply_naming(operation: Operation, output: Output, step_id: str,
                  default: dict | None = None) -> None:
    """``mod.name`` as a list, a mapping or a pattern (G12), after the run: a
    list spreads a sequence by position, a mapping renames fields, a pattern
    renames each column the step wrote. A single name went to the verb."""
    rule = operation.name_rule or default
    if rule is None or operation.naming is not None:
        return
    verb = operation.shape_verb
    kind = verb.kind if verb is not None else None
    if kind == "auto":
        kind = (output.meta.get("auto") or {}).get("verb")
    declared = record_return(kind, operation.fn)
    written = list(_record_fields(declared[0])) if declared else (
        [output.meta.get("value_column")] if output.meta.get("value_column") else [])
    written = [c for c in written if c in output.data.columns]
    if not written:
        return
    to = rule.get("to")
    if isinstance(to, list) and len(written) == 1:
        # a sequence, spread by position: a row of the wrong length fails
        column, data, states = written[0], output.data, output.states
        notes = dict(output.meta.get("notes") or {})
        at = list(data.columns).index(column)
        new, new_states = data.iloc[:, :at].copy(), states.iloc[:, :at].copy()
        values = {n: [] for n in to}
        bad = []
        for i in data.index:
            cell, state = data.at[i, column], str(states.at[i, column])
            ok = state == "known" and isinstance(cell, (list, tuple)) and len(cell) == len(to)
            if state == "known" and not ok:
                got = len(cell) if isinstance(cell, (list, tuple)) else 1
                bad.append(i)
                notes[i] = {**notes.get(i, {}), "error": f"returned {got} values for {len(to)} names"}
            for n, k_ in enumerate(to):
                values[k_].append(cell[n] if ok else None)
        for k_ in to:
            new[k_] = _typed(values[k_], data.index)
            new_states[k_] = states[column]
            for i in bad:
                new_states.at[i, k_] = "failed"
        for c in list(data.columns)[at + 1:]:
            new[c], new_states[c] = data[c], states[c]
        output.data, output.states = new, new_states
        output.meta["notes"] = notes
        written = list(to)
        rule = {"pattern": rule.get("pattern")}
    final = named_columns(rule, written, step_id, operation.tool)
    rename = {old: new_ for old, new_ in zip(written, final) if old != new_}
    if rename:
        output.data = output.data.rename(columns=rename)
        output.states = output.states.rename(columns=rename)
    output.meta["value_column"] = final[0] if len(final) == 1 else None


def _spread_dict(operation: Operation, output: Output) -> None:
    """A map whose tool declares ``-> dict`` spreads each row's dict into one
    column per key, in the order keys first appear (S4, core-asks L22). A key a
    row's dict lacks is ``absent`` there (C6); a row that failed or was blocked
    keeps its state in every column."""
    if not spreads_dict(operation):
        return
    column = output.meta.get("value_column")
    if column is None or column not in output.data.columns:
        return
    data, states = output.data, output.states
    cells = [data.at[i, column] if str(states.at[i, column]) == "known" else None for i in data.index]
    keys = list(dict.fromkeys(str(k) for c in cells if isinstance(c, Mapping) for k in c))
    if not keys:
        return
    at = list(data.columns).index(column)
    new, new_states = data.iloc[:, :at].copy(), states.iloc[:, :at].copy()
    for key in keys:
        values, marks = [], []
        for i, cell in zip(data.index, cells):
            state = str(states.at[i, column])
            if isinstance(cell, Mapping) and key in {str(k) for k in cell}:
                values.append(next(v for k, v in cell.items() if str(k) == key))
                marks.append(state)
            else:
                values.append(None)
                marks.append(state if state != "known" else "absent")
        new[key] = _typed(values, data.index)
        new_states[key] = _state_column(marks, data.index)
    for c in data.columns[at + 1:]:
        new[c], new_states[c] = data[c], states[c]
    output.data, output.states = new, new_states
    output.meta["value_column"] = keys[0] if len(keys) == 1 else None


def _mapping_keeps_value(output: Output, step_id: str, source: Output | None) -> None:
    """An expand of mappings writes two columns, ``key`` and ``value`` (J-D4):
    not one output, so the step's name doesn't replace ``value`` (D9, W12)."""
    if output.meta.get("verb") != "expand" or output.meta.get("value_column") != step_id:
        return
    carried = set(source.data.columns) if source is not None else set()
    if "key" not in output.data.columns or "key" in carried or VALUE_COLUMN in output.data.columns:
        return
    output.data = output.data.rename(columns={step_id: VALUE_COLUMN})
    output.states = output.states.rename(columns={step_id: VALUE_COLUMN})
    output.meta["value_column"] = VALUE_COLUMN


def _named(operation: Operation) -> str:
    """The column a step's `mod.name` gives it, or `value`."""
    for m in reversed(operation.modifiers):
        if m.kind == "name" and isinstance(m.settings.get("to"), str):
            return m.settings["to"]
    return VALUE_COLUMN
