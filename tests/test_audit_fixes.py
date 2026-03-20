"""Regression tests for follow-up audit fixes (v0.1.2).

Covers:
- Label order change does NOT bump content_modified_at
- Label-only push does NOT send redundant desc update
- Re-pull failure surfaces in PushResult.errors
- Old checklists/ migration path cleanup
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from conftest import make_mock_client, setup_cache

from trache.cache.db import read_card, write_card, write_labels_raw
from trache.cache.models import Card
from trache.sync.pull import pull_full_board
from trache.sync.push import push_changes


class TestLabelOrderDoesNotBumpContentModifiedAt:
    def test_label_reorder_preserves_content_modified_at(self, tmp_path: Path) -> None:
        """Labels in a different order should NOT bump content_modified_at."""
        cache_dir, config = setup_cache(tmp_path)

        original_time = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Same",
            labels=["bug", "feature"],
            content_modified_at=original_time,
            last_activity=original_time,
        )

        # First pull
        client = make_mock_client([card])
        pull_full_board(config, client, cache_dir, force=True)

        stored = read_card("67abc123def4567890fedcba", "clean", cache_dir)
        first_modified = stored.content_modified_at

        # Re-pull with labels in REVERSED order, same content otherwise
        later_time = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)
        card_v2 = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Same",
            labels=["feature", "bug"],  # reversed order
            content_modified_at=later_time,
            last_activity=later_time,
        )
        client2 = make_mock_client([card_v2])
        pull_full_board(config, client2, cache_dir, force=True)

        stored2 = read_card("67abc123def4567890fedcba", "clean", cache_dir)
        assert stored2.content_modified_at == first_modified


class TestLabelOnlyPushNoRedundantDesc:
    def test_label_only_change_does_not_send_desc(self, tmp_path: Path) -> None:
        """When only labels change, desc should NOT be included in update_card."""
        cache_dir, config = setup_cache(tmp_path)

        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Same description",
            labels=["bug"],
            content_modified_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        )

        write_card(card, "clean", cache_dir)
        labels_data = [
            {"id": "lbl1", "name": "bug", "color": "red"},
            {"id": "lbl2", "name": "feature", "color": "blue"},
        ]
        write_labels_raw(labels_data, "clean", cache_dir)
        write_labels_raw(labels_data, "working", cache_dir)

        # Change only labels in working copy
        working_card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Same description",
            labels=["bug", "feature"],
            content_modified_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            last_activity=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        write_card(working_card, "working", cache_dir)

        client = MagicMock()
        client.update_card.return_value = working_card
        client.get_card.return_value = working_card
        client.get_card_checklists.return_value = []

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        # Verify update_card was called
        client.update_card.assert_called_once()
        call_args = client.update_card.call_args
        update_fields = call_args[0][1]
        # Should have idLabels but NOT desc (since description didn't change)
        assert "idLabels" in update_fields
        assert "desc" not in update_fields


class TestRepullFailureSurfaced:
    def test_repull_failure_appears_in_errors(self, tmp_path: Path) -> None:
        """Re-pull failure after push must surface in result.errors."""
        cache_dir, config = setup_cache(tmp_path)

        card = Card(
            id="67abc123def4567890fedcba",
            board_id="board1",
            list_id="list1",
            title="Card",
            description="Desc",
        )
        write_card(card, "clean", cache_dir)
        card.title = "Modified"
        write_card(card, "working", cache_dir)

        client = MagicMock()
        client.update_card.return_value = card
        # Make re-pull fail
        client.get_card.side_effect = RuntimeError("API timeout")

        changeset, result = push_changes(config, client, cache_dir)

        assert len(result.pushed) == 1
        assert any("Re-pull failed" in e for e in result.errors)


class TestInstanceOwnedApiStats:
    """F-001: API stats are per-client instance, not module-global."""

    def test_fresh_client_starts_at_zero(self) -> None:
        """New TrelloClient starts with zero stats."""
        from trache.api.auth import TrelloAuth
        from trache.api.client import TrelloClient

        auth = MagicMock(spec=TrelloAuth)
        auth.query_params = {"key": "k", "token": "t"}
        client = TrelloClient(auth)
        stats = client.get_stats()
        assert stats["calls"] == 0
        assert stats["total_ms"] == 0.0

    def test_track_call_increments_correctly(self) -> None:
        """_track_call accumulates count and latency."""
        from trache.api.auth import TrelloAuth
        from trache.api.client import TrelloClient

        auth = MagicMock(spec=TrelloAuth)
        auth.query_params = {"key": "k", "token": "t"}
        client = TrelloClient(auth)
        client._track_call(50.0)
        client._track_call(50.0)
        stats = client.get_stats()
        assert stats["calls"] == 2
        assert stats["total_ms"] == 100.0

    def test_two_clients_have_independent_counters(self) -> None:
        """Stats on client A do not affect client B."""
        from trache.api.auth import TrelloAuth
        from trache.api.client import TrelloClient

        auth = MagicMock(spec=TrelloAuth)
        auth.query_params = {"key": "k", "token": "t"}
        client_a = TrelloClient(auth)
        client_b = TrelloClient(auth)
        client_a._track_call(99.0)
        assert client_b.get_stats()["calls"] == 0
        assert client_b.get_stats()["total_ms"] == 0.0

    def test_output_api_stats_with_protocol(self, capsys) -> None:
        """OutputWriter.api_stats renders stats from a HasStats-compliant object."""
        from trache.cli._output import OutputWriter

        class StubClient:
            def get_stats(self) -> dict[str, float]:
                return {"calls": 3, "total_ms": 150.0}

        out = OutputWriter(human=True)
        out.api_stats(StubClient())
        captured = capsys.readouterr()
        assert "3 API calls" in captured.out

    def test_output_api_stats_none_is_silent(self, capsys) -> None:
        """OutputWriter.api_stats(None) produces no output."""
        from trache.cli._output import OutputWriter

        out = OutputWriter(human=True)
        out.api_stats(None)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_output_api_stats_machine_mode_json(self, capsys) -> None:
        """Machine mode: api_stats emits compact JSON to stderr with api_calls and api_ms keys."""
        import json

        from trache.cli._output import OutputWriter

        class StubClient:
            def get_stats(self) -> dict[str, float]:
                return {"calls": 5, "total_ms": 250.0}

        out = OutputWriter(human=False)
        out.api_stats(StubClient())
        captured = capsys.readouterr()
        data = json.loads(captured.err)
        assert isinstance(data["api_calls"], int)
        assert isinstance(data["api_ms"], int)
        assert data["api_calls"] == 5
        assert data["api_ms"] == 250
        assert captured.out == ""
        # Verify compact JSON (no whitespace) per machine-output contract
        assert captured.err.strip() == json.dumps(data, separators=(",", ":"))


class TestParseTrelloDateLog:
    def test_malformed_date_emits_debug_log(self, caplog):
        """F-014: unparseable date strings emit DEBUG log."""
        import logging

        from trache.api.client import _parse_trello_date

        with caplog.at_level(logging.DEBUG, logger="trache.api.client"):
            result = _parse_trello_date("not-a-date")
        assert result is None
        assert any("Failed to parse Trello date" in r.message for r in caplog.records)

    def test_empty_and_none_do_not_log(self, caplog):
        """Empty/None hit the early return before try/except — no log emitted."""
        import logging

        from trache.api.client import _parse_trello_date

        with caplog.at_level(logging.DEBUG, logger="trache.api.client"):
            assert _parse_trello_date("") is None
            assert _parse_trello_date(None) is None
        assert not any("Failed to parse" in r.message for r in caplog.records)


class TestApiTimeoutEnvVar:
    def _make_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRELLO_API_KEY", "k")
        monkeypatch.setenv("TRELLO_TOKEN", "t")
        from trache.config import TracheConfig, ensure_cache_structure

        cache_dir = tmp_path / "board"
        ensure_cache_structure(cache_dir)
        TracheConfig(board_id="board1").save(cache_dir)
        return cache_dir

    def test_default_timeout_is_60s(self, tmp_path, monkeypatch):
        """O-012: CLI default timeout is 60s when env var unset."""
        monkeypatch.delenv("TRACHE_API_TIMEOUT", raising=False)
        cache_dir = self._make_cache(tmp_path, monkeypatch)
        from trache.cli._context import get_client_and_config

        client, _ = get_client_and_config(cache_dir)
        assert client._client.timeout.connect == 60.0
        client.close()

    def test_env_var_overrides_timeout(self, tmp_path, monkeypatch):
        """O-012: TRACHE_API_TIMEOUT env var is respected."""
        monkeypatch.setenv("TRACHE_API_TIMEOUT", "90")
        cache_dir = self._make_cache(tmp_path, monkeypatch)
        from trache.cli._context import get_client_and_config

        client, _ = get_client_and_config(cache_dir)
        assert client._client.timeout.connect == 90.0
        client.close()

    def test_invalid_env_var_raises(self, tmp_path, monkeypatch):
        """O-012: Invalid TRACHE_API_TIMEOUT fails fast with ValueError."""
        monkeypatch.setenv("TRACHE_API_TIMEOUT", "banana")
        cache_dir = self._make_cache(tmp_path, monkeypatch)
        from trache.cli._context import get_client_and_config

        with pytest.raises(ValueError):
            get_client_and_config(cache_dir)
