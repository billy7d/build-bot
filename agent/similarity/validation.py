"""Validation helpers for temporal and feature-only similarity."""

from __future__ import annotations

from typing import Any, Mapping

from ..data.normalization.timestamps import timestamp_to_datetime
from .models import SimilarityResult


def validate_similarity_results(results: Mapping[str, SimilarityResult]) -> dict[str, Any]:
    violations: list[dict[str, str]] = []
    self_matches: list[str] = []
    for query_id, result in sorted(results.items()):
        for neighbor in result.neighbors:
            if neighbor.canonical_opportunity_id == query_id:
                self_matches.append(query_id)
            if not timestamp_to_datetime(neighbor.timestamp_utc) < timestamp_to_datetime(result.query_timestamp_utc):
                violations.append({
                    "query_opportunity_id": query_id,
                    "neighbor_opportunity_id": neighbor.canonical_opportunity_id,
                    "neighbor_timestamp_utc": neighbor.timestamp_utc,
                    "query_timestamp_utc": result.query_timestamp_utc,
                })
    return {
        "query_count": len(results),
        "temporal_leakage_count": len(violations),
        "self_match_count": len(self_matches),
        "violations": violations,
        "passed": not violations and not self_matches,
    }


__all__ = ["validate_similarity_results"]
