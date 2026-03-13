---
name: trache
description: Trache CLI command reference, workflow guide, and troubleshooting for Trello board management.
---

# Trache — Command Cookbook & Workflow Guide

Trache is a local-first Trello cache. All edits happen locally. Nothing hits the API until `trache push`.

## Setup

```bash
# Set credentials
export TRELLO_API_KEY=your_key
export TRELLO_TOKEN=your_token

# Initialise for a board
trache init --board-id <board_id>
# or:
trache init --board-url https://trello.com/b/<board_id>/board-name

# Pull board data
trache pull
```

## Core Workflow

```bash
trache card list                          # 1. Discover cards (local index)
trache card list --list "In Progress"     # 1b. Filter by list name
trache card show <uid6>                   # 2. Read a card
# 3. Mutate locally (see commands below)
trache status                             # 4. Review dirty state
trache diff                               # 5. Review detailed changes
trache push --dry-run                     # 6. Preview push
trache push                               # 7. Push to Trello
```

## Pull Commands

```bash
trache pull                     # Full board pull
trache pull --card <uid6>       # Pull single card (preferred)
trache pull --list "To Do"      # Pull single list
trache pull --force             # Overwrite dirty working copy
```

**Prefer `--card` or `--list`** over full-board pull to minimise API calls.

## Push Commands

```bash
trache push                     # Push all local changes
trache push --card <uid6>       # Push single card
trache push --dry-run           # Preview what would be pushed
```

## Sync

```bash
trache sync                     # Push then full pull
trache sync --dry-run           # Preview
```

Push first, then full pull. If push has errors, pull is skipped to preserve local state.

## Card Commands

```bash
# Discovery
trache card list                          # All cards
trache card list --list "Done"            # Filter by list

# Read
trache card show <uid6>                   # Show card content

# Mutate (all local-first)
trache card edit-title <uid6> "New Title"
trache card edit-desc <uid6> "New description text"
trache card move <uid6> "In Progress"     # Move to list (by name or ID)
trache card create "To Do" "Card Title"   # Create in list
trache card create "To Do" "Title" --desc "Description here"
trache card archive <uid6>                # Archive card
trache card add-label <uid6> "Bug"        # Add label by name
trache card remove-label <uid6> "Bug"     # Remove label by name
```

**UID6**: Last 6 characters of the Trello card ID. Uppercase. Input is case-insensitive.

## Checklist Commands

```bash
trache checklist show <uid6>                          # Show all checklists
trache checklist check <uid6> <item_id>               # Mark complete
trache checklist uncheck <uid6> <item_id>             # Mark incomplete
trache checklist add-item <uid6> "Checklist Name" "Item text"   # Add item
trache checklist remove-item <uid6> <item_id>         # Remove item
```

All checklist mutations are local-first — push to sync. Use `checklist show` to find item IDs and checklist names.

## Comment Commands

```bash
trache comment add <uid6> "Comment text"    # Add comment (immediate API call)
trache comment list <uid6>                  # List comments (API fetch)
```

**Note**: Comments are NOT local-first. They hit the API directly.

## Status & Diff

```bash
trache status       # Summary: which cards/checklists are modified/added/deleted
trache diff         # Detailed field-by-field diff (clean vs working)
```

## Other Commands

```bash
trache version      # Show installed version
trache init         # Re-initialise (--board-id or --board-url)
```

## Common Workflows

### Read a card and update its title
```bash
trache card show ABC123
trache card edit-title ABC123 "Updated Title"
trache push
```

### Move a card and add a label
```bash
trache card move ABC123 "In Progress"
trache card add-label ABC123 "Priority"
trache status
trache push
```

### Check off a checklist item
```bash
trache checklist show ABC123           # Find the item ID
trache checklist check ABC123 <item_id>
trache push
```

### Create a new card
```bash
trache card create "To Do" "New Feature" --desc "Implement the thing"
trache push
```

### Refresh a single card after someone else edited it on Trello
```bash
trache pull --card ABC123
trache card show ABC123
```

## Troubleshooting

**"Working copy has unpushed changes"** on pull:
- Push first: `trache push`, then `trache pull`
- Or force: `trache pull --force` (overwrites local changes)

**Card not found / UID6 not recognised**:
- Run `trache pull` to refresh the index
- Run `trache card list` to see available UID6 values

**Push reports errors for some cards**:
- Failed cards remain in dirty state — fix and retry
- Successfully pushed cards are reconciled via re-pull

**Checklist item ID unknown**:
- Run `trache checklist show <uid6>` to see all items with their IDs

## When NOT to Use Trache

- For one-off Trello reads where you won't need the data again (direct API may be simpler)
- When you need real-time board state (Trache is cached — pull to refresh)
- For operations Trache doesn't support (e.g., board creation, member management, attachments)
