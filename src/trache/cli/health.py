"""Health check command: layered diagnostic probe."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from trache.cli._output import get_output


def _check_board_config(cache_dir: Path) -> tuple[dict[str, Any], Any]:
    """Check board config loads and has a non-empty board_id."""
    from trache.config import TracheConfig

    try:
        config = TracheConfig.load(cache_dir)
    except Exception as e:
        return {"name": "board_config", "status": "fail", "detail": str(e)}, None
    if not config.board_id:
        return {
            "name": "board_config",
            "status": "fail",
            "detail": "board_id is empty",
        }, None
    return {
        "name": "board_config",
        "status": "pass",
        "detail": f"board_id={config.board_id[:12]}...",
    }, config


def _check_database(cache_dir: Path) -> dict[str, Any]:
    """Check cache.db exists, opens, and schema_version matches."""
    from trache.cache.db import DB_FILENAME, SCHEMA_VERSION, connect

    db_path = cache_dir / DB_FILENAME
    if not db_path.exists():
        return {
            "name": "database",
            "status": "fail",
            "detail": f"{DB_FILENAME} not found — run 'trache pull'",
        }
    try:
        with connect(cache_dir) as conn:
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if not row:
                return {
                    "name": "database",
                    "status": "fail",
                    "detail": "schema_version table is empty",
                }
            version = row[0]
            if version != SCHEMA_VERSION:
                return {
                    "name": "database",
                    "status": "fail",
                    "detail": (
                        f"schema version mismatch: DB has {version}, "
                        f"expected {SCHEMA_VERSION}"
                    ),
                }
    except Exception as e:
        return {"name": "database", "status": "fail", "detail": str(e)}
    return {
        "name": "database",
        "status": "pass",
        "detail": f"schema_version={version}",
    }


def _check_db_pragmas(cache_dir: Path) -> dict[str, Any]:
    """Check WAL mode, synchronous=NORMAL, foreign_keys=ON."""
    from trache.cache.db import connect

    issues: list[str] = []
    try:
        with connect(cache_dir) as conn:
            jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if jm != "wal":
                issues.append(f"journal_mode={jm} (expected wal)")
            sync = conn.execute("PRAGMA synchronous").fetchone()[0]
            if sync != 1:
                issues.append(f"synchronous={sync} (expected 1/NORMAL)")
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            if fk != 1:
                issues.append(f"foreign_keys={fk} (expected 1)")
    except Exception as e:
        return {"name": "db_pragmas", "status": "fail", "detail": str(e)}

    if issues:
        return {
            "name": "db_pragmas",
            "status": "fail",
            "detail": "; ".join(issues),
        }
    return {
        "name": "db_pragmas",
        "status": "pass",
        "detail": "journal_mode=wal, synchronous=NORMAL, foreign_keys=ON",
    }


def _check_auth_env(config) -> tuple[dict[str, Any], bool]:
    """Check TrelloAuth.from_env() succeeds."""
    from trache.api.auth import TrelloAuth

    try:
        TrelloAuth.from_env(config.api_key_env, config.token_env)
    except ValueError as e:
        return {
            "name": "auth_env",
            "status": "fail",
            "detail": str(e),
        }, False
    return {
        "name": "auth_env",
        "status": "pass",
        "detail": f"{config.api_key_env} and {config.token_env} set",
    }, True


def _check_api_connectivity(config) -> dict[str, Any]:
    """Check API connectivity via get_current_member()."""
    import httpx

    from trache.api.auth import TrelloAuth
    from trache.api.client import TrelloClient

    try:
        auth = TrelloAuth.from_env(config.api_key_env, config.token_env)
        with TrelloClient(auth) as client:
            member = client.get_current_member()
            username = member.get("username", "unknown")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {
                "name": "api_connectivity",
                "status": "fail",
                "detail": "401 Unauthorized — bad token or API key",
            }
        return {
            "name": "api_connectivity",
            "status": "fail",
            "detail": f"HTTP {e.response.status_code}",
        }
    except Exception as e:
        return {
            "name": "api_connectivity",
            "status": "fail",
            "detail": str(e),
        }
    return {
        "name": "api_connectivity",
        "status": "pass",
        "detail": f"authenticated as {username}",
    }


def _check_sync_state(cache_dir: Path) -> dict[str, Any]:
    """Report sync state: last_pull and onboarding_acked."""
    from trache.config import SyncState

    state = SyncState.load(cache_dir)
    parts = [
        f"last_pull={state.last_pull or 'never'}",
        f"onboarding_acked={state.onboarding_acked}",
    ]
    return {
        "name": "sync_state",
        "status": "pass",
        "detail": ", ".join(parts),
    }


def health(
    local_only: bool = typer.Option(
        False, "--local", help="Skip API connectivity check"
    ),
) -> None:
    """Run layered health checks on the current board."""
    from trache.cli._context import resolve_cache_dir

    out = get_output()
    checks: list[dict[str, Any]] = []

    # 1. Board config
    try:
        cache_dir = resolve_cache_dir()
    except (FileNotFoundError, Exception) as e:
        checks.append({
            "name": "board_config",
            "status": "fail",
            "detail": str(e),
        })
        # Short-circuit: cannot proceed without config
        for name in ("database", "db_pragmas", "auth_env", "api_connectivity", "sync_state"):
            checks.append({
                "name": name,
                "status": "skipped",
                "detail": "skipped — board_config failed",
            })
        _emit_result(out, checks)
        raise typer.Exit(1)

    config_result, config = _check_board_config(cache_dir)
    checks.append(config_result)

    if config_result["status"] == "fail":
        for name in ("database", "db_pragmas", "auth_env", "api_connectivity", "sync_state"):
            checks.append({
                "name": name,
                "status": "skipped",
                "detail": "skipped — board_config failed",
            })
        _emit_result(out, checks)
        raise typer.Exit(1)

    # 2. Database
    db_result = _check_database(cache_dir)
    checks.append(db_result)

    # 3. DB pragmas (skip if database failed)
    if db_result["status"] == "fail":
        checks.append({
            "name": "db_pragmas",
            "status": "skipped",
            "detail": "skipped — database failed",
        })
    else:
        checks.append(_check_db_pragmas(cache_dir))

    # 4. Auth env
    auth_result, auth_ok = _check_auth_env(config)
    checks.append(auth_result)

    # 5. API connectivity
    if local_only:
        checks.append({
            "name": "api_connectivity",
            "status": "skipped",
            "detail": "skipped — --local flag",
        })
    elif not auth_ok:
        checks.append({
            "name": "api_connectivity",
            "status": "skipped",
            "detail": "skipped — auth_env failed",
        })
    else:
        checks.append(_check_api_connectivity(config))

    # 6. Sync state
    checks.append(_check_sync_state(cache_dir))

    # Determine all_ok from non-skipped checks
    non_skipped = [c for c in checks if c["status"] != "skipped"]
    all_ok = all(c["status"] == "pass" for c in non_skipped)

    _emit_result(out, checks, all_ok=all_ok)
    if not all_ok:
        raise typer.Exit(1)


def _emit_result(
    out, checks: list[dict[str, Any]], *, all_ok: bool = False
) -> None:
    """Emit health check results in human or machine format."""
    if not out.is_human:
        out.json({"checks": checks, "all_ok": all_ok})
        return

    status_icons = {
        "pass": "[green]pass[/green]",
        "fail": "[red]fail[/red]",
        "skipped": "[yellow]skipped[/yellow]",
    }
    for check in checks:
        icon = status_icons.get(check["status"], check["status"])
        out.human(f"  {icon}  {check['name']}: {check['detail']}")

    if all_ok:
        out.human("\n[green]All checks passed.[/green]")
    else:
        out.human("\n[red]Some checks failed.[/red]")
