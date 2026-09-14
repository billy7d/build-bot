"""Chuẩn hóa timestamp và bảo vệ chống giả định timezone ngầm."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TIME_FORMATS = (
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


class TimestampNormalizationError(ValueError):
    """Timestamp thiếu dữ kiện hoặc không thể chuyển đổi an toàn."""


def parse_source_datetime(value: object) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise TimestampNormalizationError("timestamp rỗng")
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise TimestampNormalizationError(f"timestamp không hợp lệ: {raw!r}")


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_timestamp(
    value: object,
    source_timezone: str | None,
    *,
    epoch_hint: int | None = None,
) -> str:
    """Trả ISO-8601 UTC; chỉ dùng epoch hint khi raw text khớp tuyệt đối.

    Không được tự coi một timestamp không có timezone là UTC.  Với V82, epoch
    nằm trong event_id là bằng chứng độc lập để kiểm tra raw timestamp.
    """

    naive = parse_source_datetime(value)
    if epoch_hint is not None:
        try:
            expected = datetime.fromtimestamp(epoch_hint, UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise TimestampNormalizationError("epoch hint không hợp lệ") from exc
        if naive != expected.replace(tzinfo=None):
            raise TimestampNormalizationError(
                "timestamp raw không khớp epoch hint; từ chối giả định timezone"
            )
        return _format_utc(expected)

    timezone_name = str(source_timezone or "").strip()
    if not timezone_name or timezone_name.upper() in {"UNKNOWN", "UNSPECIFIED"}:
        raise TimestampNormalizationError(
            "timestamp không có source_timezone rõ ràng"
        )
    if timezone_name.upper() in {"UTC", "GMT", "Z"}:
        zone = timezone.utc
    else:
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise TimestampNormalizationError(
                f"source_timezone không được hệ thống biết: {timezone_name!r}"
            ) from exc
    return _format_utc(naive.replace(tzinfo=zone))


def timestamp_to_datetime(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise TimestampNormalizationError("timestamp nội bộ phải có timezone")
    return parsed.astimezone(UTC)


def add_bars(timestamp_utc: str, bars: int, timeframe_hours: int = 1) -> str:
    """Tính mốc outcome từ bar count đã được source ghi nhận."""

    return _format_utc(
        timestamp_to_datetime(timestamp_utc)
        + timedelta(hours=bars * timeframe_hours)
    )
