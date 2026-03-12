"""Diff engine: compare clean snapshot vs working copy to produce changesets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from trache.cache.store import list_card_files, read_card_file


@dataclass
class CardChange:
    """A single card's changes."""

    card_id: str
    title: str
    change_type: str  # "modified" | "added" | "deleted"
    field_changes: dict[str, tuple[str, str]] = field(default_factory=dict)  # field: (old, new)


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


def compute_diff(cache_dir: Path) -> Changeset:
    """Compute diff between clean and working directories."""
    clean_dir = cache_dir / "clean" / "cards"
    working_dir = cache_dir / "working" / "cards"

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
            old_val = str(getattr(clean_card, f))
            new_val = str(getattr(working_card, f))
            if old_val != new_val:
                field_changes[f] = (old_val, new_val)

        if field_changes:
            changeset.modified.append(CardChange(
                card_id=card_id,
                title=working_card.title,
                change_type="modified",
                field_changes=field_changes,
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
