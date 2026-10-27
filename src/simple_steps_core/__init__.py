"""simple-steps-core: the engine of Simple Steps.

The grid model is the only model (docs/design/README.md). You work with it
through a kernel: a catalog of what may be used, and one workflow::

    from simple_steps_core import Catalog, Kernel, tool, mod, wf

    k = Kernel(Catalog(tools=[readings, to_fahrenheit]))
    k["r"] = readings[mod.source()]()
    k["f"] = to_fahrenheit[mod.map()](wf["r"])
    k.run_all()

The ``grid`` module still re-exports everything during the redesign
(docs/design/cleanup-plan.md §4).
"""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("simple-steps-core")
except PackageNotFoundError:          # running from a source tree, not installed
    __version__ = "0.0.0.dev0"

from . import grid  # loads every module, in dependency order
from .catalog import Catalog, bound_tool, resource, tool
from .combines import join, stack, zip_
from .kernel import Kernel
from .modifiers import mod
from .problems import Problem
from .references import cols, res, rows, wf

__all__ = [
    "Catalog", "Kernel", "tool", "resource", "bound_tool",
    "mod", "wf", "res", "rows", "cols", "join", "stack", "zip_", "Problem",
    "grid", "__version__",
]
