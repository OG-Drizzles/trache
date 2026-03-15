"""Working copy mutations — local edits before push."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from trache.cache.db import (
    list_cards,
    read_card,
    read_labels_raw,
    resolve_card_id,
    resolve_list_id,
    write_card,
)
from trache.cache.models import Card


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
    card = read_working_card(identifier, cache_dir)
    card.title = new_title
    card.content_modified_at = _now()
    card.dirty = True
    write_card(card, "working", cache_dir)
    return card


def edit_description(identifier: str, new_desc: str, cache_dir: Path) -> Card:
    """Edit a card's description in the working copy."""
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
