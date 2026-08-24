"""
Public API
=========

The curated surface other code (and the app repo) imports. Everything here is
considered stable; internal modules may change as long as these names keep
their behavior. Import from ``simple_steps_core`` rather than reaching into
sub-packages directly.
"""

from ..domain.models import (
    Cell,
    ExecutionConfig,
    ItemOutcome,
    MapResult,
    OperationDefinition,
    OperationParam,
    OrchestrationConfig,
    Shape,
    Step,
    StepError,
    StepOutput,
    StepResult,
    StepSpec,
    StepStatus,
    ToolCall,
)
from ..domain.references import is_reference, split_reference
from ..execution.context import SessionContext
from ..execution.data_store import DataEntry, DataStore
from ..execution.engine import CoreEngine, ExecutionHandle
from ..execution.resolver import ReferenceResolver
from ..execution.resources import ResourceContainer, ResourceMissingError
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
from ..execution.workflow import Workflow
from ..operations.dependencies import Resource
from ..operations.orchestrations import register_orchestrators
from ..operations.registry import (
    REGISTRY,
    Operation,
    OperationRegistry,
    RegistryFrozenError,
    register_operation,
)
from ..operations.validation import ValidationError, validate_tool_call

__all__ = [
    # domain
    "Cell",
    "ItemOutcome",
    "MapResult",
    "OperationDefinition",
    "OperationParam",
    "Shape",
    "Step",
    "StepError",
    "StepOutput",
    "StepResult",
    "StepStatus",
    "StepSpec",
    "OrchestrationConfig",
    "ExecutionConfig",
    "ToolCall",
    "is_reference",
    "split_reference",
    # operations
    "Operation",
    "OperationRegistry",
    "RegistryFrozenError",
    "REGISTRY",
    "register_operation",
    "register_orchestrators",
    "ValidationError",
    "validate_tool_call",
    # execution
    "CoreEngine",
    "ExecutionHandle",
    "ReferenceResolver",
    "SessionContext",
    "SessionManager",
    "make_session_id",
    "Workflow",
    # resources
    "Resource",
    "ResourceContainer",
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
