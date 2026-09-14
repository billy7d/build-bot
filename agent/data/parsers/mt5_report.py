"""Đọc metadata tối thiểu từ report MT5 mà không biến report thành raw events."""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path


def supports(path: Path) -> bool:
    return path.suffix.lower() in {".html", ".htm"}


def _read_report_text(path: Path) -> str:
    """Đọc đúng BOM để report UTF-8 không bị decode nhầm thành UTF-16."""

    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8", errors="replace")


def parse(path: Path) -> dict[str, object]:
    text = unescape(_read_report_text(path))
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    return {
        "path": path.as_posix(),
        "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else path.name,
        "is_aggregate_metadata": True,
        "event_level_source": False,
    }
