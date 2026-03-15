"""Tests for the SQLite persistence layer (cache/db.py)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trache.cache.db import (
    DB_FILENAME,
    MIGRATION_SENTINEL,
    _db_path,
    add_list,
    connect,
    delete_card,
    delete_stale_cards,
    init_db,
    list_cards,
    load_cards_index,
    read_card,
    read_checklists,
    read_labels,
    read_labels_raw,
    read_lists,
    resolve_card_id,
    resolve_list_id,
    resolve_list_name,
    write_card,
    write_card_pull,
    write_cards_batch,
    write_checklists,
    write_full_snapshot,
    write_labels,
    write_lists,
)
from trache.cache.models import (
    Card,
    Checklist,
    ChecklistItem,
    Label,
    TrelloList,
)


@pytest.fixture
def db_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with an initialised database."""
    d = tmp_path / "board"
    init_db(d)
    return d


def _make_card(
    card_id: str = "67abc123def4567890fedcba",
    title: str = "Test Card",
    **kwargs,
) -> Card:
    defaults = dict(
        id=card_id,
        board_id="abc123def456789012345678",
        list_id="234567890abcdef123456789",
        title=title,
        description="A test description.",
        created_at=datetime(2026, 3, 13, 1, 22, 33, tzinfo=timezone.utc),
        content_modified_at=datetime(2026, 3, 13, 4, 10, 11, tzinfo=timezone.utc),
        last_activity=datetime(2026, 3, 13, 5, 30, 0, tzinfo=timezone.utc),
        labels=["bug", "priority-high"],
    )
    defaults.update(kwargs)
    return Card(**defaults)


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------


class TestInitDb:
    def test_init_db_is_idempotent(self, tmp_path: Path) -> None:
        d = tmp_path / "board"
        init_db(d)
        assert (d / DB_FILENAME).exists()
        # Second call should not fail
        init_db(d)
        assert (d / DB_FILENAME).exists()

    def test_init_db_creates_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "deep" / "nested" / "board"
        init_db(d)
        assert d.exists()
        assert (d / DB_FILENAME).exists()


# ---------------------------------------------------------------------------
# Card CRUD
# ---------------------------------------------------------------------------


class TestCardCrud:
    def test_write_read_card_roundtrip(self, db_dir: Path) -> None:
        card = _make_card()
        write_card(card, "working", db_dir)
        loaded = read_card(card.id, "working", db_dir)

        assert loaded.id == card.id
        assert loaded.uid6 == card.uid6
        assert loaded.title == card.title
        assert loaded.description == card.description
        assert loaded.board_id == card.board_id
        assert loaded.list_id == card.list_id
        assert loaded.labels == card.labels
        assert loaded.created_at == card.created_at
        assert loaded.content_modified_at == card.content_modified_at
        assert loaded.last_activity == card.last_activity
        assert loaded.closed == card.closed
        assert loaded.dirty == card.dirty

    def test_clean_working_independent(self, db_dir: Path) -> None:
        card = _make_card()
        write_card(card, "clean", db_dir)

        # Modify and write to working
        card.title = "Modified Title"
        card.dirty = True
        write_card(card, "working", db_dir)

        clean = read_card(card.id, "clean", db_dir)
        working = read_card(card.id, "working", db_dir)

        assert clean.title == "Test Card"
        assert clean.dirty is False
        assert working.title == "Modified Title"
        assert working.dirty is True

    def test_read_card_not_found(self, db_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_card("nonexistent", "working", db_dir)

    def test_write_cards_batch(self, db_dir: Path) -> None:
        cards = [
            _make_card(card_id=f"card{i:022d}", title=f"Card {i}")
            for i in range(5)
        ]
        write_cards_batch(cards, "working", db_dir)
        loaded = list_cards("working", db_dir)
        assert len(loaded) == 5

    def test_delete_card(self, db_dir: Path) -> None:
        card = _make_card()
        write_card(card, "working", db_dir)
        delete_card(card.id, "working", db_dir)

        with pytest.raises(FileNotFoundError):
            read_card(card.id, "working", db_dir)

    def test_delete_stale_cards(self, db_dir: Path) -> None:
        cards = [
            _make_card(card_id=f"card{i:022d}", title=f"Card {i}")
            for i in range(5)
        ]
        write_cards_batch(cards, "working", db_dir)

        # Keep only cards 0 and 2
        keep = {f"card{i:022d}" for i in [0, 2]}
        delete_stale_cards(keep, "working", db_dir)

        remaining = list_cards("working", db_dir)
        assert len(remaining) == 2
        ids = {c.id for c in remaining}
        assert ids == keep


# ---------------------------------------------------------------------------
# Checklists
# ---------------------------------------------------------------------------


class TestChecklists:
    def test_write_checklists_replaces(self, db_dir: Path) -> None:
        card = _make_card()
        write_card(card, "working", db_dir)

        cl1 = Checklist(
            id="cl001",
            name="MVP",
            card_id=card.id,
            items=[
                ChecklistItem(id="ci001", name="Item 1", state="complete"),
                ChecklistItem(id="ci002", name="Item 2", state="incomplete"),
            ],
        )
        write_checklists(card.id, [cl1], "working", db_dir)

        loaded = read_checklists(card.id, "working", db_dir)
        assert len(loaded) == 1
        assert loaded[0].name == "MVP"
        assert len(loaded[0].items) == 2

        # Replace with different checklists
        cl2 = Checklist(
            id="cl002",
            name="Release",
            card_id=card.id,
            items=[ChecklistItem(id="ci003", name="Ship it", state="incomplete")],
        )
        write_checklists(card.id, [cl2], "working", db_dir)

        loaded = read_checklists(card.id, "working", db_dir)
        assert len(loaded) == 1
        assert loaded[0].name == "Release"
        assert len(loaded[0].items) == 1

    def test_checklists_empty_when_none(self, db_dir: Path) -> None:
        card = _make_card()
        write_card(card, "working", db_dir)
        loaded = read_checklists(card.id, "working", db_dir)
        assert loaded == []


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class TestLabels:
    def test_write_read_labels(self, db_dir: Path) -> None:
        labels = [
            Label(id="lbl1", name="bug", color="red"),
            Label(id="lbl2", name="feature", color="green"),
        ]
        write_labels(labels, "working", db_dir)

        loaded = read_labels("working", db_dir)
        assert len(loaded) == 2
        assert loaded[0].name == "bug"
        assert loaded[1].name == "feature"

    def test_labels_raw(self, db_dir: Path) -> None:
        labels = [Label(id="lbl1", name="bug", color="red")]
        write_labels(labels, "working", db_dir)
        raw = read_labels_raw("working", db_dir)
        assert raw == [{"id": "lbl1", "name": "bug", "color": "red"}]


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


class TestLists:
    def test_write_read_lists(self, db_dir: Path) -> None:
        lists = [
            TrelloList(id="list1", name="To Do", pos=1),
            TrelloList(id="list2", name="Done", pos=2),
        ]
        write_lists(lists, db_dir)

        loaded = read_lists(db_dir)
        assert len(loaded) == 2
        assert loaded["list1"]["name"] == "To Do"
        assert loaded["list2"]["name"] == "Done"

    def test_add_list(self, db_dir: Path) -> None:
        add_list("list1", "To Do", 1.0, db_dir)
        loaded = read_lists(db_dir)
        assert "list1" in loaded

    def test_remove_list(self, db_dir: Path) -> None:
        from trache.cache.db import remove_list

        add_list("list1", "To Do", 1.0, db_dir)
        remove_list("list1", db_dir)
        loaded = read_lists(db_dir)
        assert "list1" not in loaded


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


class TestResolve:
    def test_resolve_card_by_uid6(self, db_dir: Path) -> None:
        card = _make_card()
        write_card(card, "working", db_dir)
        resolved = resolve_card_id(card.uid6, db_dir)
        assert resolved == card.id

    def test_resolve_card_case_insensitive(self, db_dir: Path) -> None:
        card = _make_card()
        write_card(card, "working", db_dir)
        resolved = resolve_card_id(card.uid6.lower(), db_dir)
        assert resolved == card.id

    def test_resolve_card_full_id(self, db_dir: Path) -> None:
        result = resolve_card_id("67abc123def4567890fedcba", db_dir)
        assert result == "67abc123def4567890fedcba"

    def test_resolve_card_not_found(self, db_dir: Path) -> None:
        with pytest.raises(KeyError, match="not found"):
            resolve_card_id("AAAAAA", db_dir)

    def test_resolve_card_invalid_format(self, db_dir: Path) -> None:
        with pytest.raises(KeyError, match="Invalid card identifier"):
            resolve_card_id("not-hex!", db_dir)

    def test_resolve_card_no_db(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(KeyError, match="No board initialised"):
            resolve_card_id("ABCDEF", d)

    def test_resolve_list_by_name(self, db_dir: Path) -> None:
        add_list("list1", "To Do", 1.0, db_dir)
        result = resolve_list_id("To Do", db_dir)
        assert result == "list1"

    def test_resolve_list_case_insensitive(self, db_dir: Path) -> None:
        add_list("list1", "To Do", 1.0, db_dir)
        result = resolve_list_id("to do", db_dir)
        assert result == "list1"

    def test_resolve_list_not_found(self, db_dir: Path) -> None:
        with pytest.raises(KeyError, match="Cannot resolve"):
            resolve_list_id("Missing", db_dir)

    def test_resolve_list_name(self, db_dir: Path) -> None:
        add_list("list1", "To Do", 1.0, db_dir)
        assert resolve_list_name("list1", db_dir) == "To Do"
        assert resolve_list_name("unknown", db_dir) == "unknown"


# ---------------------------------------------------------------------------
# Cards index
# ---------------------------------------------------------------------------


class TestIndex:
    def test_load_cards_index(self, db_dir: Path) -> None:
        card = _make_card()
        write_card(card, "working", db_dir)
        index = load_cards_index(db_dir)
        assert card.id in index
        assert index[card.id]["uid6"] == card.uid6
        assert index[card.id]["title"] == card.title


# ---------------------------------------------------------------------------
# Full snapshot
# ---------------------------------------------------------------------------


class TestFullSnapshot:
    def test_write_full_snapshot(self, db_dir: Path) -> None:
        cards = [_make_card(card_id=f"card{i:022d}", title=f"Card {i}") for i in range(3)]
        checklists = [
            Checklist(
                id="cl001",
                name="MVP",
                card_id="card0000000000000000000000",
                items=[ChecklistItem(id="ci001", name="Item 1", state="complete")],
            )
        ]
        lists = [TrelloList(id="list1", name="To Do", pos=1)]
        labels = [Label(id="lbl1", name="bug", color="red")]

        write_full_snapshot(cards, checklists, lists, labels, db_dir)

        # Verify both copies exist
        clean_cards = list_cards("clean", db_dir)
        working_cards = list_cards("working", db_dir)
        assert len(clean_cards) == 3
        assert len(working_cards) == 3

        # Verify checklists
        cls = read_checklists("card0000000000000000000000", "clean", db_dir)
        assert len(cls) == 1
        assert cls[0].items[0].name == "Item 1"

        # Verify lists
        loaded_lists = read_lists(db_dir)
        assert "list1" in loaded_lists

        # Verify labels
        loaded_labels = read_labels("clean", db_dir)
        assert len(loaded_labels) == 1


# ---------------------------------------------------------------------------
# Migration from files
# ---------------------------------------------------------------------------


class TestMigration:
    def _setup_file_cache(self, d: Path) -> None:
        """Create a file-based cache structure for migration testing."""
        from trache.cache._atomic import atomic_write
        from trache.cache.store import card_to_markdown

        # Create directory structure
        for sub in ("clean/cards", "clean/checklists", "working/cards", "working/checklists", "indexes"):
            (d / sub).mkdir(parents=True, exist_ok=True)

        # Write a card
        card = _make_card()
        md = card_to_markdown(card)
        atomic_write(d / "clean" / "cards" / f"{card.id}.md", md)
        atomic_write(d / "working" / "cards" / f"{card.id}.md", md)

        # Write checklists
        cl_data = [
            {
                "id": "cl001",
                "name": "MVP",
                "card_id": card.id,
                "items": [
                    {"id": "ci001", "name": "Item 1", "state": "complete", "pos": 0},
                ],
                "pos": 0,
            }
        ]
        cl_json = json.dumps(cl_data, indent=2)
        atomic_write(d / "clean" / "checklists" / f"{card.id}.json", cl_json)
        atomic_write(d / "working" / "checklists" / f"{card.id}.json", cl_json)

        # Write labels
        labels_data = [{"id": "lbl1", "name": "bug", "color": "red"}]
        atomic_write(d / "clean" / "labels.json", json.dumps(labels_data))
        atomic_write(d / "working" / "labels.json", json.dumps(labels_data))

        # Write index
        index_data = {
            "cards_by_id": {},
            "cards_by_uid6": {},
            "cards_by_list": {},
            "lists_by_id": {"list1": {"name": "To Do", "pos": 1}},
        }
        atomic_write(d / "indexes" / "index.json", json.dumps(index_data))

    def test_migration_from_files(self, tmp_path: Path) -> None:
        d = tmp_path / "board"
        d.mkdir()
        self._setup_file_cache(d)

        # init_db should detect files and migrate
        init_db(d)

        # DB should exist, file dirs should be gone
        assert (d / DB_FILENAME).exists()
        assert not (d / "clean").exists()
        assert not (d / "working").exists()
        assert not (d / "indexes").exists()

        # Data should be accessible
        cards = list_cards("working", d)
        assert len(cards) == 1
        assert cards[0].title == "Test Card"

        cls = read_checklists(cards[0].id, "working", d)
        assert len(cls) == 1

        labels = read_labels("working", d)
        assert len(labels) == 1

        lists = read_lists(d)
        assert "list1" in lists

    def test_migration_crash_resume(self, tmp_path: Path) -> None:
        d = tmp_path / "board"
        d.mkdir()
        self._setup_file_cache(d)

        # Simulate Phase 1 complete (db created, sentinel written) but Phase 2 interrupted
        from trache.cache.db import _create_schema

        _create_schema(d)
        # Write sentinel but leave file dirs intact
        (d / MIGRATION_SENTINEL).write_text("done\n")

        # init_db should detect sentinel and resume Phase 2 (cleanup)
        init_db(d)

        assert (d / DB_FILENAME).exists()
        assert not (d / "clean").exists()
        assert not (d / "working").exists()
        assert not (d / "indexes").exists()
        assert not (d / MIGRATION_SENTINEL).exists()


# ---------------------------------------------------------------------------
# write_card_pull (atomic card-pull write)
# ---------------------------------------------------------------------------


class TestWriteCardPull:
    def test_roundtrip_both_copies(self, db_dir: Path) -> None:
        """write_card_pull writes card + checklists to both clean and working."""
        card = _make_card()
        cl = Checklist(
            id="cl001", name="MVP", card_id=card.id,
            items=[ChecklistItem(id="ci001", name="Item 1", state="complete")],
        )
        write_card_pull(card, [cl], db_dir)

        for copy in ("clean", "working"):
            loaded = read_card(card.id, copy, db_dir)
            assert loaded.title == card.title
            cls = read_checklists(card.id, copy, db_dir)
            assert len(cls) == 1
            assert cls[0].items[0].state == "complete"

    def test_caller_conn_no_independent_commit(self, db_dir: Path) -> None:
        """When conn is provided, write_card_pull doesn't commit independently."""
        card = _make_card()
        cl = Checklist(
            id="cl001", name="MVP", card_id=card.id,
            items=[ChecklistItem(id="ci001", name="Item 1", state="incomplete")],
        )

        with connect(db_dir) as conn:
            write_card_pull(card, [cl], db_dir, conn=conn)
            # Still inside caller's transaction — rollback to prove no independent commit
            conn.rollback()

        # Data should NOT exist because we rolled back the caller's transaction
        with pytest.raises(FileNotFoundError):
            read_card(card.id, "clean", db_dir)
