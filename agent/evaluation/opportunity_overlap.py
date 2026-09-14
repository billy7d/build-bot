"""Đối chiếu observation V81/V82 và thống kê opportunity canonical."""

from __future__ import annotations

import sqlite3
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from ..data.normalization.canonical import (
    canonical_identity_collision,
    canonical_identity_key_from_record,
)
from ..data.normalization.timestamps import timestamp_to_datetime


def _rows_by_audit(connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {"V81": [], "V82": []}
    rows = connection.execute(
        """
        SELECT * FROM trading_episodes
        WHERE audit_version IN ('V81', 'V82')
        ORDER BY timestamp_utc, episode_id
        """
    ).fetchall()
    for row in rows:
        result[str(row["audit_version"])].append(dict(row))
    return result


def _value(value: object) -> str:
    if value is None:
        return "NULL"
    return str(value)


def _timestamp_side(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(_value(row.get("timestamp_utc")), _value(row.get("side"))) for row in rows}


def _timestamp_entry(rows: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    return {
        (_value(row.get("timestamp_utc")), _value(row.get("side")), _value(row.get("entry_candidate")))
        for row in rows
    }


def _timestamp_only(rows: list[dict[str, Any]]) -> set[str]:
    return {_value(row.get("timestamp_utc")) for row in rows}


def _raw_fields(row: dict[str, Any]) -> dict[str, Any]:
    try:
        loaded = json.loads(str(row.get("raw_fields_json") or "{}"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _comparable_value(value: object) -> object:
    """So sánh số raw khác số chữ số thập phân mà không làm tròn ngầm."""

    raw = "" if value is None else str(value).strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return raw.upper()


def _canonical_groups(rows_by_audit: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rows in rows_by_audit.values():
        for row in rows:
            canonical_id = row.get("canonical_opportunity_id")
            if canonical_id:
                groups[str(canonical_id)].append(row)
    return dict(groups)


def build_overlap_audit(connection: sqlite3.Connection) -> dict[str, object]:
    """Tính overlap từ row canonical, giữ riêng audit observation và opportunity."""

    rows_by_audit = _rows_by_audit(connection)
    v81 = rows_by_audit["V81"]
    v82 = rows_by_audit["V82"]
    groups = _canonical_groups(rows_by_audit)

    intentional_groups = 0
    independent_groups = 0
    ambiguous_groups = 0
    identity_collision_groups = 0
    same_audit_duplicate_groups = 0
    offset_hours: Counter[str] = Counter()
    examples: list[dict[str, object]] = []
    context_comparison_fields = (
        ("d1_regime_score", "d1_regime_score"),
        ("h4_regime_score", "h4_regime_score"),
        ("composite_regime_score", "composite_regime_score"),
        ("entry_rsi", "shadow_entry_rsi"),
        ("entry_atr_pct", "entry_atr_pct"),
        ("entry_spread_r", "entry_spread_r"),
    )
    context_exact_matches: Counter[str] = Counter()
    setup_generation_present = Counter()
    candidate_field_matches = Counter()

    for canonical_id, rows in sorted(groups.items()):
        audits = Counter(str(row.get("audit_version")) for row in rows)
        identity_keys = {canonical_identity_key_from_record(row) for row in rows}
        if canonical_identity_collision(identity_keys):
            identity_collision_groups += 1
        if any(count > 1 for count in audits.values()):
            same_audit_duplicate_groups += 1

        if audits == Counter({"V81": 1, "V82": 1}) and len(identity_keys) == 1:
            v81_row = next(row for row in rows if row.get("audit_version") == "V81")
            v82_row = next(row for row in rows if row.get("audit_version") == "V82")
            try:
                delta_hours = (
                    timestamp_to_datetime(str(v81_row["timestamp_utc"]))
                    - timestamp_to_datetime(str(v82_row["timestamp_utc"]))
                ).total_seconds() / 3600
            except (TypeError, ValueError):
                delta_hours = None
            if delta_hours == 1:
                intentional_groups += 1
                offset_hours[str(int(delta_hours))] += 1
                v81_raw = _raw_fields(v81_row)
                v82_raw = _raw_fields(v82_row)
                for field in ("symbol", "timeframe", "side"):
                    if _comparable_value(v81_row.get(field)) == _comparable_value(v82_row.get(field)):
                        candidate_field_matches[field] += 1
                if canonical_identity_key_from_record(v81_row) == canonical_identity_key_from_record(v82_row):
                    candidate_field_matches["candidate_semantic_entry_stop_risk"] += 1
                for v81_field, v82_field in context_comparison_fields:
                    if _comparable_value(v81_raw.get(v81_field)) == _comparable_value(v82_raw.get(v82_field)):
                        context_exact_matches[f"{v81_field}->{v82_field}"] += 1
                if v81_raw.get("setup_generation") not in (None, ""):
                    setup_generation_present["V81"] += 1
                if v82_raw.get("setup_generation") not in (None, ""):
                    setup_generation_present["V82"] += 1
                if len(examples) < 3:
                    examples.append(
                        {
                            "canonical_opportunity_id": canonical_id,
                            "v81_episode_id": v81_row["episode_id"],
                            "v82_episode_id": v82_row["episode_id"],
                            "v81_raw_event_id": v81_row["raw_event_id"],
                            "v82_raw_event_id": v82_row["raw_event_id"],
                            "v81_timestamp_utc": v81_row["timestamp_utc"],
                            "v82_timestamp_utc": v82_row["timestamp_utc"],
                        }
                    )
            else:
                ambiguous_groups += 1
        elif len(audits) == 1:
            independent_groups += 1
        else:
            ambiguous_groups += 1

    v81_timestamp_side = _timestamp_side(v81)
    v82_timestamp_side = _timestamp_side(v82)
    v81_timestamp_entry = _timestamp_entry(v81)
    v82_timestamp_entry = _timestamp_entry(v82)
    v81_timestamps = _timestamp_only(v81)
    v82_timestamps = _timestamp_only(v82)
    raw_ids_v81 = {_value(row.get("raw_event_id")) for row in v81}
    raw_ids_v82 = {_value(row.get("raw_event_id")) for row in v82}

    return {
        "schema": "trading_memory_v81_v82_overlap_audit_v1",
        "v81_audit_observations": len(v81),
        "v82_audit_observations": len(v82),
        "audit_observations": len(v81) + len(v82),
        "unique_v81_opportunities": len({row.get("canonical_opportunity_id") for row in v81 if row.get("canonical_opportunity_id")}),
        "unique_v82_opportunities": len({row.get("canonical_opportunity_id") for row in v82 if row.get("canonical_opportunity_id")}),
        "exact_timestamp_side_matches": len(v81_timestamp_side & v82_timestamp_side),
        "timestamp_only_matches": len(v81_timestamps & v82_timestamps),
        "timestamp_side_entry_matches": len(v81_timestamp_entry & v82_timestamp_entry),
        "raw_event_id_matches": len(raw_ids_v81 & raw_ids_v82),
        "confirmed_same_underlying_opportunities": intentional_groups,
        "confirmed_independent_opportunities": independent_groups,
        "ambiguous_matches": ambiguous_groups,
        "intentional_cross_audit_observation_groups": intentional_groups,
        "unexpected_canonical_collisions": identity_collision_groups,
        "same_audit_duplicate_canonical_groups": same_audit_duplicate_groups,
        "timestamp_offset_hours": dict(sorted(offset_hours.items())),
        "field_comparison": {
            "symbol_exact_matches": candidate_field_matches["symbol"],
            "timeframe_exact_matches": candidate_field_matches["timeframe"],
            "side_exact_matches": candidate_field_matches["side"],
            "candidate_semantic_entry_stop_risk_exact_matches": candidate_field_matches["candidate_semantic_entry_stop_risk"],
            "signal_context_exact_matches": dict(sorted(context_exact_matches.items())),
            "setup_generation_present": {
                "V81": setup_generation_present["V81"],
                "V82": setup_generation_present["V82"],
            },
            "setup_generation_used_as_join_key": False,
        },
        "examples": examples,
        "methodology": {
            "exact_timestamp_side": "Giao của (timestamp_utc, side) sau normalization, không bù giờ.",
            "timestamp_only": "Giao của timestamp_utc distinct, không dùng side hay price.",
            "timestamp_side_entry": "Giao của (timestamp_utc, side, entry_candidate).",
            "canonical_match": "Giao của canonical_opportunity_id; mỗi nhóm được kiểm tra identity key và một row mỗi audit.",
            "identity_fields": [
                "strategy_version",
                "symbol",
                "timeframe",
                "candidate_semantic",
                "side",
                "entry_candidate",
                "stop_candidate",
                "risk_distance",
            ],
            "excluded_fields": ["audit_version", "source path", "parser version", "database id", "raw_event_id"],
            "timestamp_reconciliation": "V81 timestamp_utc lớn hơn V82 đúng 1 giờ ở mọi nhóm confirmed; chỉ dùng cho audit linkage, không rewrite source_time/source_timezone/raw fields.",
            "timestamp_identity_note": "Timestamp không đưa vào hash canonical vì raw V81/V82 lệch một giờ; candidate identity tuple phải unique trên dataset và được quality gate kiểm tra collision.",
            "independence_rule": "Một episode/audit observation không mặc định là một opportunity độc lập; chỉ canonical id khác mới là opportunity khác.",
        },
    }


def render_overlap_audit(overlap: dict[str, object]) -> str:
    """Render báo cáo overlap để reviewer thấy cả match raw và unique count."""

    methodology = overlap.get("methodology", {})
    field_comparison = overlap.get("field_comparison", {})
    examples = overlap.get("examples", [])
    return f"""# V81 ↔ V82 Opportunity Overlap Audit

## Counts

| Metric | Count |
| --- | ---: |
| V81 audit observations | `{overlap.get('v81_audit_observations', 0)}` |
| V82 audit observations | `{overlap.get('v82_audit_observations', 0)}` |
| Total audit observations | `{overlap.get('audit_observations', 0)}` |
| Unique V81 opportunities | `{overlap.get('unique_v81_opportunities', 0)}` |
| Unique V82 opportunities | `{overlap.get('unique_v82_opportunities', 0)}` |
| Exact timestamp + side matches | `{overlap.get('exact_timestamp_side_matches', 0)}` |
| Timestamp-only matches | `{overlap.get('timestamp_only_matches', 0)}` |
| Timestamp + side + entry matches | `{overlap.get('timestamp_side_entry_matches', 0)}` |
| Raw event_id matches | `{overlap.get('raw_event_id_matches', 0)}` |
| Confirmed same underlying opportunities | `{overlap.get('confirmed_same_underlying_opportunities', 0)}` |
| Confirmed independent opportunities | `{overlap.get('confirmed_independent_opportunities', 0)}` |
| Ambiguous matches | `{overlap.get('ambiguous_matches', 0)}` |
| Unexpected canonical collisions | `{overlap.get('unexpected_canonical_collisions', 0)}` |

## Interpretation

The database contains audit observations, not automatically independent opportunities. The canonical linkage currently confirms **{overlap.get('confirmed_same_underlying_opportunities', 0)}** V81↔V82 observation pairs as the same underlying opportunity. Therefore the combined unique opportunity count is not the sum of the two audit row counts.

The V81 source timestamp remains preserved as `source_time` with its existing `UTC / INFERRED` provenance. The observed one-hour offset is used only to explain the cross-audit match; it does not rewrite raw timestamps or timezone metadata.

## Methodology

- Exact timestamp + side: {methodology.get('exact_timestamp_side', '')}
- Timestamp-only: {methodology.get('timestamp_only', '')}
- Timestamp + side + entry: {methodology.get('timestamp_side_entry', '')}
- Canonical match: {methodology.get('canonical_match', '')}
- Canonical identity fields: `{', '.join(methodology.get('identity_fields', []))}`
- Excluded from identity: `{', '.join(methodology.get('excluded_fields', []))}`
- Timestamp reconciliation: {methodology.get('timestamp_reconciliation', '')}
- Independence rule: {methodology.get('independence_rule', '')}

## Field-by-field comparison

- Symbol exact matches: `{field_comparison.get('symbol_exact_matches', 0)}`; timeframe: `{field_comparison.get('timeframe_exact_matches', 0)}`; side: `{field_comparison.get('side_exact_matches', 0)}`.
- Candidate semantic + entry + stop + risk exact matches: `{field_comparison.get('candidate_semantic_entry_stop_risk_exact_matches', 0)}`.
- Common signal-context exact matches: `{field_comparison.get('signal_context_exact_matches', {})}`. Context fields not equal remain audit-specific source fields and were not silently overwritten.
- `setup_generation` present: V81 `{field_comparison.get('setup_generation_present', {}).get('V81', 0)}`, V82 `{field_comparison.get('setup_generation_present', {}).get('V82', 0)}`; setup generation is not used as a join key because V81 does not report the same field.
- {methodology.get('timestamp_identity_note', '')}

## Collision and provenance checks

- Same-audit duplicate canonical groups: `{overlap.get('same_audit_duplicate_canonical_groups', 0)}`.
- Unexpected canonical identity collisions: `{overlap.get('unexpected_canonical_collisions', 0)}`. A two-row V81/V82 group is intentional only when it has one row from each audit and the proven timestamp reconciliation.
- Timestamp offsets among confirmed pairs (hours): `{overlap.get('timestamp_offset_hours', {})}`.
- Raw `event_id` is retained per source as `raw_event_id`; it is not used as a cross-audit join key because V81 and V82 expose different identity formats.

## Sample linked pairs

```json
{json.dumps(examples, ensure_ascii=False, indent=2, sort_keys=True)}
```

Phase 2 export must carry `canonical_opportunity_id` and must not sample two audit observations with the same canonical id as independent training opportunities.
"""
