# Changelog

## 0.3.7 — 2026-03-20

Final audit remediation: fail-closed comment guards, input length validation, `--json` flag, schema migration framework, and `trache health` diagnostic command.

### Security

- **Fail-closed comment confirmation** (F-013): `comment add`, `comment edit`, and `comment delete` now use a unified `_confirm_api_direct` guard — machine mode and non-TTY stdin always exit 1 without `--yes`; human mode with TTY prompts with default=No. The old warn-and-proceed path in human mode is removed. `comment delete` gains the `-y` alias for `--yes`.

### Validation

- **Input length validation** (F-016): `edit_title`, `edit_description`, and `create_card` now validate against Trello's 16,384-char API limit at the working layer. Descriptions are checked against a conservative 16,084-char limit (300-char identity block budget). Push layer performs a second check on the rendered description (with identity block injected) against the full 16,384-char limit.

### Features

- **`--json` CLI flag** (O-005): `trache --json <command>` forces machine-readable JSON output for a single invocation, overriding `TRACHE_HUMAN=1`.
- **`trache health`** (O-008): 6-layer diagnostic probe checking board config, database schema, DB pragmas, auth env vars, API connectivity, and sync state. `--local` skips the API check. Exits 0 on all-pass, 1 on any failure. First-pull tip suggests running `trache health`.
- **Schema migration framework** (O-011): `_MIGRATIONS` registry, `_run_migrations`, and `_check_and_migrate` in `db.py` — drives incremental DDL from `schema_version` table. Future schema changes register a migration function keyed by target version. Handles corrupt DB, future-version, and missing-migration errors.

### Tests

- Updated `TestCommentGuards`: human mode now asserts exit 1 (fail-closed); 3 new tests for edit/delete non-TTY and machine mode.
- New `TestJsonFlag` (2 tests): `--json` forces machine output.
- New `TestInputLengthValidation` (6 tests): title/description overflow and at-limit checks.
- New `TestPushDescriptionOverflow` (2 tests): rendered description and title overflow at push time.
- New `TestSchemaMigration` (5 tests): noop, future-version, apply-and-bump, rollback-on-failure, missing-migration.
- New `tests/test_health.py` (9 tests): all-pass local, no config, bad schema, missing auth, API pass, API 401, machine output, exit code, `--local` skips API.

## 0.3.6 — 2026-03-20

Audit batches 5–6 remediation: DB performance/resilience, datetime consolidation, and diff single-connection refactor.

### Performance

- **`executemany` for card inserts** (O-002): `write_cards_batch` and `write_full_snapshot` use `executemany` instead of per-card `execute` loops.
- **Single-connection `compute_diff`** (O-004): diff engine opens one DB connection for the entire diff instead of N+1 connections per card/checklist/label query.
- **Resolve push filter once** (F-017): `push_changes` resolves `card_filter` to a full ID once up front, replacing per-change `_matches_filter` calls that each re-resolved the UID6.

### Reliability

- **`PRAGMA synchronous=NORMAL`** (O-003): every connection now sets `synchronous=NORMAL` for WAL-safe durability with reduced fsync overhead.
- **Configurable `busy_timeout`** (O-007): `TRACHE_DB_BUSY_TIMEOUT` env var (ms, default 10000) prevents `database is locked` errors under concurrent access; validated as positive integer.
- **WAL checkpoint after snapshot** (O-014): `write_full_snapshot` runs a `TRUNCATE` checkpoint on a fresh connection after commit, preventing WAL file growth.

### Refactoring

- **`_datetime.py` extraction** (F-008/O-009): `_fmt_dt`/`_parse_dt` consolidated from `db.py` and `store.py` into `cache/_datetime.py` with strict type annotations; hard cutover, no legacy fallbacks.

### Tests

- New `TestConnectionPragmas` (5 tests): synchronous=NORMAL, busy_timeout default/override/invalid/zero/negative.
- New `TestFullSnapshot.test_write_full_snapshot_card_count_both_copies` (O-002): 50-card behavioural snapshot test.
- New `TestFullSnapshot.test_wal_checkpoint_after_snapshot` (O-014): checkpoint smoke test.
- New `TestPushCardFilter` (2 tests): filtered push selects only target card; unresolvable filter raises KeyError.
- New `tests/test_datetime.py` (10 tests): `fmt_dt`/`parse_dt` unit tests including roundtrip, timezone normalisation, fractional seconds.
- New `TestComputeDiffSingleConnection`: asserts exactly one DB connection opened during `compute_diff`.

## 0.3.5 — 2026-03-20

Audit batches 2–4 remediation: 10 findings across data integrity, API client hardening, and code consolidation.

### Fixed

- **Large-board `delete_stale_cards` safety** (F-004): replaced unbounded `IN (?,?,…)` clause with temp-table approach to avoid SQLite's `SQLITE_MAX_VARIABLE_NUMBER` limit on boards with 1000+ cards.
- **Tri-state board context for `status`** (F-018): `status` now distinguishes uninitialised (no boards), configured (normal diff), and broken config (error surfaces) — no longer masks real config errors as "Clean".
- **POST retry safety** (F-006): `_retry` now accepts `idempotent` parameter; POST requests no longer retry on 5xx/transport errors, preventing duplicate side effects (comments, cards).
- **Debug log for unparseable Trello dates** (F-014): `_parse_trello_date` emits a DEBUG log on malformed date strings instead of silent `None`.
- **Batch archived-card guard** (F-011): all 9 mutation batch handlers now reject operations on archived cards; `create` and `archive` are intentionally unguarded.
- **`create_checklist` extracted to `working.py`** (F-012): thin CLI delegation replaces duplicated logic in `checklist.py`.

### Changed

- **Configurable API timeout** (O-012): `TRACHE_API_TIMEOUT` env var overrides the default; CLI default raised from 30s to 60s via `get_client_and_config`.
- **DRY comment commands** (F-005/O-006): 4 duplicated client-init blocks in `comment.py` replaced with shared `get_client_and_config`, inheriting the 60s timeout.
- **`ChecklistMutator` Protocol** (O-010): typed callback protocol for `_checklist_update` in `working.py`.

### Tests

- New `tests/test_client_retry.py` (O-001): 9 test classes covering retry behaviour with `httpx.MockTransport` — 429 Retry-After, exponential backoff, POST no-retry on 5xx/transport, client errors, max retries, success path.
- New `TestStatusBoardContext` (3 tests): uninitialised, no-boards-dir, broken-config.
- New `TestBatchArchivedGuard` (4 tests): edit-title blocked, checklist check blocked, archive allowed, error isolation.
- New `TestCreateChecklist` (3 tests): success + persistence, duplicate raises, card dirtied.
- New `TestParseTrelloDateLog` (2 tests): malformed date logs, empty/None no-log.
- New `TestApiTimeoutEnvVar` (3 tests): default 60s, env var override, invalid fails fast.
- Large-board `delete_stale_cards` test (1200 cards).

## 0.3.4 — 2026-03-20

### Changed
- **API stats are now per-client, not process-global.** `TrelloClient.get_stats()` replaces the module-level `get_api_stats()` / `reset_api_stats()` functions. Each client instance tracks its own call count and latency independently. _(F-001)_
- **Onboarding grandfather clause removed (hard cutover).** `SyncState.load()` no longer auto-acks boards that predate the onboarding gate. Boards that have already been acked are unaffected. Any board that has not yet been acked must now run `trache agents --ack` explicitly. _(F-003)_

### Fixed
- **OutputWriter singleton** is now thread-safe via double-checked locking. _(F-002)_
- **Board override** replaced `threading.local()` with plain module-level variable to eliminate `AttributeError` risk. _(F-007)_
- **Rich markup injection** in `card show`, `checklist show`, and `comment list` — user-sourced text (descriptions, labels, checklist names, comment text) is now escaped to prevent mangled output from `[WIP]`, `[BLOCKED]`, etc. _(F-010)_

## 0.3.3 — 2026-03-19

Onboarding ack gate: agents must acknowledge the install block before `pull`/`sync` are unlocked, preventing the common failure mode where agents parse init JSON for success signals and skip the install block entirely.

### Onboarding Gate

- **`trache agents --ack`**: new flag that sets `onboarding_acked = true` in `state.json` and unlocks `pull`/`sync`; mutually exclusive with `--reference`; outputs Rich confirmation (human) or `{"ok": true, "onboarding_acked": true}` (machine)
- **`trache pull` / `trache sync` gated**: both commands now check `onboarding_acked` before proceeding; if false, exit 1 with guidance to run `trache agents` then `trache agents --ack`
- **Grandfathering**: existing boards with a prior `last_pull` timestamp are auto-acked on `SyncState.load()` so they are not broken by the new gate
- **`SyncState.onboarding_acked`**: new boolean field (default `false`) persisted in `state.json`

### Init Output (Machine Mode)

- **Removed `install_block` from JSON**: machine-mode `init` no longer embeds the install block as a JSON string field (agents were ignoring it)
- **Added `next_step: "ACTION REQUIRED"`**: JSON payload now signals the agent to take action
- **Stderr action notice**: plain-text `ACTION REQUIRED` block emitted to stderr with instructions to run `trache agents` and `trache agents --ack`

### Tests

- 248 tests: new `TestOnboardingAckGate` suite (9 tests) covering pull/sync blocking, ack persistence, machine-mode output, mutual exclusivity, grandfathering, and new-board behaviour; updated `test_init_machine_output` for new JSON shape

## 0.3.2 — 2026-03-18

Non-interactive safety: machine-mode guards for init, comment commands, and a hardened agent install block.

### Non-Interactive Guards

- **`trache init` without `--board-id`**: in machine mode or non-TTY stdin, emits a structured JSON error instead of hanging on an interactive prompt
- **`trache comment add` / `comment edit`**: now require `--yes` in machine mode to prevent accidental API-direct writes; human mode prints a warning but proceeds
- **`trache comment delete`**: error message updated for consistency with add/edit guard wording
- **Comment JSON output**: all comment commands now include `api_direct: true` field; `comment list` wraps results in `{api_direct, comments}` object

### Agent Install Block

- **Rewritten `INSTALL_BLOCK_TEMPLATE`**: stronger MCP/API fallback guardrail, explicit pull/push/sync rule, read-only-by-default posture, UID6 explanation, prominent comment API-direct warning, actionable `agents --reference` directive, and a concrete example workflow
- **Agent reference block**: updated to document `--yes` requirements for comment commands

### Tests

- 239 tests: new suites for init non-interactive guard (2) and comment command guards (4)

## 0.3.1 — 2026-03-17

### License

- **License changed from MIT to AGPL-3.0-or-later**: updated `LICENSE`, `pyproject.toml`, and `README.md`. All prior versions (0.1.0–0.3.0) were released under MIT; from this version onward the project is licensed under the GNU Affero General Public License v3.0 or later.

## 0.3.0 — 2026-03-15

Major release: SQLite storage backend, machine-first output layer, batch operations, staleness checks, and three rounds of audit remediation.

### Breaking Changes

- **Storage backend**: file-based `clean/`, `working/`, `indexes/` directories replaced by a single `cache.db` SQLite database with WAL mode. Existing file-based caches are auto-migrated on first command (two-phase sentinel-guarded migration with crash recovery).
- **File layout**: `.trache/boards/<alias>/` now contains `config.json`, `cache.db`, and `state.json` only. Old directories are removed after migration.
- **Machine-first output**: default output is now TSV/JSON (set `TRACHE_HUMAN=1` for Rich-formatted human output). Commands that previously used `--raw` now emit machine output by default.

### Storage Layer

- **SQLite persistence** (`cache/db.py`): cards, checklists, labels, and lists stored in a single WAL-mode database with `(id, copy)` composite keys for clean/working separation
- **Atomic full-board write**: `write_full_snapshot()` replaces all data in one transaction
- **Atomic card-pull write**: `write_card_pull()` writes card + checklists to both clean and working in a single transaction, eliminating crash-divergence risk (F-001/F-002)
- **Index compatibility shim** (`cache/index.py`): thin facade delegates to `db.py` for backward compatibility during migration; CLI modules progressively migrated to direct `db.py` calls (F-004/F-005)

### Machine-First Output

- **Dual-mode output layer** (`_output.py`): `OutputWriter` emits TSV/JSON to stdout in machine mode, Rich-formatted text in human mode; errors go to stderr as JSON in machine mode
- **`OutputWriter.error(**extra)`**: structured error payloads with arbitrary extra fields (e.g., `available_boards` on board switch failure)
- **API stats on stderr**: machine mode emits `{"api_calls":N,"api_ms":M}` to stderr for AI observability
- **`trache init`**: machine mode returns JSON with `install_block` field (raw text for CLAUDE.md); Rich agent guidance panels gated behind `is_human`
- **`trache sync`**: machine mode returns `{"ok", "dry_run", "push", "pull"}` with full push result and pull summaries including `card_summaries` and `list_summaries`
- **`trache push`**: machine output via shared `_serialise_push_result()` helper (also used by `sync`)
- **`trache card show`**: JSON includes `list_name`, `due`, and `checklists` fields
- **`trache card edit-desc`**: JSON includes updated `description`
- **`trache card create`**: JSON includes `list_id`
- **`trache card move`**: JSON includes both `list_id` and `list_name`
- **`trache pull --card` / `sync --card`**: JSON includes full card data (`labels`, `due`, `closed`, `list_name`, `checklists`) — eliminates follow-up `card show`
- **`trache pull --list`**: card summaries use resolved `list_name`
- **`trache label delete`**: JSON includes `affected_cards` and `affected_count`
- **`trache label list`**: includes label `id` column; no longer silently drops unnamed labels
- **`trache list archive`**: JSON includes list `name`
- **`trache board offboard`**: JSON includes `archived_on_trello` and `new_active_board`
- **`trache board switch`**: error includes `available_boards` in machine stderr JSON
- **`trache status`**: empty-state fast-path JSON includes `label_changes` key (matches normal shape)
- **Empty-state output**: `board list` and `list show` emit proper empty output in machine mode instead of silence/exit(1)

### New Commands

- **`trache stale`**: one cheap API call to check if the board has remote changes since last pull; returns `{"stale", "local_activity", "remote_activity"}`
- **`trache batch run`**: execute multiple local-first commands from stdin (one per line); returns JSON array of results; supports `card` and `checklist` subcommands

### Batch Operations

- Dispatch table for `card edit-title`, `card edit-desc`, `card move`, `card create`, `card archive`, `card add-label`, `card remove-label`, `checklist check`, `checklist uncheck`, `checklist add-item`, `checklist remove-item`
- Batch handlers aligned with CLI equivalents: `edit-desc` returns `description`, `move` returns `list_id`/`list_name`, `create` returns `list_id`
- Error isolation: individual command failures don't halt the batch; each result includes `ok` and `error` fields

### Shared Checklist Mutations (F-006)

- **Extracted to `working.py`**: `check_checklist_item()`, `uncheck_checklist_item()`, `add_checklist_item()`, `remove_checklist_item()` with idempotency guards
- `checklist.py` and `batch.py` both delegate to shared functions instead of duplicating logic
- All raise `KeyError` on not-found (matches `handle_resolve_errors` in CLI layer)

### API Efficiency

- **`pull_list` batch checklists**: single `get_board_checklists()` call replaces N per-card `get_card_checklists()` fetches

### Facade Migration

- **`comment.py`**: migrated 4 sites from `trache.cache.index.resolve_card_id` to `trache.cache.db.resolve_card_id` (F-004)
- **`list_cmd.py`**: migrated all `trache.cache.index` imports to direct `trache.cache.db` calls (F-005)

### Documentation

- **CLAUDE.md**: updated file layout to reflect SQLite/multi-board structure; added `trache stale` and `trache batch run` to command reference

### Tests

- 250 tests (up from 189): new suites for `write_card_pull` atomicity, shared checklist mutations (idempotent check/uncheck, not-found errors, add/remove), pull clean/working consistency, sync machine output, init machine output
- Removed 2 dead skipped tests for file-based code paths superseded by SQLite

## 0.2.3 — 2026-03-15

Audit v2 remediation. Addresses 8 findings (F-001–F-008) and 6 opportunities (O-001–O-006) from the post-remediation audit.

### Data Integrity

- **Checklist push for new cards** (F-001/O-001): `_push_new_card()` now reads the temp checklist JSON and creates checklists, items, and checked states on Trello before cleanup — previously checklists on locally-created cards were silently lost
- **Clean snapshot cleanup after archive** (F-002/O-002): pushing a deleted card now removes `clean/cards/*.md`, `clean/checklists/*.json`, `working/checklists/*.json`, and the index entry — previously archived cards were re-detected as deleted on every subsequent push
- **Atomic active-board write** (F-004/O-004): `set_active_board()` now uses `atomic_write()` instead of `write_text()` for crash safety
- **Atomic legacy migration** (F-008): `_migrate_legacy()` uses a copy→marker→delete two-phase approach; interrupted migrations resume from the marker on next invocation

### CLI Correctness

- **Card show displays checklists** (F-005/O-003): `show_card()` now loads checklists from the separate JSON file into `card.checklists` — previously the checklist display code was dead because checklists aren't stored in card markdown
- **Rich markup escaping**: `[x]` and `[ ]` checklist markers are now escaped to prevent Rich from interpreting them as markup tags
- **Path containment fix** (F-003/O-005): `offboard` safety check uses `Path.is_relative_to()` instead of string-prefix comparison, preventing false positives on sibling directories like `.trache/boardsX/`

### Observability

- **API stats display** (O-006): `pull`, `push`, and `sync` commands now print `(N API calls, X.Xs)` at the end of each invocation

### Efficiency

- **Guard-archived returns card** (F-006): `guard_archived()` now returns the loaded `Card` object so callers can pass `card.id` directly, eliminating a redundant `read_working_card()` call per guarded command

### Tests

- 189 tests (up from 180): new suites for checklist push on new cards (3), archive cleanup idempotency (2), card-show checklist display (2), offboard path safety (1), legacy migration resumption (1)

## 0.2.2 — 2026-03-15

Full system audit remediation. Addresses all 14 findings (F-001–F-014) and all 11 opportunities (O-001–O-011) from the 2026-03-15 audit.

### Sync Layer Correctness

- **Scoped dirty guard** (F-001/O-004): `pull --card` and `pull --list` now check only the targeted card(s) for unpushed changes, not the entire board. Dirty card A no longer blocks refresh of unrelated card B
- **Eliminated extra GET on push** (F-003): removed `_check_remote_conflict` and its redundant per-card API call; conflict detection now uses stored timestamps
- **Scoped checklist fetch** (F-006): `pull --list` now fetches checklists per card instead of the entire board
- **Batch index writes** (O-001): `pull --list` loads index once, applies all card updates, writes once (was N read/write cycles)
- **Card timestamps in targeted pulls** (F-014): `pull --card` and `pull --list` now update `SyncState.card_timestamps`, fixing false-positive conflict warnings
- **Skip redundant dirty check on re-pull** (O-002): post-push re-pulls skip the dirty guard entirely via `_skip_dirty_check` flag
- **TypeAdapter for checklist serialization** (O-009): replaced `json.dumps(model_dump())` with Pydantic `TypeAdapter.dump_json()`

### Write Safety

- **Atomic checklist writes** (F-002): `_save_checklists_for_card` in `checklist.py` now uses `atomic_write` (was bare `write_text`)
- **Atomic label writes** (O-011): `_save_labels` in `label.py` now uses `atomic_write`
- **Atomic label push writes** (O-010): `_push_label_creates` receives pre-loaded `labels_data` (avoids redundant file read) and writes atomically

### API Observability & Resilience

- **Retry-After support** (O-005): 429 retries now parse and respect the `Retry-After` header, with jitter
- **API call tracking** (O-008): `_api_call_count` and `_api_total_ms` tracked across all HTTP methods; `get_api_stats()`/`reset_api_stats()` exposed; stats reset on each CLI invocation
- **`__del__` safety net** (F-004): `TrelloClient` now has `__del__` for defence-in-depth connection cleanup

### CLI Efficiency

- **Single `_cache_dir()` resolution** (F-005): label commands resolve `cache_dir` once per invocation, not per helper call
- **Fixed double `_cache_dir()` in card move** (F-010): resolved once, passed to both `guard_archived` and `move_card`
- **Consolidated client creation** (O-007): `list_cmd.py` now imports `get_client_and_config` from `_context` instead of duplicating it
- **Thread-local board override** (F-007): replaced module-level `_active_board_override` global with `threading.local()` for test isolation
- **Removed filesystem scan fallback** (O-003): `resolve_card_id` no longer scans `working/cards/*.md`; raises `KeyError` with guidance to `trache pull`

### Code Quality

- **Public `fields_equal` API** (F-012): renamed from `_fields_equal` in `diff.py`; updated import in `pull.py`
- **Removed `DEFAULT_CACHE_DIR` alias** (F-009): replaced with `TRACHE_ROOT` in 3 call sites
- **Hardened `_parse_dt`** (F-008): strips fractional seconds for Python 3.10 `fromisoformat()` compat
- **Cleaned up `_atomic.py`** (F-011): replaced `_fd_closed` exception-based control flow with boolean flag
- **Simplified `_BLOCK_PATTERN` regex** (F-013): removed trailing `(?:---\s*\n)*` cleanup group (prior bug long remediated)
- **Shared test helpers** (O-006): extracted `make_mock_client()` and `setup_cache()` to `conftest.py`; deduplicated from 3 test files
- **Autouse fixture for board override reset**: prevents test pollution from thread-local state

### Tests

- 180 tests (up from 169): new suites for scoped dirty guard, card timestamp updates, batch index operations, `_parse_dt` edge cases, identity regex regression, unindexed card error

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
