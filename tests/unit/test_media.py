"""Images and video: steps pass handles, bytes live in the media store."""

import pytest

from simple_steps_core import (
    Collection,
    CoreEngine,
    DEFAULT_CODECS,
    ListCollection,
    MediaAsset,
    MediaStore,
    ToolCall,
    ToolRegistry,
    Workflow,
    media_type_of,
    register_orchestrators,
    set_media_store,
)

Image = pytest.importorskip("PIL.Image")


@pytest.fixture
def store(tmp_path):
    """Point new assets at a temp store for the duration of one test."""
    return set_media_store(MediaStore(tmp_path / "media"))


def _image(color="red", size=(64, 32)):
    return Image.new("RGB", size, color)


# ── the store ────────────────────────────────────────────────────────────
def test_bytes_spill_to_disk_and_the_step_keeps_only_a_handle(store):
    asset = MediaAsset.from_image(_image(), name="red")

    assert asset.exists()
    assert asset.path.startswith(str(store.root))
    assert asset.media_type == "image/png"
    assert (asset.width, asset.height) == (64, 32)
    # The handle is small: five short fields, no pixels.
    assert len(str(asset.__dict__)) < 400


def test_identical_bytes_are_written_once(store):
    first = MediaAsset.from_image(_image(), name="a")
    second = MediaAsset.from_image(_image(), name="b")

    assert first.path == second.path
    assert first.version == second.version
    assert len(list(store.root.iterdir())) == 1


def test_different_images_get_different_files(store):
    red = MediaAsset.from_image(_image("red"))
    blue = MediaAsset.from_image(_image("blue"))

    assert red.path != blue.path
    assert red.version != blue.version


def test_from_path_references_a_file_without_copying_it(tmp_path, store):
    original = tmp_path / "clip.mp4"
    original.write_bytes(b"not really a video")

    asset = MediaAsset.from_path(original)

    assert asset.path == str(original)
    assert asset.media_type == "video/mp4"
    assert asset.is_video and not asset.is_image
    # Referencing copies nothing into the store.
    assert not store.root.exists() or list(store.root.iterdir()) == []


def test_a_missing_file_is_reported_rather_than_guessed(tmp_path):
    asset = MediaAsset.from_path(tmp_path / "gone.png")

    assert asset.exists() is False
    assert asset.version == ""
    assert asset.size_bytes is None


def test_opening_a_video_as_an_image_says_why_it_cannot(tmp_path):
    asset = MediaAsset.from_path(tmp_path / "clip.mp4")
    with pytest.raises(TypeError, match="not an image"):
        asset.open()


def test_an_asset_round_trips_through_pillow(store):
    asset = MediaAsset.from_image(_image(size=(10, 20)))
    assert asset.open().size == (10, 20)


def test_media_type_of_reads_the_suffix():
    assert media_type_of("a/b/photo.jpg") == "image/jpeg"
    assert media_type_of("clip.mp4") == "video/mp4"
    assert media_type_of("mystery.zzz") == "application/octet-stream"


def test_the_version_stamp_identifies_the_bytes(store):
    asset = MediaAsset.from_image(_image())
    assert asset.unchanged_since(asset.version) is True
    assert asset.unchanged_since("sha:something-else") is False


# ── snapshots ────────────────────────────────────────────────────────────
def test_a_snapshot_carries_the_handle_not_the_pixels(store):
    asset = MediaAsset.from_image(_image(size=(400, 400)), name="big")
    encoding, data = DEFAULT_CODECS.encode(asset)

    assert encoding == "media"
    assert set(data) == {"path", "media_type", "version", "name", "width", "height"}
    assert len(str(data)) < 500          # regardless of the image's size

    restored = DEFAULT_CODECS.decode(encoding, data)
    assert restored == asset
    assert restored.open().size == (400, 400)


def test_shape_describes_an_asset_without_decoding_it(store):
    shape = DEFAULT_CODECS.shape(MediaAsset.from_image(_image()))
    assert shape.value_type == "MediaAsset"
    assert "width" in shape.columns


# ── in a pipeline ────────────────────────────────────────────────────────
def _pipeline_registry():
    registry = ToolRegistry()
    register_orchestrators(registry)

    def load_images() -> Collection:
        assets = [MediaAsset.from_image(_image(c, (40, 40)), name=c)
                  for c in ("red", "green", "blue")]
        return ListCollection(items=assets, version="v1")

    def thumbnail(image: MediaAsset, size: int = 16) -> MediaAsset:
        picture = image.open()
        picture.thumbnail((size, size))
        return MediaAsset.from_image(picture, name=f"thumb-{image.name}")

    def is_wide(image: MediaAsset) -> bool:
        return (image.width or 0) >= (image.height or 0)

    for fn in (load_images, thumbnail, is_wide):
        registry.register(fn.__name__, fn)
    return registry


def test_mapping_an_operation_over_images_produces_assets(store):
    workflow = Workflow(CoreEngine(_pipeline_registry()), session_id="media")
    workflow["step1"] = ToolCall(operation_id="load_images")
    workflow["step2"] = ToolCall(operation_id="map",
                                 arguments={"over": "step1", "op": "thumbnail"})
    workflow.run()

    produced = workflow["step2"].output.value.ok
    assert len(produced) == 3
    assert all(isinstance(a, MediaAsset) for a in produced)
    assert all(a.exists() for a in produced)
    assert produced[0].open().size == (16, 16)


def test_orchestrations_work_over_a_collection_of_media(store):
    workflow = Workflow(CoreEngine(_pipeline_registry()), session_id="media-filter")
    workflow["step1"] = ToolCall(operation_id="load_images")
    workflow["step2"] = ToolCall(operation_id="filter",
                                 arguments={"over": "step1", "op": "is_wide"})
    workflow.run()

    kept = workflow["step2"].output.value
    assert len(kept) == 3
    assert all(isinstance(a, MediaAsset) for a in kept)
