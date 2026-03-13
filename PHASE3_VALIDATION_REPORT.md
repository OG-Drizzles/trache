# Phase 3 Validation Report — Trache v0.1.3

## 1. Already proven on real board (Phase 2)

- Full board pull (`trache pull`)
- Card CRUD: edit-title, edit-desc, create, archive
- Label round-trip: add label locally → push → re-pull → label persists
- Checklist lifecycle: check, uncheck, add-item, remove-item → push → re-pull
- Comments: add, list
- Identity block: injected on push, stripped on pull, no accumulation
- Dirty pull guard: pull refused with local changes, `--force` overrides
- Dry-run push: `--dry-run` shows changes without API calls
- UID6 resolution: case-insensitive 6-char identifier → full card ID

## 2. Proven in mock-based tests (Phase 3)

| Scenario | Test location | Status |
|---|---|---|
| Sync happy-path (push + pull combo) | `test_pull_safety.py::TestSyncHappyPath` | Pass |
| Targeted pull `--card` | `test_pull.py::TestPullCard` (3 tests) | Pass |
| Targeted pull `--list` | `test_pull.py::TestPullList` (3 tests) | Pass |
| Push-failure preserves working copy | `test_push.py::TestPushFailurePreservation` (2 tests) | Pass |
| Stale-state local-wins behaviour | `test_push.py::TestStaleStateBehaviour` | Pass |
| Friendly errors on invalid UID6 | `test_cli.py::TestCardShowInvalidUID6` (2 tests) | Pass |
| Friendly errors on invalid list | `test_cli.py::TestCardListInvalidList` | Pass |
| `card add-label` (new + idempotent) | `test_cli.py::TestCardAddLabel` (3 tests) | Pass |
| `card remove-label` (existing + absent) | `test_cli.py::TestCardRemoveLabel` (2 tests) | Pass |
| `checklist add-item` help text clarity | `test_cli.py::TestChecklistAddItemHelp` | Pass |

**Total tests: 113/113 passing, lint clean.**

## 3. Still awaiting real-board confirmation

These scenarios are covered by mocks but have not been verified against a live Trello API:

- **Sync end-to-end**: `trache sync` against live Trello (push + full re-pull in one command)
- **Targeted pull against live Trello**: `trache pull --card <uid6>` and `trache pull --list <name>`
- **Stale-state with concurrent edits**: True concurrent edit scenario (another user modifies card between our pull and push). Current behaviour is local-wins; no server-side conflict detection.
- **Large-board performance**: Boards with 100+ cards — observation of pull/push timing (optional)
- **Label add/remove CLI against live board**: `trache card add-label` / `remove-label` → push → verify on Trello

### Prerequisites for real-board testing

```bash
export TRELLO_API_KEY=<your_key>
export TRELLO_TOKEN=<your_token>
trache init --board-id <board_id>
trache pull
```
