"""Machine-first output layer.

Default output is TSV/JSON for machine consumption.
Set TRACHE_HUMAN=1 for Rich-formatted human output.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

from rich.console import Console
from rich.table import Table

_singleton: Optional[OutputWriter] = None


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

    def error(self, message: str) -> None:
        """Errors to stderr. JSON in machine mode, Rich in human mode."""
        if self._human:
            self._console.print(f"[red]{message}[/red]")
        else:
            print(json.dumps({"error": message}, separators=(",", ":")), file=sys.stderr)

    def api_stats(self) -> None:
        """API stats — human mode only."""
        if not self._human:
            return
        from trache.api.client import get_api_stats

        stats = get_api_stats()
        if stats["calls"] > 0:
            self._console.print(
                f"[dim]({int(stats['calls'])} API calls, "
                f"{stats['total_ms'] / 1000:.1f}s)[/dim]"
            )


def get_output() -> OutputWriter:
    """Module-level singleton, reads TRACHE_HUMAN on first call."""
    global _singleton
    if _singleton is None:
        human = os.environ.get("TRACHE_HUMAN", "").strip() == "1"
        _singleton = OutputWriter(human=human)
    return _singleton


def reset_output() -> None:
    """Reset singleton — for tests."""
    global _singleton
    _singleton = None
