"""
Collections — sources that are read, not copied
===============================================

A source tool usually returns a ``list``: the engine stores the list in the
session, and a downstream ``map`` reads it back. That is the right thing for a
few dozen items.

It stops being right when the items are **expensive to read** (walking a large
directory, paging an API) or when they **change underneath the workflow**. Then
you want the step to hold a *recipe* rather than a copy:

* the stored value is a handful of fields, so a session snapshot stays small,
* the items are read on demand, every time something iterates it, and
* a cheap ``version`` stamp says whether the outside world moved, so a caller
  can tell "nothing changed" from "I have not looked yet".

Write one as a dataclass with an ``__iter__``::

    @dataclass
    class FileListing(Collection):
        root: str
        pattern: str
        version: str = ""

        def __iter__(self):
            return (str(p) for p in Path(self.root).glob(self.pattern))

        def count(self):
            return None          # a glob does not know without walking it

Two rules make a Collection safe to hand to an orchestrator:

**It must be re-iterable.** ``__iter__`` returns a *fresh* iterator on every
call — note the generator *expression* above rather than a generator function.
A Collection that is itself a generator is drained by the first ``map``, and
then reads as empty in the preview pane, in the next step, and on re-run.
:func:`check_reiterable` asserts this in a test.

**``version`` must be cheap.** It is a stamp — an mtime, a max row id, an
etag — not a hash of the contents. Comparing two stamps is how a workflow
decides whether to re-read a source, so computing one must cost much less than
reading the source.

Snapshots round-trip through :meth:`to_state` / :meth:`from_state`, which
default to the dataclass fields. Subclasses holding something unserializable
(an open handle, a client) should override both to store only what is needed to
rebuild it.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from collections.abc import Iterator
from itertools import islice
from typing import Any


class Collection(ABC):
    """A re-iterable, versioned view over items held outside the session store."""

    #: Cheap stamp of the underlying source; ``""`` means "unversioned".
    version: str = ""

    @abstractmethod
    def __iter__(self) -> Iterator[Any]:
        """Return a **fresh** iterator over the items."""

    def count(self) -> int | None:
        """Number of items when it is known cheaply, else ``None``.

        A directory listing knows its length; a paged API does not. Returning
        ``None`` keeps the UI from claiming a row count it cannot back up.
        """
        return None

    def materialize(self) -> list[Any]:
        """Read every item into a list (the point of no return for laziness)."""
        return list(self)

    def head(self, limit: int = 50, offset: int = 0) -> list[Any]:
        """Read one window of items without materializing the whole source."""
        if limit <= 0:
            return []
        return list(islice(iter(self), max(offset, 0), max(offset, 0) + limit))

    def unchanged_since(self, version: str | None) -> bool:
        """True when this source carries the same stamp as *version*.

        Unversioned collections always report ``False``: with no stamp there is
        no evidence the source held still, and re-reading is the safe answer.
        """
        return bool(self.version) and self.version == version

    # ── snapshot round-trip ──────────────────────────────────────────────
    def to_state(self) -> dict[str, Any]:
        """The fields needed to rebuild this collection."""
        if dataclasses.is_dataclass(self):
            return dataclasses.asdict(self)
        raise NotImplementedError(
            f"{type(self).__name__} is not a dataclass; override to_state()/"
            "from_state() so it can be written to a session snapshot."
        )

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "Collection":
        """Rebuild a collection from :meth:`to_state`."""
        return cls(**state)

    def __repr__(self) -> str:
        known = self.count()
        size = "?" if known is None else str(known)
        stamp = f" @{self.version}" if self.version else ""
        return f"<{type(self).__name__} {size} item(s){stamp}>"


@dataclasses.dataclass
class ListCollection(Collection):
    """A Collection backed by an in-memory list.

    The trivial case: useful for tests, and for wrapping a small source so it
    presents the same contract as a large one.
    """

    items: list[Any] = dataclasses.field(default_factory=list)
    version: str = ""

    def __iter__(self) -> Iterator[Any]:
        return iter(self.items)

    def count(self) -> int | None:
        return len(self.items)


def check_reiterable(collection: Collection) -> None:
    """Raise if *collection* does not yield the same items twice.

    The one mistake this design invites is returning a generator, which the
    first consumer drains. Call this in a test for every Collection you write.
    """
    first = list(collection)
    second = list(collection)
    if first != second:
        raise AssertionError(
            f"{type(collection).__name__} is not re-iterable: a second pass "
            f"yielded {len(second)} item(s) after the first yielded {len(first)}. "
            "__iter__ must return a fresh iterator each call — return a "
            "generator expression or iter(...), not a generator function's result."
        )


@dataclasses.dataclass
class Group:
    """One stratum: the key that defined it, and the rows that fell into it.

    ``rows`` keeps the shape of whatever was grouped — a DataFrame when a
    DataFrame was grouped, a list otherwise — so a per-stratum tool works the
    same way the upstream step did.
    """

    key: Any
    rows: Any = None

    def __len__(self) -> int:
        try:
            return len(self.rows)
        except TypeError:
            return 0

    def __repr__(self) -> str:
        return f"<Group {self.key!r} · {len(self)} row(s)>"


@dataclasses.dataclass
class Groups(Collection):
    """The result of ``group``: strata you can fan out over.

    Unlike a plain dict, **iterating yields :class:`Group` records, not keys**.
    That is the whole point: a stratified table is built by mapping a tool over
    the strata, and that tool needs the key *and* the rows to write its row::

        step3 = group(over=step2, op="speaker_of")
        step4 = map(over=step3, op="summarize_stratum")

        def summarize_stratum(group) -> dict:
            return {"speaker": group.key, "n": len(group), ...}

    Dict-style access is still there when you want one stratum by name —
    ``groups["east"]``, ``groups.keys()``, ``groups.items()``,
    ``groups.to_dict()``.
    """

    groups: list[Group] = dataclasses.field(default_factory=list)
    version: str = ""

    def __iter__(self) -> Iterator[Group]:
        return iter(self.groups)

    def count(self) -> int | None:
        return len(self.groups)

    def __len__(self) -> int:
        return len(self.groups)

    # ── dict-style access ────────────────────────────────────────────────
    def __getitem__(self, key: Any) -> Any:
        """The rows of one stratum, by key."""
        for group in self.groups:
            if group.key == key:
                return group.rows
        raise KeyError(key)

    def __contains__(self, key: Any) -> bool:
        return any(group.key == key for group in self.groups)

    def keys(self) -> list[Any]:
        """The stratum keys, in first-appearance order."""
        return [group.key for group in self.groups]

    def items(self) -> list[tuple[Any, Any]]:
        """``(key, rows)`` pairs, in first-appearance order."""
        return [(group.key, group.rows) for group in self.groups]

    def values(self) -> list[Any]:
        """Each stratum's rows, in first-appearance order."""
        return [group.rows for group in self.groups]

    def to_dict(self) -> dict[Any, Any]:
        """A plain ``{key: rows}`` dict, for code that wants one."""
        return {group.key: group.rows for group in self.groups}

    @classmethod
    def of(cls, buckets: dict[Any, Any], *, version: str = "") -> "Groups":
        """Build Groups from a ``{key: rows}`` mapping."""
        return cls(groups=[Group(key=k, rows=v) for k, v in buckets.items()],
                   version=version)

    def __repr__(self) -> str:
        return f"<Groups {len(self.groups)} stratum(s): {self.keys()!r}>"
