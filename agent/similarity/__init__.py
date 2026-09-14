"""Historical, feature-only similarity engine with temporal guardrails."""

from .distance import distance_with_overlap, standardized_euclidean
from .index import HistoricalSimilarityIndex, evaluate_temporal_similarity
from .models import Neighbor, SimilarityConfig, SimilarityResult
from .validation import validate_similarity_results

__all__ = [
    "HistoricalSimilarityIndex",
    "Neighbor",
    "SimilarityConfig",
    "SimilarityResult",
    "distance_with_overlap",
    "evaluate_temporal_similarity",
    "standardized_euclidean",
    "validate_similarity_results",
]
