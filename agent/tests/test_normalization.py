import unittest

from agent.data.normalization.identifiers import (
    deterministic_episode_id,
    normalize_symbol,
    normalize_timeframe,
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


if __name__ == "__main__":
    unittest.main()
