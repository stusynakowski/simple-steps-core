"""Operation: what a step does, as data, and how it prints as a formula.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Callable
import json
import numbers


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

    tool: str
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
        ids += [str(v) for m in self.modifiers for v in m.settings.values()
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
        return Operation(self.tool,
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
            operation = operation._add(modifier.kind, **modifier.settings)
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

    def to_source(self) -> str:
        """The formula that builds this operation (008 P).

        ``score[mod.map(name="s"), mod.retry(times=2)](wf["raw"], weight=2)``.
        One canonical form: modifiers in written order, the input in the call,
        arguments by keyword, selections rows first then ``cols``. Evaluated
        with :func:`formula_names`, it gives back an equal Operation.
        """
        if is_combine(self):
            grids = ", ".join(_src(g) for g in self.inputs)
            name = "zip_" if self.tool == "zip" else self.tool
            config = "".join(f", {k}={_src(v)}" for k, v in self.arguments.items())
            return f"{name}({grids}{config})"
        if self.bound_to is not None:
            head = f"res[{_src(self.bound_to.name)}].{self.tool.rsplit('.', 1)[-1]}"
        elif (self.fn is not None and self.tool not in BUILTIN_TOOLS
              and self.tool.isidentifier()):
            head = self.tool
        else:
            head = f"op({_src(self.tool)})"
        if self.modifiers:
            head += "[" + ", ".join(
                f"mod.{m.kind}(" + ", ".join(f"{k}={_src(v)}" for k, v in m.settings.items()) + ")"
                for m in self.layers) + "]"
        kwargs = [f"{k}={_src(v)}" for k, v in self.arguments.items()]
        verb = self.shape_verb.kind if self.shape_verb else None
        if self.input is not None:
            return f"{head}({', '.join([_src(self.input), *kwargs])})"
        if verb in ("source", "sweep"):
            return f"{head}({', '.join(kwargs)})"
        if kwargs:
            # No input and no verb that runs without one: bind, then decorate.
            base = head.split("[", 1)
            rest = "[" + base[1] if len(base) > 1 else ""
            return f"{base[0]}.bind({', '.join(kwargs)}){rest}"
        return head

    def check(self, workflow: "Workflow | None" = None,
              step_id: str | None = None) -> tuple[str, ...]:
        """This operation's problems — without a workflow, what is knowable from it alone."""
        return check(self, workflow, step_id)

    def bind(self, **literals) -> "Operation":
        """Add bound arguments — literals, or a StepRef to read another step's value."""
        return Operation(self.tool, self.modifiers,
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
            "tool": self.tool,
            "input": _encode_ref(self.input),          # {"$ref": id} or null — the data
            "arguments": {k: _encode_argument(v) for k, v in self.arguments.items()},
            "modifiers": [{"kind": m.kind,
                           "settings": {k: _encode_argument(v) for k, v in m.settings.items()}}
                          for m in self.modifiers],     # literal-only
        }
        if self.inputs:                                 # a combine reads many grids
            blob["inputs"] = [_encode_ref(g) for g in self.inputs]
        if self.bound_to is not None:                   # a bound tool's instance
            blob["bound_to"] = _encode_argument(self.bound_to)
        return blob

    @classmethod
    def from_spec(cls, spec: dict, catalog: Any = None) -> "Operation":
        """An operation from its spec (``op.to_dict()``), with its tools from
        *catalog*: how a front end that parses formula text itself (the app's
        formula bar) hands core an operation to declare or check."""
        return cls.from_dict(spec, catalog.functions if catalog is not None else None)

    @classmethod
    def from_dict(cls, blob: dict, tools: dict[str, Callable] | None = None
                  ) -> "Operation":
        """Rebuild an Operation from :meth:`to_dict`, re-attaching its function."""
        table = {**BUILTIN_TOOLS, **(tools or {})}
        fn = table.get(blob["tool"])
        modifiers = []
        for m in blob["modifiers"]:
            params = dict(m["settings"])
            modifiers.append(Modifier(m["kind"], {k: _with_tool(_decode_argument(v), table)
                                                  for k, v in params.items()}))
        arguments = {k: _decode_argument(v)
                     for k, v in (blob.get("arguments") or {}).items()}
        inputs = tuple(_decode_ref(g) for g in blob.get("inputs") or ())
        bound_to = _decode_argument(blob.get("bound_to"))
        return cls(
            tool=blob["tool"],
            modifiers=tuple(modifiers),
            arguments=arguments,
            # A bound tool's function comes from its resource type, never from
            # a tool table; the workflow attaches it once it knows the type.
            fn=None if bound_to is not None
            else (fn.fn if isinstance(fn, Tool) else fn),
            input=_decode_ref(blob.get("input")),
            inputs=inputs,
            bound_to=bound_to,
        )

    # ── the other half: hand the decorated tool some data ────────────────
    def __call__(self, source: Any = _NO_SOURCE, /, *more: Any, **literals) -> Any:
        """Apply the decorated tool to its input.

        Keyword arguments here are **bound literals**, exactly as
        :meth:`bind` would set them — ``score[mod.map()](ref, weight=2)`` and
        ``score.bind(weight=2)[mod.map()](ref)`` are the same Operation.
        ``Tool.__call__`` already accepted them; this is the other half.
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
            raise TypeError(f"{self.tool}: pass the data to apply it to, "
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
        based = Operation(self.tool, self.modifiers,
                          self.arguments, self.fn, ref, bound_to=self.bound_to)
        if based.bound_to is not None and based.fn is None \
                and ref.workflow is not None:
            # The reference knows its workflow, which knows the resource's
            # declared type — enough to find the method and infer from it.
            based = _attach_bound(based, ref.workflow.resources)
        if based.shape_verb is not None:
            return based
        # The verb is no longer picked here: staging and each run pick it from
        # the input as it is then (`_provisional`, `_resolve_auto`).
        # 009 decision 6: an unstated orchestration is auto, saved as
        # `mod.auto()` and decided from the data at each run.
        return based._add("auto")             # _add carries based.input forward

    def run(self, source: Any, tools: dict[str, Callable] | None = None) -> Any:
        """Compile the stack and apply it to *source*.

        Mirrors ``Tool.run()`` in the registry: the deferred form is the
        default and this is the immediate escape hatch. *tools* is needed only
        when this Operation names its tool by id (``op("score")``) rather than
        carrying it (``score[...]`` from a ``@tool`` handle).
        """
        if self.resources:
            raise TypeError(
                f"{self.tool} uses resource(s) "
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
        table = {**BUILTIN_TOOLS, **(tools or {})}
        if self.fn is not None:
            table.setdefault(self.tool, self.fn)
        if self.tool not in table:
            raise KeyError(
                f"cannot run {self.tool!r}: this Operation names its tool "
                f"by id, so pass the function — "
                f"run(source, tools={{{self.tool!r}: fn}}). "
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
        return f"<Operation {stack}{self.tool}{src}>"


def _with_tool(value: Any, table: dict) -> Any:
    """A saved tool name (``{"$tool": id}``) as the tool *table* has under it;
    left as a name when the table doesn't have it (``check`` then says so)."""
    if isinstance(value, ToolRef) and value.id in table:
        found = table[value.id]
        return found if isinstance(found, Tool) else Tool(found, value.id)
    return value


def op(tool_id: str, **arguments) -> Operation:
    """Start building an Operation for the tool named *tool_id*."""
    return Operation(tool=tool_id, arguments=arguments)


def _src(value: Any) -> str:
    """A value as formula text: a reference, a tool, or a Python literal."""
    if isinstance(value, StepRef):
        text = f"wf[{_src(value.id)}]"
        if isinstance(value.columns, dict) and value.columns.get("header"):
            return text + ".header"
        rows_ = value.rows
        if rows_ is not None:
            if isinstance(rows_, dict):
                lo = "" if rows_.get("start") is None else rows_["start"]
                hi = "" if rows_.get("stop") is None else rows_["stop"]
                text += f"[{lo}:{hi}]"
            else:
                text += f"[{rows_!r}]"
        columns = value.columns
        if columns is not None:
            if "names" in columns:
                names = columns["names"]
                inner = _src(names[0]) if len(names) == 1 else _src(list(names))
            elif "from" in columns or "to" in columns:
                lo = "" if columns.get("from") is None else _src(columns["from"])
                hi = "" if columns.get("to") is None else _src(columns["to"])
                inner = f"{lo}:{hi}"
            else:
                positions = columns["positions"]
                if isinstance(positions, dict):
                    lo = "" if positions.get("start") is None else positions["start"]
                    hi = "" if positions.get("stop") is None else positions["stop"]
                    inner = f"{lo}:{hi}"
                else:
                    inner = repr(positions[0]) if len(positions) == 1 else repr(list(positions))
            text += f"[cols[{inner}]]"
        return text
    if isinstance(value, ResRef):
        return f"res[{_src(value.name)}]"
    if isinstance(value, (ToolRef, Tool)):
        return value.id
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, numbers.Integral):
        return repr(int(value))
    if isinstance(value, numbers.Real):
        return repr(float(value))
    if isinstance(value, tuple):
        inner = ", ".join(_src(v) for v in value)
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    if isinstance(value, (set, frozenset)):
        if not value:
            return "set()"
        items = list(value)
        try:
            items = sorted(items)
        except TypeError:
            pass
        return "{" + ", ".join(_src(v) for v in items) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_src(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_src(k)}: {_src(v)}" for k, v in value.items()) + "}"
    return repr(value)


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .system_tools import BUILTIN_TOOLS  # noqa: E402
from .catalog import Tool, _attach_bound  # noqa: E402
from .checks import check  # noqa: E402
from .combines import is_combine  # noqa: E402
from .modifiers import Modifier  # noqa: E402
from .references import (  # noqa: E402
    ResRef,
    StepRef,
    ToolRef,
    _decode_ref,
    _encode_ref,
)
from .run import compile_operation  # noqa: E402
from .values import _bind_positional, _decode_argument, _encode_argument  # noqa: E402
from .workflow import Workflow  # noqa: E402
