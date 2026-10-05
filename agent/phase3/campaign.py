"""Forward campaign: gom nhiều FORWARD run cùng bundle thành một mẫu đánh giá.

Một run FAILED không resume được, nên mỗi sự cố hạ tầng tạo run mới. Nếu chỉ đếm
mẫu theo từng run, bộ đếm hướng tới gate 500 mẫu quay về 0 sau mỗi sự cố. Campaign
giải quyết việc đó mà không nới contract của run:

- Membership không tùy chọn: mọi FORWARD run cùng bundle/canonicalizer, bắt đầu từ
  ``window_start_utc`` trở đi, đều thuộc campaign. Operator không thể chọn run theo
  kết quả.
- Dự đoán vẫn bất biến theo run; campaign chỉ khử trùng theo
  ``canonical_opportunity_id`` (giữ prediction commit sớm nhất).
- Khoảng gián đoạn giữa các run được báo cáo là coverage, không backfill: bản ghi
  phát sinh khi không có collector không có dự đoán commit trước outcome.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from .evaluation.metrics import evaluate_forward_records
from .models import format_utc_timestamp, parse_utc_timestamp, sha256_json


CAMPAIGN_SCHEMA = "phase3-forward-campaign/1"
MEMBERSHIP_RULE = "ALL_FORWARD_RUNS_SAME_BUNDLE_AND_CANONICALIZER_STARTED_AT_OR_AFTER_WINDOW_START"
_CAMPAIGN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class CampaignError(RuntimeError):
    """Campaign không tồn tại hoặc vi phạm contract khai báo trước."""


def validate_campaign_id(campaign_id: str) -> str:
    value = str(campaign_id or "").strip()
    if not _CAMPAIGN_ID_RE.match(value):
        raise CampaignError(f"invalid campaign_id: {campaign_id!r}")
    return value


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def get_campaign(connection: Any, campaign_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM phase3_forward_campaigns WHERE campaign_id = ?", (campaign_id,)
    ).fetchone()
    return dict(row) if row is not None else None


def declare_campaign(
    connection: Any,
    *,
    campaign_id: str,
    bundle_id: str,
    window_start_utc: str,
    primary_source_schema: str,
    canonical_schema: str,
    canonicalizer_version: str,
    canonicalizer_fingerprint: str,
    now: str,
) -> dict[str, Any]:
    """Khai báo campaign một lần; khai báo lại phải giống hệt."""

    campaign_id = validate_campaign_id(campaign_id)
    declaration = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign_id": campaign_id,
        "bundle_id": str(bundle_id),
        "window_start_utc": format_utc_timestamp(window_start_utc),
        "primary_source_schema": str(primary_source_schema),
        "canonical_schema": str(canonical_schema),
        "canonicalizer_version": str(canonicalizer_version),
        "canonicalizer_fingerprint": str(canonicalizer_fingerprint),
        "membership_rule": MEMBERSHIP_RULE,
        "deduplication": "canonical_opportunity_id, earliest prediction_committed_at_utc",
        "gap_policy": "REPORT_ONLY_NO_BACKFILL",
    }
    declaration_hash = sha256_json(declaration)
    existing = get_campaign(connection, campaign_id)
    if existing is not None:
        if str(existing["declaration_hash"]) != declaration_hash:
            raise CampaignError(f"campaign {campaign_id} already declared with a different contract")
        return existing
    with connection:
        connection.execute(
            """
            INSERT INTO phase3_forward_campaigns(
                campaign_id, bundle_id, primary_source_schema, canonical_schema,
                canonicalizer_version, canonicalizer_fingerprint, window_start_utc,
                declared_at_utc, declaration_json, declaration_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_id, declaration["bundle_id"], declaration["primary_source_schema"],
                declaration["canonical_schema"], declaration["canonicalizer_version"],
                declaration["canonicalizer_fingerprint"], declaration["window_start_utc"],
                format_utc_timestamp(now),
                json.dumps(declaration, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                declaration_hash,
            ),
        )
    return dict(get_campaign(connection, campaign_id) or {})


def _require_campaign(connection: Any, campaign_id: str) -> dict[str, Any]:
    campaign = get_campaign(connection, validate_campaign_id(campaign_id))
    if campaign is None:
        raise CampaignError(f"campaign is not declared: {campaign_id}")
    return campaign


def _run_canonicalizer_fingerprints(connection: Any, run_id: str) -> set[str]:
    rows = connection.execute(
        "SELECT DISTINCT canonicalizer_fingerprint FROM phase3_opportunity_observations WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def sync_campaign_runs(connection: Any, campaign_id: str, *, now: str) -> dict[str, Any]:
    """Gắn mọi run đủ điều kiện; không có lựa chọn thủ công từng run."""

    campaign = _require_campaign(connection, campaign_id)
    window_start = parse_utc_timestamp(str(campaign["window_start_utc"]))
    rows = connection.execute(
        "SELECT * FROM phase3_forward_runs WHERE mode = 'FORWARD' AND bundle_id = ? ORDER BY started_at_utc, run_id",
        (campaign["bundle_id"],),
    ).fetchall()
    existing = set(campaign_run_ids(connection, campaign["campaign_id"]))
    attached: list[str] = []
    excluded: list[dict[str, str]] = []
    for row in rows:
        run_id = str(row["run_id"])
        if parse_utc_timestamp(str(row["started_at_utc"])) < window_start:
            continue
        fingerprints = _run_canonicalizer_fingerprints(connection, run_id)
        if fingerprints and fingerprints != {str(campaign["canonicalizer_fingerprint"])}:
            excluded.append({"run_id": run_id, "reason": "CANONICALIZER_MISMATCH"})
            continue
        if run_id in existing:
            continue
        with connection:
            connection.execute(
                "INSERT INTO phase3_forward_campaign_runs(campaign_id, run_id, attached_at_utc, attach_reason) VALUES (?, ?, ?, ?)",
                (campaign["campaign_id"], run_id, format_utc_timestamp(now), MEMBERSHIP_RULE),
            )
        attached.append(run_id)
    return {
        "campaign_id": campaign["campaign_id"],
        "attached": attached,
        "excluded": excluded,
        "member_run_ids": campaign_run_ids(connection, campaign["campaign_id"]),
    }


def campaign_run_ids(connection: Any, campaign_id: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT c.run_id FROM phase3_forward_campaign_runs c
        JOIN phase3_forward_runs r ON r.run_id = c.run_id
        WHERE c.campaign_id = ?
        ORDER BY r.started_at_utc, c.run_id
        """,
        (campaign_id,),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def campaign_sample_count(connection: Any, campaign_id: str) -> dict[str, int]:
    """Đếm canonical opportunity khác nhau qua mọi run thành viên."""

    members = campaign_run_ids(connection, campaign_id)
    if not members:
        return {"forward_sample_count": 0, "canonical_row_count": 0, "cross_run_duplicate_count": 0}
    row = connection.execute(
        f"""
        SELECT COUNT(DISTINCT canonical_opportunity_id), COUNT(*)
        FROM phase3_canonical_opportunities
        WHERE run_id IN ({_placeholders(members)}) AND status IN ('SCORABLE', 'NO_OPINION')
        """,
        tuple(members),
    ).fetchone()
    distinct, total = int(row[0]), int(row[1])
    return {
        "forward_sample_count": distinct,
        "canonical_row_count": total,
        "cross_run_duplicate_count": total - distinct,
    }


def _latest_failure(connection: Any, run_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT value_json, created_at_utc FROM phase3_health_events WHERE run_id = ? AND event_type = 'RUN_FAILED' ORDER BY id DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        value = json.loads(str(row["value_json"]))
    except (TypeError, ValueError):
        value = {}
    return {"at_utc": str(row["created_at_utc"]), **(value if isinstance(value, Mapping) else {})}


def campaign_coverage(connection: Any, campaign_id: str) -> dict[str, Any]:
    """Khoảng collector thực sự chạy và các khoảng trống giữa chúng."""

    campaign = _require_campaign(connection, campaign_id)
    runs: list[dict[str, Any]] = []
    intervals: list[tuple[Any, Any]] = []
    for run_id in campaign_run_ids(connection, campaign["campaign_id"]):
        run = _row_dict(connection.execute("SELECT * FROM phase3_forward_runs WHERE run_id = ?", (run_id,)).fetchone())
        liveness = connection.execute(
            "SELECT first_cycle_utc, last_cycle_utc, cycle_count FROM phase3_forward_run_liveness WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if liveness is not None:
            first, last = str(liveness["first_cycle_utc"]), str(liveness["last_cycle_utc"])
            basis, cycles = "LIVENESS", int(liveness["cycle_count"])
        else:
            # Run tạo trước migration 010 không có liveness: ước lượng bảo thủ từ dữ liệu đã nhận.
            received = connection.execute(
                "SELECT MAX(received_at_utc) FROM phase3_opportunity_observations WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            first = str(run.get("started_at_utc"))
            last = str(received) if received else first
            basis, cycles = "ESTIMATED_PRE_LIVENESS", 0
        runs.append({
            "run_id": run_id,
            "status": run.get("status"),
            "git_sha": run.get("git_sha"),
            "started_at_utc": run.get("started_at_utc"),
            "active_from_utc": first,
            "active_to_utc": last,
            "coverage_basis": basis,
            "cycle_count": cycles,
            "last_failure": _latest_failure(connection, run_id),
        })
        intervals.append((parse_utc_timestamp(first), parse_utc_timestamp(last)))
    intervals.sort()
    merged: list[list[Any]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    gaps = [
        {
            "from_utc": format_utc_timestamp(previous[1]),
            "to_utc": format_utc_timestamp(current[0]),
            "seconds": round((current[0] - previous[1]).total_seconds(), 3),
        }
        for previous, current in zip(merged, merged[1:])
    ]
    covered = sum((end - start).total_seconds() for start, end in merged)
    span = (merged[-1][1] - merged[0][0]).total_seconds() if merged else 0.0
    return {
        "campaign_id": campaign["campaign_id"],
        "runs": runs,
        "gaps": gaps,
        "covered_seconds": round(covered, 3),
        "span_seconds": round(span, 3),
        "coverage_ratio": round(covered / span, 6) if span > 0 else None,
    }


def campaign_evaluation_records(runtime: Any, campaign_id: str) -> tuple[list[dict[str, Any]], int]:
    """Record đã resolve của mọi run thành viên, khử trùng theo canonical id."""

    members = set(campaign_run_ids(runtime.connection, campaign_id))
    selected: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for record in runtime._evaluation_records(None):
        if str(record.get("forward_run_id")) not in members:
            continue
        key = str(record.get("canonical_opportunity_id") or f"event:{record.get('forward_event_id')}")
        previous = selected.get(key)
        if previous is None:
            selected[key] = record
            continue
        duplicates += 1
        # So sánh theo thời gian thật: chuỗi có/không có microsecond không sắp xếp đúng theo từ điển.
        if parse_utc_timestamp(str(record["prediction_committed_at_utc"])) < parse_utc_timestamp(
            str(previous["prediction_committed_at_utc"])
        ):
            selected[key] = record
    records = sorted(
        selected.values(),
        key=lambda item: (parse_utc_timestamp(str(item["source_event_timestamp_utc"])), str(item.get("forward_event_id"))),
    )
    return records, duplicates


def evaluate_campaign(runtime: Any, campaign_id: str) -> dict[str, Any]:
    campaign = _require_campaign(runtime.connection, campaign_id)
    if str(campaign["bundle_id"]) != runtime.bundle.bundle_id:
        raise CampaignError("runtime bundle does not match campaign bundle")
    records, duplicates = campaign_evaluation_records(runtime, campaign["campaign_id"])
    result = evaluate_forward_records(
        records,
        classification_min_resolved=runtime.config.classification_min_resolved,
        regression_min_resolved=runtime.config.regression_min_resolved,
        seed=runtime.config.random_seed,
    )
    return {
        **result,
        "campaign_id": campaign["campaign_id"],
        "member_run_ids": campaign_run_ids(runtime.connection, campaign["campaign_id"]),
        "cross_run_duplicate_resolved_count": duplicates,
        "sample_counts": campaign_sample_count(runtime.connection, campaign["campaign_id"]),
    }


__all__ = [
    "CAMPAIGN_SCHEMA",
    "CampaignError",
    "campaign_coverage",
    "campaign_evaluation_records",
    "campaign_run_ids",
    "campaign_sample_count",
    "declare_campaign",
    "evaluate_campaign",
    "get_campaign",
    "sync_campaign_runs",
    "validate_campaign_id",
]
