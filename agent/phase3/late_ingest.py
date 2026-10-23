"""Nạp lại observation bị loại vì lỗi định dạng thời gian hoặc lệch đồng hồ, gắn nhãn LATE_NOT_FORWARD.

Các bản ghi này đến sau khi collector đã bỏ qua chúng, nên dự đoán (nếu có) sẽ được ghi sau diễn biến giá.
Vì vậy chúng không bao giờ vào forward: không tạo prediction, không vào campaign, không tính vào
forward_sample_count. Bảng chỉ phục vụ kiểm tra pipeline và bằng chứng.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .ingestion.opportunity import canonicalize_observation, validate_opportunity_payload
from .models import format_utc_timestamp, parse_utc_timestamp, sha256_json, utc_now
from .runtime import _json, _safe_raw_hash

REJECTION_REASON_PREFIX = "invalid UTC timestamp:"
FUTURE_SKEW_REASON = "EVENT_TIMESTAMP_IN_FUTURE"
OFFSET_MISSED_REASON = "COLLECTOR_OFFSET_MISSED"


def late_ingest_rejected_observations(
    connection: sqlite3.Connection,
    *,
    ingested_at_utc: str | None = None,
) -> dict[str, Any]:
    """Idempotent: chạy lại không tạo bản ghi trùng."""

    ingested_at = format_utc_timestamp(ingested_at_utc or utc_now())
    rows = connection.execute(
        """
        SELECT forward_event_id, run_id, received_at_utc, raw_payload, raw_payload_sha256
        FROM phase3_forward_events
        WHERE (validation_status = 'REJECTED_SCHEMA' AND failure_reason LIKE ?)
           OR (validation_status = 'REJECTED_STALE' AND failure_reason IN (?, ?))
        ORDER BY received_at_utc, forward_event_id
        """,
        (REJECTION_REASON_PREFIX + "%", FUTURE_SKEW_REASON, OFFSET_MISSED_REASON),
    ).fetchall()
    stored = already = still_invalid = 0
    for row in rows:
        exists = connection.execute(
            "SELECT 1 FROM phase3_late_ingested_observations WHERE source_forward_event_id = ?",
            (row["forward_event_id"],),
        ).fetchone()
        if exists:
            already += 1
            continue
        try:
            payload = json.loads(row["raw_payload"])
            observation = validate_opportunity_payload(
                payload,
                source="late-ingest",
                received_at_utc=row["received_at_utc"],
            )
        except (TypeError, ValueError):
            still_invalid += 1
            continue
        try:
            canonical_id = canonicalize_observation(observation).canonical_opportunity_id
        except (TypeError, ValueError, KeyError):
            canonical_id = None
        with connection:
            connection.execute(
                """
                INSERT INTO phase3_late_ingested_observations(
                    source_forward_event_id, run_id, source_observation_id, event_timestamp_utc,
                    original_received_at_utc, late_ingested_at_utc, symbol, timeframe, side,
                    source_audit_family, source_event_type, bar_state, build_valid,
                    canonical_opportunity_id, raw_payload_sha256, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["forward_event_id"], row["run_id"], observation.source_observation_id,
                    observation.event_timestamp_utc, row["received_at_utc"], ingested_at,
                    observation.symbol, observation.timeframe, observation.side,
                    observation.source_audit_family, observation.source_event_type,
                    observation.bar_state, 1 if observation.build_valid else 0, canonical_id,
                    row["raw_payload_sha256"], row["raw_payload"],
                ),
            )
        stored += 1
    return {
        "status": "LATE_INGEST_DONE",
        "ingest_class": "LATE_NOT_FORWARD",
        "candidates": len(rows),
        "stored": stored,
        "already_present": already,
        "still_invalid": still_invalid,
        "counts_toward_forward": False,
    }


def record_missed_file_region(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    file_path: str | Path,
    start_offset: int,
    end_offset: int | None = None,
    recorded_at_utc: str | None = None,
) -> dict[str, Any]:
    """Ghi các dòng nằm phía trước offset của collector thành event REJECTED_STALE.

    Xảy ra khi EA live ghi đè lên vùng file mà collector đã đọc qua (ví dụ tester ghi thêm vào cuối file).
    Chỉ nhận dòng hoàn chỉnh, hợp lệ, có thời điểm sau lúc run bắt đầu forward và chưa có trong DB.
    Sau đó late_ingest_rejected_observations() chuyển chúng sang bảng LATE_NOT_FORWARD.
    """

    recorded_at = format_utc_timestamp(recorded_at_utc or utc_now())
    run = connection.execute(
        "SELECT forward_start_utc FROM phase3_forward_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if run is None:
        raise ValueError(f"unknown run_id: {run_id}")
    forward_start = parse_utc_timestamp(str(run["forward_start_utc"]))
    data = Path(file_path).read_bytes()
    stop = len(data) if end_offset is None else min(int(end_offset), len(data))
    region = data[int(start_offset):stop]
    candidates = skipped_before_start = invalid = duplicate = recorded = 0
    for raw_line in region.split(b"\n"):
        text = raw_line.decode("utf-8", "replace").strip()
        if not text:
            continue
        candidates += 1
        try:
            payload = json.loads(text)
            observation = validate_opportunity_payload(
                payload, source="offset-recovery", received_at_utc=recorded_at
            )
        except (TypeError, ValueError):
            invalid += 1
            continue
        if parse_utc_timestamp(observation.event_timestamp_utc) < forward_start:
            skipped_before_start += 1
            continue
        digest = _safe_raw_hash(payload)
        event_id = "p3-event-rejected-" + sha256_json(
            {
                "run_id": run_id,
                "source": "offset-recovery",
                "source_event_id": observation.source_observation_id,
                "raw": digest,
            }
        )
        known = connection.execute(
            "SELECT 1 FROM phase3_opportunity_observations WHERE run_id = ? AND source_observation_id = ?",
            (run_id, observation.source_observation_id),
        ).fetchone()
        if known or connection.execute(
            "SELECT 1 FROM phase3_forward_events WHERE forward_event_id = ?", (event_id,)
        ).fetchone():
            duplicate += 1
            continue
        with connection:
            connection.execute(
                """
                INSERT INTO phase3_forward_events(
                    forward_event_id, run_id, forward_opportunity_id, source_event_id,
                    event_timestamp_utc, received_at_utc, symbol, timeframe, side,
                    candidate_type, bar_state, source_timezone, raw_payload_sha256,
                    raw_payload, schema_version, validation_status, lifecycle_status,
                    failure_reason, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, run_id, "p3-opportunity-rejected-" + digest, observation.source_observation_id,
                    observation.event_timestamp_utc, recorded_at, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN",
                    "event_instant", None, digest, _json(payload), "UNKNOWN", "REJECTED_STALE", "REJECTED_STALE",
                    OFFSET_MISSED_REASON, recorded_at,
                ),
            )
        recorded += 1
    return {
        "status": "MISSED_REGION_RECORDED",
        "candidates": candidates,
        "recorded": recorded,
        "skipped_before_forward_start": skipped_before_start,
        "invalid_or_partial": invalid,
        "already_known": duplicate,
    }
