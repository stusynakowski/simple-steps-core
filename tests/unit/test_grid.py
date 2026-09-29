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
    identity,
    is_shape,
    mod,
    op,
    rows,
    tool,
)


@tool
def score(row, weight=1):
    return row["n"] * 10 * weight


@tool
def keep(row):
    return row["n"] > 1


@tool
def burst(row):
    return [row["n"]] * row["n"]


@tool
def total(acc, row):
    return (acc or 0) + row["n"]


@pytest.fixture
def three():
    return pd.DataFrame({"n": [1, 2, 3]})


# ─────────────────────────────────────────────────────────────────────────
# The calling rule: parens run, brackets decorate
# ─────────────────────────────────────────────────────────────────────────
def test_parens_call_the_plain_function():
    assert score({"n": 3}) == 30


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
    assert identity({"value": 7}) == 7
    assert identity({"only": 7}) == 7
    assert identity({"a": 1, "b": 2}) == {"a": 1, "b": 2}
    assert identity({"a": 1, "b": 2}, column="b") == 2


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
    fn = compile_operation(score[mod.map()], {"score": lambda row: row["n"]})
    assert fn(grid(three)).values == [1, 2, 3]


def test_retry_runs_per_item():
    attempts = []

    def flaky(row):
        attempts.append(row["n"])
        if attempts.count(row["n"]) < 2:
            raise RuntimeError("boom")
        return row["n"]

    out = op("flaky")[mod.map(), mod.retry(times=3)].run(
        grid(pd.DataFrame({"n": [1, 2]})), tools={"flaky": flaky}
    )
    assert out.values == [1, 2]
    assert attempts.count(1) == 2 and attempts.count(2) == 2


def test_an_id_only_operation_says_how_to_run_it(three):
    with pytest.raises(KeyError, match="names its tool"):
        op("score")[mod.map()](grid(three))


def test_no_orchestration_gives_a_single_value():
    assert score[()].run({"n": 4}) == 40


def test_sweep_generates_its_own_grid():
    @tool
    def cell(row):
        return f"{row['model']}/{row['window']}"

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
    assert isinstance(wf.step("raw"), Step)
    assert wf.inputs["raw"] is three, "the payload lives beside the Operation"


def test_declaring_stages_both_halves(three):
    wf = Workflow()
    wf["raw"] = three
    step = wf.step("raw")
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
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(over=wf["raw"])]
    with pytest.raises(ValueError, match="which has not run"):
        wf.run("scored")


def test_pending_lists_what_must_run_first(three):
    @tool
    def again(row):
        return row["value"] + 1

    wf = Workflow()
    wf["raw"] = three
    wf["b"] = score[mod.map(over=wf["raw"])]
    wf["c"] = again[mod.map(over=wf["b"])]
    assert wf.pending("c") == ["raw", "b"]
    assert wf.pending("raw") == []


def test_run_all_orders_the_chain(three):
    @tool
    def again(row):
        return row["value"] + 1

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
    def again(row):
        return row["value"] + 1

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


def test_declaring_a_non_operation_object_is_a_source_step():
    wf = Workflow()
    wf["xs"] = [1, 2, 3]
    assert wf.step("xs").output.meta["expected"] == 3


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


def test_staging_is_a_pure_function_of_structure_plus_inputs(three):
    """The round-trip invariant: re-declaring from an export re-derives staging."""
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(over=wf["raw"])]
    blob = wf.to_session_dict()
    back = Workflow.from_dict(blob, {"score": score.fn})
    for sid in wf.steps:
        assert back.step(sid).describe() == wf.step(sid).describe()
        assert back.step(sid).output.meta["expected"] == wf.step(sid).output.meta["expected"]


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
    assert json.loads(ran.to_session_json())["inputs"]["raw"]["kind"] == "frame"
