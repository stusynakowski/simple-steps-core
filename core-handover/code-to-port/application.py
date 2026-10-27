"""
application.py — ``App``, the one object a Simple Steps application is built from.

A developer writes their tools and resources, then composes them in an
``app.py`` next to them (``docs/dev_plan/122-skeleton-complete.md`` §1):

.. code-block:: python

    # app.py
    from SIMPLE_STEPS import App, Loaded, env
    import my_tools
    from my_resources import ClinicalDB, Claude

    app = App(
        tools=[my_tools],                     # modules, or single tools
        resources=[ClinicalDB, Claude],       # types users may create
        loaded={"study": Loaded(ClinicalDB, url=env("DB_URL"), locked=["url"])},
    )

    if __name__ == "__main__":
        app.serve()

Every setting has a default, so ``App(tools=[my_tools]).serve()`` is a complete
application. Two ways to start it, both equivalent:

- ``python app.py`` — :meth:`App.serve`;
- ``simple-steps`` (or ``simple-steps-dev``, ``--local``) in that folder: the
  server finds ``app.py`` in the workspace and uses the ``App`` it defines.

**Explicit vs. discovered tools.** ``App(tools=[…])`` *is* the list of tools:
the workspace's top-level ``*.py`` files are not scanned, so a module that
``app.py`` imports is never imported a second time under another name (which
would register every tool and resource class twice). ``App()`` with no tools —
and a workspace with no ``app.py`` at all — keep today's discovery exactly.
``packs/``, ``ops/`` and project folders are discovered either way.

What isn't swappable yet (122 S1.2, after the MVP): the workspace format,
session store and result store keep their current implementations, and the
server is configured when ``SIMPLE_STEPS.main`` is first imported — so one
process serves one ``App``.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import threading
import time
import types
import webbrowser
from typing import Any, Dict, Iterable, List, Mapping, Optional

#: The App this process serves: the first one built (``python app.py``), or
#: the one in the workspace's ``app.py`` (``simple-steps``).
CURRENT: Optional["App"] = None

#: The file a workspace's application lives in.
APP_FILE = "app.py"


class AppError(ValueError):
    """An ``App`` that can't be built as written, with the reason."""


class App:
    """The composition root: the tools, resources and settings of one
    Simple Steps application. Every argument is optional."""

    def __init__(
        self,
        tools: Iterable[Any] = (),
        resources: Iterable[type] = (),
        loaded: Optional[Mapping[str, Any]] = None,
        *,
        workspace: Optional[str] = None,
        title: str = "Simple Steps",
        host: str = "127.0.0.1",
        port: int = 8000,
        cell_types: Iterable[Any] = (),
        freeze: bool = False,
        agent: Any = None,
    ):
        """
        Args:
            tools: modules whose ``@simple_step_tool`` functions to offer, or
                single tools. Given → the workspace's ``*.py`` files are not
                scanned. Empty → they are, as before.
            resources: resource types users may create. A class not yet
                decorated is declared with ``@simple_step_resource`` here.
            loaded: ready-made resources, ``{"name": Loaded(Type, …)}``.
            workspace: where ``projects/`` and workflow files live. Defaults
                to the folder of the file that builds the ``App``.
            title: the server's title.
            host: where :meth:`serve` listens.
            port: the preferred port for :meth:`serve`; the next free one is
                used if it's taken.
            cell_types: extra ``CellType``\\ s for the grid (``cell_types.py``).
            freeze: refuse new tools once the server has started, for an app
                served to others.
            agent: the agent's model, ``Agent(model="qwen2.5:7b")``; ``False``
                turns the agent off. Default: a local Ollama model if one is
                running (``agent/model.py``), else no agent.
        """
        global CURRENT
        self.workspace = os.path.abspath(workspace or _caller_folder())
        self.title = title
        self.host = host
        self.port = port
        self.freeze = freeze
        self.agent = agent
        self.tool_ids: List[str] = []
        for item in tools:
            self.tool_ids += _tool_ids(item)
        #: Whether tools were listed. If so, the workspace isn't scanned.
        self.explicit = bool(self.tool_ids)
        self.resource_types: List[type] = [_resource_type(cls) for cls in resources]
        self.loaded: Dict[str, Any] = {}
        from .resources import ResourceError, register_loaded
        for name, item in (loaded or {}).items():
            try:
                self.loaded[name] = register_loaded(name, item)
            except ResourceError as exc:
                raise AppError(str(exc)) from None
        from .cell_types import register_cell_type
        for cell_type in cell_types:
            register_cell_type(cell_type)
        if CURRENT is None:
            CURRENT = self

    def __repr__(self) -> str:
        return (f"App({len(self.tool_ids)} tools, {len(self.resource_types)} resource types, "
                f"{len(self.loaded)} ready-made, workspace={self.workspace!r})")

    # ── Serving ─────────────────────────────────────────────────────────────

    @property
    def api(self):
        """The FastAPI application serving this App (for mounting, or tests)."""
        _configure_environment(self)
        from . import main
        if os.path.abspath(main._WORKSPACE) != self.workspace:
            raise AppError(
                f"this process already serves the workspace {main._WORKSPACE}; one "
                f"process serves one App (asked for {self.workspace})"
            )
        return main.app

    def serve(self, host: Optional[str] = None, port: Optional[int] = None,
              open_browser: bool = True) -> None:
        """Start the server and (by default) open the UI in a browser."""
        import uvicorn
        from .cli import _find_free_port

        host = host or self.host
        wanted = port or self.port
        chosen = _find_free_port(host, wanted)
        if chosen != wanted:
            print(f"  ⚠️  Port {wanted} is in use, using port {chosen} instead.")
        api = self.api
        url = f"http://{'localhost' if host == '0.0.0.0' else host}:{chosen}"
        print(f"\n  ⚡ {self.title}: {url}\n     {self!r}\n")
        if open_browser:
            def _open() -> None:
                time.sleep(1.5)
                webbrowser.open(url)
            threading.Thread(target=_open, daemon=True).start()
        uvicorn.run(api, host=host, port=chosen, log_level="info")


# ─────────────────────────────────────────────────────────────────────────────
# Finding the App a workspace defines
# ─────────────────────────────────────────────────────────────────────────────

def app_file(workspace: str) -> Optional[str]:
    """``<workspace>/app.py`` if it exists."""
    path = os.path.join(workspace, APP_FILE)
    return path if os.path.isfile(path) else None


def load_app(workspace: str) -> Optional[App]:
    """The App this process serves: :data:`CURRENT` if one was built already
    (``python app.py``), else the one ``<workspace>/app.py`` builds, else None.
    """
    if CURRENT is not None:
        return CURRENT
    path = app_file(workspace)
    if path is None:
        return None
    _import_app_file(path)
    if CURRENT is None:
        print(f"  ⚠️  {path} defines no App; discovering tools in the workspace instead.")
    return CURRENT


def load_app_file(path: str) -> App:
    """The App the Python file at *path* builds — ``simple-steps run app.py``.

    The file is imported as a module, not run as ``__main__``, so its own
    ``if __name__ == "__main__": app.serve()`` doesn't fire: the CLI serves it,
    with the CLI's host and port. A file that registers tools but builds no
    App gets one for its folder, listing those tools.
    """
    global CURRENT
    path = os.path.abspath(path)
    module = _import_app_file(path)
    if CURRENT is None:
        folder = os.path.dirname(path)
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            CURRENT = App(tools=[module], workspace=folder, title=name)
        except AppError:
            raise AppError(
                f"{path} builds no App and has no @simple_step_tool functions. "
                "Add `app = App(tools=[...])`, or decorate a function with @simple_step_tool"
            ) from None
    return CURRENT


def _import_app_file(path: str) -> types.ModuleType:
    """Import *path* as ``simple_steps_app``; the App it builds becomes CURRENT."""
    global CURRENT
    folder = os.path.dirname(os.path.abspath(path))
    if folder not in sys.path:
        sys.path.insert(0, folder)   # so app.py can `import my_tools`
    spec = importlib.util.spec_from_file_location("simple_steps_app", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["simple_steps_app"] = module
    spec.loader.exec_module(module)
    if CURRENT is None:
        built = [v for v in vars(module).values() if isinstance(v, App)]
        CURRENT = getattr(module, "app", None) if isinstance(getattr(module, "app", None), App) \
            else (built[0] if built else None)
    return module


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _caller_folder() -> str:
    """The folder of the file that called ``App(…)``, or the working directory."""
    for frame in inspect.stack()[2:]:
        filename = frame.filename
        if filename and not filename.startswith("<") and os.path.basename(filename) != "application.py":
            return os.path.dirname(os.path.abspath(filename))
    return os.getcwd()


def _tool_ids(item: Any) -> List[str]:
    """The tool ids a module, or a single tool, contributes."""
    from .decorators import OPERATION_REGISTRY

    if isinstance(item, types.ModuleType):
        ids = [op_id for op_id, entry in OPERATION_REGISTRY.items()
               if getattr(entry.get("func"), "__module__", None) == item.__name__]
        if not ids:
            raise AppError(f"module {item.__name__} has no @simple_step_tool functions")
        return ids
    op_id = getattr(item, "_tool_id", None)
    if op_id in OPERATION_REGISTRY:
        return [op_id]
    for op_id, entry in OPERATION_REGISTRY.items():
        if entry.get("func") is item:
            return [op_id]
    name = getattr(item, "__name__", repr(item))
    raise AppError(f"{name} isn't a tool; decorate it with @simple_step_tool")


def _resource_type(cls: Any) -> type:
    from .core_bridge import simple_step_resource
    from .resources import RESOURCE_TYPES

    if not inspect.isclass(cls):
        raise AppError(f"resources= takes classes, got {cls!r}")
    if RESOURCE_TYPES.get(cls.__name__) is not cls:
        simple_step_resource(cls)
    return cls


def _configure_environment(app: App) -> None:
    """What ``SIMPLE_STEPS.main`` reads when it is first imported."""
    os.environ["SIMPLE_STEPS_WORKSPACE"] = app.workspace
    if app.explicit:
        os.environ["SIMPLE_STEPS_SCAN_WORKSPACE"] = "0"
