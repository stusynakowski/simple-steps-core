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

from simple_steps_core import grid as grid_module
from simple_steps_core.grid import (
    BUILTIN_TOOLS,
    DECORATORS,
    DEFAULT_PAYLOAD,
    MODIFIERS,
    SHAPE_VERBS,
    Modifier,
    Operation,
    Output,
    PayloadError,
    ROWS_RULE,
    Step,
    StepRef,
    Workflow,
    TOOLS,
    annotation_problems,
    catalog,
    compile_operation,
    grid,
    infer_verb,
    predicted_columns,
    identity,
    is_shape,
    mod,
    op,
    rows,
    slice_,
    sort_,
    distinct_,
    rename_,
    tool,
    widen_,
    declaration_problems,
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
def sum_up(acc, n):
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


def test_step_refs_never_survive_into_the_export():
    """A ref is kept in memory (it knows its workflow) and flattened for JSON."""
    stored = score[mod.map(over=StepRef("videos"))]
    assert isinstance(stored.modifiers[0].params["over"], StepRef)
    assert stored.to_dict()["modifiers"][0]["params"]["over"] == "videos"
    json.dumps(stored.to_dict())


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


# ─────────────────────────────────────────────────────────────────────────
# select — the column-axis mirror of filter, and it applies no tool
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def wide():
    return pd.DataFrame({"city": ["Oslo", "Cairo"], "celsius": [-5, 38],
                         "note": ["a", "b"]})


def test_select_keeps_and_reorders(wide):
    wf = Workflow()
    wf["raw"] = wide
    wf["narrow"] = op("identity")[mod.select(columns=["celsius", "city"], over=wf["raw"])]
    wf.run_all()
    assert list(wf.step("narrow").output.data.columns) == ["celsius", "city"]


def test_drop_is_its_own_verb(wide):
    wf = Workflow()
    wf["raw"] = wide
    wf["less"] = op("identity")[mod.drop(columns=["note"], over=wf["raw"])]
    wf.run_all()
    assert list(wf.step("less").output.data.columns) == ["city", "celsius"]


def test_drop_keeps_the_remaining_order(wide):
    wf = Workflow()
    wf["raw"] = wide
    wf["less"] = op("identity")[mod.drop(columns=["celsius"], over=wf["raw"])]
    wf.run_all()
    assert list(wf.step("less").output.data.columns) == ["city", "note"]


def test_dropping_a_column_that_is_not_there_is_a_typo_not_a_no_op(wide):
    wf = Workflow()
    wf["raw"] = wide
    wf["typo"] = op("identity")[mod.drop(columns=["nte"], over=wf["raw"])]
    assert not wf.step("typo").valid
    assert "drop names 'nte'" in wf.step("typo").problems[0]
    with pytest.raises(KeyError, match="drop names 'nte'"):
        op("identity")[mod.drop(columns=["nte"])](wide)


def test_drop_applies_no_tool(wide):
    with pytest.raises(ValueError, match="drop applies no tool"):
        score[mod.drop(columns=["note"])](wide)


def test_both_column_verbs_need_their_columns(wide):
    with pytest.raises(ValueError, match="select needs columns="):
        op("identity")[mod.select()](wide)
    with pytest.raises(ValueError, match="drop needs columns="):
        op("identity")[mod.drop()](wide)


def test_select_predicts_its_columns_exactly_including_order(wide):
    """The one verb that knows its output columns without seeing the data."""
    wf = Workflow()
    wf["raw"] = wide
    wf["narrow"] = op("identity")[mod.select(columns=["celsius", "city"], over=wf["raw"])]
    wf["less"] = op("identity")[mod.drop(columns=["note"], over=wf["raw"])]
    staged = {sid: wf.step(sid).output.meta["columns"] for sid in ("narrow", "less")}
    wf.run_all()
    for sid, predicted in staged.items():
        assert predicted == list(wf.step(sid).output.data.columns), sid


def test_select_keeps_every_row(wide):
    wf = Workflow()
    wf["raw"] = wide
    wf["narrow"] = op("identity")[mod.select(columns=["city"], over=wf["raw"])]
    wf.run_all()
    assert len(wf.step("narrow").output.data) == 2
    assert wf.step("narrow").output.meta["payload"] is None


def test_select_applies_no_tool(wide):
    with pytest.raises(ValueError, match="select applies no tool"):
        score[mod.select(columns=["n"])](wide)


def test_select_cannot_keep_a_column_the_input_lacks(wide):
    wf = Workflow()
    wf["raw"] = wide
    wf["bad"] = op("identity")[mod.select(columns=["nope"], over=wf["raw"])]
    assert not wf.step("bad").valid
    assert "select names 'nope'" in wf.step("bad").problems[0]


def test_is_identity_sees_through_the_adapter():
    from simple_steps_core.grid import _d_apply, is_identity
    assert is_identity(identity)
    assert is_identity(_d_apply(identity))
    assert not is_identity(_d_apply(score.fn))


def test_select_is_a_shape_verb_so_it_cannot_share_a_step(wide):
    wf = Workflow()
    wf["raw"] = wide
    wf["both"] = op("identity")[mod.select(columns=["city"], over=wf["raw"]), mod.map()]
    assert "at most one is allowed" in wf.step("both").problems[0]


def test_source_applies_no_tool():
    with pytest.raises(ValueError, match="source applies no tool"):
        score[mod.source()](pd.DataFrame({"n": [1]}))


# ─────────────────────────────────────────────────────────────────────────
# builtins and bare modifiers — the tool that discards nothing
# ─────────────────────────────────────────────────────────────────────────
BUILTIN_IDS = {"identity", "gather", "count", "total", "first", "last"}


def test_the_catalog_describes_every_builtin():
    """First lines are user-facing sentences, because a palette shows them."""
    described = catalog()
    assert BUILTIN_IDS <= set(described)
    for name in BUILTIN_IDS:
        entry = described[name]
        assert entry["description"][0].isupper(), name
        assert entry["description"].endswith("."), name
        assert entry["origin"] == "builtin", name


def test_the_catalog_separates_system_tools_from_declared_ones():
    described = catalog()
    assert described["score"]["origin"] == "declared"
    assert described["identity"]["origin"] == "builtin"


def test_a_catalog_entry_carries_what_a_form_needs():
    entry = catalog()["score"]          # score(n, weight=1) — unannotated
    assert entry["params"] == [
        {"name": "n", "required": True, "default": None, "type": None},
        {"name": "weight", "required": False, "default": 1, "type": None},
    ]
    assert entry["takes_whole_row"] is False
    assert entry["returns"] is None
    assert entry["typed"] is False


def test_a_catalog_entry_publishes_a_typed_tools_boundary():
    """The palette says what goes in and what comes out, not just the names."""
    @tool(strict=True)
    def celsius_to_f(celsius: float) -> float:
        """Convert one reading."""
        return celsius * 9 / 5 + 32

    entry = catalog()["celsius_to_f"]
    assert entry["params"] == [
        {"name": "celsius", "required": True, "default": None, "type": "float"},
    ]
    assert entry["returns"] == "float"
    assert entry["typed"] is True


def test_a_whole_row_tool_is_flagged_in_the_catalog():
    assert catalog()["identity"]["takes_whole_row"] is True


def test_the_catalog_is_json_safe():
    json.dumps(catalog())


def test_a_user_tool_cannot_shadow_a_builtin():
    with pytest.raises(ValueError, match="is a builtin tool"):
        @tool
        def identity(**row):
            return row


def test_a_bare_shape_verb_is_a_complete_step():
    wf = Workflow()
    wf["xs"] = pd.DataFrame({"n": [1, 2, 3, 4]})
    wf["all"] = mod.collapse(over=wf["xs"])
    assert wf.step("all").operation.tool_id == "gather"
    wf.run_all()
    assert wf.step("all").output.item() == [1, 2, 3, 4]


def test_collapse_defaults_to_gather_and_expand_to_identity():
    """The two are exact inverses once each has the tool that discards nothing."""
    wf = Workflow()
    wf["xs"] = pd.DataFrame({"n": [1, 2, 3, 4]})
    wf["one"] = mod.collapse(over=wf["xs"])
    wf["back"] = mod.expand(over=wf["one"])
    wf.run_all()
    assert wf.step("one").output.item() == [1, 2, 3, 4]
    assert wf.step("back").output.values == [1, 2, 3, 4]


@pytest.mark.parametrize("tool_id, expected", [
    ("gather", [1, 2, 3, 4]), ("count", 4), ("total", 10),
    ("first", 1), ("last", 4),
])
def test_the_builtin_reducers(tool_id, expected):
    wf = Workflow()
    wf["xs"] = pd.DataFrame({"n": [1, 2, 3, 4]})
    wf["out"] = op(tool_id)[mod.collapse(over=wf["xs"])]
    wf.run_all()
    assert wf.step("out").output.item() == expected


def test_reducers_work_on_any_payload_column():
    """They resolve the payload like identity, not by demanding a 'value' column."""
    wf = Workflow()
    wf["xs"] = pd.DataFrame({"celsius": [1, 2, 3]})
    wf["sum"] = op("total")[mod.collapse(over=wf["xs"])]
    wf.run_all()
    assert wf.step("sum").output.item() == 6


def test_an_execution_modifier_alone_is_refused():
    wf = Workflow()
    with pytest.raises(TypeError, match="changes nothing on its own"):
        wf["bad"] = mod.retry(times=2)


def test_a_bare_modifier_no_longer_becomes_a_source_step():
    """It used to build a source step whose payload was the Modifier object."""
    wf = Workflow()
    wf["xs"] = pd.DataFrame({"n": [1, 2]})
    wf["flat"] = mod.expand(over=wf["xs"])
    assert wf.step("flat").operation.shape_verb.kind == "expand"
    assert wf.step("flat").operation.tool_id == "identity"


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
    wf["sum"] = sum_up(wf["raw"])          # sum_up(acc, n) — acc is not a column
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


def test_inference_reads_a_carried_through_column_while_staged(three):
    """`sum_up(acc, n)` reduces over a column that merely passes through."""
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score(wf["raw"])
    assert sum_up(wf["scored"]).shape_verb.kind == "collapse"   # staged
    wf.run_all()
    assert sum_up(wf["scored"]).shape_verb.kind == "collapse"   # and after


def test_staged_prediction_matches_what_actually_appears(three):
    """The invariant worth protecting: predicting is not guessing — order too."""
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score(wf["raw"])
    wf["kept"] = keep[mod.filter()](wf["scored"])
    wf["narrow"] = op("identity")[mod.select(columns=["value", "n"], over=wf["kept"])]
    wf["thin"] = op("identity")[mod.drop(columns=["n"], over=wf["kept"])]
    wf["sum"] = sum_up[mod.collapse()](wf["kept"])
    predicted = {sid: predicted_columns(st.output) for sid, st in wf.steps.items()}
    wf.run_all()
    for sid, step in wf.steps.items():
        assert predicted[sid] == list(step.output.data.columns), sid


def test_naming_the_payload_column_is_predicted_too(three):
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(name="score")](wf["raw"])
    assert predicted_columns(wf.step("scored").output) == ["n", "score"]
    wf.run_all()
    assert list(wf.step("scored").output.data.columns) == ["n", "score"]


def test_filter_carries_columns_through_and_writes_none(three):
    wf = Workflow()
    wf["raw"] = three
    wf["kept"] = keep[mod.filter()](wf["raw"])
    assert wf.step("kept").output.meta["payload"] is None
    assert predicted_columns(wf.step("kept").output) == ["n"]


def test_inference_reads_a_list_return_as_expand():
    @tool
    def words(note) -> list[str]:
        return note.split()

    wf = Workflow()
    wf["notes"] = pd.DataFrame({"note": ["clear sky", "heavy rain today"]})
    wf["word"] = words(wf["notes"])
    assert wf.step("word").operation.shape_verb.kind == "expand"
    wf.run_all()
    assert wf.step("word").output.values == ["clear", "sky", "heavy", "rain", "today"]


def test_inference_handles_string_annotations():
    """`from __future__ import annotations` makes annotations strings; inference
    must read "bool"/"list" the same as the real types, or a tools file with
    future annotations silently loses filter/expand inference."""
    @tool
    def is_big(n) -> "bool":
        return n > 1

    @tool
    def split_it(note) -> "list[str]":
        return note.split()

    assert infer_verb(is_big.fn, grid(pd.DataFrame({"n": [1, 2]})), {})[0] == "filter"
    assert infer_verb(split_it.fn, grid(pd.DataFrame({"note": ["a b"]})), {})[0] == "expand"


def test_an_explicit_verb_overrides_what_would_be_inferred():
    @tool
    def words(note) -> list[str]:
        return note.split()

    wf = Workflow()
    wf["notes"] = pd.DataFrame({"note": ["clear sky"]})
    wf["as_lists"] = words[mod.map()](wf["notes"])     # I really want a column of lists
    assert wf.step("as_lists").operation.shape_verb.kind == "map"
    wf.run_all()
    assert wf.step("as_lists").output.values == [["clear", "sky"]]


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


def test_a_declared_tool_resolves_by_id(three):
    """@tool registers it, so a workflow loaded from JSON needs no tools map."""
    assert TOOLS["score"] is score.fn
    assert op("score")[mod.map()](grid(three)).values == [10, 20, 30]


def test_an_unknown_tool_says_how_to_supply_it(three):
    with pytest.raises(KeyError, match="names its tool"):
        op("never_declared")[mod.map()](grid(three))


def test_an_explicit_tool_overrides_the_registry(three):
    out = op("score")[mod.map()].run(grid(three), tools={"score": lambda n: n})
    assert out.values == [1, 2, 3]


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
        (lambda ref: sum_up[mod.collapse(over=ref)], "one", "collapse sum_up · 1 cell"),
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
    wf["sum"] = sum_up[mod.collapse(over=wf["raw"])]   # sum_up(acc, n)
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


def test_two_shape_verbs_in_one_step_are_refused(three):
    """§11: an intermediate grid has no cell address, so it cannot be re-driven."""
    wf = Workflow()
    wf["raw"] = three
    wf["both"] = score[mod.map(over=wf["raw"]), mod.filter()]
    assert not wf.step("both").valid
    assert "at most one is allowed" in wf.step("both").problems[0]


def test_one_shape_verb_with_execution_modifiers_is_fine(three):
    wf = Workflow()
    wf["raw"] = three
    wf["ok"] = score[mod.map(over=wf["raw"]), mod.retry(times=2), mod.timeout(seconds=5)]
    assert wf.step("ok").valid


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
    # A list is one cell, not one row per element — reshape with expand.
    assert len(wf.step("xs").output.data) == 1
    assert wf.step("xs").output.data["value"].iloc[0] == [1, 2, 3]


def test_a_list_source_expands_into_rows():
    wf = Workflow()
    wf["xs"] = [1, 2, 3]                       # one cell holding the list
    wf["rows"] = mod.expand(over=wf["xs"])     # the explicit reshape
    wf.run_all()
    assert wf.step("rows").output.values == [1, 2, 3]


def test_a_dict_source_is_one_cell_widen_spreads_it():
    wf = Workflow()
    wf["d"] = {"a": 1, "b": 2}                 # one cell holding the dict
    assert len(wf.step("d").output.data) == 1
    wf["wide"] = mod.widen(over=wf["d"], columns=["a", "b"])
    wf.run_all()
    assert wf.step("wide").output.data["a"].iloc[0] == 1
    assert wf.step("wide").output.data["b"].iloc[0] == 2


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


# ─────────────────────────────────────────────────────────────────────────
# typing: the tool's declared boundary, and what it is checked against
# ─────────────────────────────────────────────────────────────────────────
def test_strict_typing_refuses_an_unannotated_tool():
    with pytest.raises(TypeError, match="is not fully typed"):
        @tool(strict=True)
        def untyped(n):
            return n


def test_strict_typing_names_every_gap_at_once():
    @tool(strict=False)
    def half(n: int, weight):
        return n

    assert annotation_problems(half.fn) == [
        "parameter 'weight' has no type annotation",
        "it has no return annotation",
    ]


def test_strict_typing_exempts_a_whole_row_tool():
    """**kwargs has no per-column parameter to annotate; the return still does."""
    @tool(strict=True)
    def whole(**row: object) -> int:
        return len(row)

    assert catalog()["whole"]["typed"] is True


def test_strict_types_can_be_turned_on_globally(monkeypatch):
    monkeypatch.setattr(grid_module, "STRICT_TYPES", True)
    with pytest.raises(TypeError, match="is not fully typed"):
        @tool
        def bare(n):
            return n


def test_a_bound_literal_is_checked_against_its_annotation():
    @tool(strict=True)
    def scaled(n: int, factor: int = 2) -> int:
        return n * factor

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"n": [1, 2]})
    wf["bad"] = scaled.bind(factor="three")[mod.map(over=wf["raw"])]
    assert "declares factor: int" in wf.step("bad").problems[0]
    assert "'three'" in wf.step("bad").problems[0]


def test_an_upstream_dtype_is_checked_against_its_annotation():
    @tool(strict=True)
    def needs_number(city: float) -> float:
        return city * 2

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"city": ["SF", "NYC"]})
    wf["bad"] = needs_number[mod.map(over=wf["raw"])]
    problem = wf.step("bad").problems[0]
    assert "declares city: float" in problem
    assert "'raw' has city as str" in problem


def test_an_int_column_satisfies_a_float_parameter():
    """Widening is not a mismatch — refusing it would reject a step that runs."""
    @tool(strict=True)
    def halve(n: float) -> float:
        return n / 2

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"n": [1, 2]})
    wf["ok"] = halve[mod.map(over=wf["raw"])]
    assert wf.step("ok").problems == ()
    wf.run("ok")
    assert wf.step("ok").output.values == [0.5, 1.0]


def test_an_undecidable_annotation_is_not_a_problem():
    @tool(strict=True)
    def anything(value: object) -> object:
        return value

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"value": [object(), object()]})
    wf["ok"] = anything[mod.map(over=wf["raw"])]
    assert wf.step("ok").problems == ()


def test_dtype_checking_waits_for_the_upstream_to_run():
    """Same timing rule as the missing-column check: a staged Output has no dtypes."""
    @tool(strict=True)
    def to_f(celsius: float) -> float:
        return celsius * 9 / 5 + 32

    @tool(strict=True)
    def needs_text(fahrenheit: str) -> str:
        return fahrenheit.upper()

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"celsius": [1.0, 2.0]})
    wf["f"] = to_f[mod.map(over=wf["raw"], name="fahrenheit")]
    wf["bad"] = needs_text[mod.map(over=wf["f"])]
    assert wf.step("bad").problems == (), "staged upstream: nothing to check yet"

    wf.run("f")
    wf["bad"] = needs_text[mod.map(over=wf["f"])]
    assert "declares fahrenheit: str" in wf.step("bad").problems[0]


def test_a_string_column_satisfies_a_string_parameter():
    """The guard against the obvious false positive: str on a text column."""
    @tool(strict=True)
    def shout(city: str) -> str:
        return city.upper()

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"city": ["SF", "NYC"]})
    wf["ok"] = shout[mod.map(over=wf["raw"])]
    assert wf.step("ok").problems == ()
    wf.run("ok")
    assert wf.step("ok").output.values == ["SF".upper(), "NYC".upper()]


def test_a_list_column_satisfies_a_list_parameter():
    @tool(strict=True)
    def size(xs: list) -> int:
        return len(xs)

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"xs": [[1, 2], [3]]})
    wf["ok"] = size[mod.map(over=wf["raw"])]
    assert wf.step("ok").problems == ()
    wf.run("ok")
    assert wf.step("ok").output.values == [2, 1]


def test_a_collapse_accumulator_is_not_type_checked_against_a_column():
    """The verb supplies acc, so it is never bound from the grid."""
    @tool(strict=True)
    def add_up(acc: float | None, n: int) -> float:
        return (acc or 0) + n

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"n": [1, 2, 3]})
    wf["sum"] = add_up[mod.collapse(over=wf["raw"])]
    assert wf.step("sum").problems == ()
    wf.run("sum")
    assert wf.step("sum").output.item() == 6


# ─────────────────────────────────────────────────────────────────────────
# provenance: a reference belongs to the workflow it was read from
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def two_workflows():
    """Two workflows with a same-named step holding different data."""
    a, b = Workflow(), Workflow()
    a["raw"] = pd.DataFrame({"n": [1, 2, 3]})
    b["raw"] = pd.DataFrame({"n": [100, 200]})
    return a, b


def test_a_ref_carries_the_workflow_it_was_read_from(two_workflows):
    """No side channel: the ref itself is what stays in params."""
    a, _ = two_workflows
    assert a["raw"].workflow is a
    assert score[mod.map(over=a["raw"])].modifiers[0].params["over"].workflow is a


def test_provenance_is_not_part_of_the_data(two_workflows):
    """Naming a step two ways must not change equality or the export."""
    a, _ = two_workflows
    from_ref = score[mod.map(over=a["raw"])]
    from_str = score[mod.map(over="raw")]
    assert from_ref == from_str
    assert from_ref.to_dict() == from_str.to_dict()
    assert from_str.modifiers[0].params["over"] == "raw"


def test_a_ref_from_another_workflow_is_refused(two_workflows):
    """The silent case: both have 'raw', so nothing else would have caught it."""
    a, b = two_workflows
    b["x"] = score[mod.map()](a["raw"])
    assert "reads a different Workflow" in b.step("x").problems[0]


def test_a_borrowed_ref_cannot_run(two_workflows):
    a, b = two_workflows
    b["x"] = score[mod.map()](a["raw"])
    with pytest.raises(ValueError, match="reads a different Workflow"):
        b.run("x")


def test_the_over_form_is_refused_the_same_way(two_workflows):
    a, b = two_workflows
    b["x"] = score[mod.map(over=a["raw"])]
    assert "reads a different Workflow" in b.step("x").problems[0]


def test_a_borrowed_bare_shape_verb_is_refused(two_workflows):
    a, b = two_workflows
    b["flat"] = mod.collapse(over=a["raw"])
    assert "reads a different Workflow" in b.step("flat").problems[0]


def test_provenance_is_diagnosed_before_a_dangling_reference(two_workflows):
    """Borrowing is the root cause, so it must be problems[0], not the symptom."""
    a, _ = two_workflows
    c = Workflow()
    c["other"] = pd.DataFrame({"n": [9]})
    c["x"] = score[mod.map()](a["raw"])
    assert "reads a different Workflow" in c.step("x").problems[0]


def test_a_string_ref_means_whatever_is_here(two_workflows):
    """The escape hatch: no origin, so no provenance to violate."""
    a, b = two_workflows
    b["x"] = score[mod.map(over="raw")]
    assert b.step("x").problems == ()
    b.run("x")
    assert b.step("x").output.values == [1000, 2000], "ran on b's own raw"


def test_an_operation_with_a_string_ref_is_reusable(two_workflows):
    a, b = two_workflows
    template = score[mod.map(over="raw")]
    a["x"] = template
    b["x"] = template
    assert a.step("x").problems == () and b.step("x").problems == ()


def test_a_reloaded_workflow_has_no_stale_provenance(ran):
    """from_dict rebuilds refs as plain strings, so an import is never self-flagged."""
    back = Workflow.from_json(ran.to_session_json(), TOOLS)
    assert all(p == () for p in back.validate().values())
    assert all(not isinstance(m.params.get("over"), StepRef)
               for step in back.steps.values()
               for m in step.operation.modifiers)


def test_a_stale_ref_into_an_imported_workflow_is_refused(ran):
    """Export, import as a second workflow, then use the ORIGINAL's ref."""
    imported = Workflow.from_json(ran.to_session_json(), TOOLS)
    imported["late"] = score[mod.map()](ran["raw"])      # ran, not imported
    assert "reads a different Workflow" in imported.step("late").problems[0]


def test_an_imported_workflow_extends_with_its_own_refs(ran):
    imported = Workflow.from_json(ran.to_session_json(), TOOLS)
    imported["late"] = score[mod.map(name="again")](imported["raw"])
    assert imported.step("late").problems == ()
    imported.run("late")
    assert imported.step("late").output.values == [10, 20, 30]


def test_a_session_round_trip_preserves_dtypes():
    """JSON carries no types, so they are recorded beside the data.

    This went from cosmetic to load-bearing when annotations started being
    checked against real dtypes: a float column of whole numbers came back
    int64, which could change a step's verdict after a reload.
    """
    @tool(strict=True)
    def to_f(celsius: float) -> float:
        """C to F."""
        return celsius * 9 / 5 + 32

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"celsius": [18.0, 31.0],      # whole floats
                              "city": ["SF", "NYC"],
                              "n": [1, 2],
                              "flag": [True, False]})
    wf["f"] = to_f[mod.map(name="fahrenheit")](wf["raw"])
    wf.run_all()

    back = Workflow.from_json(wf.to_session_json(), TOOLS)
    for sid in ("raw", "f"):
        before, after = wf.step(sid).output.data, back.step(sid).output.data
        assert list(before.dtypes) == list(after.dtypes), sid
        assert list(before.columns) == list(after.columns), sid
    assert list(wf.step("f").output.ledger.dtypes) == \
           list(back.step("f").output.ledger.dtypes)


def test_an_export_without_dtypes_still_decodes():
    """Exports written before dtypes were recorded keep working."""
    from simple_steps_core.grid import _decode
    frame = _decode({"kind": "frame",
                     "data": pd.DataFrame({"a": [1, 2]}).to_json(orient="split")})
    assert list(frame["a"]) == [1, 2]


def test_a_repr_does_not_depend_on_how_a_step_was_named(two_workflows):
    """A ref lives in params, so a repr must flatten it like __eq__ does."""
    a, _ = two_workflows
    assert repr(score[mod.map()](a["raw"])) == repr(score[mod.map(over="raw")])
    assert "over='raw'" in repr(score[mod.map(over=a["raw"])])


def test_a_problem_message_names_the_step_not_the_ref(two_workflows):
    @tool(strict=True)
    def needs_absent(nope: int) -> int:
        """Asks for a column that is not there."""
        return nope

    a, _ = two_workflows
    a["x"] = needs_absent[mod.map()](a["raw"])
    assert "which 'raw' does not have" in a.step("x").problems[0]


# ─────────────────────────────────────────────────────────────────────────
# an empty result is "ran and produced nothing", not "has not run"
# ─────────────────────────────────────────────────────────────────────────
def test_an_expand_to_nothing_keeps_its_columns_and_their_dtypes():
    """`filter` keeps its columns when it drops every row; expand must agree.

    `DataFrame([])` has no columns, which made a downstream step report "it has
    no columns" rather than "it is empty" — two different problems.
    """
    @tool(strict=True)
    def nothing(n: int) -> list:
        """Always expands to nothing."""
        return []

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"n": [1, 2], "city": ["a", "b"]})
    wf["gone"] = nothing[mod.expand()](wf["raw"])
    wf.run("gone")

    out = wf.step("gone").output.data
    assert len(out) == 0
    assert list(out.columns) == ["n", "city", "value"]
    # carried dtypes survive, so a downstream annotation is not falsely refused
    assert out["n"].dtype == wf.step("raw").output.data["n"].dtype


def test_a_downstream_step_of_an_empty_expand_still_validates_and_runs():
    @tool(strict=True)
    def nothing(n: int) -> list:
        """Expands to nothing."""
        return []

    @tool(strict=True)
    def dbl(n: int) -> int:
        """Double."""
        return n * 2

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"n": [1, 2]})
    wf["gone"] = nothing[mod.expand()](wf["raw"])
    wf.run("gone")
    wf["after"] = dbl[mod.map()](wf["gone"])
    assert wf.step("after").problems == ()
    wf.run("after")
    assert wf.step("after").status == "completed"


def test_a_step_that_ran_to_zero_rows_reports_completed():
    """An empty ledger cannot say which; meta['staged'] is what distinguishes."""
    @tool(strict=True)
    def nothing(n: int) -> list:
        """Expands to nothing."""
        return []

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"n": [1, 2]})
    wf["gone"] = nothing[mod.expand()](wf["raw"])
    assert wf.step("gone").status == "staged", "before running"
    wf.run("gone")
    assert wf.step("gone").status == "completed", "ran, and legitimately empty"


def test_a_filter_that_keeps_nothing_agrees_with_expand():
    @tool(strict=True)
    def never(n: int) -> bool:
        """Keeps nothing."""
        return False

    wf = Workflow()
    wf["raw"] = pd.DataFrame({"n": [1, 2], "city": ["a", "b"]})
    wf["none"] = never[mod.filter()](wf["raw"])
    wf.run("none")
    assert wf.step("none").status == "completed"
    assert list(wf.step("none").output.data.columns) == ["n", "city"]


# ─────────────────────────────────────────────────────────────────────────
# widen — one cell's fields become columns (unnest_wider to expand's longer)
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def records():
    return pd.DataFrame({"value": [{"city": "SF", "temp": 18.0},
                                   {"city": "NYC", "temp": 31.0}]})


def test_widen_lifts_fields_into_columns(records):
    wf = Workflow()
    wf["raw"] = records
    wf["wide"] = mod.widen(columns=["city", "temp"], over=wf["raw"])
    wf.run_all()

    out = wf.step("wide").output.data
    assert list(out.columns) == ["value", "city", "temp"], "carried, then fields"
    assert list(out["city"]) == ["SF", "NYC"]
    assert list(out["temp"]) == [18.0, 31.0]
    assert list(out.index) == list(records.index), "1:1, index preserved"
    assert wf.step("wide").status == "completed"


def test_widen_predicts_its_columns_exactly(records):
    """The reason columns= is required: staging has to know them."""
    wf = Workflow()
    wf["raw"] = records
    wf["wide"] = mod.widen(columns=["city", "temp"], over=wf["raw"])
    predicted = predicted_columns(wf.step("wide").output)
    wf.run_all()
    assert predicted == list(wf.step("wide").output.data.columns)


def test_a_downstream_tool_binds_to_a_widened_field(records):
    @tool(strict=True)
    def to_f(temp: float) -> float:
        """C to F."""
        return temp * 9 / 5 + 32

    wf = Workflow()
    wf["raw"] = records
    wf["wide"] = mod.widen(columns=["city", "temp"], over=wf["raw"])
    wf.run("wide")
    wf["f"] = to_f[mod.map(name="fahrenheit")](wf["wide"])
    assert wf.step("f").problems == ()
    wf.run("f")
    assert wf.step("f").output.values == [64.4, 87.8]


def test_widen_needs_columns():
    with pytest.raises(ValueError, match="widen needs columns="):
        widen_(pd.DataFrame({"value": [{"a": 1}]}))


def test_widen_applies_no_tool(records):
    wf = Workflow()
    wf["raw"] = records
    wf["bad"] = score[mod.widen(columns=["city"], over=wf["raw"])]
    assert "widen applies no tool" in wf.step("bad").problems[0]


def test_widen_does_not_check_its_columns_against_the_upstream(records):
    """Its columns are the record's fields — they are not upstream by design."""
    wf = Workflow()
    wf["raw"] = records
    wf["wide"] = mod.widen(columns=["city", "temp"], over=wf["raw"])
    assert wf.step("wide").problems == ()


def test_a_non_mapping_cell_is_a_per_unit_failure():
    wf = Workflow()
    wf["raw"] = pd.DataFrame({"value": [{"a": 1}, 42]})
    wf["wide"] = mod.widen(columns=["a"], over=wf["raw"])
    wf.run_all()
    ledger = wf.step("wide").output.ledger
    assert list(ledger["status"]) == ["completed", "failed"]
    assert "needs a mapping per row" in ledger["error"].iloc[1]
    assert list(wf.step("wide").output.failed.index) == [1], "re-drivable"


def test_a_missing_field_is_a_per_unit_failure_not_a_crash():
    wf = Workflow()
    wf["raw"] = pd.DataFrame({"value": [{"a": 1, "b": 2}, {"a": 3}]})
    wf["wide"] = mod.widen(columns=["a", "b"], over=wf["raw"])
    wf.run_all()
    ledger = wf.step("wide").output.ledger
    assert list(ledger["status"]) == ["completed", "failed"]
    assert "has no 'b'" in ledger["error"].iloc[1]
    assert wf.step("wide").output.data["a"].iloc[1] == 3, "the rest still lifted"


def test_widen_round_trips(records):
    wf = Workflow()
    wf["raw"] = records
    wf["wide"] = mod.widen(columns=["city", "temp"], over=wf["raw"])
    wf.run_all()
    back = Workflow.from_json(wf.to_session_json(), TOOLS)
    assert all(p == () for p in back.validate().values())
    assert list(back.step("wide").output.data.columns) == ["value", "city", "temp"]
    assert back.to_dict()["steps"][1]["operation"]["modifiers"] == [
        {"kind": "widen", "params": {"columns": ["city", "temp"], "over": "raw"}}
    ]


def test_widen_is_one_shape_verb_like_the_rest(records):
    wf = Workflow()
    wf["raw"] = records
    wf["both"] = op("identity")[mod.widen(columns=["city"], over=wf["raw"]),
                                mod.map()]
    assert "at most one is allowed" in wf.step("both").problems[0]


def test_widen_a_tuple_cell_auto_names_c0_c1():
    """A column of tuples widens instead of failing — positional names."""
    wf = Workflow()
    wf["raw"] = pd.DataFrame({"value": [(10, 1), (20, 4)]})
    wf["wide"] = mod.widen(over=wf["raw"])          # no columns=
    wf.run_all()
    out = wf.step("wide").output
    assert list(out.data.columns) == ["value", "c0", "c1"]
    assert list(out.data["c0"]) == [10, 20] and list(out.data["c1"]) == [1, 4]
    assert set(out.ledger["status"]) == {"completed"}


def test_widen_a_tuple_with_explicit_columns_matches_by_position():
    wf = Workflow()
    wf["raw"] = pd.DataFrame({"value": [(10, 1), (20, 4)]})
    wf["wide"] = mod.widen(columns=["a", "b"], over=wf["raw"])
    wf.run_all()
    out = wf.step("wide").output.data
    assert list(out["a"]) == [10, 20] and list(out["b"]) == [1, 4]


def test_widen_ragged_tuples_auto_pad_with_none():
    wf = Workflow()
    wf["raw"] = pd.DataFrame({"value": [(1, 2, 3), (9,)]})
    wf["wide"] = mod.widen(over=wf["raw"])          # width = 3
    wf.run_all()
    out = wf.step("wide").output
    assert list(out.data.columns) == ["value", "c0", "c1", "c2"]
    assert out.data["c0"].tolist() == [1, 9]
    assert out.data["c2"].iloc[0] == 3 and pd.isna(out.data["c2"].iloc[1])
    assert set(out.ledger["status"]) == {"completed"}, "ragged is not a failure"


def test_widen_explicit_columns_too_many_for_a_short_tuple_is_a_failure():
    wf = Workflow()
    wf["raw"] = pd.DataFrame({"value": [(10, 1), (20,)]})
    wf["wide"] = mod.widen(columns=["a", "b"], over=wf["raw"])
    wf.run_all()
    ledger = wf.step("wide").output.ledger
    assert list(ledger["status"]) == ["completed", "failed"]
    assert "too few" in ledger["error"].iloc[1]


def test_widen_a_mapping_still_needs_columns():
    """Only sequences are auto-named; a record's fields are not guessed."""
    with pytest.raises(ValueError, match="widen needs columns="):
        widen_(pd.DataFrame({"value": [{"a": 1}]}))


# ─────────────────────────────────────────────────────────────────────────
def test_expand_refuses_a_dataframe_instead_of_yielding_column_names():
    """Iterating a DataFrame yields its columns — a silent wrong answer before."""
    @tool(strict=True)
    def frame(n: int) -> pd.DataFrame:
        """Returns a frame."""
        return pd.DataFrame({"city": ["SF"], "temp": [18]})

    wf = Workflow()
    wf["seed"] = pd.DataFrame({"n": [1]})
    wf["e"] = frame[mod.expand()](wf["seed"])
    wf.run("e")
    assert wf.step("e").status == "failed"
    assert "yields its column names" in wf.step("e").output.ledger["error"].iloc[0]


# ─────────────────────────────────────────────────────────────────────────
# F1 — a bound literal is a value, never a step reference
# ─────────────────────────────────────────────────────────────────────────
def test_binding_a_step_reference_is_refused():
    """It used to store the id string and fail per row with a type error."""
    wf = Workflow()
    wf["cutoff"] = pd.DataFrame({"k": [60.0]})
    with pytest.raises(TypeError, match="cannot bind 'weight' to a step reference"):
        score.bind(weight=wf["cutoff"])


def test_binding_a_step_reference_is_refused_on_an_operation_too():
    wf = Workflow()
    wf["cutoff"] = pd.DataFrame({"k": [60.0]})
    with pytest.raises(TypeError, match="step reference"):
        score[mod.map()].bind(weight=wf["cutoff"])


# ─────────────────────────────────────────────────────────────────────────
# F2/F3 — the declaration contract
# ─────────────────────────────────────────────────────────────────────────
def test_a_positional_only_parameter_is_refused():
    def poso(n, /):
        return n
    with pytest.raises(TypeError, match="positional-only"):
        tool(poso)


def test_a_var_positional_tool_is_refused():
    """*args silently received nothing and returned a plausible wrong answer."""
    def varargs(*args):
        return sum(args)
    with pytest.raises(TypeError, match=r"\*args declares no names"):
        tool(varargs)


def test_a_mutable_default_is_refused():
    def accum(n, seen=[]):
        seen.append(n)
        return len(seen)
    with pytest.raises(TypeError, match="mutable default"):
        tool(accum)


def test_a_tool_id_must_be_an_identifier():
    with pytest.raises(TypeError, match="not a valid identifier"):
        tool(lambda n: n)
    with pytest.raises(TypeError, match="not a valid identifier"):
        tool(id="my tool!")(lambda n: n)


def test_declaration_problems_reports_every_gap_at_once():
    def bad(n, /, *args, seen=[]):
        return n
    found = declaration_problems(bad, "bad")
    assert len(found) == 3, found


def test_a_duplicate_tool_id_warns_rather_than_raising():
    @tool
    def dupe_a(n):
        return 1
    with pytest.warns(UserWarning, match="already declared"):
        @tool(id="dupe_a")
        def dupe_b(n):
            return 2


def test_redeclaring_the_same_function_does_not_warn():
    """Re-running a notebook cell is the common case and must stay quiet."""
    @tool
    def same_fn(n):
        return n
    import warnings as _w
    with _w.catch_warnings():
        _w.simplefilter("error")
        tool(same_fn.fn)


# ─────────────────────────────────────────────────────────────────────────
# F4/F5 — a modifier's own parameters are checked, by name and by type
# ─────────────────────────────────────────────────────────────────────────
def test_an_unknown_modifier_parameter_is_caught_at_declaration(three):
    wf = Workflow()
    wf["raw"] = three
    wf["t"] = score[mod.map(nmae="s")](wf["raw"])
    assert "map takes no parameter 'nmae'" in wf.step("t").problems[0]
    assert "it accepts axis, name, over, retries" in wf.step("t").problems[0]


def test_sweep_accepts_arbitrary_parameter_names(three):
    """Its parameters are the user's own, so names cannot be validated."""
    @tool
    def cell(model, window):
        return f"{model}{window}"
    wf = Workflow()
    wf["s"] = cell[mod.sweep(model=["a"], window=[1])]
    assert wf.step("s").problems == ()


def test_a_swept_parameter_cannot_shadow_the_verbs_own(three):
    @tool
    def labelled(name):
        return name
    wf = Workflow()
    wf["s"] = labelled[mod.sweep(name=["a", "b"])]
    assert "must be str, got list" in wf.step("s").problems[0]
    assert "collides with the verb's own" in wf.step("s").problems[0]


def test_a_bool_does_not_satisfy_an_int_parameter(three):
    wf = Workflow()
    wf["raw"] = three
    wf["s"] = mod.slice(stop=True, over=wf["raw"])
    assert "stop= must be int, got bool" in wf.step("s").problems[0]


def test_a_bool_parameter_accepts_a_bool(three):
    wf = Workflow()
    wf["raw"] = three
    wf["s"] = mod.sort(by="n", ascending=False, over=wf["raw"])
    assert wf.step("s").problems == ()


# ─────────────────────────────────────────────────────────────────────────
# F6/F7 — staged claims that depend on the verb's own parameters
# ─────────────────────────────────────────────────────────────────────────
def test_collapse_by_stages_as_one_per_group_not_one_cell(three):
    @tool
    def hemi(n):
        return "lo" if n < 3 else "hi"

    wf = Workflow()
    wf["raw"] = three
    wf["g"] = hemi[mod.group(name="h")](wf["raw"])
    wf.run_all()
    wf["c"] = sum_up[mod.collapse(by="h", over=wf["g"])]
    assert "one cell per group" in wf.step("c").describe()
    wf.run("c")
    assert wf.step("c").describe().endswith("2 cells")


def test_sweep_stages_its_exact_count_from_its_own_parameters():
    @tool
    def cell(model, window):
        return f"{model}{window}"
    wf = Workflow()
    wf["s"] = cell[mod.sweep(model=["a", "b"], window=[7, 30, 90])]
    assert wf.step("s").describe().endswith("6 cells"), wf.step("s").describe()
    assert len(wf.step("s").output.ledger) == 6, "addresses are known in advance"
    wf.run("s")
    assert len(wf.step("s").output.data) == 6


# ─────────────────────────────────────────────────────────────────────────
# F8 — a RangeIndex survives a session round trip
# ─────────────────────────────────────────────────────────────────────────
def test_a_range_index_round_trips_as_a_range_index(ran):
    back = Workflow.from_json(ran.to_session_json(), TOOLS)
    for sid in ran.steps:
        before, after = ran.step(sid).output.data, back.step(sid).output.data
        assert type(before.index) is type(after.index), sid
        assert before.equals(after), sid


def test_a_labelled_index_is_not_turned_into_a_range(three):
    wf = Workflow()
    wf["raw"] = pd.DataFrame({"n": [1, 2]}, index=["p", "q"])
    wf["s"] = score[mod.map(over=wf["raw"])]
    wf.run_all()
    back = Workflow.from_json(wf.to_session_json(), TOOLS)
    assert list(back.step("s").output.data.index) == ["p", "q"]


# ─────────────────────────────────────────────────────────────────────────
# B2 — wf[0] is positional sugar that resolves to an id
# ─────────────────────────────────────────────────────────────────────────
def test_a_workflow_can_be_indexed_by_position(three):
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map(over=wf["raw"])]
    assert wf[0] == wf["raw"]
    assert wf[-1] == wf["scored"]


def test_a_positional_reference_stores_the_id_not_the_position(three):
    """Positions shift when a step is inserted; a stored id cannot."""
    wf = Workflow()
    wf["raw"] = three
    wf["scored"] = score[mod.map()](wf[0])
    assert wf.step("scored").operation.to_dict()["modifiers"][0]["params"]["over"] == "raw"


def test_an_int_is_a_position_and_a_string_is_a_name():
    wf = Workflow()
    wf["0"] = pd.DataFrame({"n": [7]})
    wf["b"] = pd.DataFrame({"n": [8]})
    assert wf["0"].id == "0", "a step named '0' stays reachable"
    assert wf[1].id == "b", "an int counts"


def test_a_position_past_the_end_says_so(three):
    wf = Workflow()
    wf["raw"] = three
    with pytest.raises(KeyError, match="no step at position 9"):
        wf[9]


# ─────────────────────────────────────────────────────────────────────────
# B1/B3/B4 — slice, rename, sort, distinct
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def table():
    return pd.DataFrame({"city": ["Oslo", "Cairo", "Lima", "Cairo"],
                         "n": [3, 1, 2, 1]}, index=["p", "q", "r", "s"])


def test_slice_takes_rows_by_position(table):
    wf = Workflow()
    wf["raw"] = table
    wf["first2"] = mod.slice(stop=2, over=wf["raw"])
    wf["mid"] = mod.slice(start=1, stop=3, over=wf["raw"])
    wf["picked"] = mod.slice(at=[0, 3], over=wf["raw"])
    wf.run_all()
    assert list(wf.step("first2").output.data.index) == ["p", "q"]
    assert list(wf.step("mid").output.data.index) == ["q", "r"]
    assert list(wf.step("picked").output.data.index) == ["p", "s"]
    assert list(wf.step("first2").output.data.columns) == ["city", "n"]


def test_slice_promises_at_most_and_applies_no_tool(table):
    wf = Workflow()
    wf["raw"] = table
    wf["s"] = mod.slice(stop=2, over=wf["raw"])
    assert "at most 4 cells" in wf.step("s").describe()
    wf["bad"] = score[mod.slice(stop=2, over=wf["raw"])]
    assert "slice applies no tool" in wf.step("bad").problems[0]


def test_slice_refuses_both_forms_at_once(table):
    with pytest.raises(ValueError, match="at= or start=/stop="):
        slice_(table, at=[0], stop=2)


def test_slice_refuses_a_position_past_the_end(table):
    with pytest.raises(IndexError, match=r"names position\(s\) \[9\]"):
        slice_(table, at=[0, 9])


def test_rename_changes_names_and_keeps_order(table):
    wf = Workflow()
    wf["raw"] = table
    wf["r"] = mod.rename(columns={"n": "count"}, over=wf["raw"])
    assert predicted_columns(wf.step("r").output) == ["city", "count"]
    wf.run_all()
    out = wf.step("r").output.data
    assert list(out.columns) == ["city", "count"]
    assert list(out["count"]) == [3, 1, 2, 1]
    assert list(out.index) == list(table.index)


def test_rename_refuses_an_absent_column(table):
    wf = Workflow()
    wf["raw"] = table
    wf["r"] = mod.rename(columns={"nope": "x"}, over=wf["raw"])
    assert "which the input does not have" in wf.step("r").problems[0]


def test_rename_refuses_to_overwrite_an_existing_column(table):
    with pytest.raises(ValueError, match="would overwrite"):
        rename_(table, columns={"n": "city"})


def test_sort_reorders_rows_and_the_index_travels(table):
    wf = Workflow()
    wf["raw"] = table
    wf["asc"] = mod.sort(by="n", over=wf["raw"])
    wf["desc"] = mod.sort(by=["n"], ascending=False, over=wf["raw"])
    wf.run_all()
    assert list(wf.step("asc").output.data["n"]) == [1, 1, 2, 3]
    assert list(wf.step("desc").output.data["n"]) == [3, 2, 1, 1]
    assert set(wf.step("asc").output.data.index) == set(table.index)


def test_sort_accepts_one_column_or_several(table):
    assert list(sort_(table, by="n").data["n"]) == [1, 1, 2, 3]
    assert list(sort_(table, by=["city", "n"]).data["city"])[0] == "Cairo"


def test_sort_refuses_an_absent_column(table):
    wf = Workflow()
    wf["raw"] = table
    wf["s"] = mod.sort(by="nope", over=wf["raw"])
    assert "which the input does not have" in wf.step("s").problems[0]


def test_distinct_keeps_the_first_of_each_group(table):
    wf = Workflow()
    wf["raw"] = table
    wf["u"] = mod.distinct(columns=["city"], over=wf["raw"])
    wf.run_all()
    out = wf.step("u").output.data
    assert list(out["city"]) == ["Oslo", "Cairo", "Lima"]
    assert list(out.index) == ["p", "q", "r"], "the first occurrence keeps its address"


def test_distinct_over_the_whole_row_by_default():
    frame = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    assert len(distinct_(frame).data) == 2


def test_the_new_verbs_are_in_every_derived_table():
    for verb in ("slice", "rename", "sort", "distinct"):
        assert verb in MODIFIERS and verb in SHAPE_VERBS
        assert verb in DECORATORS and verb in ROWS_RULE
        assert verb in DEFAULT_PAYLOAD and DEFAULT_PAYLOAD[verb] is None


def test_the_new_verbs_round_trip(table):
    wf = Workflow()
    wf["raw"] = table
    wf["s"] = mod.slice(stop=2, over=wf["raw"])
    wf["r"] = mod.rename(columns={"n": "count"}, over=wf["s"])
    wf["o"] = mod.sort(by="count", over=wf["r"])
    wf["d"] = mod.distinct(columns=["city"], over=wf["o"])
    wf.run_all()
    back = Workflow.from_json(wf.to_session_json(), TOOLS)
    assert all(p == () for p in back.validate().values())
    assert list(back.step("d").output.data.columns) == ["city", "count"]


def test_a_bare_sweep_is_refused_for_the_right_reason():
    """It used to be called an execution modifier, which it is not."""
    wf = Workflow()
    with pytest.raises(TypeError, match="a shape verb with no default tool"):
        wf["s"] = mod.sweep(model=["a"])


def test_a_bare_execution_modifier_still_says_so():
    wf = Workflow()
    with pytest.raises(TypeError, match="an execution modifier"):
        wf["s"] = mod.retry(times=2)
