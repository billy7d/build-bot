"""Contract tests cho Live Shadow Bridge và forward evidence Phase 3."""

from __future__ import annotations

import json
import sqlite3
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from agent.features.fingerprint import fingerprint
from agent.features.registry import FEATURE_ALLOWLIST, FEATURE_SET_VERSION
from agent.memory.database import apply_migrations, connect_database, integrity_status, migration_versions
from agent.phase3.bundle import BundleMismatchError, BundleMutationError, freeze_bundle, validate_bundle
from agent.phase3.config import Phase3Config, Phase3ConfigError
from agent.phase3.evaluation.metrics import evaluate_forward_records
from agent.phase3.evaluation.reporting import REQUIRED_PHASE3_STATUSES, write_phase3_reports
from agent.phase3.health import detect_drift
from agent.phase3.ingestion.canonicalize import canonicalize_event
from agent.phase3.ingestion.file_tail import TelemetryFileTailer
from agent.phase3.ingestion.validation import TelemetryValidationError, validate_telemetry_payload
from agent.phase3.models import TelemetryEvent
from agent.phase3.outcomes.resolver import resolve_prediction_outcome
from agent.phase3.runtime import Phase3Runtime
from agent.phase3.scoring.bridge import Phase2ScoringBridge
from agent.phase3.scoring.parity import run_replay_parity
from agent.scoring.train import ModelBundle, ModelConfig, train_models
from agent.similarity.index import HistoricalSimilarityIndex
from agent.similarity.models import SimilarityConfig


BASE_SHA = "1bbdfafa5f516a3adab262dae14b618fc5777764"
CLOCK = "2024-01-01T00:00:01Z"


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _features(index: int, side: str) -> dict[str, Any]:
    """Tạo bộ feature event-time đầy đủ cho fixture nhỏ."""

    return {
        "rsi": 50.0 + index,
        "atr_percent": 0.5 + index * 0.01,
        "spread_r": 0.1 + index * 0.005,
        "return_std_20": 0.01 + index * 0.0005,
        "return_std_rank": 45.0 + index,
        "price_std_20": 2.0 + index * 0.1,
        "price_std_100": 3.0 + index * 0.1,
        "price_std_pct_20": 2.0 + index * 0.1,
        "std_ratio_20_100": 0.7 + index * 0.01,
        "price_z20": 0.2 + index * 0.02,
        "price_abs_z20": 0.2 + index * 0.02,
        "rsi_std_20": 4.0 + index * 0.1,
        "rsi_std_rank": 55.0 + index,
        "atr_return_std_ratio": 1.5 + index * 0.02,
        "atr_return_std_rank": 60.0 + index,
        "entry_atr_rank": 50.0 + index,
        "entry_efficiency_20": 0.2 + index * 0.01,
        "initial_sl_atr": 2.0 + index * 0.05,
        "d1_regime_score": 0.7 if side == "LONG" else -0.7,
        "h4_regime_score": 0.7 if side == "LONG" else -0.7,
        "composite_regime_score": 0.7 if side == "LONG" else -0.7,
        "symbol": "BTCUSD",
        "timeframe": "H1",
        "side": side,
        "strategy_version": "V26",
        "d1_bias": "BULL" if side == "LONG" else "BEAR",
        "h4_bias": "BULL" if side == "LONG" else "BEAR",
        "h1_bias": "BULL" if side == "LONG" else "BEAR",
        "source_regime": "TRENDING",
    }


def _historical_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(8):
        side = "LONG" if index % 2 == 0 else "SHORT"
        timestamp = datetime(2023, 1, 1, tzinfo=UTC) + timedelta(days=index)
        plus = index % 2 == 0
        rows.append({
            "canonical_opportunity_id": f"hist-{index}",
            "timestamp_utc": _iso(timestamp),
            "symbol": "BTCUSD",
            "timeframe": "H1",
            "side": side,
            "features": _features(index, side),
            "labels": {
                "resolved": True,
                "shadow_first_hit": "PLUS_1R" if plus else "MINUS_1R",
                "shadow_plus_1r_first": plus,
                "shadow_minus_1r_first": not plus,
                "shadow_return_6bar_r": 0.4 if plus else -0.4,
                "shadow_return_12bar_r": 0.5 if plus else -0.5,
                "shadow_return_24bar_r": 0.6 if plus else -0.6,
                "shadow_return_48bar_r": 0.7 if plus else -0.7,
                "outcome_timestamp_utc": _iso(timestamp + timedelta(hours=48)),
            },
        })
    return rows


def _fixture_bundle() -> tuple[Any, Any, HistoricalSimilarityIndex, list[dict[str, Any]]]:
    rows = _historical_rows()
    splits = {row["canonical_opportunity_id"]: "TRAIN" for row in rows}
    model = train_models(
        rows,
        splits,
        dataset_fingerprint="phase1-fixture",
        config=ModelConfig(logistic_iterations=20, calibration_iterations=20, min_training_labels=2),
    )
    similarity_config = SimilarityConfig(
        top_k=5,
        min_neighbors=1,
        min_feature_overlap=1,
        side_mode="any",
        regime_mode="none",
    )
    bundle = freeze_bundle(
        phase1_fingerprint="phase1-fixture",
        phase2_base_sha=BASE_SHA,
        feature_manifest={
            "feature_set_version": FEATURE_SET_VERSION,
            "feature_fingerprint": "feature-fixture",
            "preprocessing_fingerprint": model.preprocessor.to_dict()["preprocessing_fingerprint"],
            "allowlist": sorted(FEATURE_ALLOWLIST),
        },
        regime_manifest={
            "regime_version": "regime/1",
            "regime_fingerprint": "regime-fixture",
            "similarity_version": "similarity/1",
            "threshold_values": {
                "trend_score_threshold": 0.5,
                "trend_abs_z_threshold": 1.5,
                "atr_volatility_low": 0.4,
                "atr_volatility_high": 0.7,
                "volatility_low": 0.4,
                "volatility_high": 0.7,
                "liquidity_spread_stressed": 0.5,
            },
        },
        model_manifest={"model_version": "scoring/1"},
        model_bundle=model.to_dict(),
        similarity_config=similarity_config.to_dict(),
        historical_reference_cutoff_utc="2023-12-31T00:00:00Z",
        seed=42,
        created_at_utc="2026-09-15T00:00:00Z",
    )
    vectors = model.preprocessor.transform(rows)
    index = HistoricalSimilarityIndex([
        {
            **row,
            "regime": "TREND_NORMAL_VOL",
            "feature_vector": vectors[row["canonical_opportunity_id"]],
        }
        for row in rows
    ])
    return bundle, model, index, rows


def _payload(source_event_id: str = "live-1", *, timestamp: str = "2024-01-01T00:00:00Z", side: str = "LONG", features: dict[str, Any] | None = None, bar_state: str | None = "closed_bar") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "phase3-live-telemetry/1",
        "source_event_id": source_event_id,
        "event_timestamp": timestamp,
        "symbol": "BTCUSD",
        "timeframe": "H1",
        "side": side,
        "context": {
            "features": features if features is not None else _features(8, side),
            "entry_price": 100.0,
            "risk_distance": 1.0,
        },
    }
    if bar_state is not None:
        payload["bar_state"] = bar_state
    return payload


def _runtime(path: Path, bundle: Any, model: Any, index: HistoricalSimilarityIndex, *, mode: str = "FORWARD") -> Phase3Runtime:
    connection = connect_database(path)
    config = Phase3Config(mode=mode, bundle_id=bundle.bundle_id, classification_min_resolved=1, regression_min_resolved=1)
    return Phase3Runtime(
        connection,
        bundle,
        model_bundle=model,
        similarity_index=index,
        config=config,
        clock=lambda: CLOCK,
    )


class Phase3ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.model, cls.index, cls.rows = _fixture_bundle()

    def test_migration_adds_phase3_schema_and_integrity(self) -> None:
        with TemporaryDirectory() as directory:
            connection = connect_database(Path(directory) / "memory.db")
            apply_migrations(connection)
            self.assertEqual(migration_versions(connection)[-1], "008")
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'phase3_%'")
            }
            self.assertTrue({
                "phase3_shadow_bundles", "phase3_forward_runs", "phase3_ingest_offsets",
                "phase3_forward_events", "phase3_feature_snapshots", "phase3_predictions",
                "phase3_outcomes", "phase3_health_events", "phase3_evaluation_snapshots",
            } <= tables)
            self.assertTrue(integrity_status(connection)["integrity_ok"])
            self.assertTrue(integrity_status(connection)["foreign_key_ok"])
            connection.close()

    def test_bundle_freeze_is_deterministic_and_review_manifest_omits_model_payload(self) -> None:
        manifest = self.bundle.to_dict(include_model_payload=False)
        self.assertNotIn("model_bundle", manifest["config"])
        self.assertEqual(validate_bundle(manifest).bundle_id, self.bundle.bundle_id)
        again, _, _, _ = _fixture_bundle()
        self.assertEqual(again.bundle_id, self.bundle.bundle_id)
        changed = replace(self.bundle, config_json={**self.bundle.config_json, "seed": 99})
        with self.assertRaises(BundleMutationError):
            validate_bundle(changed)
        changed_model_config = dict(self.bundle.config_json)
        changed_model = dict(self.model.to_dict())
        changed_model["seed"] = 99
        changed_model_config["model_bundle"] = changed_model
        changed_model_config["model_payload_fingerprint"] = fingerprint(changed_model)
        changed_model_bundle = replace(self.bundle, bundle_id="", config_json=changed_model_config)
        self.assertNotEqual(self.bundle.bundle_id, changed_model_bundle.recompute_id())
        changed_cutoff = replace(self.bundle, bundle_id="", historical_reference_cutoff_utc="2023-12-30T00:00:00Z")
        self.assertNotEqual(self.bundle.bundle_id, changed_cutoff.recompute_id())
        with self.assertRaises(BundleMismatchError):
            validate_bundle(self.bundle, expected_phase1_fingerprint="wrong-phase1")
        payload_without_fingerprint = dict(self.bundle.config_json)
        payload_without_fingerprint["model_payload_fingerprint"] = None
        with self.assertRaises(BundleMutationError):
            validate_bundle(replace(self.bundle, config_json=payload_without_fingerprint))

    def test_config_cannot_enable_execution(self) -> None:
        with self.assertRaises(Phase3ConfigError):
            Phase3Config(execution_mode="LIVE")
        self.assertFalse(Phase3Config().live_execution_enabled)

    def test_telemetry_schema_closed_world_and_availability_gate(self) -> None:
        event = validate_telemetry_payload(_payload())
        self.assertIsInstance(event, TelemetryEvent)
        self.assertEqual(event.bar_state, "closed_bar")
        bad_future = _payload()
        bad_future["context"]["future_price"] = 101.0
        with self.assertRaisesRegex(TelemetryValidationError, "future/outcome"):
            validate_telemetry_payload(bad_future)
        bad_unknown = _payload()
        bad_unknown["context"]["features"]["not_registered"] = 1
        with self.assertRaises(TelemetryValidationError):
            validate_telemetry_payload(bad_unknown)
        bad_context = _payload()
        bad_context["context"]["unregistered_context"] = 1
        with self.assertRaisesRegex(TelemetryValidationError, "unknown context"):
            validate_telemetry_payload(bad_context)
        bad_available = _payload()
        bad_available["available_at_utc"] = "2024-01-01T00:00:02Z"
        with self.assertRaisesRegex(TelemetryValidationError, "availability"):
            validate_telemetry_payload(bad_available)

    def test_bridge_parity_and_missing_index_fail_closed(self) -> None:
        event = validate_telemetry_payload(_payload())
        canonical = canonicalize_event(event)
        bridge = Phase2ScoringBridge(self.bundle, model_bundle=self.model, similarity_index=self.index)
        expected = bridge.score_event(canonical)[1]
        parity = run_replay_parity([canonical], {event.source_event_id: expected}, bridge)
        self.assertTrue(parity.passed)
        self.assertEqual(bridge.score_event(event)[1].score_status, expected.score_status)
        for neighbor in expected.similarity_summary.get("neighbors", []):
            self.assertLess(neighbor["timestamp_utc"], event.event_timestamp_utc)
        no_index = Phase2ScoringBridge(self.bundle, model_bundle=self.model)
        _, score = no_index.score_event(canonical)
        self.assertEqual(score.score_status, "NO_OPINION")
        self.assertEqual(score.abstention_reason, "HISTORICAL_INDEX_UNAVAILABLE")
        changed_model = dict(self.model.to_dict())
        changed_model["seed"] = 99
        with self.assertRaises(BundleMismatchError):
            Phase2ScoringBridge(
                self.bundle,
                model_bundle=ModelBundle.from_dict(changed_model),
                similarity_index=self.index,
            )

    def test_runtime_idempotency_restart_and_prediction_hash(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "memory.db"
            runtime = _runtime(db_path, self.bundle, self.model, self.index)
            run = runtime.create_run("run-idempotent", started_at_utc="2024-01-01T00:00:00Z")
            self.assertEqual(run["mode"], "FORWARD")
            responses = [runtime.process_payload("run-idempotent", _payload("same-event")) for _ in range(10)]
            self.assertEqual(responses[0]["status"], "PREDICTION_COMMITTED")
            self.assertTrue(all(item["status"] == "REJECTED_DUPLICATE" for item in responses[1:]))
            self.assertEqual(runtime.status("run-idempotent")["counts"]["predictions"], 1)
            prediction = runtime.connection.execute("SELECT prediction_hash FROM phase3_predictions").fetchone()
            self.assertTrue(prediction[0])
            runtime.close()

            restarted = _runtime(db_path, self.bundle, self.model, self.index)
            restarted.create_run("run-idempotent", started_at_utc="2024-01-01T00:00:00Z")
            duplicate = restarted.process_payload("run-idempotent", _payload("same-event"))
            self.assertEqual(duplicate["status"], "REJECTED_DUPLICATE")
            self.assertEqual(restarted.status("run-idempotent")["counts"]["predictions"], 1)
            restarted.close()

    def test_malformed_missing_identity_and_forward_cutoff_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = _runtime(Path(directory) / "memory.db", self.bundle, self.model, self.index)
            runtime.create_run("run-invalid", started_at_utc="2024-01-01T00:00:01Z")
            unknown_schema = _payload("unknown-schema")
            unknown_schema["schema_version"] = "phase3-live-telemetry/999"
            missing_id = _payload("missing-id")
            missing_id.pop("source_event_id")
            missing_timestamp = _payload("missing-timestamp")
            missing_timestamp.pop("event_timestamp")
            self.assertEqual(runtime.process_payload("run-invalid", unknown_schema)["status"], "REJECTED_SCHEMA")
            self.assertEqual(runtime.process_payload("run-invalid", missing_id)["status"], "REJECTED_SCHEMA")
            self.assertEqual(runtime.process_payload("run-invalid", missing_timestamp)["status"], "REJECTED_SCHEMA")
            before_start = runtime.process_payload(
                "run-invalid", _payload("before-start", timestamp="2024-01-01T00:00:00Z")
            )
            self.assertEqual(before_start["status"], "REJECTED_STALE")
            self.assertEqual(before_start["reason"], "BEFORE_FORWARD_START")
            runtime.set_run_status("run-invalid", "STOPPED", stopped_at_utc="2024-01-01T00:00:01Z")
            stopped = runtime.process_payload("run-invalid", _payload("after-stop"))
            self.assertEqual(stopped["status"], "REJECTED_CONFLICT")
            runtime.close()

    def test_closed_bar_future_and_out_of_order_rejections(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = _runtime(Path(directory) / "memory.db", self.bundle, self.model, self.index, mode="SMOKE")
            runtime.create_run("run-gates", mode="SMOKE", started_at_utc="2024-01-01T00:00:00Z")
            forming = runtime.process_payload("run-gates", _payload("forming", bar_state="forming_bar"))
            self.assertEqual(forming["status"], "REJECTED_SCHEMA")
            future = runtime.process_payload("run-gates", _payload("future", timestamp="2024-01-01T00:01:00Z"))
            self.assertEqual(future["status"], "REJECTED_STALE")
            first = runtime.process_payload("run-gates", _payload("ordered-1", timestamp="2024-01-01T00:00:00Z"))
            older = runtime.process_payload("run-gates", _payload("ordered-0", timestamp="2023-12-31T23:59:00Z"))
            self.assertEqual(first["status"], "PREDICTION_COMMITTED")
            self.assertEqual(older["status"], "REJECTED_STALE")
            runtime.close()

    def test_ood_and_missing_features_abstain(self) -> None:
        event = validate_telemetry_payload(_payload(features={**_features(8, "LONG"), "rsi": 9999.0}))
        _, ood_score = Phase2ScoringBridge(self.bundle, model_bundle=self.model, similarity_index=self.index).score_event(event)
        self.assertEqual(ood_score.score_status, "NO_OPINION")
        self.assertEqual(ood_score.abstention_reason, "OUT_OF_DISTRIBUTION")
        missing = validate_telemetry_payload(_payload(features={}))
        _, missing_score = Phase2ScoringBridge(self.bundle, model_bundle=self.model, similarity_index=self.index).score_event(missing)
        self.assertEqual(missing_score.score_status, "NO_OPINION")
        self.assertEqual(missing_score.abstention_reason, "INSUFFICIENT_FEATURES")

    def test_delayed_outcome_requires_prediction_before_observation(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "memory.db"
            runtime = _runtime(db_path, self.bundle, self.model, self.index)
            runtime.create_run("run-outcome", started_at_utc="2024-01-01T00:00:00Z")
            committed = runtime.process_payload("run-outcome", _payload("outcome-event"))
            event_id = committed["forward_event_id"]
            bars = [
                {
                    "bar_id": f"bar-{index}",
                    "timestamp_utc": _iso(datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=index)),
                    "high": 101.0,
                    "low": 99.5,
                    "close": 100.5,
                }
                for index in range(1, 25)
            ]
            resolution = runtime.resolve_outcomes("run-outcome", {event_id: bars}, observed_at_utc="2024-01-02T00:00:00Z")[event_id]
            self.assertEqual(resolution["status"], "RESOLVED")
            self.assertEqual(resolution["classification_label"], 1)
            metrics = runtime.evaluate("run-outcome")
            self.assertEqual(metrics["resolved_sample_count"], 1)
            self.assertEqual(metrics["forward_predictive_edge_status"], "INSUFFICIENT_DATA")
            self.assertEqual(runtime.status("run-outcome")["counts"]["resolved_outcomes"], 1)
            second = runtime.resolve_outcomes("run-outcome", {event_id: bars}, observed_at_utc="2024-01-02T00:00:00Z")
            self.assertEqual(second, {})
            runtime.close()

    def test_prediction_after_observed_outcome_is_invalid(self) -> None:
        prediction = {
            "source_event_timestamp_utc": "2024-01-01T00:00:00Z",
            "prediction_committed_at_utc": "2024-01-01T12:00:00Z",
            "side": "LONG",
        }
        bars = [{"timestamp_utc": "2024-01-01T06:00:00Z", "high": 101.0, "low": 99.5, "close": 100.5}]
        result = resolve_prediction_outcome(
            prediction,
            bars,
            context={"entry_price": 100.0, "risk_distance": 1.0},
            observed_at_utc="2024-01-02T00:00:00Z",
        )
        self.assertEqual(result.status, "INVALID")
        self.assertEqual(result.incomplete_reason, "PREDICTION_AFTER_OUTCOME")
        no_bars = resolve_prediction_outcome(
            prediction,
            [],
            context={"entry_price": 100.0, "risk_distance": 1.0},
            observed_at_utc="2024-01-01T06:00:00Z",
        )
        self.assertEqual(no_bars.status, "INVALID")
        self.assertEqual(no_bars.incomplete_reason, "PREDICTION_AFTER_OUTCOME")

    def test_prediction_and_outcome_rows_are_append_only(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = _runtime(Path(directory) / "memory.db", self.bundle, self.model, self.index)
            runtime.create_run("run-append", started_at_utc="2024-01-01T00:00:00Z")
            committed = runtime.process_payload("run-append", _payload("append-event"))
            prediction_id = committed["prediction_id"]
            with self.assertRaises(sqlite3.DatabaseError):
                runtime.connection.execute("UPDATE phase3_predictions SET score_status='OK' WHERE prediction_id=?", (prediction_id,))
            with self.assertRaises(sqlite3.DatabaseError):
                runtime.connection.execute("DELETE FROM phase3_predictions WHERE prediction_id=?", (prediction_id,))
            event_id = committed["forward_event_id"]
            bars = [{
                "timestamp_utc": _iso(datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=index)),
                "high": 101.0, "low": 99.5, "close": 100.5,
            } for index in range(1, 25)]
            runtime.resolve_outcomes("run-append", {event_id: bars}, observed_at_utc="2024-01-02T00:00:00Z")
            with self.assertRaises(sqlite3.DatabaseError):
                runtime.connection.execute("UPDATE phase3_outcomes SET status='INCOMPLETE' WHERE forward_event_id=?", (event_id,))
            with self.assertRaises(sqlite3.DatabaseError):
                runtime.connection.execute("DELETE FROM phase3_outcomes WHERE forward_event_id=?", (event_id,))
            runtime.close()

    def test_file_tail_partial_line_and_rotation(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.jsonl"
            first = json.dumps(_payload("file-1"), separators=(",", ":"))
            path.write_text(first + "\n", encoding="utf-8")
            tailer = TelemetryFileTailer(path)
            initial = tailer.read_available()
            self.assertEqual(len(initial.records), 1)
            unchanged = tailer.read_available(offset_bytes=initial.next_offset, source_identity=initial.source_identity)
            self.assertEqual(len(unchanged.records), 0)
            partial = json.dumps(_payload("file-2"), separators=(",", ":"))
            with path.open("ab") as stream:
                stream.write(partial.encode("utf-8"))
            waiting = tailer.read_available(offset_bytes=initial.next_offset, source_identity=initial.source_identity)
            self.assertTrue(waiting.partial_final_line)
            self.assertEqual(len(waiting.records), 0)
            with path.open("ab") as stream:
                stream.write(b"\n")
            complete = tailer.read_available(offset_bytes=initial.next_offset, source_identity=initial.source_identity)
            self.assertEqual(len(complete.records), 1)
            path.write_text(json.dumps(_payload("file-rotated"), separators=(",", ":")) + "\n", encoding="utf-8")
            rotated = tailer.read_available(offset_bytes=complete.next_offset, source_identity=complete.source_identity)
            self.assertTrue(rotated.rotated)
            self.assertEqual(len(rotated.records), 1)

    def test_metrics_align_missing_labels_and_predictions(self) -> None:
        records = [
            {
                "run_mode": "FORWARD", "forward_valid": 1, "outcome_status": "RESOLVED",
                "prediction_committed_at_utc": "2024-01-01T00:00:01Z", "outcome_observed_at_utc": "2024-01-02T00:00:00Z",
                "classification_label": None, "probability_plus1_before_minus1": None,
                "expected_return_24bar_r": None, "return_24bar_r": 0.1,
                "side": "LONG", "regime": "TREND_NORMAL_VOL", "symbol": "BTCUSD", "timeframe": "H1",
            },
            {
                "run_mode": "FORWARD", "forward_valid": 1, "outcome_status": "RESOLVED",
                "prediction_committed_at_utc": "2024-01-01T00:00:01Z", "outcome_observed_at_utc": "2024-01-03T00:00:00Z",
                "classification_label": 1, "probability_plus1_before_minus1": 0.8,
                "expected_return_24bar_r": 0.3, "return_24bar_r": 0.2,
                "side": "SHORT", "regime": "RANGE_NORMAL_VOL", "symbol": "BTCUSD", "timeframe": "H1",
            },
        ]
        result = evaluate_forward_records(records, classification_min_resolved=1, regression_min_resolved=1, bootstrap_iterations=10)
        self.assertEqual(result["classification"]["logistic_phase2"]["count"], 1)
        self.assertEqual(result["regression"]["ridge_phase2"]["count"], 1)

    def test_health_drift_and_resource_observability_are_read_only(self) -> None:
        historical = [
            {"side": "LONG", "regime": "TREND_NORMAL_VOL", "confidence": "MEDIUM", "ood_status": "IN_DISTRIBUTION", "features": {"rsi": 50.0}, "similarity_summary": {"neighbors": [{"distance": 0.5}]}},
            {"side": "SHORT", "regime": "RANGE_NORMAL_VOL", "confidence": "MEDIUM", "ood_status": "IN_DISTRIBUTION", "features": {"rsi": 51.0}, "similarity_summary": {"neighbors": [{"distance": 0.6}]}},
        ]
        forward = [
            {"side": "LONG", "regime": "TREND_HIGH_VOL", "confidence": "LOW", "ood_status": "OUT_OF_DISTRIBUTION", "features": {"rsi": 999.0}, "similarity_summary": {"neighbors": [{"distance": 4.0}]}},
            {"side": "LONG", "regime": "TREND_HIGH_VOL", "confidence": "LOW", "ood_status": "OUT_OF_DISTRIBUTION", "features": {"rsi": 1000.0}, "similarity_summary": {"neighbors": [{"distance": 5.0}]}},
        ]
        drift = detect_drift(historical, forward, feature_names=("rsi",))
        self.assertEqual(drift["status"], "DRIFT_SEVERE")
        self.assertEqual(drift["auto_retrain"], False)
        self.assertEqual(drift["auto_reference_update"], False)
        with TemporaryDirectory() as directory:
            runtime = _runtime(Path(directory) / "memory.db", self.bundle, self.model, self.index)
            runtime.create_run("run-health", started_at_utc="2024-01-01T00:00:00Z")
            runtime.process_payload("run-health", _payload("health-event"))
            status = runtime.status("run-health")
            self.assertIn("resource_safety", status)
            self.assertFalse(status["resource_safety"]["unbounded_backlog_detected"])
            self.assertIsNotNone(status["health"]["latency_p50_ms"])
            runtime.close()

    def test_phase3_has_no_execution_api_names(self) -> None:
        root = Path(__file__).resolve().parents[1] / "phase3"
        source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
        for forbidden in ("order_send", "order_modify", "order_cancel", "position_modify", "trade_request"):
            self.assertNotIn(forbidden, source)

    def test_report_set_contains_required_statuses_and_zero_forward_sample(self) -> None:
        with TemporaryDirectory() as directory:
            report = write_phase3_reports(Path(directory), self.bundle)
            self.assertEqual(set(REQUIRED_PHASE3_STATUSES), set(report["statuses"]))
            self.assertEqual(report["FORWARD_SAMPLE_COUNT"], 0)
            self.assertEqual(report["FORWARD_COLLECTION_STATUS"], "READY")
            self.assertEqual(report["FORWARD_PREDICTIVE_EDGE_STATUS"], "INSUFFICIENT_DATA")
            self.assertEqual(report["LIVE_EXECUTION_ENABLED"], "NO")
            self.assertFalse(report["runtime_status"]["resource_safety"]["unbounded_backlog_detected"])
            required_files = {
                "phase3_report.md", "architecture_validation.md", "shadow_bundle_manifest.json",
                "replay_parity_report.json", "safety_validation.md", "forward_run_manifest.json",
                "bridge_health_report.md", "forward_validation.json", "forward_validation.md",
            }
            self.assertTrue(required_files <= {path.name for path in Path(directory).iterdir()})


if __name__ == "__main__":
    unittest.main()
