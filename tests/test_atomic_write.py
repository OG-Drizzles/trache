"""Tests for atomic file write utility."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from trache.cache._atomic import atomic_write


class TestAtomicWrite:
    def test_writes_content(self, tmp_path: Path) -> None:
        path = tmp_path / "test.txt"
        atomic_write(path, "hello world")
        assert path.read_text() == "hello world"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "test.txt"
        path.write_text("old content")
        atomic_write(path, "new content")
        assert path.read_text() == "new content"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "test.txt"
        atomic_write(path, "nested")
        assert path.read_text() == "nested"

    def test_original_survives_write_failure(self, tmp_path: Path) -> None:
        path = tmp_path / "test.txt"
        path.write_text("original")

        with patch("os.replace", side_effect=OSError("simulated failure")):
            with pytest.raises(OSError, match="simulated failure"):
                atomic_write(path, "should not persist")

        assert path.read_text() == "original"

    def test_no_temp_files_left_on_failure(self, tmp_path: Path) -> None:
        path = tmp_path / "test.txt"

        with patch("os.replace", side_effect=OSError("simulated failure")):
            with pytest.raises(OSError):
                atomic_write(path, "content")

        # No .tmp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []
