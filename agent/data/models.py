"""Domain object dùng chung giữa parser và episode builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class NormalizedEvent:
    """Một event đã chuẩn hóa nhưng vẫn giữ nguyên raw fields để truy vết."""

    source_key: str
    event_type: str
    event_time_utc: str
    source_time: str
    source_timezone: str
    symbol: str
    timeframe: str
    strategy_version: str | None
    audit_version: str | None
    side: str
    raw_event_id: str
    price: float | None
    volume: float | None
    fields: Mapping[str, Any] = field(default_factory=dict)
    raw_fields: Mapping[str, str] = field(default_factory=dict)

    @property
    def source_id(self) -> str:
        """Tên tương thích với contract PRD; source_key vẫn là khóa provenance nội bộ."""

        return self.source_key


@dataclass(frozen=True)
class ParsedPreset:
    """Preset đã đọc từ file .set, không làm thay đổi nội dung file gốc."""

    preset_id: str
    name: str
    strategy_version: str | None
    audit_version: str | None
    file_path: str
    sha256: str
    magic_number: int | None
    parameters: Mapping[str, Any]
