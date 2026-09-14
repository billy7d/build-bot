"""Prediction objects constrained to offline/shadow output only."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from ..regime.models import RegimeAssignment
from ..similarity.models import SimilarityResult
from .baseline import prior_prediction
from .train import ModelBundle


@dataclass(frozen=True)
class ScoreRecord:
    canonical_opportunity_id: str
    p_plus_1r_before_minus_1r: float | None
    expected_r_24bar: float | None
    regime: str
    similarity_sample_size: int
    model_confidence: str
    data_quality: str
    score_status: str
    reason: str
    model_version: str
    feature_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_FORBIDDEN_OUTPUT_TERMS = (
    "order", "position", "lot", "volume", "stop_loss", "take_profit", "pyramid",
    "execution", "mt5", "buy", "sell", "open", "close", "modify", "risk_management",
)


def assert_no_execution_action(payload: Mapping[str, Any]) -> None:
    """Fail if a score payload grows an execution command field."""

    bad = [key for key in payload if any(term in str(key).lower() for term in _FORBIDDEN_OUTPUT_TERMS)]
    if bad:
        raise AssertionError(f"execution action leaked into shadow score: {sorted(bad)}")


def _regime_value(regime: RegimeAssignment | Mapping[str, Any] | str | None) -> tuple[str, str]:
    if isinstance(regime, RegimeAssignment):
        return regime.composite_regime, regime.confidence
    if isinstance(regime, Mapping):
        return str(regime.get("composite_regime", "UNKNOWN")), str(regime.get("confidence", "LOW"))
    return str(regime or "UNKNOWN"), "LOW"


def _similarity_size(similarity: SimilarityResult | Mapping[str, Any] | None) -> int:
    if isinstance(similarity, SimilarityResult):
        return int(similarity.neighbor_count)
    if isinstance(similarity, Mapping):
        return int(similarity.get("neighbor_count", len(similarity.get("neighbors", ()))) or 0)
    return 0


def _similarity_status(similarity: SimilarityResult | Mapping[str, Any] | None) -> str | None:
    if isinstance(similarity, SimilarityResult):
        return similarity.opinion_status
    if isinstance(similarity, Mapping):
        value = similarity.get("opinion_status")
        return str(value) if value is not None else None
    return None


def score_opportunity(
    row: Mapping[str, Any],
    bundle: ModelBundle,
    *,
    regime: RegimeAssignment | Mapping[str, Any] | str | None = None,
    similarity: SimilarityResult | Mapping[str, Any] | None = None,
) -> ScoreRecord:
    identifier = str(row.get("canonical_opportunity_id", ""))
    regime_name, regime_confidence = _regime_value(regime)
    similarity_size = _similarity_size(similarity)
    similarity_status = _similarity_status(similarity)
    quality_check = bundle.preprocessor.ood_check(row)
    completeness = bundle.preprocessor.feature_completeness(row)
    if bundle.status != "READY" or bundle.logistic is None and bundle.ridge is None:
        result = ScoreRecord(identifier, None, None, regime_name, similarity_size, "NO_OPINION", "LOW", "NO_OPINION", "INSUFFICIENT_DATA", bundle.model_version, bundle.feature_set_version)
        assert_no_execution_action(result.to_dict())
        return result
    if str(row.get("feature_status", "")).upper() == "CONFLICT":
        result = ScoreRecord(identifier, None, None, regime_name, similarity_size, "NO_OPINION", "LOW", "NO_OPINION", "FEATURE_CONFLICT", bundle.model_version, bundle.feature_set_version)
        assert_no_execution_action(result.to_dict())
        return result
    if quality_check["is_ood"]:
        result = ScoreRecord(identifier, None, None, regime_name, similarity_size, "NO_OPINION", "LOW", "NO_OPINION", "OUT_OF_DISTRIBUTION", bundle.model_version, bundle.feature_set_version)
        assert_no_execution_action(result.to_dict())
        return result
    if completeness < 0.25:
        result = ScoreRecord(identifier, None, None, regime_name, similarity_size, "NO_OPINION", "LOW", "NO_OPINION", "INSUFFICIENT_FEATURES", bundle.model_version, bundle.feature_set_version)
        assert_no_execution_action(result.to_dict())
        return result
    vector = bundle.preprocessor.transform_one(row)
    probability = bundle.calibrator.transform(bundle.logistic.predict_proba(vector)) if bundle.logistic else None
    expected = bundle.ridge.predict(vector) if bundle.ridge else None
    calibration_supported = bool(bundle.calibrator.fit_ids)
    if completeness >= 0.75 and regime_confidence == "HIGH" and similarity_status == "OK" and similarity_size >= 10 and calibration_supported:
        confidence = "HIGH"
        quality = "HIGH"
    elif completeness >= 0.5 and similarity_status == "OK" and similarity_size >= 3:
        confidence = "MEDIUM"
        quality = "MEDIUM"
    else:
        confidence = "LOW"
        quality = "LOW"
    result = ScoreRecord(identifier, probability, expected, regime_name, similarity_size, confidence, quality, "OK", "SUPPORTED", bundle.model_version, bundle.feature_set_version)
    assert_no_execution_action(result.to_dict())
    return result


def predict_rows(
    rows: Iterable[Mapping[str, Any]],
    bundle: ModelBundle,
    *,
    regimes: Mapping[str, Any] | None = None,
    similarities: Mapping[str, SimilarityResult | Mapping[str, Any]] | None = None,
) -> dict[str, ScoreRecord]:
    regimes = regimes or {}
    similarities = similarities or {}
    return {
        str(row["canonical_opportunity_id"]): score_opportunity(
            row, bundle, regime=regimes.get(str(row["canonical_opportunity_id"])), similarity=similarities.get(str(row["canonical_opportunity_id"]))
        )
        for row in rows
    }


__all__ = ["ScoreRecord", "assert_no_execution_action", "predict_rows", "score_opportunity"]
