"""Kiểm tra contract episode trước khi ghi vào Trading Memory."""

from __future__ import annotations

from typing import Any, Mapping

from ..normalization.timestamps import TimestampNormalizationError, timestamp_to_datetime


EPISODE_KINDS = {
    "EXECUTION_CANDIDATE", "EXECUTED_TRADE", "FLAT_CANDIDATE", "BLOCKED_OPPORTUNITY",
    "CONTROL_OPPORTUNITY", "SIMULTANEOUS_CONFLICT", "PYRAMID_OPPORTUNITY", "UNKNOWN",
}
CANDIDATE_TYPES = {"BASE", "PYRAMID", "FLAT", "BLOCKED", "CONTROL", "UNKNOWN"}


def validate_episode_record(record: Mapping[str, Any]) -> list[str]:
    """Trả danh sách lỗi thay vì tự sửa dữ liệu source."""

    errors: list[str] = []
    for field in (
        "episode_id", "source_artifact_id", "symbol", "timeframe", "timestamp_utc",
        "side", "episode_kind", "candidate_type", "candidate_exists", "was_executed",
        "fold_type",
    ):
        if record.get(field) in (None, ""):
            errors.append(f"episode thiếu {field}")
    if record.get("side") not in {"LONG", "SHORT"}:
        errors.append("episode side không hợp lệ")
    if record.get("episode_kind") not in EPISODE_KINDS:
        errors.append("episode_kind không hợp lệ")
    if record.get("candidate_type") not in CANDIDATE_TYPES:
        errors.append("candidate_type không hợp lệ")
    if record.get("candidate_exists") not in {0, 1}:
        errors.append("candidate_exists phải là 0/1")
    if record.get("was_executed") not in {0, 1}:
        errors.append("was_executed phải là 0/1")
    try:
        timestamp_to_datetime(str(record.get("timestamp_utc", "")))
    except (TimestampNormalizationError, ValueError):
        errors.append("timestamp_utc không phải ISO-8601 UTC")
    return errors


def validate_bundle(bundle: Any) -> list[str]:
    """Kiểm tra các record trong bundle và quan hệ event-time cơ bản."""

    errors = validate_episode_record(bundle.episode)
    episode_id = bundle.episode.get("episode_id")
    candidate_time = bundle.episode.get("timestamp_utc")
    feature_time = bundle.features.get("feature_timestamp_utc")
    if bundle.features.get("episode_id") != episode_id:
        errors.append("feature episode_id không khớp episode")
    try:
        if timestamp_to_datetime(str(feature_time)) > timestamp_to_datetime(str(candidate_time)):
            errors.append("feature timestamp vượt candidate timestamp")
    except (TimestampNormalizationError, ValueError):
        errors.append("feature timestamp không hợp lệ")
    if bundle.outcome.get("episode_id") != episode_id:
        errors.append("outcome episode_id không khớp episode")
    for name in ("opportunity_context", "active_context", "opportunity_outcome"):
        record = getattr(bundle, name)
        if record is not None and record.get("episode_id") != episode_id:
            errors.append(f"{name} episode_id không khớp episode")
    return errors


def assert_valid_bundle(bundle: Any) -> None:
    """Dừng import trước khi insert nếu bundle vi phạm contract cơ bản."""

    errors = validate_bundle(bundle)
    if errors:
        raise ValueError("; ".join(errors))
