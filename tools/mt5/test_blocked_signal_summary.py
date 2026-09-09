#!/usr/bin/env python3
"""Kiểm thử deterministic nhỏ cho bộ tổng hợp V82."""

import unittest

try:
    from blocked_signal_summary import build_summary
except ModuleNotFoundError:
    from tools.mt5.blocked_signal_summary import build_summary


def event(**overrides):
    row = {
        "event_id": "event-1",
        "event_time": "2025.01.01 00:00",
        "entry_bar_time": "2025.01.01 00:00",
        "year": "2025",
        "fold": "oos_2025_plus",
        "side": "SHORT",
        "event_type": "BLOCKED_OPPOSITE",
        "active_side": "LONG",
        "shadow_side": "SHORT",
        "actual_selected_side": "NONE",
        "blocked_side": "SHORT",
        "direction": "LONG_active_to_SHORT_blocked",
        "shadow_build_valid": "true",
        "shadow_risk_distance": "2",
        "shadow_first_hit": "PLUS_1R",
        "shadow_mfe_r": "2",
        "shadow_mae_r": "-0.5",
        "shadow_return_24bar_r": "2.0",
        "shadow_return_48bar_r": "2.5",
        "active_continuation_24bar_r": "0.5",
        "active_continuation_48bar_r": "1.0",
        "opportunity_diff_24bar_r": "1.5",
        "opportunity_diff_48bar_r": "1.5",
        "age_bars": "48",
        "completed": "true",
    }
    row.update(overrides)
    return row


class BlockedSignalSummaryTests(unittest.TestCase):
    def test_opportunity_difference_is_preserved(self):
        summary = build_summary([event()])
        group = summary["fold_groups"][0]
        self.assertEqual(group["direction"], "LONG active -> SHORT blocked")
        self.assertEqual(group["median_opportunity_diff_24_r"], 1.5)
        self.assertEqual(group["median_opportunity_diff_48_r"], 1.5)

    def test_duplicate_and_nonfinite_values_fail_quality_gate(self):
        duplicate = event(event_id="event-1", shadow_risk_distance="nan")
        summary = build_summary([event(), duplicate])
        quality = summary["data_quality"]
        self.assertEqual(quality["duplicate_event_ids"], 1)
        self.assertEqual(quality["nan_or_inf_values"], 1)
        self.assertFalse(quality["quality_gate_pass"])

    def test_incomplete_event_is_excluded_from_metrics(self):
        incomplete = event(event_id="event-2", age_bars="12", completed="false")
        summary = build_summary([event(), incomplete])
        self.assertEqual(summary["data_quality"]["incomplete_valid_events"], 1)
        self.assertEqual(summary["data_quality"]["valid_completed_events"], 1)
        self.assertEqual(summary["input_rows"], 2)


if __name__ == "__main__":
    unittest.main()
