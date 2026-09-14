"""CLI inventory -> parse -> normalize -> validate -> store -> report/export."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .episodes.builder import build_bundle
from .episodes.validator import assert_valid_bundle
from .inventory import build_inventory, sha256_file, write_inventory
from .models import NormalizedEvent
from .parsers import preset as preset_parser
from .parsers import v81_stddev, v82_blocked_signal
from .source_registry import descriptor_for
from ..evaluation.data_quality import run_quality
from ..evaluation.reporting import write_reports
from ..evaluation.reproducibility import build_manifest, write_manifest
from ..memory.database import apply_migrations, connect_database
from ..memory.parquet import export_tables


REPORT_DIR = Path("reports/trading_agent/phase1")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _git_commit(root: Path) -> str | None:
    from ..evaluation.reproducibility import current_git_commit
    return current_git_commit(root)


def _ea_hash(root: Path) -> str | None:
    path = root / "outputs" / "Mentor_RSI_MTF_v1.mq5"
    return sha256_file(path) if path.exists() else None


def register_version_catalog(connection: sqlite3.Connection, root: Path) -> None:
    from ..memory.repository import TradingMemoryRepository

    repository = TradingMemoryRepository(connection)
    commit = _git_commit(root)
    source_hash = _ea_hash(root)
    with connection:
        repository.register_strategy(
            {
                "id": "V26",
                "name": "V26",
                "parent_strategy_version": None,
                "git_commit": commit,
                "source_hash": source_hash,
                "description": "Execution baseline; Phase 1 không sửa execution.",
                "status": "BASELINE",
            }
        )
        repository.register_strategy(
            {
                "id": "V63",
                "name": "V63",
                "parent_strategy_version": "V26",
                "git_commit": commit,
                # Chưa có EA/source độc lập của V63 trong checkout; không mượn hash V26.
                "source_hash": None,
                "description": "Execution challenger nhận diện từ preset; chưa có trade-history raw trong checkout.",
                "status": "CHALLENGER_MISSING_EXECUTION_DATA",
            }
        )
        repository.register_audit(
            {
                "id": "V81",
                "name": "V81",
                "audit_type": "STDDEV_SHADOW",
                "base_strategy_version": "V26",
                "parent_audit_version": None,
                "git_commit": commit,
                "source_hash": source_hash,
                "mode": "SHADOW",
                "execution_authority": "NONE",
                "description": "Standard Deviation market-context audit.",
                "status": "RESEARCH_ONLY",
            }
        )
        repository.register_audit(
            {
                "id": "V82",
                "name": "V82",
                "audit_type": "BLOCKED_OPPORTUNITY",
                "base_strategy_version": "V26",
                "parent_audit_version": "V81",
                "git_commit": commit,
                "source_hash": source_hash,
                "mode": "SHADOW",
                "execution_authority": "NONE",
                "description": "Blocked signal, active context and counterfactual opportunity audit.",
                "status": "RESEARCH_ONLY",
            }
        )


def _canonical_raw_kind(item: dict[str, object]) -> bool:
    return item.get("status") == "SUPPORTED" and item.get("artifact_type") in {
        "STDDEV_SHADOW_TELEMETRY", "BLOCKED_SIGNAL_SHADOW_TELEMETRY"
    }


def _year_from_path(path: str) -> str:
    match = re.search(r"(?:^|[/_])((?:20)\d{2})(?:[/_.-]|$)", path)
    return match.group(1) if match else "unknown"


def _experiment_id(item: dict[str, object]) -> str:
    audit = str(item.get("audit_version") or "UNKNOWN")
    return f"{audit}-{_year_from_path(str(item['path']))}"


def _preset_id(item: dict[str, object]) -> str | None:
    value = item.get("preset_id")
    return str(value) if value else None


def _experiment_record(item: dict[str, object], events: list[NormalizedEvent]) -> dict[str, object]:
    timestamps = sorted(event.event_time_utc for event in events)
    year = _year_from_path(str(item["path"]))
    fold = "VALIDATION" if year in {"2023", "2024"} else "OOS" if year in {"2025", "2026"} else "UNKNOWN"
    history = "75% REAL_TICKS" if year == "2023" else "100% REAL_TICKS"
    audit = str(item.get("audit_version") or "UNKNOWN")
    return {
        "id": _experiment_id(item),
        "name": f"{audit} {year} raw shadow telemetry",
        "strategy_version": item.get("strategy_version"),
        "audit_version": item.get("audit_version"),
        "preset_id": _preset_id(item),
        "symbol": events[0].symbol if events else "BTCUSD",
        "timeframe": events[0].timeframe if events else "H1",
        "start_time": timestamps[0] if timestamps else None,
        "end_time": timestamps[-1] if timestamps else None,
        "deposit": 5000.0,
        "leverage": "1:10",
        "history_quality": history,
        "tick_model": "EVERY_TICK_REAL_TICKS",
        "purpose": f"{audit} research/audit import; không phải execution source",
        "fold_type": fold,
    }


def _parse_events(item: dict[str, object], path: Path) -> list[NormalizedEvent]:
    descriptor = descriptor_for(str(item["path"]))
    if descriptor.artifact_type == "STDDEV_SHADOW_TELEMETRY":
        return v81_stddev.parse(path, source_key=str(item["path"]), source_timezone=str(descriptor.source_timezone or ""))
    if descriptor.artifact_type == "BLOCKED_SIGNAL_SHADOW_TELEMETRY":
        return v82_blocked_signal.parse(path, source_key=str(item["path"]), source_timezone=str(descriptor.source_timezone or ""))
    raise ValueError(f"không có episode parser cho {item['path']}")


def _validate_event_ids(events: list[NormalizedEvent]) -> None:
    ids = [event.raw_event_id for event in events]
    duplicates = sorted(event_id for event_id, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate raw event_id: {duplicates[:5]}")


def _register_metadata_artifacts(connection: sqlite3.Connection, inventory: dict[str, object], root: Path) -> dict[str, int]:
    from ..memory.repository import TradingMemoryRepository

    repository = TradingMemoryRepository(connection)
    result = {"registered": 0, "skipped_duplicate": 0}
    for item in inventory.get("artifacts", []):
        if item.get("status") == "DUPLICATE_SOURCE_PATH":
            result["skipped_duplicate"] += 1
            continue
        if _canonical_raw_kind(item):
            continue
        file_hash = item.get("sha256")
        if not file_hash:
            continue
        record = {
            "path": item["path"],
            "artifact_type": item["artifact_type"],
            "sha256": file_hash,
            "file_size": item.get("size", 0),
            "parser_name": item.get("parser"),
            "parser_version": item.get("parser_version"),
            "strategy_version": item.get("strategy_version"),
            "audit_version": item.get("audit_version"),
            "preset_id": item.get("preset_id"),
            "source_timezone": item.get("source_timezone"),
            "status": "METADATA_ONLY" if item.get("status") == "METADATA_ONLY" else "UNSUPPORTED",
            "metadata": item.get("metadata", {}),
        }
        try:
            repository.insert_source_artifact(record)
            result["registered"] += 1
        except sqlite3.IntegrityError:
            # Hash/parser unique là idempotency bình thường của metadata.
            result["skipped_duplicate"] += 1
    return result


def _register_presets(connection: sqlite3.Connection, inventory: dict[str, object], root: Path) -> int:
    from ..memory.repository import TradingMemoryRepository

    repository = TradingMemoryRepository(connection)
    count = 0
    for item in inventory.get("artifacts", []):
        if item.get("artifact_type") not in {"PRESET", "AUDIT_PRESET"} or not item.get("sha256"):
            continue
        path = root / str(item["path"])
        parsed = preset_parser.parse(path, relative_path=str(item["path"]))
        repository.register_preset(
            {
                "id": parsed.preset_id,
                "name": parsed.name,
                "strategy_version": parsed.strategy_version,
                "audit_version": parsed.audit_version,
                "file_path": parsed.file_path,
                "sha256": parsed.sha256,
                "magic_number": parsed.magic_number,
                "parameters": parsed.parameters,
            }
        )
        count += 1
    return count


def _import_raw_source(connection: sqlite3.Connection, item: dict[str, object], root: Path) -> dict[str, object]:
    from ..memory.repository import TradingMemoryRepository

    repository = TradingMemoryRepository(connection)
    path = root / str(item["path"])
    parser_version = str(item.get("parser_version") or "")
    source_hash = str(item.get("sha256") or "")
    if repository.source_already_imported(source_hash, parser_version):
        return {"path": item["path"], "status": "SKIP_IDEMPOTENT", "episodes": 0}
    source_record = {
        "path": item["path"],
        "artifact_type": item["artifact_type"],
        "sha256": source_hash,
        "file_size": item.get("size", 0),
        "parser_name": item.get("parser"),
        "parser_version": parser_version,
        "strategy_version": item.get("strategy_version"),
        "audit_version": item.get("audit_version"),
        "preset_id": item.get("preset_id"),
        # Experiment chỉ được liên kết sau khi parser đọc thành công và
        # register metadata; tránh FK trỏ tới record chưa tồn tại.
        "experiment_id": None,
        "source_timezone": item.get("source_timezone"),
        "status": "IMPORTING",
        "metadata": item.get("metadata", {}),
    }
    source_id = repository.insert_source_artifact(source_record)
    try:
        events = _parse_events(item, path)
        _validate_event_ids(events)
        repository.register_experiment(_experiment_record(item, events))
        repository.link_source_experiment(source_id, _experiment_id(item))
        ordered = sorted(events, key=lambda event: (event.event_time_utc, event.raw_event_id))
        ordinal_by_key: Counter[tuple[str, str, str]] = Counter()
        with connection:
            for event in ordered:
                kind = "BLOCKED_OPPORTUNITY" if event.event_type in {"BLOCKED_SIGNAL", "CONTROL_SIGNAL", "SIGNAL"} and event.audit_version == "V82" else "FLAT_CANDIDATE" if (str(event.fields.get("raw_event_type", "")).startswith("FLAT_")) else "BLOCKED_OPPORTUNITY"
                key = (event.event_time_utc, event.side, kind)
                ordinal_by_key[key] += 1
                bundle = build_bundle(
                    event,
                    source_artifact_id=source_id,
                    experiment_id=_experiment_id(item),
                    preset_id=_preset_id(item),
                    ordinal=ordinal_by_key[key],
                )
                assert_valid_bundle(bundle)
                repository.insert_episode(bundle.episode)
                repository.insert_features(bundle.features)
                repository.insert_outcome(bundle.outcome)
                if bundle.opportunity_context:
                    repository.insert_opportunity_context(bundle.opportunity_context)
                if bundle.active_context:
                    repository.insert_active_context(bundle.active_context)
                if bundle.opportunity_outcome:
                    repository.insert_opportunity_outcome(bundle.opportunity_outcome)
            repository.update_source_status(source_id, "IMPORTED")
        return {"path": item["path"], "status": "IMPORTED", "episodes": len(events)}
    except Exception as exc:
        # Chỉ source registry được giữ lại; transaction episode đã rollback.
        with connection:
            repository.update_source_status(source_id, "FAILED", error_message=str(exc))
        return {"path": item["path"], "status": "FAILED", "episodes": 0, "error": str(exc)}


def import_all(
    *,
    root: Path,
    db_path: Path,
    inventory_path: Path,
    manifest_path: Path,
    quality_path: Path,
    parquet_dir: Path,
) -> dict[str, object]:
    root = root.resolve()
    inventory = build_inventory(root)
    write_inventory(root, inventory_path)
    connection = connect_database(db_path)
    applied = apply_migrations(connection)
    register_version_catalog(connection, root)
    with connection:
        _register_presets(connection, inventory, root)
        metadata = _register_metadata_artifacts(connection, inventory, root)
    source_results = []
    for item in inventory.get("artifacts", []):
        if _canonical_raw_kind(item):
            source_results.append(_import_raw_source(connection, item, root))
    export_result = export_tables(connection, parquet_dir)
    quality = run_quality(connection, inventory)
    quality_path.parent.mkdir(parents=True, exist_ok=True)
    quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = build_manifest(connection, root=root, inventory=inventory, quality=quality)
    write_manifest(manifest, manifest_path)
    write_reports(connection, output_dir=manifest_path.parent, inventory=inventory, quality=quality, manifest=manifest)
    fatal_quality_failure = _has_fatal_quality_failure(quality)
    result = {
        "migrations_applied": applied,
        "metadata": metadata,
        "source_results": source_results,
        "export": export_result,
        "quality": {
            "status": quality["status"],
            "fingerprint": quality["fingerprint"],
            "fatal_failures": int(fatal_quality_failure),
        },
        "manifest": manifest,
    }
    connection.close()
    return result


def _has_fatal_quality_failure(quality: dict[str, object]) -> bool:
    """Import chỉ dừng ở FATAL; ERROR vẫn được quarantine và báo cáo đầy đủ."""

    checks = quality.get("checks", [])
    return any(
        isinstance(check, dict)
        and check.get("severity") == "FATAL"
        and check.get("passed") is False
        for check in checks
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--db", type=Path, default=Path("data/trading_memory.db"))
    parser.add_argument("--inventory", type=Path, default=REPORT_DIR / "source_inventory.json")
    parser.add_argument("--manifest", type=Path, default=REPORT_DIR / "dataset_manifest.json")
    parser.add_argument("--quality", type=Path, default=REPORT_DIR / "quality_report.json")
    parser.add_argument("--parquet-dir", type=Path, default=Path("data/parquet"))
    args = parser.parse_args()
    result = import_all(
        root=args.root,
        db_path=args.db,
        inventory_path=args.inventory,
        manifest_path=args.manifest,
        quality_path=args.quality,
        parquet_dir=args.parquet_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result["quality"].get("fatal_failures", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
