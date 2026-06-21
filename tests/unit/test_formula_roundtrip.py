from simple_steps_core.domain.formulas import parse_formula, render_formula
from simple_steps_core.domain.models import ToolCall


def test_formula_roundtrip_keywords_only():
    call = ToolCall(operation_id="load_csv", arguments={"filepath": "data.csv", "limit": 10})
    formula = render_formula(call)
    parsed = parse_formula(formula)

    assert parsed.operation_id == "load_csv"
    assert parsed.arguments["filepath"] == "data.csv"
    assert parsed.arguments["limit"] == 10
