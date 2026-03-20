"""Push: diff → API calls → re-pull touched objects only."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from trache.api.client import TrelloClient
from trache.cache.db import (
    delete_card,
    read_card,
    read_checklists_raw,
    read_labels_raw,
    resolve_card_id,
    write_labels_raw,
)
from trache.cache.diff import CardChange, Changeset, ChecklistChange, LabelChange, compute_diff
from trache.cache.working import TRELLO_MAX_DESCRIPTION, TRELLO_MAX_TITLE
from trache.config import TracheConfig
from trache.identity import generate_block, inject_block
from trache.sync.pull import pull_card


@dataclass
class PushEntry:
    """A single pushed card with metadata for display."""

    card_id: str
    title: str
    uid6: str
    change_type: str  # "modified" | "created" | "archived"
    fields: list[str] = field(default_factory=list)  # changed field names
    old_uid6: str = ""  # temp UID6 before push (for created cards)
    also_archived: bool = False  # created card that was also archived


@dataclass
class PushResult:
    """Result of a push operation."""

    pushed: list[PushEntry] = field(default_factory=list)
    created: list[PushEntry] = field(default_factory=list)
    archived: list[PushEntry] = field(default_factory=list)
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
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> tuple[Changeset, PushResult]:
    """Push local changes to Trello."""
    changeset = compute_diff(cache_dir)
    result = PushResult()

    # Resolve card filter once up front
    resolved_filter: str | None = None
    if card_filter:
        try:
            resolved_filter = resolve_card_id(card_filter, cache_dir)
        except KeyError:
            raise KeyError(f"Cannot resolve card identifier: {card_filter}")

    if changeset.is_empty:
        return changeset, result

    # Collect changes, applying the resolved filter
    all_changes: list[tuple[str, CardChange]] = []
    for change in changeset.modified:
        if resolved_filter and change.card_id != resolved_filter:
            continue
        all_changes.append(("modified", change))
    for change in changeset.added:
        if resolved_filter and change.card_id != resolved_filter:
            continue
        all_changes.append(("added", change))
    for change in changeset.deleted:
        if resolved_filter and change.card_id != resolved_filter:
            continue
        all_changes.append(("deleted", change))

    # Push label creates before card changes
    labels_data = read_labels_raw("working", cache_dir)
    if not dry_run and not card_filter:
        _push_label_creates(
            changeset.label_changes, client, config, cache_dir, result,
            labels_data=labels_data,
        )

    total = len(all_changes)

    for idx, (kind, change) in enumerate(all_changes, 1):
        uid6 = change.card_id[-6:].upper()

        if kind == "modified":
            entry = PushEntry(
                card_id=change.card_id,
                title=change.title,
                uid6=uid6,
                change_type="modified",
                fields=list(change.field_changes.keys()),
            )
            if dry_run:
                result.pushed.append(entry)
                continue
            if on_progress:
                on_progress(idx, total, f"Updating {change.title} [{uid6}]")
            try:
                _push_modified_card(change, client, config, cache_dir)
                result.pushed.append(entry)
            except Exception as e:
                result.errors.append(f"Failed to push {change.card_id}: {e}")

        elif kind == "added":
            if dry_run:
                entry = PushEntry(
                    card_id=change.card_id,
                    title=change.title,
                    uid6=uid6,
                    change_type="created",
                    old_uid6=uid6,
                )
                result.created.append(entry)
                continue
            if on_progress:
                on_progress(idx, total, f"Creating {change.title} [{uid6}]")
            try:
                create_result = _push_new_card(
                    change, client, config, cache_dir
                )
                result.created.append(create_result)
            except Exception as e:
                result.errors.append(f"Failed to create {change.card_id}: {e}")

        elif kind == "deleted":
            entry = PushEntry(
                card_id=change.card_id,
                title=change.title,
                uid6=uid6,
                change_type="archived",
            )
            if dry_run:
                result.archived.append(entry)
                continue
            if on_progress:
                on_progress(idx, total, f"Archiving {change.title} [{uid6}]")
            try:
                client.archive_card(change.card_id)
                # Clean up local state: remove from both clean and working
                delete_card(change.card_id, "clean", cache_dir)
                delete_card(change.card_id, "working", cache_dir)
                result.archived.append(entry)
            except Exception as e:
                result.errors.append(f"Failed to archive {change.card_id}: {e}")

    # Push label deletes after card changes
    if not dry_run and not card_filter:
        _push_label_deletes(changeset.label_changes, client, result)

    # Re-pull touched objects (not in dry-run)
    if not dry_run:
        for entry in result.pushed:
            try:
                pull_card(
                    entry.card_id, config, client, cache_dir,
                    force=True, _skip_dirty_check=True,
                )
            except Exception as e:
                result.errors.append(f"Re-pull failed for {entry.card_id}: {e}")

    return changeset, result


def _push_modified_card(
    change: CardChange,
    client: TrelloClient,
    config: TracheConfig,
    cache_dir: Path,
) -> None:
    """Push a modified card to Trello."""
    card = read_card(change.card_id, "working", cache_dir)
    _push_validate_title(card.title)

    update_fields: dict = {}

    if "title" in change.field_changes:
        update_fields["name"] = card.title

    if "description" in change.field_changes:
        block = generate_block(
            title=card.title,
            created_at=card.created_at,
            content_modified_at=card.content_modified_at,
            last_activity=card.last_activity,
            uid6=card.uid6,
        )
        desc_rendered = inject_block(card.description, block)
        _validate_rendered_description(desc_rendered, card.title, len(card.description))
        update_fields["desc"] = desc_rendered

    if "list_id" in change.field_changes:
        update_fields["idList"] = card.list_id

    if "closed" in change.field_changes:
        update_fields["closed"] = card.closed

    if "due" in change.field_changes:
        update_fields["due"] = card.due.isoformat() if card.due else None

    if "labels" in change.field_changes:
        label_ids = _resolve_label_ids(card.labels, cache_dir)
        update_fields["idLabels"] = ",".join(label_ids)

    if update_fields:
        # Only inject description if the rendered output actually changed
        if "desc" not in update_fields:
            block = generate_block(
                title=card.title,
                created_at=card.created_at,
                content_modified_at=card.content_modified_at,
                last_activity=card.last_activity,
                uid6=card.uid6,
            )
            new_rendered = inject_block(card.description, block)
            _validate_rendered_description(new_rendered, card.title, len(card.description))

            clean_card = read_card(change.card_id, "clean", cache_dir)
            clean_block = generate_block(
                title=clean_card.title,
                created_at=clean_card.created_at,
                content_modified_at=clean_card.content_modified_at,
                last_activity=clean_card.last_activity,
                uid6=clean_card.uid6,
            )
            old_rendered = inject_block(clean_card.description, clean_block)

            if new_rendered != old_rendered:
                update_fields["desc"] = new_rendered

        client.update_card(change.card_id, update_fields)

    # Push checklist changes
    if change.checklist_changes:
        _push_checklist_changes(change.card_id, change.checklist_changes, client, cache_dir)


def _push_new_card(
    change: CardChange,
    client: TrelloClient,
    config: TracheConfig,
    cache_dir: Path,
) -> PushEntry:
    """Create a new card on Trello."""
    card = read_card(change.card_id, "working", cache_dir)
    _push_validate_title(card.title)

    # Inject identifier block
    block = generate_block(
        title=card.title,
        created_at=card.created_at,
        content_modified_at=card.content_modified_at,
        last_activity=card.last_activity,
        uid6=card.uid6,
    )
    desc_with_block = inject_block(card.description, block)
    _validate_rendered_description(desc_with_block, card.title, len(card.description))

    new_card = client.create_card(card.list_id, card.title, desc_with_block)

    # Fix identifier block with real UID6
    real_uid6 = new_card.id[-6:].upper()
    corrected_block = generate_block(
        title=card.title,
        created_at=card.created_at,
        content_modified_at=card.content_modified_at,
        last_activity=card.last_activity,
        uid6=real_uid6,
    )
    corrected_desc = inject_block(card.description, corrected_block)
    client.update_card(new_card.id, {"desc": corrected_desc})

    # Push checklists for the new card
    cl_data_list = read_checklists_raw(change.card_id, "working", cache_dir)
    for cl_data in cl_data_list:
        new_cl = client.create_checklist(new_card.id, cl_data["name"])
        for item in cl_data.get("items", []):
            new_item = client.add_checklist_item(new_cl.id, item["name"])
            if item.get("state") == "complete":
                client.update_checklist_item(new_card.id, new_item.id, "complete")

    # Archive on Trello if the card was archived locally
    was_archived = card.closed
    if was_archived:
        client.archive_card(new_card.id)

    # Clean up temp card from db
    delete_card(change.card_id, "working", cache_dir)
    delete_card(change.card_id, "clean", cache_dir)

    # Re-pull the real card to reconcile
    pull_card(new_card.id, config, client, cache_dir, force=True)

    old_uid6 = change.card_id[-6:].upper()
    return PushEntry(
        card_id=new_card.id,
        title=card.title,
        uid6=real_uid6,
        change_type="created",
        old_uid6=old_uid6,
        also_archived=was_archived,
    )


def _push_checklist_changes(
    card_id: str,
    changes: list[ChecklistChange],
    client: TrelloClient,
    cache_dir: Path,
) -> None:
    """Push checklist changes to Trello API."""
    temp_to_real: dict[str, str] = {}

    for cl_change in changes:
        if cl_change.change_type == "new_checklist":
            new_cl = client.create_checklist(card_id, cl_change.checklist_name)
            temp_to_real[cl_change.checklist_id] = new_cl.id
        elif cl_change.change_type == "state_change":
            client.update_checklist_item(card_id, cl_change.item_id, cl_change.new_value)
        elif cl_change.change_type == "new_item":
            cl_id = temp_to_real.get(cl_change.checklist_id, cl_change.checklist_id)
            client.add_checklist_item(cl_id, cl_change.new_value)
        elif cl_change.change_type == "removed_item":
            client.delete_checklist_item(cl_change.checklist_id, cl_change.item_id)
        elif cl_change.change_type == "text_change":
            client.update_checklist_item_name(card_id, cl_change.item_id, cl_change.new_value)


def _push_label_creates(
    label_changes: list[LabelChange],
    client: TrelloClient,
    config: TracheConfig,
    cache_dir: Path,
    result: PushResult,
    *,
    labels_data: list[dict] | None = None,
) -> None:
    """Push label creates to Trello API. Updates working labels with real IDs."""
    creates = [lc for lc in label_changes if lc.change_type == "created"]
    if not creates:
        return

    if labels_data is None:
        labels_data = read_labels_raw("working", cache_dir)

    for lc in creates:
        try:
            new_label = client.create_label(config.board_id, lc.label_name, lc.label_color)
            for lb in labels_data:
                if lb["id"] == lc.label_id:
                    lb["id"] = new_label.id
                    break
        except Exception as e:
            result.errors.append(f"Failed to create label '{lc.label_name}': {e}")

    write_labels_raw(labels_data, "working", cache_dir)


def _push_label_deletes(
    label_changes: list[LabelChange],
    client: TrelloClient,
    result: PushResult,
) -> None:
    """Push label deletes to Trello API."""
    deletes = [lc for lc in label_changes if lc.change_type == "deleted"]
    for lc in deletes:
        try:
            client.delete_label(lc.label_id)
        except Exception as e:
            result.errors.append(f"Failed to delete label '{lc.label_name}': {e}")


def _resolve_label_ids(label_names: list[str], cache_dir: Path) -> list[str]:
    """Resolve label names to Trello IDs."""
    labels_data = read_labels_raw("working", cache_dir)
    if not labels_data:
        raise ValueError(
            "Cannot push labels: no labels in cache. Run 'trache pull' first."
        )

    name_to_id: dict[str, str] = {}
    color_to_ids: dict[str, list[str]] = {}
    for lb in labels_data:
        if lb.get("name"):
            name_to_id[lb["name"]] = lb["id"]
        if lb.get("color"):
            color_to_ids.setdefault(lb["color"], []).append(lb["id"])

    resolved: list[str] = []
    for label in label_names:
        if label in name_to_id:
            resolved.append(name_to_id[label])
        elif label in color_to_ids:
            ids = color_to_ids[label]
            if len(ids) == 1:
                resolved.append(ids[0])
            else:
                raise ValueError(
                    f"Ambiguous label '{label}': color matches {len(ids)} labels. "
                    f"Use label names instead of colours."
                )
        else:
            raise ValueError(
                f"Cannot resolve label '{label}' to a Trello label ID. "
                f"Known labels: {list(name_to_id.keys())}. "
                f"Run 'trache pull' to refresh label data."
            )
    return resolved


def _push_validate_title(title: str) -> None:
    """Belt-and-suspenders title check at push time."""
    if len(title) > TRELLO_MAX_TITLE:
        raise ValueError(
            f"Title '{title[:40]}...' is {len(title)} chars, "
            f"exceeds Trello limit of {TRELLO_MAX_TITLE}."
        )


def _validate_rendered_description(
    rendered: str, card_title: str, raw_len: int = 0
) -> None:
    """Raise ValueError if rendered description (with identity block) exceeds Trello limit."""
    length = len(rendered)
    if length > TRELLO_MAX_DESCRIPTION:
        excess = length - TRELLO_MAX_DESCRIPTION
        block_len = length - raw_len if raw_len else 0
        block_note = (
            f" The identity block added {block_len} chars to the "
            f"{raw_len}-char raw description."
            if block_len > 0
            else ""
        )
        raise ValueError(
            f"Rendered description for '{card_title}' exceeds Trello's "
            f"{TRELLO_MAX_DESCRIPTION}-char limit ({length} chars).{block_note} "
            f"Shorten the description by {excess} chars."
        )


