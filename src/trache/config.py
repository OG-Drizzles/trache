"""Configuration management for .trache/config.json."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

TRACHE_ROOT = ".trache"
# Backwards compat alias
DEFAULT_CACHE_DIR = TRACHE_ROOT


class TracheConfig(BaseModel):
    """Configuration stored in .trache/config.json."""

    board_id: str
    board_name: str = ""
    api_key_env: str = "TRELLO_API_KEY"
    token_env: str = "TRELLO_TOKEN"
    cache_dir: str = DEFAULT_CACHE_DIR

    @classmethod
    def load(cls, cache_dir: Optional[Path] = None) -> TracheConfig:
        """Load config from .trache/config.json."""
        path = (cache_dir or Path(DEFAULT_CACHE_DIR)) / "config.json"
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}. Run 'trache init' first.")
        return cls.model_validate_json(path.read_text())

    def save(self, cache_dir: Optional[Path] = None) -> Path:
        """Save config to .trache/config.json."""
        from trache.cache._atomic import atomic_write

        base = cache_dir or Path(self.cache_dir)
        base.mkdir(parents=True, exist_ok=True)
        path = base / "config.json"
        atomic_write(path, self.model_dump_json(indent=2) + "\n")
        return path


class SyncState(BaseModel):
    """Sync metadata stored in .trache/state.json."""

    last_pull: Optional[str] = None
    board_last_activity: Optional[str] = None
    card_timestamps: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def load(cls, cache_dir: Optional[Path] = None) -> SyncState:
        path = (cache_dir or Path(DEFAULT_CACHE_DIR)) / "state.json"
        if not path.exists():
            return cls()
        return cls.model_validate_json(path.read_text())

    def save(self, cache_dir: Optional[Path] = None) -> Path:
        from trache.cache._atomic import atomic_write

        base = cache_dir or Path(DEFAULT_CACHE_DIR)
        base.mkdir(parents=True, exist_ok=True)
        path = base / "state.json"
        atomic_write(path, self.model_dump_json(indent=2) + "\n")
        return path



def ensure_cache_structure(cache_dir: Path) -> None:
    """Create the full cache directory structure."""
    for subdir in [
        "indexes",
        "clean/cards",
        "clean/checklists",
        "working/cards",
        "working/checklists",
    ]:
        (cache_dir / subdir).mkdir(parents=True, exist_ok=True)
