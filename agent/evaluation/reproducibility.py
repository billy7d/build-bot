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
CANONICAL_LINKAGE_VERSION = "canonical-opportunity/1"
DATASET_VERSION = "TA-DATA-V1"
PHASE2_MIGRATION_START = "007"


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


def repository_base_sha(root: Path) -> str | None:
    """Lấy merge-base thật với origin/main, không dùng HEAD làm Base SHA."""

    try:
        result = subprocess.run(
            ["git", "merge-base", "HEAD", "origin/main"],
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
        # Phase 2 migrations are derived/modeling state and must not change
        # the authoritative Phase 1 dataset identity.  This keeps the same
        # source dataset fingerprint stable before and after migration 007.
        "schema_versions": [
            version for version in migration_versions(connection)
            if version < PHASE2_MIGRATION_START
        ],
        "parser_versions": parser_versions,
        "normalization_version": NORMALIZATION_VERSION,
        "canonical_linkage_version": CANONICAL_LINKAGE_VERSION,
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
    dataset_generation_commit: str | None,
    report_capture_commit: str | None,
) -> dict[str, object]:
    strategy_versions = [row[0] for row in connection.execute("SELECT id FROM strategy_versions ORDER BY id")]
    audit_versions = [row[0] for row in connection.execute("SELECT id FROM audit_versions ORDER BY id")]
    blocked = int(connection.execute(
        """
        SELECT COUNT(*) FROM trading_episodes
        WHERE episode_kind = 'BLOCKED_OPPORTUNITY' AND audit_version = 'V82'
        """
    ).fetchone()[0])
    audit_observations = _count(connection, "trading_episodes")
    unique_opportunities = int(connection.execute(
        "SELECT COUNT(DISTINCT canonical_opportunity_id) FROM trading_episodes"
    ).fetchone()[0])
    v81_unique = int(connection.execute(
        "SELECT COUNT(DISTINCT canonical_opportunity_id) FROM trading_episodes WHERE audit_version = 'V81'"
    ).fetchone()[0])
    v82_unique = int(connection.execute(
        "SELECT COUNT(DISTINCT canonical_opportunity_id) FROM trading_episodes WHERE audit_version = 'V82'"
    ).fetchone()[0])
    raw_v82_observations = int(connection.execute(
        "SELECT COUNT(*) FROM trading_episodes WHERE audit_version = 'V82'"
    ).fetchone()[0])
    overlap = (quality or {}).get("overlap", {})
    return {
        "dataset_version": DATASET_VERSION,
        "repository_base_sha": repository_base_sha(root),
        "dataset_generation_commit": dataset_generation_commit,
        "report_capture_commit": report_capture_commit,
        "dataset_fingerprint": dataset_fingerprint(connection),
        "schema_versions": migration_versions(connection),
        "parser_versions": fingerprint_inputs(connection)["parser_versions"],
        "normalization_version": NORMALIZATION_VERSION,
        "canonical_linkage_version": CANONICAL_LINKAGE_VERSION,
        "sources": _count(connection, "source_artifacts"),
        "strategies": strategy_versions,
        "audits": audit_versions,
        "experiments": _count(connection, "experiments"),
        "presets": _count(connection, "presets"),
        "episodes": audit_observations,
        "audit_observations": audit_observations,
        "unique_opportunities": unique_opportunities,
        "unique_v81_opportunities": v81_unique,
        "unique_v82_opportunities": v82_unique,
        "raw_v82_observations": raw_v82_observations,
        "confirmed_same_underlying_opportunities": overlap.get("confirmed_same_underlying_opportunities", 0),
        "confirmed_independent_opportunities": overlap.get("confirmed_independent_opportunities", 0),
        "ambiguous_matches": overlap.get("ambiguous_matches", 0),
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
