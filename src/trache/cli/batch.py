"""Batch operations: execute multiple local-first commands from stdin."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Callable

import typer

from trache.cli._output import get_output

batch_app = typer.Typer(no_args_is_help=True)

# Dispatch table: (group, subcommand) → handler function
_DISPATCH: dict[tuple[str, str], Callable] = {}


def _register_handlers() -> None:
    """Populate dispatch table with batchable command handlers."""
    if _DISPATCH:
        return  # Already registered

    from trache.cache.db import read_card, resolve_card_id, write_card
    from trache.cache.working import (
        add_label,
        archive_card,
        create_card,
        edit_description,
        edit_title,
        move_card,
        remove_label,
    )

    def _handle_edit_title(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 2:
            return {"ok": False, "error": "Usage: card edit-title <uid6> <title>"}
        card = edit_title(args[0], args[1], cache_dir)
        return {"ok": True, "uid6": card.uid6, "title": card.title}

    def _handle_edit_desc(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 2:
            return {"ok": False, "error": "Usage: card edit-desc <uid6> <desc>"}
        card = edit_description(args[0], args[1], cache_dir)
        return {"ok": True, "uid6": card.uid6, "title": card.title}

    def _handle_move(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 2:
            return {"ok": False, "error": "Usage: card move <uid6> <list>"}
        card = move_card(args[0], args[1], cache_dir)
        return {"ok": True, "uid6": card.uid6, "title": card.title}

    def _handle_create(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 2:
            return {"ok": False, "error": "Usage: card create <list> <title>"}
        desc = ""
        # Parse --desc flag
        for i, a in enumerate(args):
            if a in ("--desc", "-d") and i + 1 < len(args):
                desc = args[i + 1]
                args = args[:i] + args[i + 2:]
                break
        card = create_card(args[0], args[1], cache_dir, board_id, desc)
        return {"ok": True, "uid6": card.uid6, "title": card.title}

    def _handle_archive(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 1:
            return {"ok": False, "error": "Usage: card archive <uid6>"}
        card = archive_card(args[0], cache_dir)
        return {"ok": True, "uid6": card.uid6, "title": card.title}

    def _handle_add_label(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 2:
            return {"ok": False, "error": "Usage: card add-label <uid6> <label>"}
        card, added = add_label(args[0], args[1], cache_dir)
        return {"ok": True, "uid6": card.uid6, "title": card.title, "added": added}

    def _handle_remove_label(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 2:
            return {"ok": False, "error": "Usage: card remove-label <uid6> <label>"}
        card = remove_label(args[0], args[1], cache_dir)
        return {"ok": True, "uid6": card.uid6, "title": card.title}

    def _handle_checklist_check(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 2:
            return {"ok": False, "error": "Usage: checklist check <uid6> <item_id>"}
        from trache.cache.db import read_card as db_read_card, read_checklists_raw, resolve_card_id as db_resolve, write_card as db_write_card, write_checklists_raw
        from datetime import datetime, timezone
        card_id = db_resolve(args[0], cache_dir)
        checklists = read_checklists_raw(card_id, "working", cache_dir)
        for cl in checklists:
            for item in cl.get("items", []):
                if item["id"] == args[1]:
                    item["state"] = "complete"
                    write_checklists_raw(card_id, checklists, "working", cache_dir)
                    card = db_read_card(card_id, "working", cache_dir)
                    card.content_modified_at = datetime.now(timezone.utc)
                    card.dirty = True
                    db_write_card(card, "working", cache_dir)
                    return {"ok": True, "item_id": args[1], "state": "complete"}
        return {"ok": False, "error": f"Item {args[1]} not found"}

    def _handle_checklist_uncheck(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 2:
            return {"ok": False, "error": "Usage: checklist uncheck <uid6> <item_id>"}
        from trache.cache.db import read_card as db_read_card, read_checklists_raw, resolve_card_id as db_resolve, write_card as db_write_card, write_checklists_raw
        from datetime import datetime, timezone
        card_id = db_resolve(args[0], cache_dir)
        checklists = read_checklists_raw(card_id, "working", cache_dir)
        for cl in checklists:
            for item in cl.get("items", []):
                if item["id"] == args[1]:
                    item["state"] = "incomplete"
                    write_checklists_raw(card_id, checklists, "working", cache_dir)
                    card = db_read_card(card_id, "working", cache_dir)
                    card.content_modified_at = datetime.now(timezone.utc)
                    card.dirty = True
                    db_write_card(card, "working", cache_dir)
                    return {"ok": True, "item_id": args[1], "state": "incomplete"}
        return {"ok": False, "error": f"Item {args[1]} not found"}

    def _handle_checklist_add_item(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 3:
            return {"ok": False, "error": "Usage: checklist add-item <uid6> <checklist_name> <text>"}
        from trache.cache.db import read_card as db_read_card, read_checklists_raw, resolve_card_id as db_resolve, write_card as db_write_card, write_checklists_raw
        from datetime import datetime, timezone
        from uuid import uuid4
        card_id = db_resolve(args[0], cache_dir)
        checklists = read_checklists_raw(card_id, "working", cache_dir)
        for cl in checklists:
            if cl["name"] == args[1]:
                temp_id = f"temp_{uuid4().hex[:14]}t~"
                max_pos = max((i.get("pos", 0) for i in cl.get("items", [])), default=0)
                cl.setdefault("items", []).append({
                    "id": temp_id, "name": args[2], "state": "incomplete", "pos": max_pos + 1024,
                })
                write_checklists_raw(card_id, checklists, "working", cache_dir)
                card = db_read_card(card_id, "working", cache_dir)
                card.content_modified_at = datetime.now(timezone.utc)
                card.dirty = True
                db_write_card(card, "working", cache_dir)
                return {"ok": True, "item_id": temp_id, "text": args[2]}
        return {"ok": False, "error": f"Checklist '{args[1]}' not found"}

    def _handle_checklist_remove_item(args: list[str], cache_dir: Path, board_id: str) -> dict:
        if len(args) < 2:
            return {"ok": False, "error": "Usage: checklist remove-item <uid6> <item_id>"}
        from trache.cache.db import read_card as db_read_card, read_checklists_raw, resolve_card_id as db_resolve, write_card as db_write_card, write_checklists_raw
        from datetime import datetime, timezone
        card_id = db_resolve(args[0], cache_dir)
        checklists = read_checklists_raw(card_id, "working", cache_dir)
        for cl in checklists:
            for i, item in enumerate(cl.get("items", [])):
                if item["id"] == args[1]:
                    cl["items"].pop(i)
                    write_checklists_raw(card_id, checklists, "working", cache_dir)
                    card = db_read_card(card_id, "working", cache_dir)
                    card.content_modified_at = datetime.now(timezone.utc)
                    card.dirty = True
                    db_write_card(card, "working", cache_dir)
                    return {"ok": True, "item_id": args[1]}
        return {"ok": False, "error": f"Item {args[1]} not found"}

    _DISPATCH[("card", "edit-title")] = _handle_edit_title
    _DISPATCH[("card", "edit-desc")] = _handle_edit_desc
    _DISPATCH[("card", "move")] = _handle_move
    _DISPATCH[("card", "create")] = _handle_create
    _DISPATCH[("card", "archive")] = _handle_archive
    _DISPATCH[("card", "add-label")] = _handle_add_label
    _DISPATCH[("card", "remove-label")] = _handle_remove_label
    _DISPATCH[("checklist", "check")] = _handle_checklist_check
    _DISPATCH[("checklist", "uncheck")] = _handle_checklist_uncheck
    _DISPATCH[("checklist", "add-item")] = _handle_checklist_add_item
    _DISPATCH[("checklist", "remove-item")] = _handle_checklist_remove_item


@batch_app.command("run")
def run() -> None:
    """Execute batch commands from stdin (one per line)."""
    from trache.cli._context import resolve_cache_dir
    from trache.config import TracheConfig

    out = get_output()
    cache_dir = resolve_cache_dir()
    config = TracheConfig.load(cache_dir)
    _register_handlers()

    results: list[dict] = []
    lines = sys.stdin.read().splitlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            parts = shlex.split(line)
        except ValueError as e:
            results.append({"line": line, "ok": False, "error": f"Parse error: {e}"})
            continue

        if len(parts) < 2:
            results.append({"line": line, "ok": False, "error": "Too few arguments"})
            continue

        group, subcmd = parts[0], parts[1]
        handler = _DISPATCH.get((group, subcmd))

        if handler is None:
            results.append({
                "line": line, "ok": False,
                "error": f"Unknown or non-batchable command: {group} {subcmd}",
            })
            continue

        try:
            result = handler(parts[2:], cache_dir, config.board_id)
            result["line"] = line
            results.append(result)
        except Exception as e:
            results.append({"line": line, "ok": False, "error": str(e)})

    out.json(results)
