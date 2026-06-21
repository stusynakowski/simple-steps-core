import ast

from .models import ToolCall
from .safe_formula import validate_formula_text


def parse_formula(formula: str) -> ToolCall:
    validate_formula_text(formula)
    expression = formula[1:].strip()
    if not expression:
        raise ValueError("Formula expression is empty")

    tree = ast.parse(expression, mode="eval")
    node = tree.body
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        raise ValueError("Formula must be a function-style call, e.g. '=op(a=1)'")

    if node.args:
        raise ValueError("Positional arguments are not supported; use keyword arguments")

    operation_id = node.func.id
    kwargs: dict[str, object] = {}
    for kw in node.keywords:
        if kw.arg is None:
            raise ValueError("Unsupported '**kwargs' syntax in formula")
        kwargs[kw.arg] = ast.literal_eval(kw.value)

    return ToolCall(operation_id=operation_id, arguments=kwargs)


def render_formula(tool_call: ToolCall) -> str:
    if not tool_call.operation_id:
        raise ValueError("operation_id is required")
    parts = [f"{key}={value!r}" for key, value in tool_call.arguments.items()]
    return f"={tool_call.operation_id}({', '.join(parts)})"
