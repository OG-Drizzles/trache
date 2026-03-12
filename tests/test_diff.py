"""Tests for diff engine."""

from __future__ import annotations

from pathlib import Path

from trache.cache.diff import compute_diff, format_diff
from trache.cache.models import Card
from trache.cache.store import write_card_file


class TestComputeDiff:
    def test_no_changes(self, sample_card: Card, cache_dir: Path) -> None:
        write_card_file(sample_card, cache_dir / "clean" / "cards")
        write_card_file(sample_card, cache_dir / "working" / "cards")

        changeset = compute_diff(cache_dir)
        assert changeset.is_empty
        assert changeset.total_changes == 0

    def test_title_change(self, sample_card: Card, cache_dir: Path) -> None:
        write_card_file(sample_card, cache_dir / "clean" / "cards")

        sample_card.title = "Modified Title"
        write_card_file(sample_card, cache_dir / "working" / "cards")

        changeset = compute_diff(cache_dir)
        assert len(changeset.modified) == 1
        assert "title" in changeset.modified[0].field_changes

    def test_added_card(self, sample_card: Card, cache_dir: Path) -> None:
        # Only in working, not in clean
        write_card_file(sample_card, cache_dir / "working" / "cards")

        changeset = compute_diff(cache_dir)
        assert len(changeset.added) == 1
        assert changeset.added[0].card_id == sample_card.id

    def test_deleted_card(self, sample_card: Card, cache_dir: Path) -> None:
        # Only in clean, not in working
        write_card_file(sample_card, cache_dir / "clean" / "cards")

        changeset = compute_diff(cache_dir)
        assert len(changeset.deleted) == 1
        assert changeset.deleted[0].card_id == sample_card.id

    def test_description_change(self, sample_card: Card, cache_dir: Path) -> None:
        write_card_file(sample_card, cache_dir / "clean" / "cards")

        sample_card.description = "Updated description"
        write_card_file(sample_card, cache_dir / "working" / "cards")

        changeset = compute_diff(cache_dir)
        assert len(changeset.modified) == 1
        assert "description" in changeset.modified[0].field_changes

    def test_list_move(self, sample_card: Card, cache_dir: Path) -> None:
        write_card_file(sample_card, cache_dir / "clean" / "cards")

        sample_card.list_id = "different_list_id_here_000"
        write_card_file(sample_card, cache_dir / "working" / "cards")

        changeset = compute_diff(cache_dir)
        assert len(changeset.modified) == 1
        assert "list_id" in changeset.modified[0].field_changes


class TestFormatDiff:
    def test_empty(self) -> None:
        from trache.cache.diff import Changeset

        assert format_diff(Changeset()) == "No changes."

    def test_formatted_output(self, sample_card: Card, cache_dir: Path) -> None:
        write_card_file(sample_card, cache_dir / "working" / "cards")

        changeset = compute_diff(cache_dir)
        output = format_diff(changeset)
        assert "Added (1):" in output
        assert "Test Card" in output
