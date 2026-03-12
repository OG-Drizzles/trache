"""Shared test fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from trache.cache.models import Card, Checklist, ChecklistItem, TrelloList
from trache.config import TracheConfig, ensure_cache_structure


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory with full structure."""
    d = tmp_path / ".trache"
    ensure_cache_structure(d)
    config = TracheConfig(board_id="abc123def456789012345678", board_name="Test Board")
    config.save(d)
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
