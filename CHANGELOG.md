# Changelog

## 0.2.0 — 2026-03-15

Multi-board support and board lifecycle commands.

### Features

- **Multi-board directory layout**: `.trache/boards/<alias>/` per board with `.trache/active` file for board selection
- **`--board` / `-B` global flag**: route any command to a specific board without switching active board
- **`trache board list`**: show all configured boards with alias, Trello name, and last pull timestamp; marks active board with `*`
- **`trache board switch <alias>`**: switch the active board
- **`trache board offboard <alias>`**: remove a board's local cache with `--yes` safety flag, `--force` to override dirty guard, `--archive` to close the board on Trello
- **`trache init --name <alias>`**: choose a short alias for the board at init time
- **`trache init --new "Board Name"`**: create a new Trello board on Trello and init locally in one step
- **Auto-generated aliases**: board names are slugified (`"My Work Board"` → `"my-work-board"`)
- **Fuzzy alias matching**: typos in `--board` flag suggest the closest known alias
- **Automatic legacy migration**: flat `.trache/` layout is transparently migrated to multi-board on first command

### API

- `TrelloClient.create_board()`: create a new Trello board
- `TrelloClient.close_board()`: archive (close) a board on Trello

### Infrastructure

- Central board routing in `_context.py` replaces 6 copies of `_cache_dir()` returning `Path(".trache")`
- Removed dead `get_cache_dir()` from config module
- 27 new tests in `test_multi_board.py` (163 total)

## 0.1.10 — 2026-03-15

Raw output mode, lightweight pull check, and auth onboarding.

### Features

- **`--raw` flag**: tab-separated output on `card list`, `card show`, `checklist show`, `label list`, and `list show` for agent/script consumption
- **Lightweight pull check**: `pull` fetches board `dateLastActivity` before full pull; skips if unchanged
- **Auth onboarding flow**: `trache init` now shows an Auth Setup panel with token URL when credentials are missing; `--auth` flag forces the panel even when auth is configured
- **`GET /members/me` validation**: `init` validates the token on setup and prints the authenticated user's name

### Tests

- Auth panel tests for init with various env var states
- `build_auth_url()` unit tests

## 0.1.9 — 2026-03-15

List management commands and targeted sync.

### Features

- **`trache list create <name>`**: create a new list on the board (API-direct)
- **`trache list rename <id-or-name> <new-name>`**: rename a list (API-direct)
- **`trache list archive <id-or-name> --yes`**: archive a list (API-direct)
- **`trache pull --list <name>`**: pull all cards in a single list without full-board pull
- **`trache push --card <uid6>`**: push changes for a single card
- **`trache sync --card <uid6>`**: push then pull a single card

### API

- `TrelloClient.create_list()`, `rename_list()`, `archive_list()`
- Index helpers: `add_list_to_index()`, `update_list_in_index()`, `remove_list_from_index()`

### Agent Block

- Reference block updated with list and targeted sync commands

## 0.1.8 — 2026-03-14

Push reporting, error handling, comment/checklist/label management commands.

### Features

- **`trache comment edit <uid6> <comment_id> <text>`**: edit a comment (API-direct)
- **`trache comment delete <uid6> <comment_id> --yes`**: delete a comment (API-direct)
- **`trache checklist create <uid6> <name>`**: create a new checklist on a card (local-first)
- **`trache label create <name> [--color]`**: create a board label (local-first)
- **`trache label delete <name>`**: delete a board label with card-usage warning (local-first)
- **Push progress reporting**: `push` prints `[n/m] description` lines during execution
- **`--raw` push output**: tab-separated output for script consumption

### Error Handling

- **Shared CLI error decorator**: `@handle_resolve_errors` catches `KeyError`, `ValueError`, `FileNotFoundError` for clean error output
- **Archived card guard**: edit commands warn when targeting an archived card; `--force` flag to proceed
- **Push exit code**: push now exits 1 when any card fails

### Diff Improvements

- **Deterministic sort**: added cards sorted by title for stable output
- **Label change tracking**: diff now reports label creates and deletes

## 0.1.7 — 2026-03-14

Bug fixes and validation improvements.

### Push Fixes

- **Partial push exit code**: push now exits with code 1 when any card fails, instead of silently returning 0
- **Invalid UID6 on push**: `push --card NOPE12` now gives a clear resolution error instead of "Nothing to push"
- **Temp UID6 in identifier block**: newly created cards now get a corrected identifier block with the real UID6 pushed back to Trello
- **Archive state for new cards**: locally created + archived cards are now created then archived on Trello in a single push
- **Pushed-and-archived message**: push reports "Card <UID6> (<title>) successfully pushed and archived" for the two-step workflow

### Pull Fixes

- **Deleted remote card**: `pull --force --card` on a deleted remote card now gives a user-friendly error instead of a traceback
- **Archived card cleanup**: `pull --card` on an archived card removes it from the discovery index
- **Dirty pull guard wording**: error message now says `--force` instead of `force=True`

### Validation & Warnings

- **Label validation at edit time**: `add-label` now validates against `labels.json` and rejects unknown labels with guidance
- **Duplicate list name detection**: `resolve_list_id` now errors on ambiguous list names with IDs for disambiguation
- **Archived card edit warning**: edit commands warn when targeting an archived card (edit still proceeds)
- **ValueError handling**: shared CLI error decorator now catches `ValueError` for clean error output

## 0.1.6 — 2026-03-14

Agent block improvements and CLI display polish.

### Agent Block & Init

- **Install block rewrite**: canonical workflow line, board context injection, "user instructions override" clause, read vs pull clarification
- **Reference block tightened**: ephemeral header, subcommands section, elevated comment warning, default workflow line
- **Init flow**: next-step hint pointing to `trache agents --reference`, labeled human note panel, board name passed through

### CLI Display

- **card show**: resolve list name, unified status line (ARCHIVED/MODIFIED/CLEAN), inline checklist items with IDs, title truncation at 120 chars
- **card move**: show resolved list name instead of raw ID
- **comment list**: display comment IDs
- **pull --list**: echo resolved list name in output

### Infrastructure

- `resolve_list_name()` helper in `cache/index.py`

## 0.1.5 — 2026-03-13

AI agent onboarding command.

### Features

- **`trache agents` command**: prints a short install block for permanent insertion into CLAUDE.md/AGENTS.md, with `--reference` flag for on-demand command/workflow reference
- **Init agent guidance**: `trache init` now prints the agent setup block and a human fallback note after initialising

### Housekeeping

- Removed validation report files from project root

## 0.1.4 — 2026-03-13

Onboarding, documentation, packaging, and Claude skill integration release.

### Documentation

- **README overhaul**: complete rewrite with all commands, options, semantics, validation status, and install instructions
- **CLAUDE.md update**: refocused as agent operating policy with full command coverage and pointer to skill

### Packaging

- **License metadata fix**: changed `license = "MIT"` (PEP 639) to `license = {text = "MIT"}` for compatibility with older pip/packaging versions
- **Install validation**: confirmed `pip install -e .` and `pip install .` both work cleanly

### Claude Integration

- **Trache skill**: added `.claude/skills/trache/SKILL.md` — command cookbook, workflow guide, troubleshooting, and examples

## 0.1.3 — 2026-03-13

Mock-backed workflow validation, documentation update, label CLI commands.

### Features

- **Label CLI**: `trache card add-label` and `trache card remove-label` commands
- **Checklist help clarity**: improved CLI help text for checklist commands
- **Friendly error handling**: user-facing error messages for common failure modes

### Tests

- Mock-backed coverage for remaining command paths (card create, archive, move, comment, checklist mutations)

## 0.1.2 — 2026-03-12

Follow-up audit clearance release.

### Fixes

- Identifier block separator accumulation on push/pull cycles
- Remaining audit findings cleared

## 0.1.1 — 2026-03-12

Audit remediation release. Closes 12 of 13 findings from the initial implementation audit (F-012 rate limiting deferred).

### Breaking Changes

- **Cache layout migration**: First `trache pull` after upgrade will migrate:
  - Checklists: `checklists/<checklist_id>.json` → `clean/checklists/<card_id>.json` + `working/checklists/<card_id>.json`
  - Indexes: 4 separate files → single `indexes/index.json`
  - Card files: description sections now use HTML comment markers alongside headings
- **Checklist CLI commands**: `check`, `uncheck`, `add-item` are now local-first (edit working copy, push to sync) instead of pushing immediately to API
- **Operator action**: Run `trache push` before upgrading to avoid losing unpushed checklist edits in old format

### Trust & Safety

- **Dirty pull guard** (F-005): `pull` refuses to overwrite dirty working state unless `--force` is passed
- **Sync partial-failure safety** (F-008): `sync` skips full pull if push had errors, preserving local state
- **New card identifier injection** (F-004): `push` now injects identifier block for newly created cards
- **Label push support** (F-006): label changes are now pushed to Trello with fail-loud resolution

### State Integrity

- **content_modified_at preservation** (F-002): re-pull preserves `content_modified_at` when content hasn't changed (comments/member changes no longer corrupt it)
- **Checklist clean/working split**: checklists now follow the same local-first model as cards
- **Temp card discovery** (F-003): newly created cards are immediately resolvable by UID6 via index update
- **Typed diff comparisons** (F-007): label order no longer produces false diffs
- **Description boundary hardening** (F-009): HTML comment markers prevent description corruption from cards containing `# Checklist Summary` headings

### Code Quality

- **Index consolidation**: 4 JSON files → single `index.json` with sections
- **`fmt_date` made public** (F-010): renamed from `_fmt_date`
- **Redundant UID6 loop removed** (F-011)
- **UTC assertion in `_fmt_dt`** (F-013): catches non-UTC datetimes early
- **Makefile** (F-001): uses `PYTHON ?= python3` for portability

### Tests

- 82 tests (up from 43): new suites for working mutations, pull safety, content_modified_at semantics, labels, checklists, description parsing, index operations

## 0.1.0 — 2026-03-12

Initial implementation. Local-first Trello cache with Git-style pull/push/sync.
