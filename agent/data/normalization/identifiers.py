"""Chuẩn hóa symbol/timeframe và tạo logical episode ID deterministic."""

from __future__ import annotations

import re

from .timestamps import timestamp_to_datetime


TIMEFRAME_ALIASES = {
    "1": "M1",
    "M1": "M1",
    "5": "M5",
    "M5": "M5",
    "15": "M15",
    "M15": "M15",
    "30": "M30",
    "M30": "M30",
    "16385": "H1",
    "60": "H1",
    "H1": "H1",
    "16388": "H4",
    "240": "H4",
    "H4": "H4",
    "D1": "D1",
    "1440": "D1",
}


class IdentifierNormalizationError(ValueError):
    """Identifier không đủ chắc chắn để đưa vào dataset."""


def normalize_symbol(value: object) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        raise IdentifierNormalizationError("symbol rỗng")
    # Giữ BTCUSD, BTCUSDM và BTCUSD.A tách biệt; không tự tạo alias.
    if not re.fullmatch(r"[A-Z0-9._-]+", symbol):
        raise IdentifierNormalizationError(f"symbol không hợp lệ: {symbol!r}")
    return symbol


def normalize_timeframe(value: object) -> str:
    raw = str(value or "").strip().upper()
    if raw not in TIMEFRAME_ALIASES:
        raise IdentifierNormalizationError(f"timeframe không hỗ trợ: {raw!r}")
    return TIMEFRAME_ALIASES[raw]


def normalize_side(value: object, *, allow_none: bool = False) -> str:
    side = str(value or "").strip().upper()
    allowed = {"LONG", "SHORT"} | ({"NONE"} if allow_none else set())
    if side not in allowed:
        raise IdentifierNormalizationError(f"side không hợp lệ: {side!r}")
    return side


def normalize_fold_type(value: object, timestamp_utc: str) -> str:
    raw = str(value or "").strip().upper()
    if raw.startswith("TRAIN"):
        return "TRAIN"
    if raw.startswith("VALIDATION"):
        return "VALIDATION"
    if raw.startswith("OOS"):
        return "OOS"
    if raw.startswith("FORWARD"):
        return "FORWARD"
    if raw.startswith("SMOKE"):
        return "SMOKE"
    year = timestamp_to_datetime(timestamp_utc).year
    if year in {2023, 2024}:
        return "VALIDATION"
    if year >= 2025:
        return "OOS"
    return "UNKNOWN"


def slug(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip().upper())
    return text.strip("-") or "UNKNOWN"


def deterministic_episode_id(
    *,
    symbol: str,
    timeframe: str,
    timestamp_utc: str,
    strategy_version: str | None,
    audit_version: str | None,
    side: str,
    episode_kind: str,
    ordinal: int,
) -> str:
    timestamp = timestamp_to_datetime(timestamp_utc).strftime("%Y%m%dT%H%M%SZ")
    return "-".join(
        (
            slug(symbol),
            slug(timeframe),
            timestamp,
            slug(strategy_version or "NONE"),
            slug(audit_version or "NONE"),
            slug(side),
            slug(episode_kind),
            f"{ordinal:04d}",
        )
    )
