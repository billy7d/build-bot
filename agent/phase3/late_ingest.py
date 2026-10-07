"""Nạp lại observation bị loại vì lỗi định dạng thời gian, gắn nhãn LATE_NOT_FORWARD.

Các bản ghi này đến sau khi collector đã bỏ qua chúng, nên dự đoán (nếu có) sẽ được ghi sau diễn biến giá.
Vì vậy chúng không bao giờ vào forward: không tạo prediction, không vào campaign, không tính vào
forward_sample_count. Bảng chỉ phục vụ kiểm tra pipeline và bằng chứng.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .ingestion.opportunity import canonicalize_observation, validate_opportunity_payload
from .models import format_utc_timestamp, utc_now

REJECTION_REASON_PREFIX = "invalid UTC timestamp:"


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
        WHERE validation_status = 'REJECTED_SCHEMA' AND failure_reason LIKE ?
        ORDER BY received_at_utc, forward_event_id
        """,
        (REJECTION_REASON_PREFIX + "%",),
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
