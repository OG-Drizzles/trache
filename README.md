# Trache

Local-first Trello cache with Git-style sync — optimised for on-machine AI workflows.

## What Is Trache?

Trache gives you a local cache of your Trello board with explicit pull/push sync semantics. Instead of hitting the Trello API for every read or write, you work against a local copy and sync deltas on your terms.

- **Targeted, not bulk** — small index read for discovery, targeted card load, targeted push
- **Token-efficient** — compact markdown per card, small JSON indexes for discovery
- **Version-verified** — identifier blocks ensure AI and human see the same version on Trello
- **Granular sync** — pull/push at card or list level; never forced to sync the entire board

## Why?

MCP-based Trello integrations and direct API calls are wasteful for AI agent workflows:
- Every card read is an API call
- Every edit is an API call
- Full-board fetches burn tokens and rate limits
- No local diff/status to preview changes before pushing

Trache solves this by maintaining a local cache with Git-style semantics: pull once, work locally, push when ready.

## Install

**From source (recommended for now):**

```bash
git clone <repo-url>
cd trache
pip install -e .          # editable install
# or
pip install .             # standard install
```

Requires Python 3.10+.

**Optional dependencies:**

```bash
pip install -e ".[dev]"   # pytest, ruff, coverage
pip install -e ".[oauth]" # OAuth support (authlib)
```

## Prerequisites

You need a Trello API key and token:

1. Get your API key from https://trello.com/power-ups/admin
2. Generate a token using the key
3. Set environment variables:

```bash
export TRELLO_API_KEY=your_key
export TRELLO_TOKEN=your_token
```

## Quick Start

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

## Command Reference

### Top-Level Commands

| Command | Description |
|---|---|
| `trache init` | Initialise cache for a board (`--board-id` or `--board-url`) |
| `trache pull` | Pull from Trello (`--card <id>`, `--list <name>`, `--force`) |
| `trache push` | Push local changes to Trello (`--card <id>`, `--dry-run`) |
| `trache sync` | Push then pull (`--dry-run`) |
| `trache status` | Show dirty state summary |
| `trache diff` | Show detailed clean vs working diff |
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
| `trache card add-label <id> <label>` | Add a label to a card |
| `trache card remove-label <id> <label>` | Remove a label from a card |

All card commands accept Card ID or UID6 as the identifier.

### Checklist Commands

| Command | Description |
|---|---|
| `trache checklist show <card>` | Show checklists for a card |
| `trache checklist check <card> <item_id>` | Mark item complete |
| `trache checklist uncheck <card> <item_id>` | Mark item incomplete |
| `trache checklist add-item <card> <checklist_name> <text>` | Add item to checklist by name |
| `trache checklist remove-item <card> <item_id>` | Remove a checklist item |

All checklist mutations are local-first — push to sync.

### Comment Commands

| Command | Description |
|---|---|
| `trache comment add <card> <text>` | Add a comment (pushes immediately) |
| `trache comment list <card>` | List comments (fetches from API) |

Note: Comment commands hit the Trello API directly — they are not local-first.

## Local-First Model

Trache maintains two copies of your board data:

- **Clean** (`.trache/clean/`) — baseline from last pull. Never edited directly.
- **Working** (`.trache/working/`) — your editable copy. All local mutations happen here.

`trache status` and `trache diff` compare clean vs working to detect changes. `trache push` sends working changes to Trello and re-pulls each pushed card to reconcile.

### UID6

The last 6 characters of a Trello card ID (uppercase). All card/checklist commands accept UID6 as an identifier. Input is case-insensitive.

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

### Identifier Block

Each card's Trello description is prepended with an identifier block containing metadata (card name, dates, UID6). This block is:

- Regenerated on every push from canonical frontmatter
- Stripped on every pull (never stored locally)
- Ensures humans and AI see the same version on Trello

### Modified Date vs Last Activity

- **`content_modified_at`** — Trache-tracked. Updates only when card content changes (title, description, list, labels, due, closed, checklists).
- **`last_activity`** — Trello's `dateLastActivity`. Updates on any activity including comments, member changes, etc.

On re-pull, Trache preserves `content_modified_at` if content hasn't changed, even if `dateLastActivity` bumped due to non-content activity.

### Checklist State Model

Checklists follow the same clean/working split as cards:

- Stored as `<card_id>.json` in `clean/checklists/` and `working/checklists/`
- CLI commands edit the working copy locally
- Changes show in `trache status` / `trache diff`
- Pushed to Trello with `trache push`

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

## Validation Status

**Live-validated on real Trello boards:**
- pull (full board, targeted card, targeted list)
- push (card fields, labels, checklists, description with identifier block)
- sync (push + pull cycle)
- dirty pull guard
- identifier block injection and stripping

**Mock-validated (unit/integration tests):**
- card create, archive, move
- checklist add-item, remove-item, check, uncheck
- comment add, comment list
- status, diff
- all error/edge case paths

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

Trache is designed for Claude Code and similar AI coding agents. See the [Claude skill](.claude/skills/trache/SKILL.md) for a complete command cookbook and workflow guide.

For Claude Code projects, the `CLAUDE.md` file provides agent-facing operating policy. The skill provides detailed command syntax and examples.

## License

MIT
