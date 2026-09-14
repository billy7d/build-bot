"""Regime validation that deliberately excludes all outcome columns."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from ..features.fingerprint import fingerprint_records
from ..features.registry import extract_feature_fields
from .models import RegimeAssignment


def _assignment(value: RegimeAssignment | Mapping[str, Any]) -> dict[str, Any]:
    return value.to_dict() if isinstance(value, RegimeAssignment) else dict(value)


def _source_regime(row: Mapping[str, Any]) -> str | None:
    fields = extract_feature_fields(row)
    value = fields.get("source_regime")
    return str(value).strip().upper() if value not in (None, "") else None


def validate_regimes(
    rows: Iterable[Mapping[str, Any]],
    assignments: Mapping[str, RegimeAssignment | Mapping[str, Any]],
) -> dict[str, Any]:
    records = sorted(rows, key=lambda row: (str(row.get("timestamp_utc", "")), str(row.get("canonical_opportunity_id", ""))))
    distribution = Counter()
    confusion = Counter()
    by_side: dict[str, Counter[str]] = defaultdict(Counter)
    by_timeframe: dict[str, Counter[str]] = defaultdict(Counter)
    by_period: dict[str, Counter[str]] = defaultdict(Counter)
    source_count = 0
    agreement = 0
    for row in records:
        identifier = str(row.get("canonical_opportunity_id", ""))
        item = _assignment(assignments[identifier]) if identifier in assignments else {"composite_regime": "UNKNOWN"}
        composite = str(item.get("composite_regime", "UNKNOWN"))
        distribution[composite] += 1
        side = str(row.get("side") or "UNKNOWN")
        timeframe = str(row.get("timeframe") or "UNKNOWN")
        period = str(row.get("timestamp_utc", "UNKNOWN"))[:7]
        by_side[side][composite] += 1
        by_timeframe[timeframe][composite] += 1
        by_period[period][composite] += 1
        source = _source_regime(row)
        if source is not None:
            source_count += 1
            source_composite = source
            if source in {"TRENDING", "TREND"}:
                source_composite = "TREND"
            elif source in {"RANGE", "RANGING", "NEUTRAL"}:
                source_composite = "RANGE"
            predicted_prefix = "TREND" if composite.startswith("TREND_") else "RANGE" if composite.startswith("RANGE_") else composite
            if source_composite == predicted_prefix or source == composite:
                agreement += 1
            confusion[(source, composite)] += 1

    transitions = 0
    previous: tuple[str, str, str] | None = None
    for row in records:
        identifier = str(row.get("canonical_opportunity_id", ""))
        current = str(_assignment(assignments[identifier]).get("composite_regime", "UNKNOWN")) if identifier in assignments else "UNKNOWN"
        key = (str(row.get("symbol") or "UNKNOWN"), str(row.get("timeframe") or "UNKNOWN"), current)
        if previous is not None and previous[:2] == key[:2] and previous[2] != key[2]:
            transitions += 1
        previous = key

    return {
        "schema": "trading_agent_phase2_regime_validation_v1",
        "row_count": len(records),
        "coverage": round(sum(_assignment(assignments[item["canonical_opportunity_id"]]).get("composite_regime") != "UNKNOWN" for item in records if item["canonical_opportunity_id"] in assignments) / len(records), 8) if records else 0.0,
        "source_reported_coverage": round(source_count / len(records), 8) if records else 0.0,
        "agreement_rate": round(agreement / source_count, 8) if source_count else None,
        "confusion_matrix": {f"{left}->{right}": count for (left, right), count in sorted(confusion.items())},
        "distribution": dict(sorted(distribution.items())),
        "transition_frequency": transitions,
        "by_side": {key: dict(sorted(value.items())) for key, value in sorted(by_side.items())},
        "by_timeframe": {key: dict(sorted(value.items())) for key, value in sorted(by_timeframe.items())},
        "by_calendar_period": {key: dict(sorted(value.items())) for key, value in sorted(by_period.items())},
        "outcome_dependency": False,
        "regime_fingerprint": fingerprint_records([_assignment(value) for value in assignments.values()], key="canonical_opportunity_id"),
    }


__all__ = ["validate_regimes"]
