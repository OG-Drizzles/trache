"""Tests for checklist clean/working split — dirty detection and push."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from conftest import seed_board

from trache.cache.db import read_checklists_raw, write_card, write_checklists_raw
from trache.cache.diff import compute_diff
from trache.cache.models import Card, ChecklistItem, TrelloList
from trache.config import TracheConfig, ensure_cache_structure


def _setup_card_with_checklists(cache_dir: Path) -> tuple[Card, list[dict]]:
    """Setup a card with checklists in both clean and working."""
    card = Card(
        id="67abc123def4567890fedcba",
        board_id="board1",
        list_id="list1",
        title="Test Card",
        description="Test",
    )
    lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
    write_card(card, "clean", cache_dir)
    write_card(card, "working", cache_dir)
    seed_board([card], lists, cache_dir)

    cl_data = [
        {
            "id": "cl001",
            "name": "MVP",
            "card_id": "67abc123def4567890fedcba",
            "pos": 1,
            "items": [
                {"id": "ci001", "name": "Item 1", "state": "incomplete", "pos": 1},
                {"id": "ci002", "name": "Item 2", "state": "incomplete", "pos": 2},
                {"id": "ci003", "name": "Item 3", "state": "complete", "pos": 3},
            ],
        }
    ]
    write_checklists_raw("67abc123def4567890fedcba", cl_data, "clean", cache_dir)
    write_checklists_raw("67abc123def4567890fedcba", cl_data, "working", cache_dir)

    return card, cl_data


class TestChecklistDirtyDetection:
    def test_check_creates_dirty_state(self, cache_dir: Path) -> None:
        card, cl_data = _setup_card_with_checklists(cache_dir)

        # Modify working: mark item 1 as complete
        working_cls = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
        working_cls[0]["items"][0]["state"] = "complete"
        write_checklists_raw("67abc123def4567890fedcba", working_cls, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert not changeset.is_empty
        assert len(changeset.modified) == 1
        assert len(changeset.modified[0].checklist_changes) == 1
        cl_change = changeset.modified[0].checklist_changes[0]
        assert cl_change.change_type == "state_change"
        assert cl_change.old_value == "incomplete"
        assert cl_change.new_value == "complete"

    def test_uncheck_creates_dirty_state(self, cache_dir: Path) -> None:
        card, cl_data = _setup_card_with_checklists(cache_dir)

        # Mark item 3 (which is complete) as incomplete
        working_cls = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
        working_cls[0]["items"][2]["state"] = "incomplete"
        write_checklists_raw("67abc123def4567890fedcba", working_cls, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert not changeset.is_empty
        assert any(
            c.change_type == "state_change" for c in changeset.modified[0].checklist_changes
        )

    def test_add_item_creates_dirty_state(self, cache_dir: Path) -> None:
        card, cl_data = _setup_card_with_checklists(cache_dir)

        working_cls = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
        working_cls[0]["items"].append(
            {"id": "temp_newitem", "name": "New Item", "state": "incomplete", "pos": 4}
        )
        write_checklists_raw("67abc123def4567890fedcba", working_cls, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert not changeset.is_empty
        assert any(
            c.change_type == "new_item" for c in changeset.modified[0].checklist_changes
        )

    def test_remove_item_creates_dirty_state(self, cache_dir: Path) -> None:
        card, cl_data = _setup_card_with_checklists(cache_dir)

        working_cls = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
        working_cls[0]["items"].pop(0)  # Remove first item
        write_checklists_raw("67abc123def4567890fedcba", working_cls, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert not changeset.is_empty
        assert any(
            c.change_type == "removed_item" for c in changeset.modified[0].checklist_changes
        )

    def test_rename_item_creates_dirty_state(self, cache_dir: Path) -> None:
        card, cl_data = _setup_card_with_checklists(cache_dir)

        working_cls = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
        working_cls[0]["items"][0]["name"] = "Renamed Item"
        write_checklists_raw("67abc123def4567890fedcba", working_cls, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert not changeset.is_empty
        assert any(
            c.change_type == "text_change" for c in changeset.modified[0].checklist_changes
        )


class TestChecklistPerCardFormat:
    def test_per_card_file_contains_all_checklists(self, cache_dir: Path) -> None:
        """Verify per-card DB entry contains all checklists for that card."""
        card = Card(id="67abc123def4567890fedcba", board_id="board1", list_id="list1", title="Card")
        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
        write_card(card, "clean", cache_dir)
        write_card(card, "working", cache_dir)
        seed_board([card], lists, cache_dir)

        cl_data = [
            {
                "id": "cl001", "name": "MVP",
                "card_id": "67abc123def4567890fedcba", "pos": 1, "items": [],
            },
            {
                "id": "cl002", "name": "Polish",
                "card_id": "67abc123def4567890fedcba", "pos": 2, "items": [],
            },
        ]
        write_checklists_raw("67abc123def4567890fedcba", cl_data, "clean", cache_dir)
        write_checklists_raw("67abc123def4567890fedcba", cl_data, "working", cache_dir)

        loaded = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
        assert len(loaded) == 2
        assert loaded[0]["name"] == "MVP"
        assert loaded[1]["name"] == "Polish"


class TestChecklistPush:
    def test_state_change_push(self, tmp_path: Path) -> None:
        """Toggle item state → push → verify API call."""
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)

        card = Card(id="67abc123def4567890fedcba", board_id="board1", list_id="list1", title="Card")
        write_card(card, "clean", cache_dir)
        write_card(card, "working", cache_dir)

        cl_data = [
            {
                "id": "cl001", "name": "MVP", "card_id": "67abc123def4567890fedcba", "pos": 1,
                "items": [{"id": "ci001", "name": "Item 1", "state": "incomplete", "pos": 1}],
            }
        ]
        write_checklists_raw("67abc123def4567890fedcba", cl_data, "clean", cache_dir)

        # Modify working checklist
        working_cl = [
            {
                "id": "cl001", "name": "MVP", "card_id": "67abc123def4567890fedcba", "pos": 1,
                "items": [{"id": "ci001", "name": "Item 1", "state": "complete", "pos": 1}],
            }
        ]
        write_checklists_raw("67abc123def4567890fedcba", working_cl, "working", cache_dir)

        client = MagicMock()
        client.update_card.return_value = card
        client.get_card.return_value = card
        client.get_card_checklists.return_value = []

        from trache.sync.push import push_changes
        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        client.update_checklist_item.assert_called_once_with(
            "67abc123def4567890fedcba", "ci001", "complete"
        )

    def test_add_item_push(self, tmp_path: Path) -> None:
        """Add item locally → push → verify add API call."""
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)

        card = Card(id="67abc123def4567890fedcba", board_id="board1", list_id="list1", title="Card")
        write_card(card, "clean", cache_dir)
        write_card(card, "working", cache_dir)

        cl_data = [
            {
                "id": "cl001", "name": "MVP", "card_id": "67abc123def4567890fedcba", "pos": 1,
                "items": [],
            }
        ]
        write_checklists_raw("67abc123def4567890fedcba", cl_data, "clean", cache_dir)

        working_cl = [
            {
                "id": "cl001", "name": "MVP", "card_id": "67abc123def4567890fedcba", "pos": 1,
                "items": [{"id": "temp_new", "name": "New Item", "state": "incomplete", "pos": 1}],
            }
        ]
        write_checklists_raw("67abc123def4567890fedcba", working_cl, "working", cache_dir)

        client = MagicMock()
        client.update_card.return_value = card
        client.get_card.return_value = card
        client.get_card_checklists.return_value = []
        client.add_checklist_item.return_value = ChecklistItem(id="real_id", name="New Item")

        from trache.sync.push import push_changes
        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        client.add_checklist_item.assert_called_once_with("cl001", "New Item")

    def test_remove_item_push(self, tmp_path: Path) -> None:
        """Remove item locally → push → verify DELETE API call."""
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)

        card = Card(id="67abc123def4567890fedcba", board_id="board1", list_id="list1", title="Card")
        write_card(card, "clean", cache_dir)
        write_card(card, "working", cache_dir)

        cl_data = [
            {
                "id": "cl001", "name": "MVP", "card_id": "67abc123def4567890fedcba", "pos": 1,
                "items": [{"id": "ci001", "name": "Item 1", "state": "incomplete", "pos": 1}],
            }
        ]
        write_checklists_raw("67abc123def4567890fedcba", cl_data, "clean", cache_dir)

        # Remove the item in working
        working_cl = [
            {
                "id": "cl001", "name": "MVP", "card_id": "67abc123def4567890fedcba", "pos": 1,
                "items": [],
            }
        ]
        write_checklists_raw("67abc123def4567890fedcba", working_cl, "working", cache_dir)

        client = MagicMock()
        client.update_card.return_value = card
        client.get_card.return_value = card
        client.get_card_checklists.return_value = []

        from trache.sync.push import push_changes
        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        client.delete_checklist_item.assert_called_once_with("cl001", "ci001")
