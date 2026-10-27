"""
kernels.py — kernels: each open workflow, live (dev_plan/124 phase 2).

Vocabulary (docs/system_design/10-object-model.md): a **session** is a user's
browser connection (the ``ss_session`` cookie); a **kernel** is one workflow,
live, inside a session — not a process (yet); the **kernel manager** (below)
decides which kernels are live and puts the others away.

Before this, every step ran in a throwaway ``grid.Workflow`` with the steps it
read loaded back in as plain tables. Two things were lost on the way:

* **row links** — core keeps, for each row, the input row it came from, and
  ``zip_`` pairs by it. A loaded table is renumbered 0…n-1 (core 010, ``#``),
  so a result computed after a sort and zipped back beside its input paired
  the wrong rows, silently;
* **staleness** — editing an earlier step can't mark later ones out of date
  when they ran in workflows that are already gone.

Here the session's active workflow is one core ``Workflow`` for as long as it
stays active. Each run request carries every step's name and formula; they
are (re)declared — an unchanged formula is left alone, a changed one makes
core mark it and everything after it ``stale`` — and the step is run in that
workflow. Steps it reads that have never run in this session (a fresh session,
a reopened workflow) run first. The output is still stored under a ref id, so
``/api/data``, ``/api/cell`` and the grid read it as before; every response
also reports each step's state (completed, stale and why, staged, invalid).

Each live workflow is a *kernel* (see "Kernels" below): one is live per
session (owner, 2026-10-21); switching workflows saves the current one to disk
and restores — or starts — the other, without recomputing anything.

Only formulas in core's syntax (``operation_formula.is_canonical``) live here.
A step in the app's older syntax still runs on the old path; a core step that
reads one gets its stored output as a table, as before.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from simple_steps_core import grid

from .grid_runner import (
    GridStepError, _bind_positional_resources, _engine_metrics, _formula_tool, _tools, _verb_of,
)


@dataclass
class Kernel:
    """One workflow, live: its core Workflow, and what the app declared into it."""

    key: str
    wf: grid.Workflow
    #: The resource declarations it was built with (a change rebuilds it).
    declarations: Dict[str, Any]
    types: Dict[str, type] = field(default_factory=dict)
    #: step → the formula last declared for it.
    formulas: Dict[str, str] = field(default_factory=dict)
    #: step → the core operation it was declared as.
    operations: Dict[str, dict] = field(default_factory=dict)
    #: step → the steps it reads, and the resources it uses.
    reads: Dict[str, List[str]] = field(default_factory=dict)
    uses: Dict[str, List[str]] = field(default_factory=dict)
    #: step → why it couldn't be declared (a formula that doesn't compile, …).
    problems: Dict[str, str] = field(default_factory=dict)
    #: step → the stored ref an old-syntax step was loaded from.
    loaded: Dict[str, str] = field(default_factory=dict)
    #: the app's step id → its name, as last synced (to follow renames).
    ids: Dict[str, str] = field(default_factory=dict)
    #: When it was last used (time.monotonic), for the idle culler.
    last_used: float = 0.0
    lock: threading.RLock = field(default_factory=threading.RLock)


# ─────────────────────────────────────────────────────────────────────────────
# Kernels: the live workflows, and putting them away
# ─────────────────────────────────────────────────────────────────────────────
#
# A *kernel* is one workflow, live: its core Workflow with every step declared,
# each step's last output (with its version and what it read — how core knows
# what is stale), and the app's bookkeeping. As in JupyterHub, a kernel belongs
# to a session and a workflow; unlike a Jupyter kernel it has no hidden state,
# so it can be saved whole and brought back exactly (core's
# ``to_session_dict`` / ``Workflow.from_dict``) — outputs, versions and row
# links — without recomputing anything.
#
# At most MAX_LIVE kernels per session are live (owner, 2026-10-21: one
# workflow is worked on at a time). Opening another saves the least recently
# used one to disk first; one idle for IDLE_SECONDS is saved and freed; all are
# saved when the server stops. Asking for a saved one restores it.

#: Live kernels per session. One, by the owner's rule; raise it to keep
#: several tabs live.
MAX_LIVE = 1
#: A kernel unused this long is saved to disk and freed.
IDLE_SECONDS = 30 * 60
#: Whether kernels are saved to disk when put away. Off for throwaway runs
#: (the examples' checks), which then just start fresh.
PERSIST = True

#: session → workflow key → its live kernel.
_LIVE: Dict[str, Dict[str, Kernel]] = {}
_GUARD = threading.Lock()


def _snapshot_path(session_id: str, key: str) -> str:
    import hashlib
    import os
    from .engine import RESULT_CACHE_DIR, _session_token
    name = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return os.path.join(RESULT_CACHE_DIR, _session_token(session_id), "kernels", f"{name}.json")


def _save(session_id: str, s: Kernel) -> bool:
    """Put a kernel away on disk: its core workflow, outputs and all."""
    import json
    import os
    if not PERSIST:
        return False
    with s.lock:
        try:
            core = s.wf.to_session_dict()
        except Exception as exc:
            # An output core can't save — an image array, a Figure (core asks
            # C29/C30). Save the steps without outputs: restored, they re-run
            # when needed rather than coming back.
            print(f"  kernel '{s.key}': outputs not saved ({exc}); its steps will re-run")
            core = s.wf.to_dict()
        try:
            text = json.dumps({
                "key": s.key, "declarations": s.declarations,
                "formulas": s.formulas, "operations": s.operations, "reads": s.reads,
                "uses": s.uses, "problems": s.problems, "loaded": s.loaded, "ids": s.ids,
                "core": core,
            })
        except (TypeError, ValueError) as exc:
            print(f"  kernel '{s.key}' not saved: {exc}")
            return False
    path = _snapshot_path(session_id, s.key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return True


def _restore(session_id: str, key: str, declarations: Dict[str, Any]) -> Optional[Kernel]:
    """A saved kernel, brought back as it was; None when there is none (or it
    was saved with other resources, or core can no longer read it)."""
    import json
    import os
    from .resources import resolve
    path = _snapshot_path(session_id, key)
    if not PERSIST or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            blob = json.load(fh)
        if blob.get("key") != key or blob.get("declarations") != declarations:
            return None
        types = {name: resolve(name, decl)[0] for name, decl in declarations.items()}
        wf = grid.Workflow.from_dict(blob["core"], _tools(),
                                     resource_types={cls.__name__: cls for cls in types.values()})
    except Exception as exc:
        print(f"  kernel '{key}' not restored, starting fresh: {exc}")
        return None
    s = Kernel(key, wf, dict(declarations), types=types)
    for name in ("formulas", "operations", "reads", "uses", "problems", "loaded", "ids"):
        setattr(s, name, blob.get(name) or {})
    return s


def _cull_idle(now: float) -> None:
    """Save and free kernels nobody has used for IDLE_SECONDS. Holds _GUARD."""
    for session_id, live in list(_LIVE.items()):
        for key, s in list(live.items()):
            if now - s.last_used > IDLE_SECONDS and s.lock.acquire(blocking=False):
                try:
                    _save(session_id, s)
                    del live[key]
                finally:
                    s.lock.release()
        if not live:
            del _LIVE[session_id]


def _kernel_for(session_id: str, key: str, declarations: Dict[str, Any]) -> Kernel:
    """The live kernel for *key* in this session: kept, restored from disk, or
    new — putting away the least recently used one when the session is full."""
    import time
    now = time.monotonic()
    with _GUARD:
        _cull_idle(now)
        live = _LIVE.setdefault(session_id, {})
        s = live.get(key)
        if s is not None and s.declarations != declarations:
            # Resources changed: a kernel is built around its resources.
            del live[key]
            s = None
        if s is None:
            # Put away the least recently used — never one that's mid-run
            # (the session goes over the cap until it finishes).
            for oldest in sorted(live, key=lambda k: live[k].last_used):
                if len(live) < MAX_LIVE:
                    break
                victim = live[oldest]
                if victim.lock.acquire(blocking=False):
                    try:
                        _save(session_id, victim)
                        del live[oldest]
                    finally:
                        victim.lock.release()
            s = _restore(session_id, key, declarations)
            if s is None:
                s = Kernel(key, grid.Workflow(), dict(declarations))
                _define_resources(s)
            live[key] = s
        s.last_used = now
        return s


def save_all() -> None:
    """Put every live kernel away (the server is stopping)."""
    with _GUARD:
        for session_id, live in _LIVE.items():
            for s in live.values():
                _save(session_id, s)


def forget(session_id: str) -> None:
    """Drop a session's live kernels, unsaved (tests; a session that ends)."""
    with _GUARD:
        _LIVE.pop(session_id, None)


import atexit as _atexit  # noqa: E402
_atexit.register(save_all)


def _define_resources(s: Kernel) -> None:
    """Every declared resource, defined once — before any step that uses one."""
    from .resources import ResourceError, resolve
    for name, declaration in s.declarations.items():
        try:
            s.types[name], settings = resolve(name, declaration)
            s.wf.define(name, s.types[name], **settings)
        except (ResourceError, TypeError) as exc:
            s.problems[f'res["{name}"]'] = str(exc)


# ─────────────────────────────────────────────────────────────────────────────
# Declaring
# ─────────────────────────────────────────────────────────────────────────────

_NOT_LITERAL = object()


def _literal_value(formula: str) -> Any:
    """`=[1, 2]`, `={"x": 1}`, `=7`, `="text"` → the value; else _NOT_LITERAL."""
    import ast
    try:
        return ast.literal_eval(formula[1:].strip())
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return _NOT_LITERAL

def _operation_for(s: Kernel, formula: str, tools: Dict[str, Any]) -> Tuple[dict, Any]:
    """A formula in core's syntax → (the core operation, its compiled form)."""
    from .operation_formula import compile_formula

    compiled = compile_formula(formula)
    for name in compiled.resources:
        if name not in s.declarations:
            known = ", ".join(f'res["{n}"]' for n in s.declarations) or "none yet"
            raise GridStepError(
                f'no resource named "{name}" in this workflow (its resources: {known}). '
                "Add it to the workflow's resources first"
            )
    fn = _formula_tool(compiled, tools, s.types)
    _bind_positional_resources(compiled, fn, s.types)
    inferred = None
    if compiled.needs_inference:
        # tool(wf["x"], …) is core's implicit auto (core 009 decision 6).
        if fn is None:
            raise GridStepError(f"no tool named '{compiled.tool_id}'")
        inferred = "source" if compiled.input is None else "auto"
    bound_type = s.types[compiled.bound_to].__name__ if compiled.bound_to in s.types else None
    return compiled.operation(inferred, bound_type), compiled


def sync(s: Kernel, steps: List[Dict[str, Any]], tools: Dict[str, Any],
         load: Callable[[str], Any]) -> None:
    """Make the workflow's steps match *steps* (``[{name, formula}]``, in order).

    An unchanged formula is left alone, so its output stays current; a changed
    one is re-declared and core marks it — and what reads it — stale. A step
    the app no longer has is removed. *load(name)* is an old-syntax step's
    stored output, loaded as a table for core steps that read it.
    """
    from .operation_formula import is_canonical

    names = [str(step["name"]) for step in steps]
    # Renamed in the app (same id, new name): rename in core, which keeps the
    # step's output — a rename is not a recompute.
    for step in steps:
        sid, name = step.get("id"), str(step["name"])
        old = s.ids.get(sid) if sid else None
        if old and old != name and old in s.wf.steps and name not in s.wf.steps:
            try:
                s.wf.rename(old, name)
            except (KeyError, ValueError):
                continue
            for table in (s.formulas, s.operations, s.reads, s.uses, s.problems, s.loaded):
                if old in table:
                    table[name] = table.pop(old)
            for reads in s.reads.values():
                reads[:] = [name if r == old else r for r in reads]
    s.ids = {step.get("id"): str(step["name"]) for step in steps if step.get("id")}
    # Gone from the app: remove, last first, so readers go before what they read.
    for name in reversed(list(s.wf.steps)):
        if name not in names:
            try:
                s.wf.remove(name)
            except (KeyError, ValueError):
                continue
            for table in (s.formulas, s.operations, s.reads, s.uses, s.problems, s.loaded):
                table.pop(name, None)

    for step in steps:
        name = str(step["name"])
        formula = (step.get("formula") or "").strip()
        if formula and not formula.startswith("="):
            formula = "=" + formula
        if not formula or formula == "=":
            continue
        literal = _literal_value(formula)
        if literal is not _NOT_LITERAL:
            # A literal (`[1, 2]`, `{"x": 1}`, `7`) is a value; core takes it
            # as a step, declared here in its place among the others.
            if s.formulas.get(name) != formula or name not in s.wf.steps:
                s.wf[name] = literal
                s.formulas[name] = formula
                s.problems.pop(name, None)
            continue
        if not is_canonical(formula):
            # The app's older syntax: run on the old path. A core step that
            # reads it gets its stored output, as a table.
            ref = step.get("ref")
            if ref and s.loaded.get(name) != ref:
                data = load(name)
                if data is not None:
                    s.wf[name] = data
                    s.loaded[name] = ref
            continue
        if s.formulas.get(name) == formula and name in s.wf.steps:
            continue
        try:
            operation, compiled = _operation_for(s, formula, tools)
            earlier = names[:names.index(name)]
            for read in compiled.reads:
                if read not in earlier:
                    # The same words as a step run on its own (run_formula).
                    raise GridStepError(
                        f'no earlier step named "{read}" has output — check the name in '
                        f'wf["{read}"], or run that step first'
                    )
            s.wf[name] = grid.Operation.from_dict(operation, tools)
        except Exception as exc:
            s.problems[name] = str(exc)
            s.formulas.pop(name, None)
            continue
        s.formulas[name] = formula
        s.operations[name] = operation
        s.reads[name] = list(compiled.reads)
        s.uses[name] = list(compiled.resources)
        s.problems.pop(name, None)
        s.loaded.pop(name, None)


# ─────────────────────────────────────────────────────────────────────────────
# Running
# ─────────────────────────────────────────────────────────────────────────────

def _unrun_inputs(s: Kernel, name: str) -> List[str]:
    """The steps *name* reads, directly or not, that have never run here — in
    the order they were declared, so each runs after what it reads."""
    seen: set = set()

    def walk(step: str) -> None:
        for read in s.reads.get(step, []):
            if read not in seen:
                seen.add(read)
                walk(read)

    walk(name)
    return [step for step in s.wf.steps
            if step in seen and step in s.operations and s.wf.step(step).status == "staged"]


def summary(s: Kernel) -> Dict[str, dict]:
    """Every step's state, for the UI: status, why it's stale, problems."""
    out: Dict[str, dict] = {}
    for name, step in s.wf.steps.items():
        output = step.output
        meta = output.meta if output is not None else {}
        problems = list(step.problems)
        if name in s.problems:
            problems.insert(0, s.problems[name])
        out[name] = {
            "status": step.status,
            "stale_reason": meta.get("stale_reason"),
            "problems": problems,
        }
    for name, problem in s.problems.items():
        out.setdefault(name, {"status": "invalid", "stale_reason": None, "problems": [problem]})
    return out


def run_step(session_id: str, key: str, steps: List[Dict[str, Any]], name: str,
             declarations: Optional[Dict[str, Any]], load: Callable[[str], Any],
             live: Callable[[str, Any], Any], store: Callable[[Any], str]) -> Tuple[str, dict]:
    """Run step *name* of the session's workflow. Returns ``(output_ref, metrics)``.

    *store(frame)* saves an output and returns its ref; *live(name, decl)* is a
    resource's live object. Inputs that never ran here run first; their refs
    are reported under ``metrics["outputs"]`` so the UI can show them too.
    """
    s = _kernel_for(session_id, key, declarations or {})
    tools = _tools()
    with s.lock:
        sync(s, steps, tools, load)
        if name in s.problems:
            raise GridStepError(s.problems[name])
        if name not in s.operations:
            raise GridStepError(f"step '{name}' has no formula in core's syntax to run")
        step = s.wf.step(name)
        if step.problems:
            raise GridStepError("; ".join(step.problems))

        first = _unrun_inputs(s, name)
        needed = {res for step_name in first + [name] for res in s.uses.get(step_name, [])}
        try:
            objects = {res: live(res, s.declarations[res]) for res in needed}
        except Exception as exc:
            raise GridStepError(str(exc)) from exc

        outputs: Dict[str, str] = {}
        for step_name in first + [name]:
            try:
                s.wf.run(step_name, tools, resources=objects)
            except grid.ResourceNotLoaded as exc:
                raise GridStepError(str(exc)) from exc
            ran = s.wf.step(step_name)
            if _verb_of(s.operations[step_name]) == "source" and len(ran.output.failed):
                # One call, so one unit: if it failed there is no output to show.
                raise GridStepError(str(ran.output.failed.iloc[0].get("error", "the tool failed")))
            outputs[step_name] = store(ran.output.data)

        step = s.wf.step(name)
        frame = step.output.data
        metrics = {
            "rows": len(frame),
            "columns": [str(c) for c in frame.columns],
            **_engine_metrics(s.operations[name], step, step.output),
            "steps": summary(s),
        }
        if first:
            metrics["also_ran"] = first
            metrics["outputs"] = {k: v for k, v in outputs.items() if k != name}
        return outputs[name], metrics


def sync_only(session_id: str, key: str, steps: List[Dict[str, Any]],
              declarations: Optional[Dict[str, Any]], load: Callable[[str], Any],
              store: Optional[Callable[[Any], str]] = None) -> Dict[str, Any]:
    """Declare the app's steps without running anything.

    What the UI calls after an edit (which later steps are now stale?) and
    when a workflow becomes active (its kernel may come back from disk). With
    *store*, a step the kernel has an output for but the UI sent no ref for —
    a reopened workflow — has its output stored, and its ref returned, so the
    UI shows it without anything re-running.

    Returns ``{"steps": every step's state, "outputs": {name: ref}}``.
    """
    s = _kernel_for(session_id, key, declarations or {})
    with s.lock:
        sync(s, steps, _tools(), load)
        outputs: Dict[str, str] = {}
        if store is not None:
            for step in steps:
                name = str(step["name"])
                if step.get("ref") or name not in s.operations or name not in s.wf.steps:
                    continue
                ran = s.wf.step(name)
                if ran.status in ("completed", "stale") and ran.output is not None:
                    outputs[name] = store(ran.output.data)
        return {"steps": summary(s), "outputs": outputs}
