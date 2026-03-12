"""Tests for cache store — card serialization/deserialization."""

from __future__ import annotations

from trache.cache.models import Card
from trache.cache.store import (
    card_to_markdown,
    list_card_files,
    markdown_to_card,
    read_card_file,
    write_card_file,
)


class TestCardSerialization:
    def test_roundtrip(self, sample_card: Card) -> None:
        """Card → markdown → Card preserves key fields."""
        md = card_to_markdown(sample_card)
        restored = markdown_to_card(md)

        assert restored.id == sample_card.id
        assert restored.uid6 == sample_card.uid6
        assert restored.title == sample_card.title
        assert restored.description == sample_card.description
        assert restored.board_id == sample_card.board_id
        assert restored.list_id == sample_card.list_id
        assert restored.labels == sample_card.labels
        assert restored.closed == sample_card.closed

    def test_frontmatter_present(self, sample_card: Card) -> None:
        md = card_to_markdown(sample_card)
        assert md.startswith("---\n")
        assert "card_id: 67abc123def4567890fedcba" in md
        assert "uid6: FEDCBA" in md

    def test_identity_block_present(self, sample_card: Card) -> None:
        md = card_to_markdown(sample_card)
        assert "[TRACHE CARD IDENTITY]" in md
        assert "**Card Name:** Test Card" in md
        assert "**Unique ID:** FEDCBA" in md

    def test_description_section(self, sample_card: Card) -> None:
        md = card_to_markdown(sample_card)
        assert "# Description" in md
        assert "This is a test description." in md

    def test_checklist_summary(self, sample_card: Card) -> None:
        md = card_to_markdown(sample_card)
        assert "# Checklist Summary" in md
        assert "MVP: 2/3 complete" in md

    def test_empty_description(self, sample_card: Card) -> None:
        sample_card.description = ""
        md = card_to_markdown(sample_card)
        restored = markdown_to_card(md)
        assert restored.description == ""


class TestFileOperations:
    def test_write_and_read(self, sample_card: Card, cache_dir) -> None:
        cards_dir = cache_dir / "working" / "cards"
        path = write_card_file(sample_card, cards_dir)

        assert path.exists()
        assert path.name == f"{sample_card.id}.md"

        restored = read_card_file(path)
        assert restored.id == sample_card.id
        assert restored.title == sample_card.title

    def test_list_card_files(self, sample_card: Card, cache_dir) -> None:
        cards_dir = cache_dir / "working" / "cards"
        write_card_file(sample_card, cards_dir)

        files = list_card_files(cards_dir)
        assert len(files) == 1
        assert files[0].stem == sample_card.id

    def test_list_card_files_empty(self, cache_dir) -> None:
        files = list_card_files(cache_dir / "working" / "cards")
        assert files == []
