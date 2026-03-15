"""Shared test fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from trache.cache.models import Board, Card, Checklist, ChecklistItem, Label, TrelloList
from trache.config import TracheConfig, ensure_cache_structure


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory with full multi-board structure."""
    trache_root = tmp_path / ".trache"
    trache_root.mkdir()
    d = trache_root / "boards" / "test"
    ensure_cache_structure(d)
    config = TracheConfig(board_id="abc123def456789012345678", board_name="Test Board")
    config.save(d)
    # Set active board
    (trache_root / "active").write_text("test\n")
    return d


@pytest.fixture
def sample_card() -> Card:
    """A sample card for testing."""
    return Card(
        id="67abc123def4567890fedcba",
        board_id="abc123def456789012345678",
        list_id="234567890abcdef123456789",
        title="Test Card",
        description="This is a test description.",
        created_at=datetime(2026, 3, 13, 1, 22, 33, tzinfo=timezone.utc),
        content_modified_at=datetime(2026, 3, 13, 4, 10, 11, tzinfo=timezone.utc),
        last_activity=datetime(2026, 3, 13, 5, 30, 0, tzinfo=timezone.utc),
        labels=["bug", "priority-high"],
        checklists=[
            Checklist(
                id="cl001",
                name="MVP",
                card_id="67abc123def4567890fedcba",
                items=[
                    ChecklistItem(id="ci001", name="Item 1", state="complete"),
                    ChecklistItem(id="ci002", name="Item 2", state="incomplete"),
                    ChecklistItem(id="ci003", name="Item 3", state="complete"),
                ],
            ),
        ],
    )


@pytest.fixture
def sample_lists() -> list[TrelloList]:
    """Sample lists for testing."""
    return [
        TrelloList(id="234567890abcdef123456789", name="To Do", board_id="abc123", pos=1),
        TrelloList(id="345678901bcdef1234567890", name="In Progress", board_id="abc123", pos=2),
        TrelloList(id="456789012cdef12345678901", name="Done", board_id="abc123", pos=3),
    ]


def seed_board(cards: list[Card], lists: list[TrelloList], cache_dir: Path) -> None:
    """Seed the database with cards (working copy) and lists. Replaces old build_index()."""
    from trache.cache.db import write_cards_batch, write_lists

    write_cards_batch(cards, "working", cache_dir)
    write_lists(lists, cache_dir)


def make_mock_client(cards, lists=None, checklists=None, labels=None):
    """Create a mock TrelloClient with standard board-level responses.

    Args:
        cards: List of Card objects for get_board_cards
        lists: List of TrelloList objects for get_board_lists (default: empty)
        checklists: List of Checklist objects for get_board_checklists (default: empty)
        labels: List of Label objects for get_board_labels (default: [bug/red])
    """
    client = MagicMock()
    client.get_board.return_value = Board(id="board1", name="Test Board", url="")
    client.get_board_lists.return_value = lists or []
    client.get_board_cards.return_value = cards
    client.get_board_checklists.return_value = checklists or []
    client.get_board_labels.return_value = labels or [Label(id="lbl1", name="bug", color="red")]
    return client


def setup_cache(tmp_path: Path) -> tuple[Path, TracheConfig]:
    """Create a minimal cache directory with config for testing."""
    cache_dir = tmp_path / ".trache"
    ensure_cache_structure(cache_dir)
    config = TracheConfig(board_id="board1")
    config.save(cache_dir)
    return cache_dir, config


@pytest.fixture(autouse=True)
def _reset_board_override():
    """Reset the board override after each test."""
    yield
    from trache.cli import _context

    if hasattr(_context, "_board_local"):
        _context._board_local.override = None
    else:
        _context._active_board_override = None


@pytest.fixture(autouse=True)
def _reset_output():
    """Reset the output singleton after each test."""
    yield
    from trache.cli._output import reset_output

    reset_output()
