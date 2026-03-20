"""Trello REST API client using httpx."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol, TypeVar

import httpx

from trache.api.auth import TrelloAuth
from trache.cache.models import (
    Board,
    Card,
    Checklist,
    ChecklistItem,
    Comment,
    Label,
    TrelloList,
)

BASE_URL = "https://api.trello.com/1"

T = TypeVar("T")

_MAX_RETRIES = 3
_BASE_DELAY = 1.0

logger = logging.getLogger(__name__)


class HasStats(Protocol):
    """Protocol for type-safe stats consumption."""

    def get_stats(self) -> dict[str, float]: ...


def _retry(fn: Callable[[], T], *, idempotent: bool = True) -> T:
    """Retry with exponential backoff + jitter on transient errors.

    Retries on 429, 5xx HTTP status codes, and transport errors.
    Respects Retry-After header on 429 responses.
    Max 3 attempts, 1s base delay with jitter.

    Non-idempotent calls (POST) only retry on 429 — 5xx and transport
    errors raise immediately to avoid duplicate side effects.
    """
    last_exc: BaseException | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429 or (status >= 500 and idempotent):
                last_exc = e
                if attempt < _MAX_RETRIES - 1:
                    if status == 429:
                        # Respect Retry-After header if present
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = float(retry_after) + random.uniform(0, 0.5)
                            except (ValueError, TypeError):
                                delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                        else:
                            delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    else:
                        delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.debug(
                        "Retry %d/%d after %s (status=%d, delay=%.1fs)",
                        attempt + 1, _MAX_RETRIES, e, status, delay,
                    )
                    time.sleep(delay)
                continue
            else:
                raise
        except httpx.TransportError as e:
            if not idempotent:
                raise
            last_exc = e
            if attempt < _MAX_RETRIES - 1:
                delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                logger.debug(
                    "Retry %d/%d after transport error: %s (delay=%.1fs)",
                    attempt + 1, _MAX_RETRIES, e, delay,
                )
                time.sleep(delay)

    raise last_exc  # type: ignore[misc]


class TrelloClient:
    """Typed Trello REST API client."""

    def __init__(self, auth: TrelloAuth, timeout: float = 30.0) -> None:
        self._auth = auth
        self._client = httpx.Client(base_url=BASE_URL, timeout=timeout)
        self._call_count: int = 0
        self._total_ms: float = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TrelloClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _track_call(self, elapsed_ms: float) -> None:
        """Record an API call's latency."""
        self._call_count += 1
        self._total_ms += elapsed_ms

    def get_stats(self) -> dict[str, float]:
        """Return current API call count and total latency in ms."""
        return {"calls": self._call_count, "total_ms": self._total_ms}

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        all_params = {**(params or {}), **self._auth.query_params}

        def _do() -> Any:
            t0 = time.monotonic()
            resp = self._client.get(path, params=all_params)
            self._track_call((time.monotonic() - t0) * 1000)
            resp.raise_for_status()
            return resp.json()

        return _retry(_do)

    def _put(self, path: str, data: Optional[dict] = None) -> Any:
        params = self._auth.query_params

        def _do() -> Any:
            t0 = time.monotonic()
            resp = self._client.put(path, params=params, json=data or {})
            self._track_call((time.monotonic() - t0) * 1000)
            resp.raise_for_status()
            return resp.json()

        return _retry(_do)

    def _post(self, path: str, data: Optional[dict] = None) -> Any:
        params = self._auth.query_params

        def _do() -> Any:
            t0 = time.monotonic()
            resp = self._client.post(path, params=params, json=data or {})
            self._track_call((time.monotonic() - t0) * 1000)
            resp.raise_for_status()
            return resp.json()

        return _retry(_do, idempotent=False)

    def _delete(self, path: str) -> None:
        def _do() -> None:
            t0 = time.monotonic()
            resp = self._client.delete(path, params=self._auth.query_params)
            self._track_call((time.monotonic() - t0) * 1000)
            resp.raise_for_status()

        _retry(_do)

    # --- Member ---

    def get_current_member(self) -> dict[str, str]:
        """Validate token via GET /members/me."""
        return self._get("/members/me", {"fields": "fullName,username"})

    # --- Board ---

    def get_board(self, board_id: str) -> Board:
        data = self._get(f"/boards/{board_id}", {"fields": "name,url,dateLastActivity"})
        return Board(
            id=data["id"],
            name=data["name"],
            url=data.get("url", ""),
            date_last_activity=_parse_trello_date(data.get("dateLastActivity")),
        )

    def create_board(self, name: str, default_lists: bool = False) -> Board:
        """Create a new Trello board."""
        data = self._post("/boards", {"name": name, "defaultLists": default_lists})
        return Board(id=data["id"], name=data["name"], url=data.get("url", ""))

    def close_board(self, board_id: str) -> None:
        """Archive (close) a board on Trello."""
        self._put(f"/boards/{board_id}", {"closed": True})

    def get_board_lists(self, board_id: str) -> list[TrelloList]:
        data = self._get(f"/boards/{board_id}/lists", {"filter": "open"})
        return [
            TrelloList(
                id=d["id"],
                name=d["name"],
                board_id=board_id,
                closed=d.get("closed", False),
                pos=d.get("pos", 0),
            )
            for d in data
        ]

    def get_board_labels(self, board_id: str) -> list[Label]:
        data = self._get(f"/boards/{board_id}/labels")
        return [
            Label(id=d["id"], name=d.get("name", ""), color=d.get("color"))
            for d in data
        ]

    def get_board_cards(self, board_id: str) -> list[Card]:
        data = self._get(
            f"/boards/{board_id}/cards",
            {"fields": "name,desc,idList,idBoard,labels,idMembers,closed,due,pos,dateLastActivity"},
        )
        return [self._parse_card(d) for d in data]

    def get_board_checklists(self, board_id: str) -> list[Checklist]:
        data = self._get(f"/boards/{board_id}/checklists")
        return [self._parse_checklist(d) for d in data]

    # --- Card ---

    def get_card(self, card_id: str) -> Card:
        data = self._get(
            f"/cards/{card_id}",
            {"fields": "name,desc,idList,idBoard,labels,idMembers,closed,due,pos,dateLastActivity"},
        )
        return self._parse_card(data)

    def get_card_checklists(self, card_id: str) -> list[Checklist]:
        data = self._get(f"/cards/{card_id}/checklists")
        return [self._parse_checklist(d) for d in data]

    def update_card(self, card_id: str, fields: dict[str, Any]) -> Card:
        data = self._put(f"/cards/{card_id}", fields)
        return self._parse_card(data)

    def create_card(self, list_id: str, name: str, desc: str = "") -> Card:
        data = self._post("/cards", {"idList": list_id, "name": name, "desc": desc})
        return self._parse_card(data)

    def archive_card(self, card_id: str) -> Card:
        return self.update_card(card_id, {"closed": True})

    # --- List ---

    def get_list_cards(self, list_id: str) -> list[Card]:
        data = self._get(
            f"/lists/{list_id}/cards",
            {"fields": "name,desc,idList,idBoard,labels,idMembers,closed,due,pos,dateLastActivity"},
        )
        return [self._parse_card(d) for d in data]

    def create_list(self, board_id: str, name: str, pos: str = "bottom") -> TrelloList:
        """Create a new list on a board."""
        data = self._post("/lists", {"name": name, "idBoard": board_id, "pos": pos})
        return TrelloList(
            id=data["id"],
            name=data["name"],
            board_id=board_id,
            closed=data.get("closed", False),
            pos=data.get("pos", 0),
        )

    def rename_list(self, list_id: str, name: str) -> TrelloList:
        """Rename a list."""
        data = self._put(f"/lists/{list_id}", {"name": name})
        return TrelloList(
            id=data["id"],
            name=data["name"],
            board_id=data.get("idBoard", ""),
            closed=data.get("closed", False),
            pos=data.get("pos", 0),
        )

    def archive_list(self, list_id: str) -> None:
        """Archive (close) a list."""
        self._put(f"/lists/{list_id}/closed", {"value": True})

    # --- Comments ---

    def get_card_comments(self, card_id: str) -> list[Comment]:
        data = self._get(
            f"/cards/{card_id}/actions",
            {"filter": "commentCard"},
        )
        return [
            Comment(
                id=d["id"],
                card_id=card_id,
                text=d["data"].get("text", ""),
                author=d.get("memberCreator", {}).get("fullName", ""),
                created_at=_parse_trello_date(d.get("date")),
            )
            for d in data
        ]

    def add_comment(self, card_id: str, text: str) -> Comment:
        data = self._post(f"/cards/{card_id}/actions/comments", {"text": text})
        return Comment(
            id=data["id"],
            card_id=card_id,
            text=text,
            created_at=_parse_trello_date(data.get("date")),
        )

    def update_comment(self, card_id: str, comment_id: str, text: str) -> Comment:
        """Update a comment's text."""
        data = self._put(
            f"/cards/{card_id}/actions/{comment_id}/comments",
            {"text": text},
        )
        return Comment(
            id=data["id"],
            card_id=card_id,
            text=text,
            created_at=_parse_trello_date(data.get("date")),
        )

    def delete_comment(self, card_id: str, comment_id: str) -> None:
        """Delete a comment."""
        self._delete(f"/cards/{card_id}/actions/{comment_id}/comments")

    # --- Checklist ---

    def update_checklist_item(
        self, card_id: str, check_item_id: str, state: str
    ) -> None:
        self._put(
            f"/cards/{card_id}/checkItem/{check_item_id}",
            {"state": state},
        )

    def update_checklist_item_name(
        self, card_id: str, check_item_id: str, name: str
    ) -> None:
        """Update a checklist item's name."""
        self._put(
            f"/cards/{card_id}/checkItem/{check_item_id}",
            {"name": name},
        )

    def delete_checklist_item(self, checklist_id: str, check_item_id: str) -> None:
        """Delete a checklist item."""
        self._delete(f"/checklists/{checklist_id}/checkItems/{check_item_id}")

    def add_checklist_item(self, checklist_id: str, name: str) -> ChecklistItem:
        data = self._post(f"/checklists/{checklist_id}/checkItems", {"name": name})
        return ChecklistItem(
            id=data["id"],
            name=data["name"],
            state=data.get("state", "incomplete"),
            pos=data.get("pos", 0),
        )

    def create_checklist(self, card_id: str, name: str) -> Checklist:
        """Create a new checklist on a card."""
        data = self._post("/checklists", {"idCard": card_id, "name": name})
        return self._parse_checklist(data)

    # --- Labels ---

    def create_label(self, board_id: str, name: str, color: Optional[str] = None) -> Label:
        """Create a new board label."""
        payload: dict[str, Any] = {"name": name, "idBoard": board_id}
        if color:
            payload["color"] = color
        data = self._post("/labels", payload)
        return Label(id=data["id"], name=data.get("name", ""), color=data.get("color"))

    def delete_label(self, label_id: str) -> None:
        """Delete a board label."""
        self._delete(f"/labels/{label_id}")

    # --- Parsers ---

    def _parse_card(self, data: dict) -> Card:
        card_id = data["id"]
        created_at = _card_created_at(card_id)
        labels = [
            lbl.get("name", "") or lbl.get("color", "")
            for lbl in data.get("labels", [])
        ]
        return Card(
            id=card_id,
            board_id=data.get("idBoard", ""),
            list_id=data.get("idList", ""),
            title=data.get("name", ""),
            description=data.get("desc", ""),
            created_at=created_at,
            content_modified_at=_parse_trello_date(data.get("dateLastActivity")),
            last_activity=_parse_trello_date(data.get("dateLastActivity")),
            due=_parse_trello_date(data.get("due")),
            labels=labels,
            members=data.get("idMembers", []),
            closed=data.get("closed", False),
            pos=data.get("pos", 0),
        )

    def _parse_checklist(self, data: dict) -> Checklist:
        return Checklist(
            id=data["id"],
            name=data["name"],
            card_id=data.get("idCard", ""),
            pos=data.get("pos", 0),
            items=[
                ChecklistItem(
                    id=item["id"],
                    name=item.get("name", ""),
                    state=item.get("state", "incomplete"),
                    pos=item.get("pos", 0),
                )
                for item in data.get("checkItems", [])
            ],
        )


def _parse_trello_date(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        logger.debug("Failed to parse Trello date: %r", val)
        return None


def _card_created_at(card_id: str) -> Optional[datetime]:
    """Extract creation timestamp from Trello card ID (first 8 hex chars = Unix timestamp)."""
    try:
        timestamp = int(card_id[:8], 16)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (ValueError, TypeError):
        return None
