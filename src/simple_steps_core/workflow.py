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


class Workflow:
    """Ordered Steps. Assign an Operation, get a Step that is already staged.

    ``wf["scored"] = score[mod.map(over=wf["videos"])]`` — declaring stages;
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
            operation = Operation(tool=default,
                                  fn=BUILTIN_TOOLS[default])[operation]

        return operation

    def __setitem__(self, step_id: str, operation: Any) -> None:
        _check_caller_scope()
        existed = step_id in self.steps
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
            self.steps[step_id] = self._literal_step(step_id, operation, kept_extras)
            if existed:
                self._mark_stale_dependents(step_id)
            if not existed or was_empty or self.steps[step_id].output.meta.get("empty"):
                self._recheck_readers(step_id)    # an empty step written, or emptied (G17)
            return
        operation = _attach_bound(operation, self.resources)
        if self.catalog is not None:
            operation = self.catalog.admit(operation)
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
        return check(operation, self, step_id)

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
        for sid, st in self.steps.items():
            if sid == step_id or step_id not in st.operation.reads:
                continue
            problems = check(st.operation, self, sid)
            if problems != st.problems:
                st.problems = problems
                st.output = stage(st.operation, self, problems, sid)
                st.warnings = warn(st.operation, self, sid)

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
        self.steps[new].name = new
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
                recipe = {"operation": st.operation.to_dict()}
                if st.literal is not NO_LITERAL and _literal_problem(st.literal) is None:
                    recipe["literal"] = _encode_argument(st.literal)
            except Exception as error:
                # A step that can't be saved (a lambda) can't be reproduced: no
                # id, for it or for anything that reads it.
                out[name] = {"id": None, "why": str(error)}
                continue
            upstream = [r for r in st.operation.reads if r in out and out[r]["id"] is None]
            if upstream:
                out[name] = {"id": None, "why": f"it reads {upstream[0]!r}, which has no id"}
                continue
            parts = {
                "recipe": _short_hash(recipe),
                "tool": self._tool_hash(st.operation),
                "resources": {r: self._resource_version(r, data=False)
                              for r in sorted(st.operation.resources)},
                "inputs": {r: out[r]["id"] if r in out else None
                           for r in sorted(st.operation.reads)},
            }
            parts["id"] = _short_hash(parts)
            out[name] = parts
        return out

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
        """``{"step", "columns", "fp": [[row id, hash], …]}`` for a row-aligned step."""
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
            columns = self._columns_bound(op_, source, kind)
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
                "fp": [[_plain(i), h] for i, h in _row_fps(upstream.output.data, columns).items()]}

    def stale_rows(self, step_id: str) -> list | None:
        """The rows of a stale step that are out of date — None when all of them are."""
        meta = self.steps[step_id].output.meta
        if not meta.get("stale"):
            return []
        rows_ = meta.get("stale_rows")
        return None if rows_ is None else list(rows_)

    def _refresh_staleness(self) -> None:
        """Set every run step's ``stale``, and a short ``stale_reason``, from its stamps.

        Reasons, shown as *"stale output (<reason>)"*: ``updated args`` (its own
        formula changed), ``input r changed`` / ``w changed`` (a step it read
        has new data), ``resource llm changed``, ``r is stale`` (a step it read
        is itself stale).
        """
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
                elif name in self.steps and reason(name) \
                        and name not in (output.meta.get("read_stale") or {}):
                    found = found or f"{name} is stale"
                    upstream_rows = partial.get(name)
                    if tracked and upstream_rows is not None \
                            and output.meta.get("groups") is not None:
                        grouped = self._groups_of(output, set(upstream_rows), name)
                        if grouped is None:
                            everything = True
                        else:
                            rows_ |= grouped
                    elif tracked and upstream_rows is not None:
                        rows_ |= upstream_rows      # row-aligned: the same rows
                    else:
                        everything = True
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
                    if key not in ids:
                        return None            # a new group: the whole output changes
                    out.add(key)
        return out

    def _changed_rows(self, row_reads: dict) -> set | None:
        """Input rows whose read columns changed since the run; None if rows came or went."""
        upstream = self.steps.get(row_reads["step"])
        if upstream is None or upstream.output.meta.get("staged"):
            return None
        before = {k: h for k, h in row_reads["fp"]}
        columns = [c for c in row_reads["columns"] if c in upstream.output.data.columns]
        if len(columns) != len(row_reads["columns"]):
            return None
        now = _row_fps(upstream.output.data, columns)
        if {str(k) for k in now} != {str(k) for k in before}:
            return None
        by_str = {str(k): v for k, v in before.items()}
        return {k for k, h in now.items() if by_str[str(k)] != h}

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

    def _predicted_of(self, step_id: str) -> list:
        """The columns a step is known to have (or will have), [] when it doesn't exist."""
        step = self.steps.get(step_id)
        return [] if step is None or not step.valid else predicted_columns(step.output)

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
            states[name] = _state_column(["known"] * len(data), data.index)
            for row, p in zip(data.index, partners):
                if (p is None or p not in column.index) and row not in blocked:
                    why = f"{name}: {ref.id!r} has no row {_plain(row if p is None else p)!r}"
                    blocked[row] = (why, why)
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

    def _value_if_known(self, ref: StepRef) -> Any:
        """The value a reference will resolve to, if its step holds data now."""
        step = self.steps.get(ref.id)
        if step is None or step.output.meta.get("staged"):
            return _UNKNOWN
        return _ref_value(step.output.data, None, ref.id)

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
            return {**summary, "columns": [], "rows": [], "row_count": None,
                    "problems": list(step.problems),
                    "markers": [{"kind": "invalid", "text": f"‹can't run — {step.problems[0]}›",
                                 "root": root, "because": why}]}
        types = plan.get("types", {})
        names = list(plan.get("columns", {}).get("names", []))
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
        return {**summary, "columns": columns, "rows": all_rows[lo:hi],
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
                    state = str(out.states.at[row_id, c])
                    if state == "known" and stale:
                        state = "stale"
                    cell = {"state": state, "type": types.get(c, "any")}
                    if state in ("known", "stale"):
                        cell["value"] = _plain(out.data.at[row_id, c])
                    if state in ("failed", "blocked"):
                        cell.update({k: v for k, v in note.items() if k in ("error", "cause")})
                    cells[str(c)] = cell
                row_state = str(row_states[row_id])
                result.append({ROW_ID: _plain(row_id), "position": position, "id": _plain(row_id),
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
        return [{ROW_ID: _plain(row_id), "position": i, "id": _plain(row_id), "state": state,
                 "cells": {c: {"state": state, "type": types.get(c, "any")} for c in names}}
                for i, row_id in enumerate(index)]

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
            cell = {**base, "id": entry["id"], **entry["cells"].get(column, {"state": entry["state"]}),
                    "type": type_}
            cell["inputs"] = self._cell_inputs(step_id, entry["id"], column)
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
        def may_be_none(column: str) -> bool:
            """A `#` column a stack or an outer join wrote, here or carried."""
            seen = step_id
            while seen in self.steps:
                o = self.steps[seen].operation
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
        columns, rows_ = (plan or {}).get("columns") or {}, (plan or {}).get("rows") or {}
        if columns.get("certainty") == "exact" and list(columns.get("names") or []) != list(data.columns):
            found.append(f"A6 {step_id}: planned columns {columns.get('names')}, got {list(data.columns)}")
        if rows_.get("certainty") == "exact" and rows_.get("count") is not None \
                and rows_["count"] != len(data):
            found.append(f"A6 {step_id}: planned {rows_['count']} rows, got {len(data)}")
        return found

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
        if kind == "pack" and _named(op_) == VALUE_COLUMN:
            chosen = list(settings.get("columns") or variables(self._predicted_of(source)))
            return {"kind": "rebuild", "formula": f"mod.widen(columns={chosen!r})({me})"}
        if kind == "widen":
            names_ = variables(self._predicted_of(source))
            spread = VALUE_COLUMN if VALUE_COLUMN in names_ else (names_[0] if len(names_) == 1 else None)
            fields = list(settings.get("columns") or [])
            if not fields and step_id in self.steps and not self.steps[step_id].output.meta.get("staged"):
                fields = [c for c in variables(self.steps[step_id].output.data.columns) if c not in names_]
            if spread == VALUE_COLUMN:
                return {"kind": "rebuild",
                        "formula": f"mod.pack(columns={fields!r})({me})" if fields else None}
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
        return [p.name for p in parameters
                if p.name in columns and p.name not in op_.arguments]

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
                            for m in operation.modifiers for v in m.settings.values())
        if operation.bound_to is None and not settings_refs and not any(
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
            fn = getattr(instance, operation.tool.rsplit(".", 1)[-1])
        modifiers = tuple(
            Modifier(m.kind, {k: (_ref_value(_apply_selection(
                                      self.steps[v.id].output.data, v.rows,
                                      v.columns, v.id), None, v.id)
                                  if isinstance(v, StepRef) else v)
                              for k, v in m.settings.items()})
            for m in operation.modifiers)
        return Operation(operation.tool, modifiers, resolved,
                         fn, operation.input)

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
        read = self._read_stamps(step.operation) if step_id in self.steps else {}
        # Inputs that are stale as this runs pass through as they are; this
        # output is then up to date with them, and says it read them stale.
        read_stale = {name: self.steps[name].output.meta.get("stale_reason")
                      for name in read if name in self.steps
                      and self.steps[name].output.meta.get("stale")}
        result = self._run_step(step_id, tools, resources)
        out = self.steps[step_id].output
        if not out.meta.get("staged"):
            out.meta["version"] = _data_version(out.data)
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
                mismatch = _output_mismatch(step.operation, step.output.data)
                if mismatch:
                    step.output = _failed_output(step.operation, mismatch)
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
        bad_argument = self._failed_argument(step.operation)
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
        try:
            step.output = resolved.run(source, tools)
            step.output.data = _str_columns(step.output.data, step_id)
            _spread_record(resolved, step.output)
            _apply_naming(resolved, step.output, step_id, self.default_name_rule(resolved))
            _carry_id_columns(resolved, source, step.output)
            found = step.output.meta.pop("warnings", None) or []
            for read in dict.fromkeys(str(g) for g in step.operation.reads):
                upstream = self.steps.get(read)
                if upstream is not None and upstream.output.meta.get("stale"):
                    found.append(f"read {read!r} while it's stale (version "
                                 f"{upstream.output.version}): an earlier step changed since "
                                 f"{read!r} ran; run it first for current values")
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
                raise SelectionError(mismatch)
        except (SelectionError, KeyError, TypeError, ValueError) as exc:
            # 008 C7: a position out of range, a column that is gone — the step
            # fails with the reason, never None, NaN or an empty grid. A TypeError
            # here is core's own reshaping (a tool's is caught per row): a sort,
            # group or match key holding lists or dicts (V6).
            why = str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)
            if isinstance(exc, TypeError):
                why = (f"{step.operation.shape_verb.kind if step.operation.shape_verb else 'step'}: "
                       f"{why}. A column used to sort, group or match must hold single "
                       f"values, not lists or dicts (V6)")
            step.output = _failed_output(step.operation, why)
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
                if other.name in changed:
                    continue
                if not any(name in changed for name in other.operation.reads):
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
                          columns_unknown(other.output))
                other.problems = check(other.operation, self, other.name)
                other.output = stage(other.operation, self, other.problems, other.name)
                other.warnings = warn(other.operation, self, other.name)
                after = (other.output.meta.get("expected"), other.problems,
                         predicted_columns(other.output),
                         columns_unknown(other.output))
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
    _paired_arguments,
    ROWS_RULE,
    ROW_ALIGNED,
    _is_tool_verb,
    _output_mismatch,
    _plan_markers,
    _source_column,
    _worst,
    check,
    columns_unknown,
    predicted_columns,
    stage,
    warn,
    keeps_ids,
    _tool_parameters,
)
from .combines import _row_lookup, _run_combine, is_combine, own_id_columns  # noqa: E402
from .errors import PayloadError, ResourceNotLoaded, SelectionError, StepFailed  # noqa: E402
from .problems import Problem  # noqa: E402
from .values import _record_fields, named_columns, record_return  # noqa: E402
from .modifiers import (  # noqa: E402
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
    _UNKNOWN,
    _apply_selection,
    _check_caller_scope,
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
from .verbs import source_  # noqa: E402


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


def _named(operation: Operation) -> str:
    """The column a step's `mod.name` gives it, or `value`."""
    for m in reversed(operation.modifiers):
        if m.kind == "name" and isinstance(m.settings.get("to"), str):
            return m.settings["to"]
    return VALUE_COLUMN
