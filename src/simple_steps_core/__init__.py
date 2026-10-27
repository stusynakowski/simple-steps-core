"""simple-steps-core: the engine of Simple Steps.

The grid model is the only model (docs/design/README.md). It lives in the
``grid`` module for now; the public names move to this package when it is
split along the object model (docs/design/cleanup-plan.md §3)::

    from simple_steps_core import grid
    from simple_steps_core.grid import tool, mod, wf

    w = grid.Workflow()
    w["readings"] = frame
    w["f"] = to_fahrenheit(wf["readings"])
"""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("simple-steps-core")
except PackageNotFoundError:          # running from a source tree, not installed
    __version__ = "0.0.0.dev0"

from . import grid

__all__ = ["grid", "__version__"]
