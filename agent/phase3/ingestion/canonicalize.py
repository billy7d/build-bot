"""Canonical identity cho forward events/opportunities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ...features.fingerprint import canonical_json
from ..models import TelemetryEvent, sha256_bytes, sha256_json


@dataclass(frozen=True)
class CanonicalForwardEvent:
    """Event canonicalized nhưng chưa score và chưa có outcome."""

    forward_event_id: str
    forward_opportunity_id: str
    event: TelemetryEvent

    @property
    def feature_values(self) -> dict[str, Any]:
        return self.event.features

    def to_dict(self) -> dict[str, Any]:
        return {
            "forward_event_id": self.forward_event_id,
            "forward_opportunity_id": self.forward_opportunity_id,
            "event": self.event.to_dict(),
        }


def derive_forward_ids(event: TelemetryEvent) -> tuple[str, str]:
    """Derive deterministic IDs, không dùng random UUID làm identity."""

    material = {
        "source": event.source,
        "source_event_id": event.source_event_id,
        "symbol": event.symbol,
        "timeframe": event.timeframe,
        "event_timestamp_utc": event.event_timestamp_utc,
        "side": event.side,
        "candidate_type": event.candidate_type,
    }
    digest = sha256_bytes(canonical_json(material).encode("utf-8"))
    return f"p3-event-{digest}", f"p3-opportunity-{digest}"


def canonicalize_event(event: TelemetryEvent) -> CanonicalForwardEvent:
    forward_event_id, forward_opportunity_id = derive_forward_ids(event)
    return CanonicalForwardEvent(forward_event_id, forward_opportunity_id, event)


__all__ = ["CanonicalForwardEvent", "canonicalize_event", "derive_forward_ids"]
