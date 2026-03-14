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
        assert "0.1." in result.output


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


class TestCardShowInvalidUID6:
    def test_invalid_uid6_friendly_error(self, tmp_path: Path, monkeypatch) -> None:
        """card show XXXXXX → exit 1, 'Invalid card identifier' in output (no traceback)."""
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["card", "show", "XXXXXX"])
        assert result.exit_code == 1
        assert "Invalid card identifier format" in result.output
        assert "Traceback" not in result.output

    def test_valid_hex_not_found(self, tmp_path: Path, monkeypatch) -> None:
        """card show ABCDEF (valid hex but not on board) → 'not found on this board'."""
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["card", "show", "ABCDEF"])
        assert result.exit_code == 1
        assert "not found on this board" in result.output
        assert "Traceback" not in result.output

    def test_invalid_uid6_on_edit_title(self, tmp_path: Path, monkeypatch) -> None:
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["card", "edit-title", "XXXXXX", "New"])
        assert result.exit_code == 1
        assert "Invalid card identifier format" in result.output
        assert "Traceback" not in result.output


class TestCardListInvalidList:
    def test_invalid_list_friendly_error(self, tmp_path: Path, monkeypatch) -> None:
        """card list --list Nonexistent → exit 1, 'Cannot resolve' in output."""
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["card", "list", "--list", "Nonexistent"])
        assert result.exit_code == 1
        assert "Cannot resolve" in result.output
        assert "Traceback" not in result.output


class TestCardAddLabel:
    def test_add_new_label(self, tmp_path: Path, monkeypatch) -> None:
        """Add a new label → status shows modified card."""
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["card", "add-label", "FEDCBA", "Bug"])
        assert result.exit_code == 0
        assert "added" in result.output

        # Verify status detects modification
        status_result = runner.invoke(app, ["status"])
        assert "Modified" in status_result.output

    def test_add_duplicate_label_idempotent(self, tmp_path: Path, monkeypatch) -> None:
        """Add same label twice → idempotent no-op on second call."""
        _setup_cli_cache(tmp_path, monkeypatch)
        runner.invoke(app, ["card", "add-label", "FEDCBA", "Bug"])
        result = runner.invoke(app, ["card", "add-label", "FEDCBA", "Bug"])
        assert result.exit_code == 0
        assert "already present" in result.output

    def test_add_label_invalid_uid6(self, tmp_path: Path, monkeypatch) -> None:
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["card", "add-label", "XXXXXX", "Bug"])
        assert result.exit_code == 1
        assert "Invalid card identifier format" in result.output


class TestCardRemoveLabel:
    def test_remove_existing_label(self, tmp_path: Path, monkeypatch) -> None:
        """Remove a label that exists → status detects modification."""
        _setup_cli_cache(tmp_path, monkeypatch)
        # First add a label
        runner.invoke(app, ["card", "add-label", "FEDCBA", "Bug"])
        # Then remove it
        result = runner.invoke(app, ["card", "remove-label", "FEDCBA", "Bug"])
        assert result.exit_code == 0
        assert "removed" in result.output.lower()

    def test_remove_absent_label_error(self, tmp_path: Path, monkeypatch) -> None:
        """Remove absent label → exit 1."""
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["card", "remove-label", "FEDCBA", "Nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestAgents:
    def test_agents_prints_install_block(self) -> None:
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        assert "local-first" in result.output.lower()
        assert "targeted" in result.output.lower()
        assert ".trache/" in result.output
        assert "trache agents --reference" in result.output

    def test_agents_contains_permission_prompt(self) -> None:
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "ask" in output_lower
        assert "permission" in output_lower

    def test_agents_reference_prints_reference(self) -> None:
        result = runner.invoke(app, ["agents", "--reference"])
        assert result.exit_code == 0
        assert "UID6" in result.output
        assert "trache card list" in result.output
        assert "trache push" in result.output

    def test_default_does_not_contain_reference_content(self) -> None:
        result = runner.invoke(app, ["agents"])
        assert result.exit_code == 0
        # UID6 explanation is reference-only content
        assert "Last 6 characters of a Trello card ID" not in result.output

    def test_reference_does_not_contain_preamble(self) -> None:
        result = runner.invoke(app, ["agents", "--reference"])
        assert result.exit_code == 0
        assert "copy below this line" not in result.output
        assert "Agent setup block" not in result.output

    def test_init_prints_agent_guidance(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TRELLO_API_KEY", "test_key")
        monkeypatch.setenv("TRELLO_TOKEN", "test_token")

        result = runner.invoke(app, ["init", "--board-id", "abc123def456789012345678"])
        output = result.output
        # Install block content
        assert "local-first" in output.lower()
        assert "trache agents --reference" in output
        # Human fallback note
        assert "setting this up manually" in output.lower()

    def test_preamble_and_human_note_outside_copy_block(self) -> None:
        result = runner.invoke(app, ["agents"])
        output = result.output
        copy_start = output.index("copy below this line")
        copy_end = output.index("copy above this line")
        # Preamble is before the copy block
        assert "Agent setup block" in output[:copy_start]
        # The install content is between delimiters
        between = output[copy_start:copy_end]
        assert "local-first" in between.lower()


class TestCardCreateTempMarker:
    def test_create_card_uid6_ends_with_temp_marker(self, tmp_path: Path, monkeypatch) -> None:
        """Locally created cards should have UID6 ending with 'T~'."""
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["card", "create", "To Do", "My New Card"])
        assert result.exit_code == 0

        # Find the newly created card file in working/cards
        working_cards = tmp_path / ".trache" / "working" / "cards"
        new_files = [f for f in working_cards.glob("*.md") if "new_" in f.stem]
        assert len(new_files) == 1
        # The filename stem is the card ID; uid6 = stem[-6:].upper()
        uid6 = new_files[0].stem[-6:].upper()
        assert uid6.endswith("T~"), f"Expected UID6 ending with 'T~', got '{uid6}'"


class TestChecklistAddItemHelp:
    def test_help_text_mentions_exact_match(self) -> None:
        """Verify help text contains 'exact match' and does not imply ID usage."""
        result = runner.invoke(app, ["checklist", "add-item", "--help"])
        assert result.exit_code == 0
        assert "exact match" in result.output.lower()
        # Help text may line-wrap, so check for both words separately
        assert "checklist" in result.output.lower()
        assert "show" in result.output.lower()
