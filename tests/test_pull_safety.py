"""Tests for pull/sync safety guards."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import json

from trache.cache.db import read_card, write_card, write_lists
from trache.cache.models import Board, Card, Label, TrelloList
from trache.config import TracheConfig, ensure_cache_structure
from trache.sync.pull import pull_full_board
from trache.sync.push import push_changes

from conftest import seed_board, setup_cache


def _make_client(cards, lists=None, activity=None):
    """Make a mock client with a board that has date_last_activity set."""
    client = MagicMock()
    client.get_board.return_value = Board(
        id="board1", name="Test Board", url="",
        date_last_activity=activity or datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    client.get_board_lists.return_value = lists or []
    client.get_board_cards.return_value = cards
    client.get_board_checklists.return_value = []
    client.get_board_labels.return_value = [Label(id="lbl1", name="bug", color="red")]
    return client


class TestDirtyPullGuard:
    def test_dirty_pull_refused(self, tmp_path: Path) -> None:
        """F-005: pull with dirty working state should raise RuntimeError."""
        cache_dir, config = setup_cache(tmp_path)
        card = Card(id="67abc123def4567890fedcba", board_id="board1", list_id="list1", title="Card")
        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
        t1 = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        client = _make_client([card], lists, activity=t1)

        # Initial pull
        pull_full_board(config, client, cache_dir, force=True)

        # Dirty the working copy
        working_card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Dirty",
        )
        write_card(working_card, "working", cache_dir)

        # Use a new client with later activity so stale check passes
        t2 = datetime(2026, 3, 15, 13, 0, 0, tzinfo=timezone.utc)
        client2 = _make_client([card], lists, activity=t2)

        # Pull should be refused due to dirty state
        with pytest.raises(RuntimeError, match="unpushed changes"):
            pull_full_board(config, client2, cache_dir)

    def test_dirty_pull_force_overwrites(self, tmp_path: Path) -> None:
        """F-005: pull with --force should overwrite dirty state."""
        cache_dir, config = setup_cache(tmp_path)
        card = Card(id="67abc123def4567890fedcba", board_id="board1", list_id="list1", title="Card")
        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
        t1 = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        client = _make_client([card], lists, activity=t1)

        # Initial pull
        pull_full_board(config, client, cache_dir, force=True)

        # Dirty the working copy
        dirty_card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Dirty",
        )
        write_card(dirty_card, "working", cache_dir)

        # Force pull should succeed
        result = pull_full_board(config, client, cache_dir, force=True)
        assert result.cards == 1

        # Working copy should be overwritten to clean state
        restored = read_card("67abc123def4567890fedcba", "working", cache_dir)
        assert restored.title == "Card"


class TestSyncPartialFailure:
    def test_sync_partial_failure_skips_pull(self, tmp_path: Path) -> None:
        """F-008: sync with push errors should NOT full-pull."""
        cache_dir, config = setup_cache(tmp_path)

        card_clean = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Original",
        )
        card_working = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Modified",
        )
        write_card(card_clean, "clean", cache_dir)
        write_card(card_working, "working", cache_dir)

        # Mock client that fails on update
        client = MagicMock()
        client.update_card.side_effect = Exception("API Error")

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.errors) == 1
        assert "API Error" in result.errors[0]

        # Working copy should still have the local changes
        working = read_card("67abc123def4567890fedcba", "working", cache_dir)
        assert working.title == "Modified"

    def test_sync_success_allows_pull(self, tmp_path: Path) -> None:
        """Push OK → full pull should proceed."""
        cache_dir, config = setup_cache(tmp_path)

        card_clean = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Original",
        )
        card_working = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Modified",
        )
        write_card(card_clean, "clean", cache_dir)
        write_card(card_working, "working", cache_dir)

        # Mock client that succeeds
        client = MagicMock()
        client.update_card.return_value = card_working
        client.get_card.return_value = card_working
        client.get_card_checklists.return_value = []

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        assert len(result.errors) == 0


class TestSyncHappyPath:
    """Mock-backed sync (push + pull combo) happy path."""

    def test_sync_push_then_pull(self, tmp_path: Path) -> None:
        """Sync: dirty state → push succeeds → full pull succeeds → clean state."""
        cache_dir, config = setup_cache(tmp_path)
        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]

        card_clean = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Original",
        )
        card_working = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Updated via sync",
        )
        write_card(card_clean, "clean", cache_dir)
        write_card(card_working, "working", cache_dir)

        post_push_card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Updated via sync",
        )
        client = _make_client([post_push_card], lists)
        client.update_card.return_value = post_push_card
        client.get_card.return_value = post_push_card
        client.get_card_checklists.return_value = []

        # Push phase
        changeset, result = push_changes(config, client, cache_dir)
        assert len(result.pushed) == 1
        assert len(result.errors) == 0

        # Pull phase
        pull_result = pull_full_board(config, client, cache_dir, force=True)
        assert pull_result.cards == 1

        # Final state: clean and working should match
        clean = read_card("67abc123def4567890fedcba", "clean", cache_dir)
        working = read_card("67abc123def4567890fedcba", "working", cache_dir)
        assert clean.title == "Updated via sync"
        assert working.title == "Updated via sync"

        # Status should be clean
        from trache.cache.diff import compute_diff
        diff = compute_diff(cache_dir)
        assert diff.is_empty


# ---------------------------------------------------------------------------
# F-003: Sync machine output tests
# ---------------------------------------------------------------------------


def _setup_sync_cli(tmp_path: Path, monkeypatch) -> Path:
    """Set up cache for CLI sync tests with machine output."""
    monkeypatch.chdir(tmp_path)
    from trache.cli._output import reset_output
    reset_output()

    trache_root = tmp_path / ".trache"
    trache_root.mkdir(exist_ok=True)
    cache_dir = trache_root / "boards" / "test"
    ensure_cache_structure(cache_dir)
    config = TracheConfig(board_id="board1")
    config.save(cache_dir)
    (trache_root / "active").write_text("test\n")

    lists = [TrelloList(id="list1", name="To Do", pos=1)]
    write_lists(lists, cache_dir)
    card = Card(id="67abc123def4567890fedcba", board_id="board1", list_id="list1", title="Card")
    write_card(card, "clean", cache_dir)
    write_card(card, "working", cache_dir)
    seed_board([card], lists, cache_dir)
    return cache_dir


class TestSyncMachineOutput:
    def test_sync_machine_output(self, tmp_path: Path, monkeypatch) -> None:
        """F-003: sync in machine mode returns JSON with push and pull keys."""
        cache_dir = _setup_sync_cli(tmp_path, monkeypatch)

        # Dirty a card so push has something to do
        dirty = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Updated",
        )
        write_card(dirty, "working", cache_dir)

        # Mock the API client
        post_push = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Updated",
        )
        client = _make_client([post_push], [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)])
        client.update_card.return_value = post_push
        client.get_card.return_value = post_push
        client.get_card_checklists.return_value = []

        with monkeypatch.context() as m:
            m.setattr("trache.cli.app.get_client_and_config", lambda _: (client, TracheConfig(board_id="board1")))
            from trache.cli.app import app
            from typer.testing import CliRunner
            runner = CliRunner()
            result = runner.invoke(app, ["sync"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip().split("\n")[-1])
        assert data["ok"] is True
        assert "push" in data
        assert "pull" in data

    def test_sync_dry_run_machine_output(self, tmp_path: Path, monkeypatch) -> None:
        """F-003: sync --dry-run in machine mode returns JSON with pull=None."""
        cache_dir = _setup_sync_cli(tmp_path, monkeypatch)

        # Dirty a card
        dirty = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Updated",
        )
        write_card(dirty, "working", cache_dir)

        client = _make_client([], [])
        with monkeypatch.context() as m:
            m.setattr("trache.cli.app.get_client_and_config", lambda _: (client, TracheConfig(board_id="board1")))
            from trache.cli.app import app
            from typer.testing import CliRunner
            runner = CliRunner()
            result = runner.invoke(app, ["sync", "--dry-run"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip().split("\n")[-1])
        assert data["ok"] is True
        assert data["dry_run"] is True
        assert data["pull"] is None
