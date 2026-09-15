"""Deterministic, train-only Feature Store for Trading Agent Phase 2."""

from .builder import build_canonical_opportunities, build_canonical_view, load_canonical_view, persist_canonical_view
from .fingerprint import fingerprint_records
from .normalization import TrainOnlyPreprocessor
from .registry import (
    FEATURE_ALLOWLIST,
    FEATURE_SET_VERSION,
    LABEL_ALLOWLIST,
    FeatureLeakageError,
    FeatureSchemaError,
)
from .splits import SplitConfig, build_temporal_splits, build_split_manifest

__all__ = [
    "FEATURE_ALLOWLIST",
    "FEATURE_SET_VERSION",
    "LABEL_ALLOWLIST",
    "FeatureLeakageError",
    "FeatureSchemaError",
    "TrainOnlyPreprocessor",
    "SplitConfig",
    "build_canonical_view",
    "build_canonical_opportunities",
    "load_canonical_view",
    "persist_canonical_view",
    "build_temporal_splits",
    "build_split_manifest",
    "fingerprint_records",
]
