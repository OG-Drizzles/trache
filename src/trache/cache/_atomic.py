"""Atomic file writes using tempfile + os.replace."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically.

    Uses tempfile.mkstemp in the same directory, then os.replace to
    atomically swap the file. If the process crashes mid-write, the
    original file remains intact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    fd_closed = False
    try:
        os.write(fd, content.encode())
        os.close(fd)
        fd_closed = True
        os.replace(tmp_path, path)
    except BaseException:
        if not fd_closed:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
