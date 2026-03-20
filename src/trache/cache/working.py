"""Working copy mutations — local edits before push."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from trache.cache.db import (
    list_cards,
    read_card,
    read_checklists_raw,
    read_labels_raw,
    resolve_card_id,
    resolve_list_id,
    write_card,
    write_checklists_raw,
)
from trache.cache.models import Card

# Trello API hard limits
TRELLO_MAX_TITLE: int = 16_384
TRELLO_MAX_DESCRIPTION: int = 16_384

# Conservative identity-block overhead budget for the working-layer pre-check.
# The actual block is ~160–200 chars + 2-char separator; 300 provides safe headroom
# without requiring the working layer to simulate the render. This is intentionally
# stricter than Trello's raw limit — the push layer performs the exact rendered-length
# check against the real 16,384-char API limit after identity block injection.
_IDENTITY_BLOCK_BUDGET: int = 300
_EFFECTIVE_DESCRIPTION_LIMIT: int = TRELLO_MAX_DESCRIPTION - _IDENTITY_BLOCK_BUDGET


class ChecklistMutator(Protocol):
    """Callback that mutates a checklists list in-place and returns a result dict."""

    def __call__(self, checklists: list[dict[str, Any]]) -> dict[str, Any]: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def read_working_card(identifier: str, cache_dir: Path) -> Card:
    """Read a card from the working copy by ID or UID6."""
    card_id = resolve_card_id(identifier, cache_dir)
    return read_card(card_id, "working", cache_dir)


def list_working_cards(cache_dir: Path) -> list[Card]:
    """Read all cards from the working copy."""
    return list_cards("working", cache_dir)


def edit_title(identifier: str, new_title: str, cache_dir: Path) -> Card:
    """Edit a card's title in the working copy."""
    _validate_title_length(new_title)
    card = read_working_card(identifier, cache_dir)
    card.title = new_title
    card.content_modified_at = _now()
    card.dirty = True
    write_card(card, "working", cache_dir)
    return card


def edit_description(identifier: str, new_desc: str, cache_dir: Path) -> Card:
    """Edit a card's description in the working copy."""
    _validate_description_length(new_desc)
    card = read_working_card(identifier, cache_dir)
    card.description = new_desc
    card.content_modified_at = _now()
    card.dirty = True
    write_card(card, "working", cache_dir)
    return card


def move_card(identifier: str, list_identifier: str, cache_dir: Path) -> Card:
    """Move a card to a different list in the working copy."""
    card = read_working_card(identifier, cache_dir)
    new_list_id = resolve_list_id(list_identifier, cache_dir)
    card.list_id = new_list_id
    card.content_modified_at = _now()
    card.dirty = True
    write_card(card, "working", cache_dir)
    return card


def create_card(
    list_identifier: str,
    title: str,
    cache_dir: Path,
    board_id: str,
    description: str = "",
) -> Card:
    """Create a new card in the working copy."""
    _validate_title_length(title)
    if description:
        _validate_description_length(description)
    list_id = resolve_list_id(list_identifier, cache_dir)

    temp_id = f"new_{uuid4().hex[:16]}t~"

    card = Card(
        id=temp_id,
        board_id=board_id,
        list_id=list_id,
        title=title,
        description=description,
        created_at=_now(),
        content_modified_at=_now(),
        last_activity=_now(),
        dirty=True,
    )
    write_card(card, "working", cache_dir)
    return card


def archive_card(identifier: str, cache_dir: Path) -> Card:
    """Archive a card in the working copy."""
    card = read_working_card(identifier, cache_dir)
    card.closed = True
    card.content_modified_at = _now()
    card.dirty = True
    write_card(card, "working", cache_dir)
    return card


def _validate_label(label_name: str, cache_dir: Path) -> None:
    """Validate that a label name exists on the board. Raises ValueError if not."""
    labels_data = read_labels_raw("working", cache_dir)
    if not labels_data:
        return  # No labels cache — skip validation (pre-pull state)

    valid_names = [lb["name"] for lb in labels_data if lb.get("name")]
    valid_colors = list({lb["color"] for lb in labels_data if lb.get("color")})

    if label_name in valid_names or label_name in valid_colors:
        return

    raise ValueError(
        f"Label '{label_name}' does not exist on this board. "
        f"Valid labels: {valid_names}. "
        f"Use `trache label list` to see all labels. "
        f"Use `trache label create` to add a new label."
    )


def _validate_title_length(title: str) -> None:
    """Raise ValueError if title exceeds Trello's character limit."""
    length = len(title)
    if length > TRELLO_MAX_TITLE:
        excess = length - TRELLO_MAX_TITLE
        raise ValueError(
            f"Title too long: {length} chars (max {TRELLO_MAX_TITLE}). "
            f"Shorten by {excess} chars."
        )


def _validate_description_length(description: str) -> None:
    """Raise ValueError if description may overflow after identity block injection."""
    length = len(description)
    if length > _EFFECTIVE_DESCRIPTION_LIMIT:
        excess = length - _EFFECTIVE_DESCRIPTION_LIMIT
        raise ValueError(
            f"Description too long: {length} chars "
            f"(max {_EFFECTIVE_DESCRIPTION_LIMIT} after identity block overhead). "
            f"Shorten by {excess} chars."
        )


def add_label(identifier: str, label_name: str, cache_dir: Path) -> tuple[Card, bool]:
    """Add a label to a card in the working copy. Idempotent."""
    _validate_label(label_name, cache_dir)
    card = read_working_card(identifier, cache_dir)
    if label_name in card.labels:
        return card, False
    card.labels.append(label_name)
    card.content_modified_at = _now()
    card.dirty = True
    write_card(card, "working", cache_dir)
    return card, True


def remove_label(identifier: str, label_name: str, cache_dir: Path) -> Card:
    """Remove a label from a card in the working copy."""
    card = read_working_card(identifier, cache_dir)
    if label_name not in card.labels:
        raise ValueError(
            f"Label '{label_name}' not found on card {card.title} [{card.uid6}]. "
            f"Current labels: {card.labels}"
        )
    card.labels.remove(label_name)
    card.content_modified_at = _now()
    card.dirty = True
    write_card(card, "working", cache_dir)
    return card


# ---------------------------------------------------------------------------
# Checklist mutations (shared by CLI checklist commands and batch)
# ---------------------------------------------------------------------------


def _checklist_update(
    identifier: str, cache_dir: Path, mutate_fn: ChecklistMutator
) -> dict[str, Any]:
    """Resolve → load → mutate → save → dirty card. Returns mutate_fn result."""
    card_id = resolve_card_id(identifier, cache_dir)
    checklists = read_checklists_raw(card_id, "working", cache_dir)
    result = mutate_fn(checklists)
    write_checklists_raw(card_id, checklists, "working", cache_dir)
    # Dirty the card
    try:
        card = read_card(card_id, "working", cache_dir)
        card.content_modified_at = _now()
        card.dirty = True
        write_card(card, "working", cache_dir)
    except FileNotFoundError:
        pass
    return result


def check_checklist_item(identifier: str, item_id: str, cache_dir: Path) -> dict:
    """Mark a checklist item complete. Idempotent. Returns {ok, item_id, state, changed}."""
    def _mutate(checklists: list[dict]) -> dict:
        for cl in checklists:
            for item in cl.get("items", []):
                if item["id"] == item_id:
                    changed = item["state"] != "complete"
                    item["state"] = "complete"
                    return {"ok": True, "item_id": item_id, "state": "complete", "changed": changed}
        raise KeyError(f"Item {item_id} not found")

    return _checklist_update(identifier, cache_dir, _mutate)


def uncheck_checklist_item(identifier: str, item_id: str, cache_dir: Path) -> dict:
    """Mark a checklist item incomplete. Idempotent. Returns {ok, item_id, state, changed}."""
    def _mutate(checklists: list[dict]) -> dict:
        for cl in checklists:
            for item in cl.get("items", []):
                if item["id"] == item_id:
                    changed = item["state"] != "incomplete"
                    item["state"] = "incomplete"
                    return {
                        "ok": True, "item_id": item_id, "state": "incomplete", "changed": changed,
                    }
        raise KeyError(f"Item {item_id} not found")

    return _checklist_update(identifier, cache_dir, _mutate)


def add_checklist_item(
    identifier: str, checklist_name: str, text: str, cache_dir: Path
) -> dict:
    """Add an item to a checklist by name. Returns {ok, item_id, text}."""
    from uuid import uuid4 as _uuid4

    def _mutate(checklists: list[dict]) -> dict:
        for cl in checklists:
            if cl["name"] == checklist_name:
                temp_id = f"temp_{_uuid4().hex[:14]}t~"
                max_pos = max((i.get("pos", 0) for i in cl.get("items", [])), default=0)
                cl.setdefault("items", []).append({
                    "id": temp_id, "name": text, "state": "incomplete", "pos": max_pos + 1024,
                })
                return {"ok": True, "item_id": temp_id, "text": text}
        raise KeyError(f"Checklist '{checklist_name}' not found")

    return _checklist_update(identifier, cache_dir, _mutate)


def remove_checklist_item(identifier: str, item_id: str, cache_dir: Path) -> dict:
    """Remove an item from a checklist. Returns {ok, item_id}."""
    def _mutate(checklists: list[dict]) -> dict:
        for cl in checklists:
            for i, item in enumerate(cl.get("items", [])):
                if item["id"] == item_id:
                    cl["items"].pop(i)
                    return {"ok": True, "item_id": item_id}
        raise KeyError(f"Item {item_id} not found")

    return _checklist_update(identifier, cache_dir, _mutate)


def create_checklist(identifier: str, name: str, cache_dir: Path) -> dict[str, Any]:
    """Create a new checklist. Raises ValueError on duplicate name."""
    from uuid import uuid4 as _uuid4

    def _mutate(checklists: list[dict[str, Any]]) -> dict[str, Any]:
        for cl in checklists:
            if cl["name"] == name:
                raise ValueError(f"Checklist '{name}' already exists on this card")
        temp_id = f"temp_{_uuid4().hex[:14]}t~"
        checklists.append({"id": temp_id, "name": name, "items": []})
        return {"ok": True, "name": name, "id": temp_id}

    return _checklist_update(identifier, cache_dir, _mutate)
