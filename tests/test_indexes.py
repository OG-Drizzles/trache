"""Tests for index building and querying."""

from __future__ import annotations

from pathlib import Path

from trache.cache.index import (
    add_card_to_index,
    build_card_indexes,
    build_index,
    build_list_index,
    load_index,
    remove_card_from_index,
    resolve_card_id,
    resolve_list_id,
)
from trache.cache.models import Card, TrelloList


class TestUnifiedIndex:
    def test_build_index_creates_unified_file(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        index_dir = cache_dir / "indexes"
        build_index([sample_card], sample_lists, index_dir)

        assert (index_dir / "index.json").exists()
        # Old files should not exist
        assert not (index_dir / "cards_by_id.json").exists()
        assert not (index_dir / "cards_by_uid6.json").exists()
        assert not (index_dir / "lists_by_id.json").exists()

    def test_load_index_sections(
        self, sample_card: Card, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        index_dir = cache_dir / "indexes"
        build_index([sample_card], sample_lists, index_dir)

        by_id = load_index(index_dir, "cards_by_id")
        assert sample_card.id in by_id
        assert by_id[sample_card.id]["title"] == "Test Card"

        by_uid6 = load_index(index_dir, "cards_by_uid6")
        assert "FEDCBA" in by_uid6

        by_list = load_index(index_dir, "cards_by_list")
        assert sample_card.list_id in by_list

        lists = load_index(index_dir, "lists_by_id")
        assert len(lists) == 3
        assert lists["234567890abcdef123456789"]["name"] == "To Do"


class TestCardIndexes:
    def test_build_and_load(self, sample_card: Card, cache_dir: Path) -> None:
        index_dir = cache_dir / "indexes"
        build_card_indexes([sample_card], index_dir)

        by_id = load_index(index_dir, "cards_by_id")
        assert sample_card.id in by_id
        assert by_id[sample_card.id]["title"] == "Test Card"
        assert by_id[sample_card.id]["uid6"] == "FEDCBA"

        by_uid6 = load_index(index_dir, "cards_by_uid6")
        assert "FEDCBA" in by_uid6
        assert by_uid6["FEDCBA"] == sample_card.id

        by_list = load_index(index_dir, "cards_by_list")
        assert sample_card.list_id in by_list
        assert sample_card.id in by_list[sample_card.list_id]

    def test_resolve_card_id_by_full_id(self, sample_card: Card, cache_dir: Path) -> None:
        index_dir = cache_dir / "indexes"
        build_card_indexes([sample_card], index_dir)

        resolved = resolve_card_id(sample_card.id, index_dir)
        assert resolved == sample_card.id

    def test_resolve_card_id_by_uid6(self, sample_card: Card, cache_dir: Path) -> None:
        index_dir = cache_dir / "indexes"
        build_card_indexes([sample_card], index_dir)

        resolved = resolve_card_id("FEDCBA", index_dir)
        assert resolved == sample_card.id

    def test_resolve_card_id_case_insensitive(self, sample_card: Card, cache_dir: Path) -> None:
        index_dir = cache_dir / "indexes"
        build_card_indexes([sample_card], index_dir)

        resolved = resolve_card_id("fedcba", index_dir)
        assert resolved == sample_card.id

    def test_resolve_card_id_not_found(self, cache_dir: Path) -> None:
        import pytest

        index_dir = cache_dir / "indexes"
        build_card_indexes([], index_dir)

        with pytest.raises(KeyError):
            resolve_card_id("NONEXISTENT", index_dir)


class TestIncrementalIndex:
    def test_add_card_to_index(self, sample_card: Card, cache_dir: Path) -> None:
        index_dir = cache_dir / "indexes"
        build_card_indexes([], index_dir)

        add_card_to_index(sample_card, index_dir)

        by_uid6 = load_index(index_dir, "cards_by_uid6")
        assert sample_card.uid6 in by_uid6
        assert by_uid6[sample_card.uid6] == sample_card.id

    def test_add_card_removes_from_old_list(self, sample_card: Card, cache_dir: Path) -> None:
        """Moving a card between lists should remove it from the old list."""
        index_dir = cache_dir / "indexes"
        build_card_indexes([sample_card], index_dir)

        old_list_id = sample_card.list_id
        new_list_id = "345678901bcdef1234567890"

        # Move card to a different list
        moved_card = Card(
            id=sample_card.id,
            board_id=sample_card.board_id,
            list_id=new_list_id,
            title=sample_card.title,
        )
        add_card_to_index(moved_card, index_dir)

        by_list = load_index(index_dir, "cards_by_list")
        # Card should NOT be in old list
        assert sample_card.id not in by_list.get(old_list_id, [])
        # Card should be in new list
        assert sample_card.id in by_list[new_list_id]

    def test_remove_card_from_index(self, sample_card: Card, cache_dir: Path) -> None:
        index_dir = cache_dir / "indexes"
        build_card_indexes([sample_card], index_dir)

        remove_card_from_index(sample_card.id, index_dir)

        by_uid6 = load_index(index_dir, "cards_by_uid6")
        assert sample_card.uid6 not in by_uid6

        by_id = load_index(index_dir, "cards_by_id")
        assert sample_card.id not in by_id


class TestListIndex:
    def test_build_and_resolve(self, sample_lists: list[TrelloList], cache_dir: Path) -> None:
        index_dir = cache_dir / "indexes"
        build_list_index(sample_lists, index_dir)

        lists_by_id = load_index(index_dir, "lists_by_id")
        assert len(lists_by_id) == 3
        assert lists_by_id["234567890abcdef123456789"]["name"] == "To Do"

    def test_resolve_list_by_name(self, sample_lists: list[TrelloList], cache_dir: Path) -> None:
        index_dir = cache_dir / "indexes"
        build_list_index(sample_lists, index_dir)

        resolved = resolve_list_id("To Do", index_dir)
        assert resolved == "234567890abcdef123456789"

    def test_resolve_list_case_insensitive(
        self, sample_lists: list[TrelloList], cache_dir: Path
    ) -> None:
        index_dir = cache_dir / "indexes"
        build_list_index(sample_lists, index_dir)

        resolved = resolve_list_id("to do", index_dir)
        assert resolved == "234567890abcdef123456789"

    def test_resolve_list_not_found(self, sample_lists: list[TrelloList], cache_dir: Path) -> None:
        import pytest

        index_dir = cache_dir / "indexes"
        build_list_index(sample_lists, index_dir)

        with pytest.raises(KeyError):
            resolve_list_id("Nonexistent", index_dir)
