"""Tests for trache health command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from trache.cache.db import connect
from trache.cli.app import app
from trache.config import TracheConfig, ensure_cache_structure

runner = CliRunner()


def _setup_health_cache(tmp_path: Path, monkeypatch, *, human: bool = True) -> Path:
    """Set up a full .trache/ directory for health tests."""
    if human:
        monkeypatch.setenv("TRACHE_HUMAN", "1")
    else:
        monkeypatch.delenv("TRACHE_HUMAN", raising=False)
    from trache.cli._output import reset_output
    reset_output()
    monkeypatch.chdir(tmp_path)
    trache_root = tmp_path / ".trache"
    trache_root.mkdir(exist_ok=True)
    cache_dir = trache_root / "boards" / "test"
    ensure_cache_structure(cache_dir)
    config = TracheConfig(board_id="abc123def456789012345678")
    config.save(cache_dir)
    (trache_root / "active").write_text("test\n")
    return cache_dir


class TestHealth:
    def test_health_all_pass_local(self, tmp_path: Path, monkeypatch) -> None:
        """Full setup + --local → all pass, exit 0."""
        _setup_health_cache(tmp_path, monkeypatch)
        monkeypatch.setenv("TRELLO_API_KEY", "dummy")
        monkeypatch.setenv("TRELLO_TOKEN", "dummy")
        result = runner.invoke(app, ["health", "--local"])
        assert result.exit_code == 0
        assert "pass" in result.output
        assert "All checks passed" in result.output

    def test_health_no_board_config(self, tmp_path: Path, monkeypatch) -> None:
        """No .trache → config fails, exit 1."""
        monkeypatch.setenv("TRACHE_HUMAN", "1")
        from trache.cli._output import reset_output
        reset_output()
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 1
        assert "fail" in result.output

    def test_health_bad_schema_version(self, tmp_path: Path, monkeypatch) -> None:
        """Tamper schema version to 999 → database check fails, exit 1."""
        cache_dir = _setup_health_cache(tmp_path, monkeypatch)
        monkeypatch.setenv("TRELLO_API_KEY", "dummy")
        monkeypatch.setenv("TRELLO_TOKEN", "dummy")
        with connect(cache_dir) as conn:
            conn.execute("UPDATE schema_version SET version = 999")
        result = runner.invoke(app, ["health", "--local"])
        assert result.exit_code == 1
        assert "mismatch" in result.output or "fail" in result.output

    def test_health_missing_auth_env(self, tmp_path: Path, monkeypatch) -> None:
        """Unset API key → auth fails, exit 1."""
        _setup_health_cache(tmp_path, monkeypatch)
        monkeypatch.delenv("TRELLO_API_KEY", raising=False)
        monkeypatch.delenv("TRELLO_TOKEN", raising=False)
        result = runner.invoke(app, ["health", "--local"])
        assert result.exit_code == 1
        assert "fail" in result.output

    def test_health_api_connectivity_pass(self, tmp_path: Path, monkeypatch) -> None:
        """Mock get_current_member() → pass, exit 0."""
        _setup_health_cache(tmp_path, monkeypatch)
        monkeypatch.setenv("TRELLO_API_KEY", "dummy")
        monkeypatch.setenv("TRELLO_TOKEN", "dummy")

        with patch("trache.api.client.TrelloClient") as MockClient:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get_current_member.return_value = {"username": "testuser"}
            MockClient.return_value = mock_client

            result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "testuser" in result.output

    def test_health_api_401(self, tmp_path: Path, monkeypatch) -> None:
        """Mock HTTPStatusError(401) → fail, exit 1."""
        import httpx

        _setup_health_cache(tmp_path, monkeypatch)
        monkeypatch.setenv("TRELLO_API_KEY", "dummy")
        monkeypatch.setenv("TRELLO_TOKEN", "dummy")

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("trache.api.client.TrelloClient") as MockClient:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get_current_member.side_effect = httpx.HTTPStatusError(
                "401", request=MagicMock(), response=mock_response
            )
            MockClient.return_value = mock_client

            result = runner.invoke(app, ["health"])
        assert result.exit_code == 1
        assert "401" in result.output or "Unauthorized" in result.output

    def test_health_machine_output(self, tmp_path: Path, monkeypatch) -> None:
        """Machine mode → JSON output with checks array."""
        _setup_health_cache(tmp_path, monkeypatch, human=False)
        monkeypatch.setenv("TRELLO_API_KEY", "dummy")
        monkeypatch.setenv("TRELLO_TOKEN", "dummy")
        result = runner.invoke(app, ["health", "--local"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "checks" in data
        assert "all_ok" in data
        assert data["all_ok"] is True
        check_names = [c["name"] for c in data["checks"]]
        assert "board_config" in check_names
        assert "database" in check_names

    def test_health_exit_code_on_failure(self, tmp_path: Path, monkeypatch) -> None:
        """Any non-skipped failure → exit 1."""
        _setup_health_cache(tmp_path, monkeypatch)
        monkeypatch.delenv("TRELLO_API_KEY", raising=False)
        monkeypatch.delenv("TRELLO_TOKEN", raising=False)
        result = runner.invoke(app, ["health", "--local"])
        assert result.exit_code == 1

    def test_health_local_skips_api(self, tmp_path: Path, monkeypatch) -> None:
        """--local flag → api_connectivity is skipped."""
        _setup_health_cache(tmp_path, monkeypatch, human=False)
        monkeypatch.setenv("TRELLO_API_KEY", "dummy")
        monkeypatch.setenv("TRELLO_TOKEN", "dummy")
        result = runner.invoke(app, ["health", "--local"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        api_check = next(c for c in data["checks"] if c["name"] == "api_connectivity")
        assert api_check["status"] == "skipped"
        assert "--local" in api_check["detail"]
