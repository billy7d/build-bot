import unittest
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.data.import_all import _resolve_dataset_generation_commit
from agent.evaluation.leakage_checks import synthetic_future_mutation_test
from agent.evaluation.reporting import render_foundation_report
from agent.evaluation.reproducibility import build_manifest, dataset_fingerprint
from agent.memory.database import apply_migrations, connect_database
from agent.memory.parquet import TABLE_FILES, export_tables
from agent.data.queries import run_named_query


class EvaluationTests(unittest.TestCase):
    def test_future_mutation_is_detected(self):
        self.assertTrue(synthetic_future_mutation_test({"rsi": 1}, {"rsi": 1})["passed"])
        self.assertFalse(synthetic_future_mutation_test({"rsi": 1}, {"rsi": 2})["passed"])

    def test_parquet_exports_have_valid_container_markers(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            connection = connect_database(root / "memory.db")
            apply_migrations(connection)
            result = export_tables(connection, root / "parquet")
            self.assertEqual(result["writer"], "minimal-parquet")
            for filename in TABLE_FILES.values():
                payload = (root / "parquet" / filename).read_bytes()
                self.assertEqual(payload[:4], b"PAR1")
                self.assertEqual(payload[-4:], b"PAR1")
                footer_size = int.from_bytes(payload[-8:-4], "little")
                self.assertGreater(footer_size, 0)
                self.assertLessEqual(footer_size + 8, len(payload))
                if filename == "episodes.parquet":
                    self.assertIn(b"canonical_opportunity_id", payload)
            self.assertEqual(run_named_query(connection, "O")[0]["unique_canonical_opportunities"], 0)
            self.assertEqual(run_named_query(connection, "P"), [])
            connection.close()

    def test_manifest_provenance_is_separate_from_mutable_pr_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            connection = connect_database(root / "memory.db")
            apply_migrations(connection)
            quality = {"status": "PASS", "checks": [], "leakage": {"passed": True}}
            first = build_manifest(
                connection,
                root=root,
                quality=quality,
                dataset_generation_commit="dataset-sha",
                report_capture_commit="capture-sha",
            )
            second = build_manifest(
                connection,
                root=root,
                quality=quality,
                dataset_generation_commit="dataset-sha",
                report_capture_commit="later-capture-sha",
            )
            self.assertNotIn("pr_head", first)
            self.assertEqual(first["dataset_generation_commit"], "dataset-sha")
            self.assertEqual(first["report_capture_commit"], "capture-sha")
            self.assertEqual(first["dataset_fingerprint"], dataset_fingerprint(connection))
            self.assertEqual(first["dataset_fingerprint"], second["dataset_fingerprint"])
            report = render_foundation_report(
                connection,
                inventory={"artifact_count": 0, "raw_v82_status": "UNKNOWN"},
                quality=quality,
                manifest=first,
            )
            self.assertIn("Report capture commit: `capture-sha`", report)
            self.assertNotIn("PR head", report)
            self.assertNotIn("final head", report.lower())
            existing = {"dataset_generation_commit": "dataset-sha", "dataset_fingerprint": "same"}
            self.assertEqual(_resolve_dataset_generation_commit(existing, "same", "capture-sha"), "dataset-sha")
            self.assertEqual(_resolve_dataset_generation_commit(existing, "changed", "capture-sha"), "capture-sha")
            connection.close()


if __name__ == "__main__":
    unittest.main()
