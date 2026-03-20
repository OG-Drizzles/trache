"""Machine-first output layer.

Default output is TSV/JSON for machine consumption.
Set TRACHE_HUMAN=1 for Rich-formatted human output.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from typing import Optional

from rich.console import Console
from rich.table import Table

from trache.api.client import HasStats

_singleton: Optional[OutputWriter] = None
_singleton_lock = threading.Lock()


class OutputWriter:
    """Dual-mode output: machine (TSV/JSON) by default, human (Rich) opt-in."""

    def __init__(self, *, human: bool) -> None:
        self._human = human
        self._console = Console() if human else Console(stderr=True)

    @property
    def is_human(self) -> bool:
        return self._human

    def tsv(self, rows: list[list[str]], *, header: list[str]) -> None:
        """Emit TSV with header row to stdout."""
        print("\t".join(header))
        for row in rows:
            print("\t".join(str(c) for c in row))

    def json(self, data: object) -> None:
        """Emit compact JSON (no whitespace) to stdout."""
        print(json.dumps(data, separators=(",", ":"), default=str))

    def human(self, markup: str) -> None:
        """Rich-formatted output — only emits in human mode, silent otherwise."""
        if self._human:
            self._console.print(markup)

    def human_table(self, table: Table) -> None:
        """Render Rich table — only in human mode."""
        if self._human:
            self._console.print(table)

    def error(self, message: str, **extra) -> None:
        """Errors to stderr. JSON in machine mode, Rich in human mode."""
        if self._human:
            self._console.print(f"[red]{message}[/red]")
        else:
            payload = {"error": message, **extra}
            print(json.dumps(payload, separators=(",", ":"), default=str), file=sys.stderr)

    def api_stats(self, client: HasStats | None = None) -> None:
        """Emit API stats: human-readable to console, or JSON to stderr in machine mode."""
        if client is None:
            return
        stats = client.get_stats()
        if stats["calls"] == 0:
            return
        if self._human:
            self._console.print(
                f"[dim]({int(stats['calls'])} API calls, "
                f"{stats['total_ms'] / 1000:.1f}s)[/dim]"
            )
        else:
            print(
                json.dumps(
                    {"api_calls": int(stats["calls"]), "api_ms": int(stats["total_ms"])},
                    separators=(",", ":"),
                ),
                file=sys.stderr,
            )


def get_output() -> OutputWriter:
    """Module-level singleton, reads TRACHE_HUMAN on first call."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                human = os.environ.get("TRACHE_HUMAN", "").strip() == "1"
                _singleton = OutputWriter(human=human)
    return _singleton


def reset_output() -> None:
    """Reset singleton — for tests."""
    global _singleton
    with _singleton_lock:
        _singleton = None
