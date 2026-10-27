"""The grid model, as one namespace: a compatibility layer for phase 2.

``grid.py`` used to hold the whole model in 7,444 lines. It is now split into
modules along the object model (docs/design/cleanup-plan.md §3), with the code
moved unchanged. This module loads them and re-exports every name they define,
private ones included, so ``from simple_steps_core import grid`` and
``grid.<name>`` behave exactly as before. It goes in phase 3, when the public
names move to ``simple_steps_core`` itself.

**How the modules refer to each other.** Each module imports at the top only
the names it needs while it loads (decorators, defaults, base classes,
module-level tables). Names used only inside functions are imported at the
bottom of the module, which lets modules call each other freely. That only
works when the modules load in dependency order, which this module does
(``_LOAD_ORDER``).

"""

from __future__ import annotations

# __all__ names the modules' names, which are copied in below, so ruff can't
# see them defined here.
# ruff: noqa: F822

import importlib

__all__ = [
    "Catalog", "Kernel", "Problem",
    "Output", "grid", "rows", "map_", "filter_", "group_", "collapse_",
    "expand_", "sweep_", "source_", "select_", "drop_", "widen_",
    "slice_", "rename_", "sort_", "distinct_",
    "identity", "gather", "count", "total", "first", "last",
    "BUILTIN_TOOLS", "DEFAULT_TOOL", "catalog", "tool_entry",
    "modifier_catalog",
    "op", "Modifier", "Operation",
    "join", "stack", "zip_", "COMBINE", "is_combine",
    "tool", "ToolHandle", "StepRef", "Step", "Workflow", "check", "warn", "stage",
    "wf", "res", "ResRef", "bound_tool", "cols", "Rows", "Cols", "SelectionError",
    "RESERVED_NAMES", "FORMAT_VERSION", "ToolRef", "StepFailed",
    "builtin_tools", "shape_verbs",
    "payload_column", "check_modifier", "formula_names",
    "resource",
    "resource_entry", "resource_catalog", "ResourceNotLoaded",
    "annotation_problems", "declaration_problems",
    "PARAM_TYPES", "PARAM_TYPES_BY_VERB",
    "ROWS_RULE", "DEFAULT_PAYLOAD", "CARRIES_COLUMNS", "PayloadError",
    "is_identity", "infer_verb",
    "predicted_columns", "columns_unknown",

    "mod",
    "DECORATORS", "MODIFIERS", "ModifierKind", "SHAPE_VERBS", "is_shape",
    "compile_operation",
    "PAYLOAD", "STATES", "ROW_ID",
]

#: Leaves first: each module only needs, while it loads, names from modules
#: before it.
_LOAD_ORDER = ('problems', 'specs', 'system_tools', 'output', 'verbs', 'modifiers', 'checks', 'catalog', 'combines', 'errors', 'operation', 'references', 'run', 'step', 'values', 'workflow', 'kernel')

_MODULES = {name: importlib.import_module(f"simple_steps_core.{name}") for name in _LOAD_ORDER}

for _module in _MODULES.values():
    for _name, _value in vars(_module).items():
        if _name.startswith("__") or _name in globals():
            continue
        globals()[_name] = _value
del _module, _name, _value

