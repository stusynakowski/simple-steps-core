"""
Config components
=================

Editors for the four scope configs. They mirror the isolation rule the models
enforce (see ``docs/config-isolation.md``):

* :class:`OrchestrationConfig` — **shape**: how data fans out and comes back.
* :class:`StepExecutionConfig` — **conduct**: how the unit of work is carried out.
* :class:`StageExecutionConfig` / :class:`WorkflowExecutionConfig` — conduct at
  the stage and workflow scopes.

The configs are frozen, so every ``edit_*`` returns a **new** instance rather
than mutating. Each editor draws only the fields its own config owns — that is
what keeps the UI honest about the split.
"""

from __future__ import annotations

from simple_steps_core import (
    OrchestrationConfig,
    StageExecutionConfig,
    StepExecutionConfig,
    WorkflowExecutionConfig,
)

__all__ = [
    "edit_data_input",
    "execution_popover",
    "orchestration_popover",
    "MODE_VERBS",
    "VERB_MODES",
    "edit_orchestration",
    "edit_step_execution",
    "edit_stage_execution",
    "edit_workflow_execution",
    "render_orchestration",
    "render_step_execution",
    "is_fanned_out",
]

MODES = ["single", "map", "filter", "expand", "collapse"]
ITEM_ERROR = ["(default)", "collect", "fail_fast", "skip"]

#: One short word per mode — the vocabulary already used when talking about the
#: pipeline ("expand it, then map, then filter"). Long phrases do not fit a step
#: card, which is only ~260px wide.
MODE_VERBS = {
    "single": "once",
    "map": "map",
    "filter": "filter",
    "expand": "expand",
    "collapse": "reduce",
}
VERB_MODES = {verb: mode for mode, verb in MODE_VERBS.items()}

#: The verb list in the order it reads best in the picker.
VERBS = [MODE_VERBS[m] for m in MODES]

NO_SOURCE = "(a value)"


def is_fanned_out(orchestration: OrchestrationConfig) -> bool:
    """True when the step has a real fan-out (more than one unit of work)."""
    return orchestration.mode != "single"


# ── the compact input row ────────────────────────────────────────────────
def edit_data_input(st, mode: str, source: str | None, *, key: str,
                    prior_steps: list[str], takes_data: bool = True) -> tuple[str, str | None]:
    """How this step consumes its data, and where that data comes from.

    Two short selectboxes and nothing else. Both collapse away when they cannot
    apply — a first step has nothing to read from, and a step with no source has
    nothing to iterate — so a source step shows neither.

    Returns ``(mode, source)``. This is the only place data routing is asked,
    in every mode: ``over`` is not a separate field the user ever sees.
    """
    if not takes_data or not prior_steps:
        return "single", None

    options = [NO_SOURCE, *prior_steps]
    current_source = source if source in options else NO_SOURCE

    # The source is drawn first: which verbs apply depends on it, and a widget
    # only reports its new value once drawn.
    chosen_source = st.selectbox(
        "from", options, index=options.index(current_source), key=f"{key}_source",
        help=f"The earlier step this one reads. {NO_SOURCE} means it is typed in below.",
    )

    if chosen_source == NO_SOURCE:
        return "single", None

    verbs = [MODE_VERBS[m] for m in MODES]
    current_verb = MODE_VERBS.get(mode, MODE_VERBS["single"])
    chosen_verb = st.selectbox(
        "apply", verbs, index=verbs.index(current_verb), key=f"{key}_verb",
        help="once: pass it whole · map: per element · filter: keep matches · "
             "expand: each element becomes a row · reduce: fold to one value",
    )
    return VERB_MODES[chosen_verb], chosen_source


def execution_popover(st, config: StepExecutionConfig, *, key: str,
                      fanned_out: bool = False) -> StepExecutionConfig:
    """Conduct, folded into a small popover — rarely touched, never in the way."""
    with st.popover(":material/settings:", help="Execution settings"):
        return edit_step_execution(st, config, key=key, fanned_out=fanned_out)


def orchestration_popover(st, config: OrchestrationConfig, *, key: str,
                          param_names: list[str], inferred: str | None = None) -> OrchestrationConfig:
    """The orchestration details the compact row leaves out: item binding, seed."""
    with st.popover(":material/account_tree:", help="Orchestration details"):
        if config.mode == "single":
            st.caption("Runs once — nothing to orchestrate.")
            return config

        st.caption(f"`{config.mode}` over `{config.over or '—'}`")
        options = ["(auto)", *param_names]
        current = config.item_arg or "(auto)"
        chosen = st.selectbox(
            "item argument", options,
            index=options.index(current) if current in options else 0,
            key=f"{key}_item",
            help=f"Which parameter each item binds to. Auto picks `{inferred or '—'}`.",
        )
        initial = config.initial
        if config.mode == "collapse":
            text = st.text_input(
                "initial", value="" if initial is None else str(initial),
                key=f"{key}_initial",
                help="Seed for the accumulator. Empty means the first item seeds it.",
            )
            initial = text or None
        return config.model_copy(update={
            "item_arg": None if chosen == "(auto)" else chosen,
            "initial": initial,
        })


# ── shape ────────────────────────────────────────────────────────────────
def edit_orchestration(st, config: OrchestrationConfig, *, key: str,
                       prior_steps: list[str] | None = None,
                       param_names: list[str] | None = None) -> OrchestrationConfig:
    """Shape only. Concurrency, retries and error policy live in execution."""
    prior_steps = prior_steps or []
    param_names = param_names or []

    mode = st.selectbox("mode", MODES, index=MODES.index(config.mode), key=f"{key}_mode",
                        help="How this tool is applied across its input data.")
    over, item_arg, initial = config.over, config.item_arg, config.initial

    if mode != "single":
        if not prior_steps:
            st.caption("Add an earlier step to fan out over.")
        over_options = ["(none)", *prior_steps]
        current = over if over in over_options else "(none)"
        chosen = st.selectbox("over — the collection to fan out across", over_options,
                              index=over_options.index(current), key=f"{key}_over")
        over = None if chosen == "(none)" else chosen

        item_options = ["(auto)", *param_names]
        current_item = item_arg if item_arg in item_options else "(auto)"
        chosen_item = st.selectbox("item argument — which param each item binds to",
                                   item_options, index=item_options.index(current_item),
                                   key=f"{key}_item")
        item_arg = None if chosen_item == "(auto)" else chosen_item

        if mode == "collapse":
            text = st.text_input("initial — seed value for the accumulator",
                                 value="" if initial is None else str(initial),
                                 key=f"{key}_initial")
            initial = text or None
    else:
        over = None  # the model rejects `over` when mode is 'single'

    return OrchestrationConfig(mode=mode, over=over, item_arg=item_arg, initial=initial)


def render_orchestration(st, config: OrchestrationConfig, *, key: str) -> None:
    """Read-only one-liner describing the data shape."""
    if config.mode == "single":
        st.caption("runs once")
        return
    st.caption(
        f"`{config.mode}` over `{config.over or '—'}` "
        f"→ item binds to `{config.item_arg or '(auto)'}`"
    )


# ── conduct ──────────────────────────────────────────────────────────────
def edit_step_execution(st, config: StepExecutionConfig, *, key: str,
                        fanned_out: bool = False) -> StepExecutionConfig:
    """Conduct for one step. Per-item fields appear only when they mean something."""
    run = st.selectbox("run", ["manual", "auto"],
                       index=["manual", "auto"].index(config.run), key=f"{key}_run",
                       help="'manual' waits for the Run button; 'auto' is a hint "
                            "for orchestrated runners.")
    has_timeout = st.checkbox("set a timeout", value=config.timeout is not None,
                              key=f"{key}_timeout_on")
    timeout = (
        st.number_input("timeout (seconds)", min_value=0.0,
                        value=float(config.timeout or 30.0), key=f"{key}_timeout")
        if has_timeout else None
    )
    retries = st.number_input(
        "retries", min_value=0, step=1, value=int(config.retries), key=f"{key}_retries",
        help="Retries one unit of work — the whole call when mode is 'single', "
             "one item when fanned out.",
    )
    cache = st.checkbox("cache result", value=config.cache, key=f"{key}_cache")

    concurrency, on_item_error = config.concurrency, config.on_item_error
    if fanned_out:
        st.markdown("___")
        st.caption("Per-item conduct — this step runs more than one unit.")
        concurrency = st.number_input("concurrency", min_value=1, step=1,
                                      value=int(config.concurrency), key=f"{key}_conc",
                                      help="How many items run at once.")
        current = on_item_error or "(default)"
        chosen = st.selectbox("on_item_error", ITEM_ERROR,
                              index=ITEM_ERROR.index(current), key=f"{key}_item_err",
                              help="What a single failed item does to the batch.")
        on_item_error = None if chosen == "(default)" else chosen

    return StepExecutionConfig(
        run=run, timeout=timeout, retries=int(retries), cache=cache,
        concurrency=int(concurrency), on_item_error=on_item_error,
    )


def render_step_execution(st, config: StepExecutionConfig, *, key: str,
                          fanned_out: bool = False) -> None:
    """Read-only summary of a step's conduct."""
    bits = [f"run `{config.run}`"]
    if config.timeout is not None:
        bits.append(f"timeout {config.timeout:g}s")
    if config.retries:
        bits.append(f"retries {config.retries}")
    if config.cache:
        bits.append("cached")
    if fanned_out:
        bits.append(f"concurrency {config.concurrency}")
        bits.append(f"on_item_error {config.on_item_error or '(default)'}")
    st.caption(" · ".join(bits))


def edit_stage_execution(st, config: StageExecutionConfig, *, key: str) -> StageExecutionConfig:
    """Conduct for a stage: how its steps run together."""
    steps = st.selectbox("steps", ["sequential", "parallel"],
                         index=["sequential", "parallel"].index(config.steps),
                         key=f"{key}_steps",
                         help="'parallel' is only valid when the stage's steps "
                              "do not reference one another.")
    concurrency = st.number_input("concurrency", min_value=1, step=1,
                                  value=int(config.concurrency), key=f"{key}_conc",
                                  help="How many steps of this stage run at once.")
    on_step_error = st.selectbox("on_step_error", ["stop", "continue"],
                                 index=["stop", "continue"].index(config.on_step_error),
                                 key=f"{key}_err")
    run = st.selectbox("run", ["manual", "auto"],
                       index=["manual", "auto"].index(config.run), key=f"{key}_run")
    return StageExecutionConfig(steps=steps, concurrency=int(concurrency),
                                on_step_error=on_step_error, run=run)


def edit_workflow_execution(st, config: WorkflowExecutionConfig, *,
                            key: str) -> WorkflowExecutionConfig:
    """Conduct for a workflow: how its stages run."""
    on_stage_error = st.selectbox("on_stage_error", ["stop", "continue"],
                                  index=["stop", "continue"].index(config.on_stage_error),
                                  key=f"{key}_err")
    run = st.selectbox("run", ["manual", "auto"],
                       index=["manual", "auto"].index(config.run), key=f"{key}_run")
    return WorkflowExecutionConfig(stages="sequential", on_stage_error=on_stage_error,
                                   run=run)
