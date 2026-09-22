"""
Application facade
==================

The top-of-the-hierarchy objects a user holds (see docs/object-model.md):

* :class:`AppConfig` — typed system/app settings.
* :class:`App`       — owns the config, the Tool registry, default Resources,
  and the live Sessions; can also serve them over HTTP (stateless server).
* :class:`Session`   — one user's isolated area: its own Resources and one or
  more Workflows.

Every object exposes ``__repr__`` (one dense line) and ``info()`` (a rich
:class:`SummaryTable`).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .execution.engine import CoreEngine
from .execution.resources import ResourceContainer
from .execution.workflow import Workflow
from .inspect import SummaryTable
from .operations.orchestrations import register_orchestrators
from .operations.registry import REGISTRY, ToolRegistry
from .operations.resource_spec import ResourceSpec


class AppConfig(BaseModel):
    """Typed system & app settings (read at startup)."""

    title: str = "Simple Steps App"
    host: str = "127.0.0.1"
    port: int = 8000
    storage: str = "memory"
    orchestrators: bool = True      # add map/filter/expand/collapse on startup
    freeze: bool = False            # lock the registry after loading

    def info(self) -> SummaryTable:
        table = SummaryTable("AppConfig", columns=["setting", "value"])
        for name, value in self.model_dump().items():
            table.add_row(name, value)
        return table

    def __repr__(self) -> str:
        return f"<AppConfig title={self.title!r} {self.host}:{self.port}>"


class Session:
    """One user's isolated working area: its own Resources + Workflows."""

    def __init__(
        self,
        session_id: str,
        engine: CoreEngine,
        *,
        user: str | None = None,
        resources: ResourceContainer | None = None,
    ) -> None:
        self.session_id = session_id
        self.user = user or session_id
        self.engine = engine
        self.resources = resources if resources is not None else ResourceContainer()
        self._workflows: dict[str, Workflow] = {}

    def workflow(self, name: str = "default") -> Workflow:
        """Get or create a Workflow in this session (sharing its Resources)."""
        if name not in self._workflows:
            wf = Workflow(self.engine, session_id=f"{self.session_id}:{name}")
            wf.context.resources = self.resources  # share the session's resources
            self._workflows[name] = wf
        return self._workflows[name]

    def workflows(self) -> list[Workflow]:
        return list(self._workflows.values())

    def info(self) -> SummaryTable:
        table = SummaryTable(
            f"Session \u00b7 {self.session_id}",
            caption=f"user={self.user} \u00b7 {len(self._workflows)} workflow(s) \u00b7 "
                    f"{len(self.resources.names())} resource(s)",
            columns=["workflow", "steps", "status"],
        )
        for name, wf in self._workflows.items():
            table.add_row(name, len(wf), wf._status_counts(wf.steps))
        if not self._workflows:
            table.add_row("(none)", "-", "-")
        return table

    def __repr__(self) -> str:
        return (f"<Session {self.session_id!r} user={self.user!r} \u00b7 "
                f"{len(self._workflows)} workflow(s)>")


class App:
    """The whole system for one process: config + tools + resources + sessions."""

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        registry: ToolRegistry = REGISTRY,
        resources: ResourceContainer | None = None,
    ) -> None:
        self.config = config or AppConfig()
        self.registry = registry
        self.engine = CoreEngine(registry)
        self.resources = resources if resources is not None else ResourceContainer()
        self._sessions: dict[str, Session] = {}

        self._specs: list[ResourceSpec] = []

        if self.config.orchestrators and not registry.has("map"):
            self._specs.append(register_orchestrators(registry))
        if self.config.freeze and not registry.frozen:
            registry.freeze()

    # ── resources (defaults, seeded into every Session) ──────────────────
    def register_resource(
        self, name: "str | ResourceSpec", factory=None, *, check=None, value: Any = None
    ) -> "App":
        """Declare a default resource seeded into every new Session.

        Takes either a :class:`ResourceSpec` — the standard-resource form, which
        brings its own factory, check and bound tools — or the older
        ``(name, factory)`` pair::

            app.register_resource(file_system)                  # spec
            app.register_resource("db", lambda: connect(), ...)  # pair
        """
        if isinstance(name, ResourceSpec):
            name.install(self.resources)
            self._specs.append(name)
            return self
        if value is not None:
            self.resources.register_value(name, value, check=check)
        else:
            self.resources.register(name, factory, check=check)
        return self

    def resource_specs(self) -> list["ResourceSpec"]:
        """The standard resources registered on this app."""
        return list(self._specs)

    # ── sessions ─────────────────────────────────────────────────────────
    def session(self, user: str = "default") -> Session:
        """Get or create a user's Session (seeded with the default Resources)."""
        if user not in self._sessions:
            self._sessions[user] = Session(
                user, self.engine, user=user, resources=self.resources.clone()
            )
        return self._sessions[user]

    def sessions(self) -> list[Session]:
        return list(self._sessions.values())

    # ── tools ────────────────────────────────────────────────────────────
    def tools(self):
        """The registered tool contracts (list of ToolDefinition)."""
        return self.registry.list_definitions()

    def tools_info(self) -> SummaryTable:
        table = SummaryTable("Tools", columns=["tool", "category", "params"])
        for d in self.tools():
            params = ", ".join(p.name for p in d.params) or "-"
            table.add_row(d.tool_id, d.category or "-", params)
        return table

    # ── inspection ───────────────────────────────────────────────────────
    def info(self) -> SummaryTable:
        table = SummaryTable(
            f"App \u00b7 {self.config.title}",
            columns=["section", "summary"],
        )
        table.add_row("AppConfig", f"{self.config.host}:{self.config.port} \u00b7 "
                                   f"storage={self.config.storage}")
        table.add_row("Tools", f"{len(self.tools())} registered "
                               f"(frozen={self.registry.frozen})")
        table.add_row("Resources", f"{len(self.resources.names())} default(s): "
                                   f"{', '.join(self.resources.names()) or '-'}")
        table.add_row("Sessions", f"{len(self._sessions)} live: "
                                  f"{', '.join(self._sessions) or '-'}")
        return table

    def serve(self) -> None:
        """Serve the registered tools over HTTP (stateless server)."""
        from .serving import build_app

        try:
            import uvicorn
        except ImportError as exc:  # pragma: no cover - optional extra
            raise SystemExit(
                'The server needs FastAPI + uvicorn: pip install "simple-steps-core[api]"'
            ) from exc

        # Rebuild default resources per request via the container's factories.
        app = build_app(
            self.registry, self.engine, title=self.config.title,
            resources={n: (lambda n=n: self.resources.get(n)) for n in self.resources.names()},
        )
        uvicorn.run(app, host=self.config.host, port=self.config.port)

    def __repr__(self) -> str:
        return (f"<App {self.config.title!r} \u00b7 {len(self.tools())} tools \u00b7 "
                f"{len(self._sessions)} session(s)>")
