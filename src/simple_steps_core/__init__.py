"""simple-steps-core: the engine of Simple Steps.

You work with it through a kernel: a catalog of what a workflow may use, and
one workflow (docs/design/kernel-session.md)::

    from simple_steps_core import Catalog, Kernel, tool, mod, wf

    k = Kernel(Catalog(tools=[readings, to_fahrenheit]))
    k["r"] = readings[mod.source()]()
    k["f"] = to_fahrenheit[mod.map()](wf["r"])
    k.run_all()

The names below are the public API. Everything else lives in the modules
(``simple_steps_core.workflow``, ``.checks``, ``.verbs``, …), whose contents
may change.
"""

import importlib as _importlib
from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("simple-steps-core")
except PackageNotFoundError:          # running from a source tree, not installed
    __version__ = "0.0.0.dev0"

#: The modules, leaves first. Several import each other at the bottom of the
#: file, for names they use only inside functions; that works when they load
#: in this order (docs/design/cleanup-plan.md §3). Plain imports replace this
#: module by module in phase 4.
_LOAD_ORDER = ('problems', 'specs', 'system_tools', 'output', 'verbs', 'modifiers', 'checks', 'catalog', 'combines', 'errors', 'operation', 'references', 'run', 'step', 'values', 'workflow', 'kernel')

for _module in _LOAD_ORDER:
    _importlib.import_module(f"{__name__}.{_module}")
del _module

from .catalog import Catalog, Tool, bound_tool, resource, tool  # noqa: E402
from .combines import join, stack, zip_  # noqa: E402
from .kernel import Kernel  # noqa: E402
from .modifiers import mod  # noqa: E402
from .operation import Operation  # noqa: E402
from .output import Output  # noqa: E402
from .problems import Problem  # noqa: E402
from .references import cols, res, rows, wf  # noqa: E402
from .specs import CatalogSpec, KernelSpec, Naming, ResourceSpec, StepSpec, WorkflowSpec  # noqa: E402
from .step import Step, StepStatus  # noqa: E402
from .values import Secret  # noqa: E402

__all__ = [
    "Catalog", "Kernel", "Tool", "tool", "resource", "bound_tool", "Secret",
    "mod", "wf", "res", "rows", "cols", "join", "stack", "zip_",
    "Operation", "Step", "StepStatus", "Output", "Problem",
    "ResourceSpec", "StepSpec", "WorkflowSpec", "CatalogSpec", "KernelSpec", "Naming",
    "__version__",
]
