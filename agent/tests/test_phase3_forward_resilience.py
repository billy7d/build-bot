"""Forward collector resilience: heartbeat best-effort, failure reasons và campaign gộp run."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent.memory.database import connect_database
from agent.phase3 import forward
from agent.phase3.campaign import (
    CampaignError,
    campaign_coverage,
    campaign_evaluation_records,
    campaign_run_ids,
    campaign_sample_count,
    declare_campaign,
    sync_campaign_runs,
)
from agent.phase3.config import Phase3Config
from agent.phase3.forward import (
    ForwardControlError,
    PersistentForwardCollector,
    create_forward_run,
    read_runtime_status,
)
from agent.phase3.runtime import Phase3Runtime

try:
    from .test_phase3 import _fixture_bundle
    from .test_phase3_1 import _authorization, _opportunity_payload, _runtime_config
except ImportError:
    from test_phase3 import _fixture_bundle
    from test_phase3_1 import _authorization, _opportunity_payload, _runtime_config


def _line(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":")) + "\n"


def _events(db_path: Path, run_id: str, event_type: str) -> list[dict[str, object]]:
    connection = connect_database(db_path)
    try:
        rows = connection.execute(
            "SELECT severity, value_json FROM phase3_health_events WHERE run_id = ? AND event_type = ? ORDER BY id",
            (run_id, event_type),
        ).fetchall()
        return [{"severity": row["severity"], **json.loads(row["value_json"])} for row in rows]
    finally:
        connection.close()


def _declare(connection: object, config: object, bundle: object, *, campaign_id: str = "camp-1", window: str = "2024-01-01T00:00:00Z") -> dict[str, object]:
    return declare_campaign(
        connection,
        campaign_id=campaign_id,
        bundle_id=bundle.bundle_id,
        window_start_utc=window,
        primary_source_schema=config.primary_opportunity_schema,
        canonical_schema=config.canonical_schema,
        canonicalizer_version=config.canonicalizer_version,
        canonicalizer_fingerprint=config.canonicalizer_fingerprint,
        now="2024-01-01T00:00:00Z",
    )


class ForwardResilienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.model, cls.index, _ = _fixture_bundle()

    def _runtime(self, config: object) -> Phase3Runtime:
        return Phase3Runtime.open(
            config.db,
            self.bundle,
            model_bundle=self.model,
            similarity_index=self.index,
            config=Phase3Config(
                mode="FORWARD",
                bundle_id=self.bundle.bundle_id,
                telemetry_source="fixture",
                db_path=str(config.db),
                classification_min_resolved=1,
                regression_min_resolved=1,
            ),
            clock=lambda: "2024-01-01T00:00:00Z",
        )

    def _collector(self, config: object, run_id: str, clock: str) -> PersistentForwardCollector:
        return PersistentForwardCollector(
            config, _authorization(self.bundle, config), self.bundle, self.model, self.index,
            run_id=run_id, clock=lambda: clock, sleep=lambda _: None,
        )

    # --- A: heartbeat là best-effort ---

    def test_heartbeat_write_failure_does_not_fail_run_or_drop_records(self) -> None:
        with TemporaryDirectory() as directory:
            config = _runtime_config(Path(directory))
            source = Path(config.primary_opportunity)
            source.write_text("", encoding="utf-8")
            runtime = self._runtime(config)
            runtime.create_run("run-hb", mode="FORWARD", started_at_utc="2024-01-01T00:00:00Z", git_sha="test-sha")
            runtime.close()
            collector = self._collector(config, "run-hb", "2024-01-01T00:00:05Z")
            source.write_text(_line(_opportunity_payload("live-1", timestamp="2024-01-01T00:00:01Z")), encoding="utf-8")

            def denied(path: object, payload: object) -> None:
                raise PermissionError(5, "Access is denied")

            # Bind sau khi file đã có bản ghi nên bản ghi đầu thuộc phần trước boundary; append thêm một bản ghi live.
            with patch.object(forward, "_atomic_json_write", denied):
                collector.run_once()
                with source.open("a", encoding="utf-8") as stream:
                    stream.write(_line(_opportunity_payload("live-2", timestamp="2024-01-01T00:00:02Z", entry_price=101.0)))
                result = collector.run_once()
            self.assertEqual(result["records_seen"], 1)
            run = collector._runtime._run("run-hb")
            self.assertNotEqual(str(run["status"]), "FAILED")
            # Ghi lại được thì phát sinh RECOVERED.
            collector.run_once()
            collector._close_runtime()
            failed = _events(config.db, "run-hb", "HEARTBEAT_WRITE_FAILED")
            self.assertEqual(len(failed), 1)
            self.assertEqual(failed[0]["error_type"], "PermissionError")
            recovered = _events(config.db, "run-hb", "HEARTBEAT_WRITE_RECOVERED")
            self.assertEqual(recovered[0]["consecutive_failures"], 2)
            heartbeat = json.loads(config.heartbeat_path.read_text(encoding="utf-8"))
            self.assertEqual(heartbeat["heartbeat_write_failures"], 2)

    def test_run_forever_survives_persistent_heartbeat_failure(self) -> None:
        with TemporaryDirectory() as directory:
            config = _runtime_config(Path(directory))
            Path(config.primary_opportunity).write_text("", encoding="utf-8")
            runtime = self._runtime(config)
            runtime.create_run("run-loop", mode="FORWARD", started_at_utc="2024-01-01T00:00:00Z", git_sha="test-sha")
            runtime.close()
            collector = self._collector(config, "run-loop", "2024-01-01T00:00:05Z")

            def denied(path: object, payload: object) -> None:
                raise PermissionError(5, "Access is denied")

            with patch.object(forward, "_atomic_json_write", denied):
                result = collector.run_forever(max_iterations=3)
            self.assertEqual(result["collector_status"], "PAUSED")
            runtime = self._runtime(config)
            try:
                self.assertEqual(str(runtime._run("run-loop")["status"]), "PAUSED")
            finally:
                runtime.close()

    # --- B: lý do lỗi được lưu ---

    def test_run_failure_reason_is_persisted_and_reported(self) -> None:
        with TemporaryDirectory() as directory:
            config = _runtime_config(Path(directory))
            Path(config.primary_opportunity).write_text("", encoding="utf-8")
            runtime = self._runtime(config)
            runtime.create_run("run-boom", mode="FORWARD", started_at_utc="2024-01-01T00:00:00Z", git_sha="test-sha")
            runtime.close()
            collector = self._collector(config, "run-boom", "2024-01-01T00:00:05Z")
            with patch.object(PersistentForwardCollector, "_cycle", side_effect=RuntimeError("database disk image is malformed")):
                with self.assertRaises(RuntimeError):
                    collector.run_forever(max_iterations=2)
            failures = _events(config.db, "run-boom", "RUN_FAILED")
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["error_type"], "RuntimeError")
            self.assertIn("malformed", failures[0]["error"])
            status = read_runtime_status(config, run_id="run-boom", now="2024-01-01T00:00:06Z")
            self.assertEqual(status["last_failure"]["event_type"], "RUN_FAILED")
            self.assertIn("malformed", status["last_failure"]["error"])

    def test_refused_resume_is_recorded_as_start_refusal(self) -> None:
        with TemporaryDirectory() as directory:
            config = _runtime_config(Path(directory))
            Path(config.primary_opportunity).write_text("", encoding="utf-8")
            runtime = self._runtime(config)
            runtime.create_run("run-failed", mode="FORWARD", started_at_utc="2024-01-01T00:00:00Z", git_sha="test-sha")
            runtime.set_run_status("run-failed", "FAILED")
            runtime.close()
            collector = self._collector(config, "run-failed", "2024-01-01T00:00:05Z")
            with self.assertRaises(ForwardControlError):
                collector.run_forever(max_iterations=1)
            self.assertEqual(len(_events(config.db, "run-failed", "RUN_START_REFUSED")), 1)
            self.assertEqual(_events(config.db, "run-failed", "RUN_FAILED"), [])

    def test_truncation_records_reason(self) -> None:
        with TemporaryDirectory() as directory:
            config = _runtime_config(Path(directory))
            source = Path(config.primary_opportunity)
            source.write_text("", encoding="utf-8")
            runtime = self._runtime(config)
            runtime.create_run("run-trunc", mode="FORWARD", started_at_utc="2024-01-01T00:00:00Z", git_sha="test-sha")
            runtime.close()
            collector = self._collector(config, "run-trunc", "2024-01-01T00:00:05Z")
            collector.run_once()
            first = _line(_opportunity_payload("a", timestamp="2024-01-01T00:00:01Z"))
            second = _line(_opportunity_payload("b", timestamp="2024-01-01T00:00:02Z", entry_price=101.0))
            with source.open("a", encoding="utf-8") as stream:
                stream.write(first + second)
            collector.run_once()
            # Cùng dòng đầu (cùng identity) nhưng ngắn hơn offset: truncation, không phải rotation.
            source.write_text(first, encoding="utf-8")
            result = collector.run_once()
            collector._close_runtime()
            self.assertTrue(result["truncated"])
            reasons = [event["reason"] for event in _events(config.db, "run-trunc", "RUN_FAILED")]
            self.assertEqual(reasons, ["SOURCE_TRUNCATED"])

    # --- C: campaign gộp mẫu qua nhiều run ---

    def test_campaign_pools_samples_across_failed_and_new_runs(self) -> None:
        with TemporaryDirectory() as directory:
            config = _runtime_config(Path(directory))
            source = Path(config.primary_opportunity)
            source.write_text("", encoding="utf-8")
            runtime = self._runtime(config)
            try:
                runtime.create_run("run-before", mode="FORWARD", started_at_utc="2023-12-31T00:00:00Z", git_sha="test-sha")
                runtime.set_run_status("run-before", "STOPPED")
                runtime.create_run("run-1", mode="FORWARD", started_at_utc="2024-01-01T00:00:00Z", git_sha="sha-a")
                first = self._collector(config, "run-1", "2024-01-01T01:00:00Z")
                first.run_once()
                with source.open("a", encoding="utf-8") as stream:
                    stream.write(_line(_opportunity_payload("opp-1", timestamp="2024-01-01T00:30:00Z")))
                self.assertEqual(first.run_once()["records_seen"], 1)
                first._close_runtime()
                runtime.set_run_status("run-1", "FAILED")

                # Bản ghi phát sinh khi không có collector: không thuộc run nào (không backfill).
                with source.open("a", encoding="utf-8") as stream:
                    stream.write(_line(_opportunity_payload("opp-gap", timestamp="2024-01-01T02:00:00Z", entry_price=102.0)))

                runtime.create_run("run-2", mode="FORWARD", started_at_utc="2024-01-01T03:00:00Z", git_sha="sha-b")
                second = self._collector(config, "run-2", "2024-01-01T04:00:00Z")
                self.assertEqual(second.run_once()["records_seen"], 0)
                with source.open("a", encoding="utf-8") as stream:
                    stream.write(_line(_opportunity_payload("opp-2", timestamp="2024-01-01T03:30:00Z", side="SHORT", entry_price=103.0)))
                self.assertEqual(second.run_once()["records_seen"], 1)
                second._close_runtime()

                _declare(runtime.connection, config, self.bundle)
                membership = sync_campaign_runs(runtime.connection, "camp-1", now="2024-01-01T05:00:00Z")
                self.assertEqual(membership["member_run_ids"], ["run-1", "run-2"])
                counts = campaign_sample_count(runtime.connection, "camp-1")
                self.assertEqual(counts["forward_sample_count"], 2)
                self.assertEqual(counts["cross_run_duplicate_count"], 0)
                # Sync lại là idempotent.
                self.assertEqual(sync_campaign_runs(runtime.connection, "camp-1", now="2024-01-01T06:00:00Z")["attached"], [])

                coverage = campaign_coverage(runtime.connection, "camp-1")
                self.assertEqual([run["git_sha"] for run in coverage["runs"]], ["sha-a", "sha-b"])
                self.assertEqual(coverage["runs"][0]["coverage_basis"], "LIVENESS")
                self.assertEqual(len(coverage["gaps"]), 1)
                self.assertEqual(coverage["gaps"][0]["from_utc"], "2024-01-01T01:00:00Z")
                self.assertEqual(coverage["gaps"][0]["to_utc"], "2024-01-01T04:00:00Z")
            finally:
                runtime.close()

    def test_campaign_declaration_is_immutable(self) -> None:
        with TemporaryDirectory() as directory:
            config = _runtime_config(Path(directory))
            runtime = self._runtime(config)
            try:
                from agent.phase3.bundle import persist_bundle

                persist_bundle(runtime.connection, self.bundle)
                first = _declare(runtime.connection, config, self.bundle)
                again = _declare(runtime.connection, config, self.bundle)
                self.assertEqual(first["declaration_hash"], again["declaration_hash"])
                with self.assertRaises(CampaignError):
                    _declare(runtime.connection, config, self.bundle, window="2024-02-01T00:00:00Z")
                with self.assertRaises(CampaignError):
                    _declare(runtime.connection, config, self.bundle, campaign_id="bad id with spaces")
            finally:
                runtime.close()

    def test_create_forward_run_requires_declared_campaign_and_attaches(self) -> None:
        with TemporaryDirectory() as directory:
            config = replace(_runtime_config(Path(directory)), campaign_id="camp-auto")
            auth = _authorization(self.bundle, config)
            with self.assertRaisesRegex(ForwardControlError, "not declared"):
                create_forward_run(config, auth, self.bundle, run_id="run-early", now="2024-01-01T00:00:00Z")
            runtime = self._runtime(config)
            try:
                from agent.phase3.bundle import persist_bundle

                persist_bundle(runtime.connection, self.bundle)
                _declare(runtime.connection, config, self.bundle, campaign_id="camp-auto", window="2020-01-01T00:00:00Z")
            finally:
                runtime.close()
            create_forward_run(config, auth, self.bundle, run_id="run-auto", now="2024-01-01T00:00:00Z")
            runtime = self._runtime(config)
            try:
                self.assertEqual(campaign_run_ids(runtime.connection, "camp-auto"), ["run-auto"])
            finally:
                runtime.close()
            status = read_runtime_status(config, run_id="run-auto", now="2024-01-01T00:00:01Z")
            self.assertEqual(status["campaign"]["campaign_id"], "camp-auto")
            self.assertEqual(status["campaign"]["forward_sample_count"], 0)

    def test_campaign_evaluation_deduplicates_by_canonical_id_keeping_earliest_commit(self) -> None:
        with TemporaryDirectory() as directory:
            config = _runtime_config(Path(directory))
            runtime = self._runtime(config)
            try:
                runtime.create_run("run-a", mode="FORWARD", started_at_utc="2024-01-01T00:00:00Z", git_sha="s")
                runtime.create_run("run-b", mode="FORWARD", started_at_utc="2024-01-02T00:00:00Z", git_sha="s")
                _declare(runtime.connection, config, self.bundle)
                sync_campaign_runs(runtime.connection, "camp-1", now="2024-01-03T00:00:00Z")
                records = [
                    {"forward_run_id": "run-a", "canonical_opportunity_id": "c1", "forward_event_id": "e1",
                     "prediction_committed_at_utc": "2024-01-01T00:00:03Z", "source_event_timestamp_utc": "2024-01-01T00:00:00Z"},
                    {"forward_run_id": "run-b", "canonical_opportunity_id": "c1", "forward_event_id": "e2",
                     "prediction_committed_at_utc": "2024-01-01T00:00:03.500000Z", "source_event_timestamp_utc": "2024-01-01T00:00:00Z"},
                    {"forward_run_id": "run-b", "canonical_opportunity_id": "c2", "forward_event_id": "e3",
                     "prediction_committed_at_utc": "2024-01-02T00:00:01Z", "source_event_timestamp_utc": "2024-01-02T00:00:00Z"},
                    {"forward_run_id": "run-outside", "canonical_opportunity_id": "c3", "forward_event_id": "e4",
                     "prediction_committed_at_utc": "2024-01-02T00:00:01Z", "source_event_timestamp_utc": "2024-01-02T00:00:00Z"},
                ]
                with patch.object(Phase3Runtime, "_evaluation_records", return_value=records):
                    selected, duplicates = campaign_evaluation_records(runtime, "camp-1")
                self.assertEqual([row["forward_event_id"] for row in selected], ["e1", "e3"])
                self.assertEqual(duplicates, 1)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
