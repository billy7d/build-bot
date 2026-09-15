"""Build the Phase 2 canonical modeling layer above Phase 1 audit rows.

No Phase 1 row is modified or deleted.  Two audit observations for the same
``canonical_opportunity_id`` become one modeling sample, while the original
episode ids and field-level provenance remain available in JSON provenance.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from typing import Any, Iterable, Mapping

from ..data.normalization.timestamps import timestamp_to_datetime
from .fingerprint import canonical_json
from .registry import (
    CONTEXT_FEATURES,
    FEATURE_SET_VERSION,
    NUMERIC_FEATURES,
)


CANONICAL_VIEW_VERSION = "canonical-modeling-view/1"
# Hai exporter V81/V82 dùng precision khác nhau; tolerance này bao phủ sai số làm tròn tối đa 5e-5.
FEATURE_TOLERANCE = {"atol": 1e-4, "rtol": 1e-5}

_RAW_FEATURE_ALIASES: dict[str, tuple[str, ...]] = {
    "rsi": ("entry_rsi", "shadow_entry_rsi"),
    "atr_percent": ("entry_atr_pct",),
    "spread_r": ("entry_spread_r",),
    "return_std_20": ("entry_return_std_20",),
    "return_std_rank": ("entry_return_std_rank",),
    "price_std_20": ("entry_price_std_20",),
    "price_std_100": ("entry_price_std_100",),
    "price_std_pct_20": ("entry_price_std_pct_20",),
    "std_ratio_20_100": ("entry_std_ratio_20_100",),
    "price_z20": ("entry_price_z20",),
    "price_abs_z20": ("entry_price_abs_z20",),
    "rsi_std_20": ("entry_rsi_std_20",),
    "rsi_std_rank": ("entry_rsi_std_rank",),
    "atr_return_std_ratio": ("entry_atr_return_std_ratio",),
    "atr_return_std_rank": ("entry_atr_return_std_rank",),
    "entry_atr_rank": ("entry_atr_rank",),
    "entry_efficiency_20": ("entry_efficiency_20",),
    "initial_sl_atr": ("initial_sl_atr",),
    "d1_regime_score": ("d1_regime_score",),
    "h4_regime_score": ("h4_regime_score",),
    "composite_regime_score": ("composite_regime_score",),
}


class CanonicalViewError(ValueError):
    """Raised when the audit observations cannot be merged safely."""


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    try:
        loaded = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _compatible(left: Any, right: Any, *, atol: float = 1e-8, rtol: float = 1e-5) -> bool:
    if not _present(left) or not _present(right):
        return True
    left_number, right_number = _number(left), _number(right)
    if left_number is not None and right_number is not None:
        return math.isclose(left_number, right_number, abs_tol=atol, rel_tol=rtol)
    return str(left).strip().upper() == str(right).strip().upper()


def _merge_values(values: list[tuple[str, Any]]) -> tuple[Any, str, dict[str, Any]]:
    present = [(source, value) for source, value in values if _present(value)]
    provenance: dict[str, Any] = {
        "sources": [source for source, _ in present],
        "values": {source: value for source, value in present},
    }
    if not present:
        return None, "INSUFFICIENT", provenance
    first = present[0][1]
    if not all(_compatible(first, value, **FEATURE_TOLERANCE) for _, value in present[1:]):
        provenance["conflict"] = True
        return None, "CONFLICT", provenance
    numeric = [_number(value) for _, value in present]
    if all(value is not None for value in numeric):
        # Averaging compatible rounded source values is deterministic and does
        # not silently select an audit layer.
        merged: Any = sum(value for value in numeric if value is not None) / len(numeric)
    else:
        merged = first
    return merged, "VALID", provenance


def _first_hit_label(outcome: Mapping[str, Any]) -> int | None:
    """Build the classification target without interpreting incomplete data."""

    if int(outcome.get("resolved") or 0) != 1 or _present(outcome.get("incomplete_reason")):
        return None
    first = str(outcome.get("shadow_first_hit") or "").strip().upper()
    plus = outcome.get("shadow_plus_1r_first")
    minus = outcome.get("shadow_minus_1r_first")
    plus_true = plus is True or plus == 1 or str(plus).strip().lower() in {"true", "1", "yes"}
    minus_true = minus is True or minus == 1 or str(minus).strip().lower() in {"true", "1", "yes"}
    plus_seen = plus not in (None, "")
    minus_seen = minus not in (None, "")
    if first == "AMBIGUOUS" or (plus_true and minus_true):
        return None
    if first == "PLUS_1R" and ((plus_seen and not plus_true) or minus_true):
        return None
    if first == "MINUS_1R" and ((minus_seen and not minus_true) or plus_true):
        return None
    if first == "PLUS_1R" or (plus_true and not minus_true):
        return 1
    if first == "MINUS_1R" or (minus_true and not plus_true):
        return 0
    return None


def _label_record(outcome: Mapping[str, Any] | None) -> dict[str, Any]:
    if not outcome:
        return {
            "plus_1r_before_minus_1r": None,
            "shadow_return_24bar_r": None,
            "label_status": "INSUFFICIENT",
        }
    label = _first_hit_label(outcome)
    resolved = int(outcome.get("resolved") or 0) == 1
    incomplete = _present(outcome.get("incomplete_reason"))
    expected = _number(outcome.get("shadow_return_24bar_r")) if resolved and not incomplete else None
    return {
        "plus_1r_before_minus_1r": label,
        "shadow_plus_1r_first": outcome.get("shadow_plus_1r_first"),
        "shadow_minus_1r_first": outcome.get("shadow_minus_1r_first"),
        "shadow_first_hit": outcome.get("shadow_first_hit"),
        "shadow_return_6bar_r": _number(outcome.get("shadow_return_6bar_r")) if resolved and not incomplete else None,
        "shadow_return_12bar_r": _number(outcome.get("shadow_return_12bar_r")) if resolved and not incomplete else None,
        "shadow_return_24bar_r": expected,
        "shadow_return_48bar_r": _number(outcome.get("shadow_return_48bar_r")) if resolved and not incomplete else None,
        "shadow_mfe_r": _number(outcome.get("shadow_mfe_r")) if resolved and not incomplete else None,
        "shadow_mae_r": _number(outcome.get("shadow_mae_r")) if resolved and not incomplete else None,
        "resolved": int(resolved),
        "outcome_timestamp_utc": outcome.get("outcome_timestamp_utc"),
        "incomplete_reason": outcome.get("incomplete_reason"),
        "label_status": "VALID" if label is not None else "PARTIAL" if expected is not None else "INSUFFICIENT",
    }


def _observation(e: Mapping[str, Any], f: Mapping[str, Any] | None, c: Mapping[str, Any] | None, o: Mapping[str, Any] | None) -> dict[str, Any]:
    raw_features = _json((f or {}).get("raw_features_json"))
    feature_timestamp = (f or {}).get("feature_timestamp_utc") or e.get("timestamp_utc")
    if feature_timestamp and e.get("timestamp_utc") and timestamp_to_datetime(str(feature_timestamp)) > timestamp_to_datetime(str(e["timestamp_utc"])):
        raise CanonicalViewError(
            f"feature timestamp {feature_timestamp} is after opportunity timestamp {e['timestamp_utc']} "
            f"for episode {e.get('episode_id')}"
        )
    feature_values = {}
    local_feature_conflicts: list[str] = []
    local_feature_provenance: dict[str, Any] = {}
    for name in NUMERIC_FEATURES:
        value = (f or {}).get(name)
        aliases = [
            raw_features[alias]
            for alias in _RAW_FEATURE_ALIASES.get(name, ())
            if _present(raw_features.get(alias))
        ]
        if _present(value) and aliases and not all(_compatible(value, alias) for alias in aliases):
            local_feature_conflicts.append(name)
            local_feature_provenance[name] = {
                "feature_table": value,
                "raw_alias_values": aliases,
            }
            value = None
        elif not _present(value) and aliases:
            value = aliases[0]
        feature_values[name] = value
    context: dict[str, Any] = {}
    # The canonical context keys are only taken from the registered raw
    # event-time namespace.  Active/outcome context is intentionally absent.
    for name in CONTEXT_FEATURES:
        context[name] = raw_features.get(name)
    return {
        "episode_id": e.get("episode_id"),
        "source_artifact_id": e.get("source_artifact_id"),
        "audit_version": e.get("audit_version"),
        "timestamp_utc": e.get("timestamp_utc"),
        "feature_timestamp_utc": feature_timestamp,
        "feature_values": feature_values,
        "context": context,
        "context_record": dict(c or {}),
        "local_feature_conflicts": local_feature_conflicts,
        "local_feature_provenance": local_feature_provenance,
        "labels": _label_record(o if e.get("audit_version") == "V82" else None),
        "raw_feature_keys": sorted(raw_features),
    }


def _fetch_observations(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    episodes = connection.execute(
        "SELECT * FROM trading_episodes ORDER BY timestamp_utc, episode_id"
    ).fetchall()
    features = {
        str(row["episode_id"]): dict(row)
        for row in connection.execute("SELECT * FROM episode_features")
    }
    contexts = {
        str(row["episode_id"]): dict(row)
        for row in connection.execute("SELECT * FROM episode_opportunity_context")
    }
    outcomes = {
        str(row["episode_id"]): dict(row)
        for row in connection.execute("SELECT * FROM episode_opportunity_outcomes")
    }
    result: list[dict[str, Any]] = []
    for row in episodes:
        record = dict(row)
        canonical_id = str(record.get("canonical_opportunity_id") or "")
        if not canonical_id:
            raise CanonicalViewError(f"episode {record.get('episode_id')} has no canonical id")
        result.append(_observation(record, features.get(str(record["episode_id"])), contexts.get(str(record["episode_id"])), outcomes.get(str(record["episode_id"]))))
        result[-1]["episode"] = record
    return result


def build_canonical_view(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return one deterministic modeling row per canonical opportunity."""

    observations = _fetch_observations(connection)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        groups[str(observation["episode"]["canonical_opportunity_id"])].append(observation)

    rows: list[dict[str, Any]] = []
    for canonical_id in sorted(groups):
        items = sorted(
            groups[canonical_id],
            key=lambda item: (
                str(item["timestamp_utc"]),
                str(item["audit_version"] or ""),
                str(item["episode_id"]),
            ),
        )
        first_episode = items[0]["episode"]
        # Use the latest audit event as the canonical availability timestamp.
        # Phase 1 V81/V82 can differ by one hour; this prevents a later V81
        # feature from being assigned to an earlier canonical timestamp.
        timestamp = max(str(item["timestamp_utc"]) for item in items)
        feature_values: dict[str, Any] = {}
        context_values: dict[str, Any] = {}
        field_status: dict[str, str] = {}
        field_provenance: dict[str, Any] = {}
        conflicts: list[str] = []
        for name in NUMERIC_FEATURES:
            if any(name in item.get("local_feature_conflicts", []) for item in items):
                merged, status, provenance = None, "CONFLICT", {
                    "sources": [str(item["episode_id"]) for item in items],
                    "reason": "WITHIN_AUDIT_SOURCE_CONFLICT",
                    "values": {
                        str(item["episode_id"]): item.get("local_feature_provenance", {}).get(name)
                        for item in items
                        if name in item.get("local_feature_provenance", {})
                    },
                }
            else:
                merged, status, provenance = _merge_values(
                    [(str(item["episode_id"]), item["feature_values"].get(name)) for item in items]
                )
            feature_values[name] = merged
            field_status[name] = status
            field_provenance[name] = provenance
            if status == "CONFLICT":
                conflicts.append(name)
        for name in CONTEXT_FEATURES:
            merged, status, provenance = _merge_values(
                [(str(item["episode_id"]), item["context"].get(name)) for item in items]
            )
            context_values[name] = merged
            field_status[name] = status
            field_provenance[name] = provenance
            if status == "CONFLICT":
                conflicts.append(name)

        # Identity fields should already agree because Phase 1 assigned the
        # same canonical id.  Keep the conflict visible if a bad database is
        # supplied instead of silently choosing one audit.
        identity_fields = ("symbol", "timeframe", "side", "strategy_version")
        identity: dict[str, Any] = {}
        for name in identity_fields:
            merged, status, provenance = _merge_values(
                [(str(item["episode_id"]), item["episode"].get(name)) for item in items]
            )
            identity[name] = merged
            field_status[name] = status
            field_provenance[name] = provenance
            if status == "CONFLICT":
                conflicts.append(name)

        v82_labels = [
            (str(item["episode_id"]), item["labels"])
            for item in items if item["audit_version"] == "V82"
        ]
        labels: dict[str, Any] = _label_record(None)
        label_conflicts: list[str] = []
        if v82_labels:
            keys = sorted({key for _, label in v82_labels for key in label})
            for key in keys:
                merged, status, provenance = _merge_values(
                    [(episode_id, label.get(key)) for episode_id, label in v82_labels]
                )
                # For labels, compatible values are okay; conflicting labels
                # are quarantined rather than resolved by audit precedence.
                labels[key] = merged
                if status == "CONFLICT":
                    label_conflicts.append(key)
            labels["label_status"] = "CONFLICT" if label_conflicts else labels.get("label_status", "INSUFFICIENT")
        conflicts.extend(f"label.{field}" for field in label_conflicts)

        numeric_present = sum(_present(feature_values.get(name)) for name in NUMERIC_FEATURES)
        if conflicts:
            feature_status = "CONFLICT"
        elif numeric_present == 0:
            feature_status = "INSUFFICIENT"
        elif numeric_present < len(NUMERIC_FEATURES):
            feature_status = "PARTIAL"
        else:
            feature_status = "VALID"

        rows.append(
            {
                "canonical_opportunity_id": canonical_id,
                "timestamp_utc": timestamp,
                "canonical_timestamp_rule": "MAX_AUDIT_EVENT_TIMESTAMP_FOR_AVAILABILITY",
                **identity,
                "observation_count": len(items),
                "audit_versions": sorted({str(item["audit_version"] or "UNKNOWN") for item in items}),
                "episode_ids": [str(item["episode_id"]) for item in items],
                "source_artifact_ids": sorted({item["source_artifact_id"] for item in items}),
                "source_timestamps": {
                    str(item["episode_id"]): str(item["timestamp_utc"]) for item in items
                },
                "features": feature_values,
                "context": context_values,
                "feature_status": feature_status,
                "feature_conflicts": sorted(set(conflicts)),
                "field_status": field_status,
                "labels": labels,
                "provenance": {
                    "canonical_view_version": CANONICAL_VIEW_VERSION,
                    "feature_set_version": FEATURE_SET_VERSION,
                    "feature_tolerance": FEATURE_TOLERANCE,
                    "field_provenance": field_provenance,
                    "conflicts": sorted(set(conflicts)),
                    "observation_count": len(items),
                    "feature_available_timestamp_rule": "source feature timestamp <= canonical timestamp",
                },
            }
        )
    return rows


def persist_canonical_view(connection: sqlite3.Connection, rows: Iterable[Mapping[str, Any]]) -> int:
    records = list(rows)
    with connection:
        connection.execute("DELETE FROM canonical_opportunities")
        for row in records:
            connection.execute(
                """
                INSERT INTO canonical_opportunities(
                    canonical_opportunity_id, timestamp_utc, symbol, timeframe, side,
                    strategy_version, observation_count, feature_status, features_json,
                    context_json, labels_json, field_status_json, audit_versions_json,
                    episode_ids_json, provenance_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["canonical_opportunity_id"], row["timestamp_utc"], row.get("symbol"),
                    row.get("timeframe"), row.get("side"), row.get("strategy_version"),
                    row.get("observation_count", 0), row.get("feature_status", "INSUFFICIENT"),
                    canonical_json(row.get("features", {})), canonical_json(row.get("context", {})),
                    canonical_json(row.get("labels", {})), canonical_json(row.get("field_status", {})),
                    canonical_json(row.get("audit_versions", [])), canonical_json(row.get("episode_ids", [])),
                    canonical_json({
                        **dict(row.get("provenance", {})),
                        "source_artifact_ids": row.get("source_artifact_ids", []),
                        "source_timestamps": row.get("source_timestamps", {}),
                    }),
                    row.get("timestamp_utc"),
                ),
            )
    return len(records)


def load_canonical_view(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in connection.execute(
        "SELECT * FROM canonical_opportunities ORDER BY timestamp_utc, canonical_opportunity_id"
    ):
        item = dict(record)
        item["features"] = _json(item.pop("features_json", "{}"))
        item["context"] = _json(item.pop("context_json", "{}"))
        item["labels"] = _json(item.pop("labels_json", "{}"))
        item["field_status"] = _json(item.pop("field_status_json", "{}"))
        item["audit_versions"] = list(_json_list(item.pop("audit_versions_json", "[]")))
        item["episode_ids"] = list(_json_list(item.pop("episode_ids_json", "[]")))
        item["provenance"] = _json(item.pop("provenance_json", "{}"))
        item["source_artifact_ids"] = item["provenance"].get("source_artifact_ids", [])
        item["source_timestamps"] = item["provenance"].get("source_timestamps", {})
        item["feature_conflicts"] = list(item["provenance"].get("conflicts", []))
        rows.append(item)
    return rows


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        loaded = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return []
    return loaded if isinstance(loaded, list) else []


__all__ = [
    "CANONICAL_VIEW_VERSION",
    "CanonicalViewError",
    "FEATURE_TOLERANCE",
    "build_canonical_view",
    "build_canonical_opportunities",
    "load_canonical_view",
    "persist_canonical_view",
]

# Descriptive alias used by callers that treat the view as a dataset builder.
build_canonical_opportunities = build_canonical_view
