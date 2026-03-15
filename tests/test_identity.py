"""Tests for identity module — identifier block generation and stripping."""

from __future__ import annotations

from datetime import datetime, timezone

from trache.identity import generate_block, inject_block, strip_block


class TestGenerateBlock:
    def test_basic_block(self) -> None:
        block = generate_block(
            title="Test Card",
            created_at=datetime(2026, 3, 13, 1, 22, tzinfo=timezone.utc),
            content_modified_at=datetime(2026, 3, 13, 4, 10, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 13, 5, 30, tzinfo=timezone.utc),
            uid6="FEDCBA",
        )
        assert "# **Card Identifier**" in block
        assert "**Card Name:** Test Card" in block
        assert "**Created Date:** 2026-03-13 01:22 UTC" in block
        assert "**Unique ID:** FEDCBA" in block

    def test_none_dates(self) -> None:
        block = generate_block(
            title="No Dates",
            created_at=None,
            content_modified_at=None,
            last_activity=None,
            uid6="ABC123",
        )
        assert "None" in block


class TestStripBlock:
    def test_strip_from_description(self) -> None:
        desc = (
            "---\n"
            "# **Card Identifier**\n"
            "- **Card Name:** Test\n"
            "- **Created Date:** 2026-03-13 01:22 UTC\n"
            "- **Modified Date:** 2026-03-13 04:10 UTC\n"
            "- **Last Activity:** 2026-03-13 05:30 UTC\n"
            "- **Unique ID:** FEDCBA\n"
            "---\n"
            "\n"
            "Actual description here."
        )
        result = strip_block(desc)
        assert result == "Actual description here."
        assert "Card Identifier" not in result

    def test_strip_no_block(self) -> None:
        desc = "Just a regular description."
        result = strip_block(desc)
        assert result == desc

    def test_strip_empty(self) -> None:
        assert strip_block("") == ""


class TestInjectBlock:
    def test_inject(self) -> None:
        block = generate_block(
            title="Test",
            created_at=None,
            content_modified_at=None,
            last_activity=None,
            uid6="ABC123",
        )
        result = inject_block("My description", block)
        assert result.startswith("---\n# **Card Identifier**")
        assert "My description" in result
        assert result.index("Card Identifier") < result.index("My description")

    def test_strip_double_separator_regression(self) -> None:
        """F-013: Double --- separators from prior bug should still be stripped cleanly."""
        desc = (
            "---\n"
            "# **Card Identifier**\n"
            "- **Card Name:** Test\n"
            "- **Created Date:** 2026-03-13 01:22 UTC\n"
            "- **Modified Date:** 2026-03-13 04:10 UTC\n"
            "- **Last Activity:** 2026-03-13 05:30 UTC\n"
            "- **Unique ID:** FEDCBA\n"
            "---\n"
            "\n"
            "Body after single separator."
        )
        result = strip_block(desc)
        assert result == "Body after single separator."

    def test_inject_replaces_existing(self) -> None:
        existing = (
            "---\n"
            "# **Card Identifier**\n"
            "- **Card Name:** Old\n"
            "- **Created Date:** old\n"
            "- **Modified Date:** old\n"
            "- **Last Activity:** old\n"
            "- **Unique ID:** OLD123\n"
            "---\n"
            "\n"
            "Body text"
        )
        block = generate_block(
            title="New",
            created_at=None,
            content_modified_at=None,
            last_activity=None,
            uid6="NEW456",
        )
        result = inject_block(existing, block)
        assert "NEW456" in result
        assert "OLD123" not in result
        assert "Body text" in result
