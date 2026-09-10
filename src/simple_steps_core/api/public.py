"""
Public API
=========

The curated surface other code (and the app repo) imports. Everything here is
considered stable; internal modules may change as long as these names keep
their behavior. Import from ``simple_steps_core`` rather than reaching into
sub-packages directly.
"""

from ..domain.models import (
    ArgGuardrail,
    Cell,
    StepExecutionConfig,
    StageExecutionConfig,
    WorkflowExecutionConfig,
    Guardrails,
    ItemOutcome,
    MapResult,
    ToolDefinition,
    ToolParam,
    OrchestrationConfig,
    Shape,
    Step,
    StepError,
    StepOutput,
    StepResult,
    Operation,
    StepStatus,
    ToolCall,
)
from ..app import App, AppConfig, Session
from ..domain.references import is_reference, split_reference
from ..execution.context import SessionContext
from ..execution.data_store import DataEntry, DataStore
from ..execution.engine import CoreEngine, ExecutionHandle
from ..execution.resolver import ReferenceResolver
from ..execution.resources import ResourceCheck, ResourceContainer, ResourceMissingError
from ..execution.session_io import (
    DEFAULT_CODECS,
    CodecRegistry,
    InMemoryStore,
    PayloadEnvelope,
    SessionSnapshot,
    SnapshotError,
    StoreBackend,
)
from ..execution.session_manager import SessionManager, make_session_id
from ..execution.workflow import Stage, Workflow
from ..inspect import SummaryTable
from ..operations.dependencies import Resource
from ..operations.orchestrations import register_orchestrators
from ..operations.registry import (
    REGISTRY,
    Tool,
    ToolRegistry,
    RegistryFrozenError,
    register_tool,
)
from ..operations.ui import ToolUI, ToolUIView, build_default_ui
from ..operations.validation import (
    ValidationError,
    check_reference_types,
    validate_tool_call,
)

__all__ = [
    # domain
    "ArgGuardrail",
    "Cell",
    "Guardrails",
    "ItemOutcome",
    "MapResult",
    "ToolDefinition",
    "ToolParam",
    "Shape",
    "Step",
    "StepError",
    "StepOutput",
    "StepResult",
    "StepStatus",
    "Operation",
    "OrchestrationConfig",
    "StepExecutionConfig",
    "StageExecutionConfig",
    "WorkflowExecutionConfig",
    "ToolCall",
    "build_default_ui",
    "ToolUI",
    "ToolUIView",
    "is_reference",
    "split_reference",
    # operations
    "Tool",
    "ToolRegistry",
    "RegistryFrozenError",
    "REGISTRY",
    "register_tool",
    "register_orchestrators",
    "ValidationError",
    "validate_tool_call",
    "check_reference_types",
    # execution
    "CoreEngine",
    "ExecutionHandle",
    "ReferenceResolver",
    "SessionContext",
    "SessionManager",
    "make_session_id",
    "Workflow",
    "Stage",
    # app facade
    "App",
    "AppConfig",
    "Session",
    "SummaryTable",
    # resources
    "Resource",
    "ResourceContainer",
    "ResourceCheck",
    "ResourceMissingError",
    "DataEntry",
    "DataStore",
    # session snapshot / codecs
    "CodecRegistry",
    "DEFAULT_CODECS",
    "InMemoryStore",
    "PayloadEnvelope",
    "SessionSnapshot",
    "SnapshotError",
    "StoreBackend",
]
