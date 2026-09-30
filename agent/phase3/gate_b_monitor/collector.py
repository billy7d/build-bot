"""Raw evidence collection for one approved monitor session.

The collector copies evidence into a new root and never truncates, rewinds or
changes an MT5 journal.  It accepts no credentials and does not read or write
the telemetry JSONL as a live signal.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import PermissionSample, parse_utc, utc_string


MONITOR_PREFIX = "PR6_READ_ONLY_PERMISSION_MONITOR_V2/1"
_PAIR_RE = re.compile(r"(?P<key>[a-z_]+)=(?P<value>[^\s]+)")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ParsedJournalLine:
    line_number: int
    raw_line: str
    sample: PermissionSample


def parse_monitor_line(line: str, line_number: int) -> ParsedJournalLine | None:
    """Parse only the V2 prefix; unrelated journal lines are ignored."""

    if MONITOR_PREFIX not in line:
        return None
    tail = line.split(MONITOR_PREFIX, 1)[1]
    values = {match.group("key"): match.group("value") for match in _PAIR_RE.finditer(tail)}
    try:
        sample = PermissionSample.from_mapping(values)
    except (KeyError, TypeError, ValueError):
        return None
    return ParsedJournalLine(line_number, line.rstrip("\r\n"), sample)


def parse_monitor_journal(path: Path) -> list[ParsedJournalLine]:
    parsed: list[ParsedJournalLine] = []
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        item = parse_monitor_line(line, number)
        if item is not None:
            parsed.append(item)
    return parsed


def parse_compile_result(path: Path, source_name: str) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    matches = [line for line in lines if source_name in line and "Compile" in line]
    if not matches:
        return {"status": "MISSING", "errors": None, "warnings": None, "line": None}
    line = matches[-1]
    error_match = re.search(r"-\s*(\d+)\s+errors?,\s*(\d+)\s+warnings?", line, flags=re.IGNORECASE)
    if not error_match:
        return {"status": "INCONCLUSIVE", "errors": None, "warnings": None, "line": line}
    errors = int(error_match.group(1))
    warnings = int(error_match.group(2))
    return {
        "status": "PASS" if errors == 0 and warnings == 0 else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "line": line,
    }


class EvidenceCollectionError(RuntimeError):
    """Evidence cannot be bounded or copied safely."""


class EvidenceCollector:
    """Collect one raw journal slice and its provenance into a new root."""

    def __init__(self, evidence_root: Path) -> None:
        self.evidence_root = evidence_root

    def _copy_no_overwrite(self, source: Path, destination: Path) -> dict[str, Any]:
        if not source.is_file():
            raise EvidenceCollectionError(f"RAW_SOURCE_MISSING:{source}")
        source_hash = sha256_file(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha256_file(destination) != source_hash:
                raise EvidenceCollectionError(f"EVIDENCE_TARGET_HASH_CONFLICT:{destination}")
        else:
            shutil.copy2(source, destination)
        return {
            "source_path": str(source),
            "evidence_path": str(destination),
            "source_length_bytes": source.stat().st_size,
            "source_sha256": source_hash,
            "evidence_sha256": sha256_file(destination),
            "source_last_write_utc": datetime.fromtimestamp(source.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z"),
        }

    def collect(
        self,
        *,
        journal_path: Path,
        session_id: str,
        chart_id: int,
        start_utc: datetime,
        end_utc: datetime,
        baseline_offset: int = 0,
        source_sha256: str,
        ex5_sha256: str,
        compile_log_path: Path | None = None,
        terminal_journal_path: Path | None = None,
        chart_closed_confirmed: bool = False,
        ea_removed_confirmed: bool = False,
        trade_matches: Iterable[str] = (),
    ) -> dict[str, Any]:
        start_utc = parse_utc(start_utc)
        end_utc = parse_utc(end_utc)
        if end_utc < start_utc:
            raise EvidenceCollectionError("INVALID_SESSION_BOUNDARY")
        if baseline_offset < 0:
            raise EvidenceCollectionError("INVALID_BASELINE_OFFSET")
        if not journal_path.is_file():
            raise EvidenceCollectionError(f"RAW_SOURCE_MISSING:{journal_path}")
        raw_bytes = journal_path.read_bytes()
        if len(raw_bytes) < baseline_offset:
            raise EvidenceCollectionError("JOURNAL_SHRANK_BELOW_BASELINE")
        parsed = parse_monitor_journal(journal_path)
        session_lines = [item for item in parsed if item.sample.session_id == session_id and item.sample.chart_id == chart_id]
        samples = [item.sample for item in session_lines if start_utc <= item.sample.timestamp_utc <= end_utc]
        if not samples:
            raise EvidenceCollectionError("NO_NEW_VALID_MONITOR_SAMPLES_IN_WINDOW")
        unrelated_monitor_sessions = [item for item in parsed if item.sample.session_id != session_id]
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        raw_meta = self._copy_no_overwrite(journal_path, self.evidence_root / "raw" / journal_path.name)
        terminal_meta = None
        if terminal_journal_path is not None:
            terminal_meta = self._copy_no_overwrite(terminal_journal_path, self.evidence_root / "raw" / f"terminal-{terminal_journal_path.name}")
        compile_result = None
        if compile_log_path is not None:
            compile_result = parse_compile_result(compile_log_path, "PR6_ReadOnlyPermissionMonitor_V2.mq5")
            compile_meta = self._copy_no_overwrite(compile_log_path, self.evidence_root / "raw" / "metaeditor.log")
        else:
            compile_meta = None
        payload: dict[str, Any] = {
            "schema": "pr6-gate-b-monitor-v2-evidence/1",
            "session_id": session_id,
            "chart_id": chart_id,
            "start_utc": utc_string(start_utc),
            "end_utc": utc_string(end_utc),
            "baseline_offset": baseline_offset,
            "end_offset": len(raw_bytes),
            "source_sha256": source_sha256,
            "ex5_sha256": ex5_sha256,
            "samples": [sample.to_dict() for sample in samples],
            "sample_line_numbers": [item.line_number for item in session_lines if start_utc <= item.sample.timestamp_utc <= end_utc],
            "raw_journal": raw_meta,
            "terminal_journal": terminal_meta,
            "compile": compile_result,
            "compile_log": compile_meta,
            "unrelated_monitor_sessions_present": bool(unrelated_monitor_sessions),
            "ea_removed_confirmed": bool(ea_removed_confirmed),
            "chart_closed_confirmed": bool(chart_closed_confirmed),
            "trade_matches": list(trade_matches),
            "credentials_recorded": False,
        }
        return payload

    def write_payload(self, payload: Mapping[str, Any], *, name: str = "monitor-evidence.json") -> Path:
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        destination = self.evidence_root / name
        if destination.exists():
            raise EvidenceCollectionError(f"EVIDENCE_TARGET_EXISTS:{destination}")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.evidence_root, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(dict(payload), handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, destination)
        return destination


__all__ = [
    "EvidenceCollectionError",
    "EvidenceCollector",
    "MONITOR_PREFIX",
    "ParsedJournalLine",
    "parse_compile_result",
    "parse_monitor_journal",
    "parse_monitor_line",
    "sha256_file",
]
