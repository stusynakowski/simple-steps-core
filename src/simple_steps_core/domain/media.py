"""
Media assets — images and video that steps pass around by handle
================================================================

An image or a clip must not live in the session store as decoded pixels. Map a
resize over 500 photos that way and the store holds 500 decoded images, the
snapshot has to base64 every one, and the dashboard re-renders them all.

So a step holds a :class:`MediaAsset`: a small handle naming a file on disk,
its media type, and a ``version`` stamp. Bytes **spill to disk** when the asset
is created; only the handle travels between steps.

Writing a tool is still ordinary Python::

    @register_tool("thumbnail")
    def thumbnail(image: MediaAsset, size: int = 128) -> MediaAsset:
        picture = image.open()              # a PIL.Image
        picture.thumbnail((size, size))
        return MediaAsset.from_image(picture, name=f"thumb-{image.name}")

Where the bytes land
--------------------

:func:`get_media_store` returns the active :class:`MediaStore` — by default a
directory under the system temp dir, created on first use, so nothing needs
configuring to try things out. Point it somewhere durable for real work::

    set_media_store(MediaStore("~/.simple-steps/media"))

Files are **content addressed**: the name is a hash of the bytes, so writing
the same image twice writes one file, and an asset's ``version`` is that hash.
Two steps that produce identical output are recognizably identical.

:meth:`MediaAsset.from_path` is the other direction — it *references* a file
already on disk without copying it, stamping the version from size and mtime.
That is what a source tool listing a media directory should return.

Pillow is imported lazily inside :meth:`MediaAsset.open`, so core never
requires it; only tools that actually decode an image do.
"""

from __future__ import annotations

import dataclasses
import hashlib
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any

#: Extensions Pillow writes for the formats worth defaulting to.
_IMAGE_FORMATS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


class MediaStore:
    """A directory that holds media bytes, addressed by content hash."""

    def __init__(self, root: str | os.PathLike) -> None:
        self.root = Path(root).expanduser()

    def put(self, data: bytes, suffix: str = "") -> Path:
        """Write *data* under its content hash and return the path.

        Writing the same bytes twice is a no-op the second time: the name is
        the hash, so the file is already there.
        """
        digest = hashlib.sha256(data).hexdigest()[:16]
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{digest}{suffix}"
        if not path.exists():
            # Write to a temp name first so a crash mid-write cannot leave a
            # truncated file sitting at a hash that claims to be complete.
            partial = path.with_suffix(path.suffix + ".partial")
            partial.write_bytes(data)
            partial.replace(path)
        return path

    def __repr__(self) -> str:
        return f"<MediaStore {str(self.root)!r}>"


_STORE: MediaStore | None = None


def get_media_store() -> MediaStore:
    """The active media store, defaulting to a temp directory."""
    global _STORE
    if _STORE is None:
        _STORE = MediaStore(Path(tempfile.gettempdir()) / "simple-steps-media")
    return _STORE


def set_media_store(store: MediaStore | str | os.PathLike) -> MediaStore:
    """Point new assets at *store* (a MediaStore or a directory path)."""
    global _STORE
    _STORE = store if isinstance(store, MediaStore) else MediaStore(store)
    return _STORE


def media_type_of(path: str | os.PathLike) -> str:
    """Best-effort media type for a path (``application/octet-stream`` if unknown)."""
    guessed, _encoding = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def media_type_for_format(format: str) -> str:
    """Map a Pillow format name (``"PNG"``) to a media type (``"image/png"``)."""
    normalized = (format or "").upper()
    if normalized in ("JPG", "JPEG"):
        return "image/jpeg"
    return f"image/{normalized.lower()}" if normalized else "application/octet-stream"


@dataclasses.dataclass
class MediaAsset:
    """A handle to one image or video file.

    ``path`` is where the bytes are, ``media_type`` says what they are, and
    ``version`` identifies *these* bytes — a content hash for assets this
    library wrote, or ``size:mtime`` for a file it merely references.
    """

    path: str
    media_type: str = "application/octet-stream"
    version: str = ""
    name: str = ""
    width: int | None = None
    height: int | None = None

    # ── constructors ─────────────────────────────────────────────────────
    @classmethod
    def from_path(cls, path: str | os.PathLike, *, name: str = "") -> "MediaAsset":
        """Reference a file already on disk, without copying it."""
        resolved = Path(path).expanduser()
        try:
            stat = resolved.stat()
            version = f"size:{stat.st_size}:mtime:{stat.st_mtime_ns}"
        except OSError:
            version = ""
        return cls(
            path=str(resolved),
            media_type=media_type_of(resolved),
            version=version,
            name=name or resolved.name,
        )

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        media_type: str = "application/octet-stream",
        name: str = "",
        store: MediaStore | None = None,
    ) -> "MediaAsset":
        """Spill *data* to the media store and return a handle to it."""
        suffix = _IMAGE_FORMATS.get(media_type) or mimetypes.guess_extension(
            media_type
        ) or ""
        path = (store or get_media_store()).put(data, suffix)
        return cls(
            path=str(path),
            media_type=media_type,
            version=f"sha:{path.stem}",
            name=name or path.name,
        )

    @classmethod
    def from_image(
        cls,
        image: Any,
        *,
        format: str = "PNG",
        name: str = "",
        store: MediaStore | None = None,
    ) -> "MediaAsset":
        """Encode a PIL image, spill it to the store, and return the handle.

        The image's own dimensions are recorded on the asset so the dashboard
        can size a thumbnail without decoding the file again.
        """
        import io

        buffer = io.BytesIO()
        image.save(buffer, format=format)
        media_type = media_type_for_format(format)
        asset = cls.from_bytes(
            buffer.getvalue(), media_type=media_type, name=name, store=store
        )
        size = getattr(image, "size", None)
        if size and len(size) == 2:
            asset.width, asset.height = int(size[0]), int(size[1])
        return asset

    # ── reading ──────────────────────────────────────────────────────────
    def read_bytes(self) -> bytes:
        return Path(self.path).read_bytes()

    def open(self) -> Any:
        """Decode this asset as a ``PIL.Image`` (images only)."""
        if not self.is_image:
            raise TypeError(
                f"{self.name or self.path!r} is {self.media_type}, not an image; "
                "use read_bytes() or hand the path to a video tool."
            )
        from PIL import Image

        return Image.open(self.path)

    def exists(self) -> bool:
        return Path(self.path).exists()

    @property
    def size_bytes(self) -> int | None:
        try:
            return Path(self.path).stat().st_size
        except OSError:
            return None

    @property
    def is_image(self) -> bool:
        return self.media_type.startswith("image/")

    @property
    def is_video(self) -> bool:
        return self.media_type.startswith("video/")

    def unchanged_since(self, version: str | None) -> bool:
        """True when this handle points at the same bytes as *version*."""
        return bool(self.version) and self.version == version

    def __repr__(self) -> str:
        dimensions = (
            f" {self.width}x{self.height}"
            if self.width and self.height
            else ""
        )
        return f"<MediaAsset {self.name or Path(self.path).name!r} {self.media_type}{dimensions}>"
