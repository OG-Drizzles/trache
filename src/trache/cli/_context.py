"""Central board routing for multi-board support."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

TRACHE_ROOT = Path(".trache")

_active_board_override: Optional[str] = None


def set_board_override(name: Optional[str]) -> None:
    """Set the board override (from --board flag)."""
    global _active_board_override
    _active_board_override = name


def get_active_board_name() -> str:
    """Read the active board alias from .trache/active."""
    active_file = TRACHE_ROOT / "active"
    if not active_file.exists():
        raise FileNotFoundError(
            "No active board set. Run 'trache init' or 'trache board switch <alias>'."
        )
    name = active_file.read_text().strip()
    if not name:
        raise FileNotFoundError(
            "No active board set. Run 'trache init' or 'trache board switch <alias>'."
        )
    return name


def set_active_board(name: str) -> None:
    """Write the active board alias to .trache/active."""
    TRACHE_ROOT.mkdir(parents=True, exist_ok=True)
    (TRACHE_ROOT / "active").write_text(name + "\n")


def list_board_names() -> list[str]:
    """List all board aliases under .trache/boards/."""
    boards_dir = TRACHE_ROOT / "boards"
    if not boards_dir.exists():
        return []
    return sorted(
        d.name for d in boards_dir.iterdir() if d.is_dir()
    )


def resolve_cache_dir() -> Path:
    """Resolve the cache directory for the active board.

    1. If legacy flat layout detected, auto-migrate
    2. Read override (--board flag) or active file
    3. Fuzzy match if alias not found
    4. Return .trache/boards/<alias>/
    """
    # Legacy migration check
    if not (TRACHE_ROOT / "boards").exists() and (TRACHE_ROOT / "config.json").exists():
        _migrate_legacy()

    # Determine which board to use
    if _active_board_override:
        name = _active_board_override
    else:
        name = get_active_board_name()

    boards_dir = TRACHE_ROOT / "boards"
    board_path = boards_dir / name
    if board_path.exists():
        return board_path

    # Try fuzzy match
    suggestion = _fuzzy_match(name)
    if suggestion:
        raise FileNotFoundError(
            f"Board '{name}' not found. Did you mean '{suggestion}'?"
        )
    raise FileNotFoundError(
        f"Board '{name}' not found. Available boards: {', '.join(list_board_names()) or '(none)'}"
    )


def slugify(name: str) -> str:
    """Convert a board name to a filesystem-safe alias.

    "My Work Board" → "my-work-board"
    """
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s or "default"


def _migrate_legacy() -> None:
    """Migrate flat .trache/ layout to multi-board layout."""
    config_path = TRACHE_ROOT / "config.json"
    if not config_path.exists():
        return

    # Read board name from config
    try:
        config_data = json.loads(config_path.read_text())
        board_name = config_data.get("board_name", "")
    except (json.JSONDecodeError, OSError):
        board_name = ""

    alias = slugify(board_name) if board_name else "default"
    board_dir = TRACHE_ROOT / "boards" / alias
    board_dir.mkdir(parents=True, exist_ok=True)

    # Move known contents into board directory
    items_to_move = [
        "config.json", "state.json", "indexes", "clean", "working",
    ]
    for item_name in items_to_move:
        src = TRACHE_ROOT / item_name
        if src.exists():
            dst = board_dir / item_name
            shutil.move(str(src), str(dst))

    # Set active board
    set_active_board(alias)

    print(
        f"Migrated .trache/ to multi-board layout (board: {alias})",
        file=sys.stderr,
    )


def _fuzzy_match(name: str) -> Optional[str]:
    """Find a near-match among known board aliases."""
    boards = list_board_names()
    if not boards:
        return None

    name_lower = name.lower()

    # Check prefix match
    for b in boards:
        if b.startswith(name_lower) or name_lower.startswith(b):
            return b

    # Check substring match
    for b in boards:
        if name_lower in b or b in name_lower:
            return b

    # Simple edit distance check (1 edit away)
    for b in boards:
        if _edit_distance_leq(name_lower, b, 2):
            return b

    return None


def get_client_and_config(cache_dir: Path):
    """Create an authenticated Trello client and config from a cache directory."""
    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient
    from trache.config import TracheConfig

    config = TracheConfig.load(cache_dir)
    auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
    return TrelloClient(auth), config


def _edit_distance_leq(a: str, b: str, threshold: int) -> bool:
    """Check if edit distance between a and b is <= threshold."""
    if abs(len(a) - len(b)) > threshold:
        return False
    # Simple Levenshtein
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for j in range(1, len(b) + 1):
        curr = [j] + [0] * len(a)
        for i in range(1, len(a) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[i] = min(curr[i - 1] + 1, prev[i] + 1, prev[i - 1] + cost)
        prev = curr
    return prev[len(a)] <= threshold
