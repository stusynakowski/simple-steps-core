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
    OperationDefinition,
    OperationParam,
    Step,
    StepOutput,
    StepStatus,
    ToolCall,
)
from ..domain.references import is_reference
from ..execution.context import SessionContext
from ..execution.engine import CoreEngine
from ..execution.resolver import ReferenceResolver
from ..execution.workflow import Workflow
from ..operations.registry import REGISTRY, Operation, OperationRegistry, register_operation
from ..operations.validation import ValidationError, validate_tool_call

__all__ = [
    # domain
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
    "REGISTRY",
    "register_operation",
    "ValidationError",
    "validate_tool_call",
    # execution
    "CoreEngine",
    "ReferenceResolver",
    "SessionContext",
    "Workflow",
]
