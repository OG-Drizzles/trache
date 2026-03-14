# Changelog

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
