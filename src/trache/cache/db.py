"""SQLite persistence layer — replaces file-based clean/working/indexes storage."""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from trache.cache.models import Card, Checklist, ChecklistItem, Label, TrelloList

SCHEMA_VERSION = 1
DB_FILENAME = "cache.db"
MIGRATION_SENTINEL = "cache.db.migrated"

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS lists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    pos REAL DEFAULT 0,
    closed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cards (
    id TEXT NOT NULL,
    copy TEXT NOT NULL CHECK(copy IN ('clean','working')),
    uid6 TEXT NOT NULL,
    board_id TEXT DEFAULT '',
    list_id TEXT DEFAULT '',
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    created_at TEXT,
    content_modified_at TEXT,
    last_activity TEXT,
    due TEXT,
    labels TEXT DEFAULT '[]',
    members TEXT DEFAULT '[]',
    closed INTEGER DEFAULT 0,
    dirty INTEGER DEFAULT 0,
    pos REAL DEFAULT 0,
    PRIMARY KEY (id, copy)
);

CREATE INDEX IF NOT EXISTS idx_cards_uid6_copy ON cards(uid6, copy);
CREATE INDEX IF NOT EXISTS idx_cards_list_copy ON cards(list_id, copy);

CREATE TABLE IF NOT EXISTS labels (
    id TEXT NOT NULL,
    copy TEXT NOT NULL CHECK(copy IN ('clean','working')),
    name TEXT DEFAULT '',
    color TEXT,
    PRIMARY KEY (id, copy)
);

CREATE TABLE IF NOT EXISTS checklists (
    id TEXT NOT NULL,
    card_id TEXT NOT NULL,
    copy TEXT NOT NULL CHECK(copy IN ('clean','working')),
    name TEXT DEFAULT '',
    pos REAL DEFAULT 0,
    PRIMARY KEY (id, card_id, copy)
);

CREATE INDEX IF NOT EXISTS idx_checklists_card ON checklists(card_id, copy);

CREATE TABLE IF NOT EXISTS checklist_items (
    id TEXT NOT NULL,
    checklist_id TEXT NOT NULL,
    card_id TEXT NOT NULL,
    copy TEXT NOT NULL CHECK(copy IN ('clean','working')),
    name TEXT DEFAULT '',
    state TEXT DEFAULT 'incomplete',
    pos REAL DEFAULT 0,
    PRIMARY KEY (id, checklist_id, copy)
);

CREATE INDEX IF NOT EXISTS idx_items_card ON checklist_items(card_id, copy);

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def _db_path(cache_dir: Path) -> Path:
    return cache_dir / DB_FILENAME


@contextmanager
def _connect(cache_dir: Path) -> Generator[sqlite3.Connection, None, None]:
    """Open a SQLite connection with WAL mode. Commits on success, rolls back on error."""
    path = _db_path(cache_dir)
    conn = sqlite3.connect(str(path), isolation_level="DEFERRED")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Public alias for callers that need explicit transaction control.
connect = _connect


# ---------------------------------------------------------------------------
# Initialisation & migration
# ---------------------------------------------------------------------------


def init_db(cache_dir: Path) -> None:
    """Create (or verify) the SQLite database. Idempotent.

    If file-based directories exist but cache.db does not, triggers migration.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    sentinel = cache_dir / MIGRATION_SENTINEL
    has_db = _db_path(cache_dir).exists()
    has_files = (cache_dir / "clean").exists() or (cache_dir / "working").exists()

    # Crash recovery: sentinel exists → Phase 1 done, resume Phase 2 cleanup
    if sentinel.exists():
        _cleanup_file_dirs(cache_dir)
        sentinel.unlink(missing_ok=True)
        return

    # Fresh init or existing db — ensure schema
    if not has_db and has_files:
        # Migration path
        _create_schema(cache_dir)
        _migrate_files_to_db(cache_dir)
        sentinel.write_text("done\n")
        _cleanup_file_dirs(cache_dir)
        sentinel.unlink(missing_ok=True)
    else:
        _create_schema(cache_dir)


def _create_schema(cache_dir: Path) -> None:
    """Create all tables if they don't exist."""
    with _connect(cache_dir) as conn:
        conn.executescript(_SCHEMA_SQL)
        # Set schema version if not already set
        existing = conn.execute("SELECT version FROM schema_version").fetchone()
        if not existing:
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )


def _cleanup_file_dirs(cache_dir: Path) -> None:
    """Remove file-based directories after successful migration."""
    for dirname in ("clean", "working", "indexes"):
        d = cache_dir / dirname
        if d.exists():
            shutil.rmtree(d)


def _migrate_files_to_db(cache_dir: Path) -> None:
    """Read all file-based data and INSERT into SQLite in one transaction."""
    from trache.cache.store import list_card_files, read_card_file

    with _connect(cache_dir) as conn:
        # Migrate cards (clean + working)
        for copy in ("clean", "working"):
            cards_dir = cache_dir / copy / "cards"
            if not cards_dir.exists():
                continue
            for card_path in list_card_files(cards_dir):
                card = read_card_file(card_path)
                _insert_card(conn, card, copy)

        # Migrate checklists (clean + working)
        for copy in ("clean", "working"):
            cl_dir = cache_dir / copy / "checklists"
            if not cl_dir.exists():
                continue
            for cl_path in sorted(cl_dir.glob("*.json")):
                card_id = cl_path.stem
                cls = json.loads(cl_path.read_text())
                _insert_checklists_raw(conn, card_id, cls, copy)

        # Migrate labels (clean + working)
        for copy in ("clean", "working"):
            labels_path = cache_dir / copy / "labels.json"
            if labels_path.exists():
                labels_data = json.loads(labels_path.read_text())
                for lb in labels_data:
                    conn.execute(
                        "INSERT OR REPLACE INTO labels (id, copy, name, color) VALUES (?, ?, ?, ?)",
                        (lb["id"], copy, lb.get("name", ""), lb.get("color")),
                    )

        # Migrate lists from index
        index_path = cache_dir / "indexes" / "index.json"
        if index_path.exists():
            index_data = json.loads(index_path.read_text())
            lists_by_id = index_data.get("lists_by_id", {})
            for list_id, info in lists_by_id.items():
                conn.execute(
                    "INSERT OR REPLACE INTO lists (id, name, pos) VALUES (?, ?, ?)",
                    (list_id, info.get("name", ""), info.get("pos", 0)),
                )


# ---------------------------------------------------------------------------
# Card serialisation helpers
# ---------------------------------------------------------------------------


def _fmt_dt(dt) -> Optional[str]:
    """Format a datetime to ISO string, or return None/str as-is."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        from datetime import timezone

        if dt.utcoffset().total_seconds() != 0:
            dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(val: Optional[str]):
    """Parse an ISO datetime string. Returns datetime or None."""
    if val is None:
        return None
    from trache.cache.store import _parse_dt as store_parse_dt

    return store_parse_dt(val)


def _card_to_row(card: Card, copy: str) -> tuple:
    """Convert a Card model to a database row tuple."""
    return (
        card.id,
        copy,
        card.uid6 or card.id[-6:].upper(),
        card.board_id,
        card.list_id,
        card.title,
        card.description,
        _fmt_dt(card.created_at),
        _fmt_dt(card.content_modified_at),
        _fmt_dt(card.last_activity),
        _fmt_dt(card.due),
        json.dumps(card.labels),
        json.dumps(card.members),
        int(card.closed),
        int(card.dirty),
        card.pos,
    )


def _row_to_card(row: sqlite3.Row) -> Card:
    """Convert a database row to a Card model."""
    return Card(
        id=row["id"],
        uid6=row["uid6"],
        board_id=row["board_id"],
        list_id=row["list_id"],
        title=row["title"],
        description=row["description"],
        created_at=_parse_dt(row["created_at"]),
        content_modified_at=_parse_dt(row["content_modified_at"]),
        last_activity=_parse_dt(row["last_activity"]),
        due=_parse_dt(row["due"]),
        labels=json.loads(row["labels"]),
        members=json.loads(row["members"]),
        closed=bool(row["closed"]),
        dirty=bool(row["dirty"]),
        pos=row["pos"],
    )


def _insert_card(conn: sqlite3.Connection, card: Card, copy: str) -> None:
    """Insert or replace a card row."""
    conn.execute(
        """INSERT OR REPLACE INTO cards
           (id, copy, uid6, board_id, list_id, title, description,
            created_at, content_modified_at, last_activity, due,
            labels, members, closed, dirty, pos)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        _card_to_row(card, copy),
    )


def _insert_checklists_raw(
    conn: sqlite3.Connection, card_id: str, cls: list[dict], copy: str
) -> None:
    """Insert checklists from raw dict data (used during migration)."""
    for cl in cls:
        conn.execute(
            """INSERT OR REPLACE INTO checklists (id, card_id, copy, name, pos)
               VALUES (?, ?, ?, ?, ?)""",
            (cl["id"], card_id, copy, cl.get("name", ""), cl.get("pos", 0)),
        )
        for item in cl.get("items", []):
            conn.execute(
                """INSERT OR REPLACE INTO checklist_items
                   (id, checklist_id, card_id, copy, name, state, pos)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["id"],
                    cl["id"],
                    card_id,
                    copy,
                    item.get("name", ""),
                    item.get("state", "incomplete"),
                    item.get("pos", 0),
                ),
            )


# ---------------------------------------------------------------------------
# Card CRUD
# ---------------------------------------------------------------------------


def write_card(card: Card, copy: str, cache_dir: Path) -> None:
    """Write a single card to the database."""
    with _connect(cache_dir) as conn:
        _insert_card(conn, card, copy)


def write_cards_batch(cards: list[Card], copy: str, cache_dir: Path) -> None:
    """Write multiple cards in a single transaction."""
    with _connect(cache_dir) as conn:
        for card in cards:
            _insert_card(conn, card, copy)


def read_card(card_id: str, copy: str, cache_dir: Path) -> Card:
    """Read a single card by ID and copy type. Raises FileNotFoundError if missing."""
    with _connect(cache_dir) as conn:
        row = conn.execute(
            "SELECT * FROM cards WHERE id = ? AND copy = ?", (card_id, copy)
        ).fetchone()
    if row is None:
        raise FileNotFoundError(f"Card not found: {card_id} ({copy})")
    return _row_to_card(row)


def list_cards(copy: str, cache_dir: Path) -> list[Card]:
    """List all cards for a given copy type."""
    with _connect(cache_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM cards WHERE copy = ? ORDER BY pos, id", (copy,)
        ).fetchall()
    return [_row_to_card(r) for r in rows]


def delete_card(card_id: str, copy: str, cache_dir: Path) -> None:
    """Delete a card and its checklists/items from the database."""
    with _connect(cache_dir) as conn:
        conn.execute("DELETE FROM cards WHERE id = ? AND copy = ?", (card_id, copy))
        conn.execute(
            "DELETE FROM checklist_items WHERE card_id = ? AND copy = ?",
            (card_id, copy),
        )
        conn.execute(
            "DELETE FROM checklists WHERE card_id = ? AND copy = ?", (card_id, copy)
        )


def delete_stale_cards(keep_ids: set[str], copy: str, cache_dir: Path) -> None:
    """Delete all cards (and their checklists) NOT in keep_ids for the given copy."""
    with _connect(cache_dir) as conn:
        if not keep_ids:
            conn.execute("DELETE FROM cards WHERE copy = ?", (copy,))
            conn.execute("DELETE FROM checklists WHERE copy = ?", (copy,))
            conn.execute("DELETE FROM checklist_items WHERE copy = ?", (copy,))
            return

        # Build placeholders
        placeholders = ",".join("?" for _ in keep_ids)
        ids = list(keep_ids)
        conn.execute(
            f"DELETE FROM cards WHERE copy = ? AND id NOT IN ({placeholders})",
            [copy] + ids,
        )
        conn.execute(
            f"DELETE FROM checklists WHERE copy = ? AND card_id NOT IN ({placeholders})",
            [copy] + ids,
        )
        conn.execute(
            f"DELETE FROM checklist_items WHERE copy = ? AND card_id NOT IN ({placeholders})",
            [copy] + ids,
        )


# ---------------------------------------------------------------------------
# Checklists
# ---------------------------------------------------------------------------


def write_checklists(
    card_id: str, checklists: list[Checklist], copy: str, cache_dir: Path
) -> None:
    """Write checklists for a card, replacing any existing ones."""
    with _connect(cache_dir) as conn:
        # Remove old checklists + items for this card/copy
        conn.execute(
            "DELETE FROM checklist_items WHERE card_id = ? AND copy = ?",
            (card_id, copy),
        )
        conn.execute(
            "DELETE FROM checklists WHERE card_id = ? AND copy = ?", (card_id, copy)
        )
        # Insert new
        for cl in checklists:
            conn.execute(
                """INSERT INTO checklists (id, card_id, copy, name, pos)
                   VALUES (?, ?, ?, ?, ?)""",
                (cl.id, card_id, copy, cl.name, cl.pos),
            )
            for item in cl.items:
                conn.execute(
                    """INSERT INTO checklist_items
                       (id, checklist_id, card_id, copy, name, state, pos)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (item.id, cl.id, card_id, copy, item.name, item.state, item.pos),
                )


def write_checklists_raw(
    card_id: str, checklists: list[dict], copy: str, cache_dir: Path
) -> None:
    """Write checklists from raw dict data (for CLI checklist commands)."""
    with _connect(cache_dir) as conn:
        conn.execute(
            "DELETE FROM checklist_items WHERE card_id = ? AND copy = ?",
            (card_id, copy),
        )
        conn.execute(
            "DELETE FROM checklists WHERE card_id = ? AND copy = ?", (card_id, copy)
        )
        _insert_checklists_raw(conn, card_id, checklists, copy)


def read_checklists(card_id: str, copy: str, cache_dir: Path) -> list[Checklist]:
    """Read all checklists (with items) for a card."""
    with _connect(cache_dir) as conn:
        cl_rows = conn.execute(
            "SELECT * FROM checklists WHERE card_id = ? AND copy = ? ORDER BY pos, id",
            (card_id, copy),
        ).fetchall()

        result: list[Checklist] = []
        for cl_row in cl_rows:
            items_rows = conn.execute(
                """SELECT * FROM checklist_items
                   WHERE checklist_id = ? AND card_id = ? AND copy = ?
                   ORDER BY pos, id""",
                (cl_row["id"], card_id, copy),
            ).fetchall()
            items = [
                ChecklistItem(
                    id=ir["id"],
                    name=ir["name"],
                    state=ir["state"],
                    pos=ir["pos"],
                )
                for ir in items_rows
            ]
            result.append(
                Checklist(
                    id=cl_row["id"],
                    name=cl_row["name"],
                    card_id=card_id,
                    items=items,
                    pos=cl_row["pos"],
                )
            )
    return result


def read_checklists_raw(card_id: str, copy: str, cache_dir: Path) -> list[dict]:
    """Read checklists as raw dicts (for CLI checklist commands)."""
    cls = read_checklists(card_id, copy, cache_dir)
    return [
        {
            "id": cl.id,
            "name": cl.name,
            "card_id": cl.card_id,
            "pos": cl.pos,
            "items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "state": item.state,
                    "pos": item.pos,
                }
                for item in cl.items
            ],
        }
        for cl in cls
    ]


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def write_labels(labels: list[Label], copy: str, cache_dir: Path) -> None:
    """Write board labels for a copy, replacing existing."""
    with _connect(cache_dir) as conn:
        conn.execute("DELETE FROM labels WHERE copy = ?", (copy,))
        for lb in labels:
            conn.execute(
                "INSERT INTO labels (id, copy, name, color) VALUES (?, ?, ?, ?)",
                (lb.id, copy, lb.name, lb.color),
            )


def write_labels_raw(labels_data: list[dict], copy: str, cache_dir: Path) -> None:
    """Write board labels from raw dict data."""
    with _connect(cache_dir) as conn:
        conn.execute("DELETE FROM labels WHERE copy = ?", (copy,))
        for lb in labels_data:
            conn.execute(
                "INSERT INTO labels (id, copy, name, color) VALUES (?, ?, ?, ?)",
                (lb["id"], copy, lb.get("name", ""), lb.get("color")),
            )


def read_labels(copy: str, cache_dir: Path) -> list[Label]:
    """Read all labels for a copy."""
    with _connect(cache_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM labels WHERE copy = ? ORDER BY name, id", (copy,)
        ).fetchall()
    return [Label(id=r["id"], name=r["name"], color=r["color"]) for r in rows]


def read_labels_raw(copy: str, cache_dir: Path) -> list[dict]:
    """Read labels as raw dicts."""
    labels = read_labels(copy, cache_dir)
    return [{"id": lb.id, "name": lb.name, "color": lb.color} for lb in labels]


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def write_lists(lists: list[TrelloList], cache_dir: Path) -> None:
    """Write board lists, replacing existing."""
    with _connect(cache_dir) as conn:
        conn.execute("DELETE FROM lists")
        for lst in lists:
            conn.execute(
                "INSERT INTO lists (id, name, pos, closed) VALUES (?, ?, ?, ?)",
                (lst.id, lst.name, lst.pos, int(lst.closed)),
            )


def read_lists(cache_dir: Path) -> dict[str, dict]:
    """Read all lists as a dict keyed by list ID (matches old index format)."""
    with _connect(cache_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM lists ORDER BY pos, id"
        ).fetchall()
    return {r["id"]: {"name": r["name"], "pos": r["pos"]} for r in rows}


def add_list(list_id: str, name: str, pos: float, cache_dir: Path) -> None:
    """Add or update a single list."""
    with _connect(cache_dir) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO lists (id, name, pos) VALUES (?, ?, ?)",
            (list_id, name, pos),
        )


def update_list(list_id: str, name: str, pos: float, cache_dir: Path) -> None:
    """Update an existing list, preserving pos if it already exists."""
    with _connect(cache_dir) as conn:
        existing = conn.execute(
            "SELECT pos FROM lists WHERE id = ?", (list_id,)
        ).fetchone()
        actual_pos = existing["pos"] if existing else pos
        conn.execute(
            "INSERT OR REPLACE INTO lists (id, name, pos) VALUES (?, ?, ?)",
            (list_id, name, actual_pos),
        )


def remove_list(list_id: str, cache_dir: Path) -> None:
    """Remove a list from the database."""
    with _connect(cache_dir) as conn:
        conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))


# ---------------------------------------------------------------------------
# Resolution (replaces index.py lookups)
# ---------------------------------------------------------------------------


def resolve_card_id(identifier: str, cache_dir: Path) -> str:
    """Resolve a card ID or UID6 to a full card ID.

    Raises KeyError with a specific message depending on failure reason.
    """
    db_path = _db_path(cache_dir)
    if not db_path.exists():
        raise KeyError(
            "No board initialised. Run 'trache init' and 'trache pull' first."
        )

    # Full 24-char ID — return as-is
    if len(identifier) == 24:
        return identifier

    # Validate UID6 format or temp ID
    is_temp_id = "_" in identifier or "~" in identifier
    if not is_temp_id:
        upper_id = identifier.upper()
        if not (
            1 <= len(identifier) <= 6
            and all(c in "0123456789ABCDEF" for c in upper_id)
        ):
            raise KeyError(
                f"Invalid card identifier format: '{identifier}'. "
                f"Expected a 6-character hex UID6 (e.g. 'A1B2C3'), "
                f"a 24-character full card ID, or a temp ID."
            )
    else:
        upper_id = identifier.upper()

    with _connect(cache_dir) as conn:
        # Try UID6 lookup (working copy first — most common)
        row = conn.execute(
            "SELECT id FROM cards WHERE uid6 = ? AND copy = 'working' LIMIT 1",
            (upper_id,),
        ).fetchone()
        if row:
            return row["id"]

        # Try clean copy
        row = conn.execute(
            "SELECT id FROM cards WHERE uid6 = ? AND copy = 'clean' LIMIT 1",
            (upper_id,),
        ).fetchone()
        if row:
            return row["id"]

        # Try direct ID match (temp card IDs)
        row = conn.execute(
            "SELECT id FROM cards WHERE id = ? LIMIT 1", (identifier,)
        ).fetchone()
        if row:
            return row["id"]

    raise KeyError(
        f"Card '{identifier}' not found on this board. "
        f"Run 'trache card list' to see available cards, "
        f"or 'trache pull' to refresh from Trello."
    )


def resolve_list_id(identifier: str, cache_dir: Path) -> str:
    """Resolve a list ID or name to a full list ID."""
    if len(identifier) == 24:
        return identifier

    with _connect(cache_dir) as conn:
        rows = conn.execute(
            "SELECT id, name FROM lists WHERE LOWER(name) = LOWER(?)",
            (identifier,),
        ).fetchall()

    if len(rows) == 1:
        return rows[0]["id"]
    if len(rows) > 1:
        ids = ", ".join(f"{r['name']} ({r['id']})" for r in rows)
        raise KeyError(
            f"Ambiguous list name '{identifier}': matches {len(rows)} lists: {ids}. "
            f"Use the full list ID instead."
        )

    raise KeyError(f"Cannot resolve list identifier: {identifier}")


def resolve_list_name(list_id: str, cache_dir: Path) -> str:
    """Resolve a list ID to its human-readable name. Falls back to raw ID."""
    with _connect(cache_dir) as conn:
        row = conn.execute(
            "SELECT name FROM lists WHERE id = ?", (list_id,)
        ).fetchone()
    if row:
        return row["name"]
    return list_id


# ---------------------------------------------------------------------------
# Index-compatible queries (for card list display)
# ---------------------------------------------------------------------------


def load_cards_index(cache_dir: Path) -> dict[str, dict]:
    """Load a cards-by-id index dict (matches old index.json format)."""
    with _connect(cache_dir) as conn:
        rows = conn.execute(
            "SELECT id, uid6, title, list_id, content_modified_at FROM cards"
            " WHERE copy = 'working' ORDER BY pos, id"
        ).fetchall()
    return {
        r["id"]: {
            "title": r["title"],
            "list_id": r["list_id"],
            "uid6": r["uid6"],
            "modified_at": r["content_modified_at"],
        }
        for r in rows
    }


def load_uid6_index(cache_dir: Path) -> dict[str, str]:
    """Load a uid6-to-id mapping (matches old index.json cards_by_uid6)."""
    with _connect(cache_dir) as conn:
        rows = conn.execute(
            "SELECT uid6, id FROM cards WHERE copy = 'working'"
        ).fetchall()
    return {r["uid6"]: r["id"] for r in rows}


# ---------------------------------------------------------------------------
# Full snapshot (atomic board-level write)
# ---------------------------------------------------------------------------


def write_full_snapshot(
    cards: list[Card],
    checklists: list[Checklist],
    lists: list[TrelloList],
    labels: list[Label],
    cache_dir: Path,
) -> None:
    """Atomic full-board write: replaces all clean and working data in one transaction."""
    # Group checklists by card
    cls_by_card: dict[str, list[Checklist]] = {}
    for cl in checklists:
        cls_by_card.setdefault(cl.card_id, []).append(cl)

    with _connect(cache_dir) as conn:
        # Clear all existing data for both copies
        for table in ("cards", "checklists", "checklist_items", "labels"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM lists")

        # Write lists
        for lst in lists:
            conn.execute(
                "INSERT INTO lists (id, name, pos, closed) VALUES (?, ?, ?, ?)",
                (lst.id, lst.name, lst.pos, int(lst.closed)),
            )

        # Write labels (both copies)
        for copy in ("clean", "working"):
            for lb in labels:
                conn.execute(
                    "INSERT INTO labels (id, copy, name, color) VALUES (?, ?, ?, ?)",
                    (lb.id, copy, lb.name, lb.color),
                )

        # Write cards + checklists (both copies)
        for copy in ("clean", "working"):
            for card in cards:
                _insert_card(conn, card, copy)
                card_cls = cls_by_card.get(card.id, [])
                for cl in card_cls:
                    conn.execute(
                        """INSERT INTO checklists (id, card_id, copy, name, pos)
                           VALUES (?, ?, ?, ?, ?)""",
                        (cl.id, card.id, copy, cl.name, cl.pos),
                    )
                    for item in cl.items:
                        conn.execute(
                            """INSERT INTO checklist_items
                               (id, checklist_id, card_id, copy, name, state, pos)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (
                                item.id,
                                cl.id,
                                card.id,
                                copy,
                                item.name,
                                item.state,
                                item.pos,
                            ),
                        )


# ---------------------------------------------------------------------------
# Atomic card-pull write (clean + working in one transaction)
# ---------------------------------------------------------------------------


def write_card_pull(
    card: Card,
    checklists: list[Checklist],
    cache_dir: Path,
    *,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Write a card + checklists to both clean and working in a single transaction.

    If *conn* is provided, uses the caller's transaction (no independent commit).
    If *conn* is None, opens its own connection via ``connect()``.
    """
    if conn is not None:
        _write_card_pull_inner(conn, card, checklists)
    else:
        with _connect(cache_dir) as own_conn:
            _write_card_pull_inner(own_conn, card, checklists)


def _write_card_pull_inner(
    conn: sqlite3.Connection,
    card: Card,
    checklists: list[Checklist],
) -> None:
    """Core logic: insert card + checklists into both copies within *conn*."""
    card_id = card.id
    for copy in ("clean", "working"):
        _insert_card(conn, card, copy)
        # Remove old checklists + items, then insert new
        conn.execute(
            "DELETE FROM checklist_items WHERE card_id = ? AND copy = ?",
            (card_id, copy),
        )
        conn.execute(
            "DELETE FROM checklists WHERE card_id = ? AND copy = ?",
            (card_id, copy),
        )
        for cl in checklists:
            conn.execute(
                """INSERT INTO checklists (id, card_id, copy, name, pos)
                   VALUES (?, ?, ?, ?, ?)""",
                (cl.id, card_id, copy, cl.name, cl.pos),
            )
            for item in cl.items:
                conn.execute(
                    """INSERT INTO checklist_items
                       (id, checklist_id, card_id, copy, name, state, pos)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (item.id, cl.id, card_id, copy, item.name, item.state, item.pos),
                )
