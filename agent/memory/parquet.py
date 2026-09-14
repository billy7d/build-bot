"""Export các bảng analytics sang Parquet, không bắt buộc dependency ngoài."""

from __future__ import annotations

import argparse
import json
import struct
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .database import apply_migrations, connect_database


TABLE_FILES = {
    "trading_episodes": "episodes.parquet",
    "episode_features": "features.parquet",
    "executions": "executions.parquet",
    "episode_outcomes": "outcomes.parquet",
    "episode_opportunity_context": "opportunity_context.parquet",
    "episode_opportunity_outcomes": "opportunity_outcomes.parquet",
}


class _CompactWriter:
    """Một phần nhỏ Thrift Compact Protocol cần cho Parquet footer."""

    STOP = 0
    BOOL_TRUE = 1
    BOOL_FALSE = 2
    I16 = 4
    I32 = 5
    I64 = 6
    DOUBLE = 7
    BINARY = 8
    LIST = 9
    STRUCT = 12

    def __init__(self) -> None:
        self.data = bytearray()
        self.last_field_ids: list[int] = []

    @staticmethod
    def _varint(value: int) -> bytes:
        result = bytearray()
        value = int(value)
        while value & ~0x7F:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value & 0x7F)
        return bytes(result)

    @staticmethod
    def _zigzag(value: int, bits: int) -> int:
        return (value << 1) ^ (value >> (bits - 1))

    def begin_struct(self) -> None:
        self.last_field_ids.append(0)

    def end_struct(self) -> None:
        self.data.append(self.STOP)
        self.last_field_ids.pop()

    def field_header(self, field_id: int, field_type: int) -> None:
        previous = self.last_field_ids[-1]
        delta = field_id - previous
        if 1 <= delta <= 15:
            self.data.append((delta << 4) | field_type)
        else:
            self.data.append(field_type)
            self.data.extend(struct.pack("<h", field_id))
        self.last_field_ids[-1] = field_id

    def field_bool(self, field_id: int, value: bool) -> None:
        self.field_header(field_id, self.BOOL_TRUE if value else self.BOOL_FALSE)

    def field_i32(self, field_id: int, value: int) -> None:
        self.field_header(field_id, self.I32)
        self.data.extend(self._varint(self._zigzag(int(value), 32)))

    def field_i64(self, field_id: int, value: int) -> None:
        self.field_header(field_id, self.I64)
        self.data.extend(self._varint(self._zigzag(int(value), 64)))

    def field_double(self, field_id: int, value: float) -> None:
        self.field_header(field_id, self.DOUBLE)
        self.data.extend(struct.pack("<d", float(value)))

    def field_string(self, field_id: int, value: str) -> None:
        self.field_header(field_id, self.BINARY)
        encoded = value.encode("utf-8")
        self.data.extend(self._varint(len(encoded)))
        self.data.extend(encoded)

    def field_bytes(self, field_id: int, value: bytes) -> None:
        self.field_header(field_id, self.BINARY)
        self.data.extend(self._varint(len(value)))
        self.data.extend(value)

    def begin_list(self, field_id: int, element_type: int, size: int) -> None:
        self.field_header(field_id, self.LIST)
        if size < 15:
            self.data.append((size << 4) | element_type)
        else:
            self.data.append(0xF0 | element_type)
            self.data.extend(self._varint(size))


def _write_schema_element(writer: _CompactWriter, *, name: str, type_id: int | None, optional: bool, num_children: int | None = None, utf8: bool = False) -> None:
    writer.begin_struct()
    if type_id is not None:
        writer.field_i32(1, type_id)
    if optional:
        writer.field_i32(3, 1)  # Trường tùy chọn của Parquet.
    writer.field_string(4, name)
    if num_children is not None:
        writer.field_i32(5, num_children)
    if utf8:
        writer.field_i32(6, 0)  # Kiểu chuyển đổi chuỗi UTF-8 của Parquet.
    writer.end_struct()


def _write_data_page_header(writer: _CompactWriter, num_values: int) -> None:
    writer.begin_struct()
    writer.field_i32(1, num_values)
    writer.field_i32(2, 0)  # Mã hóa giá trị phẳng.
    writer.field_i32(3, 3)  # Mã hóa repetition bằng RLE.
    writer.field_i32(4, 3)  # Mã hóa definition bằng RLE.
    writer.end_struct()


def _write_page_header(writer: _CompactWriter, body_size: int, num_values: int) -> None:
    writer.begin_struct()
    writer.field_i32(1, 0)  # Trang dữ liệu Parquet.
    writer.field_i32(2, body_size)
    writer.field_i32(3, body_size)
    writer.field_header(5, writer.STRUCT)
    _write_data_page_header(writer, num_values)
    writer.end_struct()


def _rle_levels(levels: list[int], bit_width: int = 1) -> bytes:
    """Mã hóa definition levels bằng RLE/bit-packed hybrid."""

    if not levels:
        return b""
    result = bytearray()
    index = 0
    value_width = max(1, (bit_width + 7) // 8)
    while index < len(levels):
        value = levels[index]
        end = index + 1
        while end < len(levels) and levels[end] == value:
            end += 1
        run_length = end - index
        result.extend(_CompactWriter._varint(run_length << 1))
        result.extend(int(value).to_bytes(value_width, "little", signed=False))
        index = end
    return bytes(result)


def _plain_values(values: list[Any], type_id: int) -> bytes:
    payload = bytearray()
    for value in values:
        if type_id == 2:  # Giá trị số nguyên 64-bit.
            payload.extend(struct.pack("<q", int(value)))
        elif type_id == 5:  # Giá trị dấu phẩy động 64-bit.
            payload.extend(struct.pack("<d", float(value)))
        else:  # Chuỗi UTF-8 dạng byte array.
            encoded = str(value).encode("utf-8")
            payload.extend(struct.pack("<I", len(encoded)))
            payload.extend(encoded)
    return bytes(payload)


def _write_data_column(handle, values: list[Any], type_id: int, name: str) -> tuple[int, int]:
    offset = handle.tell()
    definition = [0 if value is None else 1 for value in values]
    non_null = [value for value in values if value is not None]
    # Required repetition levels have max level 0, nên section có độ dài 0.
    body = struct.pack("<I", 0)
    definition_bytes = _rle_levels(definition)
    body += struct.pack("<I", len(definition_bytes)) + definition_bytes
    body += _plain_values(non_null, type_id)
    page_writer = _CompactWriter()
    _write_page_header(page_writer, len(body), len(values))
    page_header = bytes(page_writer.data)
    handle.write(page_header)
    handle.write(body)
    total_size = len(page_header) + len(body)
    return offset, total_size


def _write_column_metadata(writer: _CompactWriter, *, type_id: int, name: str, num_values: int, offset: int, size: int) -> None:
    writer.begin_struct()
    writer.field_i32(1, type_id)
    writer.begin_list(2, writer.I32, 2)
    writer.data.extend(writer._varint(writer._zigzag(0, 32)))
    writer.data.extend(writer._varint(writer._zigzag(3, 32)))
    writer.field_header(3, writer.LIST)
    writer.data.append((1 << 4) | writer.BINARY)
    # Field 3 là list<string>; viết trực tiếp vì field_string không phù hợp.
    # Header trên đã được phát ra, phần tử string chỉ cần length + bytes.
    encoded = name.encode("utf-8")
    writer.data.extend(writer._varint(len(encoded)))
    writer.data.extend(encoded)
    writer.last_field_ids[-1] = 3
    writer.field_i32(4, 0)  # Không nén dữ liệu.
    writer.field_i64(5, num_values)
    writer.field_i64(6, size)
    writer.field_i64(7, size)
    writer.field_i64(9, offset)
    writer.end_struct()


def _write_column_chunk(writer: _CompactWriter, *, type_id: int, name: str, num_values: int, offset: int, size: int) -> None:
    writer.begin_struct()
    writer.field_i64(2, offset)
    writer.field_header(3, writer.STRUCT)
    _write_column_metadata(writer, type_id=type_id, name=name, num_values=num_values, offset=offset, size=size)
    writer.end_struct()


def _write_row_group(writer: _CompactWriter, chunks: list[tuple[int, str, int, int, int]], num_rows: int) -> None:
    writer.begin_struct()
    writer.begin_list(1, writer.STRUCT, len(chunks))
    total_size = 0
    for type_id, name, num_values, offset, size in chunks:
        _write_column_chunk(writer, type_id=type_id, name=name, num_values=num_values, offset=offset, size=size)
        total_size += size
    writer.field_i64(2, total_size)
    writer.field_i64(3, num_rows)
    writer.end_struct()


def _write_footer(columns: list[tuple[str, int, bool]], chunks: list[tuple[int, str, int, int, int]], num_rows: int) -> bytes:
    writer = _CompactWriter()
    writer.begin_struct()
    writer.field_i32(1, 1)  # Phiên bản định dạng file.
    writer.begin_list(2, writer.STRUCT, len(columns) + 1)
    _write_schema_element(writer, name="schema", type_id=None, optional=False, num_children=len(columns))
    for name, type_id, utf8 in columns:
        _write_schema_element(writer, name=name, type_id=type_id, optional=True, utf8=utf8)
    writer.field_i64(3, num_rows)
    writer.begin_list(4, writer.STRUCT, 1)
    _write_row_group(writer, chunks, num_rows)
    writer.field_string(6, "trading-memory-phase1")
    writer.end_struct()
    return bytes(writer.data)


def _sqlite_type(sql_type: str) -> tuple[int, bool]:
    upper = sql_type.upper()
    if "INT" in upper:
        return 2, False
    if any(token in upper for token in ("REAL", "FLOA", "DOUB")):
        return 5, False
    return 6, True


def _export_minimal(connection: sqlite3.Connection, table: str, output: Path) -> None:
    columns_info = connection.execute(f"PRAGMA table_info({table})").fetchall()
    names = [row[1] for row in columns_info]
    if table == "trading_episodes" and "canonical_opportunity_id" not in names:
        raise RuntimeError("episodes export thiếu canonical_opportunity_id; từ chối tạo Phase 2 dataset")
    types = [_sqlite_type(row[2]) for row in columns_info]
    order_by = names[0] if names else "rowid"
    rows = connection.execute(f"SELECT * FROM {table} ORDER BY {order_by}").fetchall()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        handle.write(b"PAR1")
        chunks: list[tuple[int, str, int, int, int]] = []
        for index, name in enumerate(names):
            values = [row[index] for row in rows]
            type_id, _ = types[index]
            offset, size = _write_data_column(handle, values, type_id, name)
            chunks.append((type_id, name, len(values), offset, size))
        schema = [(name, types[index][0], types[index][1]) for index, name in enumerate(names)]
        footer = _write_footer(schema, chunks, len(rows))
        handle.write(footer)
        handle.write(struct.pack("<I", len(footer)))
        handle.write(b"PAR1")


def _export_arrow(connection: sqlite3.Connection, table: str, output: Path) -> bool:
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore
    except ImportError:
        return False
    columns_info = connection.execute(f"PRAGMA table_info({table})").fetchall()
    names = [row[1] for row in columns_info]
    if table == "trading_episodes" and "canonical_opportunity_id" not in names:
        raise RuntimeError("episodes export thiếu canonical_opportunity_id; từ chối tạo Phase 2 dataset")
    rows = connection.execute(f"SELECT * FROM {table} ORDER BY {names[0] if names else 'rowid'}").fetchall()
    payload = {name: [row[index] for row in rows] for index, name in enumerate(names)}
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(payload), output, compression="NONE", use_dictionary=False)
    return True


def export_tables(connection: sqlite3.Connection, output_dir: Path) -> dict[str, object]:
    """Xuất sáu dataset phân tách; Arrow được ưu tiên nếu môi trường có."""

    result: dict[str, object] = {"output_dir": str(output_dir), "files": {}, "writer": "minimal-parquet"}
    for table, filename in TABLE_FILES.items():
        output = output_dir / filename
        used_arrow = _export_arrow(connection, table, output)
        if not used_arrow:
            _export_minimal(connection, table, output)
        if used_arrow:
            result["writer"] = "pyarrow"
        result["files"][filename] = {"table": table, "rows": int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]), "bytes": output.stat().st_size}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--db", type=Path, default=Path("data/trading_memory.db"))
    export_parser.add_argument("--output-dir", type=Path, default=Path("data/parquet"))
    args = parser.parse_args()
    connection = connect_database(args.db)
    apply_migrations(connection)
    result = export_tables(connection, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
