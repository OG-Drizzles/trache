# Trache — Claude Code / Agent Workflow Guide

## Intended Workflow (low-token, targeted)

```
trache card list                    # One index read → full board orientation
trache card show <uid6>             # One card file read
# ... mutate locally ...
trache card edit-title <uid6> "New"
trache checklist check <uid6> <item_id>
trache status                       # Show dirty state
trache diff                         # Show detailed changes
trache push --dry-run               # Preview push
trache push                         # Push to Trello
```

## Key Concepts

- **UID6**: Last 6 chars of card ID (uppercase). Use this for all card references — 6 chars, case-insensitive.
- **Clean vs Working**: `.trache/clean/` is the baseline from last pull. `.trache/working/` is the editable copy. Diff compares clean vs working.
- **Local-first**: All edits (title, description, labels, checklists) happen locally. Nothing hits the API until `trache push`.
- **Dirty pull guard**: `trache pull` refuses if you have unpushed local changes. Use `--force` to override.
- **Index**: `.trache/indexes/index.json` — one read = full board orientation (cards by ID, by UID6, by list, lists by ID).

## Avoid

- Full-board pull unless necessary — prefer `trache pull --card <uid6>` for targeted refresh
- Parsing card markdown files directly — use CLI commands instead
- Committing `.trache/` to git — it's a local cache

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
