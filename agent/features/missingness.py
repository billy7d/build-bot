"""Missingness accounting for the Phase 2 Feature Store."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from .registry import FEATURE_ALLOWLIST, NUMERIC_FEATURES, extract_feature_fields


def _present(value: Any) -> bool:
    return value is not None and value != ""


def missingness_report(
    rows: Iterable[Mapping[str, Any]],
    *,
    feature_names: Iterable[str] | None = None,
    split_by: Mapping[str, str] | None = None,
    regime_by: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    records = list(rows)
    names = tuple(feature_names or sorted(FEATURE_ALLOWLIST))
    totals = {name: 0 for name in names}
    missing = {name: 0 for name in names}
    by_split: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "missing": Counter()})
    by_regime: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "missing": Counter()})
    for row in records:
        row_id = str(row.get("canonical_opportunity_id", ""))
        fields = extract_feature_fields(row)
        for name in names:
            totals[name] += 1
            if not _present(fields.get(name)):
                missing[name] += 1
        if split_by is not None:
            split = str(split_by.get(row_id, "UNKNOWN"))
            by_split[split]["count"] += 1
            for name in names:
                if not _present(fields.get(name)):
                    by_split[split]["missing"][name] += 1
        if regime_by is not None:
            regime = str(regime_by.get(row_id, "UNKNOWN"))
            by_regime[regime]["count"] += 1
            for name in names:
                if not _present(fields.get(name)):
                    by_regime[regime]["missing"][name] += 1

    def finalize(groups: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for group, payload in sorted(groups.items()):
            count = int(payload["count"])
            group_missing = payload["missing"]
            result[group] = {
                "count": count,
                "missing_rate": {
                    name: round(group_missing.get(name, 0) / count, 8) if count else None
                    for name in names
                },
            }
        return result

    count = len(records)
    return {
        "row_count": count,
        "feature_names": list(names),
        "missing_count": missing,
        "missing_rate": {
            name: round(missing[name] / count, 8) if count else None for name in names
        },
        "coverage_rate": {
            name: round((count - missing[name]) / count, 8) if count else 0.0 for name in names
        },
        "by_split": finalize(by_split),
        "by_regime": finalize(by_regime),
        "numeric_features": list(NUMERIC_FEATURES),
        "missing_policy": "preserve missingness; train-only imputation with explicit indicators",
    }


__all__ = ["missingness_report"]
