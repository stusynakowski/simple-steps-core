"""Standard resources: a resource that ships its own tools.

A :class:`ResourceSpec` bundles the runtime object with the tools that use it.
Two rules make a bound tool different from a plain ``@register_tool`` one: its
id is namespaced ``{resource}-{tool}``, and it may inject its own resource and
no other.
"""

import pytest

from simple_steps_core import (
    App,
    AppConfig,
    CoreEngine,
    Resource,
    ResourceBindingError,
    ResourceContainer,
    ResourceSpec,
    SessionContext,
    ToolCall,
    ToolRegistry,
    orchestrator_id,
    qualify,
    register_orchestrators,
    split_qualified,
)


def _spec(registry=None, **kwargs):
    return ResourceSpec(
        "file_system",
        factory=lambda: {"a.csv": "1,2", "b.txt": "x"},
        registry=registry or ToolRegistry(),
        **kwargs,
    )


# ── naming ───────────────────────────────────────────────────────────────
def test_a_bound_tool_is_registered_under_its_resource_name():
    spec = _spec()

    @spec.tool("list_files")
    def list_files(fs=Resource()) -> list[str]:
        return sorted(fs)

    assert list_files.tool_id == "file_system-list_files"
    assert spec.registry.has("file_system-list_files")
    # The bare name is NOT registered: only the orchestrators get aliases.
    assert not spec.registry.has("list_files")


def test_the_bare_decorator_form_uses_the_function_name():
    spec = _spec()

    @spec.tool
    def list_files(fs=Resource()) -> list[str]:
        return sorted(fs)

    assert list_files.tool_id == "file_system-list_files"


def test_two_resources_can_each_ship_a_tool_of_the_same_name():
    registry = ToolRegistry()
    fs = ResourceSpec("file_system", factory=dict, registry=registry)
    db = ResourceSpec("db", factory=dict, registry=registry)

    @fs.tool("list")
    def fs_list(res=Resource()) -> str:
        return "files"

    @db.tool("list")
    def db_list(res=Resource()) -> str:
        return "tables"

    assert fs_list.tool_id == "file_system-list"
    assert db_list.tool_id == "db-list"


def test_qualify_and_split_are_inverses():
    assert qualify("file_system", "list_files") == "file_system-list_files"
    assert split_qualified("file_system-list_files") == ("file_system", "list_files")
    assert split_qualified("unbound") == (None, "unbound")
    # Already-qualified names pass through rather than doubling the prefix.
    assert qualify("file_system", "file_system-list_files") == "file_system-list_files"


# ── binding ──────────────────────────────────────────────────────────────
def test_the_definition_records_its_owner_and_dependency():
    spec = _spec()

    @spec.tool("list_files")
    def list_files(fs=Resource()) -> list[str]:
        return sorted(fs)

    definition = spec.registry.get_definition("file_system-list_files")
    assert definition.resource == "file_system"
    # The dependency is the *container key*, not the parameter name.
    assert definition.dependencies == ["file_system"]
    assert spec.registry.tools_for("file_system") == [definition]


def test_an_unnamed_resource_param_binds_to_the_owner_whatever_it_is_called():
    """The parameter is `anything`; the injected resource is still file_system."""
    spec = _spec()

    @spec.tool("list_files")
    def list_files(anything=Resource()) -> list[str]:
        return sorted(anything)

    engine = CoreEngine(spec.registry)
    ctx = SessionContext(session_id="s")
    ctx.resources = ResourceContainer()
    ctx.resources.register("file_system", lambda: {"a.csv": "1"})

    _ref, value = engine.execute(ToolCall(operation_id="file_system-list_files"), ctx)
    assert value == ["a.csv"]


def test_a_bound_tool_may_not_reach_for_another_resource():
    spec = _spec()

    with pytest.raises(ResourceBindingError) as excinfo:

        @spec.tool("copy_to_db")
        def copy_to_db(fs=Resource(), db=Resource("database")) -> None:
            ...

    message = str(excinfo.value)
    assert "file_system-copy_to_db" in message
    assert "database" in message


def test_naming_its_own_resource_explicitly_is_allowed():
    spec = _spec()

    @spec.tool("list_files")
    def list_files(fs=Resource("file_system")) -> list[str]:
        return sorted(fs)

    assert spec.registry.get_definition("file_system-list_files").dependencies == [
        "file_system"
    ]


def test_an_unbound_tool_honors_an_explicit_resource_name():
    """Resource("name") overrides the container key on plain tools too."""
    registry = ToolRegistry()

    def read_config(cfg=Resource("settings")) -> str:
        return cfg["env"]

    registry.register("read_config", read_config)
    assert registry.get_definition("read_config").dependencies == ["settings"]

    ctx = SessionContext(session_id="s")
    ctx.resources = ResourceContainer()
    ctx.resources.register_value("settings", {"env": "prod"})

    _ref, value = CoreEngine(registry).execute(ToolCall(operation_id="read_config"), ctx)
    assert value == "prod"


# ── installation ─────────────────────────────────────────────────────────
def test_installing_a_spec_declares_its_factory_and_check():
    checked = []
    spec = ResourceSpec(
        "file_system",
        factory=lambda: {"a.csv": "1"},
        check=lambda fs: checked.append(fs) or "ok",
        registry=ToolRegistry(),
    )
    container = ResourceContainer()
    spec.install(container)

    assert container.has("file_system")
    assert container.check("file_system").status == "ok"
    assert checked == [{"a.csv": "1"}]


def test_a_namespace_only_spec_installs_nothing():
    spec = ResourceSpec("orchestration", registry=ToolRegistry())
    container = ResourceContainer()
    spec.install(container)

    assert spec.is_namespace_only
    assert container.names() == []


def test_a_spec_cannot_take_both_a_factory_and_a_value():
    with pytest.raises(ValueError):
        ResourceSpec("x", factory=dict, value={}, registry=ToolRegistry())


def test_the_app_registers_a_spec_and_seeds_it_into_sessions():
    registry = ToolRegistry()
    spec = ResourceSpec("file_system", factory=lambda: {"a.csv": "1"}, registry=registry)

    @spec.tool("list_files")
    def list_files(fs=Resource()) -> list[str]:
        return sorted(fs)

    app = App(AppConfig(orchestrators=False), registry=registry)
    app.register_resource(spec)

    assert spec in app.resource_specs()
    session = app.session("stu")
    assert session.resources.has("file_system")

    workflow = session.workflow()
    workflow["step1"] = list_files()
    workflow.run()
    assert workflow["step1"].output.value == ["a.csv"]
    assert workflow.missing_resources() == []


def test_a_missing_bound_resource_is_reported_against_its_own_name():
    registry = ToolRegistry()
    spec = ResourceSpec("file_system", factory=dict, registry=registry)

    @spec.tool("list_files")
    def list_files(anything=Resource()) -> list[str]:
        return []

    app = App(AppConfig(orchestrators=False), registry=registry)   # spec NOT registered
    workflow = app.session("stu").workflow()
    workflow["step1"] = list_files()

    # Named for the resource it needs, not for the parameter it arrives on.
    assert workflow.missing_resources() == ["file_system"]


# ── the built-in orchestration resource ──────────────────────────────────
def test_the_orchestrators_live_under_the_orchestration_resource():
    registry = ToolRegistry()
    spec = register_orchestrators(registry)

    assert spec.name == "orchestration"
    assert spec.is_namespace_only
    assert sorted(spec.tool_ids()) == [
        "orchestration-collapse",
        "orchestration-expand",
        "orchestration-filter",
        "orchestration-group",
        "orchestration-identity",
        "orchestration-map",
    ]


@pytest.mark.parametrize(
    "short", ["map", "filter", "expand", "collapse", "group", "identity"]
)
def test_the_bare_orchestrator_names_still_resolve(short):
    registry = ToolRegistry()
    register_orchestrators(registry)

    assert registry.has(short)
    assert registry.resolve(short) == f"orchestration-{short}"
    assert registry.get_definition(short).tool_id == f"orchestration-{short}"


def test_aliases_are_not_listed_as_separate_tools():
    registry = ToolRegistry()
    register_orchestrators(registry)

    ids = [d.tool_id for d in registry.list_definitions()]
    assert "map" not in ids
    assert orchestrator_id("map") in ids
    assert len(ids) == 6


def test_an_alias_cannot_shadow_a_real_tool():
    registry = ToolRegistry()

    def map_rows(x: int) -> int:
        return x

    registry.register("map", map_rows)
    with pytest.raises(ValueError):
        registry.add_alias("map", "something-else")
