"""Parser raw V81 Standard Deviation shadow telemetry."""

from __future__ import annotations

from pathlib import Path

from ..models import NormalizedEvent
from ..normalization.identifiers import normalize_side, normalize_symbol, normalize_timeframe
from ..normalization.timestamps import normalize_timestamp
from .common import as_text, normalize_fields, read_csv


REQUIRED_FIELDS = {
    "event_id", "setup_id", "time", "side", "entry_price", "initial_sl", "risk_distance",
    "conflict_type", "entry_rsi", "entry_atr_pct", "entry_return_std_20", "entry_return_std_rank",
    "entry_price_std_20", "entry_price_std_100", "entry_price_std_pct_20", "entry_std_ratio_20_100",
    "entry_price_z20", "entry_price_abs_z20", "entry_rsi_std_20", "entry_rsi_std_rank",
    "entry_atr_return_std_ratio", "entry_atr_return_std_rank", "first_hit", "mfe_r", "mae_r",
    "return_6", "return_12", "return_24", "return_48", "completed",
}


def supports(path: Path, fieldnames: list[str] | None = None) -> bool:
    return path.name.lower() == "shadow-signals.csv" and (not fieldnames or "entry_return_std_20" in fieldnames)


def parse(path: Path, *, source_key: str, source_timezone: str) -> list[NormalizedEvent]:
    rows, fieldnames = read_csv(path)
    missing = sorted(REQUIRED_FIELDS - set(fieldnames))
    if missing:
        raise ValueError(f"V81 thiếu field: {', '.join(missing)}")
    events: list[NormalizedEvent] = []
    for row_number, row in enumerate(rows, start=2):
        fields = normalize_fields(row)
        raw_event_id = as_text(fields, "event_id")
        if not raw_event_id:
            raise ValueError(f"V81 dòng {row_number}: event_id rỗng")
        source_time = as_text(fields, "time")
        if not source_time:
            raise ValueError(f"V81 dòng {row_number}: time rỗng")
        timestamp_utc = normalize_timestamp(source_time, source_timezone)
        conflict = (as_text(fields, "conflict_type", "UNKNOWN") or "UNKNOWN").upper()
        if conflict.startswith("FLAT_"):
            event_type = "FLAT_SIGNAL"
        elif conflict.startswith("OPEN_"):
            event_type = "BLOCKED_SIGNAL"
        else:
            event_type = "SIGNAL"
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
                audit_version="V81",
                side=normalize_side(as_text(fields, "side")),
                raw_event_id=raw_event_id,
                price=fields.get("entry_price"),
                volume=None,
                fields={**fields, "raw_event_type": conflict},
                raw_fields=row,
            )
        )
    return events
