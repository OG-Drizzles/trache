"""Tests for diff engine."""

from __future__ import annotations

from pathlib import Path

from trache.cache import db
from trache.cache.diff import compute_diff, format_diff
from trache.cache.models import Card


class TestComputeDiff:
    def test_no_changes(self, sample_card: Card, cache_dir: Path) -> None:
        db.write_card(sample_card, "clean", cache_dir)
        db.write_card(sample_card, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert changeset.is_empty
        assert changeset.total_changes == 0

    def test_title_change(self, sample_card: Card, cache_dir: Path) -> None:
        db.write_card(sample_card, "clean", cache_dir)

        sample_card.title = "Modified Title"
        db.write_card(sample_card, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert len(changeset.modified) == 1
        assert "title" in changeset.modified[0].field_changes

    def test_added_card(self, sample_card: Card, cache_dir: Path) -> None:
        # Only in working, not in clean
        db.write_card(sample_card, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert len(changeset.added) == 1
        assert changeset.added[0].card_id == sample_card.id

    def test_deleted_card(self, sample_card: Card, cache_dir: Path) -> None:
        # Only in clean, not in working
        db.write_card(sample_card, "clean", cache_dir)

        changeset = compute_diff(cache_dir)
        assert len(changeset.deleted) == 1
        assert changeset.deleted[0].card_id == sample_card.id

    def test_description_change(self, sample_card: Card, cache_dir: Path) -> None:
        db.write_card(sample_card, "clean", cache_dir)

        sample_card.description = "Updated description"
        db.write_card(sample_card, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert len(changeset.modified) == 1
        assert "description" in changeset.modified[0].field_changes

    def test_list_move(self, sample_card: Card, cache_dir: Path) -> None:
        db.write_card(sample_card, "clean", cache_dir)

        sample_card.list_id = "different_list_id_here_000"
        db.write_card(sample_card, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert len(changeset.modified) == 1
        assert "list_id" in changeset.modified[0].field_changes


class TestComputeDiffSingleConnection:
    """O-004: compute_diff must use exactly one DB connection."""

    def test_single_connection(self, sample_card: Card, cache_dir: Path) -> None:
        from contextlib import contextmanager
        from unittest.mock import patch

        from trache.cache import db as db_module
        from trache.cache import diff as diff_module

        connection_count = 0
        original = db_module._connect

        @contextmanager
        def counting_connect(cd):
            nonlocal connection_count
            connection_count += 1
            with original(cd) as conn:
                yield conn

        db_module.write_card(sample_card, "clean", cache_dir)
        db_module.write_card(sample_card, "working", cache_dir)

        with patch.object(diff_module, "connect", counting_connect):
            compute_diff(cache_dir)

        assert connection_count == 1


class TestFormatDiff:
    def test_empty(self) -> None:
        from trache.cache.diff import Changeset

        assert format_diff(Changeset()) == "No changes."

    def test_formatted_output(self, sample_card: Card, cache_dir: Path) -> None:
        db.write_card(sample_card, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        output = format_diff(changeset)
        assert "Added (1):" in output
        assert "Test Card" in output
