"""Tests for CLI commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from trache.cli.app import app

runner = CliRunner()


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
        assert "0.1.1" in result.output


class TestStatus:
    def test_status_no_cache(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["status"])
        # No .trache/ directory → empty diff → reports clean
        assert result.exit_code == 0
        assert "Clean" in result.output or "no local changes" in result.output
