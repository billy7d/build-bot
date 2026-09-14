"""Điểm truy cập migration versioned cho các caller ngoài database.py."""

from __future__ import annotations

from pathlib import Path

from .database import apply_migrations, migration_versions


def available_migrations(directory: str | Path | None = None) -> list[str]:
    """Liệt kê version theo thứ tự mà pipeline sẽ áp dụng."""

    root = Path(directory) if directory else Path(__file__).parent / "migrations"
    return [path.name.split("_", 1)[0] for path in sorted(root.glob("[0-9][0-9][0-9]_*.sql"))]


__all__ = ["apply_migrations", "available_migrations", "migration_versions"]
