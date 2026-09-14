"""Data models for Historical Similarity V1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class SimilarityConfig:
    version: str = "similarity/1"
    top_k: int = 20
    min_neighbors: int = 5
    min_feature_overlap: int = 3
    same_symbol: bool = True
    same_timeframe: bool = True
    side_mode: str = "same"
    regime_mode: str = "same_composite"
    require_outcome_available: bool = True
    max_distance: float | None = None

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError("similarity top_k must be positive")
        if self.min_neighbors < 1:
            raise ValueError("similarity min_neighbors must be positive")
        if self.min_feature_overlap < 1:
            raise ValueError("similarity min_feature_overlap must be positive")
        if self.side_mode not in {"same", "any"}:
            raise ValueError("similarity side_mode must be 'same' or 'any'")
        if self.regime_mode not in {"same_composite", "any", "none"}:
            raise ValueError("similarity regime_mode must be same_composite, any or none")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SimilarityConfig":
        fields = {key: payload[key] for key in cls.__dataclass_fields__ if key in payload}
        return cls(**fields)


@dataclass(frozen=True)
class Neighbor:
    canonical_opportunity_id: str
    timestamp_utc: str
    distance: float
    regime: str
    side: str
    historical_outcome: Mapping[str, Any] | None
    rank: int
    feature_overlap: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimilarityResult:
    query_opportunity_id: str
    query_timestamp_utc: str
    neighbors: tuple[Neighbor, ...]
    neighbor_count: int
    effective_sample_size: float
    historical_win_probability: float | None
    historical_expected_r: float | None
    confidence: str
    opinion_status: str
    reason: str
    filter_coverage: Mapping[str, int] = field(default_factory=dict)
    similarity_version: str = "similarity/1"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["neighbors"] = [item.to_dict() for item in self.neighbors]
        return value


__all__ = ["Neighbor", "SimilarityConfig", "SimilarityResult"]
