"""Runtime Phase 3: consumer một chiều, transaction-safe và shadow-only."""

from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..features.registry import FeatureLeakageError, FeatureSchemaError
from ..memory.database import apply_migrations, connect_database, integrity_status
from ..scoring.train import ModelBundle
from ..similarity.index import HistoricalSimilarityIndex
from .bundle import ShadowBundle, persist_bundle, validate_bundle
from .config import Phase3Config
from .evaluation.metrics import evaluate_forward_records
from .health import HealthTracker, persist_health_event
from .ingestion.adapter import ReadOnlyTelemetryAdapter
from .ingestion.canonicalize import (
    canonicalize_event,
    canonicalize_opportunity,
    derive_canonical_forward_ids,
)
from .ingestion.opportunity import (
    CANONICALIZER_FINGERPRINT,
    OpportunityValidationError,
    validate_opportunity_payload,
)
from .ingestion.validation import TelemetryValidationError, validate_telemetry_payload
from .models import (
    PHASE3_CANONICAL_OPPORTUNITY_SCHEMA,
    PHASE3_CANONICALIZER_VERSION,
    PHASE3_OPPORTUNITY_SCHEMA,
    RUN_MODES,
    RUN_STATUSES,
    TelemetryEvent,
    format_utc_timestamp,
    parse_utc_timestamp,
    sha256_json,
    utc_now,
)
from .outcomes.resolver import OutcomeResolver
from .scoring.bridge import Phase2ScoringBridge


class Phase3RuntimeError(RuntimeError):
    """Runtime dừng fail-closed, không ảnh hưởng producer MT5."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _safe_raw_hash(payload: Any) -> str:
    try:
        return sha256_json(payload)
    except (TypeError, ValueError):
        return sha256_json({"repr": repr(payload)})


class Phase3Runtime:
    """Điều phối run/event/prediction/outcome trong SQLite local."""

    def __init__(
        self,
        connection: Any,
        bundle: ShadowBundle,
        *,
        model_bundle: ModelBundle | None = None,
        similarity_index: HistoricalSimilarityIndex | None = None,
        scoring_bridge: Phase2ScoringBridge | None = None,
        config: Phase3Config | None = None,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self.connection = connection
        apply_migrations(connection)
        self.bundle = validate_bundle(bundle)
        self.config = config or Phase3Config()
        if self.config.bundle_id and self.config.bundle_id != self.bundle.bundle_id:
            raise Phase3RuntimeError("runtime config bundle_id does not match frozen bundle")
        self.clock = clock
        self.health = HealthTracker()
        self.bridge = scoring_bridge or Phase2ScoringBridge(
            self.bundle, model_bundle=model_bundle, similarity_index=similarity_index
        )

    @classmethod
    def open(
        cls,
        db_path: str | Path,
        bundle: ShadowBundle,
        **kwargs: Any,
    ) -> "Phase3Runtime":
        connection = connect_database(db_path)
        return cls(connection, bundle, **kwargs)

    def close(self) -> None:
        self.connection.close()

    def create_run(
        self,
        run_id: str,
        *,
        mode: str | None = None,
        source: str = "telemetry",
        symbol: str | None = None,
        timeframe: str | None = None,
        started_at_utc: str | None = None,
        git_sha: str | None = None,
    ) -> dict[str, Any]:
        """Tạo run bất biến về bundle; không hot-swap bundle giữa run."""

        mode = str(mode or self.config.mode).upper()
        if mode not in RUN_MODES:
            raise Phase3RuntimeError(f"unsupported run mode: {mode}")
        started = format_utc_timestamp(started_at_utc or self.clock())
        existing = self.connection.execute("SELECT * FROM phase3_forward_runs WHERE run_id = ?", (run_id,)).fetchone()
        if existing is not None:
            if str(existing["bundle_id"]) != self.bundle.bundle_id or str(existing["mode"]) != mode:
                raise Phase3RuntimeError("existing run does not match immutable run contract")
            return dict(existing)
        persist_bundle(self.connection, self.bundle)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO phase3_forward_runs(
                    run_id, bundle_id, mode, started_at_utc, stopped_at_utc,
                    source, symbol, timeframe, git_sha, forward_start_utc,
                    status, created_at_utc
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id, self.bundle.bundle_id, mode, started, source, symbol, timeframe,
                    git_sha or self.bundle.phase2_base_sha, started, "CREATED", started,
                ),
            )
            persist_health_event(self.connection, run_id, "RUN_CREATED", {"mode": mode, "bundle_id": self.bundle.bundle_id})
        return dict(self.connection.execute("SELECT * FROM phase3_forward_runs WHERE run_id = ?", (run_id,)).fetchone())

    def set_run_status(self, run_id: str, status: str, *, stopped_at_utc: str | None = None) -> dict[str, Any]:
        status = str(status).upper()
        if status not in RUN_STATUSES:
            raise Phase3RuntimeError(f"unsupported run status: {status}")
        row = self._run(run_id)
        if str(row["status"]) == "STOPPED" and status != "STOPPED":
            raise Phase3RuntimeError("stopped run cannot be resumed or mutated")
        with self.connection:
            self.connection.execute(
                "UPDATE phase3_forward_runs SET status = ?, stopped_at_utc = CASE WHEN ? = 'STOPPED' THEN ? ELSE stopped_at_utc END WHERE run_id = ?",
                (status, status, format_utc_timestamp(stopped_at_utc or self.clock()) if status == "STOPPED" else None, run_id),
            )
            persist_health_event(self.connection, run_id, "RUN_STATUS", {"status": status})
        return dict(self._run(run_id))

    def _run(self, run_id: str) -> Any:
        row = self.connection.execute("SELECT * FROM phase3_forward_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise Phase3RuntimeError(f"unknown forward run: {run_id}")
        return row

    def _duplicate(self, run_id: str, source_event_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT forward_event_id, forward_opportunity_id, lifecycle_status FROM phase3_forward_events WHERE run_id = ? AND source_event_id = ?",
            (run_id, source_event_id),
        ).fetchone()
        if row is None:
            return None
        self.health.duplicate()
        return {"status": "REJECTED_DUPLICATE", "duplicate": True, **dict(row)}

    def _insert_rejection(
        self,
        run_id: str,
        payload: Any,
        *,
        source: str,
        reason: str,
        status: str = "REJECTED_SCHEMA",
        source_event_id: str | None = None,
        received_at_utc: str | None = None,
    ) -> dict[str, Any]:
        received = format_utc_timestamp(received_at_utc or self.clock())
        digest = _safe_raw_hash(payload)
        source_event_id = source_event_id or f"invalid-{digest}"
        forward_event_id = f"p3-event-rejected-{sha256_json({'run_id': run_id, 'source': source, 'source_event_id': source_event_id, 'raw': digest})}"
        forward_opportunity_id = f"p3-opportunity-rejected-{digest}"
        raw = payload if isinstance(payload, Mapping) else {"raw_line": str(payload)}
        try:
            raw_json = _json(raw)
        except (TypeError, ValueError):
            raw_json = _json({"repr": repr(raw)})
        existing = self._duplicate(run_id, source_event_id)
        if existing:
            return existing
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO phase3_forward_events(
                    forward_event_id, run_id, forward_opportunity_id, source_event_id,
                    event_timestamp_utc, received_at_utc, symbol, timeframe, side,
                    candidate_type, bar_state, source_timezone, raw_payload_sha256,
                    raw_payload, schema_version, validation_status, lifecycle_status,
                    failure_reason, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    forward_event_id, run_id, forward_opportunity_id, source_event_id,
                    received, received, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN",
                    "event_instant", None, digest, raw_json, "UNKNOWN", status, status,
                    reason, received,
                ),
            )
            persist_health_event(self.connection, run_id, "EVENT_REJECTED", {"status": status, "reason": reason, "raw_payload_sha256": digest}, severity="WARNING")
        self.health.rejected(schema=status == "REJECTED_SCHEMA")
        return {"status": status, "forward_event_id": forward_event_id, "reason": reason}

    def _time_gate(
        self,
        run: Any,
        event: TelemetryEvent,
        *,
        enforce_monotonic: bool = True,
    ) -> tuple[str | None, str | None]:
        event_time = parse_utc_timestamp(event.event_timestamp_utc)
        now = parse_utc_timestamp(self.clock())
        if event_time > now + timedelta(seconds=self.config.future_tolerance_seconds):
            return "REJECTED_STALE", "EVENT_TIMESTAMP_IN_FUTURE"
        if self.config.max_event_age_seconds is not None and now - event_time > timedelta(seconds=self.config.max_event_age_seconds):
            return "REJECTED_STALE", "EVENT_TOO_OLD"
        if str(run["mode"]) == "FORWARD":
            if event_time < parse_utc_timestamp(str(run["forward_start_utc"])):
                return "REJECTED_STALE", "BEFORE_FORWARD_START"
            if event_time <= parse_utc_timestamp(self.bundle.historical_reference_cutoff_utc):
                return "REJECTED_STALE", "AT_OR_BEFORE_HISTORICAL_CUTOFF"
        if enforce_monotonic:
            latest = self.connection.execute(
                "SELECT MAX(event_timestamp_utc) FROM phase3_forward_events WHERE run_id = ? AND validation_status IN ('VALIDATED', 'ACCEPTED')",
                (str(run["run_id"]),),
            ).fetchone()[0]
            if latest and event_time < parse_utc_timestamp(str(latest)):
                self.health.out_of_order_event()
                return "REJECTED_STALE", "OUT_OF_ORDER_EVENT"
        return None, None

    def _opportunity_duplicate(self, run_id: str, source_observation_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT observation_id, canonical_opportunity_id, status
            FROM phase3_opportunity_observations
            WHERE run_id = ? AND source_observation_id = ?
            """,
            (run_id, source_observation_id),
        ).fetchone()
        if row is None:
            return None
        self.health.duplicate()
        return {**dict(row), "status": "REJECTED_DUPLICATE", "duplicate": True}

    def _opportunity_observation_id(self, run_id: str, source_observation_id: str) -> str:
        return "p3-observation-" + sha256_json(
            {"run_id": str(run_id), "source_observation_id": str(source_observation_id)}
        )

    def _canonical_record_id(self, run_id: str, canonical_opportunity_id: str) -> str:
        return "p3-canonical-record-" + sha256_json(
            {"run_id": str(run_id), "canonical_opportunity_id": str(canonical_opportunity_id)}
        )

    def _insert_opportunity_observation(
        self,
        run_id: str,
        observation: Any,
        canonical_id: str,
        *,
        status: str,
        created_at_utc: str,
    ) -> str:
        observation_id = self._opportunity_observation_id(run_id, observation.source_observation_id)
        self.connection.execute(
            """
            INSERT INTO phase3_opportunity_observations(
                observation_id, run_id, source_observation_id, event_timestamp_utc,
                emitted_at_utc, received_at_utc, source_strategy, source_strategy_version,
                symbol, timeframe, side, source_audit_family, source_event_type,
                bar_state, context_features_json, execution_context_json, entry_price,
                hypothetical_entry_price, risk_distance, initial_sl_distance,
                hypothetical_initial_sl, build_valid, build_reason,
                canonical_opportunity_id, canonical_schema, canonicalizer_version,
                canonicalizer_fingerprint, raw_payload_sha256, raw_payload,
                schema_version, status, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                run_id,
                observation.source_observation_id,
                observation.event_timestamp_utc,
                observation.emitted_at_utc,
                observation.received_at_utc,
                observation.source_strategy,
                observation.source_strategy_version,
                observation.symbol,
                observation.timeframe,
                observation.side,
                observation.source_audit_family,
                observation.source_event_type,
                observation.bar_state,
                _json(observation.context_features),
                _json(observation.execution_context),
                observation.entry_price,
                observation.hypothetical_entry_price,
                observation.risk_distance,
                observation.initial_sl_distance,
                observation.hypothetical_initial_sl,
                int(observation.build_valid),
                observation.build_reason,
                canonical_id,
                PHASE3_CANONICAL_OPPORTUNITY_SCHEMA,
                PHASE3_CANONICALIZER_VERSION,
                CANONICALIZER_FINGERPRINT,
                _safe_raw_hash(observation.raw_payload),
                _json(observation.raw_payload),
                observation.schema_version,
                status,
                created_at_utc,
            ),
        )
        return observation_id

    def _process_opportunity_payload(
        self,
        run_id: str,
        payload: Mapping[str, Any],
        *,
        source: str,
        received_at_utc: str | None,
    ) -> dict[str, Any]:
        """Lưu raw trước rồi dedup canonical, không làm thay đổi execution state."""

        run = self._run(run_id)
        self.health.received(received_at_utc)
        source_observation_id = str(payload.get("source_observation_id", "")) if isinstance(payload, Mapping) else ""
        if source_observation_id:
            duplicate = self._opportunity_duplicate(run_id, source_observation_id)
            if duplicate:
                with self.connection:
                    persist_health_event(self.connection, run_id, "DUPLICATE_OPPORTUNITY_OBSERVATION", duplicate, severity="INFO")
                return duplicate
        if str(run["status"]) in {"PAUSED", "STOPPED", "FAILED"}:
            return self._insert_rejection(
                run_id,
                payload,
                source=source,
                reason="RUN_NOT_ACTIVE",
                status="REJECTED_CONFLICT",
                source_event_id=source_observation_id or None,
                received_at_utc=received_at_utc,
            )
        try:
            observation = validate_opportunity_payload(payload, source=source, received_at_utc=received_at_utc)
            evidence, canonical = canonicalize_opportunity(observation, run_id=run_id)
        except (OpportunityValidationError, TypeError, ValueError) as exc:
            return self._insert_rejection(
                run_id,
                payload,
                source=source,
                reason=str(exc),
                status="REJECTED_SCHEMA",
                source_event_id=source_observation_id or None,
                received_at_utc=received_at_utc,
            )

        existing = self.connection.execute(
            "SELECT * FROM phase3_canonical_opportunities WHERE run_id = ? AND canonical_opportunity_id = ?",
            (run_id, evidence.canonical_opportunity_id),
        ).fetchone()
        committed_at = format_utc_timestamp(self.clock())
        if existing is not None:
            try:
                with self.connection:
                    self._insert_opportunity_observation(
                        run_id,
                        observation,
                        evidence.canonical_opportunity_id,
                        status="DUPLICATE_COLLAPSED",
                        created_at_utc=committed_at,
                    )
                    self.connection.execute(
                        """
                        UPDATE phase3_canonical_opportunities
                        SET raw_observation_count = raw_observation_count + 1,
                            duplicate_observation_count = duplicate_observation_count + 1,
                            updated_at_utc = ?
                        WHERE run_id = ? AND canonical_opportunity_id = ?
                        """,
                        (committed_at, run_id, evidence.canonical_opportunity_id),
                    )
                    persist_health_event(
                        self.connection,
                        run_id,
                        "CANONICAL_DUPLICATE_COLLAPSED",
                        {"canonical_opportunity_id": evidence.canonical_opportunity_id},
                        severity="INFO",
                    )
            except Exception as exc:
                return self._insert_rejection(
                    run_id,
                    payload,
                    source=source,
                    reason=f"FAIL_CLOSED:{exc}",
                    status="REJECTED_CONFLICT",
                    source_event_id=observation.source_observation_id,
                    received_at_utc=observation.received_at_utc,
                )
            return {
                "status": "DUPLICATE_COLLAPSED",
                "duplicate": True,
                "observation_id": self._opportunity_observation_id(run_id, observation.source_observation_id),
                "canonical_opportunity_id": evidence.canonical_opportunity_id,
                "duplicate_observation_count": int(existing["duplicate_observation_count"]) + 1,
            }

        gate_status, gate_reason = self._time_gate(
            run,
            observation.to_telemetry_event(),
            enforce_monotonic=False,
        )
        if gate_status:
            return self._insert_rejection(
                run_id,
                payload,
                source=source,
                reason=gate_reason or "TIME_GATE",
                status=gate_status,
                source_event_id=observation.source_observation_id,
                received_at_utc=observation.received_at_utc,
            )
        canonical_record_id = self._canonical_record_id(run_id, evidence.canonical_opportunity_id)
        if not observation.build_valid:
            try:
                with self.connection:
                    observation_id = self._insert_opportunity_observation(
                        run_id,
                        observation,
                        evidence.canonical_opportunity_id,
                        status="INVALID",
                        created_at_utc=committed_at,
                    )
                    self.connection.execute(
                        """
                        INSERT INTO phase3_canonical_opportunities(
                            canonical_record_id, run_id, canonical_opportunity_id,
                            representative_observation_id, event_timestamp_utc,
                            source_strategy_version, symbol, timeframe, side,
                            canonical_schema, canonicalizer_version, canonicalizer_fingerprint,
                            status, raw_observation_count, duplicate_observation_count,
                            build_valid, build_reason, score_status, forward_event_id,
                            prediction_id, created_at_utc, updated_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'INVALID', 1, 0, 0, ?, 'NO_OPINION', NULL, NULL, ?, ?)
                        """,
                        (
                            canonical_record_id,
                            run_id,
                            evidence.canonical_opportunity_id,
                            observation_id,
                            observation.event_timestamp_utc,
                            observation.source_strategy_version,
                            observation.symbol,
                            observation.timeframe,
                            observation.side,
                            PHASE3_CANONICAL_OPPORTUNITY_SCHEMA,
                            PHASE3_CANONICALIZER_VERSION,
                            CANONICALIZER_FINGERPRINT,
                            observation.build_reason,
                            committed_at,
                            committed_at,
                        ),
                    )
                    persist_health_event(
                        self.connection,
                        run_id,
                        "INVALID_OPPORTUNITY_BUILD",
                        {"canonical_opportunity_id": evidence.canonical_opportunity_id, "reason": observation.build_reason},
                        severity="WARNING",
                    )
            except Exception as exc:
                return self._insert_rejection(
                    run_id,
                    payload,
                    source=source,
                    reason=f"FAIL_CLOSED:{exc}",
                    status="REJECTED_CONFLICT",
                    source_event_id=observation.source_observation_id,
                    received_at_utc=observation.received_at_utc,
                )
            self.health.accepted()
            self.health.prediction(committed_at, no_opinion=True, latency_ms=0.0)
            return {
                "status": "INVALID",
                "observation_id": self._opportunity_observation_id(run_id, observation.source_observation_id),
                "canonical_opportunity_id": evidence.canonical_opportunity_id,
                "build_valid": False,
                "build_reason": observation.build_reason,
            }

        started = time.perf_counter()
        try:
            scored_at = format_utc_timestamp(self.clock())
            snapshot, score = self.bridge.score_event(canonical, scored_at_utc=scored_at)
            committed_at = format_utc_timestamp(self.clock())
            if parse_utc_timestamp(committed_at) < parse_utc_timestamp(scored_at):
                raise Phase3RuntimeError("clock moved backward during prediction commit")
            forward_event_id, prediction_id = derive_canonical_forward_ids(run_id, evidence.canonical_opportunity_id)
            primary_status = "SCORABLE" if score.score_status == "OK" else "NO_OPINION"
            prediction_material = {
                "prediction_id": prediction_id,
                "forward_event_id": forward_event_id,
                "forward_run_id": run_id,
                "forward_opportunity_id": evidence.canonical_opportunity_id,
                "canonicalizer_version": PHASE3_CANONICALIZER_VERSION,
                "source_event_timestamp_utc": observation.event_timestamp_utc,
                "received_at_utc": observation.received_at_utc,
                "scored_at_utc": scored_at,
                "prediction_committed_at_utc": committed_at,
                "bundle_id": self.bundle.bundle_id,
                "feature_snapshot_fingerprint": snapshot.feature_fingerprint,
                "regime": score.regime,
                "regime_confidence": score.regime_confidence,
                "similarity_status": score.similarity_status,
                "similarity_sample_size": score.similarity_sample_size,
                "similarity_summary_json": _json(score.similarity_summary),
                "probability_plus1_before_minus1": score.probability_plus1_before_minus1,
                "expected_return_24bar_r": score.expected_return_24bar_r,
                "confidence": score.confidence,
                "ood_status": score.ood_status,
                "ood_score": score.ood_score,
                "score_status": score.score_status,
                "abstention_reason": score.abstention_reason,
                "code_sha": score.code_sha,
                "forward_valid": int(str(run["mode"]) == "FORWARD"),
                "created_at_utc": committed_at,
            }
            prediction_hash = sha256_json(prediction_material)
            with self.connection:
                persist_bundle(self.connection, self.bundle)
                observation_id = self._insert_opportunity_observation(
                    run_id,
                    observation,
                    evidence.canonical_opportunity_id,
                    status="CANONICALIZED",
                    created_at_utc=committed_at,
                )
                self.connection.execute(
                    """
                    INSERT INTO phase3_canonical_opportunities(
                        canonical_record_id, run_id, canonical_opportunity_id,
                        representative_observation_id, event_timestamp_utc,
                        source_strategy_version, symbol, timeframe, side,
                        canonical_schema, canonicalizer_version, canonicalizer_fingerprint,
                        status, raw_observation_count, duplicate_observation_count,
                        build_valid, build_reason, score_status, forward_event_id,
                        prediction_id, created_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 1, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        canonical_record_id,
                        run_id,
                        evidence.canonical_opportunity_id,
                        observation_id,
                        observation.event_timestamp_utc,
                        observation.source_strategy_version,
                        observation.symbol,
                        observation.timeframe,
                        observation.side,
                        PHASE3_CANONICAL_OPPORTUNITY_SCHEMA,
                        PHASE3_CANONICALIZER_VERSION,
                        CANONICALIZER_FINGERPRINT,
                        primary_status,
                        score.score_status,
                        forward_event_id,
                        prediction_id,
                        committed_at,
                        committed_at,
                    ),
                )
                self.connection.execute(
                    """
                    INSERT INTO phase3_forward_events(
                        forward_event_id, run_id, forward_opportunity_id, source_event_id,
                        event_timestamp_utc, received_at_utc, symbol, timeframe, side,
                        candidate_type, bar_state, source_timezone, raw_payload_sha256,
                        raw_payload, schema_version, validation_status, lifecycle_status,
                        failure_reason, created_at_utc, source_role, canonical_opportunity_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'CANONICAL_OPPORTUNITY', ?)
                    """,
                    (
                        forward_event_id,
                        run_id,
                        evidence.canonical_opportunity_id,
                        observation.source_observation_id,
                        observation.event_timestamp_utc,
                        observation.received_at_utc,
                        observation.symbol,
                        observation.timeframe,
                        observation.side,
                        observation.candidate_type,
                        observation.bar_state,
                        observation.source_timezone,
                        _safe_raw_hash(observation.raw_payload),
                        _json(observation.raw_payload),
                        observation.schema_version,
                        "VALIDATED",
                        "CANONICALIZED",
                        committed_at,
                        evidence.canonical_opportunity_id,
                    ),
                )
                self.connection.execute(
                    """
                    INSERT INTO phase3_feature_snapshots(
                        forward_event_id, feature_set_version, feature_timestamp_utc,
                        feature_fingerprint, feature_values_json, missingness_json,
                        ood_inputs_json, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        forward_event_id,
                        snapshot.feature_set_version,
                        snapshot.feature_timestamp_utc,
                        snapshot.feature_fingerprint,
                        _json(snapshot.feature_values),
                        _json(snapshot.missingness),
                        _json({**dict(snapshot.ood_inputs), "vector": list(snapshot.vector), "output_names": list(snapshot.output_names)}),
                        committed_at,
                    ),
                )
                self.connection.execute(
                    """
                    INSERT INTO phase3_predictions(
                        prediction_id, forward_event_id, forward_run_id,
                        forward_opportunity_id, source_event_timestamp_utc,
                        received_at_utc, scored_at_utc, prediction_committed_at_utc,
                        bundle_id, feature_snapshot_fingerprint, regime,
                        regime_confidence, similarity_status, similarity_sample_size,
                        similarity_summary_json, probability_plus1_before_minus1,
                        expected_return_24bar_r, confidence, ood_status, ood_score,
                        score_status, abstention_reason, code_sha, forward_valid,
                        prediction_hash, created_at_utc, source_role,
                        canonical_opportunity_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CANONICAL_OPPORTUNITY', ?)
                    """,
                    (
                        prediction_id,
                        forward_event_id,
                        run_id,
                        evidence.canonical_opportunity_id,
                        observation.event_timestamp_utc,
                        observation.received_at_utc,
                        scored_at,
                        committed_at,
                        self.bundle.bundle_id,
                        snapshot.feature_fingerprint,
                        score.regime,
                        score.regime_confidence,
                        score.similarity_status,
                        score.similarity_sample_size,
                        _json(score.similarity_summary),
                        score.probability_plus1_before_minus1,
                        score.expected_return_24bar_r,
                        score.confidence,
                        score.ood_status,
                        score.ood_score,
                        score.score_status,
                        score.abstention_reason,
                        score.code_sha,
                        prediction_material["forward_valid"],
                        prediction_hash,
                        committed_at,
                        evidence.canonical_opportunity_id,
                    ),
                )
                self.connection.execute(
                    "UPDATE phase3_forward_events SET lifecycle_status = 'OUTCOME_PENDING' WHERE forward_event_id = ?",
                    (forward_event_id,),
                )
                persist_health_event(
                    self.connection,
                    run_id,
                    "CANONICAL_PREDICTION_COMMITTED",
                    {"canonical_opportunity_id": evidence.canonical_opportunity_id, "score_status": score.score_status},
                )
            latency_ms = (time.perf_counter() - started) * 1000.0
            self.health.accepted()
            self.health.feature_quality(
                missing=any(snapshot.missingness.values()),
                ood=bool(snapshot.ood_inputs.get("is_ood")) and "MODEL_PREPROCESSOR_UNAVAILABLE" not in snapshot.ood_inputs.get("reasons", ()),
            )
            self.health.prediction(committed_at, no_opinion=score.score_status != "OK", latency_ms=latency_ms)
            self.health.pending()
            return {
                "status": "PREDICTION_COMMITTED",
                "observation_id": observation_id,
                "forward_event_id": forward_event_id,
                "forward_opportunity_id": evidence.canonical_opportunity_id,
                "canonical_opportunity_id": evidence.canonical_opportunity_id,
                "prediction_id": prediction_id,
                "score": score.to_dict(),
                "feature_snapshot": snapshot.to_dict(),
                "forward_valid": prediction_material["forward_valid"],
            }
        except (FeatureLeakageError, FeatureSchemaError, OpportunityValidationError, TelemetryValidationError) as exc:
            return self._insert_rejection(
                run_id,
                payload,
                source=source,
                reason=str(exc),
                status="REJECTED_CONFLICT",
                source_event_id=observation.source_observation_id,
                received_at_utc=observation.received_at_utc,
            )
        except Exception as exc:
            return self._insert_rejection(
                run_id,
                payload,
                source=source,
                reason=f"FAIL_CLOSED:{exc}",
                status="REJECTED_CONFLICT",
                source_event_id=observation.source_observation_id,
                received_at_utc=observation.received_at_utc,
            )

    def process_payload(
        self,
        run_id: str,
        payload: Mapping[str, Any],
        *,
        source: str = "telemetry",
        received_at_utc: str | None = None,
    ) -> dict[str, Any]:
        """Process một payload hoàn chỉnh; outcome tuyệt đối chưa được đọc ở đây."""

        if isinstance(payload, Mapping) and payload.get("schema_version") == PHASE3_OPPORTUNITY_SCHEMA:
            return self._process_opportunity_payload(
                run_id,
                payload,
                source=source,
                received_at_utc=received_at_utc,
            )

        run = self._run(run_id)
        self.health.received(received_at_utc)
        raw_source_event_id = str(payload.get("source_event_id", "")) if isinstance(payload, Mapping) else ""
        if raw_source_event_id:
            duplicate = self._duplicate(run_id, raw_source_event_id)
            if duplicate:
                with self.connection:
                    persist_health_event(self.connection, run_id, "DUPLICATE_EVENT", duplicate, severity="INFO")
                return duplicate
        if str(run["status"]) in {"PAUSED", "STOPPED", "FAILED"}:
            return self._insert_rejection(
                run_id,
                payload,
                source=source,
                reason="RUN_NOT_ACTIVE",
                status="REJECTED_CONFLICT",
                source_event_id=raw_source_event_id or None,
                received_at_utc=received_at_utc,
            )
        try:
            event = validate_telemetry_payload(payload, source=source, received_at_utc=received_at_utc)
        except TelemetryValidationError as exc:
            return self._insert_rejection(run_id, payload, source=source, reason=str(exc), status="REJECTED_SCHEMA", source_event_id=raw_source_event_id or None, received_at_utc=received_at_utc)
        except (TypeError, ValueError) as exc:
            return self._insert_rejection(run_id, payload, source=source, reason=str(exc), status="REJECTED_SCHEMA", source_event_id=raw_source_event_id or None, received_at_utc=received_at_utc)
        gate_status, gate_reason = self._time_gate(run, event)
        if gate_status:
            return self._insert_rejection(
                run_id, payload, source=source, reason=gate_reason or "TIME_GATE", status=gate_status,
                source_event_id=event.source_event_id, received_at_utc=event.received_at_utc,
            )
        if self.config.require_closed_bar and event.bar_state != "closed_bar":
            return self._insert_rejection(
                run_id,
                payload,
                source=source,
                reason="CLOSED_BAR_REQUIRED",
                status="REJECTED_SCHEMA",
                source_event_id=event.source_event_id,
                received_at_utc=event.received_at_utc,
            )
        canonical = canonicalize_event(event)
        started = time.perf_counter()
        try:
            scored_at = format_utc_timestamp(self.clock())
            snapshot, score = self.bridge.score_event(canonical, scored_at_utc=scored_at)
            committed_at = format_utc_timestamp(self.clock())
            if parse_utc_timestamp(committed_at) < parse_utc_timestamp(scored_at):
                raise Phase3RuntimeError("clock moved backward during prediction commit")
            prediction_material = {
                "prediction_id": f"p3-prediction-{canonical.forward_event_id}",
                "forward_event_id": canonical.forward_event_id,
                "forward_run_id": run_id,
                "forward_opportunity_id": canonical.forward_opportunity_id,
                "source_event_timestamp_utc": event.event_timestamp_utc,
                "received_at_utc": event.received_at_utc,
                "scored_at_utc": scored_at,
                "prediction_committed_at_utc": committed_at,
                "bundle_id": self.bundle.bundle_id,
                "feature_snapshot_fingerprint": snapshot.feature_fingerprint,
                "regime": score.regime,
                "regime_confidence": score.regime_confidence,
                "similarity_status": score.similarity_status,
                "similarity_sample_size": score.similarity_sample_size,
                "similarity_summary_json": _json(score.similarity_summary),
                "probability_plus1_before_minus1": score.probability_plus1_before_minus1,
                "expected_return_24bar_r": score.expected_return_24bar_r,
                "confidence": score.confidence,
                "ood_status": score.ood_status,
                "ood_score": score.ood_score,
                "score_status": score.score_status,
                "abstention_reason": score.abstention_reason,
                "code_sha": score.code_sha,
                "forward_valid": int(str(run["mode"]) == "FORWARD"),
                "created_at_utc": committed_at,
            }
            prediction_hash = sha256_json(prediction_material)
            with self.connection:
                persist_bundle(self.connection, self.bundle)
                self.connection.execute(
                    """
                    INSERT INTO phase3_forward_events(
                        forward_event_id, run_id, forward_opportunity_id, source_event_id,
                        event_timestamp_utc, received_at_utc, symbol, timeframe, side,
                        candidate_type, bar_state, source_timezone, raw_payload_sha256,
                        raw_payload, schema_version, validation_status, lifecycle_status,
                        failure_reason, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        canonical.forward_event_id, run_id, canonical.forward_opportunity_id,
                        event.source_event_id, event.event_timestamp_utc, event.received_at_utc,
                        event.symbol, event.timeframe, event.side, event.candidate_type,
                        event.bar_state, event.source_timezone, event.raw_payload_sha256,
                        _json(event.raw_payload), event.schema_version, "VALIDATED",
                        "CANONICALIZED", committed_at,
                    ),
                )
                self.connection.execute(
                    "UPDATE phase3_forward_events SET lifecycle_status = ? WHERE forward_event_id = ?",
                    ("FEATURED", canonical.forward_event_id),
                )
                self.connection.execute(
                    """
                    INSERT INTO phase3_feature_snapshots(
                        forward_event_id, feature_set_version, feature_timestamp_utc,
                        feature_fingerprint, feature_values_json, missingness_json,
                        ood_inputs_json, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        canonical.forward_event_id, snapshot.feature_set_version,
                        snapshot.feature_timestamp_utc, snapshot.feature_fingerprint,
                        _json(snapshot.feature_values), _json(snapshot.missingness),
                        _json({**dict(snapshot.ood_inputs), "vector": list(snapshot.vector), "output_names": list(snapshot.output_names)}),
                        committed_at,
                    ),
                )
                self.connection.execute(
                    "UPDATE phase3_forward_events SET lifecycle_status = 'SCORED' WHERE forward_event_id = ?",
                    (canonical.forward_event_id,),
                )
                self.connection.execute(
                    """
                    INSERT INTO phase3_predictions(
                        prediction_id, forward_event_id, forward_run_id,
                        forward_opportunity_id, source_event_timestamp_utc,
                        received_at_utc, scored_at_utc, prediction_committed_at_utc,
                        bundle_id, feature_snapshot_fingerprint, regime,
                        regime_confidence, similarity_status, similarity_sample_size,
                        similarity_summary_json, probability_plus1_before_minus1,
                        expected_return_24bar_r, confidence, ood_status, ood_score,
                        score_status, abstention_reason, code_sha, forward_valid,
                        prediction_hash, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        prediction_material["prediction_id"], canonical.forward_event_id, run_id,
                        canonical.forward_opportunity_id, event.event_timestamp_utc,
                        event.received_at_utc, scored_at, committed_at, self.bundle.bundle_id,
                        snapshot.feature_fingerprint, score.regime, score.regime_confidence,
                        score.similarity_status, score.similarity_sample_size,
                        _json(score.similarity_summary), score.probability_plus1_before_minus1,
                        score.expected_return_24bar_r, score.confidence, score.ood_status,
                        score.ood_score, score.score_status, score.abstention_reason,
                        score.code_sha, prediction_material["forward_valid"], prediction_hash,
                        committed_at,
                    ),
                )
                self.connection.execute(
                    "UPDATE phase3_forward_events SET lifecycle_status = 'OUTCOME_PENDING' WHERE forward_event_id = ?",
                    (canonical.forward_event_id,),
                )
                persist_health_event(self.connection, run_id, "PREDICTION_COMMITTED", {"forward_event_id": canonical.forward_event_id, "score_status": score.score_status})
            latency_ms = (time.perf_counter() - started) * 1000.0
            self.health.accepted()
            self.health.feature_quality(
                missing=any(snapshot.missingness.values()),
                ood=bool(snapshot.ood_inputs.get("is_ood")) and "MODEL_PREPROCESSOR_UNAVAILABLE" not in snapshot.ood_inputs.get("reasons", ()),
            )
            self.health.prediction(committed_at, no_opinion=score.score_status != "OK", latency_ms=latency_ms)
            self.health.pending()
            return {
                "status": "PREDICTION_COMMITTED",
                "forward_event_id": canonical.forward_event_id,
                "forward_opportunity_id": canonical.forward_opportunity_id,
                "prediction_id": prediction_material["prediction_id"],
                "score": score.to_dict(),
                "feature_snapshot": snapshot.to_dict(),
                "forward_valid": prediction_material["forward_valid"],
            }
        except (FeatureLeakageError, FeatureSchemaError, TelemetryValidationError) as exc:
            return self._insert_rejection(run_id, payload, source=source, reason=str(exc), status="REJECTED_CONFLICT", source_event_id=event.source_event_id, received_at_utc=event.received_at_utc)
        except Exception as exc:
            # Rollback đã được SQLite đảm bảo; chỉ ghi một rejection evidence riêng.
            return self._insert_rejection(run_id, payload, source=source, reason=f"FAIL_CLOSED:{exc}", status="REJECTED_CONFLICT", source_event_id=event.source_event_id, received_at_utc=event.received_at_utc)

    def ingest_file_once(
        self,
        run_id: str,
        path: str | Path,
        *,
        source: str | None = None,
        file_format: str = "jsonl",
        expected_schema: str | None = None,
    ) -> dict[str, Any]:
        """Đọc phần mới; partial final line chờ lần sau, rotation reset đúng một lần."""

        source_key = str(Path(path).resolve())
        offset = self.connection.execute(
            "SELECT * FROM phase3_ingest_offsets WHERE source_key = ?", (source_key,)
        ).fetchone()
        adapter = ReadOnlyTelemetryAdapter(str(path), file_format=file_format)
        batch, records = adapter.read_available(
            offset_bytes=int(offset["offset_bytes"]) if offset else 0,
            source_identity=str(offset["source_identity"]) if offset else None,
        )
        if batch.truncated:
            previous_state: dict[str, Any] = {}
            if offset:
                try:
                    loaded_state = json.loads(str(offset["rotation_state_json"] or "{}"))
                    if isinstance(loaded_state, Mapping):
                        previous_state = dict(loaded_state)
                except (TypeError, ValueError):
                    previous_state = {}
            previous_state.update({"truncated": True, "rotated": False})
            with self.connection:
                self.connection.execute(
                    """
                    UPDATE phase3_ingest_offsets
                    SET rotation_state_json = ?, updated_at_utc = ?
                    WHERE source_key = ?
                    """,
                    (_json(previous_state), self.clock(), source_key),
                )
                persist_health_event(
                    self.connection,
                    run_id,
                    "SOURCE_TRUNCATED",
                    {"source_path": batch.path, "offset_bytes": int(offset["offset_bytes"]) if offset else 0, "file_size": Path(path).stat().st_size},
                    severity="ERROR",
                )
            return {
                "source_path": batch.path,
                "source_identity": batch.source_identity,
                "records_seen": 0,
                "results": [],
                "partial_final_line": batch.partial_final_line,
                "rotated": False,
                "truncated": True,
                "offset_bytes": int(offset["offset_bytes"]) if offset else 0,
                "status": "SOURCE_TRUNCATED",
            }
        results: list[dict[str, Any]] = []
        for parsed in records:
            if parsed.error is not None:
                result = self._insert_rejection(
                    run_id, {"raw_line": parsed.record.raw_line.decode("utf-8", errors="replace")},
                    source=source or source_key, reason=f"MALFORMED_RECORD:{parsed.error}",
                    status="REJECTED_SCHEMA",
                )
            else:
                payload = parsed.payload or {}
                if expected_schema and payload.get("schema_version") != expected_schema:
                    result = self._insert_rejection(
                        run_id,
                        payload,
                        source=source or source_key,
                        reason=f"PRIMARY_SOURCE_SCHEMA_MISMATCH:{payload.get('schema_version', '<missing>')}",
                        status="REJECTED_SCHEMA",
                        source_event_id=str(payload.get("source_observation_id") or payload.get("source_event_id") or "") or None,
                    )
                else:
                    result = self.process_payload(run_id, payload, source=source or source_key)
            results.append(result)
            rotation_state: dict[str, Any] = {}
            if offset:
                try:
                    loaded_state = json.loads(str(offset["rotation_state_json"] or "{}"))
                    if isinstance(loaded_state, Mapping):
                        rotation_state = dict(loaded_state)
                except (TypeError, ValueError):
                    rotation_state = {}
            rotation_state.update({"rotated": batch.rotated, "truncated": False})
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO phase3_ingest_offsets(source_key, source_identity, source_path, offset_bytes, last_consumed_event_id, rotation_state_json, updated_at_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_key) DO UPDATE SET
                        source_identity=excluded.source_identity,
                        source_path=excluded.source_path,
                        offset_bytes=excluded.offset_bytes,
                        last_consumed_event_id=excluded.last_consumed_event_id,
                        rotation_state_json=excluded.rotation_state_json,
                        updated_at_utc=excluded.updated_at_utc
                    """,
                    (
                        source_key, batch.source_identity, batch.path, parsed.record.end_offset,
                        result.get("forward_event_id"), _json(rotation_state), self.clock(),
                    ),
                )
        if not records:
            rotation_state = {"rotated": batch.rotated, "truncated": False}
            if offset:
                try:
                    loaded_state = json.loads(str(offset["rotation_state_json"] or "{}"))
                    if isinstance(loaded_state, Mapping):
                        rotation_state = dict(loaded_state)
                except (TypeError, ValueError):
                    rotation_state = {"rotated": batch.rotated, "truncated": False}
            rotation_state.update({"rotated": batch.rotated, "truncated": False})
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO phase3_ingest_offsets(source_key, source_identity, source_path, offset_bytes, last_consumed_event_id, rotation_state_json, updated_at_utc)
                    VALUES (?, ?, ?, ?, NULL, ?, ?)
                    ON CONFLICT(source_key) DO UPDATE SET source_identity=excluded.source_identity, source_path=excluded.source_path, offset_bytes=excluded.offset_bytes, rotation_state_json=excluded.rotation_state_json, updated_at_utc=excluded.updated_at_utc
                    """,
                    (source_key, batch.source_identity, batch.path, batch.next_offset, _json(rotation_state), self.clock()),
                )
        return {
            "source_path": batch.path,
            "source_identity": batch.source_identity,
            "records_seen": len(records),
            "results": results,
            "partial_final_line": batch.partial_final_line,
            "rotated": batch.rotated,
            "truncated": False,
            "offset_bytes": batch.next_offset,
        }

    def resolve_outcomes(
        self,
        run_id: str,
        bars_by_event: Mapping[str, Iterable[Mapping[str, Any]]],
        *,
        observed_at_utc: str | None = None,
    ) -> dict[str, Any]:
        resolver = OutcomeResolver(self.connection, clock=self.clock)
        results = resolver.resolve_pending(run_id, bars_by_event, observed_at_utc=observed_at_utc)
        for resolution in results.values():
            self.health.resolved(incomplete=resolution.status != "RESOLVED")
        return {key: value.to_dict() for key, value in sorted(results.items())}

    def _evaluation_records(self, run_id: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT p.*, e.event_timestamp_utc, e.symbol, e.timeframe, e.side,
                   r.mode AS run_mode, o.classification_label,
                   o.return_6bar_r, o.return_12bar_r, o.return_24bar_r,
                   o.return_48bar_r, o.mfe_r, o.mae_r, o.status AS outcome_status,
                   o.outcome_observed_at_utc
            FROM phase3_predictions p
            JOIN phase3_forward_events e ON e.forward_event_id = p.forward_event_id
            JOIN phase3_forward_runs r ON r.run_id = p.forward_run_id
            JOIN phase3_outcomes o ON o.forward_event_id = p.forward_event_id
        """
        params: tuple[Any, ...] = ()
        if run_id:
            query += " WHERE p.forward_run_id = ?"
            params = (run_id,)
        query += " ORDER BY p.source_event_timestamp_utc, p.forward_event_id"
        rows = [dict(row) for row in self.connection.execute(query, params).fetchall()]
        for row in rows:
            try:
                summary = json.loads(row.get("similarity_summary_json") or "{}")
                row["similarity_probability"] = summary.get("historical_win_probability")
            except (TypeError, ValueError):
                row["similarity_probability"] = None
        return rows

    def evaluate(self, run_id: str | None = None) -> dict[str, Any]:
        records = self._evaluation_records(run_id)
        result = evaluate_forward_records(
            records,
            classification_min_resolved=self.config.classification_min_resolved,
            regression_min_resolved=self.config.regression_min_resolved,
            seed=self.config.random_seed,
        )
        target_run = run_id
        if target_run:
            run = self._run(target_run)
            if not records:
                pending = self.connection.execute("SELECT COUNT(*) FROM phase3_predictions WHERE forward_run_id = ?", (target_run,)).fetchone()[0]
                result["forward_collection_status"] = "READY" if not pending else "COLLECTING"
            material = {"run_id": target_run, "metrics": result}
            snapshot_id = "p3-eval-" + sha256_json(material)
            snapshot_hash = sha256_json({"snapshot_id": snapshot_id, **material})
            existing = self.connection.execute("SELECT snapshot_hash FROM phase3_evaluation_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
            if existing is None:
                with self.connection:
                    self.connection.execute(
                        "INSERT INTO phase3_evaluation_snapshots(snapshot_id, run_id, generated_at_utc, forward_sample_count, collection_status, predictive_edge_status, metrics_json, snapshot_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (snapshot_id, target_run, self.clock(), int(result.get("resolved_sample_count", 0)), result["forward_collection_status"], result["forward_predictive_edge_status"], _json(result), snapshot_hash),
                    )
        return result

    def _resource_safety(self, run_id: str | None = None) -> dict[str, Any]:
        """Đo footprint hiện tại để phát hiện backlog/phình dữ liệu sớm."""

        page_count = int(self.connection.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(self.connection.execute("PRAGMA page_size").fetchone()[0])
        event_where = " WHERE run_id = ?" if run_id else ""
        event_params: tuple[Any, ...] = (run_id,) if run_id else ()
        event_stats = self.connection.execute(
            "SELECT COUNT(*), COALESCE(MAX(LENGTH(CAST(raw_payload AS BLOB))), 0), COALESCE(SUM(LENGTH(CAST(raw_payload AS BLOB))), 0) FROM phase3_forward_events" + event_where,
            event_params,
        ).fetchone()
        prediction_where = " WHERE forward_run_id = ?" if run_id else ""
        prediction_params: tuple[Any, ...] = (run_id,) if run_id else ()
        prediction_stats = self.connection.execute(
            "SELECT COUNT(*), COALESCE(MAX(LENGTH(CAST(similarity_summary_json AS BLOB))), 0), COALESCE(SUM(LENGTH(CAST(similarity_summary_json AS BLOB))), 0) FROM phase3_predictions" + prediction_where,
            prediction_params,
        ).fetchone()
        pending_query = "SELECT COUNT(*) FROM phase3_predictions p WHERE NOT EXISTS (SELECT 1 FROM phase3_outcomes o WHERE o.forward_event_id = p.forward_event_id)"
        if run_id:
            pending_query += " AND p.forward_run_id = ?"
        pending = int(self.connection.execute(pending_query, prediction_params).fetchone()[0])
        return {
            "database_size_bytes": page_count * page_size,
            "database_page_count": page_count,
            "database_page_size": page_size,
            "raw_event_payload_bytes": {
                "count": int(event_stats[0]),
                "max": int(event_stats[1]),
                "total": int(event_stats[2]),
            },
            "prediction_evidence_bytes": {
                "count": int(prediction_stats[0]),
                "max_similarity_summary": int(prediction_stats[1]),
                "total_similarity_summary": int(prediction_stats[2]),
            },
            "outcome_backlog": pending,
            "unbounded_backlog_detected": False,
            "latency": self.health.to_dict(),
        }

    def status(self, run_id: str | None = None) -> dict[str, Any]:
        run = self._run(run_id) if run_id else None
        run_clause = " WHERE run_id = ?" if run_id else ""
        run_params: tuple[Any, ...] = (run_id,) if run_id else ()
        canonical_counts = self.connection.execute(
            """
            SELECT
                COUNT(*) AS canonical_count,
                COALESCE(SUM(duplicate_observation_count), 0) AS duplicate_count,
                COALESCE(SUM(CASE WHEN status = 'SCORABLE' THEN 1 ELSE 0 END), 0) AS scorable_count,
                COALESCE(SUM(CASE WHEN status = 'NO_OPINION' THEN 1 ELSE 0 END), 0) AS no_opinion_count,
                COALESCE(SUM(CASE WHEN status = 'INVALID' THEN 1 ELSE 0 END), 0) AS invalid_count
            FROM phase3_canonical_opportunities
            """ + run_clause,
            run_params,
        ).fetchone()
        raw_observation_count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM phase3_opportunity_observations" + run_clause,
                run_params,
            ).fetchone()[0]
        )
        counts = {
            "events": int(self.connection.execute("SELECT COUNT(*) FROM phase3_forward_events" + (" WHERE run_id = ?" if run_id else ""), (run_id,) if run_id else ()).fetchone()[0]),
            "predictions": int(self.connection.execute("SELECT COUNT(*) FROM phase3_predictions" + (" WHERE forward_run_id = ?" if run_id else ""), (run_id,) if run_id else ()).fetchone()[0]),
            "pending_outcomes": int(self.connection.execute("SELECT COUNT(*) FROM phase3_predictions p WHERE NOT EXISTS (SELECT 1 FROM phase3_outcomes o WHERE o.forward_event_id = p.forward_event_id)" + (" AND p.forward_run_id = ?" if run_id else ""), (run_id,) if run_id else ()).fetchone()[0]),
            "resolved_outcomes": int(self.connection.execute("SELECT COUNT(*) FROM phase3_outcomes o" + (" JOIN phase3_forward_events e ON e.forward_event_id=o.forward_event_id WHERE o.status='RESOLVED' AND e.run_id = ?" if run_id else " WHERE o.status='RESOLVED'"), (run_id,) if run_id else ()).fetchone()[0]),
            "raw_observation_count": raw_observation_count,
            "canonical_opportunity_count": int(canonical_counts["canonical_count"]),
            "duplicate_collapse_count": int(canonical_counts["duplicate_count"]),
            "scorable_count": int(canonical_counts["scorable_count"]),
            "no_opinion_count": int(canonical_counts["no_opinion_count"]),
            "invalid_count": int(canonical_counts["invalid_count"]),
        }
        counts["forward_sample_count"] = counts["scorable_count"] + counts["no_opinion_count"]
        self.health.sync_pending(counts["pending_outcomes"])
        integrity = integrity_status(self.connection)
        return {
            "bundle_id": self.bundle.bundle_id,
            "bundle_status": self.bundle.status,
            "run": dict(run) if run else None,
            "counts": counts,
            "health": self.health.to_dict(),
            "resource_safety": self._resource_safety(run_id),
            "sqlite": integrity,
            "primary_source": "CANONICAL_OPPORTUNITY",
            "execution_diagnostic_source": "EXECUTION_CANDIDATE",
            "execution_mode": "NONE",
            "live_execution_enabled": False,
        }


__all__ = ["Phase3Runtime", "Phase3RuntimeError"]
