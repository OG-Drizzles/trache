"""Trello REST API client using httpx."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

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


class TrelloClient:
    """Typed Trello REST API client."""

    def __init__(self, auth: TrelloAuth, timeout: float = 30.0) -> None:
        self._auth = auth
        self._client = httpx.Client(base_url=BASE_URL, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TrelloClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        all_params = {**(params or {}), **self._auth.query_params}
        resp = self._client.get(path, params=all_params)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, data: Optional[dict] = None) -> Any:
        params = self._auth.query_params
        resp = self._client.put(path, params=params, json=data or {})
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: Optional[dict] = None) -> Any:
        params = self._auth.query_params
        resp = self._client.post(path, params=params, json=data or {})
        resp.raise_for_status()
        return resp.json()

    # --- Board ---

    def get_board(self, board_id: str) -> Board:
        data = self._get(f"/boards/{board_id}", {"fields": "name,url"})
        return Board(id=data["id"], name=data["name"], url=data.get("url", ""))

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
        params = self._auth.query_params
        resp = self._client.delete(
            f"/checklists/{checklist_id}/checkItems/{check_item_id}",
            params=params,
        )
        resp.raise_for_status()

    def add_checklist_item(self, checklist_id: str, name: str) -> ChecklistItem:
        data = self._post(f"/checklists/{checklist_id}/checkItems", {"name": name})
        return ChecklistItem(
            id=data["id"],
            name=data["name"],
            state=data.get("state", "incomplete"),
            pos=data.get("pos", 0),
        )

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
        return None


def _card_created_at(card_id: str) -> Optional[datetime]:
    """Extract creation timestamp from Trello card ID (first 8 hex chars = Unix timestamp)."""
    try:
        timestamp = int(card_id[:8], 16)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (ValueError, TypeError):
        return None
