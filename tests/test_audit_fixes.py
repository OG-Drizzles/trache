"""Regression tests for follow-up audit fixes (v0.1.2).

Covers:
- Label order change does NOT bump content_modified_at
- Label-only push does NOT send redundant desc update
- Re-pull failure surfaces in PushResult.errors
- Old checklists/ migration path cleanup
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from trache.cache.models import Board, Card, Label
from trache.cache.store import read_card_file, write_card_file
from trache.config import TracheConfig, ensure_cache_structure
from trache.sync.pull import pull_full_board
from trache.sync.push import push_changes


def _make_client(cards, lists=None, checklists=None, labels=None):
    client = MagicMock()
    client.get_board.return_value = Board(id="board1", name="Test Board", url="")
    client.get_board_lists.return_value = lists or []
    client.get_board_cards.return_value = cards
    client.get_board_checklists.return_value = checklists or []
    client.get_board_labels.return_value = labels or [Label(id="lbl1", name="bug", color="red")]
    return client


def _setup(tmp_path):
    cache_dir = tmp_path / ".trache"
    ensure_cache_structure(cache_dir)
    config = TracheConfig(board_id="board1")
    config.save(cache_dir)
    return cache_dir, config


class TestLabelOrderDoesNotBumpContentModifiedAt:
    def test_label_reorder_preserves_content_modified_at(self, tmp_path: Path) -> None:
        """Labels in a different order should NOT bump content_modified_at."""
        cache_dir, config = _setup(tmp_path)

        original_time = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Same",
            labels=["bug", "feature"],
            content_modified_at=original_time,
            last_activity=original_time,
        )

        # First pull
        client = _make_client([card])
        pull_full_board(config, client, cache_dir, force=True)

        stored = read_card_file(cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md")
        first_modified = stored.content_modified_at

        # Re-pull with labels in REVERSED order, same content otherwise
        later_time = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)
        card_v2 = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Same",
            labels=["feature", "bug"],  # reversed order
            content_modified_at=later_time,
            last_activity=later_time,
        )
        client2 = _make_client([card_v2])
        pull_full_board(config, client2, cache_dir, force=True)

        stored2 = read_card_file(cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md")
        assert stored2.content_modified_at == first_modified


class TestLabelOnlyPushNoRedundantDesc:
    def test_label_only_change_does_not_send_desc(self, tmp_path: Path) -> None:
        """When only labels change, desc should NOT be included in update_card."""
        cache_dir, config = _setup(tmp_path)

        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Same description",
            labels=["bug"],
            content_modified_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        )

        write_card_file(card, cache_dir / "clean" / "cards")
        labels_data = [
            {"id": "lbl1", "name": "bug", "color": "red"},
            {"id": "lbl2", "name": "feature", "color": "blue"},
        ]
        (cache_dir / "clean" / "labels.json").write_text(json.dumps(labels_data, indent=2))
        (cache_dir / "working" / "labels.json").write_text(json.dumps(labels_data, indent=2))

        # Change only labels in working copy
        working_card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Same description",
            labels=["bug", "feature"],
            content_modified_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        write_card_file(working_card, cache_dir / "working" / "cards")

        client = MagicMock()
        client.update_card.return_value = working_card
        client.get_card.return_value = working_card
        client.get_card_checklists.return_value = []

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        # Verify update_card was called
        client.update_card.assert_called_once()
        call_args = client.update_card.call_args
        update_fields = call_args[0][1]
        # Should have idLabels but NOT desc (since description didn't change)
        assert "idLabels" in update_fields
        assert "desc" not in update_fields


class TestRepullFailureSurfaced:
    def test_repull_failure_appears_in_errors(self, tmp_path: Path) -> None:
        """Re-pull failure after push must surface in result.errors."""
        cache_dir, config = _setup(tmp_path)

        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Desc",
        )
        write_card_file(card, cache_dir / "clean" / "cards")
        card.title = "Modified"
        write_card_file(card, cache_dir / "working" / "cards")

        client = MagicMock()
        client.update_card.return_value = card
        # Make re-pull fail
        client.get_card.side_effect = RuntimeError("API timeout")

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        assert any("Re-pull failed" in e for e in result.errors)


class TestOldChecklistsMigration:
    def test_old_checklists_dir_removed_on_pull(self, tmp_path: Path) -> None:
        """Old flat checklists/ dir is cleaned up during full board pull."""
        cache_dir, config = _setup(tmp_path)

        # Create old-style flat checklists/ dir
        old_cl_dir = cache_dir / "checklists"
        old_cl_dir.mkdir(parents=True, exist_ok=True)
        (old_cl_dir / "67abc123def4567890fedcba.json").write_text("[]")

        assert old_cl_dir.exists()

        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
        )
        client = _make_client([card])
        pull_full_board(config, client, cache_dir, force=True)

        # Old dir should be gone
        assert not old_cl_dir.exists()
        # New per-side dirs should exist
        assert (cache_dir / "clean" / "checklists").exists()
        assert (cache_dir / "working" / "checklists").exists()
