"""Tests for content_modified_at semantic contract.

These tests lock down the distinction between content_modified_at (tracks content changes)
and last_activity (tracks any Trello activity including comments, member changes, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trache.cache.models import Card, TrelloList
from trache.cache.store import read_card_file, write_card_file
from trache.sync.pull import pull_full_board

from conftest import make_mock_client, setup_cache


class TestContentModifiedAtPreservation:
    def test_preserved_on_repull_no_content_change(self, tmp_path: Path) -> None:
        """Re-pull with no content changes → content_modified_at unchanged."""
        cache_dir, config = setup_cache(tmp_path)

        original_time = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Stable Card",
            description="Same description",
            content_modified_at=original_time,
            last_activity=original_time,
        )

        # First pull
        client = make_mock_client([card])
        pull_full_board(config, client, cache_dir, force=True)

        # Read the stored content_modified_at
        stored = read_card_file(cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md")
        first_pull_modified = stored.content_modified_at

        # Re-pull with same content but later last_activity (simulating a comment)
        card_v2 = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Stable Card",
            description="Same description",
            # API sets this to dateLastActivity
            content_modified_at=datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc),
        )
        client2 = make_mock_client([card_v2])
        pull_full_board(config, client2, cache_dir, force=True)

        stored2 = read_card_file(cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md")
        assert stored2.content_modified_at == first_pull_modified

    def test_updated_on_repull_content_change(self, tmp_path: Path) -> None:
        """Re-pull with content change → content_modified_at updates."""
        cache_dir, config = setup_cache(tmp_path)

        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card V1",
            description="Original",
            content_modified_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        )

        client = make_mock_client([card])
        pull_full_board(config, client, cache_dir, force=True)

        stored = read_card_file(cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md")
        first_pull_modified = stored.content_modified_at

        # Re-pull with changed title
        card_v2 = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card V2",
            description="Original",
            content_modified_at=datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc),
        )
        client2 = make_mock_client([card_v2])
        pull_full_board(config, client2, cache_dir, force=True)

        stored2 = read_card_file(cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md")
        assert stored2.content_modified_at != first_pull_modified

    def test_comment_only_preserves_content_modified_at(self, tmp_path: Path) -> None:
        """Remote comment-only change updates last_activity but NOT content_modified_at."""
        cache_dir, config = setup_cache(tmp_path)

        original_time = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Stable Card",
            description="Stable desc",
            content_modified_at=original_time,
            last_activity=original_time,
        )

        client = make_mock_client([card])
        pull_full_board(config, client, cache_dir, force=True)
        stored = read_card_file(cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md")
        first_modified = stored.content_modified_at

        # Simulate: same content, but dateLastActivity bumped (comment was added)
        later_time = datetime(2026, 3, 12, 15, 0, 0, tzinfo=timezone.utc)
        card_v2 = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Stable Card",
            description="Stable desc",
            content_modified_at=later_time,  # API always sets this to dateLastActivity
            last_activity=later_time,
        )
        client2 = make_mock_client([card_v2])
        pull_full_board(config, client2, cache_dir, force=True)

        stored2 = read_card_file(cache_dir / "clean" / "cards" / "67abc123def4567890fedcba.md")
        assert stored2.content_modified_at == first_modified
        assert stored2.last_activity == later_time

    def test_local_edit_updates_content_modified_at(self, tmp_path: Path) -> None:
        """Local title edit updates content_modified_at."""
        from trache.cache.index import build_index
        from trache.cache.working import edit_title

        cache_dir, config = setup_cache(tmp_path)
        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            content_modified_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        write_card_file(card, cache_dir / "clean" / "cards")
        write_card_file(card, cache_dir / "working" / "cards")
        build_index([card], lists, cache_dir / "indexes")

        original_modified = card.content_modified_at
        updated = edit_title(card.uid6, "New Title", cache_dir)
        assert updated.content_modified_at > original_modified

    def test_local_label_change_updates_content_modified_at(self, tmp_path: Path) -> None:
        """Label add/remove locally updates content_modified_at."""
        from trache.cache.index import build_index

        cache_dir, config = setup_cache(tmp_path)
        lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            labels=["bug"],
            content_modified_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        write_card_file(card, cache_dir / "clean" / "cards")
        write_card_file(card, cache_dir / "working" / "cards")
        build_index([card], lists, cache_dir / "indexes")

        # Manually edit label in working copy (simulating what a hypothetical edit_labels would do)
        from datetime import timezone as tz

        from trache.cache.working import read_working_card
        working = read_working_card(card.uid6, cache_dir)
        working.labels = ["bug", "feature"]
        working.content_modified_at = datetime.now(tz.utc)
        working.dirty = True
        write_card_file(working, cache_dir / "working" / "cards")

        assert working.content_modified_at > card.content_modified_at

    def test_list_move_updates_content_modified_at(self, tmp_path: Path) -> None:
        """Moving a card to a different list updates content_modified_at."""
        from trache.cache.index import build_index
        from trache.cache.working import move_card

        cache_dir, config = setup_cache(tmp_path)
        lists = [
            TrelloList(id="list1", name="To Do", board_id="board1", pos=1),
            TrelloList(id="list2", name="Done", board_id="board1", pos=2),
        ]
        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            content_modified_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        write_card_file(card, cache_dir / "clean" / "cards")
        write_card_file(card, cache_dir / "working" / "cards")
        build_index([card], lists, cache_dir / "indexes")

        original = card.content_modified_at
        moved = move_card(card.uid6, "Done", cache_dir)
        assert moved.content_modified_at > original
        assert moved.list_id == "list2"
