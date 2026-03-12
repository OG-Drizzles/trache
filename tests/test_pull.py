"""Tests for pull logic (mocked API)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from trache.cache.models import Board, Card, Label, TrelloList
from trache.config import TracheConfig, ensure_cache_structure
from trache.sync.pull import pull_full_board


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

        count = pull_full_board(config, client, cache_dir)

        assert count == 1

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
