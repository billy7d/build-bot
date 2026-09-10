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
        "active_base_position_identifier": "1",
        "shadow_build_valid": "true",
        "shadow_build_reason": "",
        "long_reject": "",
        "short_reject": "",
        "shadow_entry_price": "100",
        "shadow_spread": "0.1",
        "shadow_initial_sl": "98",
        "actual_selected_build_valid": "false",
        "shadow_risk_distance": "2",
        "shadow_entry_rsi": "55",
        "shadow_entry_rsi_ema": "54",
        "shadow_entry_rsi_wma": "53",
        "d1_bias": "BULL",
        "h4_bias": "BULL",
        "h1_bias": "BULL",
        "d1_regime_score": "2",
        "h4_regime_score": "1",
        "composite_regime_score": "5",
        "entry_atr_pct": "1",
        "entry_atr_rank": "50",
        "entry_efficiency_20": "0.5",
        "entry_spread_r": "0.05",
        "initial_sl_atr": "2",
        "active_entry_price": "105",
        "active_current_price": "104",
        "active_initial_risk": "10",
        "active_initial_risk_distance": "2",
        "active_current_r": "-0.5",
        "active_sl": "107",
        "active_is_be": "false",
        "active_tp1_done": "false",
        "active_tp2_done": "false",
        "active_runner_active": "false",
        "active_pyramid_adds": "0",
        "active_bars_open": "12",
        "active_locked_profit_r": "-1",
        "active_group_volume": "1",
        "active_position_count": "1",
        "active_value_at_event_r": "-0.5",
        "active_value_6bar_r": "-0.25",
        "active_value_12bar_r": "-0.1",
        "active_value_24bar_r": "0",
        "active_value_48bar_r": "0.5",
        "shadow_first_hit": "PLUS_1R",
        "shadow_mfe_r": "2",
        "shadow_mae_r": "-0.5",
        "shadow_return_6bar_r": "1.0",
        "shadow_return_12bar_r": "1.5",
        "shadow_return_24bar_r": "2.0",
        "shadow_return_48bar_r": "2.5",
        "active_continuation_6bar_r": "0.25",
        "active_continuation_12bar_r": "0.4",
        "active_continuation_24bar_r": "0.5",
        "active_continuation_48bar_r": "1.0",
        "opportunity_diff_6bar_r": "0.75",
        "opportunity_diff_12bar_r": "1.1",
        "opportunity_diff_24bar_r": "1.5",
        "opportunity_diff_48bar_r": "1.5",
        "active_plus_1r_hit": "false",
        "active_minus_1r_hit": "true",
        "active_first_hit": "MINUS_1R",
        "shadow_plus_1r_hit": "true",
        "shadow_minus_1r_hit": "true",
        "shadow_plus_1r_first": "true",
        "shadow_minus_1r_first": "false",
        "actual_selected_plus_1r_hit": "false",
        "actual_selected_minus_1r_hit": "false",
        "actual_selected_plus_1r_first": "false",
        "actual_selected_minus_1r_first": "false",
        "actual_selected_first_hit": "NONE",
        "actual_selected_entry_price": "",
        "actual_selected_initial_sl": "",
        "actual_selected_risk_distance": "",
        "actual_selected_mfe_r": "",
        "actual_selected_mae_r": "",
        "actual_selected_return_6bar_r": "",
        "actual_selected_return_12bar_r": "",
        "actual_selected_return_24bar_r": "",
        "actual_selected_return_48bar_r": "",
        "setup_generation": "1",
        "active_group_id": "G_1",
        "age_bars": "48",
        "completed": "true",
        "incomplete_reason": "",
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

    def test_completed_event_missing_outcome_fails_closed(self):
        incomplete_outcome = event(event_id="event-2", shadow_return_48bar_r="")
        summary = build_summary([incomplete_outcome])
        quality = summary["data_quality"]
        self.assertEqual(quality["missing_completed_outcome_rows"], 1)
        self.assertEqual(quality["valid_completed_events"], 0)
        self.assertFalse(quality["quality_gate_pass"])

    def test_event_identity_and_relationship_are_validated(self):
        malformed = event(event_id="", active_side="SHORT")
        summary = build_summary([malformed])
        quality = summary["data_quality"]
        self.assertEqual(quality["missing_event_id_rows"], 1)
        self.assertEqual(quality["invalid_event_relation_rows"], 1)
        self.assertFalse(quality["quality_gate_pass"])


if __name__ == "__main__":
    unittest.main()
