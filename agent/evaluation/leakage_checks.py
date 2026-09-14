"""Kiểm tra feature/outcome theo thời gian và blocklist chống lookahead."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping

from ..data.normalization.timestamps import timestamp_to_datetime


FORBIDDEN_AS_FEATURE = frozenset(
    {
        "result_r", "net_profit", "exit_price", "exit_reason", "mfe_r", "mae_r",
        "hit_plus_1r_first", "hit_minus_1r_first", "first_hit", "completed", "incomplete_reason",
    }
)
FORBIDDEN_PREFIXES = (
    "future_return_", "forward_return_", "shadow_mfe_r", "shadow_mae_r", "shadow_return_",
    "shadow_plus_1r_hit", "shadow_minus_1r_hit", "shadow_first_hit",
    "active_value_", "active_continuation_", "active_plus_1r_hit",
    "active_minus_1r_hit", "active_first_hit", "actual_selected_",
    "opportunity_diff_",
)


def is_forbidden_feature_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in FORBIDDEN_AS_FEATURE or lowered.startswith(FORBIDDEN_PREFIXES)


def _feature_columns(connection: sqlite3.Connection) -> list[str]:
    return [row[1] for row in connection.execute("PRAGMA table_info(episode_features)")]


def run_leakage_checks(connection: sqlite3.Connection) -> dict[str, object]:
    feature_columns = _feature_columns(connection)
    violations: list[dict[str, object]] = []
    forbidden_columns = [column for column in feature_columns if is_forbidden_feature_name(column)]
    if forbidden_columns:
        violations.append({"kind": "future_field_leaked_as_feature", "columns": forbidden_columns})

    feature_rows = connection.execute(
        "SELECT episode_id, feature_timestamp_utc, raw_features_json FROM episode_features"
    ).fetchall()
    for row in feature_rows:
        try:
            feature_time = timestamp_to_datetime(row[1])
        except Exception as exc:  # pragma: no cover - chỉ xảy ra với DB thủ công hỏng
            violations.append({"kind": "invalid_feature_timestamp", "episode_id": row[0], "error": str(exc)})
            continue
        episode = connection.execute(
            "SELECT timestamp_utc FROM trading_episodes WHERE episode_id = ?", (row[0],)
        ).fetchone()
        if not episode:
            violations.append({"kind": "feature_orphan", "episode_id": row[0]})
            continue
        if feature_time > timestamp_to_datetime(episode[0]):
            violations.append({"kind": "feature_after_candidate", "episode_id": row[0]})
        try:
            raw_features = json.loads(row[2] or "{}")
        except json.JSONDecodeError:
            violations.append({"kind": "invalid_feature_provenance_json", "episode_id": row[0]})
            continue
        if isinstance(raw_features, Mapping):
            leaked = [key for key in raw_features if is_forbidden_feature_name(str(key))]
            if leaked:
                violations.append({"kind": "future_field_leaked_as_feature", "episode_id": row[0], "fields": leaked})

    outcome_rows = connection.execute(
        """
        SELECT e.episode_id, e.timestamp_utc, o.outcome_timestamp_utc
        FROM trading_episodes e
        JOIN episode_outcomes o ON o.episode_id = e.episode_id
        WHERE o.outcome_timestamp_utc IS NOT NULL
        UNION ALL
        SELECT e.episode_id, e.timestamp_utc, o.outcome_timestamp_utc
        FROM trading_episodes e
        JOIN episode_opportunity_outcomes o ON o.episode_id = e.episode_id
        WHERE o.outcome_timestamp_utc IS NOT NULL
        """
    ).fetchall()
    for row in outcome_rows:
        if timestamp_to_datetime(row[2]) <= timestamp_to_datetime(row[1]):
            violations.append({"kind": "outcome_not_after_candidate", "episode_id": row[0]})
    return {
        "feature_columns": feature_columns,
        "forbidden_columns": forbidden_columns,
        "checked_feature_rows": len(feature_rows),
        "checked_outcome_rows": len(outcome_rows),
        "violations": violations,
        "lookahead_violations": len(violations),
        "passed": not violations,
    }


def synthetic_future_mutation_test(
    before: Mapping[str, object], after: Mapping[str, object]
) -> dict[str, object]:
    """So sánh snapshot feature tại T sau khi future bars bị thay đổi."""

    shared = sorted(set(before) | set(after))
    changed = [key for key in shared if before.get(key) != after.get(key)]
    return {"passed": not changed, "changed_fields": changed}
