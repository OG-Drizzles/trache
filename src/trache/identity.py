"""Identifier block: generate, parse, and inject into Trello descriptions.

The identifier block is a rendered view prepended to Trello card descriptions.
It is regenerated on every pull from canonical metadata and never parsed as input.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

# Separator between identifier block and description body
BLOCK_SEPARATOR = "\n\n"

# Regex to detect and strip identifier block from Trello descriptions.
# The trailing (?:---\s*\n)* cleans up extra --- separators from a prior bug.
_BLOCK_PATTERN = re.compile(
    r"^---\s*\n# \*\*Card Identifier\*\*\n.*?^---\s*\n(?:---\s*\n)*",
    re.MULTILINE | re.DOTALL,
)


def fmt_date(dt: Optional[datetime]) -> str:
    """Format datetime as 'YYYY-MM-DD HH:MM UTC' or 'None'."""
    if dt is None:
        return "None"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def generate_block(
    title: str,
    created_at: Optional[datetime],
    content_modified_at: Optional[datetime],
    last_activity: Optional[datetime],
    uid6: str,
) -> str:
    """Generate the identifier block markdown for a Trello card description."""
    return (
        f"---\n"
        f"# **Card Identifier**\n"
        f"- **Card Name:** {title}\n"
        f"- **Created Date:** {fmt_date(created_at)}\n"
        f"- **Modified Date:** {fmt_date(content_modified_at)}\n"
        f"- **Last Activity:** {fmt_date(last_activity)}\n"
        f"- **Unique ID:** {uid6}\n"
        f"---"
    )


def inject_block(description: str, block: str) -> str:
    """Prepend identifier block to a description, replacing any existing block."""
    clean = strip_block(description)
    return block + BLOCK_SEPARATOR + clean


def strip_block(description: str) -> str:
    """Remove identifier block from a Trello description, returning the body."""
    stripped = _BLOCK_PATTERN.sub("", description).strip()
    return stripped
