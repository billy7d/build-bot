"""Kiểm thử cổng equality execution ở mức deal."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from compare_execution_regression import collect_execution_deals, compare_deal_sequences, compare_diagnostics
except ModuleNotFoundError:
    from tools.mt5.compare_execution_regression import collect_execution_deals, compare_deal_sequences, compare_diagnostics


def deal_row(time="2025.01.01 00:00", price="100.0", comment="RSI_MTF_LONG"):
    return [
        time,
        "1",
        "BTCUSD",
        "Buy",
        "In",
        "0.10",
        price,
        "2",
        "0.00",
        "0.00",
        "-0.10",
        "5 000.00",
        comment,
    ]


class CompareExecutionRegressionTests(unittest.TestCase):
    def test_extracts_stable_deal_sequence(self):
        header = ["Time", "Deal", "Symbol", "Type", "Direction", "Volume", "Price", "Order", "Commission", "Swap", "Profit", "Balance", "Comment"]
        deals = collect_execution_deals([header, deal_row()], 0)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0]["direction"], "in")
        self.assertEqual(deals[0]["profit"], -0.1)
        self.assertEqual(deals[0]["commission"], 0.0)
        self.assertEqual(deals[0]["swap"], 0.0)
        self.assertEqual(deals[0]["comment"], "RSI_MTF_LONG")

    def test_detects_deal_level_difference(self):
        header = ["Time", "Deal", "Symbol", "Type", "Direction", "Volume", "Price", "Order", "Commission", "Swap", "Profit", "Balance", "Comment"]
        control = collect_execution_deals([header, deal_row()], 0)
        audit = collect_execution_deals([header, deal_row(price="101.0")], 0)
        mismatches = compare_deal_sequences(control, audit, 1.0e-6)
        self.assertTrue(mismatches)
        self.assertEqual(mismatches[0]["field"], "price")

    def test_missing_on_tester_diagnostics_are_unavailable(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "journal.log"
            path.write_text("tester finished without diagnostics\n", encoding="utf-8")
            result = compare_diagnostics(path, path)
        self.assertFalse(result["available"])


if __name__ == "__main__":
    unittest.main()
