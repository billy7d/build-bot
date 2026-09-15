"""Adapter read-only cho JSONL/CSV telemetry file."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .file_tail import FileTailBatch, FileTailRecord, TelemetryFileTailer


@dataclass(frozen=True)
class ParsedTelemetryLine:
    record: FileTailRecord
    payload: Mapping[str, Any] | None
    error: str | None = None


class ReadOnlyTelemetryAdapter:
    """Đọc telemetry, không có API write/control tới MT5."""

    def __init__(self, path: str, *, file_format: str = "jsonl"):
        normalized = file_format.lower()
        if normalized not in {"jsonl", "ndjson", "csv"}:
            raise ValueError("file_format must be jsonl, ndjson or csv")
        self.tailer = TelemetryFileTailer(path)
        self.file_format = normalized

    def _csv_header(self) -> list[str] | None:
        if self.file_format != "csv":
            return None
        with self.tailer.path.open("rb") as stream:
            first_line = stream.readline()
        if not first_line or not first_line.endswith((b"\n", b"\r")):
            return None
        return next(csv.reader(io.StringIO(first_line.decode("utf-8-sig"))))

    def parse_line(self, record: FileTailRecord, *, header: list[str] | None = None) -> ParsedTelemetryLine:
        try:
            if self.file_format in {"jsonl", "ndjson"}:
                value = json.loads(record.raw_line.decode("utf-8"))
            else:
                if not header:
                    raise ValueError("CSV header is missing")
                values = next(csv.reader(io.StringIO(record.raw_line.decode("utf-8"))))
                value = dict(zip(header, values))
                if "context" in value and value["context"]:
                    value["context"] = json.loads(value["context"])
            if not isinstance(value, Mapping):
                raise ValueError("record must decode to an object")
            return ParsedTelemetryLine(record, dict(value))
        except (UnicodeDecodeError, json.JSONDecodeError, StopIteration, ValueError) as exc:
            return ParsedTelemetryLine(record, None, str(exc))

    def read_available(
        self,
        *,
        offset_bytes: int = 0,
        source_identity: str | None = None,
    ) -> tuple[FileTailBatch, tuple[ParsedTelemetryLine, ...]]:
        batch = self.tailer.read_available(offset_bytes=offset_bytes, source_identity=source_identity)
        header = self._csv_header()
        lines = list(batch.records)
        if self.file_format == "csv" and batch.previous_offset == 0 and lines:
            # Header là metadata của stream, không phải telemetry event.
            lines = lines[1:]
        return batch, tuple(self.parse_line(record, header=header) for record in lines)


__all__ = ["ParsedTelemetryLine", "ReadOnlyTelemetryAdapter"]
