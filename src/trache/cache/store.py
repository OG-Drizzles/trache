"""Read/write card markdown files with YAML frontmatter."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from trache.cache.models import Card


def _fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if val is None:
        return None
    return datetime.fromisoformat(val.replace("Z", "+00:00"))


def card_to_markdown(card: Card) -> str:
    """Serialize a Card to markdown with YAML frontmatter."""
    frontmatter = {
        "card_id": card.id,
        "uid6": card.uid6,
        "board_id": card.board_id,
        "list_id": card.list_id,
        "title": card.title,
        "created_at": _fmt_dt(card.created_at),
        "content_modified_at": _fmt_dt(card.content_modified_at),
        "last_activity": _fmt_dt(card.last_activity),
        "due": _fmt_dt(card.due),
        "labels": card.labels,
        "members": card.members,
        "closed": card.closed,
        "dirty": card.dirty,
    }

    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).rstrip()

    from trache.identity import _fmt_date

    identity_lines = [
        "[TRACHE CARD IDENTITY]",
        f"- **Card Name:** {card.title}",
        f"- **Created Date:** {_fmt_date(card.created_at)}",
        f"- **Modified Date:** {_fmt_date(card.content_modified_at)}",
        f"- **Last Activity:** {_fmt_date(card.last_activity)}",
        f"- **Unique ID:** {card.uid6}",
    ]

    sections = [
        f"---\n{fm_str}\n---", "", "\n".join(identity_lines),
        "", "---", "", "# Description", "",
    ]

    if card.description:
        sections.append(card.description)
    else:
        sections.append("")

    if card.checklists:
        sections.append("")
        sections.append("# Checklist Summary")
        sections.append("")
        for cl in card.checklists:
            sections.append(f"- {cl.name}: {cl.complete}/{cl.total} complete")

    return "\n".join(sections) + "\n"


def markdown_to_card(content: str) -> Card:
    """Deserialize a card from markdown with YAML frontmatter."""
    if not content.startswith("---"):
        raise ValueError("Card markdown must start with YAML frontmatter (---)")

    # Split frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Invalid frontmatter: could not find closing ---")

    fm_raw = parts[1].strip()
    body = parts[2]

    fm = yaml.safe_load(fm_raw)
    if not isinstance(fm, dict):
        raise ValueError("Invalid frontmatter: expected YAML mapping")

    # Extract description from body — skip identity block and checklist summary
    description = _extract_description(body)

    return Card(
        id=fm["card_id"],
        uid6=fm.get("uid6", ""),
        board_id=fm.get("board_id", ""),
        list_id=fm.get("list_id", ""),
        title=fm.get("title", ""),
        description=description,
        created_at=_parse_dt(fm.get("created_at")),
        content_modified_at=_parse_dt(fm.get("content_modified_at")),
        last_activity=_parse_dt(fm.get("last_activity")),
        due=_parse_dt(fm.get("due")),
        labels=fm.get("labels", []),
        members=fm.get("members", []),
        closed=fm.get("closed", False),
        dirty=fm.get("dirty", False),
    )


def _extract_description(body: str) -> str:
    """Extract just the description from the body, skipping identity block and checklist summary."""
    lines = body.split("\n")
    in_description = False
    desc_lines: list[str] = []

    for line in lines:
        if line.strip() == "# Description":
            in_description = True
            continue
        if in_description:
            if line.strip() == "# Checklist Summary":
                break
            desc_lines.append(line)

    # Strip leading/trailing blank lines
    result = "\n".join(desc_lines).strip()
    return result


def write_card_file(card: Card, directory: Path) -> Path:
    """Write a card to a .md file in the given directory."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{card.id}.md"
    path.write_text(card_to_markdown(card))
    return path


def read_card_file(path: Path) -> Card:
    """Read a card from a .md file."""
    if not path.exists():
        raise FileNotFoundError(f"Card file not found: {path}")
    return markdown_to_card(path.read_text())


def list_card_files(directory: Path) -> list[Path]:
    """List all card .md files in a directory."""
    if not directory.exists():
        return []
    return sorted(directory.glob("*.md"))
