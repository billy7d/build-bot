"""Tạo identity canonical audit-neutral cho cùng một trading opportunity."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from ..models import NormalizedEvent


CANONICAL_LINKAGE_VERSION = "canonical-opportunity/1"

_SEMANTIC_ALIASES = {
    "FLAT_LONG_ONLY": "LONG_ONLY",
    "FLAT_SHORT_ONLY": "SHORT_ONLY",
    "OPEN_OPPOSITE_SIDE": "BLOCKED_OPPOSITE",
    "OPEN_SAME_SIDE": "BLOCKED_SAME_SIDE",
    "LONG_ONLY": "LONG_ONLY",
    "SHORT_ONLY": "SHORT_ONLY",
    "BLOCKED_OPPOSITE": "BLOCKED_OPPOSITE",
    "BLOCKED_SAME_SIDE": "BLOCKED_SAME_SIDE",
}


def _canonical_number(value: object) -> str:
    """Chuẩn hóa số để 16516.65 và 16516.650000 có cùng identity."""

    if value is None or str(value).strip() == "":
        return "NULL"
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"giá trị canonical không phải số: {value!r}") from exc
    if not number.is_finite():
        raise ValueError(f"giá trị canonical không hữu hạn: {value!r}")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _text(value: object) -> str:
    return str(value or "").strip().upper() or "NULL"


def candidate_semantic(fields: Mapping[str, Any], event_type: str | None = None) -> str:
    """Map raw event labels về semantic chung mà không đưa audit vào key."""

    raw = fields.get("raw_event_type")
    if raw is None:
        raw = fields.get("conflict_type") or fields.get("event_type") or event_type
    normalized = _text(raw)
    return _SEMANTIC_ALIASES.get(normalized, normalized)


def _first_present(fields: Mapping[str, Any], *names: str) -> object:
    for name in names:
        if name in fields and fields[name] not in (None, ""):
            return fields[name]
    return None


def _identity_key(
    *,
    strategy_version: object,
    symbol: object,
    timeframe: object,
    side: object,
    semantic: object,
    entry: object,
    stop: object,
    risk_distance: object,
) -> str:
    """Trả chuỗi identity ổn định; audit/source/parser không nằm trong chuỗi."""

    components = (
        ("linkage_version", CANONICAL_LINKAGE_VERSION),
        ("strategy", _text(strategy_version)),
        ("symbol", _text(symbol)),
        ("timeframe", _text(timeframe)),
        ("side", _text(side)),
        ("candidate_semantic", _text(semantic)),
        ("entry", _canonical_number(entry)),
        ("stop", _canonical_number(stop)),
        ("risk_distance", _canonical_number(risk_distance)),
    )
    return "|".join(f"{name}={value}" for name, value in components)


def canonical_identity_key(event: NormalizedEvent) -> str:
    """Tạo identity từ event normalized, không dùng raw event id hay source path."""

    fields = event.fields
    return _identity_key(
        strategy_version=event.strategy_version,
        symbol=event.symbol,
        timeframe=event.timeframe,
        side=event.side,
        semantic=candidate_semantic(fields, event.event_type),
        entry=event.price,
        stop=_first_present(fields, "initial_sl", "shadow_initial_sl"),
        risk_distance=_first_present(fields, "risk_distance", "shadow_risk_distance"),
    )


def canonical_opportunity_id(event: NormalizedEvent) -> str:
    """Hash identity canonical thành id ngắn gọn, deterministic và audit-neutral."""

    return "opp-" + hashlib.sha256(canonical_identity_key(event).encode("utf-8")).hexdigest()


def canonical_identity_key_from_record(record: Mapping[str, Any]) -> str:
    """Dựng lại identity từ row SQLite để kiểm tra collision sau khi import."""

    raw_fields: dict[str, Any]
    try:
        loaded = json.loads(str(record.get("raw_fields_json") or "{}"))
        raw_fields = loaded if isinstance(loaded, dict) else {}
    except json.JSONDecodeError:
        raw_fields = {}
    return _identity_key(
        strategy_version=record.get("strategy_version"),
        symbol=record.get("symbol"),
        timeframe=record.get("timeframe"),
        side=record.get("side"),
        semantic=candidate_semantic(raw_fields),
        entry=record.get("entry_candidate"),
        stop=record.get("stop_candidate") or _first_present(raw_fields, "initial_sl", "shadow_initial_sl"),
        risk_distance=_first_present(raw_fields, "risk_distance", "shadow_risk_distance"),
    )


def canonical_id_from_key(identity_key: str) -> str:
    """Hash một identity key đã dựng lại, dùng cho kiểm tra import/export."""

    return "opp-" + hashlib.sha256(identity_key.encode("utf-8")).hexdigest()


def canonical_identity_collision(identity_keys: set[str]) -> bool:
    """Xác định collision thực sự, không coi hai audit của cùng opportunity là lỗi."""

    return len(identity_keys) > 1
