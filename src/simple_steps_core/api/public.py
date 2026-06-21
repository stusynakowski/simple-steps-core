"""
Public API
=========

The curated surface other code (and the app repo) imports. Everything here is
considered stable; internal modules may change as long as these names keep
their behavior. Import from ``simple_steps_core`` rather than reaching into
sub-packages directly.
"""

from ..domain.formulas import parse_formula, render_formula
from ..domain.models import (
    ItemOutcome,
    MapResult,
    OperationDefinition,
    OperationParam,
    Step,
    StepOutput,
    StepStatus,
    ToolCall,
)
from ..domain.references import is_reference
from ..execution.context import SessionContext
from ..execution.engine import CoreEngine, ExecutionHandle
from ..execution.resolver import ReferenceResolver
from ..execution.session_io import (
    DEFAULT_CODECS,
    CodecRegistry,
    PayloadEnvelope,
    SessionSnapshot,
    SnapshotError,
)
from ..execution.session_manager import SessionManager, make_session_id
from ..execution.workflow import Workflow
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
    "ItemOutcome",
    "MapResult",
    "OperationDefinition",
    "OperationParam",
    "Step",
    "StepOutput",
    "StepStatus",
    "ToolCall",
    "is_reference",
    "parse_formula",
    "render_formula",
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
    # session snapshot / codecs
    "CodecRegistry",
    "DEFAULT_CODECS",
    "PayloadEnvelope",
    "SessionSnapshot",
    "SnapshotError",
]
