"""Chuyển NormalizedEvent thành episode, feature, context và outcome records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..models import NormalizedEvent
from ..normalization.canonical import canonical_opportunity_id
from ..normalization.identifiers import (
    deterministic_episode_id,
    normalize_fold_type,
)
from ..normalization.timestamps import add_bars


HORIZONS = (6, 12, 24, 48)
FEATURE_COLUMNS = (
    "rsi", "atr14", "atr_percent", "spread_r", "return_1", "return_3", "return_6",
    "return_std_20", "return_std_rank", "price_std_20", "price_std_100",
    "price_std_pct_20", "std_ratio_20_100", "price_z20", "price_abs_z20",
    "rsi_std_20", "rsi_std_rank", "atr_return_std_ratio", "atr_return_std_rank",
)
V81_FEATURE_SOURCE_MAP = {
    "rsi": "entry_rsi",
    "atr_percent": "entry_atr_pct",
    "spread_r": "entry_spread_r",
    "return_std_20": "entry_return_std_20",
    "return_std_rank": "entry_return_std_rank",
    "price_std_20": "entry_price_std_20",
    "price_std_100": "entry_price_std_100",
    "price_std_pct_20": "entry_price_std_pct_20",
    "std_ratio_20_100": "entry_std_ratio_20_100",
    "price_z20": "entry_price_z20",
    "price_abs_z20": "entry_price_abs_z20",
    "rsi_std_20": "entry_rsi_std_20",
    "rsi_std_rank": "entry_rsi_std_rank",
    "atr_return_std_ratio": "entry_atr_return_std_ratio",
    "atr_return_std_rank": "entry_atr_return_std_rank",
}
V82_FEATURE_SOURCE_MAP = {
    "rsi": "shadow_entry_rsi",
    "atr_percent": "entry_atr_pct",
    "spread_r": "entry_spread_r",
}
V81_EVENT_TIME_FEATURE_FIELDS = {
    "entry_atr_pct", "entry_atr_rank", "entry_efficiency_20", "entry_spread_r",
    "initial_sl_atr", "d1_regime_score", "h4_regime_score", "composite_regime_score",
}
V82_EVENT_TIME_FEATURE_FIELDS = {
    "shadow_entry_rsi", "shadow_entry_rsi_ema", "shadow_entry_rsi_wma",
    "d1_bias", "h4_bias", "h1_bias", "d1_regime_score", "h4_regime_score",
    "composite_regime_score", "entry_atr_pct", "entry_atr_rank", "entry_efficiency_20",
    "entry_spread_r", "initial_sl_atr", "shadow_spread",
}


@dataclass(frozen=True)
class EpisodeBundle:
    episode: Mapping[str, Any]
    features: Mapping[str, Any]
    outcome: Mapping[str, Any]
    opportunity_context: Mapping[str, Any] | None
    active_context: Mapping[str, Any] | None
    opportunity_outcome: Mapping[str, Any] | None


def _text(fields: Mapping[str, Any], key: str, default: str | None = None) -> str | None:
    value = fields.get(key)
    if value is None:
        return default
    raw = str(value).strip()
    return raw or default


def _bool(fields: Mapping[str, Any], key: str) -> bool | None:
    value = fields.get(key)
    return value if isinstance(value, bool) else None if value is None else str(value).lower() in {"true", "1", "yes"}


def _number(fields: Mapping[str, Any], key: str) -> int | float | None:
    value = fields.get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _first_hit(fields: Mapping[str, Any], key: str) -> str | None:
    value = _text(fields, key)
    return value.upper() if value else None


def _episode_kind(event: NormalizedEvent) -> tuple[str, str]:
    raw_type = (_text(event.fields, "raw_event_type", "UNKNOWN") or "UNKNOWN").upper()
    if event.audit_version == "V82":
        if raw_type in {"BLOCKED_OPPOSITE", "BLOCKED_SAME_SIDE"}:
            return "BLOCKED_OPPORTUNITY", "BLOCKED"
        if raw_type in {"LONG_ONLY", "SHORT_ONLY"}:
            return "CONTROL_OPPORTUNITY", "CONTROL"
        if raw_type == "SIMULTANEOUS_CONFLICT":
            return "SIMULTANEOUS_CONFLICT", "CONTROL"
    if event.audit_version == "V81":
        if raw_type.startswith("FLAT_"):
            return "FLAT_CANDIDATE", "FLAT"
        if raw_type.startswith("OPEN_"):
            return "BLOCKED_OPPORTUNITY", "BLOCKED"
    return "UNKNOWN", "UNKNOWN"


def _outcome_time(event: NormalizedEvent, fields: Mapping[str, Any]) -> str | None:
    if not _bool(fields, "completed"):
        return None
    age = _number(fields, "age_bars") or 48
    return add_bars(event.event_time_utc, int(age))


def _feature_record(event: NormalizedEvent) -> dict[str, Any]:
    mapping = V81_FEATURE_SOURCE_MAP if event.audit_version == "V81" else V82_FEATURE_SOURCE_MAP
    record: dict[str, Any] = {column: None for column in FEATURE_COLUMNS}
    provenance: dict[str, str] = {}
    raw_features: dict[str, Any] = {}
    for target, source in mapping.items():
        value = event.fields.get(source)
        record[target] = value
        if value is not None:
            provenance[target] = "SOURCE_REPORTED"
    if event.audit_version == "V82":
        raw_features = {
            key: event.fields.get(key)
            for key in sorted(V82_EVENT_TIME_FEATURE_FIELDS)
            if event.fields.get(key) is not None
        }
    else:
        raw_features = {
            source: event.fields.get(source)
            for source in sorted(
                set(V81_FEATURE_SOURCE_MAP.values()) | V81_EVENT_TIME_FEATURE_FIELDS
                | {key for key in event.fields if key.startswith("add_")}
            )
            if event.fields.get(source) is not None
        }
    record.update(
        {
            "episode_id": None,
            "feature_schema_version": "TA-FEATURE-V1",
            "feature_provenance": provenance,
            "feature_timestamp_utc": event.event_time_utc,
            "raw_features": raw_features,
        }
    )
    return record


def _generic_outcome(event: NormalizedEvent, episode_id: str) -> dict[str, Any]:
    fields = event.fields
    is_v81 = event.audit_version == "V81"
    prefix = "" if is_v81 else "shadow_"
    if is_v81:
        hit_plus = _first_hit(fields, "first_hit") == "PLUS_1R"
        hit_minus = _first_hit(fields, "first_hit") == "MINUS_1R"
        forward = {f"forward_return_{h}h": _number(fields, f"return_{h}") for h in HORIZONS}
        mfe, mae = _number(fields, "mfe_r"), _number(fields, "mae_r")
        first_hit = _first_hit(fields, "first_hit")
    else:
        hit_plus = _bool(fields, "shadow_plus_1r_first")
        hit_minus = _bool(fields, "shadow_minus_1r_first")
        forward = {
            f"forward_return_{h}h": _number(fields, f"shadow_return_{h}bar_r") for h in HORIZONS
        }
        mfe, mae = _number(fields, "shadow_mfe_r"), _number(fields, "shadow_mae_r")
        first_hit = _first_hit(fields, "shadow_first_hit")
    return {
        "episode_id": episode_id,
        "resolved": int(bool(_bool(fields, "completed"))),
        "mfe_r": mfe,
        "mae_r": mae,
        "hit_plus_1r_first": first_hit if first_hit == "PLUS_1R" else None,
        "hit_minus_1r_first": first_hit if first_hit == "MINUS_1R" else None,
        **forward,
        "bars_to_mfe": None,
        "bars_to_mae": None,
        "outcome_timestamp_utc": _outcome_time(event, fields),
        "incomplete_reason": _text(fields, "incomplete_reason"),
        "outcome_schema_version": "TA-OUTCOME-V1",
    }


def _opportunity_context(event: NormalizedEvent, episode_id: str) -> dict[str, Any]:
    fields = event.fields
    raw_type = (_text(fields, "raw_event_type", "UNKNOWN") or "UNKNOWN").upper()
    active = _text(fields, "active_side", "NONE") or "NONE"
    shadow = _text(fields, "shadow_side", _text(fields, "side", "NONE")) or "NONE"
    selected = _text(fields, "actual_selected_side", "NONE") or "NONE"
    blocked = _text(fields, "blocked_side", "NONE") or "NONE"
    direction = _text(fields, "direction", raw_type) or raw_type
    return {
        "episode_id": episode_id,
        "event_type": raw_type,
        "active_side": active,
        "shadow_side": shadow,
        "actual_selected_side": selected,
        "blocked_side": blocked,
        "direction": direction,
        "setup_generation": _number(fields, "setup_generation"),
        "active_group_id": _text(fields, "active_group_id"),
        "active_base_position_identifier": _text(fields, "active_base_position_identifier"),
        "shadow_build_valid": _bool(fields, "shadow_build_valid"),
        "shadow_build_reason": _text(fields, "shadow_build_reason"),
        "long_reject": _text(fields, "long_reject"),
        "short_reject": _text(fields, "short_reject"),
        "source_provenance": "SOURCE_REPORTED",
    }


def _active_context(event: NormalizedEvent, episode_id: str) -> dict[str, Any]:
    fields = event.fields
    return {
        "episode_id": episode_id,
        "active_entry_price": _number(fields, "active_entry_price"),
        "active_current_price": _number(fields, "active_current_price"),
        "active_initial_risk": _number(fields, "active_initial_risk"),
        "active_initial_risk_distance": _number(fields, "active_initial_risk_distance"),
        "active_current_r": _number(fields, "active_current_r"),
        "active_sl": _number(fields, "active_sl"),
        "active_is_be": _bool(fields, "active_is_be"),
        "active_tp1_done": _bool(fields, "active_tp1_done"),
        "active_tp2_done": _bool(fields, "active_tp2_done"),
        "active_runner_active": _bool(fields, "active_runner_active"),
        "active_pyramid_adds": _number(fields, "active_pyramid_adds"),
        "active_bars_open": _number(fields, "active_bars_open"),
        "active_locked_profit_r": _number(fields, "active_locked_profit_r"),
        "active_group_volume": _number(fields, "active_group_volume"),
        "active_position_count": _number(fields, "active_position_count"),
        "active_value_at_event_r": _number(fields, "active_value_at_event_r"),
        "source_provenance": "SOURCE_REPORTED",
    }


def _opportunity_outcome(event: NormalizedEvent, episode_id: str) -> dict[str, Any]:
    fields = event.fields
    record: dict[str, Any] = {
        "episode_id": episode_id,
        "shadow_plus_1r_hit": _bool(fields, "shadow_plus_1r_hit"),
        "shadow_minus_1r_hit": _bool(fields, "shadow_minus_1r_hit"),
        "shadow_plus_1r_first": _bool(fields, "shadow_plus_1r_first"),
        "shadow_minus_1r_first": _bool(fields, "shadow_minus_1r_first"),
        "shadow_first_hit": _first_hit(fields, "shadow_first_hit"),
        "shadow_mfe_r": _number(fields, "shadow_mfe_r"),
        "shadow_mae_r": _number(fields, "shadow_mae_r"),
        "active_plus_1r_hit": _bool(fields, "active_plus_1r_hit"),
        "active_minus_1r_hit": _bool(fields, "active_minus_1r_hit"),
        "active_first_hit": _first_hit(fields, "active_first_hit"),
        "actual_selected_build_valid": _bool(fields, "actual_selected_build_valid"),
        "actual_selected_first_hit": _first_hit(fields, "actual_selected_first_hit"),
        "actual_selected_mfe_r": _number(fields, "actual_selected_mfe_r"),
        "actual_selected_mae_r": _number(fields, "actual_selected_mae_r"),
        "resolved": int(bool(_bool(fields, "completed"))),
        "outcome_timestamp_utc": _outcome_time(event, fields),
        "incomplete_reason": _text(fields, "incomplete_reason"),
        "outcome_schema_version": "TA-OPPORTUNITY-OUTCOME-V1",
        "source_provenance": "SOURCE_REPORTED",
    }
    for prefix in ("shadow_return", "active_value", "active_continuation", "actual_selected_return", "opportunity_diff"):
        for horizon in HORIZONS:
            record[f"{prefix}_{horizon}bar_r"] = _number(fields, f"{prefix}_{horizon}bar_r")
    for prefix in ("actual_selected",):
        for field in ("entry_price", "initial_sl", "risk_distance"):
            record[f"{prefix}_{field}"] = _number(fields, f"{prefix}_{field}")
        for field in ("plus_1r_hit", "minus_1r_hit", "plus_1r_first", "minus_1r_first"):
            record[f"{prefix}_{field}"] = _bool(fields, f"{prefix}_{field}")
    return record


def build_bundle(
    event: NormalizedEvent,
    *,
    source_artifact_id: int,
    experiment_id: str | None,
    preset_id: str | None,
    ordinal: int,
) -> EpisodeBundle:
    kind, candidate_type = _episode_kind(event)
    episode_id = deterministic_episode_id(
        symbol=event.symbol,
        timeframe=event.timeframe,
        timestamp_utc=event.event_time_utc,
        strategy_version=event.strategy_version,
        audit_version=event.audit_version,
        side=event.side,
        episode_kind=kind,
        ordinal=ordinal,
    )
    fields = event.fields
    episode = {
        "episode_id": episode_id,
        "source_artifact_id": source_artifact_id,
        "experiment_id": experiment_id,
        "strategy_version": event.strategy_version,
        "audit_version": event.audit_version,
        "preset_id": preset_id,
        "symbol": event.symbol,
        "timeframe": event.timeframe,
        "source_time": event.source_time,
        "source_timezone": event.source_timezone,
        "timestamp_utc": event.event_time_utc,
        "side": event.side,
        "episode_kind": kind,
        "candidate_type": candidate_type,
        "candidate_exists": 1,
        "was_executed": 0,
        "execution_id": None,
        "entry_candidate": event.price,
        "stop_candidate": _number(fields, "initial_sl") if event.audit_version == "V81" else _number(fields, "shadow_initial_sl"),
        "target_candidate": None,
        "planned_risk_r": None,
        "fold_type": normalize_fold_type(fields.get("fold"), event.event_time_utc),
        "raw_event_id": event.raw_event_id,
        "raw_fields_json": json.dumps(dict(event.raw_fields), ensure_ascii=False, sort_keys=True, allow_nan=False),
        "canonical_opportunity_id": canonical_opportunity_id(event),
        # Dùng mốc event ổn định để rebuild cùng raw tạo record deterministic.
        "created_at": event.event_time_utc,
    }
    features = _feature_record(event)
    features["episode_id"] = episode_id
    outcome = _generic_outcome(event, episode_id)
    if event.audit_version == "V82":
        return EpisodeBundle(
            episode=episode,
            features=features,
            outcome=outcome,
            opportunity_context=_opportunity_context(event, episode_id),
            active_context=_active_context(event, episode_id),
            opportunity_outcome=_opportunity_outcome(event, episode_id),
        )
    return EpisodeBundle(
        episode=episode,
        features=features,
        outcome=outcome,
        opportunity_context=None,
        active_context=None,
        opportunity_outcome=None,
    )
