"""Hợp đồng raw opportunity và adapter dùng lại canonicalizer Phase 1."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

from ...data.models import NormalizedEvent
from ...data.normalization.canonical import (
    CANONICAL_LINKAGE_VERSION,
    _SEMANTIC_ALIASES,
    canonical_opportunity_id,
)
from ...features.fingerprint import fingerprint
from ...features.registry import FeatureLeakageError, FeatureSchemaError, validate_feature_columns
from ..models import (
    PHASE3_CANONICAL_OPPORTUNITY_SCHEMA,
    PHASE3_CANONICALIZER_VERSION,
    PHASE3_OPPORTUNITY_SCHEMA,
    TelemetryEvent,
    finite_float,
    format_utc_timestamp,
    parse_utc_timestamp,
    utc_now,
)
from .validation import TelemetryValidationError, _scan_for_future_fields


CANONICALIZER_FINGERPRINT = fingerprint(
    {
        "canonicalizer_version": PHASE3_CANONICALIZER_VERSION,
        "source_of_truth": "agent.data.normalization.canonical.canonical_opportunity_id",
        "linkage_version": CANONICAL_LINKAGE_VERSION,
        "identity_fields": [
            "strategy_version",
            "symbol",
            "timeframe",
            "side",
            "candidate_semantic",
            "entry",
            "stop",
            "risk_distance",
        ],
        "semantic_aliases": dict(sorted(_SEMANTIC_ALIASES.items())),
    }
)


class OpportunityValidationError(TelemetryValidationError):
    """Raw opportunity không qua được closed-world contract."""


_OPPORTUNITY_REQUIRED = frozenset(
    {
        "schema_version",
        "source_observation_id",
        "event_timestamp_utc",
        "emitted_at_utc",
        "source_strategy",
        "source_strategy_version",
        "symbol",
        "timeframe",
        "side",
        "source_audit_family",
        "source_event_type",
        "bar_state",
        "context",
        "execution_context",
        "risk_distance",
        "initial_sl_distance",
    }
)
_OPPORTUNITY_OPTIONAL = frozenset(
    {
        "event_timestamp",
        "source",
        "received_at_utc",
        "received_at",
        "source_timezone",
        "available_at_utc",
        "available_at",
        "candidate_type",
        "entry_price",
        "hypothetical_entry_price",
        "hypothetical_initial_sl",
        "initial_sl",
        "build_valid",
        "build_reason",
    }
)
_CONTEXT_KEYS = frozenset({"features", "feature_values"})
_EXECUTION_CONTEXT_KEYS = frozenset(
    {
        "audit_family",
        "active_position_state",
        "position_state",
        "active_side",
        "blocked_side",
        "selected_side",
        "blocked_reason",
        "execution_eligible",
    }
)
_PROHIBITED_FUTURE_NAMES = frozenset(
    {
        "future_return",
        "return_6bar",
        "return_12bar",
        "return_24bar",
        "return_48bar",
        "mfe",
        "mae",
        "plus_1r_hit",
        "minus_1r_hit",
        "first_hit",
        "trade_profit",
        "future_bars",
        "resolved_label",
    }
)


def _text(payload: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _number(payload: Mapping[str, Any], *names: str) -> float | None:
    for name in names:
        if name in payload and payload[name] is not None:
            value = finite_float(payload[name])
            if value is None:
                raise OpportunityValidationError(
                    f"{name} must be a finite number", reason="NON_FINITE"
                )
            return value
    return None


def _future_scan(value: Any, path: str = "payload") -> None:
    """Bổ sung các tên outcome ngắn mà registry không cần dùng cho feature V1."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).strip().lower()
            if lowered in _PROHIBITED_FUTURE_NAMES:
                raise OpportunityValidationError(
                    f"future/outcome field rejected at {path}.{key}", reason="FUTURE_FIELD"
                )
            _future_scan(child, f"{path}.{key}")
        _scan_for_future_fields(value, path)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _future_scan(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise OpportunityValidationError(f"non-finite numeric value at {path}", reason="NON_FINITE")


def _feature_values(context: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(context) - _CONTEXT_KEYS
    if unknown:
        raise OpportunityValidationError(
            "unknown context field rejected (closed world): " + ", ".join(sorted(map(str, unknown))),
            reason="CONTEXT_SCHEMA",
        )
    values = context.get("features", context.get("feature_values", {}))
    if not isinstance(values, Mapping):
        raise OpportunityValidationError("context.features must be an object", reason="FEATURE_SCHEMA")
    try:
        validate_feature_columns(values.keys())
    except (FeatureLeakageError, FeatureSchemaError) as exc:
        raise OpportunityValidationError(str(exc), reason="FEATURE_SCHEMA") from exc
    return {str(key): values[key] for key in sorted(values)}


@dataclass(frozen=True)
class OpportunityObservation:
    """Một raw opportunity event trước canonicalization và scoring."""

    schema_version: str
    source_observation_id: str
    event_timestamp_utc: str
    emitted_at_utc: str
    source_strategy: str
    source_strategy_version: str
    symbol: str
    timeframe: str
    side: str
    source_audit_family: str
    source_event_type: str
    bar_state: str
    context_features: Mapping[str, Any]
    execution_context: Mapping[str, Any]
    entry_price: float | None
    hypothetical_entry_price: float | None
    risk_distance: float | None
    initial_sl_distance: float | None
    hypothetical_initial_sl: float | None
    build_valid: bool
    build_reason: str | None
    source: str
    received_at_utc: str
    source_timezone: str | None
    candidate_type: str
    raw_payload: Mapping[str, Any]
    available_at_utc: str | None = None

    @property
    def price(self) -> float | None:
        """Chọn đúng giá identity theo semantics của V81/V82."""

        if self.source_audit_family == "V82":
            return self.hypothetical_entry_price or self.entry_price
        return self.entry_price or self.hypothetical_entry_price

    @property
    def initial_sl(self) -> float | None:
        return self.hypothetical_initial_sl

    def to_telemetry_event(self) -> TelemetryEvent:
        return TelemetryEvent(
            schema_version=self.schema_version,
            source_event_id=self.source_observation_id,
            event_timestamp_utc=self.event_timestamp_utc,
            symbol=self.symbol,
            timeframe=self.timeframe,
            side=self.side,
            context={"features": dict(self.context_features)},
            source=self.source,
            received_at_utc=self.received_at_utc,
            raw_payload=self.raw_payload,
            emitted_at_utc=self.emitted_at_utc,
            source_strategy=self.source_strategy,
            source_strategy_version=self.source_strategy_version,
            candidate_type=self.candidate_type,
            bar_state=self.bar_state,
            available_at_utc=self.available_at_utc,
            source_timezone=self.source_timezone,
        )


@dataclass(frozen=True)
class CanonicalOpportunity:
    """Kết quả adapter, giữ cả event Phase 1 để audit có thể kiểm tra lại."""

    observation: OpportunityObservation
    normalized_event: NormalizedEvent
    canonical_opportunity_id: str
    canonical_schema: str = PHASE3_CANONICAL_OPPORTUNITY_SCHEMA
    canonicalizer_version: str = PHASE3_CANONICALIZER_VERSION
    canonicalizer_fingerprint: str = CANONICALIZER_FINGERPRINT


def validate_opportunity_payload(
    payload: Mapping[str, Any],
    *,
    source: str = "opportunity",
    received_at_utc: str | None = None,
) -> OpportunityObservation:
    """Validate raw opportunity mà không cho outcome lọt vào feature namespace."""

    if not isinstance(payload, Mapping):
        raise OpportunityValidationError("opportunity record must be an object")
    try:
        raw_payload = json.loads(json.dumps(dict(payload), ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise OpportunityValidationError("opportunity payload is not JSON-safe") from exc
    _future_scan(raw_payload)
    missing = sorted(_OPPORTUNITY_REQUIRED - set(raw_payload))
    if missing:
        raise OpportunityValidationError(
            "opportunity fields are missing: " + ", ".join(missing), reason="MISSING_FIELD"
        )
    unknown = set(raw_payload) - (_OPPORTUNITY_REQUIRED | _OPPORTUNITY_OPTIONAL)
    if unknown:
        raise OpportunityValidationError(
            "unknown opportunity field rejected (closed world): " + ", ".join(sorted(map(str, unknown))),
            reason="SCHEMA_INVALID",
        )
    if _text(raw_payload, "schema_version") != PHASE3_OPPORTUNITY_SCHEMA:
        raise OpportunityValidationError(
            f"unknown opportunity schema: {_text(raw_payload, 'schema_version') or '<missing>'}",
            reason="UNKNOWN_SCHEMA",
        )
    observation_id = _text(raw_payload, "source_observation_id")
    if not observation_id:
        raise OpportunityValidationError("source_observation_id is required", reason="MISSING_SOURCE_OBSERVATION_ID")
    if len(observation_id) > 256:
        raise OpportunityValidationError("source_observation_id is too long", reason="SOURCE_ID_TOO_LONG")

    event_value = _text(raw_payload, "event_timestamp_utc", "event_timestamp")
    emitted_value = _text(raw_payload, "emitted_at_utc")
    if not event_value or not emitted_value:
        raise OpportunityValidationError("event and emitted timestamps are required", reason="MISSING_TIMESTAMP")
    try:
        event_timestamp = format_utc_timestamp(event_value)
        emitted_at = format_utc_timestamp(emitted_value)
    except ValueError as exc:
        raise OpportunityValidationError(str(exc), reason="INVALID_TIMESTAMP") from exc

    received_value = received_at_utc or _text(raw_payload, "received_at_utc", "received_at") or utc_now()
    try:
        received_value = format_utc_timestamp(received_value)
    except ValueError as exc:
        raise OpportunityValidationError(str(exc), reason="INVALID_RECEIVED_TIMESTAMP") from exc
    available = _text(raw_payload, "available_at_utc", "available_at") or None
    if available:
        try:
            available = format_utc_timestamp(available)
        except ValueError as exc:
            raise OpportunityValidationError(str(exc), reason="INVALID_AVAILABLE_TIMESTAMP") from exc
        if parse_utc_timestamp(available) > parse_utc_timestamp(event_timestamp):
            raise OpportunityValidationError(
                "feature availability cannot be after event timestamp", reason="FEATURE_NOT_AVAILABLE"
            )

    source_strategy = _text(raw_payload, "source_strategy")
    source_version = _text(raw_payload, "source_strategy_version")
    symbol = _text(raw_payload, "symbol")
    timeframe = _text(raw_payload, "timeframe")
    side = _text(raw_payload, "side").upper()
    audit_family = _text(raw_payload, "source_audit_family").upper()
    event_type = _text(raw_payload, "source_event_type").upper()
    if not all((source_strategy, source_version, symbol, timeframe, event_type)):
        raise OpportunityValidationError("strategy, version, symbol, timeframe and event type are required", reason="MISSING_CONTEXT")
    if side not in {"LONG", "SHORT"}:
        raise OpportunityValidationError(f"unsupported side: {side!r}", reason="INVALID_SIDE")
    if audit_family not in {"V81", "V82"}:
        raise OpportunityValidationError(f"unsupported source_audit_family: {audit_family!r}", reason="UNSUPPORTED_AUDIT_FAMILY")
    bar_state = _text(raw_payload, "bar_state").lower()
    if bar_state != "closed_bar":
        raise OpportunityValidationError("bar_state must be closed_bar", reason="INVALID_BAR_STATE")
    context = raw_payload.get("context")
    if not isinstance(context, Mapping):
        raise OpportunityValidationError("context object is required", reason="MISSING_CONTEXT")
    features = _feature_values(context)
    execution_context = raw_payload.get("execution_context")
    if not isinstance(execution_context, Mapping):
        raise OpportunityValidationError("execution_context object is required", reason="MISSING_EXECUTION_CONTEXT")
    unknown_execution = set(execution_context) - _EXECUTION_CONTEXT_KEYS
    if unknown_execution:
        raise OpportunityValidationError(
            "unknown execution_context field rejected (closed world): " + ", ".join(sorted(map(str, unknown_execution))),
            reason="EXECUTION_CONTEXT_SCHEMA",
        )
    if "execution_eligible" in execution_context and not isinstance(execution_context["execution_eligible"], bool):
        raise OpportunityValidationError("execution_eligible must be boolean", reason="EXECUTION_CONTEXT_SCHEMA")
    _future_scan(execution_context, "payload.execution_context")

    entry_price = _number(raw_payload, "entry_price")
    hypothetical_entry = _number(raw_payload, "hypothetical_entry_price")
    risk_distance = _number(raw_payload, "risk_distance")
    initial_sl_distance = _number(raw_payload, "initial_sl_distance")
    explicit_sl = _number(raw_payload, "hypothetical_initial_sl", "initial_sl")
    build_value = raw_payload.get("build_valid", True)
    if not isinstance(build_value, bool):
        raise OpportunityValidationError("build_valid must be boolean", reason="INVALID_BUILD_STATUS")
    build_reason = _text(raw_payload, "build_reason") or None
    if not build_value and not build_reason:
        raise OpportunityValidationError("invalid build requires build_reason", reason="INVALID_BUILD_REASON")
    if build_value:
        price = hypothetical_entry if audit_family == "V82" else entry_price
        price = price if price is not None else (entry_price or hypothetical_entry)
        if price is None or risk_distance is None or initial_sl_distance is None:
            raise OpportunityValidationError(
                "valid build requires entry, risk_distance and initial_sl_distance", reason="INVALID_BUILD"
            )
        if risk_distance <= 0 or initial_sl_distance <= 0:
            raise OpportunityValidationError("valid build distances must be positive", reason="INVALID_BUILD")
        if explicit_sl is None:
            explicit_sl = price - initial_sl_distance if side == "LONG" else price + initial_sl_distance
    source_timezone = _text(raw_payload, "source_timezone") or None
    return OpportunityObservation(
        schema_version=PHASE3_OPPORTUNITY_SCHEMA,
        source_observation_id=observation_id,
        event_timestamp_utc=event_timestamp,
        emitted_at_utc=emitted_at,
        source_strategy=source_strategy,
        source_strategy_version=source_version,
        symbol=symbol,
        timeframe=timeframe,
        side=side,
        source_audit_family=audit_family,
        source_event_type=event_type,
        bar_state=bar_state,
        context_features=features,
        execution_context=dict(execution_context),
        entry_price=entry_price,
        hypothetical_entry_price=hypothetical_entry,
        risk_distance=risk_distance,
        initial_sl_distance=initial_sl_distance,
        hypothetical_initial_sl=explicit_sl,
        build_valid=build_value,
        build_reason=build_reason,
        source=str(source or _text(raw_payload, "source") or "opportunity"),
        received_at_utc=received_value,
        source_timezone=source_timezone,
        candidate_type=_text(raw_payload, "candidate_type") or event_type,
        raw_payload=raw_payload,
        available_at_utc=available,
    )


def _normalized_event(observation: OpportunityObservation) -> NormalizedEvent:
    """Đưa raw observation về shape mà builder Phase 1 đã dùng."""

    raw_type = observation.source_event_type.upper()
    if observation.source_audit_family == "V81":
        event_type = "FLAT_SIGNAL" if raw_type.startswith("FLAT_") else "BLOCKED_SIGNAL" if raw_type.startswith("OPEN_") else "SIGNAL"
    else:
        if raw_type in {"BLOCKED_OPPOSITE", "BLOCKED_SAME_SIDE"}:
            event_type = "BLOCKED_SIGNAL"
        elif raw_type in {"LONG_ONLY", "SHORT_ONLY"}:
            event_type = "CONTROL_SIGNAL"
        elif raw_type == "SIMULTANEOUS_CONFLICT":
            event_type = "SIGNAL"
        else:
            event_type = "SIGNAL"
    price = observation.price
    fields: dict[str, Any] = {
        **dict(observation.context_features),
        **dict(observation.execution_context),
        "raw_event_type": raw_type,
        "risk_distance": observation.risk_distance,
        "shadow_risk_distance": observation.risk_distance,
        "initial_sl_distance": observation.initial_sl_distance,
        "build_valid": observation.build_valid,
        "build_reason": observation.build_reason,
    }
    if observation.source_audit_family == "V82":
        fields["shadow_initial_sl"] = observation.initial_sl
    else:
        fields["initial_sl"] = observation.initial_sl
    return NormalizedEvent(
        source_key=observation.source,
        event_type=event_type,
        event_time_utc=observation.event_timestamp_utc,
        source_time=observation.event_timestamp_utc,
        source_timezone=observation.source_timezone or "UTC",
        symbol=observation.symbol,
        timeframe=observation.timeframe,
        strategy_version=observation.source_strategy_version,
        audit_version=observation.source_audit_family,
        side=observation.side,
        raw_event_id=observation.source_observation_id,
        price=price,
        volume=None,
        fields=fields,
        raw_fields={str(key): str(value) for key, value in observation.raw_payload.items()},
    )


def canonicalize_observation(observation: OpportunityObservation) -> CanonicalOpportunity:
    """Tạo canonical ID duy nhất bằng implementation Phase 1 hiện hữu."""

    normalized = _normalized_event(observation)
    return CanonicalOpportunity(
        observation=observation,
        normalized_event=normalized,
        canonical_opportunity_id=canonical_opportunity_id(normalized),
    )


__all__ = [
    "CANONICALIZER_FINGERPRINT",
    "CanonicalOpportunity",
    "OpportunityObservation",
    "OpportunityValidationError",
    "canonicalize_observation",
    "validate_opportunity_payload",
]
