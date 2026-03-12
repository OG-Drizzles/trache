"""Tests for working copy mutations."""

from __future__ import annotations

from pathlib import Path

from trache.cache.diff import compute_diff
from trache.cache.index import build_index, resolve_card_id
from trache.cache.models import Card, TrelloList
from trache.cache.store import read_card_file, write_card_file
from trache.cache.working import (
    archive_card,
    create_card,
    edit_description,
    edit_title,
    move_card,
)


class TestEditTitle:
    def test_edit_title_updates_content_modified_at(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        write_card_file(sample_card, cache_dir / "clean" / "cards")
        write_card_file(sample_card, cache_dir / "working" / "cards")
        build_index([sample_card], sample_lists, cache_dir / "indexes")

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
        write_card_file(sample_card, cache_dir / "clean" / "cards")
        write_card_file(sample_card, cache_dir / "working" / "cards")
        build_index([sample_card], sample_lists, cache_dir / "indexes")

        card = edit_description(sample_card.uid6, "Updated description", cache_dir)
        assert card.description == "Updated description"

        # Re-read from disk to verify persistence
        reloaded = read_card_file(cache_dir / "working" / "cards" / f"{sample_card.id}.md")
        assert reloaded.description == "Updated description"


class TestMoveCard:
    def test_move_card_changes_list_id(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        write_card_file(sample_card, cache_dir / "clean" / "cards")
        write_card_file(sample_card, cache_dir / "working" / "cards")
        build_index([sample_card], sample_lists, cache_dir / "indexes")

        new_list = sample_lists[1]  # "In Progress"
        card = move_card(sample_card.uid6, new_list.name, cache_dir)
        assert card.list_id == new_list.id
        assert card.dirty is True


class TestCreateCard:
    def test_create_card_exists_in_working_not_clean(
        self, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        build_index([], sample_lists, cache_dir / "indexes")

        card = create_card("To Do", "New Card", cache_dir, "board1", "Test desc")

        assert card.id.startswith("new_")
        assert card.title == "New Card"
        assert card.dirty is True

        # File exists in working
        working_file = cache_dir / "working" / "cards" / f"{card.id}.md"
        assert working_file.exists()

        # File does NOT exist in clean
        clean_file = cache_dir / "clean" / "cards" / f"{card.id}.md"
        assert not clean_file.exists()

    def test_create_card_then_resolve(
        self, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        """F-003: temp card should be immediately resolvable by UID6."""
        build_index([], sample_lists, cache_dir / "indexes")

        card = create_card("To Do", "Resolvable Card", cache_dir, "board1")

        # Resolve by temp ID
        resolved = resolve_card_id(card.id, cache_dir / "indexes")
        assert resolved == card.id

        # Resolve by UID6
        resolved = resolve_card_id(card.uid6, cache_dir / "indexes")
        assert resolved == card.id


class TestArchiveCard:
    def test_archive_sets_closed(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        write_card_file(sample_card, cache_dir / "clean" / "cards")
        write_card_file(sample_card, cache_dir / "working" / "cards")
        build_index([sample_card], sample_lists, cache_dir / "indexes")

        card = archive_card(sample_card.uid6, cache_dir)
        assert card.closed is True
        assert card.dirty is True
