"""Kết nối một chiều từ canonical event tới intelligence Phase 2 frozen."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from ...features.fingerprint import fingerprint
from ...features.normalization import TrainOnlyPreprocessor
from ...features.registry import FEATURE_ALLOWLIST, extract_feature_fields
from ...regime.config import RegimeConfig
from ...regime.engine import RegimeEngine
from ...scoring.predict import ScoreRecord, score_opportunity
from ...scoring.train import ModelBundle
from ...similarity.index import HistoricalSimilarityIndex
from ...similarity.models import SimilarityConfig, SimilarityResult
from ..bundle import BundleMismatchError, ShadowBundle, validate_bundle
from ..ingestion.canonicalize import CanonicalForwardEvent, canonicalize_event
from ..models import FeatureSnapshot, TelemetryEvent, utc_now


def build_scoring_row(event: TelemetryEvent | CanonicalForwardEvent) -> dict[str, Any]:
    """Đưa event về shape Phase 2 mà không đưa labels/outcomes vào."""

    telemetry = event.event if isinstance(event, CanonicalForwardEvent) else event
    forward_id = event.forward_opportunity_id if isinstance(event, CanonicalForwardEvent) else ""
    row: dict[str, Any] = {
        "canonical_opportunity_id": forward_id,
        "timestamp_utc": telemetry.event_timestamp_utc,
        "symbol": telemetry.symbol,
        "timeframe": telemetry.timeframe,
        "side": telemetry.side,
        "features": telemetry.features,
    }
    return row


def _missing(value: Any) -> bool:
    return value is None or value == ""


def build_feature_snapshot(
    event: TelemetryEvent | CanonicalForwardEvent,
    bundle: ShadowBundle,
    *,
    preprocessor: TrainOnlyPreprocessor | None = None,
    created_at_utc: str | None = None,
) -> FeatureSnapshot:
    """Snapshot value/vector/OOD trước khi bất kỳ outcome nào được resolver."""

    row = build_scoring_row(event)
    values = extract_feature_fields(row)
    missingness = {name: _missing(values.get(name)) for name in sorted(FEATURE_ALLOWLIST)}
    processor = preprocessor
    payload = bundle.config_json.get("model_bundle")
    if processor is None:
        # Manifest review giữ preprocessor riêng để snapshot vẫn deterministic dù model binary ở artifact ngoài.
        preprocessor_payload = bundle.config_json.get("preprocessor", {})
        if isinstance(payload, Mapping) and payload.get("preprocessor"):
            preprocessor_payload = payload.get("preprocessor", {})
        if isinstance(preprocessor_payload, Mapping) and preprocessor_payload:
            processor = TrainOnlyPreprocessor.from_dict(preprocessor_payload)
    if processor is not None:
        vector = processor.transform_one(row)
        output_names = tuple(processor.output_names)
        ood_inputs = processor.ood_check(row)
    else:
        vector = ()
        output_names = ()
        ood_inputs = {"is_ood": True, "reasons": ["MODEL_PREPROCESSOR_UNAVAILABLE"], "z_limit": None}
    material = {
        "version": "phase3-feature-snapshot/1",
        "feature_set_version": bundle.feature_set_version,
        "feature_timestamp_utc": (event.event.event_timestamp_utc if isinstance(event, CanonicalForwardEvent) else event.event_timestamp_utc),
        "feature_values": values,
        "missingness": missingness,
        "ood_inputs": ood_inputs,
        "vector": vector,
        "output_names": output_names,
    }
    return FeatureSnapshot(
        feature_set_version=bundle.feature_set_version,
        feature_timestamp_utc=material["feature_timestamp_utc"],
        feature_fingerprint=fingerprint(material),
        feature_values=values,
        missingness=missingness,
        ood_inputs=ood_inputs,
        created_at_utc=created_at_utc or utc_now(),
        vector=tuple(float(value) for value in vector),
        output_names=output_names,
    )


@dataclass(frozen=True)
class BridgeScore:
    """Output score chỉ là evidence, không có execution command."""

    regime: str
    regime_confidence: str
    similarity_status: str
    similarity_sample_size: int
    similarity_summary: Mapping[str, Any]
    probability_plus1_before_minus1: float | None
    expected_return_24bar_r: float | None
    confidence: str
    ood_status: str
    ood_score: float | None
    score_status: str
    abstention_reason: str | None
    code_sha: str
    model_version: str
    feature_set_version: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["similarity_summary"] = dict(self.similarity_summary)
        return value


def _similarity_summary(value: SimilarityResult | None) -> dict[str, Any]:
    if value is None:
        return {"opinion_status": "NO_OPINION", "reason": "HISTORICAL_INDEX_UNAVAILABLE", "neighbors": []}
    return value.to_dict()


def _ood_score(processor: TrainOnlyPreprocessor | None, row: Mapping[str, Any]) -> float | None:
    if processor is None:
        return None
    maximum = 0.0
    found = False
    fields = extract_feature_fields(row)
    for name, stats in processor.numeric_stats.items():
        value = fields.get(name)
        try:
            number = float(value)
            mean = float(stats.get("mean", 0.0))
            std = abs(float(stats.get("std", 1.0))) or 1.0
        except (TypeError, ValueError):
            continue
        maximum = max(maximum, abs((number - mean) / std))
        found = True
    return maximum if found else 0.0


class Phase2ScoringBridge:
    """Frozen adapter dùng lại ModelBundle/Regime/Similarity Phase 2."""

    def __init__(
        self,
        bundle: ShadowBundle,
        *,
        model_bundle: ModelBundle | None = None,
        similarity_index: HistoricalSimilarityIndex | None = None,
        regime_engine: RegimeEngine | None = None,
    ) -> None:
        self.bundle = validate_bundle(bundle)
        payload = self.bundle.config_json.get("model_bundle")
        if model_bundle is None and isinstance(payload, Mapping) and payload:
            model_bundle = ModelBundle.from_dict(payload)
        expected_model_fingerprint = self.bundle.config_json.get("model_payload_fingerprint")
        if model_bundle is not None and expected_model_fingerprint:
            actual_model_fingerprint = fingerprint(model_bundle.to_dict())
            if actual_model_fingerprint != str(expected_model_fingerprint):
                raise BundleMismatchError("supplied model bundle does not match frozen bundle")
        self.model_bundle = model_bundle
        self.similarity_index = similarity_index
        if regime_engine is not None:
            self.regime_engine = regime_engine
        else:
            regime_payload = self.bundle.config_json.get("regime_config", {})
            self.regime_engine = RegimeEngine(RegimeConfig.from_dict(regime_payload)) if isinstance(regime_payload, Mapping) else None

    def _similarity_config(self) -> SimilarityConfig:
        payload = self.bundle.config_json.get("similarity_config", {})
        return SimilarityConfig.from_dict(payload) if isinstance(payload, Mapping) else SimilarityConfig()

    def score_event(
        self,
        event: TelemetryEvent | CanonicalForwardEvent,
        *,
        scored_at_utc: str | None = None,
    ) -> tuple[FeatureSnapshot, BridgeScore]:
        canonical = event if isinstance(event, CanonicalForwardEvent) else canonicalize_event(event)
        row = build_scoring_row(canonical)
        processor = self.model_bundle.preprocessor if self.model_bundle is not None else None
        snapshot = build_feature_snapshot(canonical, self.bundle, preprocessor=processor, created_at_utc=scored_at_utc)
        regime = self.regime_engine.assign(row) if self.regime_engine is not None else None
        similarity = None
        if self.similarity_index is not None and snapshot.vector:
            similarity = self.similarity_index.query(
                row,
                query_vector=snapshot.vector,
                as_of=canonical.event.event_timestamp_utc,
                config=self._similarity_config(),
            )
        if self.model_bundle is None:
            score = ScoreRecord(
                canonical.forward_opportunity_id, None, None,
                regime.composite_regime if regime else "UNKNOWN",
                similarity.neighbor_count if similarity else 0,
                "NO_OPINION", "LOW", "NO_OPINION", "MODEL_UNAVAILABLE",
                self.bundle.model_version, self.bundle.feature_set_version,
            )
        else:
            score = score_opportunity(row, self.model_bundle, regime=regime, similarity=similarity)
        if self.similarity_index is None and score.score_status == "OK":
            # Thiếu historical index thì không được phát opinion dù model còn sẵn sàng.
            score = ScoreRecord(
                canonical.forward_opportunity_id,
                None,
                None,
                score.regime,
                score.similarity_sample_size,
                "NO_OPINION",
                "LOW",
                "NO_OPINION",
                "HISTORICAL_INDEX_UNAVAILABLE",
                score.model_version,
                score.feature_version,
            )
        ood = snapshot.ood_inputs
        ood_status = "OUT_OF_DISTRIBUTION" if ood.get("is_ood") else "IN_DISTRIBUTION"
        if "MODEL_PREPROCESSOR_UNAVAILABLE" in ood.get("reasons", ()):
            ood_status = "UNKNOWN"
        similarity_status = similarity.opinion_status if similarity else "NO_OPINION"
        result = BridgeScore(
            regime=score.regime,
            regime_confidence=regime.confidence if regime else "LOW",
            similarity_status=similarity_status,
            similarity_sample_size=score.similarity_sample_size,
            similarity_summary=_similarity_summary(similarity),
            probability_plus1_before_minus1=score.p_plus_1r_before_minus_1r,
            expected_return_24bar_r=score.expected_r_24bar,
            confidence=score.model_confidence,
            ood_status=ood_status,
            ood_score=_ood_score(processor, row),
            score_status=score.score_status,
            abstention_reason=None if score.score_status == "OK" else score.reason,
            code_sha=self.bundle.phase2_base_sha,
            model_version=score.model_version,
            feature_set_version=score.feature_version,
        )
        return snapshot, result


__all__ = ["BridgeScore", "Phase2ScoringBridge", "build_feature_snapshot", "build_scoring_row"]
