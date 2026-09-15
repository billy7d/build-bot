"""Resolver outcome trễ, bảo đảm prediction có trước observed outcome."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from ..models import OutcomeResolution, format_utc_timestamp, parse_utc_timestamp, sha256_json, utc_now
from .labels import _number, directional_return, first_hit_label


def _context_value(context: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in context:
            return context[name]
        features = context.get("features")
        if isinstance(features, Mapping) and name in features:
            return features[name]
    return None


def _outcome_from_precomputed(
    side: str,
    bars: list[Mapping[str, Any]],
    *,
    entry_price: float,
    risk_distance: float,
) -> dict[str, Any]:
    """Dùng precomputed horizon chỉ khi exporter đã ghi ở bar tương lai."""

    latest = bars[-1] if bars else {}
    values: dict[str, float | None] = {}
    for horizon in (6, 12, 24, 48):
        key = f"return_{horizon}bar_r"
        value = _number(latest.get(key))
        if value is None:
            value = directional_return(side, latest.get("close"), entry_price, risk_distance) if len(bars) >= horizon else None
        values[key] = value
    return values


def resolve_prediction_outcome(
    prediction: Mapping[str, Any],
    bars: Iterable[Mapping[str, Any]],
    *,
    context: Mapping[str, Any] | None = None,
    observed_at_utc: str | None = None,
    resolved_at_utc: str | None = None,
) -> OutcomeResolution:
    """Resolve chỉ từ bars có timestamp sau event và sau prediction commit."""

    context = dict(context or {})
    event_time = parse_utc_timestamp(str(prediction.get("source_event_timestamp_utc")))
    committed_time = parse_utc_timestamp(str(prediction.get("prediction_committed_at_utc")))
    observation_cutoff = parse_utc_timestamp(observed_at_utc) if observed_at_utc else None
    if observation_cutoff is not None and observation_cutoff <= committed_time:
        # Observed-time metadata tự nó đã chứng minh outcome không đứng sau
        # prediction; không biến trường hợp này thành incomplete/loss.
        return OutcomeResolution(
            "INVALID", None, None, None, None, None, None, None,
            None, format_utc_timestamp(observation_cutoff), "PREDICTION_AFTER_OUTCOME",
        )
    event_bars: list[Mapping[str, Any]] = []
    future_bars: list[Mapping[str, Any]] = []
    for bar in bars:
        timestamp = parse_utc_timestamp(str(bar.get("timestamp_utc", bar.get("timestamp", ""))))
        if timestamp <= event_time:
            continue
        normalized = {**bar, "timestamp_utc": format_utc_timestamp(timestamp)}
        if observation_cutoff is not None and timestamp > observation_cutoff:
            continue
        event_bars.append(normalized)
        if timestamp > committed_time:
            future_bars.append(normalized)
    event_bars.sort(key=lambda item: (parse_utc_timestamp(item["timestamp_utc"]), str(item.get("bar_id", ""))))
    future_bars.sort(key=lambda item: (parse_utc_timestamp(item["timestamp_utc"]), str(item.get("bar_id", ""))))
    if not future_bars:
        if event_bars and committed_time >= parse_utc_timestamp(event_bars[-1]["timestamp_utc"]):
            return OutcomeResolution(
                "INVALID", None, None, None, None, None, None, None,
                None, event_bars[-1]["timestamp_utc"], "PREDICTION_AFTER_OUTCOME",
            )
        return OutcomeResolution(
            "INCOMPLETE", None, None, None, None, None, None, None,
            None, None, "NO_FUTURE_BARS",
        )

    side = str(prediction.get("side") or context.get("side") or "").upper()
    entry_price = _number(_context_value(context, "entry_price", "active_entry_price", "price"))
    risk_distance = _number(_context_value(context, "risk_distance", "initial_risk_distance", "initial_sl_distance"))
    if entry_price is None:
        entry_price = _number(prediction.get("entry_price"))
    if risk_distance is None:
        risk_distance = _number(prediction.get("risk_distance"))
    if side not in {"LONG", "SHORT"} or entry_price is None or risk_distance is None or risk_distance <= 0:
        return OutcomeResolution(
            "INCOMPLETE", None, None, None, None, None, None, None,
            None, future_bars[-1]["timestamp_utc"], "MISSING_OUTCOME_CONTEXT",
        )

    label, first_hit, reason = first_hit_label(
        side, future_bars, entry_price=entry_price, risk_distance=risk_distance
    )
    precomputed = _outcome_from_precomputed(side, future_bars, entry_price=entry_price, risk_distance=risk_distance)
    returns: dict[int, float | None] = {}
    for horizon in (6, 12, 24, 48):
        key = f"return_{horizon}bar_r"
        value = precomputed[key]
        if value is None and len(future_bars) >= horizon:
            value = directional_return(side, future_bars[horizon - 1].get("close"), entry_price, risk_distance)
        returns[horizon] = value
    directional_values: list[float] = []
    for bar in future_bars:
        high = _number(bar.get("high"))
        low = _number(bar.get("low"))
        high_r = directional_return(side, high, entry_price, risk_distance)
        low_r = directional_return(side, low, entry_price, risk_distance)
        if high_r is not None:
            directional_values.append(high_r)
        if low_r is not None:
            directional_values.append(low_r)
    mfe = max(directional_values) if directional_values else None
    mae = min(directional_values) if directional_values else None
    observed = future_bars[-1]["timestamp_utc"]
    invalid_time = committed_time >= parse_utc_timestamp(observed)
    if invalid_time:
        return OutcomeResolution(
            "INVALID", None, returns[6], returns[12], returns[24], returns[48], mfe, mae,
            None, observed, "PREDICTION_AFTER_OUTCOME",
        )
    if label is None:
        status = "INCOMPLETE"
        incomplete_reason = reason or "NO_FIRST_HIT"
    elif returns[24] is None:
        status = "INCOMPLETE"
        incomplete_reason = "MISSING_24BAR_OUTCOME"
    else:
        status = "RESOLVED"
        incomplete_reason = None
    resolved = format_utc_timestamp(resolved_at_utc or utc_now()) if status == "RESOLVED" else None
    return OutcomeResolution(
        status, label, returns[6], returns[12], returns[24], returns[48], mfe, mae,
        resolved, observed, incomplete_reason,
    )


class OutcomeResolver:
    """Đọc prediction/event, insert đúng một outcome record append-only."""

    def __init__(self, connection: Any, *, clock: Any = utc_now):
        self.connection = connection
        self.clock = clock

    def resolve_prediction(
        self,
        forward_event_id: str,
        bars: Iterable[Mapping[str, Any]],
        *,
        observed_at_utc: str | None = None,
    ) -> OutcomeResolution:
        event = self.connection.execute(
            "SELECT * FROM phase3_forward_events WHERE forward_event_id = ?", (forward_event_id,)
        ).fetchone()
        prediction = self.connection.execute(
            "SELECT * FROM phase3_predictions WHERE forward_event_id = ?", (forward_event_id,)
        ).fetchone()
        if event is None or prediction is None:
            raise ValueError(f"prediction/event not found: {forward_event_id}")
        context = json.loads(str(event["raw_payload"])).get("context", {})
        prediction_dict = dict(prediction)
        prediction_dict["side"] = event["side"]
        resolution = resolve_prediction_outcome(
            prediction_dict,
            bars,
            context=context,
            observed_at_utc=observed_at_utc,
            resolved_at_utc=self.clock(),
        )
        outcome_payload = resolution.to_dict()
        outcome_hash = sha256_json(outcome_payload)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO phase3_outcomes(
                    forward_event_id, classification_label, return_6bar_r,
                    return_12bar_r, return_24bar_r, return_48bar_r, mfe_r, mae_r,
                    resolved_at_utc, outcome_observed_at_utc, status,
                    incomplete_reason, outcome_schema_version, outcome_hash, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    forward_event_id, resolution.classification_label, resolution.return_6bar_r,
                    resolution.return_12bar_r, resolution.return_24bar_r, resolution.return_48bar_r,
                    resolution.mfe_r, resolution.mae_r, resolution.resolved_at_utc,
                    resolution.outcome_observed_at_utc, resolution.status,
                    resolution.incomplete_reason, resolution.outcome_schema_version,
                    outcome_hash, self.clock(),
                ),
            )
            self.connection.execute(
                "UPDATE phase3_forward_events SET lifecycle_status = ? WHERE forward_event_id = ?",
                ("OUTCOME_RESOLVED" if resolution.status == "RESOLVED" else "OUTCOME_PENDING", forward_event_id),
            )
        return resolution

    def resolve_pending(
        self,
        run_id: str,
        bars_by_event: Mapping[str, Iterable[Mapping[str, Any]]],
        *,
        observed_at_utc: str | None = None,
    ) -> dict[str, OutcomeResolution]:
        rows = self.connection.execute(
            """
            SELECT p.forward_event_id FROM phase3_predictions p
            JOIN phase3_forward_events e ON e.forward_event_id = p.forward_event_id
            WHERE p.forward_run_id = ? AND NOT EXISTS (
                SELECT 1 FROM phase3_outcomes o WHERE o.forward_event_id = p.forward_event_id
            )
            ORDER BY e.event_timestamp_utc, p.forward_event_id
            """,
            (run_id,),
        ).fetchall()
        result: dict[str, OutcomeResolution] = {}
        for row in rows:
            event_id = str(row[0])
            if event_id in bars_by_event:
                result[event_id] = self.resolve_prediction(event_id, bars_by_event[event_id], observed_at_utc=observed_at_utc)
        return result


__all__ = ["OutcomeResolver", "resolve_prediction_outcome"]
