"""Fingerprint và manifest deterministic của Trading Memory."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from ..memory.database import migration_versions


NORMALIZATION_VERSION = "normalization/1"
DATASET_VERSION = "TA-DATA-V1"


def current_git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def fingerprint_inputs(connection: sqlite3.Connection) -> dict[str, object]:
    source_hashes = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT sha256 FROM source_artifacts WHERE sha256 IS NOT NULL ORDER BY sha256"
        )
    ]
    parser_versions = [
        {"parser_name": row[0], "parser_version": row[1]}
        for row in connection.execute(
            """
            SELECT DISTINCT parser_name, parser_version
            FROM source_artifacts
            WHERE parser_name IS NOT NULL AND parser_version IS NOT NULL
            ORDER BY parser_name, parser_version
            """
        )
    ]
    return {
        "source_sha256": source_hashes,
        "schema_versions": migration_versions(connection),
        "parser_versions": parser_versions,
        "normalization_version": NORMALIZATION_VERSION,
    }


def dataset_fingerprint(connection: sqlite3.Connection) -> str:
    payload = json.dumps(fingerprint_inputs(connection), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def build_manifest(
    connection: sqlite3.Connection,
    *,
    root: Path,
    inventory: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
) -> dict[str, object]:
    strategy_versions = [row[0] for row in connection.execute("SELECT id FROM strategy_versions ORDER BY id")]
    audit_versions = [row[0] for row in connection.execute("SELECT id FROM audit_versions ORDER BY id")]
    blocked = int(connection.execute(
        """
        SELECT COUNT(*) FROM trading_episodes
        WHERE episode_kind = 'BLOCKED_OPPORTUNITY' AND audit_version = 'V82'
        """
    ).fetchone()[0])
    return {
        "dataset_version": DATASET_VERSION,
        "git_commit": current_git_commit(root),
        "dataset_fingerprint": dataset_fingerprint(connection),
        "schema_versions": migration_versions(connection),
        "parser_versions": fingerprint_inputs(connection)["parser_versions"],
        "normalization_version": NORMALIZATION_VERSION,
        "sources": _count(connection, "source_artifacts"),
        "strategies": strategy_versions,
        "audits": audit_versions,
        "experiments": _count(connection, "experiments"),
        "presets": _count(connection, "presets"),
        "episodes": _count(connection, "trading_episodes"),
        "features": _count(connection, "episode_features"),
        "executions": _count(connection, "executions"),
        "outcomes": _count(connection, "episode_outcomes"),
        "opportunity_context": _count(connection, "episode_opportunity_context"),
        "opportunity_outcomes": _count(connection, "episode_opportunity_outcomes"),
        "blocked_opportunities": blocked,
        "raw_v82_status": (inventory or {}).get("raw_v82_status", "UNKNOWN"),
        "quality_status": (quality or {}).get("status", "NOT_RUN"),
    }


def write_manifest(manifest: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
