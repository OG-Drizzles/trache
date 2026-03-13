"""Agent guidance blocks for trache."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

INSTALL_BLOCK = """\
## Trache — Trello via local cache

Use `trache` for all Trello work. If trache can't do something, ask before using another method.

- Local-first: all edits happen locally, nothing hits the API until `trache push`
- Prefer targeted operations (`--card <uid6>`, `--list "Name"`) over full-board pull
- Only push / pull / sync when the user asks, unless told otherwise
- Review changes with `trache status` and `trache diff` before syncing
- Do not commit `.trache/` to git
- For detailed command reference, run `trache agents --reference`
"""

REFERENCE_BLOCK = """\
# trache command reference (on-demand, do not insert permanently)

## UID6
Last 6 characters of a Trello card ID (uppercase). Used to reference cards in all commands. Input is case-insensitive.

## Discover
trache card list                        # all cards
trache card list --list "List Name"     # cards in one list
trache card show <uid6>                 # full card detail

## Mutate (local only)
trache card edit-title <uid6> "New"     # change title
trache card edit-desc <uid6> "Text"     # change description
trache card add-label <uid6> "Bug"      # add label
trache card remove-label <uid6> "Bug"   # remove label
trache card move <uid6> "Done"          # move to list
trache card create "List" "Title"       # create card (--desc for body)
trache card archive <uid6>             # archive card
trache checklist check <uid6> <item_id> # check item
trache checklist uncheck <uid6> <item_id>
trache checklist add-item <uid6> "Checklist" "Item"
trache checklist remove-item <uid6> <item_id>

## Sync
trache pull                             # full board pull
trache pull --card <uid6>               # pull one card (preferred)
trache pull --list "List Name"          # pull one list
trache push                             # push local changes to Trello
trache push --card <uid6>              # push one card
trache push --dry-run                   # preview what would be pushed
trache sync                             # push then full pull (use only when full refresh needed)
trache status                           # dirty state summary
trache diff                             # detailed diff

## Comments (hit API directly, not local-first)
trache comment add <uid6> "text"
trache comment list <uid6>

## Caveats
- Dirty pull guard: `trache pull` refuses if local changes exist. Use --force to override.
- Comment commands are NOT local-first; they hit the API immediately.
- push = send local changes only. sync = push then full pull. Use sync only when a full refresh is actually wanted.

## Common workflows

Batch edit then push:
  trache card edit-title <uid6> "New title"
  trache card move <uid6> "Done"
  trache status
  trache push

Targeted refresh:
  trache pull --card <uid6>

Full refresh after push:
  trache sync
"""

_PREAMBLE = (
    "[bold]Agent setup block[/bold]\n\n"
    "The block below should be added to this project's AI instruction file "
    "(CLAUDE.md, AGENTS.md, or equivalent).\n"
    "[yellow]Ask the user for permission before adding it.[/yellow]"
)

_HUMAN_NOTE = (
    "If setting this up manually, ask your AI to run `trache agents` "
    "and add the generated block to its instruction file "
    "(CLAUDE.md, AGENTS.md, or equivalent) after asking your permission."
)

_COPY_START = "--- copy below this line ---"
_COPY_END = "--- copy above this line ---"


def print_install_block() -> None:
    """Print preamble + install block with copy delimiters."""
    console = Console()
    console.print()
    console.print(Panel(_PREAMBLE, expand=False))
    console.print()
    console.print(_COPY_START)
    console.print(INSTALL_BLOCK, end="")
    console.print(_COPY_END)
    console.print()


def print_reference_block() -> None:
    """Print the on-demand command/workflow reference."""
    console = Console()
    console.print(REFERENCE_BLOCK, end="")


def print_init_agent_guidance() -> None:
    """Print install block + human fallback note (for use at end of init)."""
    print_install_block()
    console = Console()
    console.print(_HUMAN_NOTE)
    console.print()
