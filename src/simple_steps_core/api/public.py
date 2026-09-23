"""
Public API
=========

The curated surface other code (and the app repo) imports. Everything here is
considered stable; internal modules may change as long as these names keep
their behavior. Import from ``simple_steps_core`` rather than reaching into
sub-packages directly.
"""

from ..domain.collections import (
    Collection,
    Group,
    Groups,
    ListCollection,
    check_reiterable,
)
from ..domain.media import (
    MediaAsset,
    MediaStore,
    get_media_store,
    media_type_of,
    set_media_store,
)
from ..domain.tabular import is_frame, items_of, rows_to_frame, select_positions
from ..domain.models import (
    ORCHESTRATION_RESOURCE,
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
    orchestrator_id,
)
from ..app import App, AppConfig, Session
from ..domain.references import is_reference, parse_reference, split_reference
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
from ..operations.orchestrations import orchestration_resource, register_orchestrators
from ..operations.registry import (
    REGISTRY,
    RESOURCE_SEPARATOR,
    ResourceBindingError,
    Tool,
    ToolRegistry,
    RegistryFrozenError,
    qualify,
    register_tool,
    split_qualified,
)
from ..operations.resource_spec import ResourceSpec
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
    "parse_reference",
    # operations
    "Tool",
    "ToolRegistry",
    "RegistryFrozenError",
    "REGISTRY",
    "register_tool",
    "register_orchestrators",
    "orchestration_resource",
    "ORCHESTRATION_RESOURCE",
    "orchestrator_id",
    "qualify",
    "split_qualified",
    "RESOURCE_SEPARATOR",
    "ResourceBindingError",
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
    "ResourceSpec",
    "ResourceContainer",
    "ResourceCheck",
    "ResourceMissingError",
    "DataEntry",
    "DataStore",
    # collections (lazy, versioned sources)
    "Collection",
    "ListCollection",
    "check_reiterable",
    "Group",
    "Groups",
    # media (images and video, held by handle)
    "MediaAsset",
    "MediaStore",
    "get_media_store",
    "set_media_store",
    "media_type_of",
    # tabular (what a "row" means to an orchestrator)
    "is_frame",
    "items_of",
    "select_positions",
    "rows_to_frame",
    # session snapshot / codecs
    "CodecRegistry",
    "DEFAULT_CODECS",
    "InMemoryStore",
    "PayloadEnvelope",
    "SessionSnapshot",
    "SnapshotError",
    "StoreBackend",
]
