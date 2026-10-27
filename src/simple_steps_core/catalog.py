"""Tools and resource types: @tool, @resource, bound tools, and their descriptions.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import replace
from collections.abc import Mapping
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Sequence
import hashlib
import inspect
import types
import typing
import warnings


def _arg_docs(fn: Callable) -> dict[str, str]:
    """Per-parameter text from a Google-style ``Args:`` docstring section.

    A form shows this as the field's help; the summary line stays the tool's
    own description. Continuation lines are folded into the parameter above them.
    """
    doc = inspect.getdoc(fn) or ""
    sections = {"args", "arguments", "parameters", "returns", "return", "raises",
                "yields", "examples", "example", "note", "notes", "attributes"}
    out: dict[str, str] = {}
    current, in_args = None, False
    for raw in doc.splitlines():
        stripped = raw.strip()
        if stripped.rstrip(":").lower() in sections:
            in_args = stripped.rstrip(":").lower() in ("args", "arguments", "parameters")
            current = None
            continue
        if not in_args or not stripped:
            continue
        name_part, sep, desc = stripped.partition(":")
        name = name_part.split("(")[0].strip().lstrip("*")
        if sep and name.isidentifier():
            out[name] = desc.strip()
            current = name
        elif current:                                # a wrapped continuation line
            out[current] = f"{out[current]} {stripped}".strip()
    return out


def _param_type_info(annotation: Any) -> tuple[str | None, list | None, bool]:
    """``(type_name, choices, nullable)`` for a parameter annotation.

    Keeps the inner type of ``Optional[X]`` (and sets ``nullable``) and the
    options of ``Literal[...]`` (with their own type as ``type_name``), so a form
    renders a dropdown or a typed field instead of a bare "Optional"/"Literal".
    """
    if annotation is inspect.Parameter.empty:
        return None, None, False
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = typing.get_args(annotation)
        nullable = type(None) in args
        inner = [a for a in args if a is not type(None)]
        if len(inner) == 1:
            name, choices, _ = _param_type_info(inner[0])
            return name, choices, nullable
        names = [n for n in (_type_name(a) for a in inner) if n]
        return (" | ".join(names) or None), None, nullable
    if origin is typing.Literal:
        choices = list(typing.get_args(annotation))
        element = _type_name(type(choices[0])) if choices else None
        return element, choices, False
    return _type_name(annotation), None, False


def tool_entry(tool_id: str, fn: Callable, origin: str) -> dict:
    """One tool as a palette entry: what it is, where it came from, what it takes.

    ``description`` is the docstring's first line, which is why those first
    lines are written as user-facing sentences rather than developer notes.
    ``origin`` lets a client separate the system's tools from the user's — the
    builtins are always available and rarely what someone is looking for, so a
    palette usually groups or hides them.

    Each parameter carries enough to render a form field: ``type`` (the inner
    type of an ``Optional``, not the word "Optional"), ``choices`` (a
    ``Literal``'s options), ``nullable``, and ``description`` (its ``Args:`` text).
    """
    doc = (inspect.getdoc(fn) or "").strip()
    try:
        signature = inspect.signature(fn)
        parameters = list(signature.parameters.values())
    except (TypeError, ValueError):
        signature, parameters = None, []
    # Resolve string annotations (PEP 563) to real types so Literal/Optional stay
    # inspectable; fall back to the raw annotation when a forward ref won't resolve.
    try:
        hints = typing.get_type_hints(fn, include_extras=True)
    except Exception:
        hints = {}
    arg_docs = _arg_docs(fn)
    return_ann = hints.get("return")
    if return_ann is None and signature is not None:
        return_ann = signature.return_annotation
    returns = _type_name(return_ann if return_ann is not None
                         else inspect.Parameter.empty)

    params, takes_row = [], False
    for parameter in parameters:
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            takes_row = True
            continue
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        required = parameter.default is inspect.Parameter.empty
        annotation = hints.get(parameter.name, parameter.annotation)
        type_name, choices, nullable = _param_type_info(annotation)
        params.append({
            "name": parameter.name,
            "required": required,
            "default": None if required else parameter.default,
            "type": type_name,
            "choices": choices,
            "nullable": nullable,
            "description": arg_docs.get(parameter.name),
        })

    return {
        "tool": tool_id,
        "description": doc.split("\n", 1)[0] if doc else "",
        "origin": origin,
        "params": params,
        #: The declared return type, or None. With `params` above, this is the
        #: tool's whole boundary: what goes in, what comes out.
        "returns": returns,
        #: True when every parameter and the return are annotated (a
        #: **kwargs tool never is — 008 C12).
        "typed": not annotation_problems(fn),
        #: True when the tool takes **kwargs: keywords nobody can check.
        "open": _open_keywords(fn) is not None,
        # True when the tool declares **kwargs, so it receives every column and
        # `check` cannot verify its inputs against the upstream (§4).
        "takes_whole_row": takes_row,
    }


def catalog(tools: dict[str, Callable] | None = None) -> dict[str, dict]:
    """Every callable tool, id → :func:`tool_entry`, for a palette.

    Feeds the ``GET /tools`` response (docs/react-api.md §2). A user tool cannot
    shadow a builtin, so an id appears exactly once and ``origin`` is
    unambiguous.
    """
    entries = {}
    for name, fn in sorted(BUILTIN_TOOLS.items()):
        entries[name] = tool_entry(name, fn, "builtin")
        entries[name]["tags"] = []
    for name, fn in sorted((tools or {}).items()):
        entries[name] = tool_entry(name, fn.fn if isinstance(fn, Tool) else fn,
                                   "declared")
        entries[name]["tags"] = list(getattr(fn, "tags", ()))
    return entries


class BoundTool:
    """``res["db"].lookup`` — a bound tool waiting for its brackets.

    The method is found on the resource's **declared type** once the step is in
    a workflow; until then its tool id is ``"?.lookup"``. Brackets and parens
    work exactly as on a :class:`Tool`.
    """

    def __init__(self, ref: ResRef, method: str):
        self.ref, self.method = ref, method
        self.id = f"?.{method}"

    def _start(self) -> "Operation":
        return Operation(tool=self.id, bound_to=self.ref)

    def bind(self, **literals) -> "Operation":
        return self._start().bind(**literals)

    def __getitem__(self, modifiers: Any) -> "Operation":
        return self._start()[modifiers]

    def __call__(self, *args, **kwargs) -> Any:
        if args and isinstance(args[0], StepRef):
            return self._start()(*args, **kwargs)
        raise TypeError(
            f"res[{self.ref.name!r}].{self.method} has no instance until the "
            "workflow runs. Wire it into a step: "
            f"wf[...] = res[{self.ref.name!r}].{self.method}[mod.map()](wf[...])."
        )

    def __repr__(self) -> str:
        return f"<bound tool {self.ref!r}.{self.method}>"


#: The attribute ``@bound_tool`` sets on a method. The method is otherwise untouched.
_BOUND_MARK = "__simple_steps_bound_tool__"


def bound_tool(fn: Callable) -> Callable:
    """Mark a **method** of a resource class as a tool that runs on one instance.

    The method stays an ordinary method — ``FakeDB().lookup("SF")`` still works —
    and nothing is registered anywhere. The mark only records that the
    type offers it, so ``res["db"].lookup[mod.map()](…)`` can use it and the
    catalog can list it. Unmarked methods are never tools, though tool code may
    still call them::

        class FakeDB:
            @bound_tool
            def lookup(self, key: str) -> str | None: ...

            def reset(self) -> None: ...      # not a tool
    """
    try:
        first = next(iter(inspect.signature(fn).parameters), None)
    except (TypeError, ValueError):
        first = None
    if first != "self":
        raise TypeError(
            f"@bound_tool marks a method (first parameter `self`); "
            f"{getattr(fn, '__qualname__', fn)!r} is not one. "
            "Use @tool for a free function."
        )
    reserved = _reserved_problem(getattr(fn, "__name__", ""), "bound tool")
    if reserved:
        raise ValueError(reserved)
    setattr(fn, _BOUND_MARK, True)
    return fn


def _looks_like_method(fn: Callable) -> bool:
    """A function defined in a class body whose first parameter is ``self``."""
    parts = getattr(fn, "__qualname__", "").split(".")
    if len(parts) < 2 or parts[-2] == "<locals>":
        return False
    try:
        return next(iter(inspect.signature(fn).parameters), None) == "self"
    except (TypeError, ValueError):
        return False


def _signature(fn: Callable) -> inspect.Signature:
    """The signature with string annotations (PEP 563) resolved where possible."""
    try:
        return inspect.signature(fn, eval_str=True)
    except Exception:
        return inspect.signature(fn)


#: Every resource type a workflow has declared or ``@resource`` registered, by name.
#: ``Workflow.from_dict`` resolves a saved ``"type"`` through it.


def _settings(cls: type) -> list[inspect.Parameter]:
    """A resource type's settings: its constructor's named parameters."""
    try:
        parameters = list(_signature(cls.__init__).parameters.values())[1:]
    except (TypeError, ValueError):
        return []
    return [p for p in parameters
            if p.kind not in (inspect.Parameter.VAR_POSITIONAL,
                              inspect.Parameter.VAR_KEYWORD)]


def _bound_tools(cls: type) -> dict[str, Callable]:
    """The ``@bound_tool`` methods of *cls*, by name, base classes included.

    An unmarked override of a marked method is not a tool: the subclass chose
    to withdraw it.
    """
    found: dict[str, Callable] = {}
    for klass in reversed(cls.__mro__):
        for name, value in vars(klass).items():
            if callable(value) and getattr(value, _BOUND_MARK, False):
                found[name] = value
            elif name in found:
                del found[name]
    return found


def _method_view(cls: type, name: str) -> Callable:
    """The bound tool *name* of *cls*, as a function **without** ``self``.

    It carries the signature and docstring, which is everything ``check``,
    staging, verb inference and the catalog read. It cannot run — the real
    instance's method replaces it at run time.
    """
    # Cached on the class itself, so the same view comes back each time and
    # nothing is kept at module level.
    views = cls.__dict__.get("__simple_steps_views__")
    if views is None:
        views = {}
        setattr(cls, "__simple_steps_views__", views)
    if name not in views:
        method = _bound_tools(cls)[name]
        signature = _signature(method)

        def view(*args, **kwargs):
            raise TypeError(f"{cls.__name__}.{name} is a bound tool; it runs on "
                            "a resource instance supplied to Workflow.run")
        view.__signature__ = signature.replace(
            parameters=list(signature.parameters.values())[1:])
        view.__name__ = name
        view.__qualname__ = f"{cls.__name__}.{name}"
        view.__doc__ = method.__doc__
        view.__module__ = getattr(method, "__module__", None)
        views[name] = view
    return views[name]


def resource_problems(cls: type) -> list[str]:
    """Why *cls* cannot be a resource type — empty when it can."""
    problems = []
    for parameter in _settings(cls):
        if not _literal_annotation(parameter.annotation):
            problems.append(
                f"setting {parameter.name!r} is {_type_name(parameter.annotation)}; "
                "a resource is built from literal settings only (str, number, "
                "bool, list, dict), so it can always be rebuilt from its declaration"
            )
    return problems


def resource(cls: type) -> type:
    """Mark a class as a resource type, checking its settings are literals.

    Nothing is registered: a resource type is used by putting it in a
    :class:`Catalog` (``Catalog(resources=[ClinicalDB])``), and
    :meth:`Catalog.from_modules` finds every class marked with this.
    """
    problems = resource_problems(cls)
    reserved = _reserved_problem(cls.__name__, "resource type")
    if reserved:
        problems.append(reserved)
    if problems:
        raise TypeError(f"cannot declare resource type {cls.__name__!r}: "
                        + "; ".join(problems) + ".")
    cls.__simple_steps_resource__ = True
    return cls


def resource_entry(cls: type) -> dict:
    """One resource type for a palette: its settings, bound tools and bases."""
    doc = (inspect.getdoc(cls) or "").strip()
    settings = []
    for parameter in _settings(cls):
        required = parameter.default is inspect.Parameter.empty
        settings.append({
            "name": parameter.name,
            "type": _type_name(parameter.annotation),
            "required": required,
            "default": None if required else parameter.default,
        })
    return {
        "type": cls.__name__,
        "description": doc.split("\n", 1)[0] if doc else "",
        "settings": settings,
        "tools": {f"{cls.__name__}.{name}":
                  tool_entry(f"{cls.__name__}.{name}", _method_view(cls, name), "bound")
                  for name in sorted(_bound_tools(cls))},
        #: Every type this one is, so a client can show which resources fit a
        #: parameter declared as a base (`llm: LLM`).
        "bases": [k.__name__ for k in cls.__mro__ if k is not object],
    }


def resource_catalog(types_: dict[str, type] | None = None) -> dict[str, dict]:
    """Every registered resource type, name → :func:`resource_entry`."""
    return {name: resource_entry(cls)
            for name, cls in sorted((types_ or {}).items())}


@dataclass
class Resource:
    """How a workflow declared a resource — what is saved, never the object."""

    name: str
    #: The class, or ``None`` when a loaded workflow names a type this process
    #: does not have. Declaring still works; type checks are skipped.
    type: type | None
    settings: dict
    type_name: str
    source: str = "defined"
    #: The app's additions, by namespace. Saved, never read by core.
    extras: dict = field(default_factory=dict)

    @property
    def secrets(self) -> tuple[str, ...]:
        """The names of its ``Secret[…]`` settings (R3)."""
        return secret_settings(self.type) if self.type is not None else ()

    @property
    def spec(self) -> "ResourceSpec":
        """What is needed to build this resource: its type's name and settings.

        Never its secrets: the spec is what is saved, hashed and shown.
        """
        hidden = self.secrets
        return ResourceSpec(self.name, self.type_name,
                            {k: v for k, v in self.settings.items() if k not in hidden},
                            _checked_extras(self.extras), self.source)

    def to_dict(self) -> dict:
        return self.spec.to_dict()

    def __repr__(self) -> str:
        hidden = self.secrets
        shown = ", ".join(f"{k}={'•••' if k in hidden else repr(v)}"
                          for k, v in self.settings.items())
        return f"Resource({self.name!r}, {self.type_name}({shown}))"


def code_hash(name: str, obj: Any) -> str:
    """The hash of a tool or a resource type: its name, its source (its
    compiled code when the source can't be read) and the version of the
    library it comes from."""
    try:
        source = inspect.getsource(obj)
    except (OSError, TypeError):
        code = getattr(obj, "__code__", None)
        source = repr((code.co_code, code.co_consts)) if code is not None else repr(obj)
    module = getattr(obj, "__module__", None) or ""
    library = module.split(".", 1)[0]
    try:
        from importlib.metadata import version
        library += " " + version(library)
    except Exception:                               # not an installed package
        pass
    text = "\0".join((name, source, library))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def secret_settings(cls: type) -> tuple[str, ...]:
    """The settings of *cls* declared ``Secret[…]``."""
    return tuple(p.name for p in _settings(cls) if is_secret(p.annotation))


def data_version(obj: Any) -> str | None:
    """A resource's own data version (K25): ``obj.data_version()`` when its type
    defines one, as text; None when it doesn't. It is asked before each run."""
    method = getattr(obj, "data_version", None)
    if not callable(method):
        return None
    return str(method())


def _type_fits(cls: type, annotation: Any) -> bool | None:
    """Does an instance of *cls* fit *annotation*? ``None`` when undecidable."""
    if annotation is inspect.Parameter.empty or isinstance(annotation, str):
        return None
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        answers = [_type_fits(cls, a) for a in typing.get_args(annotation)]
        if any(a is True for a in answers):
            return True
        return False if all(a is False for a in answers) else None
    base = origin or annotation
    if not isinstance(base, type) or base is object:
        return None
    return issubclass(cls, base)


def _attach_bound(operation: "Operation", resources: dict) -> "Operation":
    """Give a bound-tool Operation its type-qualified id and its method view.

    Left as is when the resource or the method cannot be found — :func:`check`
    then says which.
    """
    if operation.bound_to is None:
        return operation
    decl = resources.get(operation.bound_to.name)
    method = operation.tool.rsplit(".", 1)[-1]
    if decl is None or decl.type is None or method not in _bound_tools(decl.type):
        return replace(operation, fn=None)
    return replace(operation, tool=f"{decl.type.__name__}.{method}",
                   fn=_method_view(decl.type, method))


def _no_resource(name: str, workflow: "Workflow") -> str:
    declared = ", ".join(map(repr, workflow.resources)) or "none"
    return (f"no resource named {name!r} (declared: {declared}). "
            f"Declare it first: wf.define({name!r}, <Type>, ...)")


def _bound_problem(operation: "Operation", workflow: "Workflow | None") -> str:
    """Why a bound tool's method could not be found."""
    name = operation.bound_to.name
    method = operation.tool.rsplit(".", 1)[-1]
    if workflow is None:
        return (f"{method} is bound to resource {name!r}, which only a workflow "
                "can declare")
    decl = workflow.resources.get(name)
    if decl is None:
        return _no_resource(name, workflow)
    if decl.type is None:
        return (f"resource {name!r} has type {decl.type_name!r}, which is not "
                "available here — pass resource_types= when loading")
    tools = ", ".join(sorted(_bound_tools(decl.type))) or "(none)"
    return f"{method} is not a tool of {decl.type.__name__}; its tools are: {tools}"


class Tool:
    """What ``@tool`` returns: the plain function, plus a name and brackets.

    **Parens run, brackets decorate** — the same contract a bracket-decorator
    has outside this system, and the only calling rule in it::

        transcribe({"path": "a.mp4"})              # a plain call, undecorated
        transcribe[mod.map(over=videos)](videos)   # decorated, then run

    Decorating a tool never touches the function, so the same tool is bare in
    one step and mapped in another.
    """

    def __init__(self, fn: Callable, tool_id: str | None = None):
        self.fn = fn
        self.id = tool_id or fn.__name__
        self.__doc__ = fn.__doc__
        self.__name__ = self.id
        self._hash: str | None = None
        #: Free labels, from ``@tool(tags=…)``.
        self.tags: tuple[str, ...] = ()
        #: The app's additions, by namespace, from ``@tool(extras=…)``. Core
        #: keeps them and never reads them (docs/design/extensions.md).
        self.extras: dict = {}

    @property
    def hash(self) -> str:
        """``sha256(name, source, library + version)``, first 16 hex digits (K20).

        Computed once. Its tags and extras aren't in it: two tools that differ
        only there are the same code.
        """
        if self._hash is None:
            self._hash = code_hash(self.id, self.fn)
        return self._hash

    def __call__(self, *args, **kwargs) -> Any:
        """Apply the tool to its input — running it, or wiring it into a step.

        ``score(3)`` runs the plain function. ``score(wf["raw"])`` has no data
        to run on, so it builds the step instead, inferring how to iterate::

            wf["scored"] = score(wf["raw"])      # -> map(over='raw') ∘ score

        The two cannot be confused: a :class:`StepRef` is never data.
        """
        if args and isinstance(args[0], StepRef):
            # Anything after the input binds by position (008 C1).
            return self._start()(*args, **kwargs)
        if any(isinstance(a, Operation) for a in (*args, *kwargs.values())):
            raise TypeError(_NESTED_OPERATION)
        if len(args) == 1 and _runs_over_rows(self.fn, args[0], kwargs):
            # 009 decision 7: a frame whose rows are the arguments runs over them.
            return self._start().bind(**kwargs)[mod.auto()](args[0])
        return self.fn(*args, **kwargs)

    def bind(self, **literals) -> Operation:
        """Fix some arguments now, leaving the rest to arrive with each row.

        ``score.bind(threshold=5)[mod.map(over=rows)]`` — the literals become
        the Operation's ``arguments`` and are applied innermost, inside every
        modifier, so a retry re-runs the same call and a map passes them to
        every item. A value may be a :class:`StepRef`: a *value reference*
        (K10), kept as the ref and resolved to that step's value at run.
        """
        return Operation(tool=self.id, arguments=dict(literals), fn=self.fn)

    def _start(self) -> Operation:
        return Operation(tool=self.id, fn=self.fn)

    def __getitem__(self, modifiers: Any) -> Operation:
        """``transcribe[mod.map(over=videos), mod.retry(times=2)]`` — decorate.

        Returns an :class:`Operation` (data), never a wrapped function. Bound
        literals survive it: ``transcribe.bind(model="large")[mod.map(...)]``.
        """
        return self._start()[modifiers]

    def __repr__(self) -> str:
        return f"<tool {self.id!r}>"


def builtin_tools() -> dict[str, Callable]:
    """The tools core always has (identity, gather, count, total, first, last)."""
    return dict(BUILTIN_TOOLS)


def shape_verbs() -> tuple[str, ...]:
    """The modifier kinds that change a grid's shape."""
    return tuple(SHAPE_VERBS)


def value_column(output: Any) -> str | None:
    """The column a step (or Output) writes its tool's results to, or None.

    008 C3: read this instead of assuming ``VALUE_COLUMN`` — a step may name its
    payload (``name=``), and some verbs write none.
    """
    if isinstance(output, Step):
        output = output.output
    return output.meta.get("value_column") if isinstance(output, Output) else None


def check_modifier(kind: str, params: dict | None = None) -> tuple[str, ...]:
    """Problems with one modifier on its own — no tool, no workflow (008 C3/O).

    A misspelt setting, a wrong type, a missing required setting: what a formula
    bar can say while the modifier is still being typed.
    """
    params = dict(params or {})
    params.pop("over", None)
    return check(Operation(tool="identity", fn=identity,
                           modifiers=(Modifier(kind, params),)))


def tool(fn: Callable | None = None, *, id: str | None = None,
         strict: bool = False, tags: Sequence[str] = (),
         extras: Mapping[str, Any] | None = None):
    """Make a plain function a tool. Usable bare or with arguments.

    It returns the :class:`Tool` and registers it nowhere: a tool is used
    by putting it in a :class:`Catalog`. *id* names it (the function's name
    otherwise); *tags* are free labels; *extras* are the app's additions, by
    namespace.

    *strict* requires a type annotation on every parameter and on the return,
    refusing the tool when one is missing (``Catalog(..., strict=True)`` asks
    the same of every tool in a catalog). The annotations are not decoration:
    ``check`` compares them against the upstream's real dtypes, and the catalog
    publishes them as the tool's boundary.
    """
    if isinstance(tags, str) or not all(isinstance(t, str) for t in tags):
        raise TypeError("tags= takes a list of strings, e.g. tags=['rowmap']")
    extras = _checked_extras(extras)

    def make(f: Callable, tool_id: str | None) -> Tool:
        if _looks_like_method(f):
            # @tool on a method used to replace it with a handle that never
            # receives `self`, breaking the method and registering a global
            # tool `lookup(self, key)`. A method belongs to a resource.
            raise TypeError(
                f"{f.__qualname__} is a method. Mark it @bound_tool so it runs "
                "on a resource instance (res[\"name\"]." + f.__name__ + "); "
                "@tool is for free functions."
            )
        handle = Tool(f, tool_id)
        reserved = _reserved_problem(handle.id, "tool")
        if reserved:
            raise ValueError(f"cannot declare tool {handle.id!r}: {reserved}")
        found = declaration_problems(f, handle.id)
        if found:
            raise TypeError(
                f"cannot declare tool {handle.id!r}: " + "; ".join(found) + "."
            )
        open_ = _open_keywords(f)
        if open_ and not strict:
            # 008 C12: allowed, but said out loud — strict mode refuses it.
            warnings.warn(
                f"{handle.id} accepts **{open_}: its extra keywords can't be "
                "checked, typed or shown in a form. Name the parameters you "
                "expect.", stacklevel=3)
        if strict:
            found = annotation_problems(f)
            if found:
                raise TypeError(
                    f"tool {handle.id!r} is not fully typed: {'; '.join(found)}. "
                    "A step's boundary is its annotations — they are what "
                    "`check` compares against the upstream's dtypes and what a "
                    "palette shows a user. Annotate it, or declare it with "
                    "strict=False."
                )
        if handle.id in BUILTIN_TOOLS:
            # Shadowing a builtin is never intended and never harmless: the
            # shape verbs resolve `identity` and `gather` by name, so a
            # same-named user tool would quietly change what `select` or a bare
            # `collapse` does. Refused at import, where it is cheap to rename.
            raise ValueError(
                f"{handle.id!r} is a builtin tool ({BUILTIN_TOOLS[handle.id].__doc__ or ''}"
                f"). Give yours another name, or pass id= to rename it."
            )
        handle.tags, handle.extras = tuple(tags), dict(extras)
        return handle

    if fn is not None:
        return make(fn, None)
    return lambda f: make(f, id)


def formula_names(tools: dict[str, Callable] | None = None) -> dict[str, Any]:
    """The names a formula may use: ``wf res mod rows cols op join stack zip_``
    and every declared tool. What :meth:`Operation.to_source` is written against.

    For checking a formula round-trips in Python. A formula bar should parse
    with its own grammar, never ``eval`` text a user typed.
    """
    names: dict[str, Any] = {"wf": wf, "res": res, "mod": mod, "rows": rows,
                             "cols": cols, "op": op, "join": join,
                             "stack": stack, "zip_": zip_}
    for tool_id, fn in (tools or {}).items():
        if tool_id.isidentifier():
            names[tool_id] = fn if isinstance(fn, Tool) else Tool(fn, tool_id)
    return names


def _checked_extras(extras: Mapping[str, Any] | None) -> dict:
    """*extras* as a plain dict, refused unless every key is a namespace.

    A namespace is a dotted name owned by whoever writes it
    (``"simple_steps.ui"``), so two front ends can't overwrite each other's
    additions. Values must be literals: extras hold values, never code
    (docs/design/extensions.md §3).
    """
    if extras is None:
        return {}
    if not isinstance(extras, Mapping):
        raise TypeError("extras= takes a mapping of namespace → value, "
                        "e.g. extras={'simple_steps.ui': {'when': 'date-picker'}}")
    for key, value in extras.items():
        if not isinstance(key, str) or "." not in key.strip("."):
            raise ValueError(f"extras key {key!r} must be a dotted namespace, "
                             "such as 'simple_steps.ui'")
        if not _json_safe(value):
            raise TypeError(f"extras[{key!r}] must hold literals (str, number, "
                            f"bool, None, list, dict), got {type(value).__name__}")
    return dict(extras)


def _outside(message: str) -> Problem:
    return Problem(message, "not_in_catalog")


class Catalog:
    """What a workflow may use: tools, resource types, modifiers and combines.

    Fixed once made. A workflow given a catalog checks every step against it,
    when the step is declared and when it is loaded, and runs each step with the
    catalog's own function: a step whose tool, modifier, combine or resource type
    isn't in the catalog is a problem on the step and never runs
    (docs/design/object-model.md §4.3)::

        cat = Catalog(tools=[patients, to_f], resources=[ClinicalDB])
        cat = Catalog.from_modules(my_tools)
        cat = cat.without("count", "retry")

    The built-in tools, every modifier and every combine are in a catalog by
    default; :meth:`without` removes any of them.
    """

    def __init__(self, tools: Iterable[Any] = (), resources: Iterable[type] = (), *,
                 strict: bool = False):
        found: dict[str, Tool] = {}
        for item in tools:
            if not isinstance(item, Tool):
                name = getattr(item, "__name__", repr(item))
                raise TypeError(
                    f"{name} is not a tool. Decorate it with @tool, then pass it "
                    "to the catalog.")
            if item.id in found and found[item.id].fn is not item.fn:
                raise ValueError(
                    f"two different tools are named {item.id!r}; rename one with "
                    "@tool(id=…)")
            if strict:
                missing = annotation_problems(item.fn)
                if missing:
                    raise TypeError(f"tool {item.id!r} is not fully typed: "
                                    f"{'; '.join(missing)}. A strict catalog needs "
                                    "every parameter and the return annotated.")
            found[item.id] = item
        kinds: dict[str, type] = {}
        for cls in resources:
            if not isinstance(cls, type):
                raise TypeError(f"{cls!r} is not a resource type: pass the class")
            problems = resource_problems(cls)
            if problems:
                raise TypeError(f"{cls.__name__} can't be a resource type: "
                                + "; ".join(problems) + ".")
            if cls.__name__ in kinds and kinds[cls.__name__] is not cls:
                raise ValueError(f"two different resource types are named "
                                 f"{cls.__name__!r}")
            kinds[cls.__name__] = cls
        self._tools = found
        self._resource_types = kinds
        self._builtins = frozenset(BUILTIN_TOOLS)
        self._modifiers = frozenset(MODIFIERS)
        self._combines = frozenset(COMBINE)
        # K20: hashed once, as the catalog is built.
        for item in found.values():
            item.hash
        self._type_hashes = {name: code_hash(name, kind) for name, kind in kinds.items()}

    def hash_of(self, name: str) -> str | None:
        """The hash of the code a step names: a tool's, a bound tool's resource
        type's, or core's version for a built-in, a modifier or a combine.
        None for a name not in this catalog."""
        if name in self._tools:
            return self._tools[name].hash
        type_name = name.split(".", 1)[0]
        if "." in name and type_name in self._type_hashes:
            return self._type_hashes[type_name]
        if name in self._builtins or name in self._modifiers or name in self._combines:
            from . import __version__
            return hashlib.sha256(f"simple_steps_core {__version__}".encode()).hexdigest()[:16]
        return None

    def type_hash(self, type_name: str) -> str | None:
        """The hash of resource type *type_name*'s code; None when not in it."""
        return self._type_hashes.get(type_name)

    @classmethod
    def from_modules(cls, *modules: types.ModuleType, strict: bool = False) -> "Catalog":
        """Every ``@tool`` and every resource type defined in *modules*."""
        tools_, kinds = [], []
        for module in modules:
            for value in vars(module).values():
                if isinstance(value, Tool):
                    tools_.append(value)
                elif (isinstance(value, type) and value.__module__ == module.__name__
                      and value.__dict__.get("__simple_steps_resource__")):
                    kinds.append(value)
        return cls(tools_, kinds, strict=strict)

    def without(self, *names: str) -> "Catalog":
        """A copy without the named tools, resource types, built-ins, modifiers
        or combines. A name the catalog doesn't have is refused, so a typo
        doesn't silently leave something in."""
        unknown = [n for n in names if n not in self]
        if unknown:
            raise KeyError(f"not in this catalog: {', '.join(map(repr, unknown))}")
        out = object.__new__(Catalog)
        out._tools = {k: v for k, v in self._tools.items() if k not in names}
        out._resource_types = {k: v for k, v in self._resource_types.items()
                               if k not in names}
        out._builtins = self._builtins - set(names)
        out._modifiers = self._modifiers - set(names)
        out._combines = self._combines - set(names)
        out._type_hashes = {k: v for k, v in self._type_hashes.items()
                            if k in out._resource_types}
        return out

    # ── what it holds ────────────────────────────────────────────────────
    @property
    def tools(self) -> dict[str, Tool]:
        """The developer's tools, by name."""
        return dict(self._tools)

    @property
    def resource_types(self) -> dict[str, type]:
        """The resource types, by name."""
        return dict(self._resource_types)

    @property
    def builtins(self) -> frozenset[str]:
        """The built-in tools this catalog keeps."""
        return self._builtins

    @property
    def modifiers(self) -> frozenset[str]:
        """The modifier kinds this catalog keeps."""
        return self._modifiers

    @property
    def combines(self) -> frozenset[str]:
        """The combines this catalog keeps (``join``, ``stack``, ``zip``)."""
        return self._combines

    @property
    def functions(self) -> dict[str, Callable]:
        """Tool name → the plain function: developer tools and built-ins. What
        a workflow with this catalog runs steps with."""
        out = {name: BUILTIN_TOOLS[name] for name in self._builtins}
        out.update({name: t.fn for name, t in self._tools.items()})
        return out

    def __contains__(self, name: object) -> bool:
        return (name in self._tools or name in self._resource_types
                or name in self._builtins or name in self._modifiers
                or name in self._combines)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Catalog):
            return NotImplemented
        return ({k: t.fn for k, t in self._tools.items()}
                == {k: t.fn for k, t in other._tools.items()}
                and self._resource_types == other._resource_types
                and self._builtins == other._builtins
                and self._modifiers == other._modifiers
                and self._combines == other._combines)

    __hash__ = None

    def __repr__(self) -> str:
        def names(items) -> str:
            return ", ".join(sorted(items)) or "(none)"
        removed = (len(BUILTIN_TOOLS) - len(self._builtins)
                   + len(MODIFIERS) - len(self._modifiers)
                   + len(COMBINE) - len(self._combines))
        lines = [f"Catalog: {len(self._tools)} tools, {len(self._resource_types)} "
                 f"resource types" + (f", {removed} built-ins removed" if removed else ""),
                 f"  tools           {names(self._tools)}",
                 f"  resource types  {names(self._resource_types)}",
                 f"  built-in tools  {names(self._builtins)}",
                 f"  modifiers       {names(self._modifiers)}",
                 f"  combines        {names(self._combines)}"]
        return "\n".join(lines)

    @property
    def spec(self) -> "CatalogSpec":
        """The names this catalog allows, and each tool's extras. Never code."""
        return CatalogSpec(
            tools={name: {"hash": t.hash, "extras": dict(t.extras)}
                   for name, t in sorted(self._tools.items())},
            resource_types=tuple(sorted(self._resource_types)),
            builtins=tuple(sorted(self._builtins)),
            modifiers=tuple(sorted(self._modifiers)),
            combines=tuple(sorted(self._combines)))

    def describe(self) -> dict:
        """Every entry as plain data, for a palette, a form or an agent.

        ``tools`` (built-ins first, marked by ``origin``), ``modifiers``,
        ``combines`` and ``resource_types``, each restricted to this catalog.
        """
        entries = {}
        for name in sorted(self._builtins):
            entries[name] = tool_entry(name, BUILTIN_TOOLS[name], "builtin")
            entries[name]["tags"], entries[name]["extras"] = [], {}
        for name, handle in sorted(self._tools.items()):
            entries[name] = tool_entry(name, handle.fn, "declared")
            entries[name]["tags"] = list(handle.tags)
            entries[name]["extras"] = dict(handle.extras)
        kinds = modifier_catalog()
        return {
            "tools": entries,
            "modifiers": {k: kinds[k] for k in sorted(self._modifiers)},
            "combines": sorted(self._combines),
            "resource_types": {name: resource_entry(cls)
                               for name, cls in sorted(self._resource_types.items())},
        }

    # ── checking a step against it ───────────────────────────────────────
    def problems(self, operation: Operation, workflow: Any = None) -> list[Problem]:
        """What *operation* uses that this catalog doesn't have."""
        found: list[Problem] = []
        if operation.bound_to is not None:
            decl = (workflow.resources.get(operation.bound_to.name)
                    if workflow is not None else None)
            if decl is not None and decl.type_name not in self._resource_types:
                found.append(_outside(f"resource type {decl.type_name!r} is not in this "
                             "workflow's catalog"))
        elif is_combine(operation):
            if operation.tool not in self._combines:
                found.append(_outside(f"{operation.tool!r} is not in this workflow's catalog"))
        else:
            name = operation.tool
            if name in self._tools:
                if operation.fn is not None and operation.fn is not self._tools[name].fn:
                    found.append(Problem(
                        f"{name!r} is a different function from the tool of that name "
                        "in this workflow's catalog", "different_function"))
            elif name not in self._builtins:
                found.append(_outside(f"{name!r} is not in this workflow's catalog"))
        for m in operation.modifiers:
            if m.kind not in self._modifiers:
                found.append(_outside(f"modifier {m.kind!r} is not in this workflow's catalog"))
        values = [*operation.arguments.values(),
                  *(v for m in operation.modifiers for v in m.settings.values())]
        for value in values:
            name = (value.id if isinstance(value, (Tool, ToolRef)) else None)
            if name is not None and name not in self._tools and name not in self._builtins:
                found.append(_outside(f"tool {name!r} is not in this workflow's catalog"))
        return found

    def admit(self, operation: Operation) -> Operation:
        """*operation* carrying this catalog's function for its tool, so it runs
        the catalog's code and nothing else. Unchanged when the tool isn't here
        (that is a problem :meth:`problems` reports)."""
        if operation.bound_to is not None or is_combine(operation):
            return operation
        fn = self.functions.get(operation.tool)
        if fn is None or (operation.fn is not None and operation.fn is not fn):
            return operation
        return replace(operation, fn=fn)


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .system_tools import BUILTIN_TOOLS, identity  # noqa: E402
from .checks import check  # noqa: E402
from .problems import Problem  # noqa: E402
from .specs import CatalogSpec, ResourceSpec  # noqa: E402
from .combines import COMBINE, is_combine, join, stack, zip_  # noqa: E402
from .modifiers import MODIFIERS, Modifier, SHAPE_VERBS, mod, modifier_catalog  # noqa: E402
from .operation import Operation, _NESTED_OPERATION, op  # noqa: E402
from .output import Output  # noqa: E402
from .references import (  # noqa: E402
    ResRef,
    StepRef,
    ToolRef,
    _reserved_problem,
    cols,
    res,
    rows,
    wf,
)
from .run import _runs_over_rows  # noqa: E402
from .step import Step  # noqa: E402
from .values import (  # noqa: E402
    _json_safe,
    _literal_annotation,
    is_secret,
    _open_keywords,
    _type_name,
    annotation_problems,
    declaration_problems,
)
from .workflow import Workflow  # noqa: E402
