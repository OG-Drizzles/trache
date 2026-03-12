"""Tests for index building and querying."""

from __future__ import annotations

from pathlib import Path

from trache.cache.index import (
    build_card_indexes,
    build_list_index,
    load_index,
    resolve_card_id,
    resolve_list_id,
)
from trache.cache.models import Card, TrelloList


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
