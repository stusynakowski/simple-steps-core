"""Declaring a step: checks, warnings, verb inference and staging (the plan).

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from typing import Any
from typing import Callable
import inspect
import pandas as pd
import typing

from .output import VALUE_COLUMN
from .problems import Problem, classified, coded


def _expectation(operation: "Operation") -> dict:
    """The settings of a step's ``mod.expect(…)`` layers, merged."""
    out: dict = {}
    for m in operation.modifiers:
        if m.kind == "expect":
            out.update(m.settings)
    return out


def _expected_columns(expect: dict) -> tuple[list, dict]:
    """(names, {name: type}) from an expectation's ``columns``."""
    columns = expect.get("columns")
    if isinstance(columns, dict):
        return list(columns), {k: _TYPE_NAMES.get(v, v) for k, v in columns.items()}
    return list(columns or []), {}


def _rows_plan(kind, rule, expected, n_in, expect, label, upstream=None) -> dict:
    """The row axis of a plan (008 C9): exact, stated, bounded or unknown."""
    if any(k in expect for k in ("rows", "min_rows", "max_rows")):
        plan = {"certainty": "stated"}
        for key in ("rows", "min_rows", "max_rows"):
            if key in expect:
                plan[{"rows": "count", "min_rows": "min", "max_rows": "max"}[key]] = expect[key]
        return plan
    if expected is not None:
        return {"certainty": "exact", "count": expected}
    if rule == "at_most" and n_in is not None:
        return {"certainty": "bounded", "min": 0, "max": n_in,
                "because": f"{kind} keeps at most the {n_in} rows it reads",
                "resolve": [f"run {label}"]}
    if rule == "per_group" and n_in is not None:
        return {"certainty": "bounded", "min": 1 if n_in else 0, "max": n_in,
                "because": "one row per group; the groups come from the data",
                "resolve": [f"run {label}"]}
    because = {
        "source": f"{label} is a source that hasn't run; its rows come from its data",
        "expand": f"expand: how many items {label} returns per row is only known by running",
        "table": f"table: {label} returns a new grid; its rows come from running it",
    }.get(kind, f"its input {upstream!r} doesn't know its row count yet"
                if upstream else "its input's row count isn't known yet")
    resolve = [f"run {label}" if kind in ("source", "expand", "table")
               else (f"run {upstream!r}" if upstream else "run the steps before it")]
    if kind == "expand":
        resolve.append("annotate a fixed length: -> tuple[T, T]")
    resolve.append("state it on the step: mod.expect(rows=…)")
    return {"certainty": "unknown", "because": because, "resolve": resolve}


def _columns_plan(kind, names, columns_open, expect, label, upstream) -> dict:
    """The column axis of a plan: exact, stated, bounded (these + more) or unknown."""
    if expect.get("columns") is not None:
        return {"certainty": "stated", "names": list(names),
                "more": bool(expect.get("more_columns"))}
    if not columns_open:
        return {"certainty": "exact", "names": list(names)}
    if kind in ("source", "table"):
        because = f"{label} returns a DataFrame with no declared columns"
        resolve = [f"run {label}",
                   "annotate the return: -> Annotated[pd.DataFrame, YourTypedDict]",
                   "state them on the step: mod.expect(columns=[…], more_columns=True)"]
    else:
        because = f"its input {upstream!r} doesn't know all its columns yet"
        resolve = [f"run {upstream!r}", f"declare {upstream!r}'s columns"]
    return {"certainty": "bounded" if names else "unknown", "names": list(names),
            "more": True, "because": because, "resolve": resolve}


def _declared_fits(column_type: Any, annotation: Any) -> bool | None:
    """Does a column declared as *column_type* fit a parameter? None when unsure."""
    _, base = _optional_parts(annotation)
    origin = typing.get_origin(base) or base
    col_origin = typing.get_origin(column_type) or column_type
    if not isinstance(origin, type) or origin is object or not isinstance(col_origin, type):
        return None
    if origin is float and col_origin is int:
        return True                                   # an int fits a float
    return issubclass(col_origin, origin)


def _output_mismatch(operation: "Operation", data: pd.DataFrame) -> str | None:
    """How a real output breaks what its step declared or stated, or None.

    008 C5/C9: a source's declared schema and ``mod.expect`` are promises the
    plan was built on — when the data breaks one, the step fails, never
    silently.
    """
    expect = _expectation(operation)
    verb = operation.shape_verb
    if verb is not None and verb.kind in ("source", "table"):
        fn = operation.fn
        schema = _declared_schema(fn) if fn is not None else None
        if schema is not None and list(schema) != list(data.columns):
            return (f"{operation.tool} declares columns {', '.join(schema)}; "
                    f"it returned {', '.join(map(str, data.columns)) or 'none'}")
    n = len(data)
    if isinstance(expect.get("rows"), int) and n != expect["rows"]:
        return f"expected {expect['rows']} rows, got {n}"
    if isinstance(expect.get("min_rows"), int) and n < expect["min_rows"]:
        return f"expected at least {expect['min_rows']} rows, got {n}"
    if isinstance(expect.get("max_rows"), int) and n > expect["max_rows"]:
        return f"expected at most {expect['max_rows']} rows, got {n}"
    if expect.get("columns") is not None:
        names, _ = _expected_columns(expect)
        have = list(data.columns)
        missing = [c for c in names if c not in have]
        extra = [c for c in have if c not in names]
        if missing or (extra and not expect.get("more_columns")):
            return (f"expected columns {', '.join(names)}"
                    f"{' (and maybe more)' if expect.get('more_columns') else ''}; "
                    f"got {', '.join(map(str, have)) or 'none'}")
    return None


def _plan_markers(plan: dict, step_id: str) -> list[dict]:
    """The known unknowns of a plan, as things to draw (009 §4).

    A trailing marker row for a row count that isn't exact, and a trailing
    marker column for columns that may be more than the known ones — each
    with the plan's ``because`` and ``resolve``.
    """
    markers = []
    rows_ = plan.get("rows") or {}
    certainty = rows_.get("certainty")
    if certainty == "unknown":
        markers.append({"kind": "rows", "certainty": "unknown",
                        "text": f"‹rows unknown — {rows_.get('because', '')}›",
                        "because": rows_.get("because"), "resolve": rows_.get("resolve", [])})
    elif certainty == "bounded":
        span = f"{rows_.get('min', 0)}–{rows_.get('max', '?')}"
        markers.append({"kind": "rows", "certainty": "bounded",
                        "text": f"‹{span} rows — {rows_.get('because', '')}›",
                        "because": rows_.get("because"), "resolve": rows_.get("resolve", [])})
    elif certainty == "stated" and "count" not in rows_:
        span = f"{rows_.get('min', 0)}–{rows_.get('max', '?')}"
        markers.append({"kind": "rows", "certainty": "stated",
                        "text": f"‹{span} rows (stated)›", "because": "stated with mod.expect",
                        "resolve": []})
    columns = plan.get("columns") or {}
    if columns.get("more") or columns.get("certainty") in ("bounded", "unknown"):
        known = columns.get("names") or []
        markers.append({"kind": "columns", "certainty": columns.get("certainty"),
                        "text": "‹+ maybe more columns›" if known else "‹columns unknown›",
                        "because": columns.get("because", "stated as some of the columns"),
                        "resolve": columns.get("resolve", [])})
    return markers


#: Verbs whose output rows are their input's rows, one to one (or a subset):
#: they can tell which output rows a changed input row affects (010 C25).
ROW_ALIGNED = frozenset({"map", "group", "filter", "select", "drop", "rename",
                         "sort", "slice", "distinct", "widen"})


def _worst(states: set, stale: Any = False) -> str:
    """The worst of some cell states (``stale`` shown over known)."""
    order = {s_: i for i, s_ in enumerate(STATES)}
    worst = max(states, key=lambda s_: order.get(s_, 0)) if states else "known"
    return "stale" if worst == "known" and stale else worst


def _is_tool_verb(kind: Any, op_: Any) -> bool:
    """Does this verb apply a real tool to each row (rather than copy cells)?"""
    if kind in ("map", "group", "filter", "expand"):
        return not is_identity(op_.fn or BUILTIN_TOOLS.get(op_.tool))
    return False


def _source_column(op_: Any, column: Any) -> Any:
    """The input column a no-tool step copied *column* from (a rename's old name)."""
    verb = op_.shape_verb
    if verb is not None and verb.kind == "rename" and isinstance(verb.settings.get("columns"), dict):
        for old, new in verb.settings["columns"].items():
            if new == column:
                return old
    return column


# ─────────────────────────────────────────────────────────────────────────
# Declaring: a Step is born staged
# ─────────────────────────────────────────────────────────────────────────
# Declaring a step *is* staging (docs/shape-algebra.md §7). A Step therefore
# always has both halves from the moment it exists: the Operation (what to run)
# and an Output (the slot). Running does not create the Output — it replaces it
# with the real one.
#
# Staging sharpens in three levels, and which one you get depends only on what
# the upstream already holds:
#   shape        always      — read off the outermost shape verb
#   cardinality  upstream has an Output      — "4 cells"
#   addresses    upstream has an index       — a staged ledger, one row per cell
def check(operation: Operation, workflow: "Workflow | None" = None,
          step_id: str | None = None) -> tuple[str, ...]:
    """Everything wrong with *operation* that is knowable without running it.

    Returns the problems, empty when there are none. This never raises: a
    reactive editor has to be able to *show* a bad step while you are still
    typing it, so validity is a property of the Step, not a precondition for
    building one.
    """
    if _is_auto(operation) and len(operation.shape_verbs) == 1:
        # 008 N: check the step as the verb it would be now.
        operation, _, _ = _provisional(operation, workflow)
    problems: list[str] = []

    # 0. a workflow with a catalog may only use what the catalog has: its tool,
    #    modifiers, combines, tools given as settings, and resource types.
    catalog_ = getattr(workflow, "catalog", None)
    if catalog_ is not None:
        problems.extend(catalog_.problems(operation, workflow))

    # 1. the tool has to exist — unless this is a combine verb, which names no
    #    tool (join/stack/zip apply none; their id is the verb itself). A bound
    #    tool comes from its resource's declared type, never from a tool table.
    if operation.bound_to is not None:
        fn = operation.fn
        if fn is None:
            problems.append(_bound_problem(operation, workflow))
    else:
        fn = operation.fn \
            or BUILTIN_TOOLS.get(operation.tool)
        outside = any(getattr(p, "code", None) in ("not_in_catalog", "different_function")
                      for p in problems)
        if fn is None and not is_combine(operation) and not outside:
            problems.append(f"unknown tool {operation.tool!r}")

    coded(problems, "unknown_tool")

    # 1b. every resource argument has to name a declared resource. Whether it
    #     is *loaded* is a run-time question: a workflow is portable, its
    #     resources are environment.
    if workflow is not None:
        for value in operation.arguments.values():
            if isinstance(value, ResRef) and value.name not in workflow.resources:
                problems.append(_no_resource(value.name, workflow))

    coded(problems, "unknown_resource")

    # 2. every modifier kind has to be in the vocabulary
    for modifier in operation.modifiers:
        if modifier.kind not in MODIFIERS:
            problems.append(f"unknown modifier {modifier.kind!r}")

    coded(problems, "unknown_modifier")

    # 2b. a modifier's own parameters have to be ones its verb accepts. A typo
    #     here used to pass declaration and surface at run time as a TypeError
    #     from `map_()`, which is the one validation gap `arguments` did not
    #     have. `sweep` accepts anything, because its parameters are the data.
    for modifier in operation.modifiers:
        if modifier.kind in NAMED_VERBS and "name" in modifier.settings:
            # Owner, 2026-10-26: mod.name is the one way to name an output.
            problems.append(
                f"{modifier.kind}'s name= is retired: name the output with "
                f"mod.name({_src(modifier.settings['name'])}) after the verb")
        entry = MODIFIERS.get(modifier.kind)
        if entry is None or entry.accepts is None:
            continue
        if modifier.kind == "group" and "by" in modifier.settings:
            # Owner, 2026-10-27: group's key is what its own tool returns.
            by = modifier.settings["by"]
            if isinstance(by, str):
                problems.append(
                    f"{by!r} is already a column: collapse(by={by!r}) groups by "
                    "it. group labels rows with a key its own tool computes")
            else:
                problems.append(
                    "group's key is what the step's own tool returns: write "
                    "<key tool>[mod.group()](…), not group(by=…)")
        unknown = [name for name in modifier.settings if name not in entry.accepts
                   and not (modifier.kind == "group" and name == "by")
                   and not (modifier.kind in NAMED_VERBS and name == "name")]
        if unknown:
            problems.append(
                f"{modifier.kind} takes no parameter "
                f"{', '.join(map(repr, unknown))}; it accepts "
                f"{', '.join(sorted(entry.accepts))}"
            )

    coded(problems, "unknown_setting")

    # 2b'. a naming modifier names a column a verb writes (G12): a name, not
    #      empty, not the row number, on a verb that writes a value column.
    for modifier in operation.modifiers:
        if modifier.kind != "name":
            continue
        to = modifier.settings.get("to")
        verb_ = operation.shape_verbs[-1] if operation.shape_verbs else None
        if not isinstance(to, str) or not to.strip():
            problems.append(f"mod.name needs a column name, got {to!r}")
        elif to == ROW_ID:
            problems.append(f"{ROW_ID!r} is the row id; name the column something else")
        elif verb_ is not None and verb_.kind not in NAMED_VERBS and verb_.kind != "auto":
            problems.append(
                f"{verb_.kind} writes no new values, so there is nothing to name; "
                "to rename a column, use mod.rename in a later step")
    coded(problems, "bad_name")

    # 2c. and they have to be the right *type*. `sweep` is why this matters:
    #     a swept parameter called `name` lands in the verb's own `name=`, and
    #     a list there is not a usable column name.
    for modifier in operation.modifiers:
        overrides = PARAM_TYPES_BY_VERB.get(modifier.kind, {})
        for parameter, expected in {**PARAM_TYPES, **overrides}.items():
            if parameter not in modifier.settings:
                continue
            value = modifier.settings[parameter]
            if isinstance(value, StepRef):
                # 008 C1: checked against the value once the step holds one;
                # until then the reference is resolved at run.
                known = workflow._value_if_known(value) if workflow else _UNKNOWN
                if known is _UNKNOWN:
                    continue
                if isinstance(known, expected) and (
                        bool in expected or not isinstance(known, bool)):
                    continue
                problems.append(
                    f"{modifier.kind}'s {parameter}= reads {value.id!r}, which "
                    f"holds {type(known).__name__}; it must be "
                    f"{' or '.join(t.__name__ for t in expected)}")
                continue
            if _is_tool_value(value) and parameter in TOOL_SETTINGS.get(modifier.kind, ()):
                continue                           # 008 C2: a tool in a setting
            # bool is a subclass of int, so it must not satisfy an int-typed
            # parameter — unless bool is what was asked for.
            if isinstance(value, expected) and (
                    bool in expected or not isinstance(value, bool)):
                continue
            names = " or ".join(t.__name__ for t in expected)
            extra = ""
            if modifier.kind == "sweep" and parameter in ("name", "retries"):
                extra = (f". A swept parameter cannot be called {parameter!r} — "
                         f"it collides with the verb's own")
            problems.append(
                f"{modifier.kind}'s {parameter}= must be {names}, got "
                f"{type(value).__name__}{extra}"
            )

    coded(problems, "wrong_setting_type")

    # 2d. a verb whose literal setting is mandatory must carry it at
    #     declaration, not discover it missing at run. select/drop/sort/rename
    #     each raise from their verb without their one required setting; catch
    #     it here instead, like every other declaration check.
    for modifier in operation.modifiers:
        for required in _required_settings(modifier.kind):
            if not modifier.settings.get(required) and modifier.settings.get(required) != 0:
                problems.append(
                    f"{modifier.kind} needs {required}= — it has no default, "
                    f"so a step without it cannot run"
                )

    # 2d'. select chooses rows, columns or both — it needs at least one.
    for modifier in operation.modifiers:
        if modifier.kind == "select" and not modifier.settings.get("columns") \
                and modifier.settings.get("rows") is None:
            problems.append("select needs columns= or rows= — what to keep")

    # 2d''. mod.expect states something, and never what core knows is false
    #       (008 C9.4) — "filter gives at most 3 rows; expect(rows=10) can't hold".
    expect = _expectation(operation)
    if any(m.kind == "expect" for m in operation.modifiers):
        if not any(k in expect for k in ("rows", "min_rows", "max_rows", "columns")):
            problems.append("expect needs rows=, min_rows=, max_rows= or columns= "
                            "— what the step will produce")
        verb_ = operation.shape_verb
        index = workflow._known_index(operation) if workflow is not None else None
        n = None if index is None else len(index)
        rule = ROWS_RULE.get(verb_.kind) if verb_ is not None else None
        stated = expect.get("rows")
        if isinstance(stated, int) and verb_ is not None:
            if rule == "one" and not verb_.settings.get("by") and stated != 1:
                problems.append(f"{verb_.kind} gives exactly 1 row; "
                                f"expect(rows={stated}) can't hold")
            elif n is not None and rule == "same" and stated != n:
                problems.append(f"{verb_.kind} gives exactly {n} rows; "
                                f"expect(rows={stated}) can't hold")
            elif n is not None and rule == "at_most" and stated > n:
                problems.append(f"{verb_.kind} gives at most {n} rows; "
                                f"expect(rows={stated}) can't hold")

    for i, p in enumerate(problems):
        problems[i] = classified(p, (("gives exactly", "contradicts_verb"),
                                     ("gives at most", "contradicts_verb")),
                                 "missing_setting")

    # 2e. a combine (join/stack/zip) reads several grids and merges on literal
    #     config; it has no tool, so its only extra declaration checks are its
    #     arity and, for a join, its key.
    if is_combine(operation):
        spec = COMBINE[operation.tool]
        if len(operation.grids) < spec["min_inputs"]:
            problems.append(
                f"{operation.tool} needs at least {spec['min_inputs']} grids "
                f"to combine, got {len(operation.grids)}"
            )
        if operation.tool == "join" and not operation.arguments.get("on"):
            problems.append("join needs on= — the key column(s) to merge on")
        if operation.tool == "zip" and workflow is not None:
            # 010 C22: a column both grids have would keep one silently.
            clash = _zip_clash([(str(g), workflow._predicted_of(str(g)))
                                for g in operation.grids])
            if clash:
                problems.append(clash)

    # The references this operation reads: the grid input(s), plus any argument
    # bound to a step. All are validated the same way.
    references: list[tuple[str, Any]] = []
    grids = operation.grids
    for i, g in enumerate(grids):
        references.append(("input" if len(grids) <= 1 else f"input {i + 1}", g))
    references += [(f"argument {name!r}", value)
                   for name, value in operation.arguments.items()
                   if isinstance(value, StepRef)]
    references += [(f"{m.kind}'s {name}=", value)
                   for m in operation.modifiers
                   for name, value in m.settings.items()
                   if isinstance(value, StepRef)]

    coded(problems, "bad_combine")

    # 3. a reference has to have been read from *this* workflow. A step is
    #    named by its id, so a ref borrowed from another workflow would resolve
    #    against a same-named local step — silently running the wrong data when
    #    both happen to have one. A StepRef knows which workflow it came from.
    for label, ref in references:
        if workflow is None or not isinstance(ref, StepRef):
            continue
        if ref.workflow is None or ref.workflow is workflow:
            continue
        name = ref.id
        problems.append(
            f"{label} {name!r} reads a different Workflow. A step is named by "
            f"its id, so this would resolve to *this* workflow's {name!r} — not "
            f"the step you pointed at. Read it from this workflow."
        )

    coded(problems, "foreign_reference")

    # 4. a reference has to name an existing, valid, non-circular step
    for label, ref in references:
        if workflow is None:
            continue
        name = str(ref)
        if name == step_id:
            problems.append(f"{label} is itself ({name!r})")
        elif name not in workflow.steps:
            problems.append(f"{label} {name!r}, which is not an earlier step")
        elif not workflow.steps[name].valid:
            root, why = workflow.root_cause(name)
            problems.append(f"{label} {name!r}, which is invalid "
                            f"(root cause: {root}: {why})")
        elif step_id is not None and step_id in workflow._upstream_ids(name):
            problems.append(f"{label} {name!r} is circular")
        elif (step_id is not None and step_id in workflow.steps
              and list(workflow.steps).index(name) > list(workflow.steps).index(step_id)):
            # 008 C10: re-declaring a step keeps its position, so it could
            # quietly start reading a step defined after it.
            problems.append(f"{label} {name!r} comes after {step_id!r}; a step "
                            "can only read earlier steps")

    for i, p in enumerate(problems):
        problems[i] = classified(p, (("is itself", "self_reference"),
                                     ("which is invalid", "invalid_input"),
                                     ("which is not an earlier step", "missing_step"),
                                     ("is circular", "circular"),
                                     ("comes after", "later_step")),
                                 "missing_step")

    # 5. at most one shape verb per step (§11). Two shape changes inside one
    #    step make an intermediate grid with no cell address, so a unit that
    #    fails there cannot be inspected or re-run.
    verbs = operation.shape_verbs
    if len(verbs) > 1:
        names = ", ".join(v.kind for v in verbs)
        problems.append(
            f"{len(verbs)} shape verbs in one step ({names}); at most one is "
            "allowed. Split them into separate steps so every shape change "
            "keeps a cell address you can re-drive."
        )

    coded(problems, "two_shape_verbs")

    # 6. the column verbs apply no tool (source may: it can compute its grid)
    for kind in ("select", "drop", "widen", "slice", "rename",
                 "sort", "distinct"):
        if any(m.kind == kind for m in operation.modifiers) and not is_identity(fn):
            problems.append(f"{kind} applies no tool; use map to compute")

    coded(problems, "verb_takes_no_tool")

    # 6b. select and drop must name columns the input will actually have
    verb = operation.shape_verb
    # Deliberately not `widen`: its columns are the record's fields, which do
    # not exist upstream — that is the whole point of the verb.
    if (verb is not None and verb.kind in ("select", "drop", "rename", "sort",
                                           "distinct")
            and workflow is not None
            and (verb.settings.get("columns") or verb.settings.get("by"))
            and not (isinstance(verb.settings.get("columns"), (list, tuple))
                     and ROW_ID in verb.settings["columns"] and verb.kind == "select")
            and not any(isinstance(verb.settings.get(k), StepRef)
                        or (verb.kind == "select" and isinstance(verb.settings.get(k), dict))
                        or _is_tool_value(verb.settings.get(k))
                        for k in ("columns", "by"))
            # 008 K1: while the input's columns are not known yet (a tool-backed
            # source that has not run, or anything downstream of one), a name
            # missing from the prediction may still arrive. Defer, don't fail;
            # the step is re-checked when its input runs.
            and not workflow._columns_open(operation)):
        available = workflow._known_columns(operation)
        by = verb.settings.get("by")
        named = list(verb.settings.get("columns") or
                     ([by] if isinstance(by, str) else by) or ())
        if available:
            missing = [c for c in named if c not in available]
            if missing:
                problems.append(
                    f"{verb.kind} names {', '.join(map(repr, missing))}, which "
                    f"the input does not have (it has {', '.join(map(str, available))})"
                )

    # 6b'. collapse(by=…) groups by a column the input must have (010 C23).
    if (verb is not None and verb.kind == "collapse" and workflow is not None
            and isinstance(verb.settings.get("by"), str)
            and not workflow._columns_open(operation)):
        available = workflow._known_columns(operation)
        by = verb.settings["by"]
        if available and by not in available:
            upstream_name = str(operation.input) if operation.input is not None else "the input"
            problems.append(
                f"collapse groups by {by!r}, which {upstream_name!r} does not have "
                f"(it has {', '.join(map(str, available))})")

    coded(problems, "missing_column")

    # 6c. a payload column must not silently replace an input column (008
    #     C13). Checked against the columns predicted *present*, which is sound
    #     even while the full set is still open. Only an explicit `name=` is
    #     refused: the default payload overwriting the previous step's default
    #     payload is how `map` over `map` chains, so that is a warning instead
    #     (see `warn`).
    # group carries its input's columns and adds its key (owner, 2026-10-27),
    # so a key named like an input column would replace it.
    if (verb is not None and verb.kind == "group"
            and workflow is not None and not verb.settings.get("replace")):
        written = verb.settings.get("name", DEFAULT_PAYLOAD["group"])
        upstream_name = str(operation.input) if operation.input is not None else "the input"
        if written in workflow._known_columns(operation):
            problems.append(
                f"group's key {written!r} would replace the {written!r} column "
                f"{upstream_name!r} already has; name the key (name=…), or say "
                "replace=True")

    coded(problems, "column_clash")

    # 6e. a tool in a setting (008 C2): only where the verb takes one, and it
    #     must be registered, so the saved `{"$tool": id}` resolves on load.
    for modifier in operation.modifiers:
        for name, value in modifier.settings.items():
            if not _is_tool_value(value) or isinstance(value, StepRef):
                continue
            if name not in TOOL_SETTINGS.get(modifier.kind, ()):
                problems.append(f"{modifier.kind}'s {name}= doesn't take a tool")
            elif isinstance(value, ToolRef) and value.id not in BUILTIN_TOOLS \
                    and not (getattr(workflow, "catalog", None) is not None
                             and value.id in workflow.catalog.functions):
                problems.append(f"{modifier.kind}'s {name}= names tool "
                                f"{value.id!r}, which is not registered")

    coded(problems, "bad_tool_setting")

    # 6c'. a reference argument arrives whole, shaped by the parameter's type
    #      (008 C1) — a shape that can't convert is refused here, not on every row.
    if fn is not None and workflow is not None:
        try:
            annotations = {k: p.annotation for k, p in _signature(fn).parameters.items()}
        except (TypeError, ValueError):
            annotations = {}
        paired = _paired_arguments(operation, workflow)
        for name, value in operation.arguments.items():
            if not isinstance(value, StepRef) or name not in annotations or name in paired:
                continue
            # 008 C7: a selection's shape is known from how it is written; a
            # whole step's only once it holds data.
            kind = _selection_kind(value)
            step = workflow.steps.get(value.id)
            if kind is None and (step is None or step.output.meta.get("staged")):
                continue
            if kind is None:
                kind = _shape_kind(step.output.data)
            problem = _shape_problem(kind, annotations[name], name, value.id)
            if problem:
                problems.append(problem)

    coded(problems, "wrong_shape")

    # 6f. a selection is checked against what is already known about its step
    #     (008 C7.7, C7.11): a column name it lacks, a position past the end.
    if workflow is not None:
        selections = [(f"argument {n!r}", v) for n, v in operation.arguments.items()
                      if isinstance(v, StepRef) and v.selected]
        if verb is not None and verb.kind == "select" and operation.input is not None \
                and (isinstance(verb.settings.get("columns"), dict)
                     or verb.settings.get("rows") is not None):
            selections.append(("select", StepRef(
                str(operation.input), rows=verb.settings.get("rows"),
                columns=verb.settings.get("columns"))))
        for label, ref in selections:
            step = workflow.steps.get(ref.id)
            if step is None or not step.valid:
                continue                      # reported as a reference problem
            if step.output.meta.get("staged"):
                if columns_unknown(step.output) or ref.columns is None:
                    continue
                frame = pd.DataFrame(columns=predicted_columns(step.output))
                row_sel = None                # row count not known yet
            else:
                frame, row_sel = step.output.data, ref.rows
            try:
                _apply_selection(frame, row_sel, ref.columns, ref.id)
            except SelectionError as exc:
                problems.append(f"{label}: {exc}")

    coded(problems, "bad_selection")

    # 6d. a bound value is a literal or a reference — anything else is refused
    #     here, not when the workflow is saved (008 C11).
    for name, value in operation.arguments.items():
        if isinstance(value, (StepRef, ResRef, ToolRef, Tool)):
            continue
        problem = _literal_problem(value)
        if problem:
            problems.append(f"{name}: {problem}")
    for modifier in operation.modifiers:
        for name, value in modifier.settings.items():
            if isinstance(value, (StepRef, ResRef, ToolRef, Tool)) or callable(value):
                continue                   # tools in settings: C2's check
            problem = _literal_problem(value)
            if problem:
                problems.append(f"{modifier.kind}'s {name}=: {problem}")

    coded(problems, "bad_argument")

    # 7. bound literals have to be parameters the tool accepts — the reactive
    #    argument check, done against the signature rather than at run time.
    if fn is not None and operation.arguments:
        try:
            parameters = inspect.signature(fn).parameters
        except (TypeError, ValueError):          # builtins have no signature
            parameters = {}
        if parameters and not any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
        ):
            for name in operation.arguments:
                if name not in parameters:
                    problems.append(
                        f"{operation.tool}() takes no argument {name!r}; "
                        f"it accepts {', '.join(list(parameters)[1:]) or '(none)'}"
                    )
    coded(problems, "unknown_argument")

    # 8. the values the tool requires have to exist as columns upstream.
    #    This is only possible because a tool declares what it needs by name —
    #    with a `def score(row)` convention there is nothing to check against.
    if fn is not None and workflow is not None and not problems:
        problems.extend(_missing_columns(operation, fn, workflow))

    coded(problems, "missing_column")

    # 9. declared types have to match what is actually there — the bound
    #    literals always, the upstream's dtypes once it has run. This is what
    #    the annotations are *for*; without it they would be documentation.
    if fn is not None and not problems:
        problems.extend(_type_mismatches(operation, fn, workflow))

    coded(problems, "wrong_type")
    return tuple(p.at(step_id) for p in problems)


def warn(operation: Operation, workflow: "Workflow | None" = None,
         step_id: str | None = None) -> tuple[str, ...]:
    """Non-blocking column expectations, before the upstream has run (005 C).

    The hard column check (:func:`_missing_columns`) only fires once the upstream
    is real, so a step declared ahead of its inputs says nothing. But staging
    already *predicts* the upstream's columns, so we can surface what a step
    **expects** without blocking it: a column predicted present is 🟡
    unconfirmed, one predicted absent is 🟠 likely-missing. Both clear (or harden
    into a problem) when the upstream runs. Warnings never stop a run.
    """
    if workflow is None or operation.input is None:
        return _warnings([], step_id)
    if _is_auto(operation) and len(operation.shape_verbs) == 1:
        operation, _, _ = _provisional(operation, workflow)
    verb = operation.shape_verb
    if verb is None or verb.kind in ("source", "sweep"):
        return _warnings([], step_id)
    notes: list[str] = []
    # 008 C12: a keyword that matches no named parameter lands in **kwargs,
    # unchecked — a typo there would otherwise pass silently.
    tool_fn = operation.fn
    open_ = _open_keywords(tool_fn) if tool_fn is not None else None
    if open_:
        named = {p for p in inspect.signature(tool_fn).parameters} - {open_}
        for name in operation.arguments:
            if name not in named:
                notes.append(f"{name}= isn't a named parameter of "
                             f"{operation.tool}; it lands in **{open_} unchecked")
    # 008 C7: a row position reads a different row next run when the step it
    # reads doesn't fix its row order.
    for ref in [*operation.arguments.values(),
                *(StepRef(str(operation.input), rows=verb.settings.get("rows"))
                  if verb.kind == "select" and verb.settings.get("rows") is not None
                  else None,)]:
        if not isinstance(ref, StepRef) or not isinstance(ref.rows, dict):
            continue                        # ids follow their rows; only ranges are positions
        read = workflow.steps.get(ref.id)
        made_by = read.operation.shape_verb.kind if read and read.operation.shape_verb else None
        if made_by in ("filter", "expand", "group", "distinct", "collapse"):
            notes.append(f"rows {ref.rows!r} of {ref.id!r} are positions, and "
                         f"{made_by} doesn't fix row order: they may be "
                         "different rows next run")
    # 008 N2: an argument bound on the step beats a same-named input column —
    # allowed, since pinning a value can be deliberate, but never silent.
    upstream_columns = workflow._known_columns(operation)
    for name, value in operation.arguments.items():
        if name in upstream_columns:
            shown = (f"wf[{value.id!r}]" if isinstance(value, StepRef)
                     else repr(value))
            notes.append(
                f"{name}={shown} overrides the {name!r} column of "
                f"{str(operation.input)!r} for every row; drop the argument "
                f"to use the column")
    if (verb.kind in () and "name" not in verb.settings    # 008 C13: none carry
            and not verb.settings.get("replace")):
        written = DEFAULT_PAYLOAD.get(verb.kind)
        if written in workflow._known_columns(operation):
            # 008 C13, the default-name case: allowed, but said out loud.
            notes.append(
                f"{verb.kind} writes {written!r} over the {written!r} column "
                f"{str(operation.input)!r} already has; name the output "
                f"(name=…) to keep both, or say replace=True to silence this")
    upstream = workflow.steps.get(str(operation.input))
    # G13: an input that was edited but hasn't re-run still shows its old
    # output, which this step may run on; say now if its new formula won't
    # give a column this step needs. Only when the new columns are known.
    if upstream is not None and upstream.output.meta.get("edited"):
        planned = (upstream.output.meta.get("next_plan") or {}).get("columns") or {}
        if planned.get("certainty") in ("exact", "stated") and not planned.get("more"):
            names = list(planned.get("names") or [])
            needed = _required_columns(operation, verb)
            gone = [r for r in needed if r not in set(names) | set(operation.arguments)]
            if gone:
                up_ = str(operation.input)
                notes.append(
                    f"needs {', '.join(map(repr, gone))} from {up_!r}, which its "
                    f"edited formula won't produce (it will give "
                    f"{', '.join(names) or 'no columns'}); this fails once "
                    f"{up_!r} re-runs")
    # Only predict while the upstream is staged; once it runs, `check` is exact.
    if upstream is None or not upstream.output.meta.get("staged"):
        return _warnings(notes, step_id)
    fn = operation.fn \
        or BUILTIN_TOOLS.get(operation.tool)
    if isinstance(fn, Tool):
        fn = fn.fn
    if fn is None:
        return _warnings(notes, step_id)
    try:
        parameters = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return _warnings(notes, step_id)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return _warnings(notes, step_id)                       # takes the whole row; nothing to expect
    if verb.kind in ("collapse", "table"):
        parameters = parameters[1:]     # the verb supplies the accumulator / the grid
    predicted = set(rows(upstream.output).columns) | set(operation.arguments)
    required = [p.name for p in parameters
                if p.default is inspect.Parameter.empty
                and p.kind is not inspect.Parameter.VAR_POSITIONAL]
    up = str(operation.input)
    shown = ", ".join(sorted(predicted)) or "no columns"
    warnings: list[str] = []
    absent = [r for r in required if r not in predicted]
    present = [r for r in required if r in predicted]
    if absent:
        warnings.append(
            f"expects {', '.join(map(repr, absent))} from {up!r}, which is "
            f"predicted to produce ({shown}) — likely missing once it runs"
        )
    if present:
        warnings.append(
            f"expects {', '.join(map(repr, present))} from {up!r}, "
            f"unconfirmed until it runs"
        )
    return _warnings(notes + warnings, step_id)



#: The verbs that call their tool once per row, so a column given as an
#: argument can be paired with the input row by row (K19).
_ROW_BY_ROW = frozenset({"map", "filter", "expand", "group"})


def _paired_arguments(operation: Operation, workflow: "Workflow | None") -> dict:
    """The arguments that pair with the input row by row, name → reference
    (K19, docs/design/row-ids.md §4): a column, given to a parameter that
    takes one value (or is untyped), under a verb that runs once per row."""
    if workflow is None:
        return {}
    op_ = operation
    if _is_auto(op_) and len(op_.shape_verbs) == 1:
        op_, _, _ = _provisional(op_, workflow)
    verb = op_.shape_verb
    if verb is None or verb.kind not in _ROW_BY_ROW:
        return {}
    fn = op_.fn or BUILTIN_TOOLS.get(op_.tool)
    if isinstance(fn, Tool):
        fn = fn.fn
    try:
        annotations = {k: p.annotation for k, p in _signature(fn).parameters.items()}
    except (TypeError, ValueError):
        return {}
    return {name: value for name, value in op_.arguments.items()
            if isinstance(value, StepRef) and _selection_kind(value) == "column"
            and name in annotations and _wants(annotations[name]) in (None, "scalar")}


def _required_columns(operation: Operation, verb: Any) -> list[str]:
    """The columns a row-wise step's tool needs from its input: parameters with
    no default and no bound argument. Empty when it can't tell."""
    fn = operation.fn or BUILTIN_TOOLS.get(operation.tool)
    if isinstance(fn, Tool):
        fn = fn.fn
    if fn is None:
        return []
    try:
        parameters = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return []
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return []
    if verb.kind in ("collapse", "table"):
        parameters = parameters[1:]
    return [p.name for p in parameters
            if p.default is inspect.Parameter.empty
            and p.kind is not inspect.Parameter.VAR_POSITIONAL
            and p.name not in operation.arguments]


#: How a warning's message says which kind it is.
_WARNING_KINDS = (
    ("edited formula won't produce", "column_will_be_missing"),
    ("isn't a named parameter", "unchecked_argument"),
    ("are positions", "rows_by_position"),
    ("column of", "argument_overrides_column"),
    ("writes", "output_overwrites_column"),
    ("likely missing", "likely_missing_column"),
    ("unconfirmed until it runs", "unconfirmed_column"),
)


def _warnings(notes: list[str], step_id: str | None = None) -> tuple[Problem, ...]:
    """*notes* as warnings on *step_id*, each with its code."""
    return tuple(classified(n, _WARNING_KINDS, "problem", severity="warning").at(step_id)
                 for n in notes)

def _resource_types_of(workflow: "Workflow | None") -> list[type]:
    """The resource types a workflow knows: its catalog's and its resources'."""
    if workflow is None:
        return []
    kinds = [d.type for d in workflow.resources.values() if d.type is not None]
    if getattr(workflow, "catalog", None) is not None:
        kinds += list(workflow.catalog.resource_types.values())
    return kinds


def _missing_columns(operation: Operation, fn: Callable,
                     workflow: "Workflow") -> list[str]:
    """Required parameters the upstream grid cannot supply.

    Checked only against an upstream that has **run**: a staged Output holds
    placeholder rows, not real columns, so checking one would invent errors.
    The check therefore sharpens as the workflow runs, the same way staging
    does — and a source step is born completed, so the common case is covered
    from declaration.
    """
    verb = operation.shape_verb
    if verb is None or verb.kind in ("source", "sweep"):
        return []                       # nothing upstream, or rows it generates

    upstream = workflow._input_for(operation)
    if upstream is None:
        return []

    try:
        parameters = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return []
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return []                       # takes the whole row; nothing to miss
    if verb.kind in ("collapse", "table"):
        parameters = parameters[1:]     # the verb supplies the accumulator / the grid

    available = set(rows(upstream).columns) | set(operation.arguments)
    missing = [p.name for p in parameters
               if p.default is inspect.Parameter.empty
               and p.kind is not inspect.Parameter.VAR_POSITIONAL
               and p.name not in available]
    if not missing:
        return []
    # A parameter typed as a resource is never a column — say how to bind it.
    hint = ""
    try:
        annotations = {k: p.annotation for k, p in _signature(fn).parameters.items()}
    except (TypeError, ValueError):
        annotations = {}
    for name in missing:
        kind = annotations.get(name)
        if isinstance(kind, type) and any(isinstance(t, type) and issubclass(t, kind)
                                          for t in _resource_types_of(workflow)):
            hint = (f". {name!r} is a resource ({kind.__name__}), not a column: "
                    f"bind it with {name}=res[\"<name>\"]")
            break
    return [
        f"{operation.tool}() needs {', '.join(repr(m) for m in missing)}, "
        f"which {str(operation.input) if operation.input is not None else 'the input'!r} does not have "
        f"(it has {', '.join(sorted(available)) or 'no columns'}){hint}"
    ]


def _type_mismatches(operation: Operation, fn: Callable,
                     workflow: "Workflow | None") -> list[str]:
    """Where the tool's declared types disagree with what will reach it.

    Two sources, checked on the same terms as everything else in :func:`check`:
    a **bound literal** is in hand at declaration, so it is always checkable; an
    **upstream column** needs that step to have run, exactly like
    :func:`_missing_columns`, because a staged Output holds placeholder rows.

    Only certain mismatches are reported. ``_column_fits`` answers ``None`` for
    anything it cannot decide, and an undecidable type is not an error — a false
    positive here would refuse a step that runs.
    """
    try:
        # Resolved, so `from __future__ import annotations` (a string
        # "FakeLLM") is checked like the real type rather than skipped.
        parameters = _signature(fn).parameters
    except (TypeError, ValueError):
        return []

    problems: list[str] = []
    for name, value in operation.arguments.items():
        parameter = parameters.get(name)
        if parameter is None or parameter.annotation is inspect.Parameter.empty:
            continue
        if isinstance(value, StepRef):
            continue                     # a value reference, resolved at run
        if isinstance(value, ResRef):
            # Checked against the *declared* type, so it works before anything
            # is loaded. A subclass fits its base.
            decl = workflow.resources.get(value.name) if workflow else None
            if decl is not None and decl.type is not None and \
                    _type_fits(decl.type, parameter.annotation) is False:
                problems.append(
                    f"{operation.tool}() declares {name}: "
                    f"{_type_name(parameter.annotation)}, but it is bound to "
                    f"resource {value.name!r} ({decl.type.__name__})"
                )
            continue
        if _value_fits(value, parameter.annotation) is False:
            problems.append(
                f"{operation.tool}() declares {name}: "
                f"{_type_name(parameter.annotation)}, but it is bound to "
                f"{value!r} ({type(value).__name__})"
            )

    verb = operation.shape_verb
    if workflow is None or verb is None or verb.kind in ("source", "sweep",
                                                         "select", "drop"):
        return problems
    upstream = workflow._input_for(operation)
    if upstream is None:
        # 008 C5: before the input runs, check against the types it declares
        # (a source's schema, mod.expect, or a tool's return annotation).
        declared_types = workflow._column_types(operation)
        params = list(parameters.values())
        if verb.kind in ("collapse", "table"):
            params = params[1:]
        for parameter in params:
            if parameter.name in operation.arguments:
                continue
            column_type = declared_types.get(parameter.name)
            if column_type is None or parameter.annotation is inspect.Parameter.empty:
                continue
            if _declared_fits(column_type, parameter.annotation) is False:
                problems.append(
                    f"{operation.tool}() declares {parameter.name}: "
                    f"{_type_name(parameter.annotation)}, but "
                    f"{str(operation.input)!r} will have {parameter.name} as "
                    f"{_type_label(column_type)}")
        return problems

    frame = rows(upstream)
    # Only rows that completed count: a failed cell is a failure, not a
    # missing value, and its row is blocked downstream anyway (008 C10).
    completed = pd.Index(upstream.ids_in("known"))
    declared = list(parameters.values())
    if verb.kind in ("collapse", "table"):
        declared = declared[1:]          # the verb supplies the accumulator / the grid
    upstream_name = (str(operation.input) if operation.input is not None
                     else "the input")
    for parameter in declared:
        if parameter.name in operation.arguments:
            continue                     # a literal, checked above
        if parameter.name not in frame.columns:
            continue                     # missing columns are rule 7's job
        if parameter.annotation is inspect.Parameter.empty:
            continue
        admits_none, base = _optional_parts(parameter.annotation)
        series = frame[parameter.name]
        try:
            has_none = bool(series.loc[series.index.intersection(completed)].isna().any())
        except (TypeError, ValueError):
            has_none = False
        if has_none and not admits_none:
            # 008 C14: said in terms of None, not of the float64 that NaN
            # used to force.
            problems.append(
                f"{upstream_name}.{parameter.name} can be None, but "
                f"{operation.tool}() takes {parameter.name}: "
                f"{_type_name(parameter.annotation)}; accept "
                f"{_type_name(parameter.annotation)} | None, or filter the "
                "Nones first")
            continue
        if _column_fits(series, base) is False:
            problems.append(
                f"{operation.tool}() declares {parameter.name}: "
                f"{_type_name(parameter.annotation)}, but "
                f"{str(operation.input) if operation.input is not None else 'the input'!r} has "
                f"{parameter.name} as {frame[parameter.name].dtype}"
            )
    return problems


#: The payload column each verb writes when ``name=`` is not given. ``None``
#: means the verb writes no new column at all. Staging reads this so a staged
#: step predicts the *right* column name — which is what lets a downstream
#: reducer be recognized before anything has run.
DEFAULT_PAYLOAD: dict[str, str | None] = {
    "source": None, "filter": None, "select": None, "drop": None,
    # widen writes several *named* columns, so it has no single payload.
    "widen": None,
    # the rearranging verbs write nothing new at all.
    "slice": None, "rename": None, "sort": None, "distinct": None,
    "group": "group",
    "map": VALUE_COLUMN, "collapse": VALUE_COLUMN, "expand": VALUE_COLUMN, "sweep": VALUE_COLUMN,
    "table": None,
}


#: Verbs whose output keeps **all** the input's columns (§3's columns column).
#: Not ``map``, ``group`` or ``expand``: a step that computes is only its
#: results (owner decision, 2026-10-20).
#: ``collapse`` and ``sweep`` build their rows from scratch; ``select`` keeps a
#: chosen subset, so it predicts its columns exactly and gets its own branch in
#: :func:`stage`.
CARRIES_COLUMNS: frozenset[str] = frozenset({"filter", "group"})


#: §3's rows column, as data: what each verb does to the input's row count.
#: This is what staging folds, and it is why a staged claim can be honest —
#: ``filter`` can promise "at most n", never "n".
ROWS_RULE: dict[str, str] = {
    "source": "same", "map": "same", "group": "same",
    "filter": "at_most", "select": "same", "drop": "same", "widen": "same",
    "rename": "same", "sort": "same",
    "slice": "at_most", "distinct": "at_most",
    "collapse": "one",
    "expand": "unknown", "sweep": "generated",
    # K12: one run of the tool decides the grid — rows and columns both.
    "table": "generated",
    # N: whichever verb the data picks — not knowable before it runs.
    "auto": "unknown",
}


def columns_unknown(output: Output) -> bool:
    """True while an output's columns may include more than :func:`predicted_columns`.

    Only a staged output can be open: once a step has run, its columns are
    exactly its data's. 008 K1 — an unknown set is never treated as empty.
    """
    return bool(output.meta.get("staged") and output.meta.get("columns_open"))


def predicted_columns(output: Output) -> list[str]:
    """The column names a step's output will have, **in order**, as far as known.

    Ordered, not a set: column order is real information — ``select`` reorders
    deliberately, and ``map`` appends its payload after the columns it carried
    through. Returning a set once let a prediction come out in hash order, which
    matched the actual columns only by luck.

    A step that has run knows them exactly. A **staged** one knows only the
    name of the payload column it is going to write — but that single name is
    often enough to recognize a pattern, which is why inference may use it.

    Validation may **not**: the prediction is a subset (a ``map`` also carries
    its input's columns through), so rejecting against it would invent errors.
    Inference uses predicted columns to *recognize*; ``check`` uses real ones
    to *refuse*.
    """
    if not output.meta.get("staged"):
        return list(output.data.columns)
    recorded = output.meta.get("columns")
    if recorded is not None:
        return list(recorded)
    payload = output.meta.get("value_column")
    return [payload] if payload else []


def _as_tool_function(fn: Any) -> Any:
    """What a tool looks like to a step — never with ``self`` (008 M).

    Accepts a plain function, a ``Tool``, a resource method taken from
    its class (``DB.lookup``) or a ``(type, "method")`` pair. A method's
    ``self`` is the instance, not a column, so it is dropped.
    """
    if isinstance(fn, Tool):
        return fn.fn
    if isinstance(fn, tuple) and len(fn) == 2 and isinstance(fn[0], type):
        cls, name = fn
        if name in _bound_tools(cls):
            return _method_view(cls, name)
        fn = getattr(cls, name)
    if _looks_like_method(fn):
        signature = _signature(fn)

        def view(*args, **kwargs):
            return fn(*args, **kwargs)
        view.__signature__ = signature.replace(
            parameters=list(signature.parameters.values())[1:])
        view.__name__ = getattr(fn, "__name__", "method")
        view.__doc__ = fn.__doc__
        return view
    return fn


#: First-parameter names that mark a two-argument tool as a reducer by
#: signature alone (008 K2). Matches the builtin reducers' `acc`.
_ACCUMULATOR_NAMES = frozenset({"acc", "accumulator", "memo", "carry"})


def infer_verb(fn: Callable, upstream: Any, literals: dict) -> tuple[str, str]:
    """Pick the shape verb a tool most likely wants, and say why.

    This is the "configure the iteration for me" behaviour, and it resolves
    **at wiring time into a concrete verb** — never into a stored ``auto``
    modifier. An `auto` that stayed in the data would be the one modifier whose
    shape is unknowable before running, which is exactly the property staging,
    serialization and the round-trip invariant all depend on. What gets stored
    is an ordinary ``map`` or ``collapse``, indistinguishable from one you
    typed, so the UI shows it selected and you can change it.

    Resolving once also sidesteps the clobbering problem: an inferred verb is
    never silently re-inferred later, so an edit cannot be overwritten.
    """
    columns: set[str] = set()
    n_rows: int | None = None
    if isinstance(upstream, Output):
        columns = set(predicted_columns(upstream))
        n_rows = upstream.meta.get("expected") if upstream.meta.get("staged") \
            else len(upstream.data)
    elif upstream is not None:
        frame = rows(upstream)
        columns, n_rows = set(frame.columns), len(frame)

    fn = _as_tool_function(fn)
    try:
        parameters = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return "map", "could not read the tool's signature; assuming per row"

    positional = [p for p in parameters
                  if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    needed = [p.name for p in positional
              if p.default is inspect.Parameter.empty
              and p.name not in literals]

    # 008 K12: a tool whose first input is a DataFrame wants the whole grid.
    first = positional[0] if positional else None
    if first is not None and first.name not in literals:
        try:
            hint = typing.get_type_hints(fn).get(first.name, first.annotation)
        except Exception:
            hint = first.annotation
        if hint is pd.DataFrame or hint == "pd.DataFrame" or hint == "DataFrame":
            return "table", (f"{first.name!r} is a DataFrame, so the tool gets "
                             "the whole grid")

    # 008 K2: decide from the signature first, so the verb never depends on
    # whether the input has run. A first parameter named like an accumulator
    # is a reducer, whatever the columns are.
    if len(needed) >= 2 and needed[0] in _ACCUMULATOR_NAMES:
        return "collapse", (f"{needed[0]!r} names an accumulator, so this reads "
                            "as a reducer")

    # (acc, x) where the first value is not a column: that is a reducer.
    if len(needed) >= 2 and needed[0] not in columns and needed[1] in columns:
        return "collapse", (f"{needed[0]!r} is not a column but {needed[1]!r} is, "
                            "so this reads as a reducer")

    returns = inspect.signature(fn).return_annotation
    # Normalize to a bare type name so a string annotation (PEP 563 /
    # ``from __future__ import annotations``) infers the same verb a real type
    # does — otherwise a tools file with future annotations silently loses
    # filter/expand inference and everything falls back to map.
    returns_name = (returns if isinstance(returns, str)
                    else getattr(returns, "__name__", "")) or ""
    base = returns_name.split("[", 1)[0]          # "list[int]" -> "list"
    if returns is bool or base == "bool":
        return "filter", "it returns a bool per row, so keep the rows that pass"
    sequence = {"list", "tuple", "set"}
    if (returns in (list, tuple, set)
            or typing.get_origin(returns) in (list, tuple, set)
            or base in sequence):
        return "expand", ("it returns many values per row, so unnest them into "
                          "their own rows")

    if n_rows == 1:
        return "map", "the input is a single row"

    if needed and columns and not set(needed) & columns:
        return "map", (f"none of {', '.join(map(repr, needed))} is a column yet — "
                       "check the input")

    if columns:
        return "map", (f"{', '.join(repr(n) for n in needed) or 'the tool'} "
                       f"comes from the input's columns, so apply it per row")
    return "map", "applying it per row"


def stage(operation: Operation, workflow: "Workflow | None" = None,
          problems: tuple[str, ...] = ()) -> Output:
    """The Output a step has before it runs — the slot, with what we know in it.

    An **invalid** operation stages as a single cell: it has no shape, because
    the thing that would have given it one is what is broken.

    Otherwise staging folds :data:`ROWS_RULE` over the input's index. Only the
    1:1 verbs can name their cells in advance; ``filter`` bounds them,
    ``collapse`` knows there is one, and ``expand`` cannot know at all. The
    ledger is materialized only when the addresses are actually known (§7's
    level 3) — an empty ledger is the honest answer for the rest.
    """
    if _is_auto(operation) and len(operation.shape_verbs) == 1:
        # 008 N: stage as the verb it would be now, marked provisional.
        concrete, kind, why = _provisional(operation, workflow)
        out = stage(concrete, workflow, problems)
        out.meta["auto"] = {"verb": kind, "reason": why, "provisional": True}
        return out
    if problems:
        kind = operation.shape_verb.kind if operation.shape_verb else None
        return Output(
            data=pd.DataFrame({VALUE_COLUMN: [None]}, index=[0]),
            records=[{"status": "invalid", "error": problems[0],
                             "attempts": 0, "seconds": 0.0}], index=[0],
            meta={"verb": kind, "form": "scalar", "value_column": VALUE_COLUMN,
                  "staged": True, "problems": problems, "n_in": None,
                  "expected": None, "rows_rule": None, "columns": [VALUE_COLUMN]},
        )
    if is_combine(operation):
        return _stage_combine(operation, workflow)
    verb = operation.shape_verb
    kind = verb.kind if verb else None
    # 008 C1/C2: a setting that reads a step, or is a tool, has no value until
    # run. Stage as though it were absent, and say the columns are not known.
    unsettled = verb is not None and any(
        isinstance(v, StepRef) or _is_tool_value(v) for v in verb.settings.values())
    if unsettled:
        verb = Modifier(verb.kind, {k: v for k, v in verb.settings.items()
                                    if not isinstance(v, StepRef) and not _is_tool_value(v)})

    known = workflow._known_index(operation) if workflow is not None else None
    n_in = None if known is None else len(known)
    rule = ROWS_RULE.get(kind)

    # F6: `collapse(by=)` makes one row per *group*, and the group count comes
    #     from the data — so it is unknowable, not "one". F7: `sweep` is the
    #     opposite case: its count is fully determined by its own parameter
    #     lists, with no upstream involved at all.
    swept = 0
    if kind == "collapse" and verb.settings.get("by"):
        rule = "per_group"
    elif kind == "sweep":
        lists = [v for k, v in verb.settings.items()
                 if k not in ("name", "over", "retries")]
        if lists and all(isinstance(v, (list, tuple)) for v in lists):
            swept = 1
            for values in lists:
                swept *= len(values)
            rule = "generated"

    if kind is None:                       # no orchestration → a single value
        index, expected = [0], 1
    elif rule == "same" and known is not None:
        index, expected = list(known), n_in
    elif rule == "one":
        index, expected = [0], 1
    elif rule == "generated" and swept:
        index, expected = list(range(swept)), swept
    else:                                  # not addressable yet
        index, expected = [], None

    # The column this step is going to write, honouring an explicit `name=`.
    payload = (VALUE_COLUMN if kind is None
               else verb.settings.get("name", DEFAULT_PAYLOAD.get(kind, VALUE_COLUMN)))

    # The full column set this step will produce, as far as is knowable —
    # carried-through columns plus whatever it writes. This is what a
    # downstream step reads to recognize what it is looking at, so predicting
    # only the payload would lose every column that simply passes through.
    upstream_columns = (workflow._known_columns(operation)
                        if workflow is not None else set())
    # Predicted in order, because order is what a reader and a downstream tool
    # both see. Each verb contributes its own columns and then the payload is
    # appended, which is exactly what the verbs do to the frame.
    ordered: list[str] = []
    if kind == "select":
        chosen = verb.settings.get("columns")
        if isinstance(chosen, dict) or chosen is None:
            try:
                ordered = _resolve_columns(list(upstream_columns), chosen, "the input")
            except SelectionError:
                ordered = []
        else:
            ordered = list(chosen)
    elif kind == "drop":
        removed = set(verb.settings.get("columns") or [])
        ordered = [c for c in upstream_columns if c not in removed]
    elif kind == "rename":
        mapping = verb.settings.get("columns") or {}
        ordered = [mapping.get(c, c) for c in upstream_columns]
    elif kind in ("slice", "sort", "distinct"):
        ordered = list(upstream_columns)
    elif kind == "widen":
        ordered = list(upstream_columns)
        ordered += [c for c in (verb.settings.get("columns") or [])
                    if c not in ordered]
    elif kind in CARRIES_COLUMNS:
        ordered = list(upstream_columns)
    elif kind == "sweep":
        ordered = [k for k in verb.settings if k not in ("name", "over", "retries")]
    elif kind == "collapse" and verb.settings.get("by"):
        ordered = [verb.settings["by"]]
    if payload and payload not in ordered:
        ordered.append(payload)
    index_names = ordered

    # 008 K1: are these all the columns, or only the ones known so far? A
    # source computed by a tool cannot know its columns before it runs, and a
    # verb that carries its input's columns through inherits that.
    if unsettled and kind in ("select", "drop", "rename", "widen"):
        columns_open = True
    elif kind == "select" and not isinstance(verb.settings.get("columns"), (list, tuple)):
        # a range or position selection over columns not known yet
        columns_open = workflow._columns_open(operation) if workflow is not None else False
    elif kind == "source":
        fn = operation.fn \
            or BUILTIN_TOOLS.get(operation.tool)
        columns_open = not is_identity(fn)
    elif kind == "table":
        columns_open = True             # what the tool returns — unless declared
    elif kind in ("sweep", "select", "collapse", "map", "expand"):
        columns_open = False            # these build their columns themselves
    else:
        columns_open = (workflow._columns_open(operation)
                        if workflow is not None else False)

    # 008 C5/C9: what a step will produce, as far as is known — and how sure.
    # Column types come from the input (carried), the tool's return (payload),
    # a source's declared schema, or `mod.expect`.
    fn = operation.fn or BUILTIN_TOOLS.get(operation.tool)
    label = operation.tool
    upstream_types = workflow._column_types(operation) if workflow is not None else {}
    types: dict = {c: upstream_types.get(c) for c in ordered}
    if kind == "rename":
        mapping = verb.settings.get("columns") or {}
        if isinstance(mapping, dict):
            for old, new in mapping.items():
                types[new] = upstream_types.get(old)
    if payload and kind not in ("source",):
        types[payload] = _payload_type(kind, fn)
    if kind in ("source", "table") and not is_identity(fn):
        schema = _declared_schema(fn)
        if schema is not None:
            ordered, types, columns_open = list(schema), dict(schema), False
    expect = _expectation(operation)
    if expect.get("columns") is not None:
        names, stated_types = _expected_columns(expect)
        known = [c for c in ordered if c not in names] if kind not in ("source", "table") else []
        ordered = list(dict.fromkeys(names + known))
        types = {c: stated_types.get(c, types.get(c)) for c in ordered}
        columns_open = bool(expect.get("more_columns"))
    if isinstance(expect.get("rows"), int) and expected is None:
        index, expected = list(range(expect["rows"])), expect["rows"]
    upstream_name = str(operation.input) if operation.input is not None else None
    plan = {
        "rows": _rows_plan(kind, rule, expected if "rows" not in expect else None,
                           n_in, expect, label, upstream_name),
        "columns": _columns_plan(kind, ordered, columns_open, expect, label, upstream_name),
        "types": {c: _type_label(types.get(c)) for c in ordered},
    }

    records = [{"status": "staged", "error": None, "attempts": 0, "seconds": 0.0}
               for _ in index]
    index_names = ordered
    return Output(
        data=pd.DataFrame({c: pd.Series([None] * len(index), index=index, dtype=object)
                           for c in index_names or [VALUE_COLUMN]}, index=index),
        records=records, index=index,
        meta={"verb": kind, "form": "scalar" if kind is None else "column",
              "value_column": payload, "staged": True, "problems": (),
              "n_in": n_in, "expected": expected, "rows_rule": rule,
              "columns": ordered, "columns_open": columns_open,
              "plan": plan, "column_types": types},
    )


# Names used only inside functions, imported last so the modules can refer
# to each other (see grid.py).
from .system_tools import BUILTIN_TOOLS, is_identity  # noqa: E402
from .catalog import (  # noqa: E402
    Tool,
    _bound_problem,
    _bound_tools,
    _looks_like_method,
    _method_view,
    _no_resource,
    _signature,
    _type_fits,
)
from .combines import (  # noqa: E402
    COMBINE,
    _stage_combine,
    _zip_clash,
    is_combine,
)
from .errors import SelectionError  # noqa: E402
from .modifiers import (  # noqa: E402
    MODIFIERS,
    NAMED_VERBS,
    Modifier,
    PARAM_TYPES,
    PARAM_TYPES_BY_VERB,
    _required_settings,
)
from .operation import _src, Operation  # noqa: E402
from .output import Output, ROW_ID, STATES  # noqa: E402
from .references import (  # noqa: E402
    ResRef,
    StepRef,
    TOOL_SETTINGS,
    ToolRef,
    _UNKNOWN,
    _apply_selection,
    _is_tool_value,
    _resolve_columns,
    _selection_kind,
    rows,
)
from .run import _is_auto, _provisional  # noqa: E402
from .values import (  # noqa: E402
    _wants,
    _TYPE_NAMES,
    _column_fits,
    _declared_schema,
    _literal_problem,
    _open_keywords,
    _optional_parts,
    _payload_type,
    _shape_kind,
    _shape_problem,
    _type_label,
    _type_name,
    _value_fits,
)
from .workflow import Workflow  # noqa: E402
