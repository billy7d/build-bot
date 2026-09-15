"""Kiểm thử canonical opportunity telemetry trước khi mở FORWARD."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.phase3.ingestion.opportunity import (
    CANONICALIZER_FINGERPRINT,
    OpportunityValidationError,
    canonicalize_observation,
    validate_opportunity_payload,
)
from agent.phase3.config import Phase3Config
from agent.phase3.runtime import Phase3Runtime
from agent.memory.database import connect_database

try:
    from .test_phase3 import CLOCK, _features, _fixture_bundle
except ImportError:
    from test_phase3 import CLOCK, _features, _fixture_bundle


def _opportunity(
    observation_id: str,
    *,
    audit_family: str = "V81",
    event_type: str = "FLAT_LONG_ONLY",
    timestamp: str = "2023-01-01T00:00:00Z",
    side: str = "LONG",
    entry: float | None = 100.0,
    valid: bool = True,
) -> dict[str, object]:
    features = _features(8, side)
    features["strategy_version"] = "V26"
    payload: dict[str, object] = {
        "schema_version": "phase3-opportunity-observation/1",
        "source_observation_id": observation_id,
        "event_timestamp_utc": timestamp,
        "emitted_at_utc": timestamp,
        "source_strategy": "Mentor_RSI_MTF",
        "source_strategy_version": "V26",
        "symbol": "BTCUSD",
        "timeframe": "H1",
        "side": side,
        "source_audit_family": audit_family,
        "source_event_type": event_type,
        "bar_state": "closed_bar",
        "context": {"features": features},
        "execution_context": {
            "blocked_reason": "NONE",
            "execution_eligible": False,
            "position_state": "FLAT",
        },
        "entry_price": entry,
        "hypothetical_entry_price": entry,
        "risk_distance": 1.0 if entry is not None else None,
        "initial_sl_distance": 1.0 if entry is not None else None,
        "hypothetical_initial_sl": (entry - 1.0) if side == "LONG" and entry is not None else (entry + 1.0 if entry is not None else None),
        "build_valid": valid,
    }
    if not valid:
        payload["build_reason"] = "MISSING_HYPOTHETICAL_ENTRY"
    return payload


class CanonicalOpportunityTelemetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.model, cls.index, _ = _fixture_bundle()

    def _runtime(self, path: Path) -> Phase3Runtime:
        return Phase3Runtime.open(
            path,
            self.bundle,
            model_bundle=self.model,
            similarity_index=self.index,
            config=Phase3Config(
                mode="SMOKE",
                bundle_id=self.bundle.bundle_id,
                classification_min_resolved=1,
                regression_min_resolved=1,
            ),
        )

    def test_phase1_canonicalizer_is_reused_and_fingerprint_is_stable(self) -> None:
        first = canonicalize_observation(validate_opportunity_payload(_opportunity("v81")))
        second = canonicalize_observation(
            validate_opportunity_payload(
                _opportunity("v82", audit_family="V82", event_type="LONG_ONLY", timestamp="2023-01-01T01:00:00Z")
            )
        )
        self.assertEqual(first.canonical_opportunity_id, second.canonical_opportunity_id)
        self.assertEqual(first.canonicalizer_version, "canonical-opportunity/1")
        self.assertEqual(first.canonicalizer_fingerprint, CANONICALIZER_FINGERPRINT)

    def test_future_field_attack_is_rejected_before_storage(self) -> None:
        payload = _opportunity("future")
        execution_context = dict(payload["execution_context"])
        execution_context["return_24bar"] = 1.0
        payload["execution_context"] = execution_context
        with self.assertRaisesRegex(OpportunityValidationError, "future/outcome"):
            validate_opportunity_payload(payload)

    def test_unknown_execution_context_is_rejected(self) -> None:
        payload = _opportunity("unknown-context")
        execution_context = dict(payload["execution_context"])
        execution_context["unregistered_state"] = "value"
        payload["execution_context"] = execution_context
        with self.assertRaisesRegex(OpportunityValidationError, "unknown execution_context"):
            validate_opportunity_payload(payload)

    def test_overlap_collapses_to_one_canonical_prediction(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = self._runtime(Path(directory) / "phase3.sqlite")
            try:
                runtime.create_run("canonical-run", mode="SMOKE", started_at_utc=CLOCK)
                first = runtime.process_payload("canonical-run", _opportunity("v81"), source="fixture-v81")
                overlap = runtime.process_payload(
                    "canonical-run",
                    _opportunity("v82", audit_family="V82", event_type="LONG_ONLY", timestamp="2023-01-01T01:00:00Z"),
                    source="fixture-v82",
                )
                self.assertEqual(first["status"], "PREDICTION_COMMITTED")
                self.assertEqual(overlap["status"], "DUPLICATE_COLLAPSED")
                self.assertEqual(first["canonical_opportunity_id"], overlap["canonical_opportunity_id"])
                status = runtime.status("canonical-run")
                self.assertEqual(status["counts"]["raw_observation_count"], 2)
                self.assertEqual(status["counts"]["canonical_opportunity_count"], 1)
                self.assertEqual(status["counts"]["duplicate_collapse_count"], 1)
                self.assertEqual(status["counts"]["forward_sample_count"], 1)
                self.assertEqual(status["counts"]["predictions"], 1)
            finally:
                runtime.close()

    def test_different_sides_same_timestamp_keep_separate_identities(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = self._runtime(Path(directory) / "phase3.sqlite")
            try:
                runtime.create_run("side-run", mode="SMOKE", started_at_utc=CLOCK)
                long_result = runtime.process_payload(
                    "side-run",
                    _opportunity("same-time-long", timestamp="2023-01-01T00:00:00Z", side="LONG", entry=100.0),
                )
                short_result = runtime.process_payload(
                    "side-run",
                    _opportunity(
                        "same-time-short",
                        timestamp="2023-01-01T00:00:00Z",
                        side="SHORT",
                        event_type="FLAT_SHORT_ONLY",
                        entry=100.0,
                    ),
                )
                self.assertEqual(long_result["status"], "PREDICTION_COMMITTED")
                self.assertEqual(short_result["status"], "PREDICTION_COMMITTED")
                self.assertNotEqual(long_result["canonical_opportunity_id"], short_result["canonical_opportunity_id"])
                self.assertEqual(runtime.status("side-run")["counts"]["predictions"], 2)
            finally:
                runtime.close()

    def test_flat_control_and_blocked_opportunities_are_preserved(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = self._runtime(Path(directory) / "phase3.sqlite")
            try:
                runtime.create_run("semantic-run", mode="SMOKE", started_at_utc=CLOCK)
                payloads = (
                    _opportunity("flat", entry=100.0),
                    _opportunity("control", audit_family="V82", event_type="LONG_ONLY", timestamp="2023-01-01T01:00:00Z", entry=101.0),
                    _opportunity("blocked", audit_family="V82", event_type="BLOCKED_OPPOSITE", timestamp="2023-01-01T02:00:00Z", side="SHORT", entry=102.0),
                )
                results = [runtime.process_payload("semantic-run", payload) for payload in payloads]
                self.assertEqual([result["status"] for result in results], ["PREDICTION_COMMITTED"] * 3)
                self.assertEqual(runtime.status("semantic-run")["counts"]["predictions"], 3)
            finally:
                runtime.close()

    def test_out_of_order_observations_are_accepted_and_canonicalized(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = self._runtime(Path(directory) / "phase3.sqlite")
            try:
                runtime.create_run("order-run", mode="SMOKE", started_at_utc=CLOCK)
                later = runtime.process_payload(
                    "order-run",
                    _opportunity("later", timestamp="2023-01-01T02:00:00Z", entry=102.0),
                )
                earlier = runtime.process_payload(
                    "order-run",
                    _opportunity("earlier", timestamp="2023-01-01T01:00:00Z", entry=103.0),
                )
                self.assertEqual(later["status"], "PREDICTION_COMMITTED")
                self.assertEqual(earlier["status"], "PREDICTION_COMMITTED")
                self.assertEqual(runtime.status("order-run")["counts"]["predictions"], 2)
            finally:
                runtime.close()

    def test_invalid_build_is_preserved_without_fabricated_prediction(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = self._runtime(Path(directory) / "phase3.sqlite")
            try:
                runtime.create_run("invalid-run", mode="SMOKE", started_at_utc=CLOCK)
                result = runtime.process_payload(
                    "invalid-run",
                    _opportunity("invalid", entry=None, valid=False),
                    source="fixture",
                )
                self.assertEqual(result["status"], "INVALID")
                self.assertEqual(runtime.status("invalid-run")["counts"]["invalid_count"], 1)
                self.assertEqual(runtime.status("invalid-run")["counts"]["predictions"], 0)
                row = runtime.connection.execute(
                    "SELECT build_valid, build_reason, status FROM phase3_opportunity_observations WHERE run_id = ?",
                    ("invalid-run",),
                ).fetchone()
                self.assertEqual(tuple(row), (0, "MISSING_HYPOTHETICAL_ENTRY", "INVALID"))
            finally:
                runtime.close()

    def test_diagnostic_stream_is_not_primary_sample(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = self._runtime(Path(directory) / "phase3.sqlite")
            try:
                runtime.create_run("mixed-run", mode="SMOKE", started_at_utc=CLOCK)
                diagnostic = {
                    "schema_version": "phase3-live-telemetry/1",
                    "source_event_id": "diagnostic-1",
                    "event_timestamp": "2023-01-01T00:00:00Z",
                    "emitted_at_utc": "2023-01-01T00:00:00Z",
                    "source_strategy": "Mentor_RSI_MTF",
                    "source_strategy_version": "V26",
                    "symbol": "BTCUSD",
                    "timeframe": "H1",
                    "side": "LONG",
                    "context": {"features": _features(8, "LONG")},
                }
                runtime.process_payload("mixed-run", diagnostic, source="diagnostic")
                runtime.process_payload("mixed-run", _opportunity("primary"), source="primary")
                status = runtime.status("mixed-run")
                self.assertEqual(status["counts"]["predictions"], 2)
                self.assertEqual(status["counts"]["forward_sample_count"], 1)
                self.assertEqual(
                    runtime.connection.execute(
                        "SELECT COUNT(*) FROM phase3_predictions WHERE source_role = 'EXECUTION_DIAGNOSTIC' AND forward_run_id = ?",
                        ("mixed-run",),
                    ).fetchone()[0],
                    1,
                )
            finally:
                runtime.close()

    def test_repeated_observation_is_idempotent(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = self._runtime(Path(directory) / "phase3.sqlite")
            try:
                runtime.create_run("restart-run", mode="SMOKE", started_at_utc=CLOCK)
                payload = _opportunity("repeat")
                first = runtime.process_payload("restart-run", payload)
                second = runtime.process_payload("restart-run", payload)
                self.assertTrue(first["prediction_id"])
                self.assertEqual(second["status"], "REJECTED_DUPLICATE")
                self.assertEqual(runtime.status("restart-run")["counts"]["predictions"], 1)
                self.assertEqual(runtime.status("restart-run")["counts"]["raw_observation_count"], 1)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
