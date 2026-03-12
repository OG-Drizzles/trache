# Trache Phase 2 — Real-World Validation Report

**Date:** 2026-03-12
**Board:** Trache Test Board - Phase 2 Validation (`69b3280cc728123dcbe3d297`)
**Board URL:** https://trello.com/b/u0EqMg4J
**Trache Version:** 0.1.2
**Baseline Tests:** 94/94 pass, lint clean

---

## Board Setup

- **3 lists:** To Do, In Progress, Done
- **4 labels:** Bug (red), Feature (green), Urgent (orange), Low Priority (blue)
- **7 cards** across lists with descriptions, labels, and checklists
- **2 checklist-bearing cards:** 55147B (1 checklist, 4 items), 67672F (2 checklists, 5 items)
- **1 card with comment** for last_activity testing

---

## Scenario Results

### Scenario A — Pull / Read / Local Discovery

| Test | Result | Notes |
|------|--------|-------|
| `trache init --board-id` | PASS | Config created correctly |
| `trache pull` (full board) | PASS | 7 cards, clean/working/indexes all populated |
| Cache structure verification | PASS | clean/, working/, indexes/index.json, checklists/ all correct |
| `trache card list` | PASS | All 7 cards with correct UID6, list, title |
| `trache card show <uid6>` | PASS | Description, labels shown correctly |
| Case-insensitive UID6 | PASS | `eefede` resolves same as `EEFEDE` |
| Invalid UID6 | **P2** | Raw `KeyError` traceback instead of user-friendly message |
| Labels pulled correctly | PASS | Multi-label cards (Bug + Urgent) preserved |
| Index structure | PASS | cards_by_id, cards_by_uid6, cards_by_list, lists_by_id all correct |
| No identifier block leakage | PASS | Local description section clean of Trello identifier block |

### Scenario B — Card Mutations

| Test | Result | Notes |
|------|--------|-------|
| Edit title | PASS | `edit-title` → status detects → diff shows → push updates Trello |
| Edit description | PASS | `edit-desc` → push → Trello description updated |
| Move card to list | PASS | `move` by list name → push → Trello `idList` updated |
| Label add (frontmatter) | PASS | Add label to YAML → status detects → push updates Trello |
| Label remove (frontmatter) | PASS | Remove label from YAML → push removes from Trello |
| Card create | PASS | `create` → temp UID6 → push → real UID6 assigned, card on Trello |
| Card archive | PASS | `archive` → push → `closed=true` on Trello |
| Comment add | PASS | `comment add` → comment appears on Trello (direct API, not local-first) |
| Comment list | PASS | `comment list` → shows comments with author/date |
| Missing: label add/remove CLI | **P3** | No CLI command for label mutation — requires manual frontmatter edit |

### Scenario C — Checklist Mutations

| Test | Result | Notes |
|------|--------|-------|
| `checklist show` | PASS | Both single and multi-checklist cards display correctly |
| `checklist check` | PASS | Item marked complete locally, reflected after push |
| `checklist uncheck` | PASS | Item marked incomplete locally, reflected after push |
| `checklist add-item` | PASS | New item with temp ID, replaced with real ID after push |
| `checklist remove-item` | PASS | Item removed locally, removed from Trello after push |
| Multi-checklist card | PASS | Both checklists on 67672F handled correctly |
| Temp ID reconciliation | PASS | Temp IDs replaced during push reconciliation (no re-pull needed) |
| `add-item` takes name not ID | **P3** | Docs ambiguous — `<checklist>` param is checklist name, not ID |

### Scenario D — Identity / Semantics

| Test | Result | Notes |
|------|--------|-------|
| Identifier block on Trello | PASS | Block with Card Name, dates, UID6 present after push |
| Identifier block stripped locally | PASS | Not in local description content after pull |
| `content_modified_at` preservation | PASS | Stays unchanged when only comment added (non-content activity) |
| `last_activity` independence | PASS | Bumped by comment while `content_modified_at` preserved |
| **Identifier block accumulation** | **P1 FIXED** | `---` separator accumulated on each push/pull cycle — **fixed** |

### Scenario E — Safety Checks

| Test | Result | Notes |
|------|--------|-------|
| Dirty pull refusal | PASS | "Working copy has unpushed changes" message, pull blocked |
| `pull --force` | PASS | Overwrites working copy, restores clean state |
| `push --dry-run` | PASS | Reports changes but sends nothing to Trello |
| Push with no changes | PASS | "Nothing to push." |

---

## Defects Found

### P1 — Identifier Block Separator Accumulation (FIXED)

- **File:** `src/trache/identity.py`
- **Bug:** `BLOCK_SEPARATOR = "\n---\n\n"` added an extra `---` after the identifier block's closing `---`. The strip regex only matched the block's own delimiters, leaving the separator behind. Each push/pull cycle added another `---` to the description.
- **Impact:** Description corruption — horizontal rules accumulate in card descriptions over repeated sync cycles. Data integrity issue.
- **Fix:** Changed `BLOCK_SEPARATOR` to `"\n\n"` and updated `_BLOCK_PATTERN` regex to consume trailing `---\n` separators (`(?:---\s*\n)*`). The regex update also cleans up already-corrupted descriptions on re-pull.
- **Verified:** 3 push/pull cycles with no accumulation. Existing tests pass (94/94).

### P2 — Raw KeyError on Invalid UID6

- **Symptom:** `trache card show XXXXXX` produces an unhandled `KeyError` with full traceback instead of a user-friendly "Card not found" message.
- **Severity:** P2 (annoying but not data-affecting)
- **Status:** Not fixed (out of scope for validation mission)

### P3 — Missing Label Add/Remove CLI Commands

- **Symptom:** README documents label add/remove but no CLI command exists. Must edit frontmatter YAML directly.
- **Severity:** P3 (polish — frontmatter editing works as a workaround)
- **Status:** Not fixed

### P3 — Docs Ambiguity on `add-item` Checklist Parameter

- **Symptom:** `trache checklist add-item <card> <checklist> <text>` — the `<checklist>` param accepts checklist **name**, not ID. Not obvious from help text.
- **Severity:** P3 (documentation)
- **Status:** Not fixed

---

## Files Touched

| File | Change |
|------|--------|
| `src/trache/identity.py` | Fix `BLOCK_SEPARATOR` and `_BLOCK_PATTERN` regex |

---

## Tests Run

- **Baseline:** 94/94 pass, lint clean
- **After fix:** 94/94 pass, lint clean
- **Real-board validation:** All scenarios above

---

## Recommendation

### Is Trache ready for normal personal-board use?

**Yes, with the P1 fix applied.** The fix in this mission resolves the only data-integrity issue found. All core workflows are proven against a real Trello board.

### Proven Workflows

- Full-board pull and targeted operations
- Card CRUD (create, read, edit title/desc, move, archive)
- Label round-trip (add/remove via frontmatter)
- Checklist full lifecycle (show, check, uncheck, add, remove)
- Comment add and list
- Identifier block inject/strip
- content_modified_at vs last_activity semantic distinction
- Dirty pull guard and force override
- Dry-run push
- Discovery index for cheap orientation
- UID6 resolution (case-insensitive)

### Unproven Workflows

- `trache sync` (push + pull combo) — not explicitly tested end-to-end against real board
- Targeted pull (`pull --card`, `pull --list`) — not tested
- Push failure simulation — not tested (would require mocking API errors)
- Concurrent editing scenarios — not tested
- Large board performance — not tested (7-card test board only)

### Next Highest-ROI Phase

1. **P2 fix: Friendly error messages** — wrap KeyError in CLI-friendly messages
2. **Label CLI commands** — `trache card add-label` / `trache card remove-label`
3. **Targeted pull validation** — prove `pull --card` and `pull --list` work against real board
4. **Sync command validation** — end-to-end `trache sync` test

---

## Rollback Notes

- Only one file changed: `src/trache/identity.py`
- Revert commit to restore previous behaviour
- Test board can be deleted via Trello UI or API
- No other system state was modified
