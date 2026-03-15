"""Regression tests for follow-up audit fixes (v0.1.2).

Covers:
- Label order change does NOT bump content_modified_at
- Label-only push does NOT send redundant desc update
- Re-pull failure surfaces in PushResult.errors
- Old checklists/ migration path cleanup
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from trache.cache.db import read_card, write_card, write_labels_raw
from trache.cache.models import Card
from trache.sync.pull import pull_full_board
from trache.sync.push import push_changes

from conftest import make_mock_client, setup_cache


class TestLabelOrderDoesNotBumpContentModifiedAt:
    def test_label_reorder_preserves_content_modified_at(self, tmp_path: Path) -> None:
        """Labels in a different order should NOT bump content_modified_at."""
        cache_dir, config = setup_cache(tmp_path)

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
        client = make_mock_client([card])
        pull_full_board(config, client, cache_dir, force=True)

        stored = read_card("67abc123def4567890fedcba", "clean", cache_dir)
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
        client2 = make_mock_client([card_v2])
        pull_full_board(config, client2, cache_dir, force=True)

        stored2 = read_card("67abc123def4567890fedcba", "clean", cache_dir)
        assert stored2.content_modified_at == first_modified


class TestLabelOnlyPushNoRedundantDesc:
    def test_label_only_change_does_not_send_desc(self, tmp_path: Path) -> None:
        """When only labels change, desc should NOT be included in update_card."""
        cache_dir, config = setup_cache(tmp_path)

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

        write_card(card, "clean", cache_dir)
        labels_data = [
            {"id": "lbl1", "name": "bug", "color": "red"},
            {"id": "lbl2", "name": "feature", "color": "blue"},
        ]
        write_labels_raw(labels_data, "clean", cache_dir)
        write_labels_raw(labels_data, "working", cache_dir)

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
        write_card(working_card, "working", cache_dir)

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
        cache_dir, config = setup_cache(tmp_path)

        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Desc",
        )
        write_card(card, "clean", cache_dir)
        card.title = "Modified"
        write_card(card, "working", cache_dir)

        client = MagicMock()
        client.update_card.return_value = card
        # Make re-pull fail
        client.get_card.side_effect = RuntimeError("API timeout")

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        assert any("Re-pull failed" in e for e in result.errors)


class TestOldChecklistsMigration:
    @pytest.mark.skip(reason="old checklists dir migration not applicable with SQLite backend")
    def test_old_checklists_dir_removed_on_pull(self, tmp_path: Path) -> None:
        """Old flat checklists/ dir is cleaned up during full board pull."""
        pass
