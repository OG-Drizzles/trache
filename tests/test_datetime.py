"""Unit tests for cache/_datetime.py."""

from __future__ import annotations

from datetime import datetime, timezone

from trache.cache._datetime import fmt_dt, parse_dt


class TestFmtDt:
    def test_none(self) -> None:
        assert fmt_dt(None) is None

    def test_str_passthrough(self) -> None:
        assert fmt_dt("2026-03-10T12:00:00Z") == "2026-03-10T12:00:00Z"

    def test_utc_datetime(self) -> None:
        dt = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
        assert fmt_dt(dt) == "2026-03-10T12:00:00Z"

    def test_non_utc_normalised(self) -> None:
        from datetime import timedelta

        eastern = timezone(timedelta(hours=-5))
        dt = datetime(2026, 3, 10, 7, 0, 0, tzinfo=eastern)
        assert fmt_dt(dt) == "2026-03-10T12:00:00Z"

    def test_naive_datetime(self) -> None:
        dt = datetime(2026, 3, 10, 12, 0, 0)
        assert fmt_dt(dt) == "2026-03-10T12:00:00Z"


class TestParseDt:
    def test_none(self) -> None:
        assert parse_dt(None) is None

    def test_z_suffix(self) -> None:
        result = parse_dt("2026-03-10T12:00:00Z")
        assert result == datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)

    def test_offset(self) -> None:
        result = parse_dt("2026-03-10T12:00:00+00:00")
        assert result == datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)

    def test_fractional_seconds_stripped(self) -> None:
        result = parse_dt("2026-03-10T12:00:00.123Z")
        assert result == datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)

    def test_roundtrip(self) -> None:
        dt = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
        assert parse_dt(fmt_dt(dt)) == dt
