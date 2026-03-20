"""Tests for push logic (mocked API)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from trache.cache.db import read_card, write_card, write_checklists_raw
from trache.cache.models import Card, Checklist, ChecklistItem
from trache.config import TracheConfig, ensure_cache_structure
from trache.sync.push import push_changes


class TestPushChanges:
    def _setup_cache(self, tmp_path: Path) -> tuple[Path, TracheConfig]:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)
        return cache_dir, config

    def test_push_no_changes(self, tmp_path: Path) -> None:
        cache_dir, config = self._setup_cache(tmp_path)
        client = MagicMock()

        changeset, result = push_changes(config, client, cache_dir)
        assert changeset.is_empty
        assert result.total == 0

    def test_push_dry_run(self, tmp_path: Path, sample_card: Card) -> None:
        cache_dir, config = self._setup_cache(tmp_path)

        write_card(sample_card, "clean", cache_dir)
        sample_card.title = "Modified"
        write_card(sample_card, "working", cache_dir)

        client = MagicMock()
        changeset, result = push_changes(config, client, cache_dir, dry_run=True)

        assert not changeset.is_empty
        assert len(result.pushed) == 1
        # Dry run should not call any API methods
        client.update_card.assert_not_called()

    def test_push_modified_card(self, tmp_path: Path, sample_card: Card) -> None:
        cache_dir, config = self._setup_cache(tmp_path)

        write_card(sample_card, "clean", cache_dir)
        sample_card.title = "Modified Title"
        write_card(sample_card, "working", cache_dir)

        # Mock client — update_card returns the card, get_card for re-pull
        client = MagicMock()
        client.update_card.return_value = sample_card
        client.get_card.return_value = sample_card
        client.get_card_checklists.return_value = []

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        client.update_card.assert_called_once()

    def test_push_added_card(self, tmp_path: Path, sample_card: Card) -> None:
        cache_dir, config = self._setup_cache(tmp_path)

        sample_card.id = "new_temp_abc123d4t~"
        sample_card.uid6 = "3D4T~"  # Reset uid6 manually for temp ID
        write_card(sample_card, "working", cache_dir)

        client = MagicMock()
        new_card = Card(
            id="real_id_from_trello_here",
            title=sample_card.title,
            list_id=sample_card.list_id,
        )
        client.create_card.return_value = new_card
        client.get_card.return_value = new_card
        client.get_card_checklists.return_value = []

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.created) == 1
        client.create_card.assert_called_once()


class TestPushFailurePreservation:
    """Verify that push failures do not destroy local working state."""

    def _setup_cache(self, tmp_path: Path) -> tuple[Path, TracheConfig]:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)
        return cache_dir, config

    def test_api_failure_preserves_working_copy(
        self, tmp_path: Path, sample_card: Card
    ) -> None:
        """If API update fails, working copy retains local modification."""
        cache_dir, config = self._setup_cache(tmp_path)

        write_card(sample_card, "clean", cache_dir)
        sample_card.title = "My Important Local Edit"
        write_card(sample_card, "working", cache_dir)

        # Mock client that raises on update
        client = MagicMock()
        client.update_card.side_effect = Exception("API timeout")

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.errors) == 1
        assert "API timeout" in result.errors[0]

        # Working copy must still have the local modification
        working = read_card(sample_card.id, "working", cache_dir)
        assert working.title == "My Important Local Edit"

        # Clean copy should be unchanged (original)
        clean = read_card(sample_card.id, "clean", cache_dir)
        assert clean.title == "Test Card"

    def test_no_destructive_side_effects(
        self, tmp_path: Path, sample_card: Card
    ) -> None:
        """Push failure should not delete files or corrupt indexes."""
        cache_dir, config = self._setup_cache(tmp_path)

        write_card(sample_card, "clean", cache_dir)
        sample_card.title = "Changed"
        write_card(sample_card, "working", cache_dir)

        client = MagicMock()
        client.update_card.side_effect = Exception("Network error")

        push_changes(config, client, cache_dir)

        # Both records should still exist in the database
        clean = read_card(sample_card.id, "clean", cache_dir)
        assert clean is not None
        working = read_card(sample_card.id, "working", cache_dir)
        assert working is not None


class TestStaleStateBehaviour:
    """Documents current local-wins behaviour on push.

    When a card is modified locally and pushed, the local version wins.
    This is not conflict resolution — it's last-writer-wins at push time.
    """

    def _setup_cache(self, tmp_path: Path) -> tuple[Path, TracheConfig]:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)
        return cache_dir, config

    def test_local_wins_on_push(self, tmp_path: Path, sample_card: Card) -> None:
        """Documents: local modification pushed → server accepts → re-pull returns our changes."""
        cache_dir, config = self._setup_cache(tmp_path)

        write_card(sample_card, "clean", cache_dir)
        sample_card.title = "Local Wins Title"
        write_card(sample_card, "working", cache_dir)

        # Server accepts the push and returns the updated card on re-pull
        post_push_card = Card(
            id=sample_card.id,
            board_id=sample_card.board_id,
            list_id=sample_card.list_id,
            title="Local Wins Title",
        )
        client = MagicMock()
        client.update_card.return_value = post_push_card
        client.get_card.return_value = post_push_card
        client.get_card_checklists.return_value = []

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        assert len(result.errors) == 0

        # After re-pull, working copy has our title
        working = read_card(sample_card.id, "working", cache_dir)
        assert working.title == "Local Wins Title"


class TestPushNewCardChecklists:
    """F-001: Checklists on locally-created cards must be pushed."""

    def _setup_cache(self, tmp_path: Path) -> tuple[Path, TracheConfig]:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)
        return cache_dir, config

    def test_push_new_card_with_checklists(self, tmp_path: Path) -> None:
        cache_dir, config = self._setup_cache(tmp_path)

        temp_id = "new_temp_abc123d4t~"
        card = Card(
            id=temp_id, title="Card With Checklist",
            list_id="list1", board_id="board1",
        )
        write_card(card, "working", cache_dir)

        cl_data = [
            {
                "id": "temp_cl_1", "name": "Tasks", "card_id": temp_id,
                "items": [
                    {"id": "item1", "name": "Do thing A", "state": "incomplete", "pos": 1},
                    {"id": "item2", "name": "Do thing B", "state": "incomplete", "pos": 2},
                ],
            }
        ]
        write_checklists_raw(temp_id, cl_data, "working", cache_dir)

        # Mock client
        real_card = Card(
            id="real_trello_card_id_here", title="Card With Checklist", list_id="list1"
        )
        new_cl = Checklist(id="real_cl_1", name="Tasks", card_id=real_card.id)
        item_a = ChecklistItem(id="real_item_a", name="Do thing A")
        item_b = ChecklistItem(id="real_item_b", name="Do thing B")

        client = MagicMock()
        client.create_card.return_value = real_card
        client.get_card.return_value = real_card
        client.get_card_checklists.return_value = []
        client.create_checklist.return_value = new_cl
        client.add_checklist_item.side_effect = [item_a, item_b]

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.created) == 1
        client.create_checklist.assert_called_once_with(real_card.id, "Tasks")
        assert client.add_checklist_item.call_count == 2
        client.update_checklist_item.assert_not_called()  # no complete items

    def test_push_new_card_with_checked_items(self, tmp_path: Path) -> None:
        cache_dir, config = self._setup_cache(tmp_path)

        temp_id = "new_temp_xyz789e5t~"
        card = Card(id=temp_id, title="Checked", list_id="list1", board_id="board1")
        write_card(card, "working", cache_dir)

        cl_data = [
            {
                "id": "temp_cl_2", "name": "Done", "card_id": temp_id,
                "items": [
                    {"id": "i1", "name": "Already done", "state": "complete", "pos": 1},
                ],
            }
        ]
        write_checklists_raw(temp_id, cl_data, "working", cache_dir)

        real_card = Card(id="real_checked_card_id_ok", title="Checked", list_id="list1")
        new_cl = Checklist(id="real_cl_2", name="Done", card_id=real_card.id)
        new_item = ChecklistItem(id="real_done_item", name="Already done")

        client = MagicMock()
        client.create_card.return_value = real_card
        client.get_card.return_value = real_card
        client.get_card_checklists.return_value = []
        client.create_checklist.return_value = new_cl
        client.add_checklist_item.return_value = new_item

        push_changes(config, client, cache_dir)

        client.update_checklist_item.assert_called_once_with(
            real_card.id, new_item.id, "complete"
        )

    def test_push_new_card_without_checklists(self, tmp_path: Path) -> None:
        cache_dir, config = self._setup_cache(tmp_path)

        temp_id = "new_temp_noclst99t~"
        card = Card(id=temp_id, title="No CL", list_id="list1", board_id="board1")
        write_card(card, "working", cache_dir)

        real_card = Card(id="real_nocl_card_id_here", title="No CL", list_id="list1")

        client = MagicMock()
        client.create_card.return_value = real_card
        client.get_card.return_value = real_card
        client.get_card_checklists.return_value = []

        push_changes(config, client, cache_dir)

        client.create_checklist.assert_not_called()
        client.add_checklist_item.assert_not_called()


class TestPushDeletedCardCleanup:
    """F-002: Archived cards must have clean files and index removed."""

    def _setup_cache(self, tmp_path: Path) -> tuple[Path, TracheConfig]:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)
        return cache_dir, config

    def test_push_deleted_card_cleans_local_state(self, tmp_path: Path, sample_card: Card) -> None:
        cache_dir, config = self._setup_cache(tmp_path)

        # Write only to clean (simulates a card whose working copy was deleted → "deleted" diff)
        write_card(sample_card, "clean", cache_dir)

        # Also write an empty clean checklist record
        write_checklists_raw(sample_card.id, [], "clean", cache_dir)

        # Write lists to the DB so the index lookup works, without touching working cards
        from trache.cache.db import write_lists
        from trache.cache.models import TrelloList
        lists = [TrelloList(id=sample_card.list_id, name="To Do", board_id="board1", pos=1)]
        write_lists(lists, cache_dir)

        client = MagicMock()
        client.archive_card.return_value = sample_card

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.archived) == 1
        # Clean record should be removed from the database
        with pytest.raises(FileNotFoundError):
            read_card(sample_card.id, "clean", cache_dir)
        # Index should no longer contain the card
        from trache.cache.db import load_cards_index
        cards_by_id = load_cards_index(cache_dir)
        assert sample_card.id not in cards_by_id

    def test_push_deleted_card_idempotent(self, tmp_path: Path, sample_card: Card) -> None:
        cache_dir, config = self._setup_cache(tmp_path)

        write_card(sample_card, "clean", cache_dir)

        # Write lists to the DB without adding the card to working (preserves "deleted" diff state)
        from trache.cache.db import write_lists
        from trache.cache.models import TrelloList
        lists = [TrelloList(id=sample_card.list_id, name="To Do", board_id="board1", pos=1)]
        write_lists(lists, cache_dir)

        client = MagicMock()
        client.archive_card.return_value = sample_card

        # First push archives
        push_changes(config, client, cache_dir)

        # Second push should show nothing to push
        changeset2, result2 = push_changes(config, client, cache_dir)
        assert changeset2.is_empty
        assert result2.total == 0


class TestPushCardFilter:
    """F-017: card_filter resolves once and correctly filters modified/added/deleted."""

    def _setup_cache(self, tmp_path: Path) -> tuple[Path, TracheConfig]:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)
        return cache_dir, config

    def test_filter_selects_only_target_card(self, tmp_path: Path) -> None:
        """Push with card_filter pushes only the matching card, skips others."""
        cache_dir, config = self._setup_cache(tmp_path)

        card_a = Card(
            id="card_a_00000000000000000a",
            board_id="board1",
            list_id="list1",
            title="A",
        )
        card_b = Card(
            id="card_b_00000000000000000b",
            board_id="board1",
            list_id="list1",
            title="B",
        )
        write_card(card_a, "clean", cache_dir)
        write_card(card_a, "working", cache_dir)
        write_card(card_b, "clean", cache_dir)
        write_card(card_b, "working", cache_dir)

        # Dirty both
        card_a.title = "A Modified"
        card_a.dirty = True
        write_card(card_a, "working", cache_dir)
        card_b.title = "B Modified"
        card_b.dirty = True
        write_card(card_b, "working", cache_dir)

        client = MagicMock()
        client.update_card.return_value = card_a
        client.get_card.return_value = card_a
        client.get_card_checklists.return_value = []

        changeset, result = push_changes(
            config, client, cache_dir, card_filter=card_a.uid6
        )

        # Only card A should have been pushed
        assert len(result.pushed) == 1
        assert result.pushed[0].uid6 == card_a.uid6

    def test_filter_invalid_uid6_raises(self, tmp_path: Path) -> None:
        """Push with unresolvable card_filter raises KeyError."""
        cache_dir, config = self._setup_cache(tmp_path)
        client = MagicMock()

        with pytest.raises(KeyError, match="Cannot resolve"):
            push_changes(config, client, cache_dir, card_filter="ZZZZZZ")
