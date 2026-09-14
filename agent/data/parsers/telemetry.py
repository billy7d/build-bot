"""Parser contract chung cho telemetry CSV mở rộng về sau."""

from __future__ import annotations

from pathlib import Path

from ..models import NormalizedEvent
from ..normalization.identifiers import normalize_side, normalize_symbol, normalize_timeframe
from ..normalization.timestamps import normalize_timestamp
from .common import as_text, normalize_fields, read_csv


def supports(path: Path, fieldnames: list[str] | None = None) -> bool:
    fields = set(fieldnames or [])
    return bool({"event_id", "event_time", "event_type"}.issubset(fields))


def parse(
    path: Path,
    *,
    source_key: str,
    source_timezone: str,
    strategy_version: str | None = None,
    audit_version: str | None = None,
) -> list[NormalizedEvent]:
    rows, fieldnames = read_csv(path)
    if not supports(path, fieldnames):
        raise ValueError("telemetry CSV không đủ event_id/event_time/event_type")
    result: list[NormalizedEvent] = []
    for number, row in enumerate(rows, start=2):
        fields = normalize_fields(row)
        event_id = as_text(fields, "event_id")
        source_time = as_text(fields, "event_time")
        if not event_id or not source_time:
            raise ValueError(f"telemetry dòng {number}: thiếu ID/time")
        result.append(
            NormalizedEvent(
                source_key=source_key,
                event_type=as_text(fields, "event_type", "UNKNOWN") or "UNKNOWN",
                event_time_utc=normalize_timestamp(source_time, source_timezone),
                source_time=source_time,
                source_timezone=source_timezone,
                symbol=normalize_symbol(as_text(fields, "symbol", "UNKNOWN") or "UNKNOWN"),
                timeframe=normalize_timeframe(as_text(fields, "timeframe", "H1") or "H1"),
                strategy_version=strategy_version,
                audit_version=audit_version,
                side=normalize_side(as_text(fields, "side")),
                raw_event_id=event_id,
                price=fields.get("price"),
                volume=fields.get("volume"),
                fields=fields,
                raw_fields=row,
            )
        )
    return result
