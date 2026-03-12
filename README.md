# Trache

Local-first Trello cache with Git-style sync — optimised for on-machine AI workflows.

## What

Trache provides a local cache of your Trello board with explicit pull/push sync semantics. It eliminates wasteful API round-trips by operating on a local cache and only syncing deltas.

- **Targeted, not bulk** — tiny index read → targeted card load → targeted edit → targeted push
- **Token-efficient** — compact markdown per card, small JSON indexes for discovery
- **Version-verified** — identifier blocks ensure AI and human are looking at the same version
- **Granular sync** — pull/push at card-level or list-level, never forced to sync entire board

## Install

```bash
pip install trache
```

## Quick Start

```bash
# Initialise cache for a board
export TRELLO_API_KEY=your_key
export TRELLO_TOKEN=your_token
trache init --board-id <board_id>

# Pull board data
trache pull

# Browse locally (no API calls)
trache card list
trache card show <uid6>

# Edit locally, then push changes
trache card edit-title <uid6> "New Title"
trache status
trache diff
trache push --dry-run
trache push
```

## Local-First Model

Trache maintains two copies of your board data:

- **Clean** (`.trache/clean/`) — baseline from last pull. Never edited directly.
- **Working** (`.trache/working/`) — your editable copy. All local mutations happen here.

`trache status` and `trache diff` compare clean vs working to detect changes. `trache push` sends working changes to Trello and re-pulls to reconcile.

## Dirty Pull Guard

`trache pull` refuses to overwrite your working copy if you have unpushed local changes:

```bash
trache pull           # → "Working copy has unpushed changes. Push first or pass force=True."
trache pull --force   # → Overwrites working copy with fresh pull
```

## Push vs Sync

- **`trache push`** — pushes local changes to Trello. Re-pulls each pushed card to reconcile.
- **`trache sync`** — pushes first, then does a full board pull. If push has errors, the full pull is skipped to preserve your local state for failed cards.

## Identifier Block

Each card's Trello description is prepended with an identifier block containing metadata (card name, dates, UID6). This is a rendered-only view:

- Regenerated on every push from canonical frontmatter
- Stripped on every pull (never stored locally)
- Ensures humans and AI see the same version on Trello

## Modified Date vs Last Activity

- **`content_modified_at`** — Trache-tracked. Updates only when card content changes (title, description, list, labels, due, closed, checklists).
- **`last_activity`** — Trello's `dateLastActivity`. Updates on any activity including comments, member changes, etc.

On re-pull, Trache preserves `content_modified_at` if content hasn't changed, even if `dateLastActivity` bumped due to non-content activity.

## Checklist State Model

Checklists follow the same clean/working split as cards:

- Stored as `<card_id>.json` in `clean/checklists/` and `working/checklists/`
- CLI commands (`check`, `uncheck`, `add-item`, `remove-item`) edit the working copy locally
- Changes show in `trache status` / `trache diff`
- Pushed to Trello with `trache push`

## Discovery Index

A single `index.json` in `.trache/indexes/` provides full board orientation in one read:

- `cards_by_id` — card ID → title, list, UID6, modified date
- `cards_by_uid6` — UID6 → card ID
- `cards_by_list` — list ID → card IDs
- `lists_by_id` — list ID → name, position

## LLM Workflow

Optimised for Claude Code and similar agents:

1. `trache card list` — discover cards (one index read)
2. `trache card show <uid6>` — read one card (one file read)
3. Mutate locally (edit, move, check, etc.)
4. `trache status` / `trache diff` — verify changes
5. `trache push` — targeted push of only changed objects

## Commands

| Command | Description |
|---|---|
| `trache init` | Setup board + auth → creates `.trache/` |
| `trache pull` | Full board pull (or `--card`/`--list` for granular) |
| `trache pull --force` | Pull even if working copy has unpushed changes |
| `trache push` | Push local changes to Trello (`--dry-run` supported) |
| `trache sync` | Push then pull (convenience) |
| `trache status` | Show dirty state summary |
| `trache diff` | Show clean vs working diff |
| `trache card list` | List cards from local index |
| `trache card show <id>` | Show single card |
| `trache card edit-title <id> <title>` | Edit card title locally |
| `trache card edit-desc <id> <desc>` | Edit card description locally |
| `trache card move <id> <list>` | Move card to list locally |
| `trache card create <list> <title>` | Create card locally |
| `trache card archive <id>` | Archive card locally |
| `trache checklist show <card>` | Show checklists for card |
| `trache checklist check <card> <item_id>` | Mark checklist item complete (local) |
| `trache checklist uncheck <card> <item_id>` | Mark checklist item incomplete (local) |
| `trache checklist add-item <card> <checklist> <text>` | Add checklist item (local) |
| `trache checklist remove-item <card> <item_id>` | Remove checklist item (local) |
| `trache comment add <card> <text>` | Add comment to card |
| `trache comment list <card>` | List comments on card |

## License

MIT
