"""Tests for push logic (mocked API)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from trache.cache.models import Card
from trache.cache.store import write_card_file
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

        write_card_file(sample_card, cache_dir / "clean" / "cards")
        sample_card.title = "Modified"
        write_card_file(sample_card, cache_dir / "working" / "cards")

        client = MagicMock()
        changeset, result = push_changes(config, client, cache_dir, dry_run=True)

        assert not changeset.is_empty
        assert len(result.pushed) == 1
        # Dry run should not call any API methods
        client.update_card.assert_not_called()

    def test_push_modified_card(self, tmp_path: Path, sample_card: Card) -> None:
        cache_dir, config = self._setup_cache(tmp_path)

        write_card_file(sample_card, cache_dir / "clean" / "cards")
        sample_card.title = "Modified Title"
        write_card_file(sample_card, cache_dir / "working" / "cards")

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

        sample_card.id = "new_temp_abc123def456"
        sample_card.uid6 = "EF4567"  # Reset uid6 manually for temp ID
        write_card_file(sample_card, cache_dir / "working" / "cards")

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
