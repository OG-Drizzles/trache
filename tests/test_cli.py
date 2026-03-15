"""Tests for CLI commands."""

from __future__ import annotations

from pathlib import Path

from conftest import seed_board
from typer.testing import CliRunner

from trache.cache.db import list_cards, read_checklists_raw, write_card, write_checklists_raw
from trache.cache.models import Card, TrelloList
from trache.cli.app import app
from trache.config import TracheConfig, ensure_cache_structure

runner = CliRunner()


def _setup_cli_cache(tmp_path: Path, monkeypatch) -> Path:
    """Set up a full .trache/ directory for CLI tests and chdir into tmp_path.

    Uses multi-board layout: .trache/boards/test/...
    Sets TRACHE_HUMAN=1 so CLI tests get Rich-formatted output.
    """
    monkeypatch.setenv("TRACHE_HUMAN", "1")
    from trache.cli._output import reset_output
    reset_output()
    monkeypatch.chdir(tmp_path)
    trache_root = tmp_path / ".trache"
    trache_root.mkdir(exist_ok=True)
    cache_dir = trache_root / "boards" / "test"
    ensure_cache_structure(cache_dir)
    config = TracheConfig(board_id="board1")
    config.save(cache_dir)
    # Set active board
    (trache_root / "active").write_text("test\n")

    card = Card(
        id="67abc123def4567890fedcba",
        board_id="board1",
        list_id="list1",
        title="Test Card",
    )
    lists = [TrelloList(id="list1", name="To Do", board_id="board1", pos=1)]
    write_card(card, "clean", cache_dir)
    write_card(card, "working", cache_dir)
    seed_board([card], lists, cache_dir)

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
    write_checklists_raw("67abc123def4567890fedcba", cl_data, "clean", cache_dir)
    write_checklists_raw("67abc123def4567890fedcba", cl_data, "working", cache_dir)

    return cache_dir


class TestInit:
    def test_init_creates_cache_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TRELLO_API_KEY", "test_key")
        monkeypatch.setenv("TRELLO_TOKEN", "test_token")

        result = runner.invoke(app, ["init", "--board-id", "abc123def456789012345678"])
        assert result.exit_code == 0 or "Could not fetch board name" in result.output
        assert (tmp_path / ".trache").exists()
        assert (tmp_path / ".trache" / "boards").exists()
        # Config should exist under boards/<alias>/
        boards_dir = tmp_path / ".trache" / "boards"
        aliases = [d.name for d in boards_dir.iterdir() if d.is_dir()]
        assert len(aliases) == 1
        assert (boards_dir / aliases[0] / "config.json").exists()


class TestVersion:
    def test_version(self, monkeypatch) -> None:
        monkeypatch.setenv("TRACHE_HUMAN", "1")
        from trache.cli._output import reset_output
        reset_output()
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        versions = ["0.1.", "0.2.", "0.3."]
        assert "trache " in result.output and any(v in result.output for v in versions)


class TestStatus:
    def test_status_no_cache(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("TRACHE_HUMAN", "1")
        from trache.cli._output import reset_output
        reset_output()
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
        cl_data = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
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

        cl_data = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
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

        cl_data = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
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

        cl_data = read_checklists_raw("67abc123def4567890fedcba", "working", cache_dir)
        assert len(cl_data[0]["items"]) == 1
        assert cl_data[0]["items"][0]["id"] == "ci002"

    def test_remove_item_not_found(self, tmp_path: Path, monkeypatch) -> None:
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["checklist", "remove-item", "FEDCBA", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestCardShowDisplaysChecklists:
    """F-005: card show must display checklists from the JSON file."""

    def test_card_show_displays_checklists(self, tmp_path: Path, monkeypatch) -> None:
        _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["card", "show", "FEDCBA"])
        assert result.exit_code == 0
        assert "MVP" in result.output
        assert "Item 1" in result.output
        assert "Item 2" in result.output
        # Verify checklist state markers
        assert "[ ]" in result.output  # incomplete item
        assert "[x]" in result.output  # complete item

    def test_card_show_no_checklists(self, tmp_path: Path, monkeypatch) -> None:
        """Card with no checklists should still show without errors."""
        _setup_cli_cache(tmp_path, monkeypatch)
        # Clear checklists for this card in the working copy
        cache_dir = tmp_path / ".trache" / "boards" / "test"
        write_checklists_raw("67abc123def4567890fedcba", [], "working", cache_dir)
        result = runner.invoke(app, ["card", "show", "FEDCBA"])
        assert result.exit_code == 0
        assert "Test Card" in result.output
        # Should not contain checklist headers
        assert "MVP" not in result.output


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

    def test_init_machine_includes_install_block(self, tmp_path: Path, monkeypatch) -> None:
        """Machine mode: init returns JSON with install_block field."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TRELLO_API_KEY", "test_key")
        monkeypatch.setenv("TRELLO_TOKEN", "test_token")

        result = runner.invoke(app, ["init", "--board-id", "abc123def456789012345678"])
        import json
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "install_block" in data
        assert "local-first" in data["install_block"].lower()
        assert "trache agents --reference" in data["install_block"]

    def test_init_human_prints_agent_guidance(self, tmp_path: Path, monkeypatch) -> None:
        """Human mode: init prints Rich agent guidance panels."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TRELLO_API_KEY", "test_key")
        monkeypatch.setenv("TRELLO_TOKEN", "test_token")
        monkeypatch.setenv("TRACHE_HUMAN", "1")
        from trache.cli._output import reset_output
        reset_output()

        result = runner.invoke(app, ["init", "--board-id", "abc123def456789012345678"])
        output = result.output
        assert "local-first" in output.lower()
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


class TestInitAuth:
    def test_init_no_env_vars_shows_auth_panel_with_placeholder(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """init with no env vars → output contains Auth Setup panel + YOUR_API_KEY placeholder."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("TRELLO_API_KEY", raising=False)
        monkeypatch.delenv("TRELLO_TOKEN", raising=False)

        result = runner.invoke(app, ["init", "--board-id", "abc123def456789012345678"])
        assert result.exit_code == 0
        assert "Auth Setup" in result.output
        assert "YOUR_API_KEY" in result.output

    def test_init_api_key_only_shows_real_key_in_url(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """init with API key only → output contains real key in URL."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TRELLO_API_KEY", "mykey123")
        monkeypatch.delenv("TRELLO_TOKEN", raising=False)

        result = runner.invoke(app, ["init", "--board-id", "abc123def456789012345678"])
        assert result.exit_code == 0
        assert "Auth Setup" in result.output
        assert "mykey123" in result.output
        assert "YOUR_API_KEY" not in result.output

    def test_init_auth_flag_with_both_vars_still_shows_panel(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """init --auth with both vars → still prints guidance panel."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TRELLO_API_KEY", "test_key")
        monkeypatch.setenv("TRELLO_TOKEN", "test_token")

        result = runner.invoke(app, ["init", "--board-id", "abc123def456789012345678", "--auth"])
        assert "Auth Setup" in result.output


class TestBuildAuthUrl:
    def test_build_auth_url_with_key(self) -> None:
        from trache.cli.agents import build_auth_url

        url = build_auth_url("mykey")
        assert "key=mykey" in url
        assert "YOUR_API_KEY" not in url

    def test_build_auth_url_without_key(self) -> None:
        from trache.cli.agents import build_auth_url

        url = build_auth_url(None)
        assert "key=YOUR_API_KEY" in url

    def test_build_auth_url_default(self) -> None:
        from trache.cli.agents import build_auth_url

        url = build_auth_url()
        assert "key=YOUR_API_KEY" in url


class TestCardCreateTempMarker:
    def test_create_card_uid6_ends_with_temp_marker(self, tmp_path: Path, monkeypatch) -> None:
        """Locally created cards should have UID6 ending with 'T~'."""
        cache_dir = _setup_cli_cache(tmp_path, monkeypatch)
        result = runner.invoke(app, ["card", "create", "To Do", "My New Card"])
        assert result.exit_code == 0

        # Find the newly created card in the working copy via SQLite
        cards = list_cards("working", cache_dir)
        new_cards = [c for c in cards if c.id.startswith("new_")]
        assert len(new_cards) == 1
        uid6 = new_cards[0].uid6
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
