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


class Workflow:
    """Ordered Steps. Assign an Operation, get a Step that is already staged.

    ``wf["scored"] = score[mod.map(over=wf["videos"])]`` — declaring stages;
    ``wf.run("scored")`` is what actually computes.
    """

    def __init__(self, catalog: "Catalog | None" = None) -> None:
        self.steps: dict[str, Step] = {}
        #: Declared resources, by name — the declarations, never the objects.
        self.resources: dict[str, ResourceDecl] = {}
        #: What this workflow may use. With a catalog, every step is checked
        #: against it and runs the catalog's functions; without one, the
        #: process-wide registry is used (until phase 3 removes it).
        self.catalog = catalog
        #: The app's additions to the workflow, by namespace. Saved, never read.
        self.extras: dict = {}

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
        self.resources[name] = ResourceDecl(name, type_, dict(settings),
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
                st.output = stage(operation, self, problems)
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
    def __setitem__(self, step_id: str, operation: Any) -> None:
        _check_caller_scope()
        existed = step_id in self.steps
        # The app's additions stay with the step when it is re-declared.
        kept_extras = self.steps[step_id].extras if existed else {}
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
                extras=kept_extras,
            )
            out = self.steps[step_id].output
            out.meta["version"], out.meta["read"] = _data_version(out.data), {}
            if existed:
                self._mark_stale_dependents(step_id)
            else:
                self._recheck_readers(step_id)
            return
        operation = _attach_bound(operation, self.resources)
        if self.catalog is not None:
            operation = self.catalog.admit(operation)
        problems = check(operation, self, step_id)
        previous = self.steps.get(step_id)
        staged = stage(operation, self, problems)
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
        self.steps[step_id] = Step(step_id, operation, output, problems,
                                   warn(operation, self, step_id), kept_extras)
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

    def _resource_version(self, name: str) -> str | None:
        decl = self.resources.get(name)
        if decl is None:
            return None
        return hashlib.sha1(json.dumps(decl.to_dict(), sort_keys=True,
                                       default=repr).encode()).hexdigest()[:12]

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
        if kind not in ROW_ALIGNED:
            return None
        source = str(op_.input)
        upstream = self.steps.get(source)
        if upstream is None or upstream.output.meta.get("staged"):
            return None
        if _is_tool_verb(kind, op_):
            columns = self._columns_bound(op_, source, kind)
        else:
            columns = list(dict.fromkeys(_source_column(op_, c) for c in step.output.data.columns))
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
                        if changed is None:
                            found, everything = found or f"input {name} changed", True
                        elif changed:
                            found = found or f"input {name} changed"
                            rows_ |= changed
                        continue                    # unread columns changed: not stale
                    found = found or (f"input {name} changed" if name in inputs
                                      else f"{name} changed")
                    everything = True
                elif name in self.steps and reason(name):
                    found = found or f"{name} is stale"
                    upstream_rows = partial.get(name)
                    if tracked and upstream_rows is not None:
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
        summary = {"step": step_id, "status": step.status, "summary": step.describe(),
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
                result.append({ROW_ID: position, "position": position, "id": _plain(row_id),
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
        return [{ROW_ID: i, "position": i, "id": _plain(row_id), "state": state,
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
        if view["status"] == "invalid":
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
        fn = step.operation.fn or TOOLS.get(step.operation.tool_id)
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
            if op_.tool_id == "zip":
                for g in op_.grids:
                    if column in self._predicted_of(str(g)):
                        entries.append(self._input_entry(str(g), row_id, [column], None))
                        break
            else:
                entries += [{"step": str(g), "id": None, "columns": [], "argument": None,
                             "state": "unknown", "values": {},
                             "because": f"{op_.tool_id} doesn't keep row links yet"}
                            for g in op_.grids]
            return entries

        if op_.input is not None:
            source = str(op_.input)
            if kind == "collapse":
                members = (step.output.notes.get(row_id) or {}).get("unit")
                rows_ = members if isinstance(members, list) else None
                for param in self._columns_bound(op_, source, kind):
                    entries.append(self._input_entry(source, None, [param], param, rows_=rows_))
            elif kind == "table":
                entries.append({"step": source, "id": None, "rows": "all", "columns": [],
                                "argument": self._first_param(op_), "state":
                                self._grid_state(source), "values": {}})
            elif _is_tool_verb(kind, op_):
                for param in self._columns_bound(op_, source, kind):
                    entries.append(self._input_entry(source, row_id, [param], param))
            else:
                # No tool: the cell is a copy of the input's (renamed, perhaps).
                entries.append(self._input_entry(source, row_id,
                                                 [_source_column(op_, column)], None))

        for name, value in op_.arguments.items():
            if isinstance(value, StepRef):
                entries.append(self._reference_entry(value, name))
            elif isinstance(value, ResRef):
                entries.append({"resource": value.name, "argument": name,
                                "state": "loaded at run"})
        for m in op_.modifiers:
            for name, value in m.params.items():
                if isinstance(value, StepRef):
                    entries.append(self._reference_entry(value, f"{m.kind}.{name}"))
        return entries

    def _columns_bound(self, op_: Operation, source: str, kind: str) -> list[str]:
        """The input columns a tool reads: its parameters the input supplies by name."""
        fn = op_.fn or TOOLS.get(op_.tool_id) or BUILTIN_TOOLS.get(op_.tool_id)
        columns = self._predicted_of(source)
        try:
            parameters = list(_signature(fn).parameters.values()) if fn else []
        except (TypeError, ValueError):
            parameters = []
        if kind == "collapse":
            parameters = parameters[1:]              # the accumulator
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
            return [c for c in columns if c not in op_.arguments]      # the whole row
        return [p.name for p in parameters
                if p.name in columns and p.name not in op_.arguments]

    @staticmethod
    def _first_param(op_: Operation) -> str | None:
        fn = op_.fn or TOOLS.get(op_.tool_id)
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
        lookup = _row_lookup(out.data)
        key = str(row_id)
        match = key if key in lookup else next((a for a in _ancestors(key) if a in lookup), None)
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
                return (f"argument {name!r} reads {step.step_id}, which has a failed "
                        f"cell {step.step_id}[{index}]",
                        note.get("cause") or f"{step.step_id}[{index}]: {note.get('error')}")
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
        """Execute one step; record its version and the versions it read (009 §5).

        See :meth:`_run_step` for how a step runs. Afterwards its output carries
        ``version`` (a hash of its data) and ``read`` (``{step: version}`` for
        every step it read, ``{"res:name": …}`` for resources), and every step
        is re-checked for staleness from those stamps.
        """
        if tools is None and self.catalog is not None:
            tools = self.catalog.functions
        step = self.steps[step_id]
        read = self._read_stamps(step.operation) if step_id in self.steps else {}
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
            frames = []
            for g in step.operation.inputs:
                frame = rows(self.steps[str(g)].output).copy(deep=False)
                frame.attrs["step_id"] = str(g)        # so an error can name it
                frames.append(frame)
            try:
                step.output = _run_combine(step.operation, frames)
                if step.operation.tool_id == "zip":
                    self._carry_zip_states(step)
            except ValueError as exc:
                # A zip_ that would drop rows, a join on a missing key: the step
                # fails with the reason (the run stops on it), never raises.
                step.output = _failed_output(step.operation, str(exc))
            self._restage_after(step_id)
            return step
        try:
            resolved = self._resolve_arguments(step.operation, resources)
        except SelectionError as exc:
            step.output = _failed_output(step.operation, str(exc))
            self._restage_after(step_id)
            return step
        source = self._input_for(resolved)
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
                other.warnings = warn(other.operation, self, other.step_id)
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
                  catalog: "Catalog | None" = None) -> "Workflow":
        """Rebuild a Workflow from either export — all at once.

        Every step goes through the same :func:`check` and :func:`stage` the
        incremental path uses, so loading cannot smuggle in a step that
        declaring would have rejected. *resource_types* maps a saved resource
        type name to its class, as *tools* does for tools; types registered with
        :func:`resource` (or used by ``define``) are found without it.

        With *catalog*, tools and resource types come from it alone, and every
        step is checked against it.
        """
        version = blob.get("version", 1)
        if not isinstance(version, int) or version > FORMAT_VERSION:
            # 008 K17: an older core must refuse a newer file, never strip it.
            raise ValueError(
                f"this workflow was saved in format version {version!r}; this "
                f"core reads versions 1 to {FORMAT_VERSION}. Upgrade "
                "simple-steps-core to load it.")
        workflow = cls(catalog=catalog)
        if catalog is not None:
            tools, known = catalog.functions, catalog.resource_types
        else:
            known = {**RESOURCE_TYPES, **(resource_types or {})}
        for name, entry in (blob.get("resources") or {}).items():
            workflow.resources[name] = ResourceDecl(
                name, known.get(entry["type"]), dict(entry.get("settings") or {}),
                entry["type"], entry.get("source", "defined"),
                dict(entry.get("extras") or {}))
        workflow.extras = dict(blob.get("extras") or {})
        for entry in blob["steps"]:
            sid = entry["step_id"]
            operation = _attach_bound(
                Operation.from_dict(entry["operation"], tools), workflow.resources)
            if catalog is not None:
                operation = catalog.admit(operation)
            problems = check(operation, workflow, sid)
            workflow.steps[sid] = Step(sid, operation,
                                       stage(operation, workflow, problems),
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


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .system_tools import (  # noqa: E402
    BUILTIN_TOOLS,
    DEFAULT_TOOL,
    identity,
    is_identity,
)
from .catalog import (  # noqa: E402
    Catalog,
    _checked_extras,
    RESOURCE_TYPES,
    ResourceDecl,
    TOOLS,
    _attach_bound,
    _settings,
    _signature,
    resource,
    resource_problems,
)
from .checks import (  # noqa: E402
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
)
from .combines import _row_lookup, _run_combine, is_combine  # noqa: E402
from .errors import ResourceNotLoaded, SelectionError, StepFailed  # noqa: E402
from .modifiers import (  # noqa: E402
    MODIFIERS,
    Modifier,
    is_shape,
    mod,
)
from .operation import Operation, _src  # noqa: E402
from .output import (  # noqa: E402
    Output,
    ROW_ID,
    _data_version,
    _failed_output,
    _str_columns,
    _uncaught_failure,
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
    Step,
    _changes_text,
    _ran_with,
    _row_fps,
)
from .values import (  # noqa: E402
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
from .verbs import _ancestors, source_  # noqa: E402
