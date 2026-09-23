"""
Orchestrators
=============

Higher-order operations that apply an existing operation across a *collection*
produced by an earlier step. They are how a workflow expresses iterative
processing where individual items may fail independently:

  * ``map``      — run ``op`` for each item; return a :class:`MapResult` whose
                   ``ok``/``failed`` fields isolate per-item outcomes.
  * ``filter``   — keep items for which a predicate ``op`` returns truthy.
  * ``expand``   — flat-map: each item yields an iterable that is flattened.
  * ``collapse`` — reduce a collection to a single value via a 2-arg ``op``.
  * ``group``    — bucket items by the key ``op`` returns for each.

They belong to the built-in ``orchestration`` resource, so their registered
ids are ``orchestration-map``, ``orchestration-group`` and so on. The bare
names stay registered as aliases, so ``map`` keeps resolving everywhere it
already appears.

Each orchestrator is async and receives an :class:`ExecutionHandle` as its
first argument (injected by the engine, hidden from the public contract). The
handle runs sub-operations and inspects their definitions, so the orchestrator
can infer which parameter receives each item.

Authoring examples (formulas)::

    =map(over=step1, op="process_item", concurrency=8, retries=2)
    =filter(over=step1, op="is_valid")
    =expand(over=step1, op="explode")
    =collapse(over=step3, op="merge", initial=0)

Register them onto a registry with :func:`register_orchestrators`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Literal

from ..domain.models import (
    ORCHESTRATION_RESOURCE,
    ItemOutcome,
    MapResult,
    StepStatus,
)
from ..domain.collections import Group, Groups
from ..domain.tabular import is_frame, items_of, rows_to_frame, select_positions

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .resource_spec import ResourceSpec

OnError = Literal["collect", "fail_fast", "skip"]

#: The per-item operation used when a fan-out only needs to reshape data.
#: ``map``/``filter``/``expand`` default to it, so ``map(over="step1")`` is a
#: complete call. ``collapse`` cannot: a reduce needs a two-argument combiner,
#: and identity takes one.
IDENTITY_NAME = "identity"

#: The default per-item ``op``. The bare name stays registered as an alias of
#: ``orchestration-identity``, so it resolves either way.
IDENTITY = IDENTITY_NAME


def _source(over: Any) -> Any:
    """The collection to fan out over.

    A previous ``map`` step hands on a :class:`MapResult`, which is a pydantic
    model — iterating it directly yields ``("outcomes", [...])`` field tuples,
    which is a wrong answer with no error. Every mode but ``map`` therefore
    works on its successful values; ``map`` itself keeps the outcomes so a
    failure can stay pinned to its own item (see :func:`_gather_outcomes`).
    """
    return over.ok if isinstance(over, MapResult) else over


def _infer_item_arg(handle, op: str) -> str | None:
    """Pick which parameter of *op* receives each item.

    Prefers the first required parameter, else the first parameter, else None
    (a zero-argument operation called once per item).
    """
    definition = handle.get_definition(op)
    required = [p.name for p in definition.params if p.required]
    if required:
        return required[0]
    if definition.params:
        return definition.params[0].name
    return None


async def _run_item(handle, op: str, arg: str | None, item: Any, retries: int, shared: dict | None = None):
    """Invoke *op* for one *item*, retrying up to *retries* times.

    ``shared`` supplies constant keyword arguments passed to every sub-call; the
    item overrides any shared value for the item parameter.
    """
    kwargs = dict(shared or {})
    if arg is not None:
        kwargs[arg] = item
    attempt = 0
    while True:
        try:
            return await handle.run(op, **kwargs)
        except Exception:
            if attempt >= retries:
                raise
            attempt += 1


async def _gather_outcomes(
    handle,
    over: Iterable[Any],
    op: str,
    *,
    arg: str | None,
    concurrency: int,
    on_error: OnError,
    retries: int,
    shared: dict | None = None,
    carry_failures: bool = False,
) -> list[ItemOutcome]:
    """Run *op* across *over* with bounded concurrency, isolating failures.

    When *over* is a :class:`MapResult` and ``carry_failures`` is set, each
    item keeps its **upstream index** and an item that already failed is not
    re-run: its original error is passed straight through as this step's
    outcome for that index. A failure therefore stays attached to the one item
    it belongs to, all the way down a chain of fan-outs, and the UI can show
    which item broke and re-drive just that one.
    """
    if isinstance(over, MapResult):
        work = [
            (o.index, o.value, o.error if o.status is StepStatus.FAILED else None)
            for o in over.outcomes
        ]
    else:
        work = [(index, item, None) for index, item in enumerate(items_of(over))]

    if arg is None:
        arg = _infer_item_arg(handle, op)
    semaphore = asyncio.Semaphore(max(1, int(concurrency)))

    async def run_one(index: int, item: Any, upstream_error: str | None) -> ItemOutcome | None:
        if upstream_error is not None:
            # Already failed upstream: do not call op, and do not pretend it
            # succeeded. Carry the original error so the item's history is intact.
            if not carry_failures:
                return None
            if on_error == "fail_fast":
                raise RuntimeError(f"item {index} failed upstream: {upstream_error}")
            return ItemOutcome(index=index, status=StepStatus.FAILED,
                               error=upstream_error)
        async with semaphore:
            try:
                value = await _run_item(handle, op, arg, item, retries, shared)
                return ItemOutcome(index=index, status=StepStatus.COMPLETED, value=value)
            except Exception as exc:
                if on_error == "fail_fast":
                    raise
                if on_error == "skip":
                    return None
                return ItemOutcome(index=index, status=StepStatus.FAILED, error=str(exc))

    results = await asyncio.gather(*(run_one(i, it, err) for i, it, err in work))
    return [outcome for outcome in results if outcome is not None]


async def map_op(
    handle,
    *,
    over: Iterable[Any],
    op: str = IDENTITY,
    arg: str | None = None,
    args: dict | None = None,
    concurrency: int = 8,
    on_error: OnError = "collect",
    retries: int = 0,
) -> MapResult:
    """Apply *op* to each item of *over*, returning per-item outcomes.

    Chaining onto another ``map`` works directly: ``over`` may be the previous
    step's :class:`MapResult`, in which case each item keeps its upstream index
    and anything that already failed is **not** re-run — its error passes
    through as this step's outcome for that item, so a failure stays pinned to
    the one item it belongs to and can be re-driven on its own.

    With ``on_error="collect"`` (default), failures are captured as failed
    outcomes instead of aborting the batch. ``step.ok`` / ``step.failed`` then
    let downstream steps consume successes or re-drive failures. ``args`` supplies
    constant keyword arguments shared across every item's sub-call.
    """
    outcomes = await _gather_outcomes(
        handle,
        over,
        op,
        arg=arg,
        concurrency=concurrency,
        on_error=on_error,
        retries=retries,
        shared=args,
        carry_failures=True,
    )
    return MapResult(outcomes=outcomes)


async def filter_op(
    handle,
    *,
    over: Iterable[Any],
    op: str = IDENTITY,
    arg: str | None = None,
    args: dict | None = None,
    concurrency: int = 8,
    on_error: OnError = "skip",
    retries: int = 0,
) -> list[Any]:
    """Keep the items of *over* for which *op* returns a truthy value.

    Shape is preserved: filtering a DataFrame returns a **DataFrame** of the
    surviving rows (dtypes and index intact), and filtering a list returns a
    list. Each row of a frame reaches *op* as a plain ``dict``.

    Order is preserved. Items whose predicate raises are dropped under the
    default ``on_error="skip"``; use ``"fail_fast"`` to abort instead. ``args``
    supplies constant keyword arguments shared across every item's sub-call.
    """
    over = _source(over)
    items = items_of(over)
    if arg is None:
        arg = _infer_item_arg(handle, op)
    outcomes = await _gather_outcomes(
        handle,
        items,
        op,
        arg=arg,
        concurrency=concurrency,
        on_error=on_error,
        retries=retries,
        shared=args,
    )
    keep = sorted(
        o.index for o in outcomes if o.status is StepStatus.COMPLETED and o.value
    )
    # A frame in, a frame out: select by position so dtypes and the index
    # survive, instead of rebuilding rows from dicts.
    return select_positions(over, keep)


async def expand_op(
    handle,
    *,
    over: Iterable[Any],
    op: str = IDENTITY,
    arg: str | None = None,
    args: dict | None = None,
    concurrency: int = 8,
    on_error: OnError = "collect",
    retries: int = 0,
) -> list[Any]:
    """Flat-map: each item yields an iterable from *op*; results are flattened.

    *op* defaults to ``identity``, so ``expand(over="step1")`` flattens one
    level — a cell holding lists becomes one row per inner element.

    Successful per-item iterables are concatenated in original item order.
    Failures are skipped (``collect``/``skip``) or abort (``fail_fast``). ``args``
    supplies constant keyword arguments shared across every item's sub-call.
    """
    over = _source(over)
    outcomes = await _gather_outcomes(
        handle,
        over,
        op,
        arg=arg,
        concurrency=concurrency,
        on_error=on_error,
        retries=retries,
        shared=args,
    )
    flattened: list[Any] = []
    for outcome in sorted(outcomes, key=lambda o: o.index):
        if outcome.status is not StepStatus.COMPLETED:
            continue
        produced = outcome.value
        if isinstance(produced, Iterable) and not isinstance(produced, (str, bytes, dict)):
            flattened.extend(produced)
        else:
            flattened.append(produced)
    # Expanded rows are new, so they cannot be selected from the original by
    # position — rebuild a frame only when every row is a dict.
    if is_frame(over):
        return rows_to_frame(flattened, over)
    return flattened


async def collapse_op(
    handle,
    *,
    over: Iterable[Any],
    op: str,
    initial: Any = None,
    args: dict | None = None,
) -> Any:
    """Reduce *over* to a single value with a two-argument *op*.

    Unlike the other modes *op* has no default: a reduce needs a combiner, and
    ``identity`` takes one argument rather than two.

    *op*'s first parameter receives the accumulator, its second the next item.
    When *initial* is ``None`` the first item seeds the accumulator. Runs
    sequentially because each step depends on the previous accumulator. ``args``
    supplies constant keyword arguments shared across every reduction call.
    """
    items = items_of(_source(over))
    definition = handle.get_definition(op)
    params = [p.name for p in definition.params]
    if len(params) < 2:
        raise ValueError(
            f"collapse requires a 2-argument operation; {op!r} declares {params}"
        )
    acc_name, item_name = params[0], params[1]
    shared = {k: v for k, v in (args or {}).items() if k not in (acc_name, item_name)}

    if initial is not None:
        accumulator = initial
        rest = items
    else:
        if not items:
            return None
        accumulator = items[0]
        rest = items[1:]

    for item in rest:
        accumulator = await handle.run(op, **{acc_name: accumulator, item_name: item}, **shared)
    return accumulator


async def group_op(
    handle,
    *,
    over: Iterable[Any],
    op: str = IDENTITY,
    arg: str | None = None,
    args: dict | None = None,
    concurrency: int = 8,
    on_error: OnError = "skip",
    retries: int = 0,
) -> Groups:
    """Bucket the items of *over* by the key *op* returns for each one.

    *op* is a **key function**, not a transform: each item is passed to it and
    the returned value becomes the bucket the *original item* lands in. The
    The result is a :class:`Groups` — strata in first-appearance order, items
    in their original order within each. Shape is preserved: grouping a
    DataFrame gives a **DataFrame per stratum**, and each row reaches *op* as a
    plain ``dict``.

    Fanning out over the result is the point: ``Groups`` iterates
    :class:`Group` records carrying ``key`` and ``rows``, so a per-stratum tool
    can write a labelled row and a ``map`` over the strata builds a stratified
    table. (A plain dict would have iterated its *keys*, handing each tool a
    bare label and silently losing the rows.)

    This is expand's inverse, and the step that makes a per-group reduce
    possible: group by customer, then collapse each bucket to a total.

    A key that is not hashable is a common mistake (returning a list or dict),
    so it is reported as that item's failure rather than aborting the batch.
    Items whose key function raises are dropped under the default
    ``on_error="skip"``; use ``"fail_fast"`` to abort instead. ``args`` supplies
    constant keyword arguments shared across every item's sub-call.
    """
    over = _source(over)
    items = items_of(over)
    if arg is None:
        arg = _infer_item_arg(handle, op)
    outcomes = await _gather_outcomes(
        handle,
        items,
        op,
        arg=arg,
        concurrency=concurrency,
        on_error=on_error,
        retries=retries,
        shared=args,
    )
    positions: dict[Any, list[int]] = {}
    for outcome in sorted(outcomes, key=lambda o: o.index):
        if outcome.status is not StepStatus.COMPLETED:
            continue
        key = outcome.value
        try:
            positions.setdefault(key, [])
        except TypeError as exc:
            if on_error == "fail_fast":
                raise TypeError(
                    f"group key for item {outcome.index} is unhashable "
                    f"({type(key).__name__}); {op!r} must return a hashable key"
                ) from exc
            continue
        positions[key].append(outcome.index)
    # Each bucket keeps the shape of the input: frames in, frames out.
    return Groups(groups=[
        Group(key=key, rows=select_positions(over, where))
        for key, where in positions.items()
    ])


def identity(value: Any) -> Any:
    """Return *value* unchanged.

    The per-item ``op`` for reshaping data without transforming it, so a step
    can change the *shape* of a collection with no bespoke tool:

    ``expand`` + identity
        flattens one level — a cell holding a list of lists becomes one row per
        inner element.
    ``map`` + identity
        one cell per item, with per-item status, from a single collection cell.
    ``filter`` + identity
        keeps the items that are already truthy.

    ``collapse`` needs a two-argument reducer, so identity does not apply there.
    """
    return value


#: The built-in orchestrators, as ``short name -> (function, description)``.
#: Each registers as ``orchestration-<name>`` with ``<name>`` kept as an alias.
ORCHESTRATORS: dict[str, tuple[Any, str]] = {
    "map": (map_op, "Apply op to each item"),
    "filter": (filter_op, "Keep items where op is truthy"),
    "expand": (expand_op, "Flat-map op over items"),
    "collapse": (collapse_op, "Reduce items via op"),
    "group": (group_op, "Bucket items by the key op returns"),
}


def orchestration_resource(registry) -> "ResourceSpec":
    """Build the built-in ``orchestration`` resource against *registry*.

    It is **namespace-only**: its tools take no injected resource, because an
    orchestrator receives an :class:`ExecutionHandle` from the engine instead.
    What the resource provides is the namespace — ``orchestration-map``,
    ``orchestration-group`` — and a single place to ask what orchestration
    the system can do.
    """
    from .resource_spec import ResourceSpec

    spec = ResourceSpec(
        ORCHESTRATION_RESOURCE,
        description="Applying a tool across a collection: map, filter, expand, "
                    "collapse (reduce), group.",
        registry=registry,
    )
    for name, (fn, description) in ORCHESTRATORS.items():
        spec.orchestrator(name, description=description, aliases=(name,))(fn)
    # A plain tool, not an orchestrator: it takes no handle and is what the
    # orchestrators above call per item when you only want to reshape.
    spec.tool(
        IDENTITY_NAME,
        description="Pass each item through unchanged",
        category="orchestration",
        aliases=(IDENTITY_NAME,),
    )(identity)
    return spec


def register_orchestrators(registry) -> "ResourceSpec":
    """Register the built-in orchestrators onto *registry*.

    Call this once during startup, alongside your domain operations and before
    freezing the registry. Returns the :class:`ResourceSpec` that owns them.

    The tools register under their qualified ids (``orchestration-map``) with
    the bare names (``map``) kept as aliases, so saved workflows, existing
    specs, and ``registry.has("map")`` all keep working.
    """
    return orchestration_resource(registry)
