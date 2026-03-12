"""Tests for CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from trache.cache.index import build_index
from trache.cache.models import Card, TrelloList
from trache.cache.store import write_card_file
from trache.cli.app import app
from trache.config import TracheConfig, ensure_cache_structure

runner = CliRunner()


def _setup_cli_cache(tmp_path: Path, monkeypatch) -> Path:
    """Set up a full .trache/ directory for CLI tests and chdir into tmp_path."""
    monkeypatch.chdir(tmp_path)
    cache_dir = tmp_path / ".trache"
    ensure_cache_structure(cache_dir)
    config = TracheConfig(board_id="board1")
    config.save(cache_dir)

    card = Card(
        id="67abc123def4567890fedcba",
        board_id="board1",
        list_id="list1",
        title="Test Card",
    )
    lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
    write_card_file(card, cache_dir / "clean" / "cards")
    write_card_file(card, cache_dir / "working" / "cards")
    build_index([card], lists, cache_dir / "indexes")

    cl_data = [
        {
            "id": "cl001",
            "name": "MVP",
            "card_id": "67abc123def4567890fedcba",
            "pos": 1,
            "items": [
                {"id": "ci001", "name": "Item 1", "state": "incomplete", "pos": 1},
                {"id": "ci002", "name": "Item 2", "state": "complete", "pos": 2},
            ],
        }
    ]
    cl_json = json.dumps(cl_data, indent=2) + "\n"
    (cache_dir / "clean" / "checklists").mkdir(parents=True, exist_ok=True)
    (cache_dir / "working" / "checklists").mkdir(parents=True, exist_ok=True)
    (cache_dir / "clean" / "checklists" / "67abc123def4567890fedcba.json").write_text(cl_json)
    (cache_dir / "working" / "checklists" / "67abc123def4567890fedcba.json").write_text(cl_json)

    return cache_dir


class TestInit:
    def test_init_creates_cache_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TRELLO_API_KEY", "test_key")
        monkeypatch.setenv("TRELLO_TOKEN", "test_token")

        result = runner.invoke(app, ["init", "--board-id", "abc123def456789012345678"])
        assert result.exit_code == 0 or "Could not fetch board name" in result.output
        assert (tmp_path / ".trache").exists()
        assert (tmp_path / ".trache" / "config.json").exists()


class TestVersion:
    def test_version(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "0.1.2" in result.output


class TestStatus:
    def test_status_no_cache(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["status"])
        # No .trache/ directory → empty diff → reports clean
        assert result.exit_code == 0
        assert "Clean" in result.output or "no local changes" in result.output


class TestChecklistCheck:
    def test_check_marks_complete(self, tmp_path: Path, monkeypatch) -> None:
        cache_dir = _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["checklist", "check", "FEDCBA", "ci001"])
        assert result.exit_code == 0
        assert "complete" in result.output

        # Verify the item state changed in working
        cl_data = json.loads(
            (cache_dir / "working" / "checklists" / "67abc123def4567890fedcba.json").read_text()
        )
        item = cl_data[0]["items"][0]
        assert item["state"] == "complete"

    def test_check_item_not_found(self, tmp_path: Path, monkeypatch) -> None:
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["checklist", "check", "FEDCBA", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestChecklistUncheck:
    def test_uncheck_marks_incomplete(self, tmp_path: Path, monkeypatch) -> None:
        cache_dir = _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["checklist", "uncheck", "FEDCBA", "ci002"])
        assert result.exit_code == 0
        assert "incomplete" in result.output

        cl_data = json.loads(
            (cache_dir / "working" / "checklists" / "67abc123def4567890fedcba.json").read_text()
        )
        item = cl_data[0]["items"][1]
        assert item["state"] == "incomplete"

    def test_uncheck_item_not_found(self, tmp_path: Path, monkeypatch) -> None:
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["checklist", "uncheck", "FEDCBA", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestChecklistAddItem:
    def test_add_item_to_checklist(self, tmp_path: Path, monkeypatch) -> None:
        cache_dir = _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["checklist", "add-item", "FEDCBA", "MVP", "New Task"])
        assert result.exit_code == 0
        assert "New Task" in result.output

        cl_data = json.loads(
            (cache_dir / "working" / "checklists" / "67abc123def4567890fedcba.json").read_text()
        )
        assert len(cl_data[0]["items"]) == 3
        new_item = cl_data[0]["items"][2]
        assert new_item["name"] == "New Task"
        assert new_item["state"] == "incomplete"
        assert new_item["id"].startswith("temp_")

    def test_add_item_checklist_not_found(self, tmp_path: Path, monkeypatch) -> None:
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["checklist", "add-item", "FEDCBA", "NoSuchList", "Task"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestChecklistRemoveItem:
    def test_remove_item_from_checklist(self, tmp_path: Path, monkeypatch) -> None:
        cache_dir = _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["checklist", "remove-item", "FEDCBA", "ci001"])
        assert result.exit_code == 0
        assert "removed" in result.output.lower()

        cl_data = json.loads(
            (cache_dir / "working" / "checklists" / "67abc123def4567890fedcba.json").read_text()
        )
        assert len(cl_data[0]["items"]) == 1
        assert cl_data[0]["items"][0]["id"] == "ci002"

    def test_remove_item_not_found(self, tmp_path: Path, monkeypatch) -> None:
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["checklist", "remove-item", "FEDCBA", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output
