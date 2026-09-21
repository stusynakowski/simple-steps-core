"""
Orchestration inference
=======================

Work out how a step should consume an earlier step's output by comparing the
two declared types. This is what lets the card configure orchestration from a
single choice — "read step2" — instead of asking for mode, ``over`` and an item
binding separately.

The rule is one comparison. Given what the upstream step *produces* and what the
parameter *wants*:

=========================  ==================  =========================
upstream produces          parameter wants     inferred
=========================  ==================  =========================
``list[float]``            ``float``           **map** — element-wise
``list[float]``            ``list[float]``     **once** — the whole column
``list[list[float]]``      ``list[float]``     **map** — each row is a list
anything                   unannotated         **once** — cannot tell
=========================  ==================  =========================

A fanned-out upstream produces a ``MapResult``, which is not a plain list — it
iterates its own pydantic fields, not its items — so reading it needs the
``.ok`` accessor. Inference returns that suffix with the reference.

Everything here is pure: no Streamlit, no session state.
"""

from __future__ import annotations


__all__ = ["effective_output", "infer_binding", "Binding", "describe"]

#: How deep to walk a chain of `filter` steps before giving up on the item type.
_MAX_DEPTH = 8


class Binding:
    """How a step should read an earlier step: a reference plus a mode."""

    __slots__ = ("reference", "mode", "reason")

    def __init__(self, reference: str, mode: str, reason: str = ""):
        self.reference = reference
        self.mode = mode
        self.reason = reason

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Binding) and other.reference == self.reference
                and other.mode == self.mode)

    def __repr__(self) -> str:
        return f"<Binding {self.reference!r} mode={self.mode!r}>"


def _result_schema(definition) -> dict:
    """The JSON-Schema node for a tool's return value."""
    if definition is None:
        return {}
    return (definition.output_schema or {}).get("properties", {}).get("result", {}) or {}


def effective_output(draft, registry, drafts=None, _depth: int = 0) -> tuple[dict, str | None]:
    """What *draft* actually produces, and the accessor needed to read it.

    Returns ``(schema, accessor)`` where accessor is ``".ok"`` for a fan-out that
    yields a ``MapResult``, else ``None``. The tool's own return type is only the
    answer for a ``single`` step — every other mode reshapes it.
    """
    if draft is None or not draft.op or not registry.has(draft.op):
        return {}, None

    definition = registry.get_definition(draft.op)
    result = _result_schema(definition)
    mode = draft.orchestration.mode

    if mode == "single":
        return result, None

    if mode == "map":
        # A MapResult; `.ok` reads the successful values as a list.
        return {"type": "array", "items": result}, ".ok"

    if mode == "expand":
        # Each item's iterable is concatenated, so a list return flattens to
        # itself and a scalar return becomes a list of that scalar.
        if result.get("type") == "array":
            return result, None
        return {"type": "array", "items": result}, None

    if mode == "collapse":
        return result, None

    if mode == "filter":
        # `filter` returns the *input* items, so the element type comes from
        # whatever this step reads, not from its own predicate's bool return.
        upstream = _source_draft(draft, drafts)
        if upstream is not None and _depth < _MAX_DEPTH:
            schema, _ = effective_output(upstream, registry, drafts, _depth + 1)
            if schema.get("type") == "array":
                return schema, None
            return {"type": "array", "items": schema}, None
        return {"type": "array"}, None

    return result, None


def _source_draft(draft, drafts):
    """The draft a fan-out reads, when we can find it."""
    if drafts is None:
        return None
    over = draft.orchestration.over
    return drafts.get(over) if over else None


def _compatible(have: dict, want: dict) -> bool:
    """True when a value of shape *have* can be passed where *want* is declared.

    An unannotated or unknown type on either side compares equal: the contract
    does not say enough to rule it out, and refusing would be worse than
    allowing the user to correct it.
    """
    have_type, want_type = have.get("type"), want.get("type")
    if not have_type or not want_type:
        return True
    if have_type != want_type:
        # integers satisfy a float parameter
        return {have_type, want_type} == {"integer", "number"}
    if have_type == "array":
        return _compatible(have.get("items") or {}, want.get("items") or {})
    return True


def infer_binding(step_id: str, upstream_draft, param_schema: dict, registry,
                  drafts=None, target_definition=None) -> Binding:
    """How *step_id*'s output should be consumed by a parameter wanting *param_schema*.

    This is the whole of the "configure orchestration for me" behavior: one type
    comparison decides between passing a collection whole and applying a tool
    across its elements. *target_definition* is the tool being configured — its
    return type distinguishes a predicate from a transform.
    """
    have, accessor = effective_output(upstream_draft, registry, drafts)
    reference = f"{step_id}{accessor or ''}"

    if _compatible(have, param_schema):
        return Binding(reference, "single",
                       "the parameter takes what this step produces")

    if have.get("type") == "array" and _compatible(have.get("items") or {}, param_schema):
        # A per-item tool returning bool is a predicate, not a transform: the
        # useful result is the items that pass, not a column of flags.
        if _result_schema(target_definition).get("type") == "boolean":
            return Binding(reference, "filter",
                           "it returns true/false per element, so keep what passes")
        return Binding(reference, "map",
                       "the parameter takes one element, so apply it across the column")

    return Binding(reference, "single",
                   "types do not line up — passing the value through unchanged")


def describe(binding: Binding) -> str:
    """One short line explaining an inferred binding, for the card's caption."""
    from ..components.base import format_reference

    verb = {"single": "once", "map": "per item", "filter": "per item",
            "expand": "per item", "collapse": "reduced"}.get(binding.mode, binding.mode)
    return f"{verb} on `{format_reference(binding.reference)}` — {binding.reason}"
