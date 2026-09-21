"""
Streamlit components for the core object model
==============================================

One component per user-facing object in ``simple_steps_core``. Each is a thin
adapter: the **library** owns the content (``info()``, ``validate()``,
``preview()``, ``check_all()``) and these functions own only how it looks in
Streamlit.

Conventions
-----------

``render_x(st, obj, *, key, on_… = None) -> None``
    Draw *obj*. Actions are offered as buttons, but the **caller** supplies the
    behavior through ``on_…`` callbacks — a component never mutates what it was
    handed, and never touches ``st.session_state``.

``edit_x(st, obj, *, key) -> X``
    Draw widgets seeded from *obj* and return a **new** instance (the domain
    configs are frozen, so editing means replacing).

``st`` is always the first positional argument and is never imported at module
level, so components are unit-testable with a fake and importing this package
never requires Streamlit to be installed.

``key`` is a required widget-key prefix, so one component can be drawn many
times on a page without colliding.

Dispatch
--------
:func:`render` picks the right component by type::

    from simple_steps_core.streamlit.components import render
    render(st, workflow, key="wf")
    render(st, step, key="step1")
"""

from __future__ import annotations

from typing import Any

from simple_steps_core import (
    App,
    AppConfig,
    ArgGuardrail,
    Cell,
    DataEntry,
    ItemOutcome,
    ResourceCheck,
    SessionSnapshot,
    Shape,
    StepError,
    StepResult,
    StepStatus,
    ToolRegistry,
    ToolUI,
    ToolUIView,
    DataStore,
    Guardrails,
    MapResult,
    Operation,
    OrchestrationConfig,
    ResourceContainer,
    Session,
    SessionContext,
    Stage,
    StageExecutionConfig,
    Step,
    StepExecutionConfig,
    StepOutput,
    SummaryTable,
    Tool,
    ToolCall,
    ToolDefinition,
    ToolParam,
    Workflow,
    WorkflowExecutionConfig,
)

from .base import caption_list, empty, summary, summary_frame
from .configs import (
    MODE_VERBS,
    VERB_MODES,
    edit_data_input,
    execution_popover,
    orchestration_popover,
    edit_orchestration,
    edit_stage_execution,
    edit_step_execution,
    edit_workflow_execution,
    is_fanned_out,
    render_orchestration,
    render_step_execution,
)
from .forms import (
    build_help,
    render_arg_combo,
    check_rule,
    coerce_value,
    render_literal_arg,
    render_tool_form,
)
from .steps import (
    FAILED_FILL,
    OK_FILL,
    STAGED_FILL,
    output_type_name,
    shade,
    shade_by_status,
    staged_frame,
    render_map_result,
    render_operation,
    render_output,
    render_output_status,
    render_staged_output,
    render_step,
    render_tool_call,
    staged_output_type,
    to_dataframe,
)
from .tools import (
    describe_arg_guardrail,
    render_arg_guardrail,
    render_guardrails,
    render_param,
    render_registry,
    render_resource_params,
    render_tool,
    render_tool_definition,
)
from .values import (
    render_app_config,
    render_cell,
    render_data_entry,
    render_item_outcome,
    render_resource_check as render_one_resource_check,
    render_shape,
    render_snapshot,
    render_status,
    render_step_error,
    render_step_result,
    render_tool_registry,
    render_tool_ui,
    render_tool_ui_view,
)
from .workflow import (
    render_app,
    render_data_store,
    render_preview,
    render_resource_check,
    render_resources,
    render_session,
    render_session_context,
    render_stage,
    render_stages,
    render_workflow,
    render_workflow_validation,
)

__all__ = [
    # dispatch
    "render", "COMPONENTS",
    # base
    "summary", "summary_frame", "caption_list", "empty",
    # tools
    "render_tool", "render_tool_definition", "render_param", "render_guardrails",
    "render_arg_guardrail", "render_resource_params", "render_registry",
    "describe_arg_guardrail",
    # forms
    "render_tool_form", "render_literal_arg", "render_arg_combo",
    "coerce_value", "check_rule", "build_help",
    "edit_data_input", "execution_popover", "orchestration_popover",
    "MODE_VERBS", "VERB_MODES",
    # steps & outputs
    "render_step", "render_operation", "render_tool_call", "render_output",
    "render_output_status", "render_map_result", "render_staged_output",
    "to_dataframe", "output_type_name", "staged_output_type",
    "shade", "shade_by_status", "staged_frame",
    "STAGED_FILL", "OK_FILL", "FAILED_FILL",
    # configs
    "edit_orchestration", "edit_step_execution", "edit_stage_execution",
    "edit_workflow_execution", "render_orchestration", "render_step_execution",
    "is_fanned_out",
    # workflow & app
    "render_workflow", "render_workflow_validation", "render_preview", "render_stage",
    "render_stages", "render_app", "render_session", "render_resources",
    "render_resource_check", "render_session_context", "render_data_store",
    # value objects
    "render_status", "render_step_error", "render_step_result", "render_item_outcome",
    "render_shape", "render_cell", "render_data_entry", "render_snapshot",
    "render_app_config", "render_tool_ui", "render_tool_ui_view", "render_tool_registry",
]


#: Every exposed object mapped to the component that draws it. Editors for the
#: frozen configs are listed separately because they return a value.
COMPONENTS: dict[type, Any] = {
    SummaryTable: summary,
    # tool contract
    Tool: render_tool,
    ToolDefinition: render_tool_definition,
    ToolParam: render_param,
    Guardrails: render_guardrails,
    ArgGuardrail: render_arg_guardrail,
    # step specs and results
    Step: render_step,
    Operation: render_operation,
    ToolCall: render_tool_call,
    StepOutput: render_output,
    MapResult: render_map_result,
    # configs (read-only views; use edit_* to change them)
    OrchestrationConfig: render_orchestration,
    StepExecutionConfig: render_step_execution,
    # workflow and app
    Workflow: render_workflow,
    Stage: render_stage,
    App: render_app,
    Session: render_session,
    # resources and payload store
    ResourceContainer: render_resources,
    SessionContext: render_session_context,
    DataStore: render_data_store,
    # value objects and declarations
    ToolRegistry: render_tool_registry,
    ToolUI: render_tool_ui,
    ToolUIView: render_tool_ui_view,
    StepStatus: render_status,
    StepError: render_step_error,
    StepResult: render_step_result,
    ItemOutcome: render_item_outcome,
    Shape: render_shape,
    Cell: render_cell,
    DataEntry: render_data_entry,
    ResourceCheck: render_one_resource_check,
    SessionSnapshot: render_snapshot,
    AppConfig: render_app_config,
}

#: Configs that are edited rather than only displayed.
EDITORS: dict[type, Any] = {
    OrchestrationConfig: edit_orchestration,
    StepExecutionConfig: edit_step_execution,
    StageExecutionConfig: edit_stage_execution,
    WorkflowExecutionConfig: edit_workflow_execution,
}


def render(st, obj: Any, *, key: str, **kwargs: Any) -> Any:
    """Draw *obj* with the component registered for its type.

    Raises ``TypeError`` for an object with no component, rather than guessing —
    a missing component is a gap to fill, not something to paper over.
    """
    component = COMPONENTS.get(type(obj))
    if component is None:
        for cls, candidate in COMPONENTS.items():
            if isinstance(obj, cls):
                component = candidate
                break
    if component is None:
        raise TypeError(
            f"no Streamlit component for {type(obj).__name__}; "
            f"registered: {', '.join(sorted(c.__name__ for c in COMPONENTS))}"
        )
    return component(st, obj, key=key, **kwargs)
