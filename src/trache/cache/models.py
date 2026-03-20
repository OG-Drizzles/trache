"""Pydantic models for Trache cache objects."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Label(BaseModel):
    """Trello label."""

    id: str
    name: str
    color: Optional[str] = None


class ChecklistItem(BaseModel):
    """Single checklist item."""

    id: str
    name: str
    state: str = "incomplete"  # "complete" | "incomplete"
    pos: float = 0


class Checklist(BaseModel):
    """Trello checklist."""

    id: str
    name: str
    card_id: str
    items: list[ChecklistItem] = Field(default_factory=list)
    pos: float = 0

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def complete(self) -> int:
        return sum(1 for i in self.items if i.state == "complete")


class Card(BaseModel):
    """Trello card — core cache object.

    Note on ``content_modified_at``: on first pull this equals ``last_activity``
    because the Trello API only exposes ``dateLastActivity`` (which includes
    comments, moves, and member changes — not just content edits). After the
    first pull, the local ``_preserve_content_modified_at()`` heuristic diverges
    the two fields by comparing content before overwriting. See F-009.
    """

    id: str
    uid6: str = ""  # Last 6 chars of card ID (uppercase)
    board_id: str = ""
    list_id: str = ""
    title: str = ""
    description: str = ""
    created_at: Optional[datetime] = None
    content_modified_at: Optional[datetime] = None  # approximate on first pull; see docstring
    last_activity: Optional[datetime] = None
    due: Optional[datetime] = None
    labels: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)
    closed: bool = False
    dirty: bool = False
    checklists: list[Checklist] = Field(default_factory=list)
    pos: float = 0

    def model_post_init(self, __context: object) -> None:
        if not self.uid6 and self.id:
            self.uid6 = self.id[-6:].upper()


class TrelloList(BaseModel):
    """Trello list."""

    id: str
    name: str
    board_id: str = ""
    closed: bool = False
    pos: float = 0


class Board(BaseModel):
    """Trello board metadata."""

    id: str
    name: str
    url: str = ""
    date_last_activity: Optional[datetime] = None
    lists: list[TrelloList] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)


class Comment(BaseModel):
    """Trello card comment."""

    id: str
    card_id: str
    text: str
    author: str = ""
    created_at: Optional[datetime] = None
