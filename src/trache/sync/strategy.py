"""Conflict resolution strategy.

For MVP: local-wins. The working copy is always authoritative.
Pull overwrites both clean and working (user must push before pull to preserve changes).
"""

from __future__ import annotations

from enum import Enum


class ConflictStrategy(str, Enum):
    """Conflict resolution strategies."""

    LOCAL_WINS = "local_wins"


# Default strategy — local always wins
DEFAULT_STRATEGY = ConflictStrategy.LOCAL_WINS
