"""Validate closed-world telemetry trước khi canonicalize/scoring."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from ...features.registry import FeatureLeakageError, FeatureSchemaError, FEATURE_ALLOWLIST, is_outcome_field, validate_feature_columns
from ..models import PHASE3_TELEMETRY_SCHEMA, TelemetryEvent, format_utc_timestamp, parse_utc_timestamp, utc_now


class TelemetryValidationError(ValueError):
    """Telemetry bị reject, không được silent drop."""

    def __init__(self, message: str, *, reason: str = "SCHEMA_INVALID") -> None:
        super().__init__(message)
        self.reason = reason


_ALLOWED_BAR_STATES = frozenset({"closed_bar", "forming_bar", "event_instant"})
_CONTEXT_METADATA = frozenset({
    "features", "feature_values", "bar_state", "available_at", "available_at_utc",
    "candidate_type", "source_timezone", "source", "event_timestamp", "event_timestamp_utc",
})
_CONTEXT_RESOLUTION = frozenset({
    "entry_price", "risk_distance", "active_entry_price", "initial_risk_distance",
    "initial_sl_distance", "price",
})


def _future_key(name: str) -> bool:
    lowered = str(name).strip().lower()
    if is_outcome_field(lowered):
        return True
    return (
        lowered in {"outcome", "outcomes", "label", "labels", "future", "future_bars", "price_after"}
        or lowered.startswith("future_")
        or lowered.endswith("_outcome")
        or lowered.endswith("_label")
    )


def _scan_for_future_fields(value: Any, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _future_key(str(key)):
                raise TelemetryValidationError(
                    f"future/outcome field rejected at {path}.{key}", reason="FUTURE_FIELD"
                )
            _scan_for_future_fields(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_for_future_fields(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise TelemetryValidationError(f"non-finite numeric value at {path}", reason="NON_FINITE")


def _text(payload: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _context_features(context: Mapping[str, Any]) -> dict[str, Any]:
    nested = context.get("features", context.get("feature_values", {}))
    if nested is not None and not isinstance(nested, Mapping):
        raise TelemetryValidationError("context.features must be an object", reason="FEATURE_SCHEMA")
    values = dict(nested or {})
    for name in FEATURE_ALLOWLIST:
        if name in context:
            values[name] = context[name]
    try:
        validate_feature_columns(values.keys())
    except (FeatureLeakageError, FeatureSchemaError) as exc:
        raise TelemetryValidationError(str(exc), reason="FEATURE_SCHEMA") from exc
    return {str(key): values[key] for key in sorted(values)}


def validate_telemetry_payload(
    payload: Mapping[str, Any],
    *,
    source: str = "telemetry",
    received_at_utc: str | None = None,
) -> TelemetryEvent:
    """Validate schema/version/time/features và giữ nguyên raw payload."""

    if not isinstance(payload, Mapping):
        raise TelemetryValidationError("telemetry record must be an object", reason="SCHEMA_INVALID")
    try:
        raw_payload = json.loads(json.dumps(dict(payload), ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise TelemetryValidationError("telemetry payload is not JSON-safe", reason="SCHEMA_INVALID") from exc
    _scan_for_future_fields(raw_payload)

    schema_version = _text(raw_payload, "schema_version")
    if schema_version != PHASE3_TELEMETRY_SCHEMA:
        raise TelemetryValidationError(
            f"unknown telemetry schema: {schema_version or '<missing>'}", reason="UNKNOWN_SCHEMA"
        )
    source_event_id = _text(raw_payload, "source_event_id")
    if not source_event_id:
        raise TelemetryValidationError("source_event_id is required", reason="MISSING_SOURCE_EVENT_ID")
    if len(source_event_id) > 256:
        raise TelemetryValidationError("source_event_id is too long", reason="SOURCE_EVENT_ID_TOO_LONG")

    event_timestamp = _text(raw_payload, "event_timestamp", "event_timestamp_utc")
    if not event_timestamp:
        raise TelemetryValidationError("event_timestamp is required", reason="MISSING_TIMESTAMP")
    try:
        event_timestamp_utc = format_utc_timestamp(event_timestamp)
    except ValueError as exc:
        raise TelemetryValidationError(str(exc), reason="INVALID_TIMESTAMP") from exc

    received_value = received_at_utc or _text(raw_payload, "received_at_utc", "received_at") or utc_now()
    try:
        received_value = format_utc_timestamp(received_value)
    except ValueError as exc:
        raise TelemetryValidationError(str(exc), reason="INVALID_RECEIVED_TIMESTAMP") from exc

    symbol = _text(raw_payload, "symbol")
    timeframe = _text(raw_payload, "timeframe")
    side = _text(raw_payload, "side").upper()
    if not symbol or not timeframe or not side:
        raise TelemetryValidationError("symbol, timeframe and side are required", reason="MISSING_CONTEXT")
    if side not in {"LONG", "SHORT"}:
        raise TelemetryValidationError(f"unsupported side: {side!r}", reason="INVALID_SIDE")

    context = raw_payload.get("context")
    if not isinstance(context, Mapping):
        raise TelemetryValidationError("context object is required", reason="MISSING_CONTEXT")
    unknown_context = set(context) - (_CONTEXT_METADATA | _CONTEXT_RESOLUTION | FEATURE_ALLOWLIST)
    if unknown_context:
        raise TelemetryValidationError(
            "unknown context field rejected (closed world): " + ", ".join(sorted(map(str, unknown_context))),
            reason="CONTEXT_SCHEMA",
        )
    _context_features(context)
    candidate_type = _text(raw_payload, "candidate_type") or _text(context, "candidate_type") or "UNKNOWN"
    bar_state = (_text(raw_payload, "bar_state") or _text(context, "bar_state") or "closed_bar").lower()
    if bar_state not in _ALLOWED_BAR_STATES:
        raise TelemetryValidationError(f"unsupported bar_state: {bar_state!r}", reason="INVALID_BAR_STATE")
    available = _text(raw_payload, "available_at_utc", "available_at") or _text(context, "available_at_utc", "available_at")
    if available:
        try:
            available = format_utc_timestamp(available)
        except ValueError as exc:
            raise TelemetryValidationError(str(exc), reason="INVALID_AVAILABLE_TIMESTAMP") from exc
        if parse_utc_timestamp(available) > parse_utc_timestamp(event_timestamp_utc):
            raise TelemetryValidationError(
                "feature availability cannot be after event timestamp",
                reason="FEATURE_NOT_AVAILABLE",
            )
    source_timezone = _text(raw_payload, "source_timezone") or _text(context, "source_timezone") or None
    return TelemetryEvent(
        schema_version=schema_version,
        source_event_id=source_event_id,
        event_timestamp_utc=event_timestamp_utc,
        symbol=symbol,
        timeframe=timeframe,
        side=side,
        context=dict(context),
        source=str(source or _text(raw_payload, "source") or "telemetry"),
        received_at_utc=received_value,
        raw_payload=raw_payload,
        candidate_type=candidate_type,
        bar_state=bar_state,
        available_at_utc=available or None,
        source_timezone=source_timezone,
    )


__all__ = ["TelemetryValidationError", "validate_telemetry_payload"]
