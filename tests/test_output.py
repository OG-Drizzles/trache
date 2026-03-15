"""Tests for the machine-first output layer."""

from __future__ import annotations

import json

from trache.cli._output import OutputWriter, get_output, reset_output


class TestOutputWriter:
    def test_machine_mode_default(self, monkeypatch) -> None:
        """Default (no TRACHE_HUMAN) should be machine mode."""
        monkeypatch.delenv("TRACHE_HUMAN", raising=False)
        reset_output()
        out = get_output()
        assert not out.is_human

    def test_human_mode_opt_in(self, monkeypatch) -> None:
        """TRACHE_HUMAN=1 enables human mode."""
        monkeypatch.setenv("TRACHE_HUMAN", "1")
        reset_output()
        out = get_output()
        assert out.is_human

    def test_human_mode_zero_is_machine(self, monkeypatch) -> None:
        """TRACHE_HUMAN=0 stays in machine mode."""
        monkeypatch.setenv("TRACHE_HUMAN", "0")
        reset_output()
        out = get_output()
        assert not out.is_human

    def test_tsv_output(self, capsys) -> None:
        out = OutputWriter(human=False)
        out.tsv(
            [["ABC123", "To Do", "Fix bug"], ["DEF456", "Done", "Ship it"]],
            header=["uid6", "list", "title"],
        )
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert lines[0] == "uid6\tlist\ttitle"
        assert lines[1] == "ABC123\tTo Do\tFix bug"
        assert lines[2] == "DEF456\tDone\tShip it"

    def test_json_output(self, capsys) -> None:
        out = OutputWriter(human=False)
        out.json({"ok": True, "uid6": "ABC123"})
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data == {"ok": True, "uid6": "ABC123"}

    def test_json_compact(self, capsys) -> None:
        """JSON output should be compact (no whitespace)."""
        out = OutputWriter(human=False)
        out.json({"a": 1, "b": 2})
        captured = capsys.readouterr()
        assert " " not in captured.out.strip()

    def test_human_silent_in_machine_mode(self, capsys) -> None:
        """human() should produce no stdout in machine mode."""
        out = OutputWriter(human=False)
        out.human("[bold]Hello[/bold]")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_error_json_in_machine_mode(self, capsys) -> None:
        """error() should produce JSON on stderr in machine mode."""
        out = OutputWriter(human=False)
        out.error("something broke")
        captured = capsys.readouterr()
        assert captured.out == ""
        data = json.loads(captured.err.strip())
        assert data == {"error": "something broke"}

    def test_singleton_caching(self, monkeypatch) -> None:
        """get_output() returns the same instance on repeated calls."""
        monkeypatch.delenv("TRACHE_HUMAN", raising=False)
        reset_output()
        a = get_output()
        b = get_output()
        assert a is b

    def test_reset_clears_singleton(self, monkeypatch) -> None:
        monkeypatch.delenv("TRACHE_HUMAN", raising=False)
        reset_output()
        a = get_output()
        reset_output()
        b = get_output()
        assert a is not b
