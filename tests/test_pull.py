"""Tests for pull logic (mocked API)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from trache.cache.index import build_index
from trache.cache.models import Board, Card, Label, TrelloList
from trache.cache.store import read_card_file, write_card_file
from trache.config import TracheConfig, ensure_cache_structure
from trache.sync.pull import pull_card, pull_full_board, pull_list


def _make_mock_client(cards: list[Card], lists: list[TrelloList]) -> MagicMock:
    client = MagicMock()
    client.get_board.return_value = Board(id="board1", name="Test Board", url="https://trello.com/b/test")
    client.get_board_lists.return_value = lists
    client.get_board_cards.return_value = cards
    client.get_board_checklists.return_value = []
    client.get_board_labels.return_value = [Label(id="lbl1", name="bug", color="red")]
    return client


class TestPullFullBoard:
    def test_basic_pull(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)

        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
        cards = [
            Card(
                id="67abc123def4567890fedcba",
                board_id="board1",
                list_id="list1",
                title="Card 1",
                description="Description 1",
            ),
        ]
        client = _make_mock_client(cards, lists)

        result = pull_full_board(config, client, cache_dir)

        assert result.cards == 1

        # Check clean snapshot exists
        clean_file = cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md"
        assert clean_file.exists()

        # Check working copy exists
        working_file = cache_dir / "working" / "cards" / "67abc123def4567890fedcba.md"
        assert working_file.exists()

        # Check unified index exists
        assert (cache_dir / "indexes" / "index.json").exists()

        # Check state file
        assert (cache_dir / "state.json").exists()

    def test_pull_creates_board_meta(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)

        client = _make_mock_client([], [])
        pull_full_board(config, client, cache_dir)

        assert (cache_dir / "clean" / "board_meta.md").exists()
        meta = (cache_dir / "clean" / "board_meta.md").read_text()
        assert "Test Board" in meta

    def test_pull_strips_identity_block(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)

        cards = [
            Card(
                id="67abc123def4567890fedcba",
                board_id="board1",
                list_id="list1",
                title="Card 1",
                description=(
                    "---\n# **Card Identifier**\n"
                    "- **Card Name:** Old\n- **Created Date:** old\n"
                    "- **Modified Date:** old\n- **Last Activity:** old\n"
                    "- **Unique ID:** OLD123\n---\n\nActual description"
                ),
            ),
        ]
        client = _make_mock_client(cards, [])

        pull_full_board(config, client, cache_dir)

        from trache.cache.store import read_card_file

        card = read_card_file(cache_dir / "working" / "cards" / "67abc123def4567890fedcba.md")
        assert "Card Identifier" not in card.description
        assert "Actual description" in card.description


def _setup(tmp_path: Path) -> tuple[Path, TracheConfig]:
    cache_dir = tmp_path / ".trache"
    ensure_cache_structure(cache_dir)
    config = TracheConfig(board_id="board1")
    config.save(cache_dir)
    return cache_dir, config


def _seed_board(cache_dir: Path) -> tuple[Card, list[TrelloList]]:
    """Seed cache with one card and one list so indexes exist."""
    card = Card(
        id="67abc123def4567890fedcba", board_id="board1",
        list_id="list1", title="Existing Card",
    )
    lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
    write_card_file(card, cache_dir / "clean" / "cards")
    write_card_file(card, cache_dir / "working" / "cards")
    build_index([card], lists, cache_dir / "indexes")
    return card, lists


class TestPullCard:
    """Targeted pull of a single card by UID6."""

    def test_pull_card_updates_clean_and_working(self, tmp_path: Path) -> None:
        cache_dir, config = _setup(tmp_path)
        card, lists = _seed_board(cache_dir)

        # Mock client returns updated card from server
        server_card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Server Title",
        )
        client = MagicMock()
        client.get_card.return_value = server_card
        client.get_card_checklists.return_value = []

        result = pull_card("FEDCBA", config, client, cache_dir, force=True)

        assert result.title == "Server Title"

        clean = read_card_file(
            cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md"
        )
        working = read_card_file(
            cache_dir / "working" / "cards" / "67abc123def4567890fedcba.md"
        )
        assert clean.title == "Server Title"
        assert working.title == "Server Title"

    def test_pull_card_dirty_refused(self, tmp_path: Path) -> None:
        """Targeted pull refuses if working copy is dirty (no force)."""
        cache_dir, config = _setup(tmp_path)
        card, lists = _seed_board(cache_dir)

        # Dirty the working copy
        dirty = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Dirty Local",
        )
        write_card_file(dirty, cache_dir / "working" / "cards")

        client = MagicMock()
        with pytest.raises(RuntimeError, match="unpushed changes"):
            pull_card("FEDCBA", config, client, cache_dir)

    def test_pull_card_dirty_force_succeeds(self, tmp_path: Path) -> None:
        cache_dir, config = _setup(tmp_path)
        card, lists = _seed_board(cache_dir)

        dirty = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Dirty Local",
        )
        write_card_file(dirty, cache_dir / "working" / "cards")

        server_card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Server Override",
        )
        client = MagicMock()
        client.get_card.return_value = server_card
        client.get_card_checklists.return_value = []

        result = pull_card("FEDCBA", config, client, cache_dir, force=True)
        assert result.title == "Server Override"


class TestScopedDirtyGuard:
    """F-001/O-004: Dirty card A should NOT block pull of unrelated card B."""

    def test_dirty_card_a_does_not_block_pull_of_card_b(self, tmp_path: Path) -> None:
        cache_dir, config = _setup(tmp_path)

        # Seed two cards
        card_a = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Card A",
        )
        card_b = Card(
            id="77abc123def4567890fedcbb", board_id="board1",
            list_id="list1", title="Card B",
        )
        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
        write_card_file(card_a, cache_dir / "clean" / "cards")
        write_card_file(card_a, cache_dir / "working" / "cards")
        write_card_file(card_b, cache_dir / "clean" / "cards")
        write_card_file(card_b, cache_dir / "working" / "cards")
        build_index([card_a, card_b], lists, cache_dir / "indexes")

        # Dirty card A
        dirty_a = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Dirty A",
        )
        write_card_file(dirty_a, cache_dir / "working" / "cards")

        # Pull card B — should succeed despite card A being dirty
        server_b = Card(
            id="77abc123def4567890fedcbb", board_id="board1",
            list_id="list1", title="Server B",
        )
        client = MagicMock()
        client.get_card.return_value = server_b
        client.get_card_checklists.return_value = []

        result = pull_card("FEDCBB", config, client, cache_dir)
        assert result.title == "Server B"

    def test_pull_card_updates_card_timestamps(self, tmp_path: Path) -> None:
        """F-014: pull_card should update SyncState.card_timestamps."""
        cache_dir, config = _setup(tmp_path)
        card, lists = _seed_board(cache_dir)

        from datetime import datetime, timezone
        server_card = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Server",
            last_activity=datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        client = MagicMock()
        client.get_card.return_value = server_card
        client.get_card_checklists.return_value = []

        pull_card("FEDCBA", config, client, cache_dir, force=True)

        from trache.config import SyncState
        state = SyncState.load(cache_dir)
        assert server_card.id in state.card_timestamps
        assert "2026-03-15" in state.card_timestamps[server_card.id]


class TestPullList:
    """Targeted pull of all cards in a list."""

    def test_pull_list_writes_all_cards(self, tmp_path: Path) -> None:
        cache_dir, config = _setup(tmp_path)
        _card, lists = _seed_board(cache_dir)

        # Server returns two cards in the list
        server_cards = [
            Card(
                id="67abc123def4567890fedcba", board_id="board1",
                list_id="list1", title="Card A",
            ),
            Card(
                id="77abc123def4567890fedcbb", board_id="board1",
                list_id="list1", title="Card B",
            ),
        ]
        client = MagicMock()
        client.get_list_cards.return_value = server_cards
        client.get_card_checklists.return_value = []

        result = pull_list("To Do", config, client, cache_dir, force=True)
        assert len(result) == 2

        for sc in server_cards:
            assert (cache_dir / "clean" / "cards" / f"{sc.id}.md").exists()
            assert (cache_dir / "working" / "cards" / f"{sc.id}.md").exists()

    def test_pull_list_dirty_refused(self, tmp_path: Path) -> None:
        """Pull list is refused if a card in the list has unpushed changes."""
        cache_dir, config = _setup(tmp_path)
        _card, lists = _seed_board(cache_dir)

        # Dirty the working copy
        dirty = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Dirty",
        )
        write_card_file(dirty, cache_dir / "working" / "cards")

        # API returns the card in this list — scoped check finds it dirty
        server_cards = [
            Card(id="67abc123def4567890fedcba", board_id="board1",
                 list_id="list1", title="Server Card"),
        ]
        client = MagicMock()
        client.get_list_cards.return_value = server_cards
        with pytest.raises(RuntimeError, match="unpushed changes"):
            pull_list("To Do", config, client, cache_dir)

    def test_pull_list_dirty_force_succeeds(self, tmp_path: Path) -> None:
        cache_dir, config = _setup(tmp_path)
        _card, lists = _seed_board(cache_dir)

        dirty = Card(
            id="67abc123def4567890fedcba", board_id="board1",
            list_id="list1", title="Dirty",
        )
        write_card_file(dirty, cache_dir / "working" / "cards")

        server_cards = [
            Card(
                id="67abc123def4567890fedcba", board_id="board1",
                list_id="list1", title="Server Card",
            ),
        ]
        client = MagicMock()
        client.get_list_cards.return_value = server_cards
        client.get_card_checklists.return_value = []

        result = pull_list("To Do", config, client, cache_dir, force=True)
        assert len(result) == 1
        assert result[0].title == "Server Card"
