"""Phân loại artifact và registry version cho các nguồn Phase 1."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


ARTIFACT_TYPES = {
    "BACKTEST_SUMMARY",
    "TRADE_HISTORY",
    "TELEMETRY",
    "STDDEV_SHADOW_TELEMETRY",
    "BLOCKED_SIGNAL_SHADOW_TELEMETRY",
    "PRESET",
    "AUDIT_PRESET",
    "MT5_REPORT",
    "JOURNAL",
    "FORWARD_REPORT",
    "EXPERIMENT_REPORT",
    "OPPORTUNITY_AUDIT_REPORT",
    "UNKNOWN",
}

PARSER_VERSIONS = {
    "v81_stddev": ("v81_stddev", "v81-parser/1"),
    "v82_blocked_signal": ("v82_blocked_signal", "v82-parser/1"),
    "preset": ("preset", "preset-parser/1"),
    "metadata": ("metadata", "metadata-parser/1"),
}


@dataclass(frozen=True)
class SourceDescriptor:
    artifact_type: str
    parser_name: str | None
    parser_version: str | None
    strategy_version: str | None
    audit_version: str | None
    preset_id: str | None
    source_timezone: str | None
    timezone_confidence: str
    timezone_evidence: str
    importable: bool
    metadata_only: bool = False


def _name(path: str | Path) -> str:
    return Path(path).as_posix().lower()


def _execution_strategy_from_path(value: str) -> str | None:
    """Chỉ gán strategy khi tên artifact nêu rõ V26 hoặc V63."""

    match = re.search(r"(?:^|[/_.-])v(26|63)(?:$|[/_.-])", value, re.IGNORECASE)
    return f"V{match.group(1)}" if match else None


def descriptor_for(path: str | Path) -> SourceDescriptor:
    """Trả mapping explicit; không suy đoán V81/V82 thành strategy."""

    value = _name(path)
    base = Path(value).name
    strategy = _execution_strategy_from_path(value)

    if base == "shadow-signals.csv" and "v81-runs/" in value:
        return SourceDescriptor(
            "STDDEV_SHADOW_TELEMETRY", "v81_stddev", "v81-parser/1", "V26", "V81",
            "81_v26_stddev_shadow_audit", "UTC", "INFERRED",
            "Cùng exporter MT5 với V82; V82 epoch cross-check xác nhận biểu diễn UTC",
            True,
        )
    if "blocked_signals.csv" in base or "v82_runs/" in value:
        return SourceDescriptor(
            "BLOCKED_SIGNAL_SHADOW_TELEMETRY", "v82_blocked_signal", "v82-parser/1", "V26", "V82",
            "82_v26_blocked_signal_shadow_audit", "UTC", "VERIFIED_BY_EPOCH",
            "Prefix epoch trong event_id khớp tuyệt đối event_time raw theo UTC",
            True,
        )
    if base.endswith(".set"):
        audit = None
        if "stddev" in base or "81_" in base:
            audit = "V81"
        if "blocked_signal" in base and "control_off" not in base:
            audit = "V82"
        return SourceDescriptor(
            "AUDIT_PRESET" if audit else "PRESET", "preset", "preset-parser/1", strategy, audit,
            Path(base).stem, None, "NOT_APPLICABLE", "Preset không chứa timestamp event", False,
            metadata_only=True,
        )
    if base.endswith((".html", ".htm")):
        report_strategy = "V26" if "v81" in value or "v82" in value else strategy
        return SourceDescriptor(
            "MT5_REPORT", "metadata", "metadata-parser/1", report_strategy, "V82" if "v82" in value else ("V81" if "v81" in value else None),
            None, "UTC", "INFERRED", "Report metadata lấy từ tester config/source run", False,
            metadata_only=True,
        )
    if "v82" in base and base.endswith((".json", ".md")):
        return SourceDescriptor(
            "OPPORTUNITY_AUDIT_REPORT", "metadata", "metadata-parser/1", "V26", "V82", None,
            "UTC", "INFERRED", "Aggregate report; không phải episode-level source", False, True,
        )
    if "v81" in base and base.endswith((".json", ".md")):
        return SourceDescriptor(
            "EXPERIMENT_REPORT", "metadata", "metadata-parser/1", "V26", "V81", None,
            "UTC", "INFERRED", "Aggregate report; không phải episode-level source", False, True,
        )
    if "journal" in base:
        return SourceDescriptor(
            "JOURNAL", "metadata", "metadata-parser/1", strategy, None, None,
            None, "UNKNOWN", "Journal chưa có timezone metadata chuẩn", False, True,
        )
    if "forward" in base:
        return SourceDescriptor(
            "FORWARD_REPORT", "metadata", "metadata-parser/1", strategy, None, None,
            None, "UNKNOWN", "Forward artifact chỉ dùng provenance/lock metadata", False, True,
        )
    if base.endswith(".csv"):
        return SourceDescriptor(
            "TRADE_HISTORY" if "trade" in base else "TELEMETRY", "metadata", "metadata-parser/1", strategy, None, None,
            None, "UNKNOWN", "CSV không có schema đủ chắc chắn cho importer hiện tại", False, True,
        )
    if base.endswith((".json", ".md", ".txt", ".log", ".ini")):
        return SourceDescriptor(
            "EXPERIMENT_REPORT" if "summary" in base or "report" in base else "UNKNOWN",
            "metadata", "metadata-parser/1", strategy, None, None, None, "UNKNOWN",
            "Metadata không phải episode source", False, True,
        )
    return SourceDescriptor(
        "UNKNOWN", None, None, None, None, None, None, "UNKNOWN",
        "Không có contract artifact tương ứng", False, False,
    )


def relative_key(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def source_timezone_policy(descriptor: SourceDescriptor) -> dict[str, str | None]:
    return {
        "source_timezone": descriptor.source_timezone,
        "timezone_confidence": descriptor.timezone_confidence,
        "timezone_evidence": descriptor.timezone_evidence,
    }
