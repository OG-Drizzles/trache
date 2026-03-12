# Changelog

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
