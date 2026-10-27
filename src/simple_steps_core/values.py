"""Values: literal types, type checks, and saving values and outputs to JSON.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from typing import Any
from typing import Callable
import inspect
import numbers
import pandas as pd
import types
import typing


def _type_name(annotation: Any) -> str | None:
    """A readable name for an annotation — ``None`` when there is not one."""
    if annotation is inspect.Parameter.empty:
        return None
    if isinstance(annotation, str):                  # from __future__ annotations
        return annotation
    return (getattr(annotation, "__name__", None)
            or str(annotation).replace("typing.", ""))


def annotation_problems(fn: Callable) -> list[str]:
    """What is unannotated about *fn*. Empty when it is fully typed.

    ``**kwargs`` counts as untyped (008 C12): its extra keywords have no names,
    so they can't be checked, typed or shown in a form. ``*args`` is refused
    outright by :func:`declaration_problems`.
    """
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):                  # builtins have no signature
        return ["its signature cannot be read"]

    untyped = [p.name for p in signature.parameters.values()
               if p.kind not in (inspect.Parameter.VAR_KEYWORD,
                                 inspect.Parameter.VAR_POSITIONAL)
               and p.annotation is inspect.Parameter.empty]
    problems = []
    open_ = [p.name for p in signature.parameters.values()
             if p.kind is inspect.Parameter.VAR_KEYWORD]
    if open_:
        problems.append(f"**{open_[0]} takes keywords that have no names or types")
    if untyped:
        plural = "s" if len(untyped) > 1 else ""
        problems.append(
            f"parameter{plural} {', '.join(map(repr, untyped))} "
            f"{'have' if plural else 'has'} no type annotation"
        )
    if signature.return_annotation is inspect.Signature.empty:
        problems.append("it has no return annotation")
    return problems


def _open_keywords(fn: Callable) -> str | None:
    """The name of *fn*'s ``**kwargs`` parameter, or None."""
    try:
        parameters = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return None
    return next((p.name for p in parameters
                 if p.kind is inspect.Parameter.VAR_KEYWORD), None)


def declaration_problems(fn: Callable, tool_id: str) -> list[str]:
    """What makes *fn* undrivable as a tool. Empty when it is well formed.

    Every rule here catches something that currently fails **late** — three of
    them with a wrong answer and no error — and none of them rejects a tool
    anyone would write on purpose. See writing-tools.md §2.2.
    """
    problems: list[str] = []
    if not tool_id.isidentifier():
        problems.append(
            f"{tool_id!r} is not a valid identifier, so it cannot be a stable "
            f"id in a palette, a JSON key, or a dropdown label"
            + (" (every lambda would collide on '<lambda>')"
               if tool_id == "<lambda>" else "")
            + ". Pass id= to name it"
        )
    try:
        parameters = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return problems + ["its signature cannot be read, so columns cannot bind"]

    positional_only = [p.name for p in parameters
                       if p.kind is inspect.Parameter.POSITIONAL_ONLY]
    if positional_only:
        problems.append(
            f"parameter{'s' if len(positional_only) > 1 else ''} "
            f"{', '.join(map(repr, positional_only))} "
            f"{'are' if len(positional_only) > 1 else 'is'} positional-only, "
            "and columns bind by name — nothing could ever fill them"
        )
    var_positional = [p.name for p in parameters
                      if p.kind is inspect.Parameter.VAR_POSITIONAL]
    if var_positional:
        problems.append(
            f"*{var_positional[0]} declares no names, so the tool would be "
            "called with no arguments at all and return a plausible wrong "
            "answer. Declare the values it needs, or take **kwargs for the "
            "whole row"
        )
    mutable = [p.name for p in parameters
               if isinstance(p.default, (list, dict, set, bytearray))]
    if mutable:
        problems.append(
            f"parameter{'s' if len(mutable) > 1 else ''} "
            f"{', '.join(map(repr, mutable))} "
            f"{'have' if len(mutable) > 1 else 'has'} a mutable default, which "
            "makes the tool stateful across runs — a step has to be re-runnable"
        )
    return problems


def _value_fits(value: Any, annotation: Any) -> bool | None:
    """Does one literal fit an annotation? ``None`` when it cannot be decided."""
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        # `dict | None` is a types.UnionType — itself a class, so the generic
        # isinstance below used to refuse every value (008 N1). A union fits
        # when any member does.
        answers = [_value_fits(value, a) for a in typing.get_args(annotation)]
        if any(a is True for a in answers):
            return True
        return False if all(a is False for a in answers) else None
    origin = typing.get_origin(annotation) or annotation
    if not isinstance(origin, type) or origin is object:
        return None                                  # Any, unions, protocols…
    if origin is float and isinstance(value, int) and not isinstance(value, bool):
        return True                                  # an int is a fine float
    return isinstance(value, origin)


def _shape_kind(frame: pd.DataFrame) -> str:
    """``cell``, ``column``, ``row`` or ``block`` — what a referenced grid is."""
    n_rows, n_cols = frame.shape
    if (n_rows, n_cols) == (1, 1):
        return "cell"
    if n_cols == 1:
        return "column"
    if n_rows == 1:
        return "row"
    return "block"


def _wants(annotation: Any) -> str | None:
    """Which form a parameter asks for: list, dict, series, frame, scalar, or None (untyped)."""
    if annotation is inspect.Parameter.empty or annotation is Any \
            or isinstance(annotation, str):
        return None
    _, base = _optional_parts(annotation)
    origin = typing.get_origin(base) or base
    if origin in (list, tuple, set):
        return "list"
    if origin is dict:
        return "dict"
    if origin is pd.Series:
        return "series"
    if origin is pd.DataFrame:
        return "frame"
    if isinstance(origin, type):
        return "scalar"
    return None


#: 008 C1/C7's conversion table: (shape, wanted form) → allowed.
_CONVERTS = {
    ("cell", "scalar"), ("cell", "list"),
    ("column", "list"), ("column", "series"), ("column", "frame"),
    ("row", "list"), ("row", "series"), ("row", "dict"), ("row", "frame"),
    ("block", "frame"), ("cell", "frame"),
}


def _shape_problem(kind: str, annotation: Any, name: str, step_id: str) -> str | None:
    """Why a *kind* of grid can't be passed as *annotation*, or None when it can."""
    wanted = _wants(annotation)
    if wanted is None or (kind, wanted) in _CONVERTS:
        return None
    if kind == "column" and wanted == "scalar":
        why = "a column; to pair its rows with the input's, join first"
    else:
        why = f"a {kind}"
    return (f"{name}: {_type_name(annotation)}, but {step_id!r} is {why} "
            f"— an argument is passed whole, not one value per row")


def _ref_value(frame: pd.DataFrame, annotation: Any, step_id: str) -> Any:
    """What a ``$ref`` argument or setting receives, by the parameter's type (008 C1).

    A cell gives its value; a column a list (or Series); a row a dict (or
    list/Series); anything else the DataFrame. Untyped, the natural form.
    """
    kind = _shape_kind(frame)
    problem = _shape_problem(kind, annotation, "argument", step_id)
    if problem:
        raise TypeError(problem)
    wanted = _wants(annotation)
    clean = lambda values: [None if _is_missing(v) else v for v in values]  # noqa: E731
    if wanted == "frame":
        return frame
    if kind == "cell" and wanted != "list":
        value = frame.iloc[0, 0]
        return None if _is_missing(value) else value
    if kind == "cell":
        return clean([frame.iloc[0, 0]])
    if kind == "column":
        return frame.iloc[:, 0] if wanted == "series" else clean(frame.iloc[:, 0])
    if kind == "row":
        row = frame.iloc[0]
        if wanted == "series":
            return row
        if wanted == "list":
            return clean(row)
        return {k: (None if _is_missing(v) else v) for k, v in row.items()}
    return frame


#: Type names a plan or `mod.expect` may use, and the types they mean.
_TYPE_NAMES: dict[str, Any] = {"str": str, "int": int, "float": float,
                               "bool": bool, "list": list, "dict": dict,
                               "tuple": tuple, "any": Any}


def _type_label(t: Any) -> str:
    """A type as the short name a plan shows: ``int``, ``float | None``, ``any``."""
    if t is None or t is Any or t is inspect.Parameter.empty:
        return "any"
    if isinstance(t, str):
        return t
    admits_none, base = _optional_parts(t)
    name = _type_name(base) or "any"
    return f"{name} | None" if admits_none and base is not t else name


def _dtype_type(series: pd.Series) -> Any:
    """The Python type a column of real data holds, or None when mixed/unknown."""
    kind = getattr(series.dtype, "kind", None)
    if kind == "b":
        return bool
    if kind in "iu":
        return int
    if kind == "f":
        return float
    present = series.dropna() if kind == "O" else series
    types_ = {type(v) for v in present}
    return types_.pop() if len(types_) == 1 else None


def _return_hint(fn: Any) -> Any:
    """A tool's resolved return annotation, or None."""
    if fn is None:
        return None
    try:
        return typing.get_type_hints(fn, include_extras=True).get("return")
    except Exception:
        try:
            ann = _signature(fn).return_annotation
        except (TypeError, ValueError):
            return None
        return None if ann is inspect.Parameter.empty else ann


def _record_fields(cls: Any) -> dict | None:
    """Field name → type for a TypedDict, dataclass or NamedTuple, else None."""
    import dataclasses
    if isinstance(cls, type) and issubclass(cls, tuple) and hasattr(cls, "_fields"):
        hints = getattr(cls, "__annotations__", {})
        return {f: hints.get(f) for f in cls._fields}
    if isinstance(cls, type) and (dataclasses.is_dataclass(cls)
                                  or (issubclass(cls, dict) and hasattr(cls, "__annotations__"))):
        try:
            return dict(typing.get_type_hints(cls))
        except Exception:
            return dict(getattr(cls, "__annotations__", {}))
    return None


def named_columns(rule: dict | None, columns: list[str], step: str | None,
                  tool: str | None) -> list[str]:
    """The names *columns* (what a step writes, before naming) get under the
    last ``mod.name`` (G12, outputs-and-reshaping.md §4): a list names a
    sequence's positions, a mapping renames fields, a pattern renames each
    (``{field}``, ``{step}``, ``{tool}``), after a list or mapping."""
    if not rule:
        return list(columns)
    to, pattern = rule.get("to"), rule.get("pattern")
    out = list(columns)
    if isinstance(to, str):
        out = [to] if len(out) <= 1 else out
    elif isinstance(to, list):
        out = list(to)
    elif isinstance(to, dict):
        out = [to.get(c, c) for c in out]
    if pattern:
        out = [pattern.format(field=c, step=step or "", tool=tool or "") for c in out]
    return out


def record_return(kind: str | None, fn: Any) -> tuple[Any, bool] | None:
    """The record type a tool declares it returns per call, and whether it may
    be None: ``-> LoHi``, ``-> LoHi | None``, and under ``expand``
    ``-> list[LoHi]`` (G8, outputs-and-reshaping.md §3). None otherwise."""
    hint = _return_hint(fn)
    if hint is None or kind in (None, "filter", "source", "widen", "table", "group"):
        return None
    if typing.get_origin(hint) is typing.Annotated:
        hint = typing.get_args(hint)[0]
    if kind == "expand":
        args = typing.get_args(hint)
        if typing.get_origin(hint) not in (list, tuple, set, frozenset) or not args:
            return None
        hint = args[0]
    optional = False
    args = typing.get_args(hint)
    if type(None) in args and len(args) == 2:
        hint, optional = next(a for a in args if a is not type(None)), True
    return (hint, optional) if _record_fields(hint) else None


def _declared_schema(fn: Any) -> dict | None:
    """The columns a tool-backed source declares (008 C5), or None.

    ``-> Annotated[pd.DataFrame, Readings]``, where ``Readings`` is a TypedDict
    or dataclass, names every column and its type.
    """
    hint = _return_hint(fn)
    if typing.get_origin(hint) is typing.Annotated:
        base, *extras = typing.get_args(hint)
        if base is pd.DataFrame:
            for extra in extras:
                fields = _record_fields(extra)
                if fields is not None:
                    return fields
    return None


def _payload_type(kind: str | None, fn: Any) -> Any:
    """The type a verb's payload column will hold, from the tool's return."""
    hint = _return_hint(fn)
    if hint is None or kind in (None, "filter", "source", "widen"):
        return None
    if typing.get_origin(hint) is typing.Annotated:
        hint = typing.get_args(hint)[0]
    if kind == "expand":
        args = typing.get_args(hint)
        if typing.get_origin(hint) in (list, set, frozenset) and args:
            return args[0]
        if typing.get_origin(hint) is tuple and args:
            return args[0] if len(set(args) - {Ellipsis}) == 1 else None
        return None
    return hint


def _plain(value: Any) -> Any:
    """A cell value as plain Python: numpy scalars unwrapped, missing as None."""
    if _is_missing(value) if not isinstance(value, (list, dict, tuple, set)) else False:
        return None
    if hasattr(value, "item") and hasattr(value, "dtype"):
        return value.item()
    return value


def _optional_parts(annotation: Any) -> tuple[bool, Any]:
    """(does it admit None?, the annotation without None) — ``int | None`` → (True, int)."""
    if annotation is Any or isinstance(annotation, str):
        return True, annotation
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        members = [a for a in typing.get_args(annotation) if a is not type(None)]
        admits = len(members) < len(typing.get_args(annotation))
        if len(members) == 1:
            return admits, members[0]
        return admits, typing.Union[tuple(members)] if members else annotation
    return annotation is type(None), annotation


def _column_fits(series: pd.Series, annotation: Any) -> bool | None:
    """Does a column's dtype fit an annotation? ``None`` when undecidable.

    Deliberately asymmetric: it returns ``False`` only when the mismatch is
    certain, because a false positive here would refuse a step that works. A
    numeric dtype answers exactly; an object column is decided by its first
    non-null value, which is the most an unparameterized ``object`` dtype can
    tell us.
    """
    origin = typing.get_origin(annotation) or annotation
    if not isinstance(origin, type) or origin is object:
        return None
    if len(series) == 0:
        return None                   # no values: nothing says what it holds
    kind = getattr(series.dtype, "kind", None)
    if kind is None:
        return None
    if origin is bool:
        return kind == "b"
    if origin is int:
        return kind in "iu"
    if origin is float:
        return kind in "iufc"                        # an int column fits a float
    if kind != "O":                                  # a real dtype, a non-numeric annotation
        return False if origin in (str, list, tuple, dict, set) else None
    present = series.dropna()
    if present.empty:
        return None
    return isinstance(present.iloc[0], origin)


#: Version of the saved format. Every version back to 1 still loads (008 K17);
#: a file from a newer core is refused with a message, never half-read.
#:
#: - 2: tagged literals (C11), references in settings (C1), tools in settings
#:   (C2), selections (C7).
#: - 3 (009): implicit steps save ``mod.auto()``; the ``breaker`` modifier;
#:   session outputs save ``data``, ``states`` and ``notes`` (no ledger), with
#:   data-hash ``version`` and ``read`` stamps in their meta.
FORMAT_VERSION = 5


#: The tags a saved value can carry. A literal dict that happens to use one of
#: these keys (or any `$` key, or a non-string key) is saved as `$dict`, so a
#: literal can never be read back as a reference.
_TAGS = ("$ref", "$res", "$tool", "$tuple", "$set", "$dict")


def _literal_problem(value: Any) -> str | None:
    """Why *value* is not a literal (008 C11), or None when it is one.

    A literal is what Python's literal syntax writes: ``int``, ``float``,
    ``str``, ``bool``, ``None``, and ``list``/``tuple``/``dict``/``set`` of
    those — ``ast.literal_eval`` minus ``bytes`` and ``complex``. Anything else
    is refused when the step is declared, not when it is saved.
    """
    if value is None or isinstance(value, (bool, str)):
        return None
    if isinstance(value, numbers.Real):          # int, float, numpy numbers; not complex
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            problem = _literal_problem(item)
            if problem:
                return problem
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            problem = _literal_problem(key) or _literal_problem(item)
            if problem:
                return problem
        return None
    kind = type(value).__name__
    if hasattr(value, "isoformat"):
        hint = f"pass a str ({value.isoformat()!r})"
    elif kind == "Decimal":
        hint = f"pass a float or a str ({str(value)!r})"
    elif isinstance(value, (bytes, bytearray)):
        hint = "pass a str"
    elif callable(value):
        hint = "a function belongs in a setting that takes a tool, as a registered @tool"
    else:
        hint = "pass a str, number, bool, None, list, tuple, dict or set"
    article = "an" if kind[:1].lower() in "aeiou" else "a"
    return f"{article} {kind} isn't a literal; {hint}, or make it a step"


def _bind_positional(operation: "Operation", source: Any, values: tuple,
                     given: dict) -> dict:
    """Name the positional arguments after the input (008 C1).

    ``scale(wf["r"], wf["w"])`` is ``scale(wf["r"], weight=wf["w"])``. Each value
    takes the tool's next parameter that is still free: not given by keyword,
    and not supplied by the input — a known input column, or, when the input's
    columns are not known, the first parameter (the row's own value). A
    ``res[…]`` takes the first free parameter its declared type fits.
    """
    fn = operation.fn or BUILTIN_TOOLS.get(operation.tool)
    if fn is None:
        raise TypeError(f"{operation.tool}: pass these arguments by keyword "
                        "— its parameters are not known here")
    parameters = [p for p in _signature(fn).parameters.values()
                  if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                inspect.Parameter.KEYWORD_ONLY)]
    free = [p for p in parameters
            if p.name not in given and p.name not in operation.arguments]
    workflow = getattr(source, "workflow", None)
    step = workflow.steps.get(source.id) if workflow is not None and isinstance(source, StepRef) else None
    if step is not None:
        columns = set(predicted_columns(step.output))
        free_for_values = [p for p in free if p.name not in columns]
        if columns_unknown(step.output) and free_for_values == free and free:
            free_for_values = free[1:]
    else:
        free_for_values = free[1:]
    bound: dict = {}
    for value in values:
        if isinstance(value, ResRef):
            decl = workflow.resources.get(value.name) if workflow is not None else None
            fits = [p for p in free if decl is not None and decl.type is not None
                    and _type_fits(decl.type, p.annotation)]
            target = fits[0] if fits else None
            if target is None:
                raise TypeError(
                    f"{operation.tool}: no free parameter fits res[{value.name!r}]"
                    + ("" if decl else " (declare it first with wf.define)")
                    + "; pass it by keyword")
        else:
            target = next((p for p in free_for_values if p in free), None)
            if target is None:
                names = ", ".join(p.name for p in parameters) or "(none)"
                raise TypeError(
                    f"{operation.tool}() has no free parameter left for "
                    f"{value!r}; it takes {names}. Pass it by keyword.")
        bound[target.name] = value
        free.remove(target)
    return bound


def _encode_argument(value: Any) -> Any:
    """A bound value as JSON, exactly: a reference, a tool, or a tagged literal.

    ``{"$ref": step}``, ``{"$res": name}``, ``{"$tool": id}``; a literal saves
    as itself where plain JSON keeps its type, and tagged where it would not
    (008 C11): ``{"$tuple": [...]}``, ``{"$set": [...]}``, and ``{"$dict":
    [[k, v], ...]}`` for a dict with non-string (or ``$``) keys.
    """
    if isinstance(value, StepRef):
        return _encode_ref(value)
    if isinstance(value, ResRef):
        return {"$res": value.name}
    if isinstance(value, ToolRef):
        return {"$tool": value.id}
    if isinstance(value, Tool):
        return {"$tool": value.id}
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    if isinstance(value, tuple):
        return {"$tuple": [_encode_argument(v) for v in value]}
    if isinstance(value, (set, frozenset)):
        items = list(value)
        try:
            items = sorted(items)
        except TypeError:
            pass
        return {"$set": [_encode_argument(v) for v in items]}
    if isinstance(value, list):
        return [_encode_argument(v) for v in value]
    if isinstance(value, dict):
        if all(isinstance(k, str) and not k.startswith("$") for k in value):
            return {k: _encode_argument(v) for k, v in value.items()}
        return {"$dict": [[_encode_argument(k), _encode_argument(v)]
                          for k, v in value.items()]}
    if callable(value):
        raise PayloadError(
            f"cannot save {getattr(value, '__name__', value)!r}: a function "
            "is saved by its tool id, so register it with @tool (a lambda "
            "can't be saved)")
    raise PayloadError(f"cannot save a {type(value).__name__}: "
                       f"{_literal_problem(value)}")


def _decode_argument(value: Any) -> Any:
    """The inverse of :func:`_encode_argument` — the same value and type back."""
    if isinstance(value, list):
        return [_decode_argument(v) for v in value]
    if not isinstance(value, dict):
        return value
    if _is_ref(value):
        return _decode_ref(value)
    if set(value) == {"$res"}:
        return ResRef(value["$res"])
    if set(value) == {"$tool"}:
        return ToolRef(value["$tool"])
    if set(value) == {"$tuple"}:
        return tuple(_decode_argument(v) for v in value["$tuple"])
    if set(value) == {"$set"}:
        return {_decode_argument(v) for v in value["$set"]}
    if set(value) == {"$dict"}:
        return {_freeze(_decode_argument(k)): _decode_argument(v)
                for k, v in value["$dict"]}
    return {k: _decode_argument(v) for k, v in value.items()}


def _freeze(key: Any) -> Any:
    """A decoded dict key must be hashable: a list key can only have been a tuple."""
    return tuple(key) if isinstance(key, list) else key


_LITERAL_TYPES = (str, int, float, bool, type(None), list, dict, tuple)


def _literal_annotation(annotation: Any) -> bool:
    """Can a setting with this annotation hold only literals?"""
    if annotation is inspect.Parameter.empty or annotation is Any \
            or isinstance(annotation, str):
        return True                       # undeclared or unresolvable: allowed
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return all(_literal_annotation(a) for a in typing.get_args(annotation))
    if origin is typing.Literal:
        return True
    base = origin or annotation
    return isinstance(base, type) and issubclass(base, _LITERAL_TYPES)


#: Distinguishes "absent" from a legitimately stored ``None``.
_MISSING = object()


_JSON_SCALARS = (type(None), bool, int, float, str)


def _json_safe(value: Any) -> bool:
    """Can this survive a JSON round-trip as itself?

    Worth checking rather than trusting: ``DataFrame.to_json`` does **not**
    fail on an object column, it writes ``{}`` and reads back an empty dict.
    Silent loss is worse than a refusal, so object columns are vetted per
    value before the frame is handed to pandas.
    """
    if isinstance(value, _JSON_SCALARS):
        return True
    if hasattr(value, "item") and hasattr(value, "dtype"):    # numpy scalar
        return _json_safe(value.item())
    if isinstance(value, (list, tuple)):
        return all(_json_safe(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _json_safe(v) for k, v in value.items())
    return False


def _encode(value: Any) -> dict:
    """One payload as JSON-safe data."""
    if isinstance(value, pd.DataFrame):
        for column in value.columns:
            if value[column].dtype != object:
                continue
            bad = next((v for v in value[column] if not _json_safe(v)), _MISSING)
            if bad is not _MISSING:
                raise PayloadError(
                    f"cannot export column {column!r}: it holds a "
                    f"{type(bad).__name__}, which to_json would silently write "
                    "as {} and read back as an empty dict. Object payloads "
                    "persist only as handles or as something with a to_json "
                    "(§8.8); the light export (to_json) carries no payloads."
                )
        # Dtypes travel beside the data: JSON has no type information, so
        # `read_json` re-infers, and a float column of whole numbers comes back
        # int64. That used to be cosmetic; now that annotations are checked
        # against real dtypes, a round trip could change a step's verdict.
        # Stored positionally — a column name need not be a string.
        return {"kind": "frame",
                "data": value.to_json(orient="split"),
                "dtypes": [str(dtype) for dtype in value.dtypes],
                # `orient="split"` writes the index as a plain list, so a
                # RangeIndex comes back as an Index of the same values. The
                # values align either way; recording it keeps a round trip
                # byte-identical rather than merely equivalent.
                "range_index": isinstance(value.index, pd.RangeIndex)}
    if value is None or isinstance(value, (bool, int, float, str)):
        return {"kind": "scalar", "data": value}
    if isinstance(value, (list, tuple)):
        return {"kind": "list", "data": [_encode(v) for v in value]}
    raise PayloadError(
        f"cannot export a {type(value).__name__} payload. Object payloads "
        "persist only as handles or as something with a to_json (§8.8); the "
        "light export (to_json) carries no payloads at all."
    )


def _decode(blob: dict) -> Any:
    kind = blob["kind"]
    if kind == "frame":
        import io
        # convert_axes=False: a row id like "1.0" (008 C16) must come back
        # as the string it was, not the float 1.0.
        frame = pd.read_json(io.StringIO(blob["data"]), orient="split",
                             convert_axes=False)
        # Restore what JSON could not carry. Absent on exports written before
        # dtypes were recorded, which then behave as they always did.
        dtypes = blob.get("dtypes")
        if dtypes and len(dtypes) == len(frame.columns):
            for column, dtype in zip(frame.columns, dtypes):
                if str(frame[column].dtype) == dtype:
                    continue
                try:
                    frame[column] = frame[column].astype(dtype)
                except (TypeError, ValueError):
                    pass          # an object column that cannot be re-cast
        if blob.get("range_index") and list(frame.index) == list(range(len(frame))):
            frame.index = pd.RangeIndex(len(frame))
        return frame
    if kind == "list":
        return [_decode(v) for v in blob["data"]]
    return blob["data"]


def _encode_output(output: Output) -> dict:
    meta = {k: v for k, v in output.meta.items()
            if k not in ("problems", "notes", "column_types")}
    blob = {"data": _encode(output.data),
            "states": {str(c): [str(v) for v in output.states[c]] for c in output.states.columns},
            "meta": meta}
    if output.notes:
        blob["notes"] = [[_plain(i), note] for i, note in output.notes.items()]
    return blob


def _decode_output(blob: dict) -> Output:
    data = _decode(blob["data"])
    meta = dict(blob["meta"])
    if blob.get("notes"):
        meta["notes"] = {i: note for i, note in blob["notes"]}
    if "states" in blob:
        states = pd.DataFrame({c: _state_column(v, data.index)
                               for c, v in blob["states"].items()}, index=data.index)
        return Output(data, states, meta)
    # An older session saved a per-row ledger: read its records once.
    ledger = _decode(blob["ledger"])
    return Output(data, meta=meta, records=ledger.to_dict("records"), index=ledger.index)


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .system_tools import BUILTIN_TOOLS  # noqa: E402
from .catalog import (  # noqa: E402
    Tool,
    _signature,
    _type_fits,
)
from .checks import columns_unknown, predicted_columns  # noqa: E402
from .errors import PayloadError  # noqa: E402
from .operation import Operation  # noqa: E402
from .output import Output, _is_missing, _state_column  # noqa: E402
from .references import (  # noqa: E402
    ResRef,
    StepRef,
    ToolRef,
    _decode_ref,
    _encode_ref,
    _is_ref,
)
