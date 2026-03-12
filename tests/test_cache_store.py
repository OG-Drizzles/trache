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


class TestDescriptionBoundaryHardening:
    """F-009: description parsing with HTML comment markers."""

    def test_description_with_checklist_heading(self, sample_card: Card) -> None:
        """Description containing '# Checklist Summary' should not be truncated."""
        sample_card.description = (
            "My description\n\n# Checklist Summary\n\nThis is part of the desc."
        )
        md = card_to_markdown(sample_card)
        restored = markdown_to_card(md)
        assert restored.description == sample_card.description

    def test_backward_compat_old_format_read(self) -> None:
        """Old heading-based format (no HTML comments) should still parse correctly."""
        old_format = (
            "---\n"
            "card_id: abc123\n"
            "uid6: BC1234\n"
            "board_id: board1\n"
            "list_id: list1\n"
            "title: Test\n"
            "created_at: null\n"
            "content_modified_at: null\n"
            "last_activity: null\n"
            "due: null\n"
            "labels: []\n"
            "members: []\n"
            "closed: false\n"
            "dirty: false\n"
            "---\n"
            "\n"
            "[TRACHE CARD IDENTITY]\n"
            "- **Card Name:** Test\n"
            "\n"
            "---\n"
            "\n"
            "# Description\n"
            "\n"
            "Old style description.\n"
            "\n"
            "# Checklist Summary\n"
            "\n"
            "- MVP: 1/3 complete\n"
        )
        card = markdown_to_card(old_format)
        assert card.description == "Old style description."


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
