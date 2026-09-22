"""Collections: sources that are read on demand instead of copied.

A source tool returns a Collection when the items are expensive to read or
change underneath the workflow. The step then stores the *recipe* — a few
fields and a version stamp — and the items are re-read whenever something
iterates it.
"""

from dataclasses import dataclass, field
from typing import Any, Iterator

import pytest

from simple_steps_core import (
    Collection,
    CoreEngine,
    DEFAULT_CODECS,
    ListCollection,
    Resource,
    ResourceContainer,
    ResourceSpec,
    SnapshotError,
    ToolCall,
    ToolRegistry,
    Workflow,
    check_reiterable,
    register_orchestrators,
)


@dataclass
class FakeListing(Collection):
    """A directory listing that records how often it was actually read."""

    names: list[str] = field(default_factory=list)
    version: str = ""
    reads: list[int] = field(default_factory=list)

    def __iter__(self) -> Iterator[Any]:
        self.reads.append(1)
        return iter(self.names)

    def count(self) -> int | None:
        return len(self.names)


@dataclass
class UnsizedFeed(Collection):
    """A source whose length is not known without walking it."""

    limit: int = 3
    version: str = ""

    def __iter__(self) -> Iterator[Any]:
        return (i for i in range(self.limit))


# ── the contract ─────────────────────────────────────────────────────────
def test_a_collection_yields_the_same_items_on_every_pass():
    listing = FakeListing(names=["a.csv", "b.csv"], version="v1")

    assert list(listing) == ["a.csv", "b.csv"]
    assert list(listing) == ["a.csv", "b.csv"]
    check_reiterable(listing)


def test_check_reiterable_catches_a_one_shot_generator():
    """The mistake this design invites: __iter__ that hands back a live generator."""

    @dataclass
    class Drainable(Collection):
        version: str = ""

        def __post_init__(self):
            self._items = iter([1, 2, 3])

        def __iter__(self):
            return self._items

    with pytest.raises(AssertionError, match="not re-iterable"):
        check_reiterable(Drainable())


def test_an_unversioned_collection_never_claims_to_be_unchanged():
    assert ListCollection(items=[1], version="").unchanged_since("") is False
    assert ListCollection(items=[1], version="").unchanged_since(None) is False


def test_the_version_stamp_answers_whether_the_source_moved():
    listing = FakeListing(names=["a.csv"], version="mtime:100")

    assert listing.unchanged_since("mtime:100") is True
    assert listing.unchanged_since("mtime:200") is False


def test_head_reads_only_the_requested_window():
    feed = UnsizedFeed(limit=1000)
    assert feed.head(limit=3) == [0, 1, 2]
    assert feed.head(limit=2, offset=5) == [5, 6]
    assert feed.head(limit=0) == []


def test_count_is_optional_and_shape_says_when_it_is_unknown():
    known = DEFAULT_CODECS.shape(ListCollection(items=[1, 2, 3]))
    assert (known.rows, known.rows_known) == (3, True)

    unknown = DEFAULT_CODECS.shape(UnsizedFeed())
    assert unknown.rows_known is False
    assert unknown.value_type == "UnsizedFeed"


def test_previewing_a_collection_does_not_walk_the_whole_source():
    cells = DEFAULT_CODECS.to_view(UnsizedFeed(limit=10_000), 0, 2)
    assert [c.value for c in cells] == [0, 1]
    assert [c.row_id for c in cells] == ["0", "1"]


# ── snapshots ────────────────────────────────────────────────────────────
def test_a_snapshot_stores_the_recipe_not_the_items():
    listing = FakeListing(names=["a.csv", "b.csv"], version="mtime:100")
    encoding, data = DEFAULT_CODECS.encode(listing)

    assert encoding == "collection"
    assert data["cls"].endswith(":FakeListing")
    assert data["state"]["version"] == "mtime:100"

    restored = DEFAULT_CODECS.decode(encoding, data)
    assert isinstance(restored, FakeListing)
    assert list(restored) == ["a.csv", "b.csv"]
    assert restored.unchanged_since("mtime:100")


def test_decoding_refuses_a_class_that_is_not_a_collection():
    with pytest.raises(SnapshotError, match="not a Collection"):
        DEFAULT_CODECS.decode("collection", {"cls": "builtins:dict", "state": {}})


def test_a_non_dataclass_collection_must_say_how_to_save_itself():
    class Opaque(Collection):
        version = "v1"

        def __iter__(self):
            return iter([])

    with pytest.raises(NotImplementedError, match="override to_state"):
        Opaque().to_state()


# ── end to end ───────────────────────────────────────────────────────────
def _pipeline_registry():
    registry = ToolRegistry()
    register_orchestrators(registry)

    files = ResourceSpec(
        "file_system",
        value={"a.csv": 1, "b.csv": 2, "c.txt": 3},
        registry=registry,
    )

    @files.tool("list_files")
    def list_files(suffix: str = ".csv", fs=Resource()) -> Collection:
        names = sorted(n for n in fs if n.endswith(suffix))
        return ListCollection(items=names, version=f"count:{len(fs)}")

    def is_first(name: str) -> bool:
        return name.startswith("a")

    registry.register("is_first", is_first)
    return registry, files


def test_an_orchestrator_consumes_a_collection_like_a_list():
    registry, files = _pipeline_registry()
    container = ResourceContainer()
    files.install(container)

    workflow = Workflow(CoreEngine(registry), session_id="s")
    workflow.context.resources = container
    workflow["step1"] = ToolCall(operation_id="file_system-list_files")
    workflow["step2"] = ToolCall(
        operation_id="orchestration-filter",
        arguments={"over": "step1", "op": "is_first"},
    )
    workflow.run()

    source = workflow["step1"].output.value
    assert isinstance(source, Collection)
    assert source.version == "count:3"
    assert workflow["step2"].output.value == ["a.csv"]


def test_the_step_holds_the_recipe_so_re_reading_is_the_caller_s_choice():
    """The stored value is the source object; iterating it is what reads."""
    registry = ToolRegistry()
    register_orchestrators(registry)
    listing = FakeListing(names=["a.csv", "b.csv"], version="v1")

    def open_listing() -> Collection:
        return listing

    registry.register("open_listing", open_listing)

    workflow = Workflow(CoreEngine(registry), session_id="s")
    workflow["step1"] = ToolCall(operation_id="open_listing")
    workflow.run()

    # Running the source step alone reads nothing: it only handed back a handle.
    assert listing.reads == []
    assert list(workflow["step1"].output.value) == ["a.csv", "b.csv"]
    assert listing.reads == [1]
