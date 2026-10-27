"""Kernel: one live workflow with what it runs with. The object you hold.

A kernel is a catalog, a workflow checked against it, and the resources it has
loaded (docs/design/object-model.md §4.12). Everything you do to a workflow in
a Python session goes through it: declare and edit steps, run them, read
values, save and load::

    k = Kernel(Catalog(tools=[patients, to_f]))
    k["p"] = patients[mod.source()]()
    k["f"] = to_f[mod.map()](wf["p"])
    k.run_all()
    k                      # a table: step, formula, state, shape, problem

Several kernels can live in one process and share nothing: each has its own
catalog, workflow and resources.
"""

from __future__ import annotations

import functools
import html
import json
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from .catalog import Catalog
from .output import VALUE_COLUMN
from .specs import KernelSpec
from .references import ResRef, StepRef
from .step import NO_LITERAL, Step
from .workflow import Workflow


class Resources(Mapping):
    """A kernel's loaded resources, by name.

    Each declared resource is built from its spec the first time something
    needs it: ``ClinicalDB(**settings)``, using the type in the catalog. An
    object the host has already built (one with secrets, or a shared
    connection) can be handed over with :meth:`attach` instead.
    """

    def __init__(self, kernel: "Kernel"):
        self._kernel = kernel
        self._loaded: dict[str, Any] = {}

    def __getitem__(self, name: str) -> Any:
        if name not in self._loaded:
            decl = self._kernel.workflow.resources.get(name)
            if decl is None:
                raise KeyError(f"no resource {name!r}; define it with "
                               f"k.define({name!r}, <type>, …)")
            if decl.type is None:
                raise KeyError(f"resource {name!r} is a {decl.type_name}, which is "
                               "not in this kernel's catalog")
            self._loaded[name] = decl.type(**decl.settings)
        return self._loaded[name]

    def __contains__(self, name: object) -> bool:
        return name in self._loaded or name in self._kernel.workflow.resources

    def __iter__(self) -> Iterator[str]:
        return iter(self._kernel.workflow.resources)

    def __len__(self) -> int:
        return len(self._kernel.workflow.resources)

    @property
    def loaded(self) -> list[str]:
        """The resources built (or attached) so far."""
        return list(self._loaded)

    def attach(self, name: str, obj: Any) -> None:
        """Use *obj* as resource *name* instead of building it from its spec."""
        decl = self._kernel.workflow.resources.get(name)
        if decl is None:
            raise KeyError(f"no resource {name!r}; define it before attaching an object")
        if decl.type is not None and not isinstance(obj, decl.type):
            raise TypeError(f"resource {name!r} is a {decl.type_name}, got "
                            f"{type(obj).__name__}")
        self._loaded[name] = obj

    def _forget(self, name: str) -> None:
        self._loaded.pop(name, None)


def _notifies(action: str):
    """Tell the kernel's listeners what *action* changed, once it is done."""
    def wrap(method):
        @functools.wraps(method)
        def run(self, *args, **kwargs):
            if not self._listeners:
                return method(self, *args, **kwargs)
            before = self._snapshot()
            try:
                return method(self, *args, **kwargs)
            finally:
                self._tell(action, before)
        return run
    return wrap


def _formula(step: Step) -> str:
    """How a step is written: its formula, or the value a literal step holds."""
    if step.literal is not NO_LITERAL:
        value = step.literal
        if hasattr(value, "shape") and hasattr(value, "columns"):
            return f"<{type(value).__name__} {value.shape[0]}×{value.shape[1]}>"
        text = repr(value)
        return text if len(text) <= 60 else text[:57] + "..."
    try:
        return step.operation.to_source()
    except Exception:                               # a step that can't print
        return step.operation.tool


class Kernel:
    """A workflow, the catalog it may use, and the resources it has loaded."""

    def __init__(self, catalog: Catalog):
        if not isinstance(catalog, Catalog):
            raise TypeError("Kernel(catalog): pass a Catalog, e.g. "
                            "Kernel(Catalog(tools=[...]))")
        self.catalog = catalog
        self.workflow = Workflow(catalog=catalog)
        self.resources = Resources(self)
        self._listeners: list[Callable[[dict], Any]] = []

    # ── steps ────────────────────────────────────────────────────────────
    def _name(self, step: str | int) -> str:
        if isinstance(step, bool) or not isinstance(step, (str, int)):
            raise TypeError(f"a step is named by a str or an int position, got {step!r}")
        if isinstance(step, int):
            names = list(self.workflow.steps)
            try:
                return names[step]
            except IndexError:
                raise IndexError(f"no step at position {step}: the workflow has "
                                 f"{len(names)}") from None
        if step not in self.workflow.steps:
            raise KeyError(f"no step {step!r}")
        return step

    @_notifies("declare")
    def __setitem__(self, name: str, operation: Any) -> None:
        """Declare step *name*, or replace it. Checked and planned at once."""
        self.workflow[name] = operation

    def __getitem__(self, step: str | int) -> StepRef:
        """A reference to a step, by name or position, for use in another step."""
        return self.workflow[step]

    @_notifies("remove")
    def __delitem__(self, step: str | int) -> None:
        self.workflow.remove(self._name(step))

    def __contains__(self, name: object) -> bool:
        return name in self.workflow.steps

    def __iter__(self) -> Iterator[str]:
        return iter(self.workflow.steps)

    def __len__(self) -> int:
        return len(self.workflow.steps)

    @property
    def steps(self) -> list[Step]:
        """The steps, in order."""
        return list(self.workflow.steps.values())

    def step(self, step: str | int) -> Step:
        """The live step, by name or position."""
        return self.workflow.step(self._name(step))

    @_notifies("rename")
    def rename(self, old: str, new: str) -> None:
        """Rename a step; later references follow."""
        self.workflow.rename(self._name(old), new)

    @_notifies("insert")
    def insert(self, index: int, name: str, operation: Any) -> None:
        """Declare a new step *name* at position *index*. Refused when it would
        read a step that comes after that position."""
        self.workflow.insert(index, name, operation)

    @_notifies("move")
    def move(self, step: str | int, index: int) -> None:
        """Move a step to position *index*. Refused when a valid step would then
        read a step after it."""
        self.workflow.move(self._name(step), index)

    # ── resources ────────────────────────────────────────────────────────
    @_notifies("define")
    def define(self, name: str, type_: type, /, **settings: Any) -> ResRef:
        """Add resource *name*: a *type_* from the catalog, built from *settings*
        when a step first needs it."""
        ref = self.workflow.define(name, type_, **settings)
        self.resources._forget(name)          # new settings: build it afresh
        return ref

    # ── checking and running ─────────────────────────────────────────────
    def validate(self) -> dict[str, tuple[str, ...]]:
        """Every step's problems, by name; empty for the good ones."""
        return self.workflow.validate()

    def check(self, name: str, operation: Any) -> tuple:
        """The problems step *name* would have, without adding it or changing
        anything: what a proposal (from the agent, or a form) is checked with
        before it is accepted. Empty when it would be fine."""
        return self.workflow.check(name, operation)

    @_notifies("run")
    def run(self, step: str | int) -> Step:
        """Run one step on what its inputs show now.

        Inputs that have never run run first, since they have nothing to show.
        An input that is stale passes through as it is.
        """
        name = self._name(step)
        for upstream in dict.fromkeys(self.workflow.pending(name)):
            self.workflow.run(upstream, resources=self.resources)
        return self.workflow.run(name, resources=self.resources)

    @_notifies("run_all")
    def run_all(self) -> "Kernel":
        """Run every valid step, in order. Stops at a failure nothing handles."""
        self.workflow.run_all(resources=self.resources)
        return self

    # ── what needs running, and who to tell ──────────────────────────────
    def _read_stale(self, name: str) -> list[str]:
        """The inputs of a step that has run which are stale now."""
        steps = self.workflow.steps
        return [r for r in steps[name].operation.reads
                if r in steps and steps[r].state == "stale"]

    def needs_run(self) -> dict[str, str]:
        """Every step that isn't up to date, in run order, with why:
        ``staged``, ``stale: <reason>``, or ``read stale '<input>'`` for a step
        that ran on an input that is stale. Invalid steps can't run and aren't
        listed (see :meth:`validate`)."""
        out: dict[str, str] = {}
        for name, st in self.workflow.steps.items():
            state = st.state
            if state == "staged":
                out[name] = "staged"
            elif state == "stale":
                out[name] = f"stale: {st.output.stale_reason or 'an input changed'}"
            elif state in ("completed", "failed"):
                stale_inputs = self._read_stale(name)
                if stale_inputs:
                    out[name] = f"read stale {stale_inputs[0]!r}"
        return out

    def on_change(self, callback: Callable[[dict], Any]) -> Callable[[], None]:
        """Call *callback* after every edit or run that changes a step's formula,
        state, problems, plan or output.

        It receives ``{"action": …, "changed": [names in order], "removed":
        [names]}``. Returns a function that stops the calls.
        """
        self._listeners.append(callback)

        def stop() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)
        return stop

    def _snapshot(self) -> dict[str, tuple]:
        return {name: (json.dumps(st.operation.to_dict(), sort_keys=True, default=str),
                       st.state, tuple(map(str, st.problems)), repr(st.output.plan),
                       st.output.version, st.output.stale_reason,
                       tuple(self._read_stale(name)))
                for name, st in self.workflow.steps.items()}

    def _tell(self, action: str, before: dict[str, tuple]) -> None:
        after = self._snapshot()
        changed = [n for n, v in after.items() if before.get(n) != v]
        removed = [n for n in before if n not in after]
        if action == "move":
            changed = changed or [n for n, o in zip(after, before) if n != o]
        if not changed and not removed:
            return
        change = {"action": action, "changed": changed, "removed": removed}
        for callback in list(self._listeners):
            callback(change)

    # ── reading ──────────────────────────────────────────────────────────
    def view(self, step: str | int, rows: tuple[int, int] | None = None) -> dict:
        """A page of a step's rows, as a UI shows them: ``rows=(start, stop)``."""
        return self.workflow.preview(self._name(step), rows)

    def cell(self, step: str | int, row: int, column: str = VALUE_COLUMN) -> dict:
        """One cell: its value, type and state, and the input cells it came from."""
        return self.workflow.cell(self._name(step), row, column)

    # ── saving ───────────────────────────────────────────────────────────
    @property
    def extras(self) -> dict:
        """The app's additions to this kernel's workflow, by namespace."""
        return self.workflow.extras

    @property
    def spec(self) -> KernelSpec:
        """Everything needed to reproduce this workflow with this set of tools:
        the workflow spec and the catalog spec. Never output data."""
        return KernelSpec(self.workflow.spec, self.catalog.spec)

    def to_json(self) -> str:
        """The spec as JSON: steps, resources, extras and the catalog's names."""
        return json.dumps(self.spec.to_dict())

    @classmethod
    def from_spec(cls, spec: KernelSpec, catalog: Catalog) -> "Kernel":
        """A kernel built from *spec*, checked against *catalog*. The spec's
        catalog names say what it was saved with; *catalog* is what it runs with."""
        return cls._load(spec.workflow.to_dict(), catalog)

    @classmethod
    def from_json(cls, text: str, catalog: Catalog) -> "Kernel":
        """A kernel from :meth:`to_json`, checked against *catalog*."""
        return cls._load(json.loads(text), catalog)

    @classmethod
    def _load(cls, blob: dict, catalog: Catalog) -> "Kernel":
        kernel = cls(catalog)
        blob = {k: v for k, v in blob.items() if k != "catalog"}
        kernel.workflow = Workflow.from_dict(blob, catalog=catalog)
        return kernel

    # ── display ──────────────────────────────────────────────────────────
    def _rows(self) -> list[tuple[str, ...]]:
        rows = []
        for index, (name, st) in enumerate(self.workflow.steps.items()):
            formula = _formula(st)
            data = st.output.data
            shape = "—" if st.output.staged else f"{data.shape[0]}×{data.shape[1]}"
            problem = st.problems[0] if st.problems else ""
            state = st.state
            stale_inputs = self._read_stale(name) if state in ("completed", "failed") else []
            if stale_inputs:
                state += f" · read stale {stale_inputs[0]!r}"
            rows.append((str(index), name, formula, state, shape, problem))
        return rows

    def __repr__(self) -> str:
        def count(n: int, word: str) -> str:
            return f"{n} {word}" + ("" if n == 1 else "s")
        head = (f"Kernel: {count(len(self), 'step')}, "
                f"{count(len(self.catalog.tools), 'tool')} (+ built-ins), "
                f"{count(len(self.workflow.resources), 'resource')}")
        rows = self._rows()
        if not rows:
            return head
        titles = ("#", "step", "formula", "state", "shape", "problem")
        widths = [max(len(t), *(len(r[i]) for r in rows)) for i, t in enumerate(titles)]
        widths[-1] = len(titles[-1])                # the last column isn't padded
        def line(cells: tuple[str, ...]) -> str:
            return "  ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()
        return "\n".join([head, line(titles), *(line(r) for r in rows)])

    def _repr_html_(self) -> str:
        head = html.escape(repr(self).splitlines()[0])
        titles = ("#", "step", "formula", "state", "shape", "problem")
        cells = "".join(
            "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>"
            for r in self._rows())
        return (f"<p>{head}</p><table><thead><tr>"
                + "".join(f"<th>{t}</th>" for t in titles)
                + f"</tr></thead><tbody>{cells}</tbody></table>")
