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
from typing import Any, Literal

from ..domain.models import ItemOutcome, MapResult, StepStatus

OnError = Literal["collect", "fail_fast", "skip"]


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


async def _run_item(handle, op: str, arg: str | None, item: Any, retries: int):
    """Invoke *op* for one *item*, retrying up to *retries* times.

    Returns the produced value. Raises the last exception if all attempts fail.
    """
    kwargs = {arg: item} if arg is not None else {}
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
) -> list[ItemOutcome]:
    """Run *op* across *over* with bounded concurrency, isolating failures."""
    items = list(over)
    if arg is None:
        arg = _infer_item_arg(handle, op)
    semaphore = asyncio.Semaphore(max(1, int(concurrency)))

    async def run_one(index: int, item: Any) -> ItemOutcome | None:
        async with semaphore:
            try:
                value = await _run_item(handle, op, arg, item, retries)
                return ItemOutcome(index=index, status=StepStatus.COMPLETED, value=value)
            except Exception as exc:
                if on_error == "fail_fast":
                    raise
                if on_error == "skip":
                    return None
                return ItemOutcome(index=index, status=StepStatus.FAILED, error=str(exc))

    results = await asyncio.gather(*(run_one(i, it) for i, it in enumerate(items)))
    return [outcome for outcome in results if outcome is not None]


async def map_op(
    handle,
    *,
    over: Iterable[Any],
    op: str,
    arg: str | None = None,
    concurrency: int = 8,
    on_error: OnError = "collect",
    retries: int = 0,
) -> MapResult:
    """Apply *op* to each item of *over*, returning per-item outcomes.

    With ``on_error="collect"`` (default), failures are captured as failed
    outcomes instead of aborting the batch. ``step.ok`` / ``step.failed`` then
    let downstream steps consume successes or re-drive failures.
    """
    outcomes = await _gather_outcomes(
        handle,
        over,
        op,
        arg=arg,
        concurrency=concurrency,
        on_error=on_error,
        retries=retries,
    )
    return MapResult(outcomes=outcomes)


async def filter_op(
    handle,
    *,
    over: Iterable[Any],
    op: str,
    arg: str | None = None,
    concurrency: int = 8,
    on_error: OnError = "skip",
    retries: int = 0,
) -> list[Any]:
    """Keep the items of *over* for which *op* returns a truthy value.

    Order is preserved. Items whose predicate raises are dropped under the
    default ``on_error="skip"``; use ``"fail_fast"`` to abort instead.
    """
    items = list(over)
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
    )
    keep = {o.index for o in outcomes if o.status is StepStatus.COMPLETED and o.value}
    return [item for index, item in enumerate(items) if index in keep]


async def expand_op(
    handle,
    *,
    over: Iterable[Any],
    op: str,
    arg: str | None = None,
    concurrency: int = 8,
    on_error: OnError = "collect",
    retries: int = 0,
) -> list[Any]:
    """Flat-map: each item yields an iterable from *op*; results are flattened.

    Successful per-item iterables are concatenated in original item order.
    Failures are skipped (``collect``/``skip``) or abort (``fail_fast``).
    """
    outcomes = await _gather_outcomes(
        handle,
        over,
        op,
        arg=arg,
        concurrency=concurrency,
        on_error=on_error,
        retries=retries,
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
    return flattened


async def collapse_op(
    handle,
    *,
    over: Iterable[Any],
    op: str,
    initial: Any = None,
) -> Any:
    """Reduce *over* to a single value with a two-argument *op*.

    *op*'s first parameter receives the accumulator, its second the next item.
    When *initial* is ``None`` the first item seeds the accumulator. Runs
    sequentially because each step depends on the previous accumulator.
    """
    items = list(over)
    definition = handle.get_definition(op)
    params = [p.name for p in definition.params]
    if len(params) < 2:
        raise ValueError(
            f"collapse requires a 2-argument operation; {op!r} declares {params}"
        )
    acc_name, item_name = params[0], params[1]

    if initial is not None:
        accumulator = initial
        rest = items
    else:
        if not items:
            return None
        accumulator = items[0]
        rest = items[1:]

    for item in rest:
        accumulator = await handle.run(op, **{acc_name: accumulator, item_name: item})
    return accumulator


def register_orchestrators(registry) -> None:
    """Register the built-in orchestrators onto *registry*.

    Call this once during startup, alongside your domain operations and before
    freezing the registry.
    """
    registry.register_orchestrator("map", map_op, description="Apply op to each item")
    registry.register_orchestrator("filter", filter_op, description="Keep items where op is truthy")
    registry.register_orchestrator("expand", expand_op, description="Flat-map op over items")
    registry.register_orchestrator("collapse", collapse_op, description="Reduce items via op")
