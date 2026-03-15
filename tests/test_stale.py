"""Tests for staleness check."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from trache.cache.models import Board
from trache.config import SyncState, TracheConfig, ensure_cache_structure
from trache.sync.pull import check_staleness


def _setup(tmp_path: Path) -> tuple[Path, TracheConfig]:
    cache_dir = tmp_path / ".trache"
    ensure_cache_structure(cache_dir)
    config = TracheConfig(board_id="board1")
    config.save(cache_dir)
    return cache_dir, config


def _mock_client(activity: datetime | None = None) -> MagicMock:
    client = MagicMock()
    client.get_board.return_value = Board(
        id="board1", name="Test Board", url="",
        date_last_activity=activity,
    )
    return client


class TestStalenessCheck:
    def test_stale_when_no_prior_pull(self, tmp_path: Path) -> None:
        cache_dir, config = _setup(tmp_path)
        t = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        client = _mock_client(activity=t)

        result = check_staleness(config, client, cache_dir)
        assert result.is_stale is True
        assert result.remote_activity == t.isoformat()
        assert result.local_activity is None

    def test_not_stale_when_matching(self, tmp_path: Path) -> None:
        cache_dir, config = _setup(tmp_path)
        t = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

        # Save state matching the board activity
        state = SyncState(board_last_activity=t.isoformat())
        state.save(cache_dir)

        client = _mock_client(activity=t)
        result = check_staleness(config, client, cache_dir)
        assert result.is_stale is False

    def test_stale_when_remote_newer(self, tmp_path: Path) -> None:
        cache_dir, config = _setup(tmp_path)
        t1 = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 15, 14, 0, 0, tzinfo=timezone.utc)

        state = SyncState(board_last_activity=t1.isoformat())
        state.save(cache_dir)

        client = _mock_client(activity=t2)
        result = check_staleness(config, client, cache_dir)
        assert result.is_stale is True
        assert result.local_activity == t1.isoformat()
        assert result.remote_activity == t2.isoformat()
