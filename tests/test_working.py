"""Tests for working copy mutations."""

from __future__ import annotations

from pathlib import Path

import pytest

from trache.cache.diff import compute_diff
from trache.cache.db import read_card, resolve_card_id, write_card, write_checklists_raw
from trache.cache.models import Card, TrelloList

from conftest import seed_board
from trache.cache.working import (
    add_checklist_item,
    archive_card,
    check_checklist_item,
    create_card,
    edit_description,
    edit_title,
    move_card,
    remove_checklist_item,
    uncheck_checklist_item,
)


class TestEditTitle:
    def test_edit_title_updates_content_modified_at(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        write_card(sample_card, "clean", cache_dir)
        write_card(sample_card, "working", cache_dir)
        seed_board([sample_card], sample_lists, cache_dir)

        old_modified = sample_card.content_modified_at
        card = edit_title(sample_card.uid6, "New Title", cache_dir)

        assert card.title == "New Title"
        assert card.content_modified_at != old_modified
        assert card.dirty is True

        # Verify dirty state detected
        changeset = compute_diff(cache_dir)
        assert not changeset.is_empty
        assert len(changeset.modified) == 1
        assert "title" in changeset.modified[0].field_changes


class TestEditDescription:
    def test_edit_desc_persists(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        write_card(sample_card, "clean", cache_dir)
        write_card(sample_card, "working", cache_dir)
        seed_board([sample_card], sample_lists, cache_dir)

        card = edit_description(sample_card.uid6, "Updated description", cache_dir)
        assert card.description == "Updated description"

        # Re-read from db to verify persistence
        reloaded = read_card(sample_card.id, "working", cache_dir)
        assert reloaded.description == "Updated description"


class TestMoveCard:
    def test_move_card_changes_list_id(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        write_card(sample_card, "clean", cache_dir)
        write_card(sample_card, "working", cache_dir)
        seed_board([sample_card], sample_lists, cache_dir)

        new_list = sample_lists[1]  # "In Progress"
        card = move_card(sample_card.uid6, new_list.name, cache_dir)
        assert card.list_id == new_list.id
        assert card.dirty is True


class TestCreateCard:
    def test_create_card_exists_in_working_not_clean(
        self, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        seed_board([], sample_lists, cache_dir)

        card = create_card("To Do", "New Card", cache_dir, "board1", "Test desc")

        assert card.id.startswith("new_")
        assert card.title == "New Card"
        assert card.dirty is True

        # Card exists in working
        working_card = read_card(card.id, "working", cache_dir)
        assert working_card.title == "New Card"

        # Card does NOT exist in clean
        with pytest.raises(FileNotFoundError):
            read_card(card.id, "clean", cache_dir)

    def test_create_card_then_resolve(
        self, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        """F-003: temp card should be immediately resolvable by UID6."""
        seed_board([], sample_lists, cache_dir)

        card = create_card("To Do", "Resolvable Card", cache_dir, "board1")

        # Resolve by temp ID
        resolved = resolve_card_id(card.id, cache_dir)
        assert resolved == card.id

        # Resolve by UID6
        resolved = resolve_card_id(card.uid6, cache_dir)
        assert resolved == card.id


class TestArchiveCard:
    def test_archive_sets_closed(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        write_card(sample_card, "clean", cache_dir)
        write_card(sample_card, "working", cache_dir)
        seed_board([sample_card], sample_lists, cache_dir)

        card = archive_card(sample_card.uid6, cache_dir)
        assert card.closed is True
        assert card.dirty is True


def _seed_card_with_checklist(
    sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
) -> None:
    """Helper: write card + checklist to cache for checklist mutation tests."""
    write_card(sample_card, "clean", cache_dir)
    write_card(sample_card, "working", cache_dir)
    seed_board([sample_card], sample_lists, cache_dir)
    cl_data = [{
        "id": "cl001", "name": "MVP", "card_id": sample_card.id, "pos": 1,
        "items": [
            {"id": "ci001", "name": "Item 1", "state": "incomplete", "pos": 1},
            {"id": "ci002", "name": "Item 2", "state": "complete", "pos": 2},
        ],
    }]
    write_checklists_raw(sample_card.id, cl_data, "working", cache_dir)


class TestCheckChecklistItem:
    def test_check_marks_complete(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        _seed_card_with_checklist(sample_card, sample_lists, cache_dir)
        result = check_checklist_item(sample_card.uid6, "ci001", cache_dir)
        assert result["ok"] is True
        assert result["state"] == "complete"
        assert result["changed"] is True

    def test_check_idempotent(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        _seed_card_with_checklist(sample_card, sample_lists, cache_dir)
        # ci002 is already complete
        result = check_checklist_item(sample_card.uid6, "ci002", cache_dir)
        assert result["ok"] is True
        assert result["changed"] is False

    def test_check_not_found(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        _seed_card_with_checklist(sample_card, sample_lists, cache_dir)
        with pytest.raises(KeyError, match="not found"):
            check_checklist_item(sample_card.uid6, "nonexistent", cache_dir)


class TestUncheckChecklistItem:
    def test_uncheck_marks_incomplete(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        _seed_card_with_checklist(sample_card, sample_lists, cache_dir)
        result = uncheck_checklist_item(sample_card.uid6, "ci002", cache_dir)
        assert result["ok"] is True
        assert result["state"] == "incomplete"
        assert result["changed"] is True

    def test_uncheck_idempotent(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        _seed_card_with_checklist(sample_card, sample_lists, cache_dir)
        result = uncheck_checklist_item(sample_card.uid6, "ci001", cache_dir)
        assert result["ok"] is True
        assert result["changed"] is False


class TestAddChecklistItem:
    def test_add_item(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        _seed_card_with_checklist(sample_card, sample_lists, cache_dir)
        result = add_checklist_item(sample_card.uid6, "MVP", "New task", cache_dir)
        assert result["ok"] is True
        assert result["text"] == "New task"
        assert result["item_id"].startswith("temp_")

    def test_add_item_checklist_not_found(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        _seed_card_with_checklist(sample_card, sample_lists, cache_dir)
        with pytest.raises(KeyError, match="not found"):
            add_checklist_item(sample_card.uid6, "Nonexistent", "text", cache_dir)


class TestRemoveChecklistItem:
    def test_remove_item(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        _seed_card_with_checklist(sample_card, sample_lists, cache_dir)
        result = remove_checklist_item(sample_card.uid6, "ci001", cache_dir)
        assert result["ok"] is True
        assert result["item_id"] == "ci001"

    def test_remove_item_not_found(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        _seed_card_with_checklist(sample_card, sample_lists, cache_dir)
        with pytest.raises(KeyError, match="not found"):
            remove_checklist_item(sample_card.uid6, "nonexistent", cache_dir)
