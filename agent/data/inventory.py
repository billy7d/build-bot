"""Quét source artifact và tạo inventory có hash/provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .source_registry import ARTIFACT_TYPES, SourceDescriptor, descriptor_for, relative_key


PHASE1_REPORT_DIR = Path("reports/trading_agent/phase1")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_v81_raw(relative: str) -> bool:
    return bool(re.fullmatch(r"outputs/build/v81-runs/[^/]+/shadow-signals\.csv", relative, re.I))


def _is_v82_raw(relative: str) -> bool:
    return bool(re.fullmatch(r"outputs/build/v82_runs/[^/]+\.csv", relative, re.I)) or (
        "blocked_signals.csv" in Path(relative).name.lower()
    )


def _include_path(relative: str) -> bool:
    """Chỉ lấy artifact research, bỏ runtime MT5/binary/cache khổng lồ."""

    lowered = relative.lower()
    parts = set(Path(lowered).parts)
    if ".git" in parts or "reports/trading_agent" in lowered:
        return False
    if Path(relative).name.lower() in {".ds_store"} or lowered.endswith(".ex5"):
        return False
    if lowered.startswith("outputs/presets/") and lowered.endswith(".set"):
        return True
    if _is_v81_raw(relative) or _is_v82_raw(relative):
        return True
    if lowered.startswith("backtests/"):
        return True
    if lowered.startswith("outputs/build/"):
        basename = Path(relative).name.lower()
        # Giữ summary/report/config/journal liên quan; loại toàn bộ MT5 runtime.
        if any(token in lowered for token in ("/mt5-latest/", "/mt5-portable/", "/mt5-provisioned/", "/mt5-v82-runtime/", "/mt5-v82-official-runtime/", "/mt5-docker/", "/v26-repo/", "/pymql5/")):
            return _is_v82_raw(relative)
        return basename.endswith((".json", ".md", ".html", ".htm", ".ini", ".log", ".txt"))
    if lowered.startswith("outputs/") and "/" not in lowered[len("outputs/"):]:
        return Path(relative).suffix.lower() in {".json", ".md", ".csv", ".txt", ".log", ".ini"}
    return False


def iter_candidate_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file():
            relative = relative_key(root, path)
            if _include_path(relative):
                paths.append(path)
    return sorted(paths, key=lambda item: relative_key(root, item).lower())


def _metadata_for(relative: str, descriptor: SourceDescriptor) -> dict[str, object]:
    return {
        "source_timezone": descriptor.source_timezone,
        "timezone_confidence": descriptor.timezone_confidence,
        "timezone_evidence": descriptor.timezone_evidence,
        "importable": descriptor.importable,
        "metadata_only": descriptor.metadata_only,
    }


def build_inventory(root: Path) -> dict[str, object]:
    root = root.resolve()
    candidates = iter_candidate_files(root)
    # Ưu tiên thư mục raw canonical hơn bản sao Agent/Tester trong runtime.
    candidates = sorted(
        candidates,
        key=lambda item: (
            0 if _is_v81_raw(relative_key(root, item)) or re.fullmatch(r"outputs/build/v82_runs/[^/]+\.csv", relative_key(root, item), re.I) else 1,
            relative_key(root, item).lower(),
        ),
    )
    artifacts: list[dict[str, object]] = []
    hash_owner: dict[tuple[str, str | None, str | None], str] = {}
    for path in candidates:
        relative = relative_key(root, path)
        descriptor = descriptor_for(relative)
        file_hash = sha256_file(path)
        key = (file_hash, descriptor.parser_name, descriptor.parser_version)
        status = "SUPPORTED" if descriptor.importable else "METADATA_ONLY" if descriptor.metadata_only else "UNKNOWN"
        if key in hash_owner and descriptor.importable:
            status = "DUPLICATE_SOURCE_PATH"
        else:
            hash_owner[key] = relative
        artifacts.append(
            {
                "path": relative,
                "artifact_type": descriptor.artifact_type if descriptor.artifact_type in ARTIFACT_TYPES else "UNKNOWN",
                "size": path.stat().st_size,
                "sha256": file_hash,
                "strategy_version": descriptor.strategy_version,
                "audit_version": descriptor.audit_version,
                "preset_id": descriptor.preset_id,
                "parser": descriptor.parser_name,
                "parser_version": descriptor.parser_version,
                "source_timezone": descriptor.source_timezone,
                "timezone_confidence": descriptor.timezone_confidence,
                "status": status,
                "metadata": _metadata_for(relative, descriptor),
            }
        )

    canonical_v82 = [item for item in artifacts if item["artifact_type"] == "BLOCKED_SIGNAL_SHADOW_TELEMETRY" and item["status"] == "SUPPORTED"]
    raw_v82_status = "AVAILABLE" if canonical_v82 else "MISSING_RAW_SOURCE"
    if not canonical_v82:
        artifacts.append(
            {
                "path": "outputs/build/v82_runs/",
                "artifact_type": "BLOCKED_SIGNAL_SHADOW_TELEMETRY",
                "size": 0,
                "sha256": None,
                "strategy_version": "V26",
                "audit_version": "V82",
                "preset_id": "82_v26_blocked_signal_shadow_audit",
                "parser": "v82_blocked_signal",
                "parser_version": "v82-parser/1",
                "source_timezone": "UTC",
                "timezone_confidence": "UNKNOWN",
                "status": "MISSING_RAW_SOURCE",
                "metadata": {"reason": "Không tìm thấy raw V82 CSV trong filesystem checkout"},
            }
        )
    artifacts.sort(key=lambda item: str(item["path"]).lower())
    counts: dict[str, int] = {}
    for item in artifacts:
        kind = str(item["artifact_type"])
        counts[kind] = counts.get(kind, 0) + 1
    return {
        "schema": "trading_memory_source_inventory_v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "root": ".",
        "raw_v82_status": raw_v82_status,
        "artifact_count": len(artifacts),
        "artifact_type_counts": dict(sorted(counts.items())),
        "artifacts": artifacts,
        "known_exclusions": [
            "outputs/build/MT5 runtime directories, .git snapshots and .ex5 binaries are not research source artifacts",
            "reports/trading_agent/phase1 is generated output and is not re-imported as raw input",
        ],
    }


def write_inventory(root: Path, output: Path) -> dict[str, object]:
    inventory = build_inventory(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=PHASE1_REPORT_DIR / "source_inventory.json")
    args = parser.parse_args()
    inventory = write_inventory(args.root, args.output)
    print(json.dumps({
        "artifact_count": inventory["artifact_count"],
        "artifact_type_counts": inventory["artifact_type_counts"],
        "raw_v82_status": inventory["raw_v82_status"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
