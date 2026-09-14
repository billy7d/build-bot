"""Mở SQLite và áp dụng migration versioned một cách deterministic."""

from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATION_TABLE = "schema_migrations"


def connect_database(path: str | Path) -> sqlite3.Connection:
    """Mở DB với các pragma bắt buộc của Trading Memory."""

    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    # WAL là yêu cầu cho đọc analytics ổn định; không dùng connection khác để
    # ghi đồng thời trong pipeline import.
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


def apply_migrations(
    connection: sqlite3.Connection,
    migrations_dir: str | Path | None = None,
) -> list[str]:
    """Chỉ chạy migration chưa có trong schema_migrations."""

    directory = Path(migrations_dir) if migrations_dir else Path(__file__).parent / "migrations"
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {
        row[0]
        for row in connection.execute("SELECT version FROM schema_migrations")
    }
    migrations_run: list[str] = []
    for migration in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        version = migration.name.split("_", 1)[0]
        if version in applied:
            continue
        sql = migration.read_text(encoding="utf-8")
        # Mỗi file là một đơn vị schema; nếu lỗi thì transaction rollback.
        with connection:
            connection.executescript(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
                (version,),
            )
        migrations_run.append(version)
    return migrations_run


def migration_versions(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return [str(row[0]) for row in rows]


def integrity_status(connection: sqlite3.Connection) -> dict[str, object]:
    """Chạy hai integrity check chuẩn của SQLite."""

    foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    return {
        "foreign_key_check": foreign_keys,
        "foreign_key_ok": not foreign_keys,
        "integrity_check": integrity,
        "integrity_ok": integrity == "ok",
    }
