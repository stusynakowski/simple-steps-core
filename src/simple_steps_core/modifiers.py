"""Modifiers: the modifier kinds, their run-time decorators, Modifier and mod.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Callable
from typing import Sequence
import inspect

from .verbs import (
    auto_,
    collapse_,
    distinct_,
    drop_,
    expand_,
    filter_,
    group_,
    map_,
    rename_,
    select_,
    slice_,
    sort_,
    source_,
    sweep_,
    table_,
    widen_,
)


# ─────────────────────────────────────────────────────────────────────────
# Compiling a stack into real runtime decorators
# ─────────────────────────────────────────────────────────────────────────
# The stack is stored as data so staging and serialization work. At run time
# it is *applied* — each modifier is a genuine higher-order function, wrapped
# innermost-first, exactly as `@` would have done at definition time.
#
# Two kinds, distinguished by what they do to the signature:
#   shape verbs       lift it:      (a -> b)  becomes  ([a] -> Output)
#   execution mods    preserve it:  (a -> b)  stays    (a -> b)
def _d_retry(fn: Callable, *, times: int) -> Callable:
    """Preserves the signature; retries whatever it wraps."""
    def run(x):
        last = None
        for _ in range(times + 1):
            try:
                return fn(x)
            except Exception as exc:
                last = exc
        raise last
    run.__name__ = f"retry({getattr(fn, '__name__', 'fn')})"
    return run


#: "No default given" to `mod.try_except` — distinct from `default=None`.
_NO_DEFAULT = object()


def _caught_by(exc: BaseException, on: Sequence[str] | None) -> bool:
    """Is *exc* one of the exception types named in ``on=`` (any, when None)?"""
    if not on:
        return True
    names = {on} if isinstance(on, str) else set(on)
    return any(k.__name__ in names for k in type(exc).__mro__)


def _d_try_except(fn: Callable, *, default: Any = _NO_DEFAULT,
                  on: Sequence[str] | None = None) -> Callable:
    """``mod.try_except(default=0, on=[ValueError])`` — let a unit's failure through.

    Without it, a failed row stops ``run_all``. With it, a caught failure
    either becomes ``default`` (the row completes; the error stays in the
    ledger) or, with no default, the row stays failed and the run carries on —
    rows that read it downstream are blocked, not run. ``on=`` limits which
    exceptions are caught; others still stop the run. Order is semantics:
    ``[mod.try_except(…), mod.retry(times=2)]`` retries first.
    """
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (_Tolerated, _Stopped):
            raise
        except Exception as exc:
            if not _caught_by(exc, on):
                raise
            error = f"{type(exc).__name__}: {exc}"
            if default is not _NO_DEFAULT:
                return _Caught(default, error)
            raise _Tolerated(error) from exc
    run.__name__ = f"try_except({getattr(fn, '__name__', 'fn')})"
    return run


#: What auto's breaker stops after (009 decision 4).
BREAKER_AFTER = 5


def _d_breaker(fn: Callable, *, after: int | None = BREAKER_AFTER) -> Callable:
    """``mod.breaker(after=5)`` — stop a step after *after* failures in a row.

    Cheap failures (009 §7): one bad row never trips it, but a systematic
    error — a bad API key, a broken tool — costs *after* calls instead of one
    per row. Once tripped, the rest of the step's units are recorded as *"not
    run: stopped after 5 failures in a row (…)"* with no call made; work
    already done is kept. ``after=None`` never stops early. Auto adds
    ``breaker(after=5)`` to row-wise steps; writing one replaces that default.
    """
    if after is None:
        return fn
    state = {"streak": 0, "kind": None, "first": None, "tripped": None}

    def run(*args, **kwargs):
        if state["tripped"]:
            raise _Stopped(state["tripped"])
        try:
            value = fn(*args, **kwargs)
        except Exception as exc:
            text = str(exc) if isinstance(exc, _Tolerated) else f"{type(exc).__name__}: {exc}"
            kind = text.split(":", 1)[0]
            if kind == state["kind"]:
                state["streak"] += 1
            else:
                state.update(streak=1, kind=kind, first=text)
            if state["streak"] >= after:
                state["tripped"] = (f"not run: stopped after {after} failures in a "
                                    f"row ({state['first']})")
            raise
        state.update(streak=0, kind=None)
        return value
    run.__name__ = f"breaker({getattr(fn, '__name__', 'fn')})"
    return run


def _d_expect(fn: Callable, *, rows: int | None = None, min_rows: int | None = None,
              max_rows: int | None = None, columns: Any = None,
              more_columns: bool = False) -> Callable:
    """``mod.expect(…)`` — what the author knows the step's output will be (008 C9).

    It changes nothing about how the tool runs. Staging uses it as the plan
    (marked ``stated``), declaration refuses it when it contradicts what core
    already knows, and the run fails the step when the output doesn't match.
    ``columns`` is a list of names, or ``{name: type}``; ``more_columns=True``
    says those are some of the columns, not all.
    """
    return fn


def _d_timeout(fn: Callable, *, seconds: float) -> Callable:
    """Placeholder: records intent. Real enforcement needs the async engine."""
    def run(x):
        return fn(x)
    run.__name__ = f"timeout({getattr(fn, '__name__', 'fn')})"
    return run


def _d_apply(fn: Callable, **literals) -> Callable:
    """Innermost decoration: hand the tool the columns it actually asked for.

    **Supplying rows is the modifier's job, not the tool's.** A tool declares
    the values it needs and nothing else::

        @tool
        def score(n, weight=1):        # not  def score(row): row["n"] * 10
            return n * 10 * weight

    ``map`` then binds each row's columns to those parameters by name — the
    same thing the engine's ``_run_item`` does when it sets ``kwargs[arg] =
    item``. Without this a tool has to name the row twice, once as a parameter
    and once as a lookup, which makes it unusable unmapped and hard-codes the
    column name in the body.

    Rules:

    * columns bind to parameters **by name**; anything the tool does not
      declare is simply not passed;
    * a tool with ``**kwargs`` receives the whole row, for the cases that
      genuinely want it (``identity``);
    * bound arguments fill the rest, and an explicit argument **wins** a name
      collision with a column (008 N2): the step says ``city="NYC"``, so the
      tool gets ``"NYC"`` whether or not the input happens to have a ``city``;
    * a non-dict input (an unorchestrated step over a bare value) is passed
      positionally, since there are no columns to bind.

    ``*leading`` carries ``collapse``'s accumulator, the one verb whose tool
    takes something before the row.
    """
    try:
        parameters = inspect.signature(fn).parameters
    except (TypeError, ValueError):                  # builtins have no signature
        parameters = {}
    wants_everything = any(p.kind is inspect.Parameter.VAR_KEYWORD
                           for p in parameters.values())
    declared = set(parameters)

    def run(*args):
        *leading, row = args
        if not isinstance(row, dict):
            return fn(*leading, row, **literals)
        merged = {**row, **literals}
        bound = merged if wants_everything else {
            k: v for k, v in merged.items() if k in declared
        }
        return fn(*leading, **bound)

    run.__name__ = f"apply({getattr(fn, '__name__', 'fn')})"
    # The verbs that apply no tool (source, select) need to recognize identity
    # through this wrapper — compile_operation always applies it, so comparing
    # against the bare function would never match.
    run.__wrapped__ = fn
    return run


def _lift(verb: Callable) -> Callable:
    """Turn a verb into a decorator that lifts (a -> b) into (source -> Output)."""
    def make(fn: Callable, **params) -> Callable:
        params.pop("over", None)          # `over` names the source, not a param
        def run(source):
            return verb(source, fn, **params)
        run.__name__ = f"{verb.__name__.rstrip('_')}({getattr(fn, '__name__', 'fn')})"
        return run
    return make


@dataclass(frozen=True)
class ModifierKind:
    """One entry in the modifier vocabulary: its class, and how it applies.

    ``cls`` is not taxonomy — it says what the modifier does to the signature
    it wraps, which is what lets staging fold shape *without running*:

    ``"shape"``
        lifts it — ``(row -> b)`` becomes ``(source -> Output)``. Changes rows
        or columns, so staging must fold it.
    ``"execution"``
        preserves it — ``(row -> b)`` stays ``(row -> b)``. Shape-preserving,
        so staging ignores it entirely.
    """

    name: str
    cls: str                     # "shape" | "execution"
    apply: Callable              # (fn, **params) -> fn
    #: The parameter names this kind accepts, derived from the underlying verb
    #: or decorator. ``None`` means "anything" — only ``sweep``, whose
    #: parameters *are* the user's own names.
    accepts: frozenset[str] | None = None
    #: The raw verb/decorator function, kept for introspection only
    #: (:func:`modifier_catalog` reads its defaults). Never serialized.
    verb: Callable | None = None


def _accepted_params(fn: Callable, extra: Sequence[str] = ()) -> frozenset[str] | None:
    """Keyword names *fn* takes, or None when it takes arbitrary ones."""
    try:
        parameters = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return None
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return None                              # sweep: the params are the data
    names = {p.name for p in parameters
             if p.kind in (inspect.Parameter.KEYWORD_ONLY,
                           inspect.Parameter.POSITIONAL_OR_KEYWORD)}
    return frozenset(names - {"source", "fn"} | set(extra))


def _kind(name: str, cls: str, apply: Callable,
          verb: Callable | None = None) -> ModifierKind:
    # `over` names the step this modifier reads; every shape verb takes it even
    # though the verb function itself never sees it (`_lift` pops it).
    # `over` is authoring sugar for the input and is hoisted out of the
    # modifier, so it is never a stored modifier parameter.
    extra = ()
    return ModifierKind(name, cls, apply,
                        _accepted_params(verb, extra) if verb else None,
                        verb)


def _lift_generated(verb: Callable) -> Callable:
    """Like :func:`_lift`, for a verb that *generates* its rows.

    ``sweep`` builds its grid from parameter lists, so it has no input to
    coerce — it still takes a source argument, and still ignores it, so that
    every compiled stack has one uniform signature.
    """
    def make(fn: Callable, **params) -> Callable:
        params.pop("over", None)
        def run(_source: Any = None):
            return verb(fn, **params)
        run.__name__ = f"{verb.__name__.rstrip('_')}({getattr(fn, '__name__', 'fn')})"
        return run
    return make


#: **The modifier vocabulary — the one place a modifier kind is declared.**
#: Adding a verb means adding one entry here; the classification, the
#: validation in ``mod``, and the runtime decorators all derive from it, so
#: there is no second list to keep in step.
MODIFIERS: dict[str, ModifierKind] = {k.name: k for k in (
    # shape verbs — at most one decides the step's final shape (§1.1)
    _kind("source",   "shape", _lift(source_), source_),
    _kind("map",      "shape", _lift(map_), map_),
    _kind("filter",   "shape", _lift(filter_), filter_),
    _kind("select",   "shape", _lift(select_), select_),
    _kind("drop",     "shape", _lift(drop_), drop_),
    _kind("widen",    "shape", _lift(widen_), widen_),
    _kind("slice",    "shape", _lift(slice_), slice_),
    _kind("rename",   "shape", _lift(rename_), rename_),
    _kind("sort",     "shape", _lift(sort_), sort_),
    _kind("distinct", "shape", _lift(distinct_), distinct_),
    _kind("group",    "shape", _lift(group_), group_),
    _kind("expand",   "shape", _lift(expand_), expand_),
    _kind("collapse", "shape", _lift(collapse_), collapse_),
    _kind("sweep",    "shape", _lift_generated(sweep_), sweep_),
    _kind("table",    "shape", _lift(table_), table_),
    _kind("auto",     "shape", _lift(auto_), auto_),
    # execution modifiers — shape-preserving
    _kind("retry",    "execution", _d_retry, _d_retry),
    _kind("timeout",  "execution", _d_timeout, _d_timeout),
    _kind("expect",   "execution", _d_expect, _d_expect),
    _kind("try_except", "execution", _d_try_except, _d_try_except),
    _kind("breaker",  "execution", _d_breaker, _d_breaker),
)}


#: What type each modifier parameter must be. Checked at declaration, because
#: staging reads several of them to predict columns — a list where a column
#: *name* belongs used to crash inside `stage()` with `unhashable type: 'list'`,
#: which named neither the parameter nor the verb.
PARAM_TYPES: dict[str, tuple[type, ...]] = {
    "name": (str,),
    "by": (str,),
    "axis": (str,),
    "retries": (int,),
    "times": (int,),
    "seconds": (int, float),
    "columns": (list, tuple, dict),
    "start": (int,),
    "stop": (int,),
    "at": (list, tuple),
    "ascending": (bool,),
    "replace": (bool,),
    "rows": (int, list, dict),
}


#: Where one verb means something different by the same parameter name.
#: ``collapse(by=)`` is a single grouping column — it becomes a column name in
#: the output, so it must be hashable. ``sort(by=)`` is an ordering, which is
#: naturally several columns.
PARAM_TYPES_BY_VERB: dict[str, dict[str, tuple[type, ...]]] = {
    "sort": {"by": (str, list, tuple)},
    "try_except": {"on": (list, tuple, str)},
    "breaker": {"after": (int, type(None))},
    "expect": {"rows": (int,), "min_rows": (int,), "max_rows": (int,),
               "columns": (list, tuple, dict), "more_columns": (bool,)},
}


#: Shape verbs whose literal setting is mandatory — caught at declaration (005
#: A2) instead of raised at run. ``widen`` is absent on purpose: a tuple cell
#: auto-names, so ``columns=`` is optional there.
REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "select": (),                      # columns= or rows= — checked in `check`
    "drop": ("columns",),
    "rename": ("columns",),
    "sort": ("by",),
}


def _required_settings(kind: str) -> tuple[str, ...]:
    """Settings a modifier cannot run without (008 O).

    :data:`REQUIRED_PARAMS` for the shape verbs that default theirs to ``None``,
    plus every keyword the modifier's own function takes with no default —
    ``retry(times=)``, ``timeout(seconds=)`` — so a new modifier is covered
    without a second list.
    """
    names = list(REQUIRED_PARAMS.get(kind, ()))
    entry = MODIFIERS.get(kind)
    if entry is not None and entry.verb is not None:
        try:
            parameters = inspect.signature(entry.verb).parameters.values()
        except (TypeError, ValueError):
            parameters = ()
        names += [p.name for p in parameters
                  if p.name not in ("source", "fn", "_source")
                  and p.kind is inspect.Parameter.KEYWORD_ONLY
                  and p.default is inspect.Parameter.empty
                  and p.name not in names]
    return tuple(names)


#: The shape verbs, derived — never written out a second time.
SHAPE_VERBS: tuple[str, ...] = tuple(
    name for name, kind in MODIFIERS.items() if kind.cls == "shape"
)


def is_shape(kind: str) -> bool:
    """Does this modifier kind change the grid's shape?"""
    return kind in MODIFIERS and MODIFIERS[kind].cls == "shape"


#: kind -> decorator factory, derived from :data:`MODIFIERS`.
DECORATORS: dict[str, Callable] = {n: k.apply for n, k in MODIFIERS.items()}


def _setting_type(verb: str, param: str) -> str | None:
    """A readable type name for a verb's setting, from the PARAM_TYPES tables."""
    types = PARAM_TYPES_BY_VERB.get(verb, {}).get(param) or PARAM_TYPES.get(param)
    takes_tool = param in TOOL_SETTINGS.get(verb, ())
    if types:
        return " | ".join(t.__name__ for t in types) + (" | tool" if takes_tool else "")
    return "tool" if takes_tool else None


def _modifier_settings(name: str, kind: ModifierKind) -> list[dict]:
    """The settings a verb form shows, each with type, required and default."""
    if name == "source":                 # a source holds a literal — no settings
        return []
    settings: list[dict] = []
    takes_extra = False
    try:
        for p in inspect.signature(kind.verb).parameters.values():
            if p.name in ("source", "fn"):
                continue
            if p.kind is inspect.Parameter.VAR_KEYWORD:
                takes_extra = True
                continue
            if p.kind is inspect.Parameter.VAR_POSITIONAL:
                continue
            required = p.default is inspect.Parameter.empty
            settings.append({"name": p.name, "type": _setting_type(name, p.name),
                             "required": required,
                             "default": None if required or p.default is _NO_DEFAULT
                             else p.default})
    except (TypeError, ValueError):
        pass
    if takes_extra:                       # sweep: extra named params are the data
        settings.append({"name": "<swept>", "type": "list", "required": False,
                         "default": None,
                         "description": "any extra named parameter is swept; "
                                        "its value is a list of values"})
    return settings


#: Which verbs apply a tool (008 K13). The column verbs apply none — `check`
#: refuses one; `source`, `expand` and `collapse` fall back to a builtin.
_TAKES_TOOL: dict[str, Any] = {
    "map": True, "filter": True, "group": True, "sweep": True, "table": True,
    "auto": True,
    "select": False, "drop": False, "widen": False, "slice": False,
    "rename": False, "sort": False, "distinct": False,
    "source": "optional", "expand": "optional", "collapse": "optional",
    "retry": None, "timeout": None, "expect": None, "try_except": None,
    "breaker": None,
}


def modifier_catalog() -> dict[str, dict]:
    """Every modifier kind as JSON — class, row rule, and settings per verb.

    Feeds ``GET /modifiers`` (docs/react-api.md): a client builds each verb's
    form from this instead of hard-coding the fields. Unlike :data:`MODIFIERS`
    — which holds the appliers and so cannot be serialized — this is plain data.
    """
    return {
        name: {
            "name": name,
            "class": kind.cls,                                   # shape | execution
            "row_rule": ROWS_RULE.get(name) if kind.cls == "shape" else None,
            "settings": _modifier_settings(name, kind),
            # 008 K13: whether the verb applies a tool — true (needs one),
            # false (refuses one), "optional" (has a default) — and the
            # default it uses. Execution modifiers wrap the step's tool
            # rather than choosing one, so theirs is null.
            "takes_tool": _TAKES_TOOL.get(name),
            "default_tool": (DEFAULT_TOOL.get(name)
                             if _TAKES_TOOL.get(name) not in (True, None) else None),
        }
        for name, kind in MODIFIERS.items()
    }


# ─────────────────────────────────────────────────────────────────────────
# The deferred half: a stack of modifiers, as data
# ─────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, eq=False)
class Modifier:
    """One entry in an Operation's stack: what to apply, and with what.

    ``params`` are **literals only** — how to orchestrate, never what data. A
    reference to another step is not a modifier setting: the data input lives in
    :attr:`Operation.input` and a value reference lives in
    :attr:`Operation.arguments`. ``over=`` is accepted as authoring sugar but is
    hoisted out of the modifier into the input slot, so it never lands here.
    """

    kind: str
    settings: dict = field(default_factory=dict)

    def __call__(self, source: Any, /, **literals) -> "Operation":
        """``mod.select(columns=["n"])(wf["r"])`` — a verb that needs no tool, applied.

        008 K8: the same Operation as ``op("identity")[mod.select(…)](wf["r"])``,
        using the verb's default tool (``identity``, or ``gather`` for
        ``collapse``). Verbs that need a tool of their own refuse.
        """
        default = DEFAULT_TOOL.get(self.kind)
        if default is None or self.kind in ("map", "filter", "group"):
            raise TypeError(
                f"{self.kind!r} needs a tool: write <tool>[mod.{self.kind}(...)](…)")
        return Operation(tool=default, fn=BUILTIN_TOOLS[default])[self](
            source, **literals)

    def __eq__(self, other: Any) -> bool:
        """Equal when they name the same step — however it was named.

        ``mod.map(over=wf["raw"])`` and ``mod.map(over="raw")`` are the same
        modifier, so equality compares the flattened params. Hand-written
        because the dataclass default would call a `StepRef` different from its
        own id and break every round-trip comparison.
        """
        if not isinstance(other, Modifier):
            return NotImplemented
        return (self.kind == other.kind
                and _deref(self.settings) == _deref(other.settings))

    @property
    def cls(self) -> str:
        """``"shape"``, ``"execution"``, or ``"unknown"`` for an unregistered kind."""
        entry = MODIFIERS.get(self.kind)
        return entry.cls if entry else "unknown"

    @property
    def is_shape(self) -> bool:
        return self.cls == "shape"

    def __repr__(self) -> str:
        # Flattened, for the same reason __eq__ is: how a step was named is not
        # part of what this modifier says, so a repr must not depend on it.
        args = ", ".join(f"{k}={v!r}" for k, v in _deref(self.settings).items())
        return f"{self.kind}({args})"


class _Mods:
    """Modifier constructors, for the vertical :func:`stack` form.

    ``mod.map(over=videos)`` just builds a :class:`Modifier`; nothing is
    applied until :func:`stack` assembles them.
    """

    def __getattr__(self, kind: str):
        if kind not in MODIFIERS:
            raise AttributeError(
                f"no modifier {kind!r}. Known: {', '.join(sorted(MODIFIERS))}. "
                "Modifier kinds are declared in MODIFIERS; add one there."
            )

        def make(**params) -> Modifier:
            if kind == "try_except" and params.get("on") is not None:
                # Exception classes are written as classes and saved by name.
                on = params["on"]
                on = [on] if isinstance(on, (str, type)) else list(on)
                params["on"] = [o.__name__ if isinstance(o, type) else o for o in on]
            if kind == "expect" and isinstance(params.get("columns"), dict):
                # Types are written as Python types and saved as their names.
                params["columns"] = {k: _type_label(v)
                                     for k, v in params["columns"].items()}
            if isinstance(params.get("over"), str):
                # 008 K5: in Python a string is data everywhere else
                # (`scale[mod.map()]("readings")`), so it must not be a
                # reference here. JSON keeps string ids: from_dict reads them.
                raise TypeError(
                    f"over= takes a step reference, not a string: pass "
                    f"wf[{params['over']!r}] (grid.wf, or your Workflow)")
            return Modifier(kind, params)
        make.__name__ = kind
        return make


#: ``mod.map(...)``, ``mod.retry(times=2)`` — descriptors for :func:`stack`.
mod = _Mods()


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .system_tools import BUILTIN_TOOLS, DEFAULT_TOOL  # noqa: E402
from .checks import ROWS_RULE  # noqa: E402
from .operation import Operation  # noqa: E402
from .references import TOOL_SETTINGS, _deref  # noqa: E402
from .values import _type_label  # noqa: E402
from .verbs import _Caught, _Stopped, _Tolerated  # noqa: E402
