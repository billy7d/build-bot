"""Ingestion read-only cho telemetry Phase 3."""

from .adapter import ParsedTelemetryLine, ReadOnlyTelemetryAdapter
from .canonicalize import (
    CanonicalForwardEvent,
    canonicalize_event,
    canonicalize_opportunity,
    derive_canonical_forward_ids,
    derive_forward_ids,
)
from .file_tail import FileTailBatch, FileTailRecord, TelemetryFileTailer
from .opportunity import (
    CANONICALIZER_FINGERPRINT,
    CanonicalOpportunity,
    OpportunityObservation,
    OpportunityValidationError,
    canonicalize_observation,
    validate_opportunity_payload,
)
from .validation import TelemetryValidationError, validate_telemetry_payload

__all__ = [
    "CanonicalForwardEvent",
    "CanonicalOpportunity",
    "CANONICALIZER_FINGERPRINT",
    "FileTailBatch",
    "FileTailRecord",
    "ParsedTelemetryLine",
    "ReadOnlyTelemetryAdapter",
    "TelemetryFileTailer",
    "TelemetryValidationError",
    "OpportunityObservation",
    "OpportunityValidationError",
    "canonicalize_observation",
    "canonicalize_event",
    "canonicalize_opportunity",
    "derive_canonical_forward_ids",
    "derive_forward_ids",
    "validate_opportunity_payload",
    "validate_telemetry_payload",
]
