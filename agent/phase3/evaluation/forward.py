"""Facade đánh giá forward từ các record đã snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .metrics import evaluate_forward_records


@dataclass(frozen=True)
class ForwardEvaluation:
    payload: Mapping[str, Any]

    @property
    def sample_count(self) -> int:
        return int(self.payload.get("resolved_sample_count", 0))

    @property
    def collection_status(self) -> str:
        return str(self.payload.get("forward_collection_status", "NO_DATA"))

    @property
    def edge_status(self) -> str:
        return str(self.payload.get("forward_predictive_edge_status", "INSUFFICIENT_DATA"))

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


class ForwardEvaluator:
    def __init__(self, **kwargs: Any):
        self.kwargs = dict(kwargs)

    def evaluate(self, records: Iterable[Mapping[str, Any]]) -> ForwardEvaluation:
        return ForwardEvaluation(evaluate_forward_records(records, **self.kwargs))


__all__ = ["ForwardEvaluation", "ForwardEvaluator"]
