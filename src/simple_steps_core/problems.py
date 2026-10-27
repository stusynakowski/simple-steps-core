"""Problem: why a step can't run, or what to watch out for.

A problem is its message, so it prints, joins and compares as text, and it
carries what a UI needs to act on it: a ``code`` from :data:`CODES`, the
``step`` it is on, and the ``argument`` or ``row`` when there is one. A warning
is a problem with ``severity="warning"``: it doesn't stop the step
(docs/design/object-model.md §4.9).
"""

from __future__ import annotations

from typing import Any

#: Every problem code, with what it means. Errors make a step invalid; warnings
#: don't.
CODES: dict[str, str] = {
    # what the step names
    "not_in_catalog": "the tool, modifier, combine or resource type isn't in the catalog",
    "different_function": "a different function has the name of a tool in the catalog",
    "unknown_tool": "no tool by that name",
    "unknown_resource": "an argument names a resource the workflow hasn't defined",
    "unknown_modifier": "no modifier by that name",
    "reserved_name": "the name is reserved for the formula language",
    # modifier settings
    "unknown_setting": "a modifier was given a setting it doesn't take",
    "missing_setting": "a modifier is missing a setting it needs",
    "wrong_setting_type": "a modifier setting has the wrong type",
    "bad_tool_setting": "a setting names a tool where none is taken, or a tool that doesn't fit",
    "bad_combine": "a combine's inputs or settings don't fit together",
    "contradicts_verb": "an expectation contradicts what the verb produces",
    "bad_name": "a naming modifier names nothing, or names a column badly",
    "two_shape_verbs": "more than one shape verb in one step",
    "verb_takes_no_tool": "the verb applies no tool, but one was given",
    # references
    "foreign_reference": "a reference was made in another workflow",
    "self_reference": "the step reads itself",
    "missing_step": "the step reads a step that doesn't exist (yet)",
    "later_step": "the step reads a step that comes after it",
    "invalid_input": "the step reads a step that is invalid",
    "circular": "the step's references go round in a circle",
    "bad_selection": "a selection of rows or columns can't be made",
    # arguments and columns
    "bad_argument": "an argument isn't a literal or a reference",
    "unknown_argument": "an argument isn't a parameter the tool takes",
    "missing_column": "a column the step needs won't be in its input",
    "column_clash": "an output column would replace an input column",
    "wrong_type": "a value's type doesn't match what the tool declares",
    "empty_input": "a step reads an empty step: one declared with no expression yet",
    "naming_case": "a column a step writes doesn't follow the kernel's naming case",
    "modifier_order": "an execution modifier written before the verb covers the whole step, not each row",
    "default_type": "a try_except default doesn't fit the tool's return type",
    "run_warning": "something a step met while it ran: rows that held no list, fields a record didn't declare",
    "not_a_list": "expand was given rows holding no list (None): they gave no rows",
    "unmatched_rows": "rows of two grids would meet with no match core recorded: join, or zip_(…, match_ids=True)",
    "wrong_shape": "a referenced argument's shape (cell, row, column, table) doesn't fit the parameter's type",
    "problem": "anything not covered by another code",
    # warnings
    "unchecked_argument": "an argument goes into **kwargs, so it can't be checked",
    "rows_by_position": "rows are picked by position from a step whose order may change",
    "argument_overrides_column": "an argument replaces a same-named input column for every row",
    "output_overwrites_column": "the step writes over a column its input already has",
    "likely_missing_column": "a column the tool needs is predicted to be missing",
    "unconfirmed_column": "a column the tool needs can't be confirmed until the input runs",
    "column_will_be_missing": "an input was edited, and its new formula won't give a column this step needs",
}


class Problem(str):
    """A problem's message, with its code, step, argument, row and severity."""

    code: str
    step: str | None
    argument: str | None
    row: Any
    severity: str

    def __new__(cls, message: str, code: str = "problem", *, step: str | None = None,
                argument: str | None = None, row: Any = None,
                severity: str = "error") -> "Problem":
        if code not in CODES:
            raise ValueError(f"unknown problem code {code!r}")
        if severity not in ("error", "warning"):
            raise ValueError(f"severity is 'error' or 'warning', got {severity!r}")
        self = super().__new__(cls, message)
        self.code, self.step, self.argument, self.row = code, step, argument, row
        self.severity = severity
        return self

    @property
    def message(self) -> str:
        return str.__str__(self)

    def __str__(self) -> str:
        return str.__str__(self)

    def __repr__(self) -> str:
        where = f", step={self.step!r}" if self.step else ""
        kind = ", severity='warning'" if self.severity == "warning" else ""
        return f"Problem({self.code!r}, {self.message!r}{where}{kind})"

    def __reduce__(self):
        return (_rebuild, (self.message, self.code, self.step, self.argument,
                           self.row, self.severity))

    def to_dict(self) -> dict:
        """The problem as plain data, for the app."""
        return {"code": self.code, "message": self.message, "step": self.step,
                "argument": self.argument, "row": self.row, "severity": self.severity}

    def at(self, step: str | None) -> "Problem":
        """The same problem, on *step*."""
        return Problem(self.message, self.code, step=step, argument=self.argument,
                       row=self.row, severity=self.severity)


def _rebuild(message, code, step, argument, row, severity) -> Problem:
    return Problem(message, code, step=step, argument=argument, row=row,
                   severity=severity)


def coded(found: list, code: str) -> None:
    """Give *code* to every entry of *found* that is still plain text."""
    for i, item in enumerate(found):
        if not isinstance(item, Problem):
            found[i] = Problem(item, code)


def classified(message: str, rules: tuple[tuple[str, str], ...], default: str,
               severity: str = "error") -> Problem:
    """*message* as a Problem whose code is the first rule whose text it contains."""
    if isinstance(message, Problem):
        return message
    for needle, code in rules:
        if needle in message:
            return Problem(message, code, severity=severity)
    return Problem(message, default, severity=severity)
