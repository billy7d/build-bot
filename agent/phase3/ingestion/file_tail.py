"""Đọc append-only JSONL/CSV an toàn với partial line và rotation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..models import sha256_bytes


@dataclass(frozen=True)
class FileTailRecord:
    start_offset: int
    end_offset: int
    raw_line: bytes


@dataclass(frozen=True)
class FileTailBatch:
    path: str
    source_identity: str
    previous_offset: int
    next_offset: int
    records: tuple[FileTailRecord, ...]
    partial_final_line: bool
    rotated: bool


def file_source_identity(path: str | Path) -> str:
    """Identity đổi khi file được rotate/recreate, ổn định khi chỉ append."""

    target = Path(path).resolve()
    stat = target.stat()
    # Chỉ đọc dòng đầu để nhận diện stream; không nạp toàn bộ file mỗi lần poll.
    with target.open("rb") as stream:
        first_line = stream.readline()
    # Không dùng ctime/mtime hay phần đuôi file vì Windows có thể cập nhật sau mỗi append.
    return f"{target}|{stat.st_dev}|{stat.st_ino}|{sha256_bytes(first_line)}"


class TelemetryFileTailer:
    """Tail theo byte offset, không parse final record chưa có newline."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read_available(
        self,
        *,
        offset_bytes: int = 0,
        source_identity: str | None = None,
    ) -> FileTailBatch:
        if offset_bytes < 0:
            raise ValueError("offset_bytes must be non-negative")
        file_size = self.path.stat().st_size
        identity = file_source_identity(self.path)
        rotated = bool(source_identity and source_identity != identity)
        start = 0 if rotated or offset_bytes > file_size else offset_bytes
        with self.path.open("rb") as stream:
            stream.seek(start)
            tail = stream.read()
        records: list[FileTailRecord] = []
        cursor = start
        partial = False
        for line in tail.splitlines(keepends=True):
            end = cursor + len(line)
            if not line.endswith((b"\n", b"\r")):
                partial = True
                break
            if line.rstrip(b"\r\n"):
                records.append(FileTailRecord(cursor, end, line))
            cursor = end
        return FileTailBatch(
            path=str(self.path.resolve()),
            source_identity=identity,
            previous_offset=start,
            next_offset=cursor,
            records=tuple(records),
            partial_final_line=partial,
            rotated=rotated,
        )


__all__ = ["FileTailBatch", "FileTailRecord", "TelemetryFileTailer", "file_source_identity"]
