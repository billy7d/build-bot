import unittest

from agent.data.normalization.identifiers import (
    deterministic_episode_id,
    normalize_symbol,
    normalize_timeframe,
)
from agent.data.models import NormalizedEvent
from agent.data.normalization.canonical import (
    canonical_identity_key,
    canonical_opportunity_id,
)
from agent.data.normalization.timestamps import TimestampNormalizationError, normalize_timestamp


class NormalizationTests(unittest.TestCase):
    def test_timestamp_requires_timezone_without_epoch(self):
        with self.assertRaises(TimestampNormalizationError):
            normalize_timestamp("2025.01.01 00:00", None)

    def test_v82_epoch_cross_check_is_utc(self):
        self.assertEqual(
            normalize_timestamp("2025.01.01 00:00", "UTC", epoch_hint=1735689600),
            "2025-01-01T00:00:00Z",
        )
        with self.assertRaises(TimestampNormalizationError):
            normalize_timestamp("2025.01.01 01:00", "UTC", epoch_hint=1735689600)

    def test_symbol_and_timeframe_are_canonical_without_alias_merge(self):
        self.assertEqual(normalize_symbol("BTCUSD.a"), "BTCUSD.A")
        self.assertEqual(normalize_timeframe("16385"), "H1")

    def test_episode_id_is_deterministic(self):
        kwargs = {
            "symbol": "BTCUSD",
            "timeframe": "H1",
            "timestamp_utc": "2025-01-01T00:00:00Z",
            "strategy_version": "V26",
            "audit_version": "V82",
            "side": "SHORT",
            "episode_kind": "BLOCKED_OPPORTUNITY",
            "ordinal": 1,
        }
        self.assertEqual(deterministic_episode_id(**kwargs), deterministic_episode_id(**kwargs))

    def test_same_canonical_id_across_audits_with_distinct_episode_inputs(self):
        v81 = NormalizedEvent(
            "v81.csv", "BLOCKED_SIGNAL", "2025-01-01T01:00:00Z", "2025.01.01 01:00", "UTC",
            "BTCUSD", "H1", "V26", "V81", "SHORT", "1", 100.0, None,
            {"raw_event_type": "OPEN_OPPOSITE_SIDE", "initial_sl": 102.0, "risk_distance": 2.0},
            {"event_id": "1"},
        )
        v82 = NormalizedEvent(
            "v82.csv", "BLOCKED_SIGNAL", "2025-01-01T00:00:00Z", "2025.01.01 00:00", "UTC",
            "BTCUSD", "H1", "V26", "V82", "SHORT", "epoch_BLOCKED_OPPOSITE", 100.0, None,
            {"raw_event_type": "BLOCKED_OPPOSITE", "shadow_initial_sl": 102.0, "shadow_risk_distance": 2.0},
            {"event_id": "epoch_BLOCKED_OPPOSITE"},
        )
        self.assertEqual(canonical_opportunity_id(v81), canonical_opportunity_id(v82))
        self.assertEqual(canonical_identity_key(v81), canonical_identity_key(v82))
        self.assertNotEqual(v81.raw_event_id, v82.raw_event_id)

    def test_canonical_identity_changes_when_candidate_changes(self):
        base = NormalizedEvent(
            "v81.csv", "BLOCKED_SIGNAL", "2025-01-01T00:00:00Z", "2025.01.01 00:00", "UTC",
            "BTCUSD", "H1", "V26", "V81", "LONG", "1", 100.0, None,
            {"raw_event_type": "OPEN_SAME_SIDE", "initial_sl": 98.0, "risk_distance": 2.0},
            {"event_id": "1"},
        )
        changed = NormalizedEvent(
            "other.csv", "BLOCKED_SIGNAL", "2025-01-01T00:00:00Z", "2025.01.01 00:00", "UTC",
            "BTCUSD", "H1", "V26", "V82", "LONG", "2", 101.0, None,
            {"raw_event_type": "BLOCKED_SAME_SIDE", "shadow_initial_sl": 98.0, "shadow_risk_distance": 3.0},
            {"event_id": "2"},
        )
        self.assertNotEqual(canonical_opportunity_id(base), canonical_opportunity_id(changed))


if __name__ == "__main__":
    unittest.main()
