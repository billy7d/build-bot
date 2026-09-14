"""Parser raw V82 blocked-signal/opportunity-cost telemetry."""

from __future__ import annotations

from pathlib import Path

from ..models import NormalizedEvent
from ..normalization.identifiers import normalize_side, normalize_symbol, normalize_timeframe
from ..normalization.timestamps import normalize_timestamp
from .common import as_text, normalize_fields, read_csv


REQUIRED_FIELDS = {
    "event_id", "event_time", "entry_bar_time", "fold", "side", "event_type", "active_side",
    "shadow_side", "actual_selected_side", "blocked_side", "direction", "setup_generation",
    "active_group_id", "active_base_position_identifier", "shadow_build_valid", "shadow_entry_price",
    "shadow_initial_sl", "shadow_risk_distance", "completed", "incomplete_reason",
}


def supports(path: Path, fieldnames: list[str] | None = None) -> bool:
    return "v82" in path.as_posix().lower() and path.suffix.lower() == ".csv" and (
        not fieldnames or {"event_id", "event_type", "shadow_return_48bar_r"}.issubset(fieldnames)
    )


def _epoch_hint(event_id: str) -> int:
    prefix = event_id.split("_", 1)[0]
    if not prefix.isdigit():
        raise ValueError(f"V82 event_id thiếu epoch prefix: {event_id!r}")
    return int(prefix)


def parse(path: Path, *, source_key: str, source_timezone: str) -> list[NormalizedEvent]:
    rows, fieldnames = read_csv(path)
    missing = sorted(REQUIRED_FIELDS - set(fieldnames))
    if missing:
        raise ValueError(f"V82 thiếu field: {', '.join(missing)}")
    events: list[NormalizedEvent] = []
    for row_number, row in enumerate(rows, start=2):
        fields = normalize_fields(row)
        raw_event_id = as_text(fields, "event_id")
        source_time = as_text(fields, "event_time")
        if not raw_event_id or not source_time:
            raise ValueError(f"V82 dòng {row_number}: event_id/event_time rỗng")
        timestamp_utc = normalize_timestamp(
            source_time, source_timezone, epoch_hint=_epoch_hint(raw_event_id)
        )
        raw_type = (as_text(fields, "event_type", "UNKNOWN") or "UNKNOWN").upper()
        if raw_type in {"BLOCKED_OPPOSITE", "BLOCKED_SAME_SIDE"}:
            event_type = "BLOCKED_SIGNAL"
        elif raw_type in {"LONG_ONLY", "SHORT_ONLY"}:
            event_type = "CONTROL_SIGNAL"
        elif raw_type == "SIMULTANEOUS_CONFLICT":
            event_type = "SIGNAL"
        else:
            raise ValueError(f"V82 dòng {row_number}: event_type không hỗ trợ {raw_type!r}")
        events.append(
            NormalizedEvent(
                source_key=source_key,
                event_type=event_type,
                event_time_utc=timestamp_utc,
                source_time=source_time,
                source_timezone=source_timezone,
                symbol=normalize_symbol("BTCUSD"),
                timeframe=normalize_timeframe("H1"),
                strategy_version="V26",
                audit_version="V82",
                side=normalize_side(as_text(fields, "side")),
                raw_event_id=raw_event_id,
                price=fields.get("shadow_entry_price"),
                volume=None,
                fields={**fields, "raw_event_type": raw_type},
                raw_fields=row,
            )
        )
    return events
