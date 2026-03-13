# Trache — Claude Code Operating Policy

Use Trache instead of raw Trello API/MCP calls. All edits happen locally; nothing hits the API until `trache push`.

## Preferred Workflow

```
trache card list                        # Discover cards (one index read)
trache card show <uid6>                 # Read one card (one file read)
# ... mutate locally ...
trache card edit-title <uid6> "New"     # Edit title
trache card edit-desc <uid6> "Text"     # Edit description
trache card add-label <uid6> "Bug"      # Add label
trache card remove-label <uid6> "Bug"   # Remove label
trache card move <uid6> "Done"          # Move to list
trache checklist check <uid6> <item_id> # Check item
trache status                           # Review dirty state
trache diff                             # Review detailed changes
trache push --dry-run                   # Preview push
trache push                             # Push to Trello
```

## Key Concepts

- **UID6**: Last 6 chars of card ID (uppercase). Use for all card references. Case-insensitive input.
- **Clean vs Working**: `.trache/clean/` is baseline from last pull. `.trache/working/` is editable. Diff compares clean vs working.
- **Local-first**: All edits happen locally. Nothing hits the API until `trache push`.
- **Dirty pull guard**: `trache pull` refuses if dirty. Use `--force` to override.
- **Index**: `.trache/indexes/index.json` — one read = full board orientation.

## When to Use Specific Commands

- **`trache pull --card <uid6>`** — refresh one card. Prefer over full-board pull.
- **`trache pull --list "List Name"`** — refresh one list.
- **`trache push --card <uid6>`** — push only one card.
- **`trache sync`** — push then full pull. Use when you want a clean slate after pushing.
- **`trache card create <list> <title>`** — create card locally. Add `--desc` for description.
- **`trache card archive <uid6>`** — archive locally (pushed on `trache push`).

## Comment Commands (Not Local-First)

- `trache comment add <uid6> <text>` — pushes immediately to API.
- `trache comment list <uid6>` — fetches from API.

## Avoid

- Full-board pull unless necessary — prefer targeted pull
- Parsing `.trache/` files directly — use CLI commands
- Committing `.trache/` to git — it's a local cache

## Caveats

- Comment commands hit the API directly (not local-first)
- Rate limiting/retry not yet implemented — avoid rapid-fire API calls
- Card create and archive are mock-validated only (not yet live-tested)

## Detailed Reference

For full command syntax, examples, and troubleshooting, invoke the `/trache` skill.

## File Layout

```
.trache/
  config.json                      # Board ID, auth env var names
  state.json                       # Last pull timestamp
  indexes/index.json               # Unified discovery index
  clean/cards/*.md                 # Baseline card files
  clean/checklists/<card_id>.json  # Baseline checklists
  working/cards/*.md               # Editable card files
  working/checklists/<card_id>.json # Editable checklists
```
