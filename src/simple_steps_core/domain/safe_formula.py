MAX_FORMULA_LENGTH = 4000


def validate_formula_text(formula: str) -> None:
    if not isinstance(formula, str):
        raise TypeError("Formula must be a string")
    if len(formula) > MAX_FORMULA_LENGTH:
        raise ValueError("Formula exceeds maximum length")
    if not formula.startswith("="):
        raise ValueError("Formula must start with '='")
