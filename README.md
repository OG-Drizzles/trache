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

## Commands

| Command | Description |
|---|---|
| `trache init` | Setup board + auth → creates `.trache/` |
| `trache pull` | Full board pull (or `--card`/`--list` for granular) |
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
| `trache checklist check <item_id>` | Mark checklist item complete |
| `trache checklist uncheck <item_id>` | Mark checklist item incomplete |
| `trache checklist add-item <checklist> <text>` | Add checklist item |
| `trache comment add <card> <text>` | Add comment to card |
| `trache comment list <card>` | List comments on card |

## License

MIT
