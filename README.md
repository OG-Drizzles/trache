# **Trache**

### Are you sick of paying premium token prices to load an entire Trello board just to rename one card?

Has your AI ever pulled half of Trello into context, chewed 27% of your weekly tokens, changed exactly one line of text, only to hit you with:
**"Done! If you need anything else changed, just say the word."**

Do you enjoy round-tripping through MCP/API calls, loading giant JSON blobs, and paying for the privilege of doing something your machine could have handled locally in the first place?

**Good news.** There is now a worse-named but better-behaved solution.

**Trache** is a local-first Trello cache, built for AI agents.  
Trache is what happens when ***Tr***ello and C***ache*** love each other very much ...

It pulls your board once, stores it locally, and lets your agent work on cards like normal files:

- read a card = local file read
- edit a card = local file write
- review changes = local diff
- hit Trello only when you actually mean to

In other words: **stop making your AI re-download Trello’s life story every time it wants to edit one card.**

Trache gives you Git-style `pull` / `push` semantics for Trello, with targeted operations, cheap local discovery, and explicit sync only when you actually want it. Reading a card becomes a file read. Editing a card becomes a file write. Nothing hits the network until you say so.

> **Using an AI agent?** Run `trache agents` after setup for agent-specific instructions, or `trache agents --reference` for a compact command cheat-sheet.

## Install

```bash
git clone <repo-url>
cd trache
pip install -e .          # editable install
# or
pip install .             # standard install
```

Requires Python 3.10+. Uses [hatchling](https://pypi.org/project/hatchling/) as the build backend — if you're in a sandboxed or offline environment without hatchling, install it first (`pip install hatchling`) or use `pip install --no-build-isolation .`

**Optional dependencies:**

```bash
pip install -e ".[dev]"   # pytest, ruff, coverage
pip install -e ".[oauth]" # OAuth support (authlib)
```

## Prerequisites

You need a Trello API key and token:

1. Get your API key from https://trello.com/power-ups/admin
2. Generate a token by visiting (substitute your API key):

   https://trello.com/1/authorize?expiration=never&name=trache&scope=read,write&response_type=token&key=YOUR_API_KEY

   Or run `trache init --auth` to print the URL with your key substituted.
3. Set environment variables:

```bash
export TRELLO_API_KEY=your_key
export TRELLO_TOKEN=your_token
```

## Quick Start

**UID6** — the last 6 characters of a Trello card ID (e.g. `B1A403`). This is how you reference cards in every command. Case-insensitive input, displayed uppercase.

```bash
# Initialise cache for a board
trache init --board-id <board_id>
# or by URL:
trache init --board-url https://trello.com/b/<board_id>/board-name

# Add the install block to your AI instruction file, then acknowledge
trache agents              # print the install block
trache agents --ack        # confirm onboarding (required before pull/sync)

# Pull board data
trache pull

# Browse locally (no API calls)
trache card list
trache card show <uid6>

# Edit locally
trache card edit-title <uid6> "New Title"
trache card add-label <uid6> "Bug"

# Review changes
trache status
trache diff

# Push to Trello
trache push --dry-run     # preview first
trache push               # push for real
```

## Core Workflow

```
init → agents → agents --ack → pull → discover → read → mutate → status/diff → push
```

1. **`trache init`** — initialise cache for a board
2. **`trache agents`** + **`trache agents --ack`** — add the install block to your AI instruction file, then acknowledge onboarding (gates `pull` and `sync`)
3. **`trache pull`** — fetch board data from Trello into local cache
4. **`trache card list`** — discover cards (reads local SQLite cache, no API call)
5. **`trache card show <uid6>`** — read a single card (one local query)
6. **Mutate locally** — edit title, description, labels, checklists, move, create, archive
7. **`trache status`** / **`trache diff`** — review what changed
8. **`trache push`** — push only the changed objects to Trello

## Things to Know

A few behaviours that aren't obvious from the happy path:

- **List names aren't unique.** If your board has duplicate list names, `--list "Name"` and `card create "Name" ...` will silently pick one. Prefer list IDs or ensure names are unique.
- **Comment commands hit the API immediately.** Unlike every other mutation, `comment add`, `comment edit`, and `comment delete` are not local-first — they write to Trello the moment you run them.
- **Labels are validated against the board.** `add-label` checks the label name against your board's labels (pulled into `labels.json`). Use `trache label list` to see what's available, or `trache label create` to add new ones.
- **New cards get temporary IDs.** Locally-created cards are assigned a temp UID6 (containing `T~`) until pushed. After push, trache reconciles the temp ID to the real Trello ID and reports the mapping.
- **Push can partially succeed.** If you push multiple cards and some fail (e.g. an invalid label), the successful ones still land. Check `trache status` after push to see what's still dirty.
- **Prefer UID6 over names** once you've resolved a card. UID6 is unambiguous; names and list names can collide.
- For agent-specific guidance, run `trache agents --reference` for the compact command surface.

## Command Reference

### Top-Level Commands

| Command | Description |
|---|---|
| `trache init` | Initialise cache for a board (`--board-id` or `--board-url`, `--auth` for token URL, `--new` to create) |
| `trache pull` | Pull from Trello (`--card <id>`, `--list <name>`, `--force`) |
| `trache push` | Push local changes to Trello (`--card <id>`, `--dry-run`) |
| `trache sync` | Push then pull (`--dry-run`, `--card <id>`) |
| `trache stale` | Check if the board has remote changes since last pull (one API call) |
| `trache status` | Show dirty state summary |
| `trache diff` | Show detailed clean vs working diff |
| `trache batch run` | Execute multiple commands from stdin (JSON output) |
| `trache agents` | Print agent setup instructions (`--reference` for command cheat-sheet, `--ack` to confirm onboarding) |
| `trache version` | Show installed version |

### Card Commands

| Command | Description |
|---|---|
| `trache card list` | List cards from local index (`--list <name>` to filter) |
| `trache card show <id>` | Show a single card |
| `trache card edit-title <id> <title>` | Edit card title |
| `trache card edit-desc <id> <desc>` | Edit card description |
| `trache card move <id> <list>` | Move card to a different list |
| `trache card create <list> <title>` | Create a new card (`--desc` for description) |
| `trache card archive <id>` | Archive a card |
| `trache card add-label <id> <label>` | Add a label (must match a board label) |
| `trache card remove-label <id> <label>` | Remove a label from a card |

All card commands accept Card ID or UID6 as the identifier.

### Board Commands

| Command | Description |
|---|---|
| `trache board list` | List all configured boards |
| `trache board switch <alias>` | Switch the active board |
| `trache board offboard <alias>` | Remove a board's local cache (`--yes`, `--archive`, `--force`) |

Use `--board <alias>` (or `-B`) on any command to target a specific board without switching.

### Checklist Commands

| Command | Description |
|---|---|
| `trache checklist show <card>` | Show checklists for a card |
| `trache checklist create <card> <name>` | Create a new checklist |
| `trache checklist check <card> <item_id>` | Mark item complete |
| `trache checklist uncheck <card> <item_id>` | Mark item incomplete |
| `trache checklist add-item <card> <checklist_name> <text>` | Add item to checklist by name |
| `trache checklist remove-item <card> <item_id>` | Remove a checklist item |

All checklist mutations are local-first — push to sync.

### Comment Commands (API-direct)

| Command | Description |
|---|---|
| `trache comment add <card> <text>` | Add a comment (`--yes` required in machine mode) |
| `trache comment edit <card> <comment_id> <text>` | Edit a comment (`--yes` required in machine mode) |
| `trache comment delete <card> <comment_id>` | Delete a comment (`--yes` required) |
| `trache comment list <card>` | List comments |

**All comment commands hit the Trello API immediately.** They bypass the local-first model entirely — there is no undo via `trache status` or `trache diff`.

### Label Commands

| Command | Description |
|---|---|
| `trache label list` | List board labels (from local cache) |
| `trache label create <name>` | Create a new board label (`--color`) |
| `trache label delete <name>` | Delete a board label |

### List Commands

| Command | Description |
|---|---|
| `trache list show` | Show all board lists |
| `trache list create <name>` | Create a new list (`--pos top\|bottom`) |
| `trache list rename <old> <new>` | Rename a list |
| `trache list archive <name>` | Archive a list (`--yes` required) |

List commands are API-direct (like comments).

## Local-First Model

Trache maintains two copies of your board data in a SQLite database:

- **Clean** — baseline from last pull. Never edited directly.
- **Working** — your editable copy. All local mutations happen here.

`trache status` and `trache diff` compare clean vs working to detect changes. `trache push` sends working changes to Trello and re-pulls each pushed card to reconcile.

### Dirty Pull Guard

`trache pull` refuses to overwrite your working copy if you have unpushed local changes:

```bash
trache pull           # → refuses if dirty
trache pull --force   # → overwrites working copy with fresh pull
```

### Push vs Sync

- **`trache push`** — pushes local changes to Trello. Re-pulls each pushed card to reconcile.
- **`trache sync`** — pushes first, then does a full board pull. If push has errors, the full pull is skipped to preserve local state for failed cards.

### Targeted Pull

Prefer targeted pulls over full-board pulls when you only need one card or list:

```bash
trache pull --card <uid6>     # refresh one card
trache pull --list "To Do"    # refresh one list
```

## How It Works

A few implementation details, if you're curious:

### Identifier Block

Each card's Trello description is prepended with a metadata block (card name, dates, UID6) on push. This block is stripped on pull and never stored locally — it exists only on the Trello side so that humans browsing the board see version metadata alongside the description.

### Modified Date vs Last Activity

- **`content_modified_at`** — Trache-tracked. Updates only when card content changes (title, description, list, labels, due, closed, checklists).
- **`last_activity`** — Trello's `dateLastActivity`. Updates on any activity including comments, member changes, etc.

On re-pull, Trache preserves `content_modified_at` if content hasn't changed, even if `dateLastActivity` bumped due to non-content activity.

## File Layout

```
.trache/
  boards/
    <alias>/
      config.json       # Board ID, auth env var names
      cache.db           # SQLite WAL store (cards, checklists, labels, lists)
      state.json         # Last pull timestamp, board_last_activity
  active                 # Current active board alias
```

## Known Limitations

- **No concurrent-agent conflict resolution** — if two agents push changes to the same card, last write wins silently. Coordinate externally if sharing a board.
- **Duplicate list names are ambiguous** — list-name targeting picks one arbitrarily. Rename duplicates or use list IDs.

## Development

```bash
pip install -e ".[dev]"

# Run tests
make test
# or: python3 -m pytest tests/ -v

# Lint
make lint
# or: ruff check src/ tests/

# Format
make fmt
```

## LLM / Agent Integration

Trache is built for Claude Code and similar AI coding agents.

- **`trache agents`** — prints setup instructions for injecting trache into your agent's instruction files
- **`trache agents --ack`** — acknowledges onboarding after the install block has been added; required before `pull` or `sync` will work
- **`trache agents --reference`** — prints a compact command reference designed for agent context windows
- **Onboarding gate** — after `init`, the onboarding gate must be explicitly acknowledged via `trache agents --ack` before `pull` or `sync` will work. There is no automatic grandfathering.
- **Machine-first output** — default output is JSON/TSV for machine consumption; set `TRACHE_HUMAN=1` for Rich-formatted human output

## License

This project is licensed under the **GNU Affero General Public License v3.0 or later** (AGPL-3.0-or-later). See [LICENSE](LICENSE) for the full text.
