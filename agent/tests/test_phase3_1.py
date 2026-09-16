"""Contract tests cho persistent forward collector Phase 3.1."""

from __future__ import annotations

import json
import os
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent.features.fingerprint import fingerprint
from agent.phase3.forward import (
    AUTHORIZATION_SCHEMA,
    ForwardControlError,
    ForwardAuthorization,
    ForwardRuntimeConfig,
    PersistentForwardCollector,
    SingleInstanceLock,
    prepare_forward_authorization,
    read_runtime_status,
    validate_forward_authorization,
    write_forward_config,
)
from agent.phase3.ingestion.file_tail import TelemetryFileTailer
from agent.phase3.runtime import Phase3Runtime
from agent.phase3.config import Phase3Config
from agent.memory.database import connect_database

try:
    from .test_phase3 import CLOCK, _fixture_bundle, _payload
except ImportError:
    from test_phase3 import CLOCK, _fixture_bundle, _payload


def _runtime_config(directory: Path) -> ForwardRuntimeConfig:
    runtime_root = directory / "runtime"
    return ForwardRuntimeConfig(
        runtime_root=str(runtime_root),
        repo_path=str(Path(__file__).resolve().parents[1]),
        python_path=os.environ.get("PYTHON", "python"),
        bundle_manifest=str(directory / "bundle.json"),
        model_bundle_path=str(directory / "model.json"),
        history_index_path=str(directory / "history.json"),
        telemetry_path=str(directory / "telemetry.jsonl"),
        runtime_db=str(runtime_root / "db" / "forward.sqlite"),
        primary_opportunity_path=str(directory / "opportunities.jsonl"),
        execution_diagnostic_path=str(directory / "telemetry.jsonl"),
        poll_interval_seconds=0.01,
    )


def _opportunity_payload(
    source_observation_id: str,
    *,
    timestamp: str,
    side: str = "LONG",
    features: dict[str, object] | None = None,
    entry_price: float = 100.0,
) -> dict[str, object]:
    """Tạo fixture primary đúng schema canonical opportunity, không dùng stream cũ."""

    return {
        "schema_version": "phase3-opportunity-observation/1",
        "source_observation_id": source_observation_id,
        "event_timestamp_utc": timestamp,
        "emitted_at_utc": timestamp,
        "source_strategy": "fixture-strategy",
        "source_strategy_version": "fixture/1",
        "symbol": "BTCUSD",
        "timeframe": "H1",
        "side": side,
        "source_audit_family": "V81",
        "source_event_type": "FLAT_LONG_ONLY" if side == "LONG" else "FLAT_SHORT_ONLY",
        "bar_state": "closed_bar",
        "candidate_type": "OPPORTUNITY_AUDIT",
        "context": {"features": features or {}},
        "execution_context": {"execution_eligible": False},
        "entry_price": entry_price,
        "hypothetical_entry_price": entry_price,
        "risk_distance": 1.0,
        "initial_sl_distance": 1.0,
        "hypothetical_initial_sl": entry_price - 1.0 if side == "LONG" else entry_price + 1.0,
        "build_valid": True,
    }


def _authorization(bundle: object, config: ForwardRuntimeConfig, *, sha: str = "test-sha") -> ForwardAuthorization:
    value = ForwardAuthorization(
        authorization_id="p3-auth-test",
        created_at_utc=CLOCK,
        authorized_git_sha=sha,
        bundle_id=bundle.bundle_id,
        bundle_version=bundle.bundle_version,
        phase1_fingerprint=bundle.phase1_fingerprint,
        historical_reference_cutoff=bundle.historical_reference_cutoff_utc,
        telemetry_schema="phase3-live-telemetry/1",
        telemetry_source_identity="fixture-source",
        model_fingerprint=bundle.model_fingerprint,
        similarity_fingerprint=bundle.similarity_fingerprint,
        runtime_db=str(config.db.resolve()),
        replay_parity_status="PASS",
        smoke_status="PASS",
        db_integrity_status="PASS",
        one_way_safety_status="PASS",
        execution_api_path_count=0,
    )
    return replace(value, authorization_hash=value.computed_hash())


class Phase31ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.model, cls.index, cls.rows = _fixture_bundle()

    def _write_assets(self, directory: Path, config: ForwardRuntimeConfig) -> None:
        Path(config.bundle_manifest).write_text(
            json.dumps(self.bundle.to_dict(include_model_payload=False), ensure_ascii=False), encoding="utf-8"
        )
        Path(config.model_bundle_path).write_text(
            json.dumps(self.model.to_dict(), ensure_ascii=False), encoding="utf-8"
        )
        artifact = {
            "schema": "phase3-historical-similarity-index/1",
            "bundle_id": self.bundle.bundle_id,
            "phase1_fingerprint": self.bundle.phase1_fingerprint,
            "source_dataset_fingerprint": self.bundle.phase1_fingerprint,
            "historical_reference_cutoff_utc": self.bundle.historical_reference_cutoff_utc,
            "similarity_version": self.bundle.similarity_version,
            "similarity_fingerprint": self.bundle.similarity_fingerprint,
            "similarity_config": dict(self.bundle.config_json["similarity_config"]),
            "row_count": len(self.index.rows),
            "rows_fingerprint": fingerprint(list(self.index.rows)),
            "rows": list(self.index.rows),
        }
        Path(config.history_index_path).write_text(
            json.dumps(artifact, ensure_ascii=False), encoding="utf-8"
        )

    def test_primary_source_cannot_fallback_to_diagnostic_stream(self) -> None:
        with TemporaryDirectory() as directory:
            config = _runtime_config(Path(directory))
            with self.assertRaisesRegex(ForwardControlError, "primary_opportunity_path"):
                replace(config, primary_opportunity_path=None)

    def test_required_live_metadata_is_enforced(self) -> None:
        payload = _payload()
        payload.pop("emitted_at_utc")
        with self.assertRaisesRegex(ValueError, "emitted_at_utc"):
            from agent.phase3.ingestion.validation import validate_telemetry_payload

            validate_telemetry_payload(payload)

    def test_truncation_is_distinguished_from_rotation(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.jsonl"
            first = json.dumps(_payload("first"), separators=(",", ":")) + "\n"
            second = json.dumps(_payload("second", timestamp="2024-01-01T00:00:01Z"), separators=(",", ":")) + "\n"
            path.write_text(first + second, encoding="utf-8")
            tailer = TelemetryFileTailer(path)
            initial = tailer.read_available()
            path.write_text(first, encoding="utf-8")
            truncated = tailer.read_available(
                offset_bytes=initial.next_offset,
                source_identity=initial.source_identity,
            )
            self.assertTrue(truncated.truncated)
            self.assertFalse(truncated.rotated)

    def test_os_lock_rejects_concurrent_and_recovers_stale_text(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "collector.lock"
            first = SingleInstanceLock(path)
            first.acquire(owner={"pid": os.getpid()})
            second = SingleInstanceLock(path)
            with self.assertRaises(Exception):
                second.acquire(owner={"pid": os.getpid()})
            first.release()
            path.write_text(json.dumps({"pid": 999999, "stale": True}), encoding="utf-8")
            recovered = SingleInstanceLock(path)
            recovered.acquire(owner={"pid": os.getpid()})
            recovered.release()

    def test_persistent_boundary_restart_rotation_and_idempotency(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = _runtime_config(root)
            source = Path(config.primary_opportunity)
            source.write_text(json.dumps(_opportunity_payload("historical", timestamp="2024-01-01T00:00:00Z"), separators=(",", ":")) + "\n", encoding="utf-8")
            auth = _authorization(self.bundle, config)
            db = connect_database(config.db)
            runtime = Phase3Runtime(
                db,
                self.bundle,
                model_bundle=self.model,
                similarity_index=self.index,
                config=Phase3Config(mode="FORWARD", bundle_id=self.bundle.bundle_id, telemetry_source="fixture", db_path=str(config.db), classification_min_resolved=1, regression_min_resolved=1),
                clock=lambda: CLOCK,
            )
            runtime.create_run("run-persistent", mode="FORWARD", started_at_utc="2024-01-01T00:00:00Z", git_sha="test-sha")
            collector = PersistentForwardCollector(
                config, auth, self.bundle, self.model, self.index,
                run_id="run-persistent", clock=lambda: "2024-01-01T00:00:03Z",
            )
            try:
                first = collector.run_once()
                self.assertEqual(first["records_seen"], 0)
                live = _opportunity_payload("live", timestamp="2024-01-01T00:00:01Z", entry_price=101.0)
                with source.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(live, separators=(",", ":")) + "\n")
                accepted = collector.run_once()
                self.assertEqual(accepted["records_seen"], 1)
            finally:
                collector._close_runtime()
            restarted = PersistentForwardCollector(
                config, auth, self.bundle, self.model, self.index,
                run_id="run-persistent", clock=lambda: "2024-01-01T00:00:03Z",
            )
            try:
                duplicate = restarted.run_once()
                self.assertEqual(duplicate["records_seen"], 0)
                source.write_text(
                    json.dumps(_opportunity_payload("rotated", timestamp="2024-01-01T00:00:02Z", entry_price=102.0), separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
                rotated = restarted.run_once()
                self.assertTrue(rotated["rotated"])
                self.assertEqual(rotated["records_seen"], 1)
            finally:
                restarted._close_runtime()
            try:
                count = sqlite3_count(config.db, "phase3_predictions")
                self.assertEqual(count, 2)
            finally:
                runtime.close()

    def test_new_authorized_run_rebinds_only_after_previous_run_stops(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = _runtime_config(root)
            source = Path(config.primary_opportunity)
            source.write_text(json.dumps(_opportunity_payload("old", timestamp=CLOCK), separators=(",", ":")) + "\n", encoding="utf-8")
            auth = _authorization(self.bundle, config)
            runtime = Phase3Runtime.open(
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
                clock=lambda: CLOCK,
            )
            try:
                runtime.create_run("run-old", mode="FORWARD", started_at_utc=CLOCK, git_sha="test-sha")
                old_collector = PersistentForwardCollector(
                    config, auth, self.bundle, self.model, self.index,
                    run_id="run-old", clock=lambda: "2024-01-01T00:00:03Z",
                )
                self.assertEqual(old_collector.run_once()["records_seen"], 0)
                old_collector._close_runtime()
                runtime.set_run_status("run-old", "STOPPED", stopped_at_utc="2024-01-01T00:00:04Z")
                runtime.create_run("run-new", mode="FORWARD", started_at_utc=CLOCK, git_sha="test-sha")
                new_collector = PersistentForwardCollector(
                    config, auth, self.bundle, self.model, self.index,
                    run_id="run-new", clock=lambda: "2024-01-01T00:00:05Z",
                )
                try:
                    result = new_collector.run_once()
                    self.assertEqual(result["records_seen"], 0)
                    state = json.loads(
                        runtime.connection.execute(
                            "SELECT rotation_state_json FROM phase3_ingest_offsets WHERE source_key = ?",
                            (str(source.resolve()),),
                        ).fetchone()[0]
                    )
                    self.assertEqual(state["run_id"], "run-new")
                    self.assertEqual(state["initial_source_offset"], source.stat().st_size)
                finally:
                    new_collector._close_runtime()
            finally:
                runtime.close()

    def test_authorization_manifest_hash_and_asset_gates(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = _runtime_config(root)
            self._write_assets(root, config)
            primary_payload = _payload("warmup")
            primary_payload.update(
                {
                    "schema_version": "phase3-opportunity-observation/1",
                    "source_observation_id": "warmup-opportunity",
                    "source_audit_family": "V81",
                    "source_event_type": "FLAT_LONG_ONLY",
                    "execution_context": {"execution_eligible": False},
                    "entry_price": 100.0,
                    "hypothetical_entry_price": 100.0,
                    "risk_distance": 1.0,
                    "initial_sl_distance": 1.0,
                    "hypothetical_initial_sl": 99.0,
                    "build_valid": True,
                }
            )
            config = replace(config, primary_opportunity_path=str(root / "opportunities.jsonl"))
            Path(config.primary_opportunity).write_text(json.dumps(primary_payload) + "\n", encoding="utf-8")
            write_forward_config(config, root / "forward.json")
            with self.assertRaises(Exception):
                validate_forward_authorization(root / "missing-authorization.json", config)
            gates = {
                "replay_parity_status": "PASS",
                "smoke_status": "PASS",
                "db_integrity_status": "PASS",
                "one_way_safety_status": "PASS",
                "execution_api_path_count": 0,
            }
            # Cô lập phép thử khỏi trạng thái dirty của checkout đang phát triển.
            with patch("agent.phase3.forward.tracked_worktree_clean", return_value=True), patch(
                "agent.phase3.forward.current_git_sha", return_value="test-sha"
            ):
                authorization = prepare_forward_authorization(config, gates=gates, now=CLOCK)
            self.assertEqual(authorization.to_dict()["schema"], AUTHORIZATION_SCHEMA)
            with patch("agent.phase3.forward.tracked_worktree_clean", return_value=True), patch(
                "agent.phase3.forward.current_git_sha", return_value="test-sha"
            ):
                loaded = validate_forward_authorization(config.authorization_path, config)
            self.assertEqual(loaded[0].authorization_id, authorization.authorization_id)
            tampered = json.loads(config.authorization_path.read_text(encoding="utf-8"))
            tampered["authorized_git_sha"] = "wrong"
            config.authorization_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(Exception):
                validate_forward_authorization(config.authorization_path, config)

    def test_runtime_status_is_machine_readable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = _runtime_config(root)
            config.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            config.heartbeat_path.write_text(json.dumps({
                "schema": "phase3-forward-heartbeat/1",
                "heartbeat_at_utc": CLOCK,
                "pid": os.getpid(),
                "run_id": "run-status",
                "collector_status": "RUNNING",
                "telemetry_status": "WAITING_FOR_SOURCE",
            }), encoding="utf-8")
            status = read_runtime_status(config, now="2024-01-01T00:00:02Z")
            self.assertTrue(status["collector_running"])
            self.assertEqual(status["run_id"], "run-status")
            self.assertFalse(status["live_execution_enabled"])
            self.assertEqual(status["execution_mode"], "NONE")


def sqlite3_count(path: Path, table: str) -> int:
    connection = connect_database(path)
    try:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
