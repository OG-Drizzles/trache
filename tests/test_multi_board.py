"""Tests for multi-board support."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from trache.cache.index import build_index
from trache.cache.models import Card, TrelloList
from trache.cache.store import write_card_file
from trache.cli._context import (
    _fuzzy_match,
    list_board_names,
    resolve_cache_dir,
    set_active_board,
    set_board_override,
    slugify,
)
from trache.cli.app import app
from trache.config import TracheConfig, ensure_cache_structure

runner = CliRunner()


# --- Helpers ---


def _create_board(trache_root: Path, alias: str, board_id: str = "board123", board_name: str = "Test") -> Path:
    """Create a board directory with config."""
    board_dir = trache_root / "boards" / alias
    ensure_cache_structure(board_dir)
    config = TracheConfig(board_id=board_id, board_name=board_name)
    config.save(board_dir)
    return board_dir


def _setup_multi_board(tmp_path: Path, monkeypatch) -> Path:
    """Set up a multi-board .trache/ with two boards."""
    monkeypatch.chdir(tmp_path)
    trache_root = tmp_path / ".trache"
    trache_root.mkdir()
    (trache_root / "boards").mkdir()

    _create_board(trache_root, "work", "board_work_id_1234567890ab", "My Work Board")
    _create_board(trache_root, "personal", "board_pers_id_1234567890ab", "Personal Projects")

    (trache_root / "active").write_text("work\n")
    # Reset any override from previous tests
    set_board_override(None)
    return trache_root


# --- slugify tests ---


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("My Board") == "my-board"

    def test_special_chars(self) -> None:
        assert slugify("Project #1 (v2)") == "project-1-v2"

    def test_spaces_and_hyphens(self) -> None:
        assert slugify("  multiple   spaces  ") == "multiple-spaces"

    def test_already_slug(self) -> None:
        assert slugify("my-board") == "my-board"

    def test_empty_string(self) -> None:
        assert slugify("") == "default"

    def test_all_special(self) -> None:
        assert slugify("!!!") == "default"

    def test_unicode(self) -> None:
        # Unicode letters outside a-z are stripped
        assert slugify("café board") == "caf-board"

    def test_consecutive_hyphens(self) -> None:
        assert slugify("a---b") == "a-b"


# --- resolve_cache_dir tests ---


class TestResolveCacheDir:
    def test_no_trache_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        set_board_override(None)
        with pytest.raises(FileNotFoundError):
            resolve_cache_dir()

    def test_legacy_layout_auto_migrates(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        set_board_override(None)

        # Create legacy flat layout
        legacy = tmp_path / ".trache"
        ensure_cache_structure(legacy)
        config = TracheConfig(board_id="legacy_board_123456789012", board_name="Legacy Board")
        config.save(legacy)

        result = resolve_cache_dir()
        assert "boards" in str(result)
        assert result.exists()
        assert (result / "config.json").exists()
        # Legacy config.json should be moved
        assert not (legacy / "config.json").exists()
        # Active file should be set
        assert (legacy / "active").exists()

    def test_override_routes_correctly(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        set_board_override("work")
        result = resolve_cache_dir()
        assert result.resolve() == (tmp_path / ".trache" / "boards" / "work").resolve()

    def test_override_unknown_alias_errors(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        set_board_override("nonexistent")
        with pytest.raises(FileNotFoundError, match="not found"):
            resolve_cache_dir()

    def test_override_unknown_alias_suggests(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        set_board_override("wrk")  # close to "work"
        with pytest.raises(FileNotFoundError, match="Did you mean"):
            resolve_cache_dir()

    def test_active_board_routes_correctly(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        result = resolve_cache_dir()
        assert result.resolve() == (tmp_path / ".trache" / "boards" / "work").resolve()

    def test_switch_changes_active(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        set_active_board("personal")
        result = resolve_cache_dir()
        assert result.resolve() == (tmp_path / ".trache" / "boards" / "personal").resolve()


# --- board list command ---


class TestBoardList:
    def test_list_shows_boards(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        result = runner.invoke(app, ["board", "list"])
        assert result.exit_code == 0
        assert "work" in result.output
        assert "personal" in result.output
        assert "My Work Board" in result.output

    def test_list_marks_active(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        result = runner.invoke(app, ["board", "list"])
        assert result.exit_code == 0
        # The active board should have an asterisk marker
        assert "*" in result.output

    def test_list_no_boards(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        set_board_override(None)
        trache_root = tmp_path / ".trache"
        trache_root.mkdir()
        (trache_root / "boards").mkdir()
        result = runner.invoke(app, ["board", "list"])
        assert result.exit_code == 0
        assert "No boards" in result.output


# --- board switch command ---


class TestBoardSwitch:
    def test_switch_updates_active(self, tmp_path: Path, monkeypatch) -> None:
        trache_root = _setup_multi_board(tmp_path, monkeypatch)
        result = runner.invoke(app, ["board", "switch", "personal"])
        assert result.exit_code == 0
        assert "personal" in result.output
        assert (trache_root / "active").read_text().strip() == "personal"

    def test_switch_unknown_alias(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        result = runner.invoke(app, ["board", "switch", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output


# --- board destroy command ---


class TestBoardDestroy:
    def test_destroy_without_yes(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        result = runner.invoke(app, ["board", "destroy", "personal"])
        assert result.exit_code == 1
        assert "--yes" in result.output

    def test_destroy_with_dirty_state_no_force(self, tmp_path: Path, monkeypatch) -> None:
        trache_root = _setup_multi_board(tmp_path, monkeypatch)
        # Create a card in working but not clean to simulate dirty state
        board_dir = trache_root / "boards" / "personal"
        card = Card(
            id="67abc123def4567890aaaaaa",
            board_id="board_pers_id_1234567890ab",
            list_id="list1",
            title="Dirty Card",
        )
        lists = [TrelloList(id="list1", name="To Do", board_id="board_pers_id_1234567890ab", pos=1)]
        write_card_file(card, board_dir / "working" / "cards")
        build_index([card], lists, board_dir / "indexes")

        result = runner.invoke(app, ["board", "destroy", "personal", "--yes"])
        assert result.exit_code == 1
        assert "unpushed" in result.output

    def test_destroy_yes_force(self, tmp_path: Path, monkeypatch) -> None:
        trache_root = _setup_multi_board(tmp_path, monkeypatch)
        result = runner.invoke(app, ["board", "destroy", "personal", "--yes", "--force"])
        assert result.exit_code == 0
        assert "Destroyed" in result.output
        assert not (trache_root / "boards" / "personal").exists()
        # Active should still be "work"
        assert (trache_root / "active").read_text().strip() == "work"

    def test_destroy_active_board_switches(self, tmp_path: Path, monkeypatch) -> None:
        trache_root = _setup_multi_board(tmp_path, monkeypatch)
        result = runner.invoke(app, ["board", "destroy", "work", "--yes", "--force"])
        assert result.exit_code == 0
        # Should switch to remaining board
        assert (trache_root / "active").read_text().strip() == "personal"

    def test_destroy_last_board_removes_active(self, tmp_path: Path, monkeypatch) -> None:
        trache_root = _setup_multi_board(tmp_path, monkeypatch)
        # Destroy both
        runner.invoke(app, ["board", "destroy", "personal", "--yes", "--force"])
        result = runner.invoke(app, ["board", "destroy", "work", "--yes", "--force"])
        assert result.exit_code == 0
        active_file = trache_root / "active"
        assert not active_file.exists()


# --- init with --name ---


class TestInitMultiBoard:
    def test_init_with_name(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        set_board_override(None)
        monkeypatch.delenv("TRELLO_API_KEY", raising=False)
        monkeypatch.delenv("TRELLO_TOKEN", raising=False)

        result = runner.invoke(app, ["init", "--board-id", "abc123def456789012345678", "--name", "work"])
        assert result.exit_code == 0
        assert (tmp_path / ".trache" / "boards" / "work").exists()
        assert (tmp_path / ".trache" / "boards" / "work" / "config.json").exists()
        assert (tmp_path / ".trache" / "active").read_text().strip() == "work"

    def test_init_alias_collision(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        set_board_override(None)
        monkeypatch.delenv("TRELLO_API_KEY", raising=False)
        monkeypatch.delenv("TRELLO_TOKEN", raising=False)

        # First init
        runner.invoke(app, ["init", "--board-id", "abc123def456789012345678", "--name", "work"])
        # Second init with same name
        result = runner.invoke(app, ["init", "--board-id", "def456789012345678abc123", "--name", "work"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_init_second_board(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        set_board_override(None)
        monkeypatch.delenv("TRELLO_API_KEY", raising=False)
        monkeypatch.delenv("TRELLO_TOKEN", raising=False)

        runner.invoke(app, ["init", "--board-id", "abc123def456789012345678", "--name", "work"])
        result = runner.invoke(app, ["init", "--board-id", "def456789012345678abc123", "--name", "personal"])
        assert result.exit_code == 0
        assert (tmp_path / ".trache" / "boards" / "personal").exists()
        # Active should still be work (first board set)
        assert (tmp_path / ".trache" / "active").read_text().strip() == "work"


# --- --board flag routing ---


class TestBoardFlag:
    def test_board_flag_routes_card_list(self, tmp_path: Path, monkeypatch) -> None:
        trache_root = _setup_multi_board(tmp_path, monkeypatch)
        # Add a card to "work" board
        board_dir = trache_root / "boards" / "work"
        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board_work_id_1234567890ab",
            list_id="list1",
            title="Work Card",
        )
        lists = [TrelloList(id="list1", name="To Do", board_id="board_work_id_1234567890ab", pos=1)]
        write_card_file(card, board_dir / "working" / "cards")
        build_index([card], lists, board_dir / "indexes")

        result = runner.invoke(app, ["--board", "work", "card", "list"])
        assert result.exit_code == 0
        assert "Work Card" in result.output


# --- Legacy migration ---


class TestLegacyMigration:
    def test_legacy_auto_migrates(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        set_board_override(None)

        # Create legacy flat layout
        legacy = tmp_path / ".trache"
        ensure_cache_structure(legacy)
        config = TracheConfig(board_id="legacy_board_123456789012", board_name="My Legacy Board")
        config.save(legacy)

        # Run any command — should trigger migration
        result = resolve_cache_dir()
        assert (legacy / "boards").exists()
        alias = (legacy / "active").read_text().strip()
        assert alias == "my-legacy-board"
        assert (legacy / "boards" / alias / "config.json").exists()

    def test_legacy_migration_is_idempotent(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        set_board_override(None)

        # Create legacy flat layout
        legacy = tmp_path / ".trache"
        ensure_cache_structure(legacy)
        config = TracheConfig(board_id="legacy_board_123456789012", board_name="Board")
        config.save(legacy)

        # Migrate once
        resolve_cache_dir()
        # Migrate again (should not error)
        result = resolve_cache_dir()
        assert result.exists()


# --- Fuzzy match ---


class TestFuzzyMatch:
    def test_prefix_match(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        assert _fuzzy_match("wor") == "work"

    def test_substring_match(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        assert _fuzzy_match("person") == "personal"

    def test_no_match(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        assert _fuzzy_match("zzzzz") is None

    def test_edit_distance_match(self, tmp_path: Path, monkeypatch) -> None:
        _setup_multi_board(tmp_path, monkeypatch)
        assert _fuzzy_match("wrk") == "work"
