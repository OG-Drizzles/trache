"""Diff engine: compare clean snapshot vs working copy to produce changesets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from trache.cache.store import list_card_files, read_card_file


@dataclass
class ChecklistChange:
    """A single checklist change for a card."""

    checklist_id: str
    checklist_name: str
    change_type: str  # "state_change" | "new_item" | "removed_item" | "text_change"
    item_id: str = ""
    old_value: str = ""
    new_value: str = ""


@dataclass
class CardChange:
    """A single card's changes."""

    card_id: str
    title: str
    change_type: str  # "modified" | "added" | "deleted"
    field_changes: dict[str, tuple[str, str]] = field(default_factory=dict)  # field: (old, new)
    checklist_changes: list[ChecklistChange] = field(default_factory=list)


@dataclass
class Changeset:
    """Full diff between clean and working."""

    modified: list[CardChange] = field(default_factory=list)
    added: list[CardChange] = field(default_factory=list)
    deleted: list[CardChange] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.modified and not self.added and not self.deleted

    @property
    def total_changes(self) -> int:
        return len(self.modified) + len(self.added) + len(self.deleted)


# Fields to compare for detecting modifications
_DIFF_FIELDS = ["title", "description", "list_id", "labels", "due", "closed"]


def _fields_equal(field_name: str, old_val: object, new_val: object) -> bool:
    """Typed comparison per field."""
    if field_name == "labels":
        return sorted(old_val) == sorted(new_val)
    if field_name == "due":
        # Both are Optional[datetime] — direct comparison
        return old_val == new_val
    return old_val == new_val


def _compute_checklist_changes(
    card_id: str, clean_cl_dir: Path, working_cl_dir: Path
) -> list[ChecklistChange]:
    """Compare clean vs working checklist files for a card."""
    clean_path = clean_cl_dir / f"{card_id}.json"
    working_path = working_cl_dir / f"{card_id}.json"

    clean_cls = json.loads(clean_path.read_text()) if clean_path.exists() else []
    working_cls = json.loads(working_path.read_text()) if working_path.exists() else []

    changes: list[ChecklistChange] = []

    # Build lookup: checklist_id → {item_id → item}
    clean_items: dict[str, dict[str, dict]] = {}
    clean_cl_names: dict[str, str] = {}
    for cl in clean_cls:
        cl_id = cl["id"]
        clean_cl_names[cl_id] = cl["name"]
        clean_items[cl_id] = {item["id"]: item for item in cl.get("items", [])}

    working_items: dict[str, dict[str, dict]] = {}
    working_cl_names: dict[str, str] = {}
    for cl in working_cls:
        cl_id = cl["id"]
        working_cl_names[cl_id] = cl["name"]
        working_items[cl_id] = {item["id"]: item for item in cl.get("items", [])}

    # Compare items in each checklist
    all_cl_ids = set(clean_items.keys()) | set(working_items.keys())
    for cl_id in all_cl_ids:
        cl_name = working_cl_names.get(cl_id) or clean_cl_names.get(cl_id, cl_id)
        old_items = clean_items.get(cl_id, {})
        new_items = working_items.get(cl_id, {})

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


def compute_diff(cache_dir: Path) -> Changeset:
    """Compute diff between clean and working directories."""
    clean_dir = cache_dir / "clean" / "cards"
    working_dir = cache_dir / "working" / "cards"
    clean_cl_dir = cache_dir / "clean" / "checklists"
    working_cl_dir = cache_dir / "working" / "checklists"

    clean_files = {p.stem: p for p in list_card_files(clean_dir)}
    working_files = {p.stem: p for p in list_card_files(working_dir)}

    changeset = Changeset()

    # Added cards (in working but not in clean)
    for card_id in working_files.keys() - clean_files.keys():
        card = read_card_file(working_files[card_id])
        changeset.added.append(CardChange(
            card_id=card_id,
            title=card.title,
            change_type="added",
        ))

    # Deleted cards (in clean but not in working)
    for card_id in clean_files.keys() - working_files.keys():
        card = read_card_file(clean_files[card_id])
        changeset.deleted.append(CardChange(
            card_id=card_id,
            title=card.title,
            change_type="deleted",
        ))

    # Modified cards (in both, check for changes)
    for card_id in clean_files.keys() & working_files.keys():
        clean_card = read_card_file(clean_files[card_id])
        working_card = read_card_file(working_files[card_id])

        field_changes: dict[str, tuple[str, str]] = {}
        for f in _DIFF_FIELDS:
            old_val = getattr(clean_card, f)
            new_val = getattr(working_card, f)
            if not _fields_equal(f, old_val, new_val):
                field_changes[f] = (str(old_val), str(new_val))

        # Check checklist changes
        cl_changes = _compute_checklist_changes(card_id, clean_cl_dir, working_cl_dir)

        if field_changes or cl_changes:
            changeset.modified.append(CardChange(
                card_id=card_id,
                title=working_card.title,
                change_type="modified",
                field_changes=field_changes,
                checklist_changes=cl_changes,
            ))

    return changeset


def format_diff(changeset: Changeset) -> str:
    """Format a changeset as human-readable text."""
    if changeset.is_empty:
        return "No changes."

    lines: list[str] = []

    if changeset.added:
        lines.append(f"Added ({len(changeset.added)}):")
        for c in changeset.added:
            lines.append(f"  + {c.title} [{c.card_id}]")
        lines.append("")

    if changeset.modified:
        lines.append(f"Modified ({len(changeset.modified)}):")
        for c in changeset.modified:
            lines.append(f"  ~ {c.title} [{c.card_id}]")
            for f, (old, new) in c.field_changes.items():
                old_short = _truncate(old, 60)
                new_short = _truncate(new, 60)
                lines.append(f"    {f}: {old_short} → {new_short}")
            for cl_change in c.checklist_changes:
                if cl_change.change_type == "state_change":
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

    return "\n".join(lines)


def _truncate(s: str, max_len: int) -> str:
    s = s.replace("\n", "\\n")
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s
