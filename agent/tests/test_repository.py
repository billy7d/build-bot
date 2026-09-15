import sqlite3
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from agent.data.episodes.builder import build_bundle
from agent.data.models import NormalizedEvent
from agent.memory.database import apply_migrations, connect_database, integrity_status, migration_versions
from agent.memory.repository import TradingMemoryRepository
from agent.evaluation.reproducibility import fingerprint_inputs


class RepositoryTests(unittest.TestCase):
    def test_migration_fk_and_idempotency(self):
        with TemporaryDirectory() as directory:
            connection = connect_database(Path(directory) / "memory.db")
            apply_migrations(connection)
            self.assertEqual(migration_versions(connection), ["001", "002", "003", "004", "005", "006", "007"])
            self.assertEqual(fingerprint_inputs(connection)["schema_versions"], ["001", "002", "003", "004", "005", "006"])
            repository = TradingMemoryRepository(connection)
            with connection:
                repository.register_strategy({"id": "V26", "name": "V26", "description": "base", "status": "BASELINE"})
                repository.register_audit({"id": "V81", "name": "V81", "audit_type": "STDDEV_SHADOW", "base_strategy_version": "V26", "mode": "SHADOW", "execution_authority": "NONE", "description": "audit", "status": "RESEARCH_ONLY"})
                repository.register_audit({"id": "V82", "name": "V82", "audit_type": "BLOCKED_OPPORTUNITY", "base_strategy_version": "V26", "parent_audit_version": "V81", "mode": "SHADOW", "execution_authority": "NONE", "description": "audit", "status": "RESEARCH_ONLY"})
                repository.register_preset({"id": "p", "name": "p", "file_path": "p.set", "sha256": "p-hash", "parameters": {}})
                repository.register_experiment({"id": "V82-2025", "name": "x", "preset_id": "p", "fold_type": "OOS"})
                source_id = repository.insert_source_artifact({"path": "fixture.csv", "artifact_type": "BLOCKED_SIGNAL_SHADOW_TELEMETRY", "sha256": "hash", "file_size": 1, "parser_name": "x", "parser_version": "x/1", "strategy_version": "V26", "audit_version": "V82", "preset_id": "p", "experiment_id": "V82-2025", "source_timezone": "UTC", "status": "IMPORTED"})
                self.assertTrue(repository.source_already_imported("hash", "x/1"))
                event = NormalizedEvent("fixture.csv", "BLOCKED_SIGNAL", "2025-01-01T00:00:00Z", "2025.01.01 00:00", "UTC", "BTCUSD", "H1", "V26", "V82", "SHORT", "e1", 100.0, None, {"raw_event_type": "BLOCKED_OPPOSITE", "shadow_initial_sl": 102.0, "shadow_risk_distance": 2.0, "completed": True}, {"event_id": "e1"})
                bundle = build_bundle(event, source_artifact_id=source_id, experiment_id="V82-2025", preset_id="p", ordinal=1)
                repository.insert_episode(bundle.episode)
                repository.insert_features(bundle.features)
                repository.insert_outcome(bundle.outcome)
                repository.insert_opportunity_context(bundle.opportunity_context)
                repository.insert_active_context(bundle.active_context)
                repository.insert_opportunity_outcome(bundle.opportunity_outcome)
                v81_event = NormalizedEvent("fixture.csv", "BLOCKED_SIGNAL", "2025-01-01T01:00:00Z", "2025.01.01 01:00", "UTC", "BTCUSD", "H1", "V26", "V81", "SHORT", "e1-v81", 100.0, None, {"raw_event_type": "OPEN_OPPOSITE_SIDE", "initial_sl": 102.0, "risk_distance": 2.0, "completed": True}, {"event_id": "e1-v81", "conflict_type": "OPEN_OPPOSITE_SIDE"})
                v81_bundle = build_bundle(v81_event, source_artifact_id=source_id, experiment_id="V82-2025", preset_id="p", ordinal=1)
                repository.insert_episode(v81_bundle.episode)
                repository.insert_features(v81_bundle.features)
                repository.insert_outcome(v81_bundle.outcome)
            self.assertEqual(len(repository.query_episodes(strategy_version="V26")), 2)
            canonical_id = bundle.episode["canonical_opportunity_id"]
            self.assertEqual(len(repository.query_episodes(canonical_opportunity_id=canonical_id)), 2)
            self.assertEqual(len(repository.get_opportunity_observations(canonical_id)), 2)
            self.assertEqual(repository.count_unique_opportunities(), 1)
            self.assertEqual(repository.count_audit_observations(), 2)
            self.assertEqual(repository.count_unique_opportunities(audit_version="V81"), 1)
            self.assertEqual(repository.count_audit_observations(audit_version="V82"), 1)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO executions(execution_id, episode_id) VALUES ('bad', 'missing')")
            self.assertTrue(integrity_status(connection)["integrity_ok"])
            connection.close()


if __name__ == "__main__":
    unittest.main()
