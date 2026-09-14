"""Parser preset MT5 dạng key=value."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..models import ParsedPreset
from ..normalization.numbers import parse_bool, parse_number
from ..source_registry import descriptor_for


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_value(key: str, raw: str) -> Any:
    text = raw.strip()
    if text.lower() in {"true", "false", "yes", "no"}:
        return parse_bool(text, field=key, allow_empty=False)
    try:
        number = parse_number(text, field=key)
    except ValueError:
        number = None
    return number if number is not None else text


def parse(path: Path, *, relative_path: str) -> ParsedPreset:
    parameters: dict[str, Any] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if "=" not in text:
            raise ValueError(f"preset dòng {line_number} thiếu '='")
        key, value = text.split("=", 1)
        key = key.strip()
        if not key or key in parameters:
            raise ValueError(f"preset dòng {line_number}: key rỗng/trùng {key!r}")
        parameters[key] = parse_value(key, value)
    descriptor = descriptor_for(relative_path)
    magic = parameters.get("MagicNumber")
    return ParsedPreset(
        preset_id=path.stem,
        name=path.name,
        strategy_version=descriptor.strategy_version,
        audit_version=descriptor.audit_version,
        file_path=relative_path,
        sha256=sha256_file(path),
        magic_number=int(magic) if isinstance(magic, (int, float)) else None,
        parameters=parameters,
    )
