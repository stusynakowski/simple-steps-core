"""The exceptions core raises: a selection that can't be made, a run that
stopped, a value that can't be saved, a resource that wasn't loaded.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from typing import Any


class StepFailed(RuntimeError):
    """``run_all`` stopped: a step has a failed cell it didn't catch.

    Steps that already ran keep their results; ``not_run`` lists the rest. Put
    ``mod.try_except(…)`` on a step to let its failures through.
    """

    def __init__(self, step_id: str, cell: Any, error: str, not_run: list[str]):
        self.step_id, self.cell, self.error, self.not_run = step_id, cell, error, not_run
        later = f" Not run: {', '.join(not_run)}." if not_run else ""
        super().__init__(
            f"step {step_id!r} failed at {step_id}[{cell}]: {error}. The run "
            f"stopped.{later} Add mod.try_except(…) to the step to let this "
            "failure through.")


# ─────────────────────────────────────────────────────────────────────────
# The authoring surface: objects instead of strings
# ─────────────────────────────────────────────────────────────────────────
# Everything here is sugar that produces the exact same `Operation` data. The
# gain is that a typo becomes a NameError at import rather than a silent
# literal at run time, and an editor can autocomplete.


# ─────────────────────────────────────────────────────────────────────────
# Selection — wf["p"][1:5][cols["name":"price"]] (008 C7)
# ─────────────────────────────────────────────────────────────────────────
# Two type rules: column names are strings, row selectors are integers. And one
# syntax rule: a plain bracket selects rows, `cols[…]` selects columns. Each
# part normalizes to its saved form at once, so every spelling of the same
# selection is the same value — and saves identically.
class SelectionError(ValueError):
    """A selection that can't be made — refused when written, or failed at run."""


# ─────────────────────────────────────────────────────────────────────────
# Resources — objects a workflow uses that are not data (core-proposals/007)
# ─────────────────────────────────────────────────────────────────────────
# `wf["…"]` is a table, `res["…"]` is a resource, everything else is a literal.
# A resource is declared on the workflow (`wf.define`) from literal settings
# only, saved as that declaration, and supplied live by the caller at run
# (`wf.run(..., resources={name: object})`). Two ways a tool uses one:
#
#   * an **unbound** tool is an ordinary ``@tool`` function with a parameter
#     typed as the resource: ``enrich(city, db: FakeDB)``, bound per step as
#     ``db=res["db"]``;
#   * a **bound** tool is a method of the resource class marked
#     ``@bound_tool``, used on one named instance: ``res["db"].lookup``.
class ResourceNotLoaded(LookupError):
    """A step needs a resource the caller did not pass to ``run``."""


# ─────────────────────────────────────────────────────────────────────────
# Payload codecs — only the full export needs these
# ─────────────────────────────────────────────────────────────────────────
# The light export is strings and numbers, so it needs nothing. Payloads are
# where serialization gets hard: an object column is not Arrow-serializable
# (docs/shape-algebra.md §8.8), so these handle frames and JSON-safe values and
# say so plainly when they meet anything else, rather than writing a `repr`
# that silently will not load back.
class PayloadError(TypeError):
    """Raised when a payload cannot be represented in a session export."""
