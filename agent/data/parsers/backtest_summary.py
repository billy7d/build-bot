"""Parser metadata cho summary JSON; không tạo trade giả từ aggregate."""

from __future__ import annotations

import json
from pathlib import Path


def supports(path: Path) -> bool:
    return path.suffix.lower() == ".json" and "summary" in path.name.lower()


def parse(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("backtest summary phải là object JSON")
    return {
        "path": path.as_posix(),
        "keys": sorted(value),
        "is_aggregate_metadata": True,
        "event_level_source": False,
    }
