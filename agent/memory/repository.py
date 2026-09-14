"""Repository typed-thin cho các bảng Trading Memory."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping, Sequence


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json(value: object) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, allow_nan=False)


class TradingMemoryRepository:
    """Các thao tác insert/query không chứa business logic execution."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def register_strategy(self, record: Mapping[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO strategy_versions(
                id, name, parent_strategy_version, git_commit, source_hash,
                description, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                parent_strategy_version=excluded.parent_strategy_version,
                git_commit=excluded.git_commit,
                source_hash=excluded.source_hash,
                description=excluded.description,
                status=excluded.status
            """,
            (
                record["id"], record["name"], record.get("parent_strategy_version"),
                record.get("git_commit"), record.get("source_hash"),
                record["description"], record["status"], record.get("created_at", utc_now()),
            ),
        )

    def register_audit(self, record: Mapping[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO audit_versions(
                id, name, audit_type, base_strategy_version, parent_audit_version,
                git_commit, source_hash, mode, execution_authority, description,
                created_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                audit_type=excluded.audit_type,
                base_strategy_version=excluded.base_strategy_version,
                parent_audit_version=excluded.parent_audit_version,
                git_commit=excluded.git_commit,
                source_hash=excluded.source_hash,
                mode=excluded.mode,
                execution_authority=excluded.execution_authority,
                description=excluded.description,
                status=excluded.status
            """,
            (
                record["id"], record["name"], record["audit_type"],
                record.get("base_strategy_version"), record.get("parent_audit_version"),
                record.get("git_commit"), record.get("source_hash"), record["mode"],
                record["execution_authority"], record["description"],
                record.get("created_at", utc_now()), record["status"],
            ),
        )

    def register_preset(self, record: Mapping[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO presets(
                id, name, strategy_version, audit_version, file_path, sha256,
                magic_number, parameters_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                strategy_version=excluded.strategy_version,
                audit_version=excluded.audit_version,
                file_path=excluded.file_path,
                sha256=excluded.sha256,
                magic_number=excluded.magic_number,
                parameters_json=excluded.parameters_json
            """,
            (
                record["id"], record["name"], record.get("strategy_version"),
                record.get("audit_version"), record["file_path"], record["sha256"],
                record.get("magic_number"), _json(record.get("parameters", {})),
                record.get("created_at", utc_now()),
            ),
        )

    def register_experiment(self, record: Mapping[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO experiments(
                id, name, strategy_version, audit_version, preset_id, symbol,
                timeframe, start_time, end_time, deposit, leverage, history_quality,
                tick_model, purpose, fold_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                strategy_version=excluded.strategy_version,
                audit_version=excluded.audit_version,
                preset_id=excluded.preset_id,
                symbol=excluded.symbol,
                timeframe=excluded.timeframe,
                start_time=excluded.start_time,
                end_time=excluded.end_time,
                deposit=excluded.deposit,
                leverage=excluded.leverage,
                history_quality=excluded.history_quality,
                tick_model=excluded.tick_model,
                purpose=excluded.purpose,
                fold_type=excluded.fold_type
            """,
            (
                record["id"], record["name"], record.get("strategy_version"),
                record.get("audit_version"), record.get("preset_id"), record.get("symbol"),
                record.get("timeframe"), record.get("start_time"), record.get("end_time"),
                record.get("deposit"), record.get("leverage"), record.get("history_quality"),
                record.get("tick_model"), record.get("purpose"), record.get("fold_type", "UNKNOWN"),
                record.get("created_at", utc_now()),
            ),
        )

    def insert_source_artifact(self, record: Mapping[str, Any]) -> int:
        existing = self.connection.execute(
            """
            SELECT id FROM source_artifacts
            WHERE sha256 = ? AND parser_name IS ? AND parser_version IS ?
            """,
            (record["sha256"], record.get("parser_name"), record.get("parser_version")),
        ).fetchone()
        if existing:
            return int(existing[0])
        cursor = self.connection.execute(
            """
            INSERT INTO source_artifacts(
                path, artifact_type, sha256, file_size, parser_name, parser_version,
                strategy_version, audit_version, preset_id, experiment_id,
                source_timezone, status, created_at, imported_at, error_message,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["path"], record["artifact_type"], record["sha256"], record["file_size"],
                record.get("parser_name"), record.get("parser_version"),
                record.get("strategy_version"), record.get("audit_version"),
                record.get("preset_id"), record.get("experiment_id"),
                record.get("source_timezone"), record["status"], record.get("created_at", utc_now()),
                record.get("imported_at"), record.get("error_message"), _json(record.get("metadata", {})),
            ),
        )
        return int(cursor.lastrowid)

    def update_source_status(
        self, source_id: int, status: str, *, error_message: str | None = None
    ) -> None:
        self.connection.execute(
            """
            UPDATE source_artifacts
            SET status = ?, imported_at = CASE WHEN ? = 'IMPORTED' THEN ? ELSE imported_at END,
                error_message = ?
            WHERE id = ?
            """,
            (status, status, utc_now(), error_message, source_id),
        )

    def link_source_experiment(self, source_id: int, experiment_id: str) -> None:
        """Gắn experiment sau khi parser đã xác nhận và register metadata."""

        self.connection.execute(
            "UPDATE source_artifacts SET experiment_id = ? WHERE id = ?",
            (experiment_id, source_id),
        )

    def source_already_imported(self, sha256: str, parser_version: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1 FROM source_artifacts
            WHERE sha256 = ? AND parser_version = ? AND status = 'IMPORTED'
            LIMIT 1
            """,
            (sha256, parser_version),
        ).fetchone()
        return row is not None

    def insert_episode(self, record: Mapping[str, Any]) -> None:
        columns = (
            "episode_id", "source_artifact_id", "experiment_id", "strategy_version",
            "audit_version", "preset_id", "symbol", "timeframe", "source_time",
            "source_timezone", "timestamp_utc", "side", "episode_kind", "candidate_type",
            "candidate_exists", "was_executed", "execution_id", "entry_candidate",
            "stop_candidate", "target_candidate", "planned_risk_r", "fold_type",
            "raw_event_id", "raw_fields_json", "created_at",
        )
        values = tuple(record.get(column) for column in columns)
        self.connection.execute(
            f"INSERT INTO trading_episodes({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            values,
        )

    def insert_features(self, record: Mapping[str, Any]) -> None:
        columns = (
            "episode_id", "rsi", "atr14", "atr_percent", "spread_r", "return_1", "return_3", "return_6",
            "return_std_20", "return_std_rank", "price_std_20", "price_std_100",
            "price_std_pct_20", "std_ratio_20_100", "price_z20", "price_abs_z20",
            "rsi_std_20", "rsi_std_rank", "atr_return_std_ratio", "atr_return_std_rank",
            "feature_schema_version", "feature_provenance", "feature_timestamp_utc",
            "raw_features_json",
        )
        values = list(record.get(column) for column in columns)
        values[columns.index("feature_provenance")] = _json(record.get("feature_provenance", {}))
        values[columns.index("raw_features_json")] = _json(record.get("raw_features", {}))
        self.connection.execute(
            f"INSERT OR REPLACE INTO episode_features({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            values,
        )

    def insert_execution(self, record: Mapping[str, Any]) -> None:
        columns = (
            "execution_id", "episode_id", "order_id", "deal_id", "entry_time", "entry_price",
            "exit_time", "exit_price", "volume", "desired_risk_money", "actual_risk_money",
            "spread_r", "slippage_r", "stop_loss", "take_profit", "exit_reason", "net_profit",
            "commission", "swap", "result_r",
        )
        self.connection.execute(
            f"INSERT OR REPLACE INTO executions({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            tuple(record.get(column) for column in columns),
        )

    def insert_outcome(self, record: Mapping[str, Any]) -> None:
        columns = (
            "episode_id", "resolved", "mfe_r", "mae_r", "hit_plus_1r_first",
            "hit_minus_1r_first", "forward_return_6h", "forward_return_12h",
            "forward_return_24h", "forward_return_48h", "bars_to_mfe", "bars_to_mae",
            "outcome_timestamp_utc", "incomplete_reason", "outcome_schema_version",
        )
        self.connection.execute(
            f"INSERT OR REPLACE INTO episode_outcomes({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            tuple(record.get(column) for column in columns),
        )

    def insert_opportunity_context(self, record: Mapping[str, Any]) -> None:
        columns = (
            "episode_id", "event_type", "active_side", "shadow_side", "actual_selected_side",
            "blocked_side", "direction", "setup_generation", "active_group_id",
            "active_base_position_identifier", "shadow_build_valid", "shadow_build_reason",
            "long_reject", "short_reject", "source_provenance",
        )
        self.connection.execute(
            f"INSERT OR REPLACE INTO episode_opportunity_context({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            tuple(record.get(column) for column in columns),
        )

    def insert_active_context(self, record: Mapping[str, Any]) -> None:
        columns = (
            "episode_id", "active_entry_price", "active_current_price", "active_initial_risk",
            "active_initial_risk_distance", "active_current_r", "active_sl", "active_is_be",
            "active_tp1_done", "active_tp2_done", "active_runner_active", "active_pyramid_adds",
            "active_bars_open", "active_locked_profit_r", "active_group_volume",
            "active_position_count", "active_value_at_event_r", "source_provenance",
        )
        self.connection.execute(
            f"INSERT OR REPLACE INTO episode_active_context({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            tuple(record.get(column) for column in columns),
        )

    def insert_opportunity_outcome(self, record: Mapping[str, Any]) -> None:
        columns = (
            "episode_id", "shadow_plus_1r_hit", "shadow_minus_1r_hit", "shadow_plus_1r_first",
            "shadow_minus_1r_first", "shadow_first_hit", "shadow_mfe_r", "shadow_mae_r",
            "shadow_return_6bar_r", "shadow_return_12bar_r", "shadow_return_24bar_r",
            "shadow_return_48bar_r", "active_value_6bar_r", "active_value_12bar_r",
            "active_value_24bar_r", "active_value_48bar_r", "active_continuation_6bar_r",
            "active_continuation_12bar_r", "active_continuation_24bar_r", "active_continuation_48bar_r",
            "active_plus_1r_hit", "active_minus_1r_hit", "active_first_hit",
            "actual_selected_build_valid", "actual_selected_entry_price", "actual_selected_initial_sl",
            "actual_selected_risk_distance", "actual_selected_plus_1r_hit", "actual_selected_minus_1r_hit",
            "actual_selected_plus_1r_first", "actual_selected_minus_1r_first", "actual_selected_first_hit",
            "actual_selected_mfe_r", "actual_selected_mae_r", "actual_selected_return_6bar_r",
            "actual_selected_return_12bar_r", "actual_selected_return_24bar_r",
            "actual_selected_return_48bar_r", "opportunity_diff_6bar_r", "opportunity_diff_12bar_r",
            "opportunity_diff_24bar_r", "opportunity_diff_48bar_r", "resolved",
            "outcome_timestamp_utc", "incomplete_reason", "outcome_schema_version", "source_provenance",
        )
        self.connection.execute(
            f"INSERT OR REPLACE INTO episode_opportunity_outcomes({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            tuple(record.get(column) for column in columns),
        )

    def get_episode(self, episode_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM trading_episodes WHERE episode_id = ?", (episode_id,)
        ).fetchone()
        return dict(row) if row else None

    def query_episodes(
        self,
        *,
        strategy_version: str | None = None,
        audit_version: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        episode_kind: str | None = None,
        was_executed: bool | None = None,
        fold_type: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        for column, value in (
            ("strategy_version", strategy_version),
            ("audit_version", audit_version),
            ("symbol", symbol),
            ("timeframe", timeframe),
            ("episode_kind", episode_kind),
            ("fold_type", fold_type),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if was_executed is not None:
            clauses.append("was_executed = ?")
            params.append(int(was_executed))
        if start_time is not None:
            clauses.append("timestamp_utc >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp_utc < ?")
            params.append(end_time)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        tail = " LIMIT ?" if limit is not None else ""
        if limit is not None:
            params.append(limit)
        rows = self.connection.execute(
            f"SELECT * FROM trading_episodes{where} ORDER BY timestamp_utc, episode_id{tail}",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def count(self, table: str) -> int:
        allowed = {
            "source_artifacts", "strategy_versions", "audit_versions", "presets", "experiments",
            "trading_episodes", "episode_features", "executions", "episode_outcomes",
            "episode_opportunity_context", "episode_active_context", "episode_opportunity_outcomes",
        }
        if table not in allowed:
            raise ValueError(f"table không hợp lệ: {table}")
        return int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def table_columns(self, table: str) -> list[str]:
        return [row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")]
