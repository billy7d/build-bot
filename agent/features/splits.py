"""Chronological, canonical-grouped Phase 2 split engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable, Mapping

from ..data.normalization.timestamps import timestamp_to_datetime
from .fingerprint import fingerprint, split_fingerprint


class SplitError(ValueError):
    """Raised for invalid temporal or canonical split assignments."""


@dataclass(frozen=True)
class SplitConfig:
    version: str = "phase2-split/1"
    train_end: str | None = None
    validation_end: str | None = None
    oos_end: str | None = None
    forward_start: str | None = None
    train_fraction: float = 0.6
    validation_fraction: float = 0.2
    forward_status: str = "RESERVED_NOT_USED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "train_end": self.train_end,
            "validation_end": self.validation_end,
            "oos_end": self.oos_end,
            "forward_start": self.forward_start,
            "train_fraction": self.train_fraction,
            "validation_fraction": self.validation_fraction,
            "forward_status": self.forward_status,
        }


def _timestamp(value: str) -> Any:
    parsed = timestamp_to_datetime(value)
    if parsed.tzinfo is None:
        raise SplitError("internal timestamp is naive; UTC timezone is mandatory")
    return parsed


def _derive_boundaries(rows: list[Mapping[str, Any]], config: SplitConfig) -> tuple[str | None, str | None]:
    timestamps = sorted({_timestamp(str(row["timestamp_utc"])) for row in rows})
    if not timestamps:
        return None, None
    if len(timestamps) == 1:
        train_boundary = timestamps[0] + timedelta(microseconds=1)
        validation_boundary = timestamps[0] + timedelta(microseconds=2)
        return (
            train_boundary.isoformat().replace("+00:00", "Z"),
            validation_boundary.isoformat().replace("+00:00", "Z"),
        )
    if len(timestamps) == 2:
        train_end = timestamps[1].isoformat().replace("+00:00", "Z")
        validation_end = (timestamps[1] + timedelta(microseconds=1)).isoformat().replace("+00:00", "Z")
        return train_end, validation_end
    train_fraction = min(max(float(config.train_fraction), 0.0), 0.99)
    validation_fraction = min(max(float(config.validation_fraction), 0.0), 0.99 - train_fraction)
    train_index = max(1, min(len(timestamps) - 1, int(len(timestamps) * train_fraction))) if len(timestamps) > 1 else 1
    validation_index = max(train_index + (1 if len(timestamps) > train_index else 0), int(len(timestamps) * (train_fraction + validation_fraction)))
    if validation_index >= len(timestamps):
        validation_index = len(timestamps) - 1 if len(timestamps) > 1 else len(timestamps)
    train_end = timestamps[train_index].isoformat().replace("+00:00", "Z") if train_index < len(timestamps) else None
    validation_end = timestamps[validation_index].isoformat().replace("+00:00", "Z") if validation_index < len(timestamps) else None
    return train_end, validation_end


def build_temporal_splits(
    rows: Iterable[Mapping[str, Any]],
    config: SplitConfig | None = None,
    *,
    train_end: str | None = None,
    validation_end: str | None = None,
    oos_end: str | None = None,
    forward_start: str | None = None,
) -> dict[str, str]:
    """Assign each canonical id exactly once in chronological order.

    Explicit cutoffs are preferred.  If absent, deterministic boundaries are
    derived from unique UTC timestamps, never from a random row shuffle.
    """

    config = config or SplitConfig(train_end=train_end, validation_end=validation_end, oos_end=oos_end, forward_start=forward_start)
    records = list(rows)
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in records:
        identifier = str(row.get("canonical_opportunity_id") or "")
        if not identifier:
            raise SplitError("canonical_opportunity_id is required for modeling splits")
        if identifier in by_id:
            # A caller may still have the two Phase 1 audit observations.  A
            # split is a modeling operation, so collapse them to one
            # canonical assignment using the conservative latest timestamp.
            previous = by_id[identifier]
            if _timestamp(str(row["timestamp_utc"])) > _timestamp(str(previous["timestamp_utc"])):
                by_id[identifier] = row
            continue
        _timestamp(str(row.get("timestamp_utc")))
        by_id[identifier] = row

    actual_train_end = config.train_end
    actual_validation_end = config.validation_end
    if actual_train_end is None or actual_validation_end is None:
        # Derive boundaries from canonical samples, not audit observations.
        # This keeps a duplicated V81/V82 pair from changing the temporal
        # cutoffs when the split API is called before canonicalization.
        actual_train_end, actual_validation_end = _derive_boundaries(list(by_id.values()), config)
    if actual_train_end is not None:
        _timestamp(actual_train_end)
    if actual_validation_end is not None:
        _timestamp(actual_validation_end)
    actual_forward_start = config.forward_start or config.oos_end
    if actual_forward_start is not None:
        _timestamp(actual_forward_start)
    if actual_train_end and actual_validation_end and _timestamp(actual_train_end) >= _timestamp(actual_validation_end):
        raise SplitError("TRAIN end must be earlier than VALIDATION end")
    if actual_validation_end and actual_forward_start and _timestamp(actual_validation_end) >= _timestamp(actual_forward_start):
        raise SplitError("VALIDATION end must be earlier than FORWARD start")

    assignments: dict[str, str] = {}
    for identifier, row in sorted(by_id.items(), key=lambda item: (_timestamp(str(item[1]["timestamp_utc"])), item[0])):
        timestamp = _timestamp(str(row["timestamp_utc"]))
        if actual_train_end is not None and timestamp < _timestamp(actual_train_end):
            split = "TRAIN"
        elif actual_validation_end is not None and timestamp < _timestamp(actual_validation_end):
            split = "VALIDATION"
        elif actual_forward_start is not None and timestamp >= _timestamp(actual_forward_start):
            split = "FORWARD"
        else:
            split = "OOS" if actual_validation_end is not None else "UNKNOWN"
        assignments[identifier] = split

    seen: dict[str, set[str]] = {}
    for identifier, split in assignments.items():
        seen.setdefault(split, set()).add(identifier)
    overlap = sum(len(seen[left] & seen[right]) for left in seen for right in seen if left < right)
    if overlap:
        raise SplitError(f"canonical overlap across folds: {overlap}")
    return assignments


def build_split_manifest(
    rows: Iterable[Mapping[str, Any]],
    assignments: Mapping[str, str],
    *,
    dataset_fingerprint: str,
    feature_set_version: str,
    config: SplitConfig | None = None,
) -> dict[str, Any]:
    records = list(rows)
    by_id = {str(row["canonical_opportunity_id"]): row for row in records}
    if set(by_id) != set(assignments):
        raise SplitError("split assignments do not cover exactly the canonical modeling rows")

    def bounds(split: str) -> tuple[str | None, str | None, int]:
        values = sorted(str(by_id[key]["timestamp_utc"]) for key, value in assignments.items() if value == split)
        return (values[0], values[-1], len(values)) if values else (None, None, 0)

    groups = {split: {key for key, value in assignments.items() if value == split} for split in {"TRAIN", "VALIDATION", "OOS", "FORWARD"}}
    overlap_count = sum(len(groups[left] & groups[right]) for left in groups for right in groups if left < right)
    split_config = config or SplitConfig()
    train_start, train_end_actual, train_count = bounds("TRAIN")
    validation_start, validation_end_actual, validation_count = bounds("VALIDATION")
    oos_start, oos_end, oos_count = bounds("OOS")
    forward_start, forward_end, forward_count = bounds("FORWARD")
    return {
        "schema": "trading_agent_phase2_split_manifest_v1",
        "dataset_fingerprint": dataset_fingerprint,
        "feature_set_version": feature_set_version,
        "split_version": split_config.version,
        "split_config": split_config.to_dict(),
        "train_start": train_start,
        "train_end": train_end_actual,
        "train_count": train_count,
        "validation_start": validation_start,
        "validation_end": validation_end_actual,
        "validation_count": validation_count,
        "oos_start": oos_start,
        "oos_end": oos_end,
        "oos_count": oos_count,
        "forward_start": forward_start,
        "forward_end": forward_end,
        "forward_count": forward_count,
        "forward_status": "RESERVED_NOT_USED" if forward_count == 0 else "REAL_DATA_ASSIGNED",
        "canonical_overlap_count": overlap_count,
        "split_fingerprint": split_fingerprint(assignments),
        "row_count": len(by_id),
        "chronological": True,
        "timezone": "UTC",
    }


create_temporal_splits = build_temporal_splits

__all__ = ["SplitConfig", "SplitError", "build_split_manifest", "build_temporal_splits", "create_temporal_splits"]
