"""Stable fingerprints for Phase 2 feature and split artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Mapping


FLOAT_DIGITS = 12


def _stable(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is not reproducible")
        return round(value, FLOAT_DIGITS)
    if isinstance(value, Mapping):
        return {str(key): _stable(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple, set, frozenset)):
        values = [_stable(item) for item in value]
        if isinstance(value, (set, frozenset)):
            return sorted(values, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
        return values
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _stable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def fingerprint_records(records: Iterable[Mapping[str, Any]], *, key: str = "canonical_opportunity_id") -> str:
    """Fingerprint records independent of input row order."""

    normalized = [_stable(record) for record in records]
    normalized.sort(key=lambda item: (str(item.get(key, "")), canonical_json(item)))
    return fingerprint(normalized)


def feature_fingerprint(records: Iterable[Mapping[str, Any]]) -> str:
    return fingerprint_records(records)


def split_fingerprint(assignments: Mapping[str, str]) -> str:
    return fingerprint({str(key): str(assignments[key]) for key in sorted(assignments)})


__all__ = ["FLOAT_DIGITS", "canonical_json", "feature_fingerprint", "fingerprint", "fingerprint_records", "split_fingerprint"]
