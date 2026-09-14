"""Sinh source mapping và Data Foundation Report từ DB hiện tại."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from .data_quality import completeness_report
from .opportunity_overlap import build_overlap_audit, render_overlap_audit
from .reproducibility import dataset_fingerprint
from ..memory.database import integrity_status, migration_versions


def _count_by(connection: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    return {
        str(row[0]): int(row[1])
        for row in connection.execute(
            f"SELECT COALESCE({column}, 'NULL'), COUNT(*) FROM {table} GROUP BY {column} ORDER BY {column}"
        )
    }


def _date_range(connection: sqlite3.Connection) -> tuple[str | None, str | None]:
    row = connection.execute("SELECT MIN(timestamp_utc), MAX(timestamp_utc) FROM trading_episodes").fetchone()
    return (row[0], row[1]) if row else (None, None)


def render_source_mapping() -> str:
    return """# Phase 1 Source Mapping

## Version semantics

- `V26` và `V63` là execution strategy registry; `V81` và `V82` chỉ là audit/observation layer.
- V81: `strategy_version=V26`, `audit_version=V81`, parser `v81-parser/1`.
- V82: `strategy_version=V26`, `audit_version=V82`, parser `v82-parser/1`.
- Aggregate report không được chuyển thành episode-level rows.

## V81 mapping

| Raw field | Trading Memory |
| --- | --- |
| `time` | `trading_episodes.source_time`; normalized `timestamp_utc` |
| `event_id` | `trading_episodes.raw_event_id` |
| `side`, `entry_price`, `initial_sl` | episode side/candidate/stop |
| `conflict_type=FLAT_*` | `FLAT_CANDIDATE` |
| `conflict_type=OPEN_*` | `BLOCKED_OPPORTUNITY` |
| `entry_rsi` | `episode_features.rsi` |
| `entry_return_std_20` | `episode_features.return_std_20` |
| `entry_spread_r` | `episode_features.spread_r` |
| `entry_return_std_rank` | `episode_features.return_std_rank` |
| `entry_price_std_20/100` | `episode_features.price_std_20/100` |
| `entry_price_std_pct_20` | `episode_features.price_std_pct_20` |
| `entry_std_ratio_20_100` | `episode_features.std_ratio_20_100` |
| `entry_price_z20`, `entry_price_abs_z20` | `episode_features.price_z20/price_abs_z20` |
| `entry_rsi_std_20`, `entry_rsi_std_rank` | RSI StdDev feature columns |
| `entry_atr_return_std_ratio/rank` | ATR/return-StdDev feature columns |
| `return_6/12/24/48`, `mfe_r`, `mae_r`, `first_hit` | `episode_outcomes` |

## V82 mapping

| Raw field | Trading Memory |
| --- | --- |
| `event_type=BLOCKED_OPPOSITE` | `BLOCKED_OPPORTUNITY` |
| `event_type=BLOCKED_SAME_SIDE` | `BLOCKED_OPPORTUNITY` |
| `LONG_ONLY` / `SHORT_ONLY` | `CONTROL_OPPORTUNITY` |
| `SIMULTANEOUS_CONFLICT` | `SIMULTANEOUS_CONFLICT` |
| `active_current_r`, `active_bars_open`, `active_pyramid_adds` | `episode_active_context` |
| `active_value_at_event_r` | `episode_active_context.active_value_at_event_r` |
| `shadow_entry_rsi`, `entry_atr_pct`, bias/regime fields | event-time features/context |
| `entry_spread_r` | `episode_features.spread_r` |
| `shadow_*` outcome fields | `episode_opportunity_outcomes` |
| `active_continuation_*` | `episode_opportunity_outcomes` |
| `actual_selected_*` | `episode_opportunity_outcomes` only |
| `opportunity_diff_*` | `episode_opportunity_outcomes` only; label, never feature |
| `completed`, `incomplete_reason` | outcome resolution metadata |

Feature provenance is `SOURCE_REPORTED` for values copied from CSV. Missing values remain SQL `NULL`.

## Canonical opportunity linkage

- `trading_episodes.canonical_opportunity_id` là identity audit-neutral cho cùng underlying opportunity.
- Identity key dùng `strategy_version`, `symbol`, `timeframe`, candidate semantic chung, `side`, `entry_candidate`, `stop_candidate` và `risk_distance` đã chuẩn hóa số.
- Identity không dùng `audit_version`, source path, parser version, database id hoặc raw `event_id`.
- Một canonical id có thể có nhiều audit observations; không gộp row và không làm mất raw provenance.
- `canonical_opportunity_id` phải được mang theo mọi export Phase 2; không lấy hai observation cùng canonical id làm hai mẫu độc lập.
"""


def render_foundation_report(
    connection: sqlite3.Connection,
    *,
    inventory: dict[str, Any] | None,
    quality: dict[str, Any],
    manifest: dict[str, Any],
) -> str:
    start, end = _date_range(connection)
    episode_kinds = _count_by(connection, "trading_episodes", "episode_kind")
    event_types = _count_by(connection, "episode_opportunity_context", "event_type")
    folds = _count_by(connection, "trading_episodes", "fold_type")
    sides = _count_by(connection, "trading_episodes", "side")
    episode_strategies = _count_by(connection, "trading_episodes", "strategy_version")
    episode_audits = _count_by(connection, "trading_episodes", "audit_version")
    completed = int(connection.execute("SELECT COUNT(*) FROM episode_outcomes WHERE resolved = 1").fetchone()[0])
    incomplete = int(connection.execute("SELECT COUNT(*) FROM episode_outcomes WHERE resolved = 0").fetchone()[0])
    strategies = [row[0] for row in connection.execute("SELECT id FROM strategy_versions ORDER BY id")]
    audits = [row[0] for row in connection.execute("SELECT id FROM audit_versions ORDER BY id")]
    source_status = _count_by(connection, "source_artifacts", "status")
    quality_checks = Counter(
        str(item["severity"])
        for item in quality.get("checks", [])
        if not item.get("passed")
    )
    integrity = integrity_status(connection)
    overlap = quality.get("overlap") or build_overlap_audit(connection)
    return f"""# Trading Agent Phase 1 — Data Foundation Report

## Status

- Dataset: `{manifest.get('dataset_version')}`
- Repository base SHA: `{manifest.get('repository_base_sha') or 'UNKNOWN'}`
- Dataset generation/implementation commit: `{manifest.get('dataset_generation_commit') or 'UNKNOWN'}`
- Report capture commit: `{manifest.get('report_capture_commit') or 'UNKNOWN'}`
- Dataset fingerprint: `{dataset_fingerprint(connection)}`
- Quality: **{quality.get('status')}** ({dict(sorted(quality_checks.items()))})
- SQLite migrations: `{', '.join(migration_versions(connection))}`
- SQLite foreign key check: **{'PASS' if integrity['foreign_key_ok'] else 'FAIL'}**
- SQLite integrity check: **{'PASS' if integrity['integrity_ok'] else 'FAIL'}**

## Source audit

- Inventory artifacts: `{(inventory or {}).get('artifact_count', 0)}`
- Source rows in registry: `{manifest.get('sources', 0)}`
- Source status: `{source_status}`
- Supported strategy versions: `{', '.join(strategies)}`
- Audit layers: `{', '.join(audits)}`
- Raw V82 status: **{(inventory or {}).get('raw_v82_status', 'UNKNOWN')}**
- Missing/failed source counts are surfaced in `quality_report.json`; no aggregate V82 report was expanded into synthetic events.

## Coverage

- Episode date range UTC: `{start}` → `{end}`
- Audit observations / episode rows: `{manifest.get('episodes', 0)}`
- Raw V82 observations: `{manifest.get('raw_v82_observations', overlap.get('v82_audit_observations', 0))}`
- Unique underlying opportunities: `{manifest.get('unique_opportunities', overlap.get('unique_v81_opportunities', 0) + overlap.get('unique_v82_opportunities', 0) - overlap.get('confirmed_same_underlying_opportunities', 0))}`
- Unique V81 / V82 opportunities: `{overlap.get('unique_v81_opportunities', 0)} / {overlap.get('unique_v82_opportunities', 0)}`
- Confirmed same underlying V81↔V82: `{overlap.get('confirmed_same_underlying_opportunities', 0)}`; independent canonical opportunities: `{overlap.get('confirmed_independent_opportunities', 0)}`; ambiguous: `{overlap.get('ambiguous_matches', 0)}`
- Executed: `{int(connection.execute("SELECT COUNT(*) FROM trading_episodes WHERE was_executed = 1").fetchone()[0])}`; non-executed candidates: `{int(connection.execute("SELECT COUNT(*) FROM trading_episodes WHERE was_executed = 0").fetchone()[0])}`
- Generic outcomes resolved/incomplete: `{completed}/{incomplete}`
- Executions imported: `{manifest.get('executions', 0)}`
- Opportunity contexts/outcomes: `{manifest.get('opportunity_context', 0)}/{manifest.get('opportunity_outcomes', 0)}`
- Episode kinds: `{episode_kinds}`
- Sides: `{sides}`
- Folds: `{folds}`
- V82 event types: `{event_types}`
- Episode strategy coverage: `{episode_strategies}`
- Episode audit coverage: `{episode_audits}`

## Feature completeness

```json
{json.dumps(completeness_report(connection), ensure_ascii=False, indent=2, sort_keys=True)}
```

Feature columns contain event-time values only. Outcome, counterfactual and opportunity-cost columns are stored separately.

## Required query coverage

The repository supports queries A-N plus O (unique canonical opportunity count) and P (all audit observations for one canonical id). `query_episodes(canonical_opportunity_id=...)`, `get_opportunity_observations(...)`, `count_unique_opportunities(...)` and `count_audit_observations(...)` preserve the distinction between opportunities and observations.

## Leakage and integrity

- Leakage status: **{'PASS' if quality.get('leakage', {}).get('passed') else 'FAIL'}**
- Lookahead violations: `{quality.get('leakage', {}).get('lookahead_violations', 0)}`
- Forbidden future fields are excluded from `episode_features` and raw feature JSON.
- V82 `opportunity_diff_*` is a label/outcome, never a feature.
- V82 `AMBIGUOUS` first-hit is preserved; incomplete rows remain in episode/outcome tables.

## Execution boundary

- V26 EA source and execution presets were not modified by Phase 1.
- No Python order sending, risk change, promotion, live deploy, V83 or execution gate is included.
- Missing V26/V63 trade history means executed-trade coverage is reported as absent rather than reconstructed.

## Known limitations

1. The raw V81 CSV has no embedded timezone field. The importer records `UTC` as `INFERRED` from the shared MT5 exporter contract and cross-checks V82 epoch IDs; this remains a provenance limitation and must be verified before cross-broker date comparisons.
2. This checkout contains V81/V82 shadow telemetry but no separate V26/V63 execution trade-history artifacts or backtests directory.
3. Parquet export uses an optional Arrow writer when available and a dependency-free uncompressed writer otherwise; SQLite remains the authoritative relational store.
4. Source files under ignored MT5 runtime copies are inventoried as duplicate paths or excluded runtime files; canonical raw V81/V82 paths are used for import.
5. Unknown metadata artifacts, inferred timezone metadata and duplicate runtime copies remain explicit warnings; they are not silently promoted to episode data.
"""


def write_reports(
    connection: sqlite3.Connection,
    *,
    output_dir: Path,
    inventory: dict[str, Any] | None,
    quality: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "source_mapping.md").write_text(render_source_mapping(), encoding="utf-8")
    (output_dir / "data_foundation_report.md").write_text(
        render_foundation_report(connection, inventory=inventory, quality=quality, manifest=manifest),
        encoding="utf-8",
    )
    overlap = quality.get("overlap") or build_overlap_audit(connection)
    (output_dir / "v81_v82_overlap_audit.md").write_text(
        render_overlap_audit(overlap),
        encoding="utf-8",
    )
