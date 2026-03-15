# Trache

Stop burning tokens talking to Trello. Pull once, work locally, push when you're done.

Trache gives your AI agent (or you) a local cache of a Trello board with Git-style `pull`/`push` semantics. Reading a card is a file read. Editing a card is a file write. Nothing hits the network until you say `trache push`.

```
Reading one card via MCP/API:  ~4,000 tokens + network round-trip
Reading one card via trache:   one local file read, zero tokens wasted
```

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
pull → discover → read → mutate → status/diff → push
```

1. **`trache pull`** — fetch board data from Trello into local cache
2. **`trache card list`** — discover cards (reads local index, no API call)
3. **`trache card show <uid6>`** — read a single card (reads one local file)
4. **Mutate locally** — edit title, description, labels, checklists, move, create, archive
5. **`trache status`** / **`trache diff`** — review what changed
6. **`trache push`** — push only the changed objects to Trello

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
| `trache init` | Initialise cache for a board (`--board-id` or `--board-url`, `--auth` for token URL) |
| `trache pull` | Pull from Trello (`--card <id>`, `--list <name>`, `--force`) |
| `trache push` | Push local changes to Trello (`--card <id>`, `--dry-run`) |
| `trache sync` | Push then pull (`--dry-run`, `--card <id>`) |
| `trache status` | Show dirty state summary |
| `trache diff` | Show detailed clean vs working diff |
| `trache agents` | Print agent setup instructions (`--reference` for command cheat-sheet) |
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
| `trache comment add <card> <text>` | Add a comment |
| `trache comment edit <card> <comment_id> <text>` | Edit a comment |
| `trache comment delete <card> <comment_id>` | Delete a comment |
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

Trache maintains two copies of your board data:

- **Clean** (`.trache/clean/`) — baseline from last pull. Never edited directly.
- **Working** (`.trache/working/`) — your editable copy. All local mutations happen here.

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

### Discovery Index

A single `index.json` in `.trache/indexes/` provides full board orientation in one read:

- `cards_by_id` — card ID → title, list, UID6, modified date
- `cards_by_uid6` — UID6 → card ID
- `cards_by_list` — list ID → card IDs
- `lists_by_id` — list ID → name, position

## File Layout

```
.trache/
  config.json                      # Board ID, auth env var names
  state.json                       # Last pull timestamp
  indexes/
    index.json                     # Unified discovery index
  clean/
    cards/*.md                     # Baseline card files
    checklists/<card_id>.json      # Baseline checklists (per card)
    labels.json                    # Board labels
    board_meta.md                  # Board name/URL
  working/
    cards/*.md                     # Editable card files
    checklists/<card_id>.json      # Editable checklists (per card)
    labels.json                    # Board labels
    board_meta.md                  # Board name/URL
```

## Known Limitations

- **No rate limiting or retry** — avoid rapid-fire API calls.
- **No concurrent-agent conflict resolution** — if two agents push changes to the same card, last write wins silently. Coordinate externally if sharing a board.
- **Duplicate list names are ambiguous** — list-name targeting picks one arbitrarily. Rename duplicates or use list IDs.
- **Card create and archive are mock-validated only** — they work in practice but don't yet have live integration tests.

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
- **`trache agents --reference`** — prints a compact command reference designed for agent context windows
- **[Claude skill](.claude/skills/trache/SKILL.md)** — full command cookbook and workflow guide
- **`CLAUDE.md`** — agent-facing operating policy (generated by `trache init`)

## License

MIT
