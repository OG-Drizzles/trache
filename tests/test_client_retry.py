"""O-001: Comprehensive retry behaviour tests for TrelloClient.

Uses httpx.MockTransport to simulate server responses without network I/O.
All tests mock time.sleep to avoid real delays.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from trache.api.auth import TrelloAuth
from trache.api.client import TrelloClient


def _make_client(handler) -> TrelloClient:
    auth = MagicMock(spec=TrelloAuth)
    auth.query_params = {"key": "k", "token": "t"}
    client = TrelloClient(auth)
    client._client = httpx.Client(
        base_url="https://api.trello.com/1",
        transport=httpx.MockTransport(handler),
    )
    return client


class TestRetry429WithRetryAfter:
    @patch("trache.api.client.time.sleep")
    def test_respects_retry_after_header(self, mock_sleep):
        """429 + Retry-After header → respects value, retries, succeeds."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "2"})
            return httpx.Response(200, json={"ok": True})

        client = _make_client(handler)
        result = client._get("/test")
        assert result == {"ok": True}
        assert len(calls) == 2
        # Sleep should have been called with ~2s + jitter
        assert mock_sleep.call_count == 1
        delay = mock_sleep.call_args[0][0]
        assert 2.0 <= delay <= 2.5


class TestRetry429WithoutRetryAfter:
    @patch("trache.api.client.time.sleep")
    def test_exponential_backoff_on_429_no_header(self, mock_sleep):
        """429 no header → exponential backoff, retries."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) < 3:
                return httpx.Response(429)
            return httpx.Response(200, json={"ok": True})

        client = _make_client(handler)
        result = client._get("/test")
        assert result == {"ok": True}
        assert len(calls) == 3
        assert mock_sleep.call_count == 2


class TestRetry500OnGet:
    @patch("trache.api.client.time.sleep")
    def test_get_retries_on_500(self, mock_sleep):
        """GET + 500 → retries (idempotent)."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(500)
            return httpx.Response(200, json={"ok": True})

        client = _make_client(handler)
        result = client._get("/test")
        assert result == {"ok": True}
        assert len(calls) == 2


class TestNoRetry500OnPost:
    @patch("trache.api.client.time.sleep")
    def test_post_raises_immediately_on_500(self, mock_sleep):
        """POST + 500 → raises immediately, call count = 1."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(500)

        client = _make_client(handler)
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            client._post("/test", {"data": "value"})
        assert exc_info.value.response.status_code == 500
        assert len(calls) == 1
        mock_sleep.assert_not_called()


class TestTransportErrorOnGet:
    @patch("trache.api.client.time.sleep")
    def test_get_retries_on_transport_error(self, mock_sleep):
        """GET + ConnectError → retries."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json={"ok": True})

        client = _make_client(handler)
        result = client._get("/test")
        assert result == {"ok": True}
        assert len(calls) == 2


class TestTransportErrorOnPost:
    @patch("trache.api.client.time.sleep")
    def test_post_raises_immediately_on_transport_error(self, mock_sleep):
        """POST + ConnectError → raises immediately, call count = 1."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            raise httpx.ConnectError("Connection refused")

        client = _make_client(handler)
        with pytest.raises(httpx.TransportError):
            client._post("/test", {"data": "value"})
        assert len(calls) == 1
        mock_sleep.assert_not_called()


class TestClientErrorNoRetry:
    @pytest.mark.parametrize("status_code", [400, 401, 403, 404])
    @patch("trache.api.client.time.sleep")
    def test_client_errors_raise_immediately(self, mock_sleep, status_code):
        """400/401/403/404 → raises immediately (parametrized)."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(status_code)

        client = _make_client(handler)
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            client._get("/test")
        assert exc_info.value.response.status_code == status_code
        assert len(calls) == 1
        mock_sleep.assert_not_called()


class TestMaxRetriesExhausted:
    @patch("trache.api.client.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        """3x 500 on GET → raises after _MAX_RETRIES attempts."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(500)

        client = _make_client(handler)
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            client._get("/test")
        assert exc_info.value.response.status_code == 500
        assert len(calls) == 3  # _MAX_RETRIES


class TestSuccessOnFirstAttempt:
    @patch("trache.api.client.time.sleep")
    def test_no_sleep_on_immediate_success(self, mock_sleep):
        """200 → no time.sleep called."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": "ok"})

        client = _make_client(handler)
        result = client._get("/test")
        assert result == {"data": "ok"}
        mock_sleep.assert_not_called()
