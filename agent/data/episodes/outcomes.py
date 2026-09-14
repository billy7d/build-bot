"""Contract dùng chung cho outcome; outcome luôn tách khỏi feature event-time."""

from .builder import HORIZONS

GENERIC_OUTCOME_SCHEMA_VERSION = "TA-OUTCOME-V1"
OPPORTUNITY_OUTCOME_SCHEMA_VERSION = "TA-OPPORTUNITY-OUTCOME-V1"

__all__ = [
    "HORIZONS",
    "GENERIC_OUTCOME_SCHEMA_VERSION",
    "OPPORTUNITY_OUTCOME_SCHEMA_VERSION",
]
