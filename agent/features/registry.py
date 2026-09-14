"""Versioned Feature Store contract and closed-world feature allowlist.

The Phase 1 database deliberately contains both event-time fields and outcome
fields.  This module is the single gate between those two namespaces.  A new
column is not a feature until it is explicitly registered here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


FEATURE_SET_VERSION = "feature-store/1"
FEATURE_SCHEMA_VERSION = "TA-FEATURE-V1"


class FeatureLeakageError(ValueError):
    """Raised when an outcome/future field is offered as a feature."""


class FeatureSchemaError(ValueError):
    """Raised when an unknown field is offered to the closed-world schema."""


@dataclass(frozen=True)
class FeatureDefinition:
    feature_name: str
    feature_version: str
    dtype: str
    unit: str
    source: str
    source_field: str
    calculation_method: str
    available_at: str
    lookback: str
    missing_policy: str
    normalization: str
    mql5_semantics: str


_NUMERIC_DEFINITIONS = (
    ("rsi", "entry_rsi|shadow_entry_rsi", "0..100", "event-time source field", "none"),
    ("atr_percent", "entry_atr_pct", "%", "event-time source field", "none"),
    ("spread_r", "entry_spread_r", "R", "event-time source field", "none"),
    ("return_std_20", "entry_return_std_20", "return units", "event-time source field", "20 bars"),
    ("return_std_rank", "entry_return_std_rank", "percentile", "event-time source field", "20 bars"),
    ("price_std_20", "entry_price_std_20", "price units", "event-time source field", "20 bars"),
    ("price_std_100", "entry_price_std_100", "price units", "event-time source field", "100 bars"),
    ("price_std_pct_20", "entry_price_std_pct_20", "%", "event-time source field", "20 bars"),
    ("std_ratio_20_100", "entry_std_ratio_20_100", "ratio", "event-time source field", "20/100 bars"),
    ("price_z20", "entry_price_z20", "standard deviations", "event-time source field", "20 bars"),
    ("price_abs_z20", "entry_price_abs_z20", "standard deviations", "event-time source field", "20 bars"),
    ("rsi_std_20", "entry_rsi_std_20", "RSI units", "event-time source field", "20 bars"),
    ("rsi_std_rank", "entry_rsi_std_rank", "percentile", "event-time source field", "20 bars"),
    ("atr_return_std_ratio", "entry_atr_return_std_ratio", "ratio", "event-time source field", "20 bars"),
    ("atr_return_std_rank", "entry_atr_return_std_rank", "percentile", "event-time source field", "20 bars"),
    ("entry_atr_rank", "entry_atr_rank", "percentile", "event-time source field", "source lookback"),
    ("entry_efficiency_20", "entry_efficiency_20", "ratio", "event-time source field", "20 bars"),
    ("initial_sl_atr", "initial_sl_atr", "ATR units", "event-time source field", "entry"),
    ("d1_regime_score", "d1_regime_score", "score", "event-time source field", "source lookback"),
    ("h4_regime_score", "h4_regime_score", "score", "event-time source field", "source lookback"),
    ("composite_regime_score", "composite_regime_score", "score", "event-time source field", "source lookback"),
)

NUMERIC_FEATURES = tuple(item[0] for item in _NUMERIC_DEFINITIONS)
CATEGORICAL_FEATURES = ("symbol", "timeframe", "side", "strategy_version")
CONTEXT_FEATURES = (
    "d1_bias", "h4_bias", "h1_bias", "source_regime",
)

# This set includes the identity/context fields used to build a vector.  The
# timestamp is deliberately absent: it is for temporal ordering only.
FEATURE_ALLOWLIST = frozenset(
    set(NUMERIC_FEATURES) | set(CATEGORICAL_FEATURES) | set(CONTEXT_FEATURES)
)

# Labels have a separate namespace.  They may be present in a canonical row,
# but never pass through feature extraction.
LABEL_ALLOWLIST = frozenset(
    {
        "plus_1r_before_minus_1r",
        "shadow_plus_1r_first",
        "shadow_minus_1r_first",
        "shadow_first_hit",
        "shadow_return_6bar_r",
        "shadow_return_12bar_r",
        "shadow_return_24bar_r",
        "shadow_return_48bar_r",
        "shadow_mfe_r",
        "shadow_mae_r",
        "resolved",
        "outcome_timestamp_utc",
        "incomplete_reason",
        "label_status",
        "source_episode_id",
    }
)

_EXPLICIT_OUTCOME_FIELDS = frozenset(
    {
        "resolved",
        "outcome_timestamp_utc",
        "incomplete_reason",
        "shadow_first_hit",
        "shadow_plus_1r_first",
        "shadow_minus_1r_first",
        "shadow_mfe_r",
        "shadow_mae_r",
        "actual_selected_first_hit",
        "actual_selected_plus_1r_first",
        "actual_selected_minus_1r_first",
        "actual_selected_mfe_r",
        "actual_selected_mae_r",
        "active_value_6bar_r",
        "active_value_12bar_r",
        "active_value_24bar_r",
        "active_value_48bar_r",
        "active_continuation_6bar_r",
        "active_continuation_12bar_r",
        "active_continuation_24bar_r",
        "active_continuation_48bar_r",
        "active_plus_1r_hit",
        "active_minus_1r_hit",
        "active_first_hit",
        "opportunity_diff_6bar_r",
        "opportunity_diff_12bar_r",
        "opportunity_diff_24bar_r",
        "opportunity_diff_48bar_r",
        "shadow_return_6bar_r",
        "shadow_return_12bar_r",
        "shadow_return_24bar_r",
        "shadow_return_48bar_r",
        "actual_selected_return_6bar_r",
        "actual_selected_return_12bar_r",
        "actual_selected_return_24bar_r",
        "actual_selected_return_48bar_r",
    }
)


def feature_definitions() -> tuple[FeatureDefinition, ...]:
    """Return immutable metadata for every V1 feature."""

    numeric = tuple(
        FeatureDefinition(
            feature_name=name,
            feature_version=FEATURE_SET_VERSION,
            dtype="float64",
            unit=unit,
            source="phase1_episode_features/raw_features",
            source_field=source_field,
            calculation_method=method,
            available_at="opportunity_timestamp_utc",
            lookback=lookback,
            missing_policy="mean_or_median_fit_on_train_with_missing_indicator",
            normalization="zscore_fit_on_train_only",
            mql5_semantics="source-reported event-time value; no outcome dependency",
        )
        for name, source_field, unit, method, lookback in _NUMERIC_DEFINITIONS
    )
    categorical = tuple(
        FeatureDefinition(
            feature_name=name,
            feature_version=FEATURE_SET_VERSION,
            dtype="category",
            unit="label",
            source="phase1_trading_episodes",
            source_field=name,
            calculation_method="source-reported canonical categorical value",
            available_at="opportunity_timestamp_utc",
            lookback="none",
            missing_policy="unknown_with_missing_indicator",
            normalization="deterministic_one_hot_fit_on_train_only",
            mql5_semantics="source identity/context; no execution instruction",
        )
        for name in CATEGORICAL_FEATURES
    )
    context = tuple(
        FeatureDefinition(
            feature_name=name,
            feature_version=FEATURE_SET_VERSION,
            dtype="category",
            unit="label",
            source="phase1_raw_features_json",
            source_field=name,
            calculation_method="source-reported event-time context",
            available_at="opportunity_timestamp_utc",
            lookback="source lookback",
            missing_policy="unknown_with_missing_indicator",
            normalization="deterministic_one_hot_fit_on_train_only",
            mql5_semantics="context only; no outcome dependency",
        )
        for name in CONTEXT_FEATURES
    )
    return numeric + categorical + context


def is_outcome_field(name: str) -> bool:
    """Conservative check for fields that can only be labels/provenance."""

    lowered = name.strip().lower()
    if lowered in {field.lower() for field in _EXPLICIT_OUTCOME_FIELDS}:
        return True
    return (
        lowered.startswith("shadow_")
        or lowered.startswith("actual_selected_")
        or lowered.startswith("opportunity_diff_")
        or lowered.startswith("active_value_")
        or lowered.startswith("active_continuation_")
        or lowered in {"first_hit", "resolved", "outcome_timestamp_utc", "incomplete_reason"}
    )


def validate_feature_columns(columns: Iterable[str]) -> None:
    """Fail closed on unknown or outcome columns."""

    unknown: list[str] = []
    outcomes: list[str] = []
    for column in columns:
        name = str(column)
        if is_outcome_field(name):
            outcomes.append(name)
        elif name not in FEATURE_ALLOWLIST:
            unknown.append(name)
    if outcomes:
        raise FeatureLeakageError(
            "outcome/future field rejected by Feature Store allowlist: "
            + ", ".join(sorted(set(outcomes)))
        )
    if unknown:
        raise FeatureSchemaError(
            "unknown feature field rejected (closed world): "
            + ", ".join(sorted(set(unknown)))
        )


def validate_feature_input(row: Mapping[str, Any]) -> None:
    """Validate a canonical row or a flat feature mapping.

    Canonical metadata containers are allowed, while fields placed directly in
    a feature mapping are checked strictly.  This makes an adversarial direct
    ``{"rsi": 50, "shadow_return_24bar_r": 1}`` input fail loudly.
    """

    if "features" in row:
        features = row.get("features")
        if not isinstance(features, Mapping):
            raise FeatureSchemaError("features must be a mapping")
        validate_feature_columns(features.keys())
    if "context" in row:
        context = row.get("context")
        if not isinstance(context, Mapping):
            raise FeatureSchemaError("context must be a mapping")
        validate_feature_columns(context.keys())

    # Normalized vectors are commonly represented as mappings in callers and
    # reports.  They are still feature input, so validate them explicitly;
    # otherwise an adversarial outcome key nested under ``feature_vector``
    # could bypass the closed-world gate.
    for vector_name in ("feature_vector", "features_normalized"):
        vector = row.get(vector_name)
        if isinstance(vector, Mapping):
            vector_columns: list[str] = []
            for name in vector:
                text = str(name)
                if text.endswith("__missing"):
                    text = text[:-9]
                elif "=" in text:
                    text = text.split("=", 1)[0]
                vector_columns.append(text)
            validate_feature_columns(vector_columns)

    containers = {
        "features", "context", "labels", "provenance", "regime", "feature_vector",
        "features_normalized", "split", "canonical_opportunity_id", "timestamp_utc",
        "symbol", "timeframe", "side", "strategy_version", "feature_status",
        "observation_count", "episode_ids", "audit_versions", "source_timestamps",
        "source_artifact_ids", "canonical_timestamp_rule", "field_status", "feature_conflicts", "created_at",
        "available_at", "canonical_timestamp_utc", "feature_fingerprint",
    }
    direct = []
    for name in row:
        if name in containers:
            continue
        # A flat row is accepted only for registered fields.
        direct.append(name)
    if direct:
        validate_feature_columns(direct)


def extract_feature_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Extract only registered feature fields from a canonical/flat row."""

    validate_feature_input(row)
    extracted: dict[str, Any] = {}
    nested_features = row.get("features")
    if isinstance(nested_features, Mapping):
        extracted.update({str(k): v for k, v in nested_features.items()})
    nested_context = row.get("context")
    if isinstance(nested_context, Mapping):
        extracted.update({str(k): v for k, v in nested_context.items()})
    for name in sorted(FEATURE_ALLOWLIST):
        if name in row:
            extracted[name] = row[name]
    return {name: extracted[name] for name in sorted(FEATURE_ALLOWLIST) if name in extracted}


def metadata_dict() -> list[dict[str, Any]]:
    return [asdict(item) for item in feature_definitions()]


def outcome_field_names() -> frozenset[str]:
    return _EXPLICIT_OUTCOME_FIELDS


__all__ = [
    "CATEGORICAL_FEATURES",
    "CONTEXT_FEATURES",
    "FEATURE_ALLOWLIST",
    "FEATURE_SCHEMA_VERSION",
    "FEATURE_SET_VERSION",
    "FeatureDefinition",
    "FeatureLeakageError",
    "FeatureSchemaError",
    "LABEL_ALLOWLIST",
    "NUMERIC_FEATURES",
    "extract_feature_fields",
    "feature_definitions",
    "is_outcome_field",
    "metadata_dict",
    "outcome_field_names",
    "validate_feature_columns",
    "validate_feature_input",
]
