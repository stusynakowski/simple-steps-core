"""Formula text, read: ``formula(text)`` gives what the text writes (EX13).

A step's formula is printed as a line of Python (``to_f[mod.map()](wf["p"])``);
``formula`` reads such a line back. It never runs the text: it parses it into a
syntax tree and builds each node with core's own constructors (``mod``,
``wf``, ``res``, ``cols``, ``row``, ``rows``, ``join``, ``stack``, ``zip_``,
``op``), so a formula means exactly what the same line means in Python, and
``formula(step.formula)`` is the step again. Anything else is refused, naming
what isn't allowed: no other names, attributes, calls, comprehensions,
lambdas or operators.

A bare name is a tool, ``op(name)``, found in the kernel's catalog when the
step is assigned. A string assigned to a step stays a string value
(decisions.md EX13); text is read only through ``formula``.

Ported in spirit from the app's ``operation_formula.py``: the same rule (a
syntax tree, a short list of shapes, never ``eval``), on today's grammar.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

from .combines import join, stack, zip_
from .modifiers import MODIFIERS, Modifier, _Mods, mod
from .operation import Operation, op
from .references import TOOL_SETTINGS, BoundTool, resource_alone, ResRef, StepRef, ToolRef, cols, res, row, rows, wf


class FormulaError(ValueError):
    """Formula text core won't read, and why."""


#: The names a formula may use, and what each means.
NAMES: dict[str, Any] = {"wf": wf, "res": res, "mod": mod, "cols": cols, "row": row,
                         "rows": rows, "join": join, "stack": stack, "zip_": zip_, "op": op}

#: What a condition may compare with, and combine by.
COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
           ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
COMBINE = {ast.BitAnd: operator.and_, ast.BitOr: operator.or_}

#: The only attributes read: a condition operand's own (`.isin`, `.idx`).
OPERAND_ATTRIBUTES = frozenset({"isin", "idx"})


def formula(text: str) -> Any:
    """What *text* writes: an operation, a pick, or a literal value."""
    if not isinstance(text, str):
        raise FormulaError(f"a formula is text, not {type(text).__name__}")
    body = text.strip().removeprefix("=").strip()
    try:
        tree = ast.parse(body, mode="eval").body
    except SyntaxError as exc:
        raise FormulaError(_not_an_expression(body) or f"not a formula: {exc.msg}") from None
    if isinstance(tree, ast.BinOp) and type(tree.op) not in COMBINE:
        raise FormulaError(f"{_text(tree)}: {EXPECTED}")              # 012 #10
    built = _build(tree)
    if isinstance(built, ResRef):
        raise FormulaError(resource_alone(built.name))
    return built


#: What a formula is, for a refusal that can't say what was meant (012 #10).
EXPECTED = ('expected tool[mod.verb(…)](wf["…"], …): a tool, its modifiers in brackets, '
            "and a call with the step it reads")

#: Computed values: a call by a bare name or of a tool, or arithmetic.
LITERAL_HINT = 'an argument is a literal (text, a number, a list, …) or wf["…"]'


def _text(node: ast.AST) -> str:
    """*node* as written, its strings in double quotes as core prints them."""
    text = ast.unparse(node)
    return text.replace("'", '"') if '"' not in text else text


def _not_an_expression(body: str) -> str | None:
    """012 #1: an assignment in the text says what to write instead."""
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return None
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
        return None
    target, value = tree.body[0].targets[0], tree.body[0].value
    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) \
            and target.value.id == "res":
        name = _text(target.slice)
        made = (_text(value.func) if isinstance(value, ast.Call) else "Type")
        return (f"a step can use a resource but not create one; declare it in the "
                f"workflow: k.define({name}, {made}, …)")
    return f"a formula is what goes after the =: write {_text(value)}, and assign it to the step"


def _computed(node: ast.AST) -> bool:
    """A value the text computes, which a formula never does: ``str(1)``,
    ``dbl[mod.map()](…)``, ``1 + x``. Conditions (``&``, ``|``, ``.isin``) aren't."""
    if isinstance(node, ast.BinOp):
        return type(node.op) not in COMBINE
    if isinstance(node, ast.Call):
        return isinstance(node.func, (ast.Name, ast.Subscript)) and not (
            isinstance(node.func, ast.Name) and node.func.id in NAMES)
    return False


def _build(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        items = [_build(e) for e in node.elts]
        return {ast.List: list, ast.Tuple: tuple, ast.Set: set}[type(node)](items)
    if isinstance(node, ast.Dict):
        if any(k is None for k in node.keys):
            raise FormulaError("a dict in a formula can't unpack another (**)")
        return {_build(k): _build(v) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.UnaryOp):
        value = _build(node.operand)
        if isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(value, (int, float)) \
                and not isinstance(value, bool):
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node.op, ast.Invert) and not isinstance(value, (int, float, str)):
            return ~value                                    # not a condition: ~c
        raise FormulaError(f"{ast.unparse(node)}: only a number takes a sign, "
                           "and only a condition takes ~")
    if isinstance(node, ast.BinOp) and type(node.op) in COMBINE:
        left, right = _build(node.left), _build(node.right)
        if isinstance(left, (int, float, str)) or isinstance(right, (int, float, str)):
            raise FormulaError(f"{ast.unparse(node)}: & and | combine conditions")
        return COMBINE[type(node.op)](left, right)
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or type(node.ops[0]) not in COMPARE:
            raise FormulaError(f"{ast.unparse(node)}: a condition compares once, "
                               "with ==, !=, <, <=, > or >=")
        left = _build(node.left)
        if isinstance(left, (int, float, str, bool, type(None))):
            raise FormulaError(f"{ast.unparse(node)}: a condition starts with "
                               "cols[…] or row[…]")
        return COMPARE[type(node.ops[0])](left, _build(node.comparators[0]))
    if isinstance(node, ast.Name):
        if node.id.startswith("_"):
            raise FormulaError(f"{node.id}: a name in a formula can't start with _")
        return NAMES[node.id] if node.id in NAMES else op(node.id)   # else a tool
    if isinstance(node, ast.Attribute):
        return _attribute(node)
    if isinstance(node, ast.Subscript):
        value = _build(node.value)
        _refuse_subscript(node, value)
        if not _subscriptable(value):
            raise FormulaError(f"{ast.unparse(node.value)} can't take […] in a formula")
        try:
            return value[_key(node.slice)]
        except KeyError as exc:                              # wf[…], res[…]: said plainly
            raise FormulaError(str(exc.args[0]) if exc.args else str(exc)) from None
    if isinstance(node, ast.Call):
        return _call(node)
    if isinstance(node, ast.BinOp):
        raise FormulaError(f"{_text(node)}: a formula doesn't compute; arithmetic goes "
                           "in a tool, as its own step")
    raise FormulaError(f"{ast.unparse(node)}: a {type(node).__name__.lower()} isn't "
                       "allowed in a formula")


def _refuse_subscript(node: ast.Subscript, value: Any) -> None:
    """012 #3, #4, #49–#51: brackets on the wrong thing say what goes there."""
    key = node.slice
    if value is wf or value is res:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return
        what, example = (("a step", "readings") if value is wf else ("a resource", "db"))
        if isinstance(key, ast.Name) and key.id not in NAMES:
            example = key.id
            sep = ":"
        else:
            sep = ","
        raise FormulaError(f'{"wf" if value is wf else "res"}[…] takes {what} name in quotes'
                           f'{sep} {"wf" if value is wf else "res"}["{example}"]')
    if isinstance(value, ResRef):
        raise FormulaError(f'{_text(node.value)} is not a tool name; a resource\'s tool is '
                           f'{_text(node.value)}.<tool>[mod.map()](wf["…"])')
    parts = key.elts if isinstance(key, ast.Tuple) else [key]
    if isinstance(value, StepRef) and any(
            isinstance(p, ast.Call) and isinstance(p.func, ast.Attribute)
            and isinstance(p.func.value, ast.Name) and p.func.value.id == "mod" for p in parts):
        raise FormulaError(f"{_text(node.value)} is not a tool name; a tool goes before the "
                           f"brackets: tool[{_text(key)}]({_text(node.value)})")


def _attribute(node: ast.Attribute) -> Any:
    name = node.attr
    if name.startswith("_"):
        raise FormulaError(f".{name}: an attribute in a formula can't start with _")
    value = _build(node.value)
    if isinstance(value, _Mods):
        try:
            return getattr(value, name)                      # mod.map, …
        except AttributeError as exc:
            raise FormulaError(str(exc)) from None
    if isinstance(value, ResRef):
        return getattr(value, name)                          # res["db"].lookup: its tool
    if name in OPERAND_ATTRIBUTES and type(value).__module__.endswith(".references"):
        return getattr(value, name)                          # cols["x"].isin, row["s"].idx
    if isinstance(node.value, ast.Name) and node.value.id not in NAMES:
        raise FormulaError(f"{ast.unparse(node)} is not a tool. A formula reads only "
                           "mod.<modifier>, res[…].<tool>, .isin and .idx")      # 012 #5
    raise FormulaError(f"{ast.unparse(node)}: a formula reads only mod.<modifier>, "
                       "res[…].<tool>, .isin and .idx")


def _subscriptable(value: Any) -> bool:
    return value is wf or value is res or value is cols or value is row or value is rows \
        or isinstance(value, (StepRef, Operation, BoundTool))


def _key(node: ast.AST) -> Any:
    if isinstance(node, ast.Slice):
        return slice(*(None if part is None else _build(part)
                       for part in (node.lower, node.upper, node.step)))
    if isinstance(node, ast.Tuple):
        return tuple(_key(e) for e in node.elts)             # tool[mod.a(), mod.b()]
    return _build(node)


def _call(node: ast.Call) -> Any:
    if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
        raise FormulaError(f"{ast.unparse(node)}: a formula can't unpack arguments (* or **)")
    if isinstance(node.func, ast.Name) and node.func.id in MODIFIERS \
            and node.func.id not in NAMES:
        raise FormulaError(f"{node.func.id}() isn't a modifier; write mod.{node.func.id}(…), "
                           "mod.select(…), mod.retry(…), …")                    # 012 #23
    fn = _build(node.func)
    if not _callable(fn):
        raise FormulaError(f"{ast.unparse(node.func)} can't be called in a formula")
    _refuse_bare_names(node, fn)
    _refuse_computed(node, fn)
    kind = _modifier_kind(fn)
    if fn in (join, stack, zip_):
        _refuse_combine_inputs(node, fn)
    args = [_build(a) for a in node.args]
    kwargs = {k.arg: (_tool_names(k.value) if k.arg in TOOL_SETTINGS.get(kind, ()) else _build(k.value))
              for k in node.keywords}
    if isinstance(fn, (Operation, BoundTool)) and args:
        # Called on a value, a tool runs at once; a formula never runs anything.
        # After the input, values go by position as in Python (008 C1, 012 C40).
        first = args[0]
        if isinstance(first, str):
            raise FormulaError(f"{_text(node)}: the input must be a step reference; "
                               f"{_text(node.args[0])} is a string. Did you mean wf[{_text(node.args[0])}]?")
        if any(isinstance(a, Operation) for a in args):
            raise FormulaError(f"{_text(node)}: an operation can't be an input; make it its "
                               f"own step and pass wf[\"…\"]")                # 012 #27
        if not isinstance(first, StepRef):
            raise FormulaError(f"{_text(node)}: the input must be a step reference, "
                               f"wf[\"…\"], not {_text(node.args[0])}")        # 012 #30
    try:
        return fn(*args, **kwargs)
    except FormulaError:
        raise
    except (TypeError, ValueError) as exc:                   # core's own refusal, said
        raise FormulaError(f"{_text(node)}: {exc}") from None


def _refuse_computed(node: ast.Call, fn: Any) -> None:
    """012 #22, #31, #33, #41: a setting or argument the text would compute."""
    for k in node.keywords:
        if not _computed(k.value):
            continue
        if isinstance(fn, (Operation, BoundTool)):
            raise FormulaError(f"{k.arg}={_text(k.value)}: {LITERAL_HINT}; to compute it, "
                               f"make it its own step and pass wf[\"…\"]")
        kind = _modifier_kind(fn)
        where = f"mod.{kind}" if kind else _text(node.func)
        raise FormulaError(f"{where}({k.arg}=…) must be a literal, not {_text(k.value)}")


def _refuse_combine_inputs(node: ast.Call, fn: Any) -> None:
    """012 #16, #18: a combine reads steps, by position; its settings go by keyword."""
    name = _text(node.func)
    least = 1 if fn is stack else 2
    if len(node.args) < least:
        steps = 'wf["a"], …' if fn is stack else 'wf["a"], wf["b"], …'
        raise FormulaError(f"{name} reads steps: {name}({steps})")
    for a in node.args:
        if isinstance(a, ast.Constant):
            hint = ' Settings go by keyword, e.g. on="city"' if fn is join else " Settings go by keyword"
            raise FormulaError(f"{name} combines steps; each positional argument is "
                               f"wf[\"…\"], not {a.value!r}.{hint}")


def _modifier_kind(fn: Any) -> str | None:
    """``"sort"`` for ``mod.sort``; None for anything else."""
    if getattr(fn, "__qualname__", "").startswith("_Mods"):
        return fn.__name__
    return None


def _bare(node: ast.AST) -> list[ast.Name]:
    """The bare names standing as values in *node*: the node itself, or the
    items of a list, tuple, set or dict. Not inside a call or a subscript."""
    if isinstance(node, ast.Name):
        return [] if node.id in NAMES else [node]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [n for e in node.elts for n in _bare(e)]
    if isinstance(node, ast.Dict):
        return [n for e in (*node.keys, *node.values) if e is not None for n in _bare(e)]
    return []


def _refuse_bare_names(node: ast.Call, fn: Any) -> None:
    """A bare name is a tool only where a tool goes (012 C41): in the tool slot,
    and in a setting that takes one (TOOL_SETTINGS). Elsewhere it is text
    without its quotes, or a step without wf[…], and is refused, saying so."""
    kind = _modifier_kind(fn)
    for k in node.keywords:
        if kind is not None and k.arg in TOOL_SETTINGS.get(kind, ()) and isinstance(k.value, ast.Name):
            continue                                         # mod.sort(by=first_letter): a tool
        names = _bare(k.value)
        if not names:
            continue
        name = names[0].id
        if isinstance(fn, (Operation, BoundTool)):
            raise FormulaError(f"{k.arg}={ast.unparse(k.value)}: {name} is not defined. "
                               f"A step is wf[\"{name}\"]; text is \"{name}\"")
        where = f"mod.{kind}" if kind else ast.unparse(node.func)
        raise FormulaError(f"{where}({k.arg}={ast.unparse(k.value)}): text needs quotes, \"{name}\"")
    if isinstance(fn, (Operation, BoundTool)):
        for a in node.args:
            if isinstance(a, ast.Name) and a.id not in NAMES:
                raise FormulaError(f"{ast.unparse(node)}: {a.id} is not defined. "
                                   f"To use the step \"{a.id}\", write wf[\"{a.id}\"]")


def _tool_names(node: ast.AST) -> Any:
    """A setting that takes a tool: a bare name on its own is that tool, ``{"$tool": name}``
    as Python saves a @tool there (008 C2); anything else is built as usual."""
    if isinstance(node, ast.Name) and node.id not in NAMES and not node.id.startswith("_"):
        return ToolRef(node.id)
    return _build(node)


def _callable(fn: Any) -> bool:
    if fn in (join, stack, zip_, op):
        return True
    if isinstance(fn, (Modifier, Operation, BoundTool)):
        return True                                          # mod.sort(…)(wf[…]), tool[…](…)
    if getattr(fn, "__name__", None) and getattr(fn, "__qualname__", "").startswith("_Mods"):
        return True                                          # mod.map, before its settings
    if getattr(fn, "__name__", None) in OPERAND_ATTRIBUTES:
        return True                                          # cols["x"].isin
    return False
