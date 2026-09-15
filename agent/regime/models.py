"""Typed output models for Regime Engine V1."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RegimeAssignment:
    canonical_opportunity_id: str
    trend_state: str
    volatility_state: str
    liquidity_state: str
    composite_regime: str
    confidence: str
    reason: str
    source_reported_regime: str | None = None
    regime_version: str = "regime/1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["RegimeAssignment"]
