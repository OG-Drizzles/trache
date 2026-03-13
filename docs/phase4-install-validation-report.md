# Trache Phase 4 — Onboarding / Install Validation Report

**Date**: 2026-03-13
**Version**: 0.1.4

## Install Validation

### Editable Install (`pip install -e .`)

| Environment | pip Version | Result |
|---|---|---|
| System Python 3.10 | pip 22.0.2 | PASS (after license fix) |
| .venv Python 3.10 | pip 22.0.2 | PASS |

**Issue found**: `license = "MIT"` (PEP 639 SPDX string format) caused `ModuleNotFoundError: No module named 'packaging.licenses'` in older pip build isolation environments. Fixed by changing to `license = {text = "MIT"}`.

### Standard Install (`pip install .`)

| Environment | pip Version | Result |
|---|---|---|
| .venv Python 3.10 | pip 22.0.2 | PASS |

### Entrypoint Validation

| Command | Result |
|---|---|
| `trache --help` | PASS — shows all 10 commands |
| `trache version` | PASS — shows `trache 0.1.4` |
| `trache pull --help` | PASS |
| `trache push --help` | PASS |
| `trache card --help` | PASS — shows all 9 subcommands |
| `trache checklist --help` | PASS — shows all 5 subcommands |
| `trache comment --help` | PASS — shows 2 subcommands |

### Version Consistency

| Location | Version |
|---|---|
| `pyproject.toml` | 0.1.4 |
| `src/trache/__init__.py` | 0.1.4 |
| `trache version` CLI output | 0.1.4 |

## Test / Lint Results

- **Tests**: 113 passed, 0 failed (pytest 9.0.2)
- **Lint**: All checks passed (ruff)

## Doc Drift Found (Pre-Fix)

| Item | Status |
|---|---|
| `trache version` not in README command table | Fixed |
| `trache push --card` option not documented | Fixed |
| `trache init --board-url` option not documented | Fixed |
| `trache card list --list` filter option not documented | Fixed |
| `trache card create --desc` option not documented | Fixed |
| CHANGELOG missing v0.1.2 and v0.1.3 entries | Fixed |
| CLAUDE.md missing most commands | Fixed |
| Install fails with system pip (PEP 639 license) | Fixed |

## Fixes Applied

1. **pyproject.toml**: `license = "MIT"` → `license = {text = "MIT"}`
2. **pyproject.toml + __init__.py**: version bump 0.1.3 → 0.1.4
3. **README.md**: complete rewrite with all commands, options, semantics
4. **CLAUDE.md**: refocused as agent policy with full command coverage
5. **CHANGELOG.md**: added v0.1.2, v0.1.3, v0.1.4 entries
6. **.claude/skills/trache/SKILL.md**: new Claude skill

## Remaining Caveats

- Not published to PyPI — install is from source only
- `trache card create` and `trache card archive` are mock-validated only (no live Trello confirmation yet)
- Comment commands hit API directly (not local-first by design)
- No rate limiting/retry framework
