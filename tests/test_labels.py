"""Tests for label diff detection and push support."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from trache.cache.db import write_card, write_labels_raw
from trache.cache.diff import compute_diff
from trache.cache.models import Card
from trache.config import TracheConfig, ensure_cache_structure
from trache.sync.push import _resolve_label_ids, push_changes


class TestLabelDiff:
    def test_label_add_detected(self, sample_card: Card, cache_dir: Path) -> None:
        write_card(sample_card, "clean", cache_dir)

        sample_card.labels = ["bug", "priority-high", "feature"]
        write_card(sample_card, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert len(changeset.modified) == 1
        assert "labels" in changeset.modified[0].field_changes

    def test_label_remove_detected(self, sample_card: Card, cache_dir: Path) -> None:
        write_card(sample_card, "clean", cache_dir)

        sample_card.labels = ["bug"]
        write_card(sample_card, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert len(changeset.modified) == 1
        assert "labels" in changeset.modified[0].field_changes

    def test_label_order_change_no_diff(self, sample_card: Card, cache_dir: Path) -> None:
        """F-007: labels in different order should NOT produce a diff."""
        write_card(sample_card, "clean", cache_dir)

        sample_card.labels = ["priority-high", "bug"]  # Same labels, different order
        write_card(sample_card, "working", cache_dir)

        changeset = compute_diff(cache_dir)
        assert changeset.is_empty


class TestLabelResolve:
    def test_resolve_by_name(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)

        labels_data = [
            {"id": "lbl1", "name": "bug", "color": "red"},
            {"id": "lbl2", "name": "feature", "color": "blue"},
        ]
        write_labels_raw(labels_data, "working", cache_dir)

        result = _resolve_label_ids(["bug", "feature"], cache_dir)
        assert result == ["lbl1", "lbl2"]

    def test_resolve_by_color_unique(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)

        labels_data = [
            {"id": "lbl1", "name": "", "color": "red"},
            {"id": "lbl2", "name": "feature", "color": "blue"},
        ]
        write_labels_raw(labels_data, "working", cache_dir)

        result = _resolve_label_ids(["red"], cache_dir)
        assert result == ["lbl1"]

    def test_resolve_ambiguous_color_fails(self, tmp_path: Path) -> None:
        import pytest

        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)

        labels_data = [
            {"id": "lbl1", "name": "", "color": "red"},
            {"id": "lbl2", "name": "", "color": "red"},
        ]
        write_labels_raw(labels_data, "working", cache_dir)

        with pytest.raises(ValueError, match="Ambiguous"):
            _resolve_label_ids(["red"], cache_dir)

    def test_resolve_unknown_label_fails(self, tmp_path: Path) -> None:
        import pytest

        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)

        labels_data = [{"id": "lbl1", "name": "bug", "color": "red"}]
        write_labels_raw(labels_data, "working", cache_dir)

        with pytest.raises(ValueError, match="Cannot resolve"):
            _resolve_label_ids(["nonexistent"], cache_dir)


class TestLabelPush:
    def test_label_push_sends_idLabels(self, tmp_path: Path, sample_card: Card) -> None:
        cache_dir = tmp_path / ".trache"
        ensure_cache_structure(cache_dir)
        config = TracheConfig(board_id="board1")
        config.save(cache_dir)

        # Write labels.json (both clean and working so labels aren't detected as new)
        labels_data = [
            {"id": "lbl1", "name": "bug", "color": "red"},
            {"id": "lbl2", "name": "feature", "color": "blue"},
        ]
        write_labels_raw(labels_data, "clean", cache_dir)
        write_labels_raw(labels_data, "working", cache_dir)

        # Clean has one label, working has two
        write_card(sample_card, "clean", cache_dir)
        sample_card.labels = ["bug", "feature"]
        write_card(sample_card, "working", cache_dir)

        client = MagicMock()
        client.update_card.return_value = sample_card
        client.get_card.return_value = sample_card
        client.get_card_checklists.return_value = []

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        call_args = client.update_card.call_args
        fields = call_args[0][1]
        assert "idLabels" in fields
        assert "lbl1" in fields["idLabels"]
        assert "lbl2" in fields["idLabels"]
