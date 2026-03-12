"""Push: diff → API calls → re-pull touched objects only."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from trache.api.client import TrelloClient
from trache.cache.diff import CardChange, Changeset, compute_diff
from trache.cache.store import read_card_file
from trache.config import TracheConfig
from trache.identity import generate_block, inject_block
from trache.sync.pull import pull_card


@dataclass
class PushResult:
    """Result of a push operation."""

    pushed: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.pushed) + len(self.created) + len(self.archived)


def push_changes(
    config: TracheConfig,
    client: TrelloClient,
    cache_dir: Path,
    dry_run: bool = False,
    card_filter: Optional[str] = None,
) -> tuple[Changeset, PushResult]:
    """Push local changes to Trello.

    Returns (changeset, result). If dry_run, no API calls are made.
    """
    changeset = compute_diff(cache_dir)
    result = PushResult()

    if changeset.is_empty:
        return changeset, result

    working_dir = cache_dir / "working" / "cards"

    for change in changeset.modified:
        if card_filter and not _matches_filter(change.card_id, card_filter, cache_dir):
            continue
        if dry_run:
            result.pushed.append(change.card_id)
            continue
        try:
            _push_modified_card(change, working_dir, client, config, cache_dir)
            result.pushed.append(change.card_id)
        except Exception as e:
            result.errors.append(f"Failed to push {change.card_id}: {e}")

    for change in changeset.added:
        if card_filter and not _matches_filter(change.card_id, card_filter, cache_dir):
            continue
        if dry_run:
            result.created.append(change.card_id)
            continue
        try:
            _push_new_card(change, working_dir, client, config, cache_dir)
            result.created.append(change.card_id)
        except Exception as e:
            result.errors.append(f"Failed to create {change.card_id}: {e}")

    for change in changeset.deleted:
        if card_filter and not _matches_filter(change.card_id, card_filter, cache_dir):
            continue
        if dry_run:
            result.archived.append(change.card_id)
            continue
        try:
            client.archive_card(change.card_id)
            result.archived.append(change.card_id)
        except Exception as e:
            result.errors.append(f"Failed to archive {change.card_id}: {e}")

    # Re-pull touched objects (not in dry-run)
    if not dry_run:
        for card_id in result.pushed:
            try:
                pull_card(card_id, config, client, cache_dir)
            except Exception:
                pass  # Best effort re-pull

    return changeset, result


def _push_modified_card(
    change: CardChange,
    working_dir: Path,
    client: TrelloClient,
    config: TracheConfig,
    cache_dir: Path,
) -> None:
    """Push a modified card to Trello."""
    card = read_card_file(working_dir / f"{change.card_id}.md")

    update_fields: dict = {}

    if "title" in change.field_changes:
        update_fields["name"] = card.title

    if "description" in change.field_changes:
        # Inject identifier block into description for Trello
        block = generate_block(
            title=card.title,
            created_at=card.created_at,
            content_modified_at=card.content_modified_at,
            last_activity=card.last_activity,
            uid6=card.uid6,
        )
        update_fields["desc"] = inject_block(card.description, block)

    if "list_id" in change.field_changes:
        update_fields["idList"] = card.list_id

    if "closed" in change.field_changes:
        update_fields["closed"] = card.closed

    if "due" in change.field_changes:
        update_fields["due"] = card.due.isoformat() if card.due else None

    if update_fields:
        # Always ensure description has identifier block
        if "desc" not in update_fields:
            block = generate_block(
                title=card.title,
                created_at=card.created_at,
                content_modified_at=card.content_modified_at,
                last_activity=card.last_activity,
                uid6=card.uid6,
            )
            update_fields["desc"] = inject_block(card.description, block)

        client.update_card(change.card_id, update_fields)


def _push_new_card(
    change: CardChange,
    working_dir: Path,
    client: TrelloClient,
    config: TracheConfig,
    cache_dir: Path,
) -> None:
    """Create a new card on Trello."""
    card = read_card_file(working_dir / f"{change.card_id}.md")
    new_card = client.create_card(card.list_id, card.title, card.description)

    # Clean up temp file and re-pull the real card
    temp_file = working_dir / f"{change.card_id}.md"
    temp_file.unlink(missing_ok=True)
    clean_file = cache_dir / "clean" / "cards" / f"{change.card_id}.md"
    clean_file.unlink(missing_ok=True)

    pull_card(new_card.id, config, client, cache_dir)


def _matches_filter(card_id: str, filter_str: str, cache_dir: Path) -> bool:
    """Check if a card matches the filter (ID or UID6)."""
    if card_id == filter_str:
        return True
    if card_id.upper().endswith(filter_str.upper()):
        return True
    from trache.cache.index import resolve_card_id

    try:
        resolved = resolve_card_id(filter_str, cache_dir / "indexes")
        return resolved == card_id
    except KeyError:
        return False
