"""The grid model: tools, modifiers, Operations, Steps and Workflows.

Organized by the three layers of docs/shape-algebra.md §6.2, because the layer
boundaries are what the tests are really protecting:

    build     Operation x Modifier -> Operation      (closed)
    run       Operation x Data     -> Output         (the one boundary)
    inspect   Output               -> DataFrame      (closed)
"""

import json

import pandas as pd
import pytest

from simple_steps_core.grid import (
    BUILTIN_TOOLS,
    DECORATORS,
    MODIFIERS,
    SHAPE_VERBS,
    Modifier,
    Operation,
    Output,
    PayloadError,
    Step,
    StepRef,
    Workflow,
    compile_operation,
    grid,
    infer_verb,
    predicted_columns,
    identity,
    is_shape,
    mod,
    op,
    rows,
    tool,
)


# Tools declare the values they need. Supplying rows is the modifier's job, so
# none of these mentions a row or digs a column out of one.
@tool
def score(n, weight=1):
    return n * 10 * weight


@tool
def keep(n):
    return n > 1


@tool
def burst(n):
    return [n] * n


@tool
def total(acc, n):
    return (acc or 0) + n


@pytest.fixture
def three():
    return pd.DataFrame({"n": [1, 2, 3]})


# ─────────────────────────────────────────────────────────────────────────
# The calling rule: parens run, brackets decorate
# ─────────────────────────────────────────────────────────────────────────
def test_parens_call_the_plain_function():
    assert score(3) == 30, "a tool stays an ordinary function"


def test_a_tool_declares_values_not_rows():
    """The modifier supplies rows; the tool names the columns it wants."""
    import inspect as _inspect

    assert list(_inspect.signature(score.fn).parameters) == ["n", "weight"]


def test_columns_bind_to_parameters_by_name(three):
    assert score[mod.map()](grid(three)).values == [10, 20, 30]


def test_undeclared_columns_are_not_passed():
    @tool
    def only_n(n):
        return n

    frame = pd.DataFrame({"n": [1, 2], "extra": ["a", "b"], "more": [9, 9]})
    assert only_n[mod.map()](grid(frame)).values == [1, 2]


def test_a_tool_can_ask_for_the_whole_row():
    @tool
    def widest(**row):
        return sorted(row)

    frame = pd.DataFrame({"b": [1], "a": [2]})
    assert widest[mod.map()](grid(frame)).values == [["a", "b"]]


def test_a_column_beats_a_bound_literal(three):
    """The row is the unit of work — the engine's rule in _run_item."""
    assert score.bind(n=99)[mod.map()](grid(three)).values == [10, 20, 30]


def test_brackets_decorate_and_return_data():
    assert isinstance(score[mod.map()], Operation)


def test_bind_fixes_literals_without_running():
    bound = score.bind(weight=2)
    assert isinstance(bound, Operation)
    assert bound.arguments == {"weight": 2}


def test_bound_literals_reach_every_item(three):
    assert score.bind(weight=2)[mod.map()](grid(three)).values == [20, 40, 60]


# ─────────────────────────────────────────────────────────────────────────
# build: Operation x Modifier -> Operation, closed
# ─────────────────────────────────────────────────────────────────────────
def test_every_modifier_application_returns_an_operation():
    start = op("score")
    for name in MODIFIERS:
        params = {"times": 1} if name == "retry" else {"seconds": 1} if name == "timeout" else {}
        assert isinstance(start[getattr(mod, name)(**params)], Operation)


def test_bind_is_closed_too():
    assert isinstance(score[mod.map()].bind(weight=2), Operation)


def test_single_layer_needs_no_tuple():
    assert score[mod.map()] == score[(mod.map(),)]


def test_written_order_is_outermost_first():
    stack = score[mod.map(), mod.retry(times=2)]
    assert [m.kind for m in stack.layers] == ["map", "retry"]
    assert [m.kind for m in stack.modifiers] == ["retry", "map"]


def test_order_is_semantics():
    assert score[mod.map(), mod.retry(times=1)] != score[mod.retry(times=1), mod.map()]


def test_repr_reads_in_written_order():
    assert repr(score[mod.map(), mod.retry(times=2)]) == (
        "<Operation map() ∘ retry(times=2) ∘ score>"
    )


def test_a_plain_decorator_is_refused():
    with pytest.raises(TypeError, match="must be a Modifier"):
        score[lambda fn: fn]


def test_step_refs_never_survive_into_stored_data():
    stored = score[mod.map(over=StepRef("videos"))]
    assert stored.modifiers[0].params["over"] == "videos"


def test_carried_function_is_not_part_of_the_data():
    assert score[mod.map()] == op("score")[mod.map()]


# ─────────────────────────────────────────────────────────────────────────
# The modifier vocabulary is one table
# ─────────────────────────────────────────────────────────────────────────
def test_shape_verbs_and_decorators_derive_from_modifiers():
    assert set(SHAPE_VERBS) | {"retry", "timeout"} == set(MODIFIERS)
    assert set(DECORATORS) == set(MODIFIERS)


def test_modifier_knows_its_class():
    assert mod.map().is_shape and mod.map().cls == "shape"
    assert not mod.retry(times=1).is_shape
    assert mod.retry(times=1).cls == "execution"


def test_unregistered_kind_reports_unknown_rather_than_crashing():
    assert Modifier("frobnicate").cls == "unknown"


def test_a_typo_fails_where_it_is_written():
    with pytest.raises(AttributeError, match="no modifier 'frobnicate'"):
        mod.frobnicate(wat=1)


def test_staging_folds_shape_and_ignores_execution():
    stack = score[mod.map(), mod.retry(times=2), mod.timeout(seconds=5)]
    assert [m.kind for m in stack.shape_verbs] == ["map"]
    assert stack.shape_verb.kind == "map"


def test_is_shape_agrees_with_the_table():
    assert is_shape("map") and not is_shape("retry") and not is_shape("nope")


# ─────────────────────────────────────────────────────────────────────────
# identity closes the algebra
# ─────────────────────────────────────────────────────────────────────────
def test_identity_is_a_builtin_tool():
    assert BUILTIN_TOOLS["identity"] is identity


def test_identity_returns_the_payload_not_the_row():
    assert identity(value=7) == 7
    assert identity(only=7) == 7
    assert identity(a=1, b=2) == {"a": 1, "b": 2}
    assert identity(a=1, b=2, column="b") == 2


def test_expand_over_identity_flattens():
    out = op("identity")[mod.expand()](grid(pd.DataFrame({"xs": [[1, 2], [3]]})))
    assert out.values == [1, 2, 3]


def test_filter_over_identity_keeps_the_truthy():
    out = op("identity")[mod.filter()](grid(pd.DataFrame({"ok": [True, False, True]})))
    assert len(out.data) == 2


def test_a_renamed_payload_is_bound_explicitly():
    frame = pd.DataFrame({"n": [1, 2], "score": [[1, 2], [3]]})
    out = op("identity", column="score")[mod.expand()](grid(frame))
    assert out.values == [1, 2, 3]


def test_source_applies_no_tool():
    with pytest.raises(ValueError, match="source applies no tool"):
        score[mod.source()](pd.DataFrame({"n": [1]}))


# ─────────────────────────────────────────────────────────────────────────
# run: Operation x Data -> Output
# ─────────────────────────────────────────────────────────────────────────
def test_run_compiles_innermost_first(three):
    fn = compile_operation(score[mod.map()], {"score": lambda n: n})
    assert fn(grid(three)).values == [1, 2, 3]


def test_retry_runs_per_item():
    attempts = []

    def flaky(n):
        attempts.append(n)
        if attempts.count(n) < 2:
            raise RuntimeError("boom")
        return n

    out = op("flaky")[mod.map(), mod.retry(times=3)].run(
        grid(pd.DataFrame({"n": [1, 2]})), tools={"flaky": flaky}
    )
    assert out.values == [1, 2]
    assert attempts.count(1) == 2 and attempts.count(2) == 2


# ─────────────────────────────────────────────────────────────────────────
# wiring: parens applied to a reference build the step
# ─────────────────────────────────────────────────────────────────────────
def test_calling_with_a_reference_wires_instead_of_running(three):
    wf = Workflow()
    wf["raw"] = three
    wired = score[mod.map()](wf["raw"])
    assert isinstance(wired, Operation)
    assert wired == score[mod.map(over=wf["raw"])], "same stored data either way"


def test_run_still_means_run_and_refuses_a_reference(three):
    wf = Workflow()
    wf["raw"] = three
    with pytest.raises(TypeError, match="names a step, it is not data"):
        score[mod.map()].run(wf["raw"])


def test_a_bare_tool_call_on_a_reference_is_the_whole_step(three):
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score(wf["raw"])
    assert wf.step("scored").operation == score[mod.map(over=wf["raw"])]
    wf.run_all()
    assert wf.step("scored").output.values == [10, 20, 30]


def test_wiring_keeps_an_explicit_verb(three):
    wf = Workflow()
    wf["raw"] = three
    wf["kept"] = keep[mod.filter()](wf["raw"])
    assert wf.step("kept").operation.shape_verb.kind == "filter"


def test_literals_survive_wiring(three):
    wf = Workflow()
    wf["raw"] = three
    wf["doubled"] = score(wf["raw"], weight=2)
    assert wf.step("doubled").operation.arguments == {"weight": 2}
    wf.run_all()
    assert wf.step("doubled").output.values == [20, 40, 60]


def test_inference_reads_a_reducer_as_collapse(three):
    wf = Workflow()
    wf["raw"] = three
    wf["sum"] = total(wf["raw"])          # total(acc, n) — acc is not a column
    assert wf.step("sum").operation.shape_verb.kind == "collapse"
    wf.run_all()
    assert wf.step("sum").output.item() == 6


def test_inference_reads_a_bool_return_as_filter(three):
    @tool
    def big(n) -> bool:
        return n > 1

    wf = Workflow()
    wf["raw"] = three
    wf["kept"] = big(wf["raw"])
    assert wf.step("kept").operation.shape_verb.kind == "filter"
    wf.run_all()
    assert len(wf.step("kept").output.data) == 2


def test_inference_works_when_the_whole_chain_is_declared_first(three):
    """Build-it-all-at-once: nothing has run, so only payload names are known."""
    @tool
    def big(value) -> bool:
        return value > 15

    @tool
    def add_up(acc, value):
        return (acc or 0) + value

    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score(wf["raw"], weight=2)
    wf["kept"] = big(wf["scored"])          # upstream staged
    wf["sum"] = add_up(wf["kept"])          # upstream staged, still a reducer
    assert wf.step("kept").operation.shape_verb.kind == "filter"
    assert wf.step("sum").operation.shape_verb.kind == "collapse"
    wf.run_all()
    assert wf.step("sum").output.item() == 120


def test_inference_on_a_staged_upstream_sees_only_the_payload(three):
    """The documented limit: a carried-through column is not predictable yet.

    `total(acc, n)` reduces over the `n` column, but a staged upstream only
    promises `value`, so the reducer is not recognized until it has run. The
    verb is visible and replaceable, which is the point of storing it
    concretely.
    """
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score(wf["raw"])
    assert total(wf["scored"]).shape_verb.kind == "map"      # staged: missed
    wf.run_all()
    assert total(wf["scored"]).shape_verb.kind == "collapse"  # ran: recognized


def test_predicted_columns_narrow_to_the_payload_while_staged(three):
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score(wf["raw"])
    assert predicted_columns(wf.step("raw").output) == {"n"}
    assert predicted_columns(wf.step("scored").output) == {"value"}
    wf.run_all()
    assert predicted_columns(wf.step("scored").output) == {"n", "value"}


def test_inference_defaults_to_map(three):
    wf = Workflow()
    wf["raw"] = three
    assert score(wf["raw"]).shape_verb.kind == "map"


def test_an_inferred_verb_is_stored_concretely_not_as_auto(three):
    """Nothing named 'auto' reaches the data — staging would have nothing to fold."""
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score(wf["raw"])
    blob = wf.to_dict()["steps"][1]["operation"]
    assert [m["kind"] for m in blob["modifiers"]] == ["map"]
    assert wf.step("scored").describe() == "map score · 3 cells"


def test_infer_verb_explains_itself(three):
    kind, reason = infer_verb(score.fn, grid(three), {})
    assert kind == "map" and "columns" in reason


def test_wiring_more_than_one_reference_is_refused(three):
    wf = Workflow()
    wf["raw"] = three
    wf["other"] = three
    with pytest.raises(TypeError, match="one reference at a time"):
        score(wf["raw"], wf["other"])


def test_an_id_only_operation_says_how_to_run_it(three):
    with pytest.raises(KeyError, match="names its tool"):
        op("score")[mod.map()](grid(three))


def test_no_orchestration_gives_a_single_value():
    assert score[()].run({"n": 4}) == 40


def test_a_bare_value_is_passed_positionally():
    @tool
    def double(x):
        return x * 2

    assert double[()].run(21) == 42


def test_sweep_generates_its_own_grid():
    @tool
    def cell(model, window):
        return f"{model}/{window}"

    out = cell[mod.sweep(model=["a", "b"], window=[7, 30])](None)
    assert out.values == ["a/7", "a/30", "b/7", "b/30"]
    assert out.meta["grid"] == (2, 2)


# ─────────────────────────────────────────────────────────────────────────
# inspect: Output
# ─────────────────────────────────────────────────────────────────────────
def test_shape_is_the_pandas_tuple_and_form_is_the_class(three):
    out = score[mod.map()](grid(three))
    assert out.shape == out.data.shape
    assert out.form == "column"


def test_map_keeps_the_input_columns(three):
    out = score[mod.map()](grid(three))
    assert list(out.data.columns) == ["n", "value"]


def test_ledger_is_row_aligned_and_view_joins_cleanly(three):
    out = score[mod.map()](grid(three))
    assert list(out.data.index) == list(out.ledger.index)
    assert len(out.view()) == 3


def test_filter_ledger_keeps_every_unit(three):
    out = keep[mod.filter()](grid(three))
    assert len(out.data) == 2 and len(out.ledger) == 3


def test_column_axis_is_guarded_not_half_built():
    with pytest.raises(NotImplementedError, match="axis='columns'"):
        rows(pd.DataFrame({"a": [1]}), axis="columns")


# ─────────────────────────────────────────────────────────────────────────
# declaring: a Step is born staged
# ─────────────────────────────────────────────────────────────────────────
def test_a_bare_value_declares_a_source_step(three):
    wf = Workflow()
    wf["raw"] = three
    step = wf.step("raw")
    assert isinstance(step, Step)
    assert step.operation.tool_id == "identity"
    assert step.operation.shape_verb.kind == "source"


def test_a_source_step_is_born_completed(three):
    """Its data arrived with the declaration, so there is nothing to compute."""
    wf = Workflow()
    wf["raw"] = three
    step = wf.step("raw")
    assert step.status == "completed"
    assert list(step.output.data["n"]) == [1, 2, 3]


def test_a_workflow_is_only_steps(three):
    """No parallel payload store: a literal is just a step's output."""
    wf = Workflow()
    wf["raw"] = three
    assert not hasattr(wf, "inputs")
    assert list(vars(wf)) == ["steps"]


def test_running_a_source_step_is_a_no_op(three):
    wf = Workflow()
    wf["raw"] = three
    before = wf.step("raw").output
    assert wf.run("raw").output is before


def test_declaring_stages_both_halves(three):
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(over=wf["raw"])]
    step = wf.step("scored")
    assert isinstance(step.output, Output)
    assert step.status == "staged"


def test_cardinality_propagates_before_anything_runs(three):
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(over=wf["raw"])]
    assert wf.step("scored").output.meta["expected"] == 3
    assert set(wf.step("scored").output.ledger["status"]) == {"staged"}


def test_declaring_never_computes(three):
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(over=wf["raw"])]
    assert wf.step("scored").output.values == [None, None, None]


def test_running_populates_and_is_manual(three):
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(over=wf["raw"])]
    wf.run("raw")
    assert wf.step("scored").status == "staged", "running raw must not compute scored"
    wf.run("scored")
    assert wf.step("scored").status == "completed"
    assert wf.step("scored").output.values == [10, 20, 30]


def test_running_against_a_staged_upstream_is_refused(three):
    @tool
    def again(value):
        return value + 1

    wf = Workflow()
    wf["raw"] = three
    wf["b"] = score[mod.map(over=wf["raw"])]
    wf["c"] = again[mod.map(over=wf["b"])]
    with pytest.raises(ValueError, match="which has not run"):
        wf.run("c")


def test_pending_lists_what_must_run_first(three):
    @tool
    def again(value):
        return value + 1

    wf = Workflow()
    wf["raw"] = three
    wf["b"] = score[mod.map(over=wf["raw"])]
    wf["c"] = again[mod.map(over=wf["b"])]
    assert wf.pending("c") == ["b"], "raw already holds its data"
    assert wf.pending("b") == []


def test_run_all_orders_the_chain(three):
    @tool
    def again(value):
        return value + 1

    wf = Workflow()
    wf["raw"] = three
    wf["b"] = score[mod.map(over=wf["raw"])]
    wf["c"] = again[mod.map(over=wf["b"])]
    wf.run_all()
    assert wf.step("c").output.values == [11, 21, 31]
    assert all(s.status == "completed" for s in wf.steps.values())


def test_run_all_skips_invalid_steps_without_failing(three):
    wf = Workflow()
    wf["raw"] = three
    wf["good"] = score[mod.map(over=wf["raw"])]
    wf["bad"] = score.bind(nope=1)[mod.map(over=wf["raw"])]
    wf.run_all()
    assert wf.step("good").status == "completed"
    assert wf.step("bad").status == "invalid"


def test_cardinality_propagates_transitively(three):
    @tool
    def again(value):
        return value + 1

    wf = Workflow()
    wf["a"] = pd.DataFrame({"n": [1, 2, 3, 4]})
    wf["b"] = score[mod.map(over=wf["a"])]
    wf["c"] = again[mod.map(over=wf["b"])]
    assert wf.step("c").output.meta["expected"] == 4
    wf.run_all()
    assert wf.step("c").output.values == [11, 21, 31, 41]


@pytest.mark.parametrize(
    "operation_for, rule, described",
    [
        (lambda ref: score[mod.map(over=ref)], "same", "map score · 3 cells"),
        (lambda ref: keep[mod.filter(over=ref)], "at_most", "filter keep · at most 3 cells"),
        (lambda ref: total[mod.collapse(over=ref)], "one", "collapse total · 1 cell"),
        (lambda ref: burst[mod.expand(over=ref)], "unknown",
         "expand burst · unknown count from 3 rows"),
    ],
)
def test_staged_claims_are_honest_per_verb(three, operation_for, rule, described):
    wf = Workflow()
    wf["raw"] = three
    wf["out"] = operation_for(wf["raw"])
    assert wf.step("out").output.meta["rows_rule"] == rule
    assert wf.step("out").describe() == described


def test_describe_reports_facts_once_a_step_has_run(three):
    wf = Workflow()
    wf["raw"] = three
    wf["kept"] = keep[mod.filter(over=wf["raw"])]
    assert wf.step("kept").describe() == "filter keep · at most 3 cells"
    wf.run_all()
    assert wf.step("kept").describe() == "filter keep · 2 cells"


# ─────────────────────────────────────────────────────────────────────────
# reactive validation: invalid is a state, not an exception
# ─────────────────────────────────────────────────────────────────────────
def test_a_mistyped_argument_is_caught_at_declaration(three):
    wf = Workflow()
    wf["raw"] = three
    wf["oops"] = score.bind(wieght=2)[mod.map(over=wf["raw"])]
    step = wf.step("oops")
    assert not step.valid and step.status == "invalid"
    assert "takes no argument 'wieght'" in step.problems[0]


def test_an_invalid_operation_is_a_single_cell(three):
    wf = Workflow()
    wf["raw"] = three
    wf["oops"] = score.bind(nope=1)[mod.map(over=wf["raw"])]
    assert len(wf.step("oops").output.data) == 1
    assert wf.step("oops").output.form == "scalar"


def test_a_missing_column_is_caught_at_declaration():
    """Possible only because the tool names the values it needs."""
    wf = Workflow()
    wf["raw"] = pd.DataFrame({"count": [1, 2, 3]})      # not "n"
    wf["scored"] = score[mod.map(over=wf["raw"])]
    step = wf.step("scored")
    assert not step.valid
    assert "needs 'n'" in step.problems[0] and "count" in step.problems[0]


def test_a_bound_literal_satisfies_a_required_value():
    wf = Workflow()
    wf["raw"] = pd.DataFrame({"count": [1, 2, 3]})
    wf["scored"] = score.bind(n=5)[mod.map(over=wf["raw"])]
    assert wf.step("scored").valid


def test_an_optional_parameter_is_not_required(three):
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(over=wf["raw"])]   # `weight` has a default
    assert wf.step("scored").valid


def test_a_whole_row_tool_is_never_flagged():
    @tool
    def anything(**row):
        return len(row)

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"whatever": [1]})
    wf["n"] = anything[mod.map(over=wf["raw"])]
    assert wf.step("n").valid


def test_collapse_does_not_require_its_accumulator_from_the_row(three):
    wf = Workflow()
    wf["raw"] = three
    wf["sum"] = total[mod.collapse(over=wf["raw"])]   # total(acc, n)
    assert wf.step("sum").valid
    wf.run_all()
    assert wf.step("sum").output.item() == 6


def test_a_staged_upstream_is_not_column_checked(three):
    """A staged Output holds placeholders, so checking it would invent errors."""
    @tool
    def again(value):
        return value + 1

    wf = Workflow()
    wf["raw"] = three
    wf["b"] = score[mod.map(over=wf["raw"])]
    wf["c"] = again[mod.map(over=wf["b"])]            # b has not run yet
    assert wf.step("c").valid
    wf.run_all()
    assert wf.step("c").output.values == [11, 21, 31]


def test_a_dangling_reference_is_caught():
    wf = Workflow()
    wf["dangling"] = score[mod.map(over="nope")]
    assert "not an earlier step" in wf.step("dangling").problems[0]


def test_reading_an_invalid_step_is_caught(three):
    wf = Workflow()
    wf["raw"] = three
    wf["bad"] = score.bind(nope=1)[mod.map(over=wf["raw"])]
    wf["downstream"] = score[mod.map(over=wf["bad"])]
    assert "which is invalid" in wf.step("downstream").problems[0]


def test_self_reference_is_caught(three):
    wf = Workflow()
    wf["raw"] = three
    wf["loop"] = score[mod.map(over=wf["raw"])]
    wf["loop"] = score[mod.map(over="loop")]
    assert "over itself" in wf.step("loop").problems[0]


def test_a_cycle_is_caught(three):
    wf = Workflow()
    wf["raw"] = three
    wf["a"] = score[mod.map(over=wf["raw"])]
    wf["b"] = score[mod.map(over=wf["a"])]
    wf["a"] = score[mod.map(over="b")]
    assert "circular" in wf.step("a").problems[0]


def test_bad_steps_stay_in_the_workflow_but_cannot_run(three):
    wf = Workflow()
    wf["raw"] = three
    wf["oops"] = score.bind(nope=1)[mod.map(over=wf["raw"])]
    assert "oops" in wf.steps
    with pytest.raises(ValueError, match="is invalid and cannot run"):
        wf.run("oops")


def test_any_bare_value_becomes_a_source_step():
    wf = Workflow()
    wf["xs"] = [1, 2, 3]
    assert wf.step("xs").status == "completed"
    assert len(wf.step("xs").output.data) == 3


# ─────────────────────────────────────────────────────────────────────────
# exporting: two modes, differing only in payloads
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def ran(three):
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(over=wf["raw"])]
    wf.run_all()
    return wf


def test_the_light_export_is_structure_only(ran):
    blob = ran.to_dict()
    assert set(blob) == {"version", "steps"}
    assert blob["steps"][1]["operation"] == {
        "tool_id": "score",
        "arguments": {},
        "modifiers": [{"kind": "map", "params": {"over": "raw"}}],
    }


def test_the_light_export_is_much_smaller(ran):
    assert len(ran.to_json()) * 3 < len(ran.to_session_json())


def test_light_round_trip_reproduces_structure_but_not_counts(ran):
    back = Workflow.from_json(ran.to_json(), {"score": score.fn})
    assert list(back.steps) == list(ran.steps)
    assert back.step("scored").operation == ran.step("scored").operation
    # Cardinality came from the data, which a light export does not carry.
    assert back.step("scored").output.meta["expected"] is None
    assert back.step("scored").describe() == "map score · one cell per upstream row"


def test_full_round_trip_restores_payloads_and_staging(ran):
    back = Workflow.from_json(ran.to_session_json(), {"score": score.fn})
    assert back.step("scored").output.values == [10, 20, 30]
    assert back.step("scored").status == "completed"
    assert back.step("raw").describe() == "source identity · 3 cells"


def test_a_light_reloaded_source_step_asks_for_its_data(ran):
    """The light export carries no payloads, so the source step needs supplying."""
    back = Workflow.from_json(ran.to_json(), {"score": score.fn})
    with pytest.raises(ValueError, match="has no data"):
        back.run("raw")
    back["raw"] = pd.DataFrame({"n": [1, 2, 3]})
    back.run_all()
    assert back.step("scored").output.values == [10, 20, 30]


def test_staging_is_a_pure_function_of_the_steps(three):
    """The round-trip invariant: re-declaring from an export re-derives staging."""
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(over=wf["raw"])]
    blob = wf.to_session_dict()
    back = Workflow.from_dict(blob, {"score": score.fn})
    for sid in wf.steps:
        assert back.step(sid).describe() == wf.step(sid).describe()
        before, after = wf.step(sid).output.meta, back.step(sid).output.meta
        assert after.get("expected") == before.get("expected")
        assert after.get("staged") == before.get("staged")


def test_loading_runs_the_same_checks_as_declaring():
    blob = {"version": 1, "steps": [
        {"step_id": "bad", "operation": {"tool_id": "score", "arguments": {},
                                         "modifiers": [{"kind": "map",
                                                        "params": {"over": "nope"}}]}},
    ]}
    back = Workflow.from_dict(blob, {"score": score.fn})
    assert not back.step("bad").valid


def test_an_unexportable_payload_says_so(three):
    wf = Workflow()
    wf["raw"] = three
    wf["objects"] = score[mod.map(over=wf["raw"])]
    wf.run_all()
    wf.step("objects").output = Output(
        data=pd.DataFrame({"value": [object()]}),
        ledger=wf.step("raw").output.ledger.head(1),
        meta={"form": "column", "payload": "value"},
    )
    with pytest.raises(PayloadError, match="cannot export"):
        wf.to_session_dict()


def test_exports_are_json(ran):
    assert json.loads(ran.to_json())["version"] == 1
    full = json.loads(ran.to_session_json())
    assert "inputs" not in full, "one payload map, not two"
    assert full["outputs"]["raw"]["data"]["kind"] == "frame"
