"""Hard-gate replay parity giữa offline Phase 2 và live adapter."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from ..ingestion.canonicalize import CanonicalForwardEvent, canonicalize_event
from ..models import sha256_json
from ..models import TelemetryEvent
from .bridge import BridgeScore, Phase2ScoringBridge


@dataclass(frozen=True)
class ParityResult:
    passed: bool
    event_count: int
    feature_parity: bool
    regime_identical: bool
    similarity_deterministic: bool
    probability_within_tolerance: bool
    expected_return_within_tolerance: bool
    confidence_identical: bool
    status_identical: bool
    differences: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "event_count": self.event_count,
            "feature_parity": self.feature_parity,
            "regime_identical": self.regime_identical,
            "similarity_deterministic": self.similarity_deterministic,
            "probability_within_tolerance": self.probability_within_tolerance,
            "expected_return_within_tolerance": self.expected_return_within_tolerance,
            "confidence_identical": self.confidence_identical,
            "status_identical": self.status_identical,
            "differences": [dict(item) for item in self.differences],
        }


def _value(score: BridgeScore | Mapping[str, Any], name: str) -> Any:
    if isinstance(score, BridgeScore):
        return getattr(score, name)
    return score.get(name)


def _close(left: Any, right: Any, tolerance: float) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    except (TypeError, ValueError):
        return left == right


def compare_score(
    expected: BridgeScore | Mapping[str, Any],
    actual: BridgeScore | Mapping[str, Any],
    *,
    tolerance: float = 1e-8,
) -> dict[str, Any]:
    checks = {
        "regime_identical": _value(expected, "regime") == _value(actual, "regime"),
        "probability_within_tolerance": _close(_value(expected, "probability_plus1_before_minus1"), _value(actual, "probability_plus1_before_minus1"), tolerance),
        "expected_return_within_tolerance": _close(_value(expected, "expected_return_24bar_r"), _value(actual, "expected_return_24bar_r"), tolerance),
        "confidence_identical": _value(expected, "confidence") == _value(actual, "confidence"),
        "status_identical": _value(expected, "score_status") == _value(actual, "score_status"),
        "similarity_deterministic": (
            _value(expected, "similarity_status") == _value(actual, "similarity_status")
            and _value(expected, "similarity_sample_size") == _value(actual, "similarity_sample_size")
            and (
                _value(expected, "similarity_summary") is None
                or sha256_json(_value(expected, "similarity_summary")) == sha256_json(_value(actual, "similarity_summary"))
            )
        ),
    }
    return {**checks, "passed": all(checks.values())}


def run_replay_parity(
    events: Iterable[TelemetryEvent | CanonicalForwardEvent],
    offline_scores: Mapping[str, BridgeScore | Mapping[str, Any]] | Callable[[TelemetryEvent | CanonicalForwardEvent], BridgeScore | Mapping[str, Any]],
    bridge: Phase2ScoringBridge,
    *,
    tolerance: float = 1e-8,
) -> ParityResult:
    """Replay luôn gắn mode REPLAY ở caller và không góp vào forward metrics."""

    differences: list[Mapping[str, Any]] = []
    count = 0
    feature_parity = True
    for event in events:
        count += 1
        canonical = event if isinstance(event, CanonicalForwardEvent) else canonicalize_event(event)
        snapshot, actual = bridge.score_event(canonical)
        expected = offline_scores(canonical) if callable(offline_scores) else offline_scores.get(canonical.event.source_event_id)
        if expected is None:
            feature_parity = False
            differences.append({"source_event_id": canonical.event.source_event_id, "reason": "MISSING_OFFLINE_SCORE"})
            continue
        comparison = compare_score(expected, actual, tolerance=tolerance)
        expected_feature = expected.get("feature_snapshot") if isinstance(expected, Mapping) else None
        if expected_feature is None and isinstance(expected, Mapping):
            expected_feature = expected.get("feature_fingerprint") or expected.get("feature_snapshot_fingerprint")
        if isinstance(expected_feature, Mapping):
            expected_fingerprint = expected_feature.get("feature_fingerprint") or expected_feature.get("feature_snapshot_fingerprint")
            comparison["feature_parity"] = expected_fingerprint == snapshot.feature_fingerprint
        elif isinstance(expected_feature, str):
            comparison["feature_parity"] = expected_feature == snapshot.feature_fingerprint
        else:
            comparison["feature_parity"] = True
        comparison["passed"] = bool(comparison["passed"] and comparison["feature_parity"])
        if not comparison["passed"]:
            feature_parity = False
            differences.append({"source_event_id": canonical.event.source_event_id, **comparison})
    regime = all(item.get("regime_identical", False) for item in differences) if differences else True
    similarity = all(item.get("similarity_deterministic", False) for item in differences) if differences else True
    probability = all(item.get("probability_within_tolerance", False) for item in differences) if differences else True
    expected_r = all(item.get("expected_return_within_tolerance", False) for item in differences) if differences else True
    confidence = all(item.get("confidence_identical", False) for item in differences) if differences else True
    status = all(item.get("status_identical", False) for item in differences) if differences else True
    passed = bool(count) and not differences
    return ParityResult(passed, count, feature_parity, regime, similarity, probability, expected_r, confidence, status, tuple(differences))


__all__ = ["ParityResult", "compare_score", "run_replay_parity"]
