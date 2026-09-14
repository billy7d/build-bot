import unittest
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.evaluation.leakage_checks import synthetic_future_mutation_test
from agent.memory.database import apply_migrations, connect_database
from agent.memory.parquet import TABLE_FILES, export_tables


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
            connection.close()


if __name__ == "__main__":
    unittest.main()
