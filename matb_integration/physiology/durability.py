"""Small cross-platform durability primitives for research capture files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO


def fsync_directory(path: Path) -> None:
    """Persist directory-entry changes where the host exposes that primitive.

    POSIX filesystems require syncing the containing directory in addition to
    syncing file contents. Windows does not provide a portable Python API for
    opening directory handles with equivalent semantics, so file flush/fsync
    remains the supported guarantee there.
    """

    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(Path(path), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def make_private_directory(path: Path, *, parents: bool = True, exist_ok: bool = True) -> None:
    """Create a directory inaccessible to other local POSIX accounts."""

    destination = Path(path)
    created: list[Path] = []
    cursor = destination
    while not cursor.exists():
        created.append(cursor)
        if not parents or cursor.parent == cursor:
            break
        cursor = cursor.parent
    destination.mkdir(mode=0o700, parents=parents, exist_ok=exist_ok)
    if os.name != "nt":
        for created_directory in created:
            os.chmod(created_directory, 0o700)
        if not created:
            os.chmod(destination, 0o700)
    # Persist each newly-created directory entry, including intermediate
    # parents created by ``parents=True``.
    for created_directory in created:
        fsync_directory(created_directory.parent)


def open_private_exclusive(path: Path, *, binary: bool) -> IO:
    """Create an exclusive 0600 file without relying on the process umask."""

    descriptor = os.open(Path(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    if binary:
        return os.fdopen(descriptor, "wb")
    return os.fdopen(descriptor, "w", encoding="utf-8", newline="")


__all__ = ["fsync_directory", "make_private_directory", "open_private_exclusive"]
