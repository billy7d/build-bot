"""Data quality gate cho SQLite Trading Memory."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .leakage_checks import run_leakage_checks
from .reproducibility import dataset_fingerprint
from ..memory.database import connect_database, apply_migrations, integrity_status


SEVERITY_ORDER = {"INFO": 0, "WARN": 1, "ERROR": 2, "FATAL": 3}
FIRST_HIT_VALUES = {None, "", "NONE", "PLUS_1R", "MINUS_1R", "AMBIGUOUS", "UNRESOLVED"}
STDDEV_FIELDS = ("return_std_20", "price_std_20", "price_std_100", "price_std_pct_20", "rsi_std_20")
RANK_FIELDS = ("return_std_rank", "rsi_std_rank", "atr_return_std_rank")


def _check(name: str, severity: str, count: int, detail: object = None) -> dict[str, object]:
    result: dict[str, object] = {"name": name, "severity": severity, "count": count, "passed": count == 0}
    if detail not in (None, [], {}, ""):
        result["detail"] = detail
    return result


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _finite_numeric_checks(connection: sqlite3.Connection) -> tuple[int, int, dict[str, int]]:
    invalid = 0
    negative_std = 0
    negative_by_field: Counter[str] = Counter()
    for table in ("episode_features", "episode_active_context", "episode_opportunity_outcomes", "episode_outcomes", "executions"):
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        for row in connection.execute(f"SELECT * FROM {table}"):
            for column in columns:
                value = row[column]
                if isinstance(value, float) and not math.isfinite(value):
                    invalid += 1
            if table == "episode_features":
                for field in STDDEV_FIELDS:
                    value = row[field]
                    if value is not None and value < 0:
                        negative_std += 1
                        negative_by_field[field] += 1
    return invalid, negative_std, dict(sorted(negative_by_field.items()))


def _quality_for_inventory(inventory: dict[str, Any] | None) -> list[dict[str, object]]:
    if not inventory:
        return []
    checks: list[dict[str, object]] = []
    unknown = sum(1 for item in inventory.get("artifacts", []) if item.get("artifact_type") == "UNKNOWN")
    duplicates = sum(1 for item in inventory.get("artifacts", []) if item.get("status") == "DUPLICATE_SOURCE_PATH")
    missing_v82 = int(inventory.get("raw_v82_status") == "MISSING_RAW_SOURCE")
    checks.append(_check("unknown_source_artifacts", "WARN", unknown))
    checks.append(_check("duplicate_source_paths", "WARN", duplicates))
    checks.append(_check("raw_v82_missing", "WARN", missing_v82))
    return checks


def run_quality(connection: sqlite3.Connection, inventory: dict[str, Any] | None = None) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    required_tables = {
        "schema_migrations", "source_artifacts", "strategy_versions", "audit_versions", "presets",
        "experiments", "trading_episodes", "episode_features", "executions", "episode_outcomes",
        "episode_opportunity_context", "episode_active_context", "episode_opportunity_outcomes",
    }
    missing_tables = sorted(table for table in required_tables if not _table_exists(connection, table))
    checks.append(_check("required_schema", "FATAL", len(missing_tables), missing_tables))
    if missing_tables:
        return {"status": "FAIL", "checks": checks, "fingerprint": None}

    failed_sources = int(connection.execute(
        "SELECT COUNT(*) FROM source_artifacts WHERE status = 'FAILED'"
    ).fetchone()[0])
    checks.append(_check("failed_source_artifacts", "ERROR", failed_sources))
    duplicate_source_rows = connection.execute(
        """
        SELECT sha256, parser_name, parser_version, COUNT(*) AS n
        FROM source_artifacts GROUP BY sha256, parser_name, parser_version HAVING n > 1
        """
    ).fetchall()
    checks.append(_check("duplicate_source_hash_parser", "ERROR", len(duplicate_source_rows)))

    duplicate_episodes = int(connection.execute(
        "SELECT COUNT(*) FROM (SELECT episode_id FROM trading_episodes GROUP BY episode_id HAVING COUNT(*) > 1)"
    ).fetchone()[0])
    checks.append(_check("duplicate_episode", "FATAL", duplicate_episodes))
    missing_timestamps = int(connection.execute(
        "SELECT COUNT(*) FROM trading_episodes WHERE timestamp_utc IS NULL OR timestamp_utc = ''"
    ).fetchone()[0])
    checks.append(_check("missing_episode_timestamps", "ERROR", missing_timestamps))

    invalid_timezone = 0
    inferred_timezone = 0
    for row in connection.execute("SELECT source_timezone, metadata_json FROM source_artifacts"):
        timezone_name = row[0]
        if timezone_name:
            try:
                if timezone_name.upper() not in {"UTC", "GMT", "Z"}:
                    ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError:
                invalid_timezone += 1
        try:
            metadata = json.loads(row[1] or "{}")
            if metadata.get("timezone_confidence") == "INFERRED":
                inferred_timezone += 1
        except json.JSONDecodeError:
            invalid_timezone += 1
    checks.append(_check("invalid_timezone", "ERROR", invalid_timezone))
    checks.append(_check("inferred_timezone_provenance", "WARN", inferred_timezone))

    invalid_numeric, negative_std, negative_by_field = _finite_numeric_checks(connection)
    checks.append(_check("invalid_numeric", "ERROR", invalid_numeric))
    checks.append(_check("negative_stddev", "ERROR", negative_std, negative_by_field))
    rank_outside = 0
    rank_detail: Counter[str] = Counter()
    for row in connection.execute("SELECT * FROM episode_features"):
        for field in RANK_FIELDS:
            value = row[field]
            if value is not None and not 0 <= value <= 100:
                rank_outside += 1
                rank_detail[field] += 1
        value = row["price_abs_z20"]
        if value is not None and value < 0:
            rank_outside += 1
            rank_detail["price_abs_z20"] += 1
    checks.append(_check("rank_or_abs_z_out_of_range", "ERROR", rank_outside, dict(rank_detail)))

    fk = integrity_status(connection)
    checks.append(_check("orphan_foreign_keys", "FATAL", len(fk["foreign_key_check"]), fk["foreign_key_check"]))
    checks.append(_check("sqlite_integrity", "FATAL", 0 if fk["integrity_ok"] else 1, fk["integrity_check"]))
    orphan_execution = int(connection.execute(
        """
        SELECT COUNT(*) FROM executions x
        LEFT JOIN trading_episodes e ON e.episode_id = x.episode_id
        WHERE x.episode_id IS NOT NULL AND e.episode_id IS NULL
        """
    ).fetchone()[0])
    orphan_outcome = int(connection.execute(
        """
        SELECT COUNT(*) FROM episode_outcomes o
        LEFT JOIN trading_episodes e ON e.episode_id = o.episode_id
        WHERE e.episode_id IS NULL
        """
    ).fetchone()[0])
    checks.append(_check("orphan_execution", "FATAL", orphan_execution))
    checks.append(_check("orphan_outcome", "FATAL", orphan_outcome))

    invalid_strategy = int(connection.execute(
        """
        SELECT COUNT(*) FROM trading_episodes e
        LEFT JOIN strategy_versions s ON s.id = e.strategy_version
        WHERE e.strategy_version IS NOT NULL AND s.id IS NULL
        """
    ).fetchone()[0])
    invalid_audit = int(connection.execute(
        """
        SELECT COUNT(*) FROM trading_episodes e
        LEFT JOIN audit_versions a ON a.id = e.audit_version
        WHERE e.audit_version IS NOT NULL AND a.id IS NULL
        """
    ).fetchone()[0])
    checks.append(_check("invalid_strategy_relationship", "ERROR", invalid_strategy))
    checks.append(_check("invalid_audit_relationship", "ERROR", invalid_audit))

    invalid_registry = 0
    strategy_ids = {row[0] for row in connection.execute("SELECT id FROM strategy_versions")}
    for row in connection.execute("SELECT parent_strategy_version FROM strategy_versions"):
        if row[0] is not None and row[0] not in strategy_ids:
            invalid_registry += 1
    for row in connection.execute("SELECT base_strategy_version, parent_audit_version, execution_authority FROM audit_versions"):
        if row[0] is not None and row[0] not in strategy_ids:
            invalid_registry += 1
        if row[1] is not None and not connection.execute("SELECT 1 FROM audit_versions WHERE id = ?", (row[1],)).fetchone():
            invalid_registry += 1
        if row[2] != "NONE":
            invalid_registry += 1
    if {"V81", "V82"} & strategy_ids:
        invalid_registry += 1
    checks.append(_check("invalid_registry_relationship", "ERROR", invalid_registry))

    invalid_direction = 0
    for row in connection.execute(
        "SELECT event_type, active_side, shadow_side, actual_selected_side, blocked_side FROM episode_opportunity_context"
    ):
        event_type, active, shadow, selected, blocked = row
        valid = (
            event_type == "BLOCKED_OPPOSITE" and active in {"LONG", "SHORT"} and active != shadow and selected == "NONE" and blocked == shadow
        ) or (
            event_type == "BLOCKED_SAME_SIDE" and active in {"LONG", "SHORT"} and active == shadow and selected == "NONE" and blocked == shadow
        ) or (
            event_type == "LONG_ONLY" and active == "NONE" and shadow == "LONG" and selected == "LONG" and blocked == "NONE"
        ) or (
            event_type == "SHORT_ONLY" and active == "NONE" and shadow == "SHORT" and selected == "SHORT" and blocked == "NONE"
        ) or (
            event_type == "SIMULTANEOUS_CONFLICT" and active == "NONE" and shadow in {"LONG", "SHORT"} and selected in {"LONG", "SHORT"} and blocked == shadow
        )
        if not valid:
            invalid_direction += 1
    checks.append(_check("invalid_v82_direction", "ERROR", invalid_direction))

    opportunity_diff_mismatch = 0
    opportunity_fields = (
        ("shadow_return_6bar_r", "active_continuation_6bar_r", "opportunity_diff_6bar_r"),
        ("shadow_return_12bar_r", "active_continuation_12bar_r", "opportunity_diff_12bar_r"),
        ("shadow_return_24bar_r", "active_continuation_24bar_r", "opportunity_diff_24bar_r"),
        ("shadow_return_48bar_r", "active_continuation_48bar_r", "opportunity_diff_48bar_r"),
    )
    for row in connection.execute("SELECT * FROM episode_opportunity_outcomes"):
        for shadow_field, active_field, diff_field in opportunity_fields:
            shadow = row[shadow_field]
            active = row[active_field]
            diff = row[diff_field]
            # Raw report có thể làm tròn diff; cho phép sai số nhỏ hơn một tick R.
            if shadow is not None and active is not None and diff is not None:
                if abs(diff - (shadow - active)) > 1e-5:
                    opportunity_diff_mismatch += 1
    checks.append(_check("opportunity_diff_consistency", "ERROR", opportunity_diff_mismatch))

    invalid_first_hit = 0
    first_hit_detail: Counter[str] = Counter()
    for table, columns in (
        ("episode_outcomes", ("hit_plus_1r_first", "hit_minus_1r_first")),
        ("episode_opportunity_outcomes", ("shadow_first_hit", "active_first_hit", "actual_selected_first_hit")),
    ):
        for row in connection.execute(f"SELECT {', '.join(columns)} FROM {table}"):
            for value in row:
                if value not in FIRST_HIT_VALUES:
                    invalid_first_hit += 1
                    first_hit_detail[str(value)] += 1
    checks.append(_check("invalid_first_hit", "ERROR", invalid_first_hit, dict(first_hit_detail)))

    opportunity_orphans = int(connection.execute(
        """
        SELECT COUNT(*) FROM episode_opportunity_outcomes o
        LEFT JOIN episode_opportunity_context c ON c.episode_id = o.episode_id
        WHERE c.episode_id IS NULL
        """
    ).fetchone()[0])
    checks.append(_check("opportunity_outcome_without_context", "FATAL", opportunity_orphans))
    missing_completed_outcomes = 0
    for table, fields in (
        ("episode_outcomes", ("mfe_r", "mae_r", "forward_return_6h", "forward_return_12h", "forward_return_24h", "forward_return_48h")),
        ("episode_opportunity_outcomes", ("shadow_mfe_r", "shadow_mae_r", "shadow_return_6bar_r", "shadow_return_12bar_r", "shadow_return_24bar_r", "shadow_return_48bar_r")),
    ):
        required = " OR ".join(f"{field} IS NULL" for field in fields)
        missing_completed_outcomes += int(connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE resolved = 1 AND ({required})"
        ).fetchone()[0])
    checks.append(_check("missing_completed_outcomes", "ERROR", missing_completed_outcomes))
    leakage = run_leakage_checks(connection)
    checks.append(_check("lookahead_violations", "FATAL", leakage["lookahead_violations"], leakage["violations"]))
    checks.extend(_quality_for_inventory(inventory))

    # Severity của check PASS không được làm fail cả dataset; chỉ xét lỗi thật.
    max_severity = max(
        (SEVERITY_ORDER[str(check["severity"])] for check in checks if not check["passed"]),
        default=0,
    )
    status = "FAIL" if max_severity >= SEVERITY_ORDER["ERROR"] else "PASS"
    return {
        "status": status,
        "checks": checks,
        "severity_order": SEVERITY_ORDER,
        "completeness": completeness_report(connection),
        "leakage": leakage,
        "fingerprint": dataset_fingerprint(connection),
    }


def completeness_report(connection: sqlite3.Connection) -> dict[str, object]:
    total = int(connection.execute("SELECT COUNT(*) FROM trading_episodes").fetchone()[0])
    def percentage(count: int) -> float:
        return round(100.0 * count / total, 4) if total else 0.0
    feature_fields = {
        "RSI": "rsi", "ATR": "atr_percent", "StdDev": "return_std_20", "Z-score": "price_z20",
    }
    result: dict[str, object] = {"episodes": total}
    for label, field in feature_fields.items():
        count = int(connection.execute(f"SELECT COUNT(*) FROM episode_features WHERE {field} IS NOT NULL").fetchone()[0])
        result[f"{label}_percent"] = percentage(count)
    result["Spread_percent"] = percentage(int(connection.execute(
        "SELECT COUNT(*) FROM episode_features WHERE spread_r IS NOT NULL"
    ).fetchone()[0]))
    result["Regime_percent"] = percentage(int(connection.execute(
        "SELECT COUNT(*) FROM episode_features WHERE raw_features_json LIKE '%regime%'"
    ).fetchone()[0]))
    result["Opportunity_outcome_percent"] = percentage(int(connection.execute(
        "SELECT COUNT(*) FROM episode_opportunity_outcomes WHERE resolved = 1"
    ).fetchone()[0]))
    result["Active_context_percent"] = percentage(int(connection.execute(
        "SELECT COUNT(*) FROM episode_active_context WHERE active_value_at_event_r IS NOT NULL"
    ).fetchone()[0]))
    result["V82_shadow_outcome_percent"] = percentage(int(connection.execute(
        "SELECT COUNT(*) FROM episode_opportunity_outcomes WHERE shadow_return_48bar_r IS NOT NULL"
    ).fetchone()[0]))
    return result


def load_inventory(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/trading_memory.db"))
    parser.add_argument("--inventory", type=Path, default=Path("reports/trading_agent/phase1/source_inventory.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/trading_agent/phase1/quality_report.json"))
    args = parser.parse_args()
    connection = connect_database(args.db)
    apply_migrations(connection)
    result = run_quality(connection, load_inventory(args.inventory))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "fingerprint": result["fingerprint"], "output": str(args.output)}, ensure_ascii=False, indent=2))
    connection.close()
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
