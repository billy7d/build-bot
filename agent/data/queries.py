"""Các query acceptance cố định cho dataset Phase 1."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from ..memory.database import apply_migrations, connect_database


NAMED_QUERIES = {
    "A": """
        SELECT * FROM trading_episodes
        WHERE strategy_version = 'V26' AND side = 'LONG'
          AND timestamp_utc >= '2025-01-01T00:00:00Z'
          AND timestamp_utc < '2026-01-01T00:00:00Z'
        ORDER BY timestamp_utc, episode_id
    """,
    "B": """
        SELECT * FROM trading_episodes
        WHERE strategy_version = 'V26' AND was_executed = 1
        ORDER BY timestamp_utc, episode_id
    """,
    "C": """
        SELECT e.*, f.return_std_rank FROM trading_episodes e
        JOIN episode_features f ON f.episode_id = e.episode_id
        WHERE e.audit_version = 'V81' AND f.return_std_rank >= 80
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "D": """
        SELECT e.*, c.* FROM trading_episodes e
        JOIN episode_opportunity_context c ON c.episode_id = e.episode_id
        WHERE e.audit_version = 'V82' AND c.event_type = 'BLOCKED_OPPOSITE'
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "E": """
        SELECT e.*, c.* FROM trading_episodes e
        JOIN episode_opportunity_context c ON c.episode_id = e.episode_id
        WHERE e.audit_version = 'V82' AND c.active_side = 'SHORT' AND c.shadow_side = 'LONG'
          AND c.event_type = 'BLOCKED_OPPOSITE'
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "F": """
        SELECT e.*, c.* FROM trading_episodes e
        JOIN episode_opportunity_context c ON c.episode_id = e.episode_id
        WHERE e.audit_version = 'V82' AND c.active_side = 'LONG' AND c.shadow_side = 'SHORT'
          AND c.event_type = 'BLOCKED_OPPOSITE'
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "G": """
        SELECT e.*, c.* FROM trading_episodes e
        JOIN episode_opportunity_context c ON c.episode_id = e.episode_id
        WHERE e.audit_version = 'V82' AND c.event_type = 'BLOCKED_SAME_SIDE'
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "H": """
        SELECT e.*, c.* FROM trading_episodes e
        JOIN episode_opportunity_context c ON c.episode_id = e.episode_id
        WHERE e.audit_version = 'V82' AND c.event_type IN ('LONG_ONLY', 'SHORT_ONLY')
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "I": """
        SELECT e.*, a.* FROM trading_episodes e
        JOIN episode_active_context a ON a.episode_id = e.episode_id
        WHERE e.audit_version = 'V82' AND e.episode_kind = 'BLOCKED_OPPORTUNITY'
          AND a.active_pyramid_adds IS NOT NULL AND a.active_pyramid_adds < 1
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "J": """
        SELECT e.*, a.* FROM trading_episodes e
        JOIN episode_active_context a ON a.episode_id = e.episode_id
        WHERE e.audit_version = 'V82' AND e.episode_kind = 'BLOCKED_OPPORTUNITY'
          AND a.active_pyramid_adds >= 1
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "K": """
        SELECT e.*, o.opportunity_diff_24bar_r FROM trading_episodes e
        JOIN episode_opportunity_outcomes o ON o.episode_id = e.episode_id
        WHERE e.audit_version = 'V82'
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "L": """
        SELECT e.*, o.resolved, o.incomplete_reason FROM trading_episodes e
        JOIN episode_outcomes o ON o.episode_id = e.episode_id
        WHERE o.resolved = 0
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "M": """
        SELECT e.*, o.shadow_first_hit FROM trading_episodes e
        JOIN episode_opportunity_outcomes o ON o.episode_id = e.episode_id
        WHERE o.shadow_first_hit = 'AMBIGUOUS'
        ORDER BY e.timestamp_utc, e.episode_id
    """,
    "N": """
        SELECT fold_type, COUNT(*) AS episodes,
               SUM(was_executed) AS executed
        FROM trading_episodes
        GROUP BY fold_type ORDER BY fold_type
    """,
}


def run_named_query(connection: sqlite3.Connection, name: str, limit: int | None = None) -> list[dict[str, object]]:
    key = name.upper()
    if key not in NAMED_QUERIES:
        raise ValueError(f"query phải thuộc A-N, nhận {name!r}")
    sql = NAMED_QUERIES[key]
    if limit is not None:
        sql = f"SELECT * FROM ({sql}) LIMIT ?"
        rows = connection.execute(sql, (limit,)).fetchall()
    else:
        rows = connection.execute(sql).fetchall()
    return [dict(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=tuple(NAMED_QUERIES))
    parser.add_argument("--db", type=Path, default=Path("data/trading_memory.db"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    connection = connect_database(args.db)
    apply_migrations(connection)
    result = run_named_query(connection, args.name, args.limit)
    print(json.dumps({"query": args.name, "rows": len(result), "data": result}, ensure_ascii=False, indent=2, default=str))
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
