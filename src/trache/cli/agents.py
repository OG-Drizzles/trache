"""Agent guidance blocks for trache."""

from __future__ import annotations

import webbrowser

import click
import typer
from rich.console import Console
from rich.panel import Panel

INSTALL_BLOCK_TEMPLATE = """\
## Trache — Trello via local cache{board_line}

Use `trache` for all Trello work. Do NOT fall back to Trello MCP or raw API calls. If trache cannot do it, stop and ask the user.
User instructions always override this block.

**Run `trache agents --reference` at the start of any session involving Trello work.**

**Never pull, push, or sync unless the user explicitly asks.**

Default to read-only / inspect-first behaviour unless the user explicitly asks for a write action.

**Default workflow:** `card list` → `card show` → edit locally → `status` / `diff` → `push`

**UID6:** Cards are referenced by UID6 — the last 6 characters of the Trello card ID (e.g. `A2CFF5`). Input is case-insensitive. Always use UID6, not full card IDs.

- **Local-first:** all reads are local (no API calls). All edits happen locally. Nothing hits the API until `trache push`.
- **Comments hit the API immediately** — they bypass local-first staging. Requires `--yes` flag. Do not add/edit/delete comments without explicit user approval.
- **API-direct:** list mutations (`list create/rename/archive`) also hit the API immediately — no push needed.
- Prefer targeted operations (`--card <uid6>`, `--list "Name"`) over full-board pull/push.
- Always review changes with `trache status` and `trache diff` before pushing.
- Do not commit `.trache/` to git.

Example — read a card, then add a comment (API-direct):
  `trache card show A2CFF5`
  `trache comment add A2CFF5 "Reviewed — looks good."`
"""

REFERENCE_BLOCK = """\
# trache command reference
Ephemeral reference for the current task — do not copy into instruction files.
User instructions always override this reference.

**Default workflow:** `card list` → `card show` → edit locally → `status` / `diff` → `push`
Prefer targeted operations (`--card <uid6>`, `--list "Name"`) over full-board pull/push.

## UID6
Last 6 characters of a Trello card ID (uppercase). Used to reference cards in all commands. Input is case-insensitive.

## Subcommands
- `trache card` — list, show, edit-title, edit-desc, add-label, remove-label, move, create, archive
- `trache checklist` — show, check, uncheck, add-item, remove-item, create
- `trache comment` — add, edit, delete, list
- `trache label` — list, create, delete
- `trache list` — show, create, rename, archive

## Discover
trache card list                        # all cards
trache card list --list "List Name"     # cards in one list
trache card show <uid6>                 # full card detail
trache checklist show <uid6>            # checklists for a card
trache list show                        # all board lists
trache label list                       # all board labels

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
trache checklist create <uid6> "Name"   # create checklist
trache label create "Name" --color green
trache label delete "Name"

## Mutate (API-direct)
trache list create "Name"               # create list (--pos top|bottom)
trache list rename "Old" "New"          # rename list
trache list archive "Name" --yes        # archive list (requires --yes)
trache comment add <uid6> "Text" --yes       # add comment (API-direct, --yes required in machine mode)
trache comment edit <uid6> <comment_id> "Text" --yes  # edit comment (API-direct, --yes required)
trache comment delete <uid6> <comment_id> --yes       # delete comment (API-direct, --yes required)

## Sync
trache pull                             # full board pull
trache pull --card <uid6>               # pull one card (preferred)
trache pull --list "List Name"          # pull one list
trache push                             # push local changes to Trello
trache push --card <uid6>              # push one card
trache push --dry-run                   # preview what would be pushed
trache sync                             # push then full pull (use only when full refresh needed)
trache sync --card <uid6>              # push one card then pull it back
trache status                           # dirty state summary
trache diff                             # detailed diff

## Caveats
- **Comments and list mutations are NOT local-first** — `comment add/edit/delete`, `comment list`, and `list create/rename/archive` hit the Trello API immediately.
- `comment add/edit/delete` require `--yes` in machine mode to prevent accidental API calls.
- `comment list` JSON output returns `{"api_direct": true, "comments": [...]}` (not a bare array).
- Every other command is local until you push.
- Dirty pull guard: `trache pull` refuses if local changes exist. Use --force to override.
- push = send local changes only. sync = push then full pull. Use sync only when a full refresh is actually wanted.

## Common workflows

Batch edit then push:
  trache card edit-title <uid6> "New title"
  trache card move <uid6> "Done"
  trache status
  trache push

Targeted sync (push one card and refresh it):
  trache sync --card <uid6>

Targeted refresh:
  trache pull --card <uid6>

Full refresh after push:
  trache sync

Agent batching — edit multiple cards then push once:
  trache card edit-title <uid6a> "Title A"
  trache card edit-title <uid6b> "Title B"
  trache card move <uid6c> "Done"
  trache status
  trache push

New list then create card in it:
  trache list create "Sprint 42"
  trache card create "Sprint 42" "First task" --desc "Description here"
  trache push
"""

def render_install_block(board_name: str | None = None) -> str:
    """Render the install block, optionally with board name."""
    board_line = f"\nBoard: {board_name} (initialised)" if board_name else ""
    return INSTALL_BLOCK_TEMPLATE.format(board_line=board_line)


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


def print_install_block(board_name: str | None = None) -> None:
    """Print preamble + install block with copy delimiters."""
    console = Console()
    console.print()
    console.print(Panel(_PREAMBLE, expand=False))
    console.print()
    console.print(_COPY_START)
    console.print(render_install_block(board_name), end="")
    console.print(_COPY_END)
    console.print()


def print_reference_block() -> None:
    """Print the on-demand command/workflow reference."""
    console = Console()
    console.print(REFERENCE_BLOCK, end="")


def print_init_agent_guidance(board_name: str | None = None) -> None:
    """Print install block + next-step hint + human fallback note (for use at end of init)."""
    print_install_block(board_name)
    console = Console()
    console.print("[bold]Next:[/bold] run [bold]trache agents --reference[/bold] for the full command cheatsheet.")
    console.print()
    console.print(Panel(f"[dim]For manual setup:[/dim] {_HUMAN_NOTE}", expand=False))
    console.print()


TRELLO_AUTH_URL_TEMPLATE = (
    "https://trello.com/1/authorize?expiration=never&name=trache"
    "&scope=read,write&response_type=token&key={api_key}"
)


def build_auth_url(api_key: str | None = None) -> str:
    """Build the Trello authorize URL, substituting the key if available."""
    return TRELLO_AUTH_URL_TEMPLATE.format(api_key=api_key or "YOUR_API_KEY")


def print_auth_guidance(
    api_key: str | None,
    *,
    key_env: str = "TRELLO_API_KEY",
    token_env: str = "TRELLO_TOKEN",
) -> None:
    """Print a Rich panel with auth/token setup instructions."""
    console = Console()
    auth_url = build_auth_url(api_key)

    lines = [
        "[bold]Auth Setup[/bold]\n",
        "1. Get your API key from: https://trello.com/power-ups/admin\n",
        f"2. Generate a token by visiting:\n   {auth_url}\n",
        "3. Export environment variables:\n"
        f"   export {key_env}=<your_api_key>\n"
        f"   export {token_env}=<your_token>",
    ]

    console.print(Panel("\n".join(lines), title="Trello Auth", expand=False))

    try:
        if typer.confirm("Open the authorize URL in your browser?", default=False):
            webbrowser.open(auth_url)
    except (EOFError, KeyboardInterrupt):
        pass
    except click.exceptions.Abort:
        console.print()
