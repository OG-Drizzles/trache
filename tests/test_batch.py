"""Tests for batch operations."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import seed_board
from typer.testing import CliRunner

from trache.cache.db import (
    read_card,
    read_checklists_raw,
    write_card,
    write_checklists_raw,
    write_lists,
)
from trache.cache.models import Card, TrelloList
from trache.cli.app import app
from trache.config import TracheConfig, ensure_cache_structure

runner = CliRunner()


def _setup_batch(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    trache_root = tmp_path / ".trache"
    trache_root.mkdir(exist_ok=True)
    cache_dir = trache_root / "boards" / "test"
    ensure_cache_structure(cache_dir)
    config = TracheConfig(board_id="board1")
    config.save(cache_dir)
    (trache_root / "active").write_text("test\n")

    lists = [
        TrelloList(id="list1", name="To Do", pos=1),
        TrelloList(id="list2", name="Done", pos=2),
    ]
    card = Card(
        id="67abc123def4567890fedcba", board_id="board1", list_id="list1", title="Test Card"
    )
    write_card(card, "clean", cache_dir)
    write_card(card, "working", cache_dir)
    write_lists(lists, cache_dir)
    seed_board([card], lists, cache_dir)

    cl_data = [{"id": "cl001", "name": "MVP", "card_id": card.id, "pos": 1, "items": [
        {"id": "ci001", "name": "Item 1", "state": "incomplete", "pos": 1},
    ]}]
    write_checklists_raw(card.id, cl_data, "clean", cache_dir)
    write_checklists_raw(card.id, cl_data, "working", cache_dir)

    return cache_dir


class TestBatchRun:
    def test_single_edit_title(self, tmp_path: Path, monkeypatch) -> None:
        cache_dir = _setup_batch(tmp_path, monkeypatch)
        input_text = 'card edit-title FEDCBA "New Title"\n'
        result = runner.invoke(app, ["batch", "run"], input=input_text)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["ok"] is True
        assert data[0]["title"] == "New Title"

        # Verify in db
        card = read_card("67abc123def4567890fedcba", "working", cache_dir)
        assert card.title == "New Title"

    def test_multiple_operations(self, tmp_path: Path, monkeypatch) -> None:
        _setup_batch(tmp_path, monkeypatch)
        input_text = (
            'card edit-title FEDCBA "Updated"\n'
            'card move FEDCBA Done\n'
        )
        result = runner.invoke(app, ["batch", "run"], input=input_text)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert all(d["ok"] for d in data)

    def test_unknown_command_rejected(self, tmp_path: Path, monkeypatch) -> None:
        _setup_batch(tmp_path, monkeypatch)
        input_text = 'comment add FEDCBA "hello"\n'
        result = runner.invoke(app, ["batch", "run"], input=input_text)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["ok"] is False
        assert "non-batchable" in data[0]["error"].lower() or "Unknown" in data[0]["error"]

    def test_blank_and_comment_lines_skipped(self, tmp_path: Path, monkeypatch) -> None:
        _setup_batch(tmp_path, monkeypatch)
        input_text = (
            '# This is a comment\n'
            '\n'
            'card edit-title FEDCBA "New"\n'
            '  \n'
        )
        result = runner.invoke(app, ["batch", "run"], input=input_text)
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["ok"] is True

    def test_error_does_not_halt_batch(self, tmp_path: Path, monkeypatch) -> None:
        _setup_batch(tmp_path, monkeypatch)
        input_text = (
            'card edit-title FEDCBA "Good"\n'
            'card edit-title ZZZZZZ "Bad"\n'
            'card move FEDCBA Done\n'
        )
        result = runner.invoke(app, ["batch", "run"], input=input_text)
        data = json.loads(result.output)
        assert len(data) == 3
        assert data[0]["ok"] is True
        assert data[1]["ok"] is False
        assert data[2]["ok"] is True

    def test_checklist_check(self, tmp_path: Path, monkeypatch) -> None:
        cache_dir = _setup_batch(tmp_path, monkeypatch)
        input_text = 'checklist check FEDCBA ci001\n'
        result = runner.invoke(app, ["batch", "run"], input=input_text)
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["ok"] is True
        assert data[0]["state"] == "complete"

        # Verify in db
        cls = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
        assert cls[0]["items"][0]["state"] == "complete"


class TestBatchArchivedGuard:
    def _archive_card(self, cache_dir: Path) -> None:
        """Archive the test card in working copy."""
        card = read_card("67abc123def4567890fedcba", "working", cache_dir)
        card.closed = True
        write_card(card, "working", cache_dir)

    def test_edit_title_blocked_on_archived(self, tmp_path: Path, monkeypatch) -> None:
        """F-011: edit-title on archived card → error dict."""
        cache_dir = _setup_batch(tmp_path, monkeypatch)
        self._archive_card(cache_dir)
        input_text = 'card edit-title FEDCBA "New Title"\n'
        result = runner.invoke(app, ["batch", "run"], input=input_text)
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["ok"] is False
        assert "archived" in data[0]["error"].lower()

    def test_checklist_check_blocked_on_archived(self, tmp_path: Path, monkeypatch) -> None:
        """F-011: checklist check on archived card → error dict."""
        cache_dir = _setup_batch(tmp_path, monkeypatch)
        self._archive_card(cache_dir)
        input_text = 'checklist check FEDCBA ci001\n'
        result = runner.invoke(app, ["batch", "run"], input=input_text)
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["ok"] is False
        assert "archived" in data[0]["error"].lower()

    def test_archive_allowed_on_archived(self, tmp_path: Path, monkeypatch) -> None:
        """F-011: archive on already-archived card is allowed (not guarded)."""
        cache_dir = _setup_batch(tmp_path, monkeypatch)
        self._archive_card(cache_dir)
        input_text = 'card archive FEDCBA\n'
        result = runner.invoke(app, ["batch", "run"], input=input_text)
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["ok"] is True

    def test_guard_does_not_halt_subsequent_commands(self, tmp_path: Path, monkeypatch) -> None:
        """F-011: archived guard error on one command doesn't halt the batch."""
        cache_dir = _setup_batch(tmp_path, monkeypatch)
        self._archive_card(cache_dir)
        input_text = (
            'card edit-title FEDCBA "Blocked"\n'
            'card archive FEDCBA\n'
        )
        result = runner.invoke(app, ["batch", "run"], input=input_text)
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["ok"] is False  # blocked by guard
        assert data[1]["ok"] is True   # archive still works
