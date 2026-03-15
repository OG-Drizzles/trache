"""Diff engine: compare clean snapshot vs working copy to produce changesets."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path

from trache.cache.db import (
    list_cards,
    read_checklists,
    read_labels_raw,
    resolve_list_name,
)


@dataclass
class ChecklistChange:
    """A single checklist change for a card."""

    checklist_id: str
    checklist_name: str
    change_type: str  # "state_change" | "new_item" | "removed_item" | "text_change" | "new_checklist"
    item_id: str = ""
    old_value: str = ""
    new_value: str = ""


@dataclass
class LabelChange:
    """A board-level label change."""

    label_name: str
    label_color: str | None
    change_type: str  # "created" | "deleted"
    label_id: str = ""


@dataclass
class CardChange:
    """A single card's changes."""

    card_id: str
    title: str
    change_type: str  # "modified" | "added" | "deleted"
    field_changes: dict[str, tuple[str, str]] = field(default_factory=dict)  # field: (old, new)
    checklist_changes: list[ChecklistChange] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)  # e.g. ["archived", "in Done"]


@dataclass
class Changeset:
    """Full diff between clean and working."""

    modified: list[CardChange] = field(default_factory=list)
    added: list[CardChange] = field(default_factory=list)
    deleted: list[CardChange] = field(default_factory=list)
    label_changes: list[LabelChange] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.modified and not self.added and not self.deleted and not self.label_changes

    @property
    def total_changes(self) -> int:
        return len(self.modified) + len(self.added) + len(self.deleted) + len(self.label_changes)


# Fields to compare for detecting modifications
_DIFF_FIELDS = ["title", "description", "list_id", "labels", "due", "closed"]


def fields_equal(field_name: str, old_val: object, new_val: object) -> bool:
    """Typed comparison per field."""
    if field_name == "labels":
        return sorted(old_val) == sorted(new_val)
    return old_val == new_val


def _compute_checklist_changes(
    card_id: str, cache_dir: Path
) -> list[ChecklistChange]:
    """Compare clean vs working checklists for a card."""
    clean_cls = read_checklists(card_id, "clean", cache_dir)
    working_cls = read_checklists(card_id, "working", cache_dir)

    changes: list[ChecklistChange] = []

    # Build lookup: checklist_id → {item_id → item}
    clean_items: dict[str, dict[str, dict]] = {}
    clean_cl_names: dict[str, str] = {}
    for cl in clean_cls:
        clean_cl_names[cl.id] = cl.name
        clean_items[cl.id] = {item.id: {"name": item.name, "state": item.state} for item in cl.items}

    working_items: dict[str, dict[str, dict]] = {}
    working_cl_names: dict[str, str] = {}
    for cl in working_cls:
        working_cl_names[cl.id] = cl.name
        working_items[cl.id] = {item.id: {"name": item.name, "state": item.state} for item in cl.items}

    # Compare items in each checklist
    all_cl_ids = set(clean_items.keys()) | set(working_items.keys())
    for cl_id in all_cl_ids:
        cl_name = working_cl_names.get(cl_id) or clean_cl_names.get(cl_id, cl_id)
        old_items = clean_items.get(cl_id, {})
        new_items = working_items.get(cl_id, {})

        # Detect entirely new checklists
        if cl_id not in clean_items and cl_id in working_items:
            changes.append(ChecklistChange(
                checklist_id=cl_id,
                checklist_name=cl_name,
                change_type="new_checklist",
            ))

        # Removed items
        for item_id in set(old_items) - set(new_items):
            changes.append(ChecklistChange(
                checklist_id=cl_id,
                checklist_name=cl_name,
                change_type="removed_item",
                item_id=item_id,
                old_value=old_items[item_id]["name"],
            ))

        # New items (including temp IDs)
        for item_id in set(new_items) - set(old_items):
            changes.append(ChecklistChange(
                checklist_id=cl_id,
                checklist_name=cl_name,
                change_type="new_item",
                item_id=item_id,
                new_value=new_items[item_id]["name"],
            ))

        # Changed items
        for item_id in set(old_items) & set(new_items):
            old = old_items[item_id]
            new = new_items[item_id]
            if old["state"] != new["state"]:
                changes.append(ChecklistChange(
                    checklist_id=cl_id,
                    checklist_name=cl_name,
                    change_type="state_change",
                    item_id=item_id,
                    old_value=old["state"],
                    new_value=new["state"],
                ))
            if old["name"] != new["name"]:
                changes.append(ChecklistChange(
                    checklist_id=cl_id,
                    checklist_name=cl_name,
                    change_type="text_change",
                    item_id=item_id,
                    old_value=old["name"],
                    new_value=new["name"],
                ))

    return changes


def _compute_label_changes(cache_dir: Path) -> list[LabelChange]:
    """Compare clean vs working labels to find created/deleted labels."""
    clean_labels = read_labels_raw("clean", cache_dir)
    working_labels = read_labels_raw("working", cache_dir)

    clean_by_id = {lb["id"]: lb for lb in clean_labels}
    working_by_id = {lb["id"]: lb for lb in working_labels}

    changes: list[LabelChange] = []

    # New labels (in working but not clean)
    for lb_id in set(working_by_id) - set(clean_by_id):
        lb = working_by_id[lb_id]
        changes.append(LabelChange(
            label_name=lb.get("name", ""),
            label_color=lb.get("color"),
            change_type="created",
            label_id=lb_id,
        ))

    # Deleted labels (in clean but not working)
    for lb_id in set(clean_by_id) - set(working_by_id):
        lb = clean_by_id[lb_id]
        changes.append(LabelChange(
            label_name=lb.get("name", ""),
            label_color=lb.get("color"),
            change_type="deleted",
            label_id=lb_id,
        ))

    return changes


def compute_diff(cache_dir: Path) -> Changeset:
    """Compute diff between clean and working copies."""
    clean_cards = {c.id: c for c in list_cards("clean", cache_dir)}
    working_cards = {c.id: c for c in list_cards("working", cache_dir)}

    changeset = Changeset()

    # Added cards (in working but not in clean)
    for card_id in working_cards.keys() - clean_cards.keys():
        card = working_cards[card_id]
        annotations: list[str] = []
        if card.closed:
            annotations.append("archived")
        if card.list_id:
            try:
                list_name = resolve_list_name(card.list_id, cache_dir)
                if list_name != card.list_id:  # resolved successfully
                    annotations.append(f"in {list_name}")
            except (KeyError, FileNotFoundError):
                pass
        if card.labels:
            annotations.append(f"labels: {', '.join(card.labels)}")
        changeset.added.append(CardChange(
            card_id=card_id,
            title=card.title,
            change_type="added",
            annotations=annotations,
        ))

    # Deleted cards (in clean but not in working)
    for card_id in clean_cards.keys() - working_cards.keys():
        card = clean_cards[card_id]
        changeset.deleted.append(CardChange(
            card_id=card_id,
            title=card.title,
            change_type="deleted",
        ))

    # Modified cards (in both, check for changes)
    for card_id in clean_cards.keys() & working_cards.keys():
        clean_card = clean_cards[card_id]
        working_card = working_cards[card_id]

        field_changes: dict[str, tuple[str, str]] = {}
        for f in _DIFF_FIELDS:
            old_val = getattr(clean_card, f)
            new_val = getattr(working_card, f)
            if not fields_equal(f, old_val, new_val):
                field_changes[f] = (str(old_val), str(new_val))

        # Check checklist changes
        cl_changes = _compute_checklist_changes(card_id, cache_dir)

        if field_changes or cl_changes:
            changeset.modified.append(CardChange(
                card_id=card_id,
                title=working_card.title,
                change_type="modified",
                field_changes=field_changes,
                checklist_changes=cl_changes,
            ))

    # Compute label changes
    changeset.label_changes = _compute_label_changes(cache_dir)

    # Sort all lists for deterministic output
    changeset.added.sort(key=lambda c: c.title)
    changeset.modified.sort(key=lambda c: c.title)
    changeset.deleted.sort(key=lambda c: c.title)

    return changeset


def serialise_changeset(changeset: Changeset) -> dict:
    """Convert a Changeset to a structured dict for JSON output."""

    def _serialise_card_change(c: CardChange) -> dict:
        d: dict = {"uid6": c.card_id[-6:].upper(), "title": c.title}
        if c.field_changes:
            d["field_changes"] = {
                k: {"old": old, "new": new} for k, (old, new) in c.field_changes.items()
            }
        if c.checklist_changes:
            d["checklist_changes"] = [
                {
                    "checklist": cl.checklist_name,
                    "type": cl.change_type,
                    **({"item_id": cl.item_id} if cl.item_id else {}),
                    **({"old": cl.old_value} if cl.old_value else {}),
                    **({"new": cl.new_value} if cl.new_value else {}),
                }
                for cl in c.checklist_changes
            ]
        if c.annotations:
            d["annotations"] = c.annotations
        return d

    return {
        "modified": [_serialise_card_change(c) for c in changeset.modified],
        "added": [_serialise_card_change(c) for c in changeset.added],
        "deleted": [_serialise_card_change(c) for c in changeset.deleted],
        "label_changes": [
            {"name": lc.label_name, "color": lc.label_color, "type": lc.change_type}
            for lc in changeset.label_changes
        ],
    }


def format_diff(changeset: Changeset) -> str:
    """Format a changeset as human-readable text."""
    if changeset.is_empty:
        return "No changes."

    lines: list[str] = []

    if changeset.added:
        lines.append(f"Added ({len(changeset.added)}):")
        for c in changeset.added:
            suffix = f" ({', '.join(c.annotations)})" if c.annotations else ""
            lines.append(f"  + {c.title} [{c.card_id}]{suffix}")
        lines.append("")

    if changeset.modified:
        lines.append(f"Modified ({len(changeset.modified)}):")
        for c in changeset.modified:
            lines.append(f"  ~ {c.title} [{c.card_id}]")
            for f, (old, new) in c.field_changes.items():
                if f == "description":
                    lines.append(f"    {f}:")
                    diff_lines = unified_diff(
                        old.splitlines(keepends=True),
                        new.splitlines(keepends=True),
                        fromfile="clean",
                        tofile="working",
                        lineterm="",
                    )
                    for dl in diff_lines:
                        lines.append(f"      {dl.rstrip()}")
                else:
                    old_short = _truncate(old, 60)
                    new_short = _truncate(new, 60)
                    lines.append(f"    {f}: {old_short} → {new_short}")
            for cl_change in c.checklist_changes:
                if cl_change.change_type == "new_checklist":
                    lines.append(
                        f"    checklist + [{cl_change.checklist_name}] (new)"
                    )
                elif cl_change.change_type == "state_change":
                    lines.append(
                        f"    checklist [{cl_change.checklist_name}] "
                        f"item {cl_change.item_id}: "
                        f"{cl_change.old_value} → {cl_change.new_value}"
                    )
                elif cl_change.change_type == "new_item":
                    lines.append(
                        f"    checklist [{cl_change.checklist_name}] "
                        f"+ {cl_change.new_value}"
                    )
                elif cl_change.change_type == "removed_item":
                    lines.append(
                        f"    checklist [{cl_change.checklist_name}] "
                        f"- {cl_change.old_value}"
                    )
                elif cl_change.change_type == "text_change":
                    lines.append(
                        f"    checklist [{cl_change.checklist_name}] "
                        f"item {cl_change.item_id}: "
                        f"'{cl_change.old_value}' → '{cl_change.new_value}'"
                    )
        lines.append("")

    if changeset.deleted:
        lines.append(f"Deleted ({len(changeset.deleted)}):")
        for c in changeset.deleted:
            lines.append(f"  - {c.title} [{c.card_id}]")
        lines.append("")

    if changeset.label_changes:
        created = [lc for lc in changeset.label_changes if lc.change_type == "created"]
        deleted = [lc for lc in changeset.label_changes if lc.change_type == "deleted"]
        if created:
            lines.append(f"Labels created ({len(created)}):")
            for lc in created:
                lines.append(f"  + {lc.label_name} ({lc.label_color or 'no color'})")
            lines.append("")
        if deleted:
            lines.append(f"Labels deleted ({len(deleted)}):")
            for lc in deleted:
                lines.append(f"  - {lc.label_name}")
            lines.append("")

    return "\n".join(lines)


def _truncate(s: str, max_len: int) -> str:
    s = s.replace("\n", "\\n")
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s
