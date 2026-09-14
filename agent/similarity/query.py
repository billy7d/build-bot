"""Functional API for historical similarity queries."""

from __future__ import annotations

from typing import Any, Mapping

from .index import HistoricalSimilarityIndex
from .models import SimilarityConfig, SimilarityResult


def query_historical_similarity(
    index: HistoricalSimilarityIndex,
    query_row: Mapping[str, Any],
    *,
    query_vector: Any = None,
    as_of: str | None = None,
    config: SimilarityConfig | None = None,
) -> SimilarityResult:
    return index.query(query_row, query_vector=query_vector, as_of=as_of, config=config)


__all__ = ["query_historical_similarity"]
