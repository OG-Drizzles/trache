# Trache — CLAUDE.md

This repo is **Trache**: a lightweight, local-first Trello cache with Git-style sync — optimised for on-machine AI workflows.

## Project Goals

Develop, build, implement and maintain a lightweight, local-first, AI token saving, automation heavy platform that maximises token efficiency through smart and automated workflows, machine optimised processes and API connectivity, foregoing the need for MCP.

## 0) Non-Negotiables (read and apply every session)

**Truth anchors:** when diagnosing issues, cite the key anchor (log line, /health output, endpoint response, command output) and state the root cause. Always provide evidence, code traces, evidence-backed assessments and RCA — no vibes-based "maybe this will work" guessing. Do not "wing it" on ports/sockets/service names: confirm in docs or systemd units.

**No quick fixes:** solve the root cause with production-grade methodology (tests, observability, rollback), not band-aids. ALWAYS use best practice software development and engineering methodology.

**Development philosophy:** this project follows Kaizen (continuous improvement), Shokunin (craftsman's pride in quality), and Ikigai (purposeful work) — in Western terms, Agile methodologies with a bias toward engineering excellence.

**Prompt ambiguity:** if the user references "this/these/that/the above" without a concrete pointer, ask a clarifying question immediately.

**Refactor strategies:** use "hard cutover" practices with sweeping compatibility verification, rather than "legacy fallbacks" and "compat shims".

**Efficiency & future proofing:** always design systems with future proofing and efficiency in mind, especially in hot paths and time sensitive modules & operations, to reduce processing times, CPU overhead & overall latency.

## 1) Claude's Role on This Repo

Claude Code is the primary implementer for codebase changes (reads repo, edits files, runs checks, commits).
Default behaviour:

- Implement scoped changes safely using production-grade, best practice software development and engineering methodology
- Adhere to and make recommendations based on the project goals and non-negotiables (user instructions may sometimes override these)

### Subagent Model Defaults

Default subagent model is **Sonnet** (set via `CLAUDE_CODE_SUBAGENT_MODEL` in `~/.claude/settings.json`). You **must** explicitly override when spawning sub-agents, following these rules:

**If Primary agent is Opus:**

| Subagent Type | Model | Action |
|---|---|---|
| Explore | Haiku | Must pass `model: "haiku"` |
| Plan | Opus | Must pass `model: "opus"` |
| claude-code-guide | Haiku | Must pass `model: "haiku"` |
| statusline-setup | Opus | Must pass `model: "opus"` |

**If Primary agent is Sonnet:**

| Subagent Type | Model | Action |
|---|---|---|
| Explore | Haiku | Must pass `model: "haiku"` |
| claude-code-guide | Haiku | Must pass `model: "haiku"` |

## 2) Engineering Quality Bar (mandatory)

- Prefer durable fixes over expedient patches. If a mitigation is required, label it clearly as TEMP, make it fail-safe, and create a follow-up task in the same mission.
- Always start from a truth anchor (log line / endpoint / artefact) and state the root cause before changing code.
- Changes must be restart-safe, idempotent where relevant, and avoid introducing new state ambiguity.
- Include tests or a reproducible verification script for the behaviour you changed (unit/integration/smoke), plus runtime verification (health endpoints, key metrics, or controlled simulation).
- If behaviour/interfaces/ops change, update docs and add a changelog-style note (what/why/impact). Don't "paper over" drift.
- Apply Kaizen: every change should leave the codebase measurably better than before, with Shokunin-level craftsmanship.

---

## 3) Trache CLI — Operating Policy

Use Trache instead of raw Trello API/MCP calls. All edits happen locally; nothing hits the API until `trache push`.

### Preferred Workflow

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

### Key Concepts

- **UID6**: Last 6 chars of card ID (uppercase). Use for all card references. Case-insensitive input.
- **Clean vs Working**: `.trache/clean/` is baseline from last pull. `.trache/working/` is editable. Diff compares clean vs working.
- **Local-first**: All edits happen locally. Nothing hits the API until `trache push`.
- **Dirty pull guard**: `trache pull` refuses if dirty. Use `--force` to override.
- **Index**: `.trache/indexes/index.json` — one read = full board orientation.

### When to Use Specific Commands

- **`trache pull --card <uid6>`** — refresh one card. Prefer over full-board pull.
- **`trache pull --list "List Name"`** — refresh one list.
- **`trache push --card <uid6>`** — push only one card.
- **`trache sync`** — push then full pull. Use when you want a clean slate after pushing.
- **`trache card create <list> <title>`** — create card locally. Add `--desc` for description.
- **`trache card archive <uid6>`** — archive locally (pushed on `trache push`).

### Comment Commands (Not Local-First)

- `trache comment add <uid6> <text>` — pushes immediately to API.
- `trache comment list <uid6>` — fetches from API.

### Avoid

- Full-board pull unless necessary — prefer targeted pull
- Parsing `.trache/` files directly — use CLI commands
- Committing `.trache/` to git — it's a local cache

### Caveats

- Comment commands hit the API directly (not local-first)
- Rate limiting/retry not yet implemented — avoid rapid-fire API calls
- Card create and archive are mock-validated only (not yet live-tested)

### Detailed Reference

For full command syntax, examples, and troubleshooting, invoke the `/trache` skill.

### File Layout

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
