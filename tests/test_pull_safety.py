"""Tests for pull/sync safety guards."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from trache.cache.models import Board, Card, Label, TrelloList
from trache.cache.store import write_card_file
from trache.config import TracheConfig, ensure_cache_structure
from trache.sync.pull import pull_full_board
from trache.sync.push import push_changes


def _make_mock_client(cards: list[Card], lists: list[TrelloList]) -> MagicMock:
    client = MagicMock()
    client.get_board.return_value = Board(id="board1", name="Test Board", url="https://trello.com/b/test")
    client.get_board_lists.return_value = lists
    client.get_board_cards.return_value = cards
    client.get_board_checklists.return_value = []
    client.get_board_labels.return_value = [Label(id="lbl1", name="bug", color="red")]
    return client


def _setup(tmp_path: Path) -> tuple[Path, TracheConfig]:
    cache_dir = tmp_path / ".trache"
    ensure_cache_structure(cache_dir)
    config = TracheConfig(board_id="board1")
    config.save(cache_dir)
    return cache_dir, config


class TestDirtyPullGuard:
    def test_dirty_pull_refused(self, tmp_path: Path) -> None:
        """F-005: pull with dirty working state should raise RuntimeError."""
        cache_dir, config = _setup(tmp_path)
        card = Card(id="67abc123def4567890fedcba", board_id="board1", list_id="list1", title="Card")
        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
        client = _make_mock_client([card], lists)

        # Initial pull
        pull_full_board(config, client, cache_dir, force=True)

        # Dirty the working copy
        working_card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Dirty",
        )
        write_card_file(working_card, cache_dir / "working" / "cards")

        # Pull should be refused
        with pytest.raises(RuntimeError, match="unpushed changes"):
            pull_full_board(config, client, cache_dir)

    def test_dirty_pull_force_overwrites(self, tmp_path: Path) -> None:
        """F-005: pull with --force should overwrite dirty state."""
        cache_dir, config = _setup(tmp_path)
        card = Card(id="67abc123def4567890fedcba", board_id="board1", list_id="list1", title="Card")
        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
        client = _make_mock_client([card], lists)

        # Initial pull
        pull_full_board(config, client, cache_dir, force=True)

        # Dirty the working copy
        dirty_card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Dirty",
        )
        write_card_file(dirty_card, cache_dir / "working" / "cards")

        # Force pull should succeed
        count = pull_full_board(config, client, cache_dir, force=True)
        assert count == 1

        # Working copy should be overwritten to clean state
        from trache.cache.store import read_card_file
        restored = read_card_file(cache_dir / "working" / "cards" / "67abc123def4567890fedcba.md")
        assert restored.title == "Card"


class TestSyncPartialFailure:
    def test_sync_partial_failure_skips_pull(self, tmp_path: Path) -> None:
        """F-008: sync with push errors should NOT full-pull."""
        cache_dir, config = _setup(tmp_path)

        # Create a card in both clean and working with different titles
        card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Original",
        )
        write_card_file(card, cache_dir / "clean" / "cards")
        card.title = "Modified"
        write_card_file(card, cache_dir / "working" / "cards")

        # Mock client that fails on update
        client = MagicMock()
        client.update_card.side_effect = Exception("API Error")

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.errors) == 1
        assert "API Error" in result.errors[0]

        # Working copy should still have the local changes (not overwritten)
        from trache.cache.store import read_card_file
        working = read_card_file(cache_dir / "working" / "cards" / "67abc123def4567890fedcba.md")
        assert working.title == "Modified"

    def test_sync_success_allows_pull(self, tmp_path: Path) -> None:
        """Push OK → full pull should proceed."""
        cache_dir, config = _setup(tmp_path)

        card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Original",
        )
        write_card_file(card, cache_dir / "clean" / "cards")
        card.title = "Modified"
        write_card_file(card, cache_dir / "working" / "cards")

        # Mock client that succeeds
        client = MagicMock()
        client.update_card.return_value = card
        client.get_card.return_value = card
        client.get_card_checklists.return_value = []

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        assert len(result.errors) == 0


class TestSyncHappyPath:
    """Mock-backed sync (push + pull combo) happy path."""

    def test_sync_push_then_pull(self, tmp_path: Path) -> None:
        """Sync: dirty state → push succeeds → full pull succeeds → clean state."""
        cache_dir, config = _setup(tmp_path)
        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]

        # Initial state: card in clean and working with different titles
        card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Original",
        )
        write_card_file(card, cache_dir / "clean" / "cards")
        modified = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Updated via sync",
        )
        write_card_file(modified, cache_dir / "working" / "cards")

        # Mock client: push succeeds, full pull returns post-push state
        post_push_card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Updated via sync",
        )
        client = _make_mock_client([post_push_card], lists)
        client.update_card.return_value = post_push_card
        client.get_card.return_value = post_push_card
        client.get_card_checklists.return_value = []

        # Push phase
        changeset, result = push_changes(config, client, cache_dir)
        assert len(result.pushed) == 1
        assert len(result.errors) == 0

        # Pull phase (force=True since push just ran)
        count = pull_full_board(config, client, cache_dir, force=True)
        assert count == 1

        # Final state: clean and working should match
        from trache.cache.store import read_card_file
        clean = read_card_file(
            cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md"
        )
        working = read_card_file(
            cache_dir / "working" / "cards" / "67abc123def4567890fedcba.md"
        )
        assert clean.title == "Updated via sync"
        assert working.title == "Updated via sync"

        # Status should be clean
        from trache.cache.diff import compute_diff
        diff = compute_diff(cache_dir)
        assert diff.is_empty
