"""Orchestration for the offline Phase 2 intelligence pipeline.

This module has no MT5 bridge and no execution writer.  Its only side effects
are additive Phase 2 SQLite tables and lightweight research reports.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from ..data.normalization.timestamps import timestamp_to_datetime
from ..evaluation.leakage_checks import run_leakage_checks
from ..evaluation.reproducibility import current_git_commit, dataset_fingerprint, repository_base_sha
from ..features.builder import build_canonical_view, load_canonical_view, persist_canonical_view
from ..features.fingerprint import canonical_json, fingerprint, fingerprint_records
from ..features.missingness import missingness_report
from ..features.normalization import TrainOnlyPreprocessor
from ..features.registry import FEATURE_ALLOWLIST, FEATURE_SET_VERSION, extract_feature_fields, metadata_dict
from ..features.splits import build_split_manifest, build_temporal_splits
from ..memory.database import apply_migrations, connect_database, integrity_status
from ..regime.config import RegimeConfig, fit_regime_config
from ..regime.engine import RegimeEngine
from ..regime.validation import validate_regimes
from ..scoring.predict import predict_rows
from ..scoring.train import ModelBundle, train_models
from ..scoring.validation import evaluate_models
from ..similarity.index import evaluate_temporal_similarity
from ..similarity.models import SimilarityConfig
from ..similarity.validation import validate_similarity_results
from .config import Phase2Config, load_config


REPORT_FILENAMES = {
    "state": "phase2_state.json",
    "feature_manifest": "feature_manifest.json",
    "feature_quality": "feature_quality_report.json",
    "split_manifest": "split_manifest.json",
    "regime_manifest": "regime_manifest.json",
    "regime_report": "regime_report.md",
    "similarity_results": "similarity_results.json",
    "similarity_report": "similarity_report.md",
    "model_bundle": "model_bundle.json",
    "model_manifest": "model_manifest.json",
    "model_validation": "model_validation.json",
    "model_validation_md": "model_validation.md",
    "phase2_report": "phase2_report.md",
    "architecture": "v1_architecture_validation.md",
}


def _json_load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.rstrip() + "\n", encoding="utf-8")


def _nowish(value: str | None) -> str:
    # Reports need a stable provenance marker when regenerated from the same
    # checkout.  The source/event cutoff is preferable to wall-clock time.
    return value or "1970-01-01T00:00:00Z"


class Phase2Pipeline:
    def __init__(
        self,
        *,
        root: str | Path | None = None,
        db_path: str | Path = "data/trading_memory.db",
        report_dir: str | Path = "reports/trading_agent/phase2",
        config: Phase2Config | None = None,
        config_path: str | Path | None = None,
    ):
        self.root = Path(root or Path.cwd()).resolve()
        self.db_path = self._resolve(db_path)
        self.report_dir = self._resolve(report_dir)
        self.config = config or load_config(config_path)

    def _resolve(self, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.root / path

    def _report(self, name: str) -> Path:
        return self.report_dir / REPORT_FILENAMES[name]

    def _open(self) -> sqlite3.Connection:
        connection = connect_database(self.db_path)
        apply_migrations(connection)
        return connection

    def _state(self) -> dict[str, Any]:
        return _json_load(self._report("state"), {})

    def _save_state(self, updates: Mapping[str, Any]) -> dict[str, Any]:
        state = self._state()
        state.update(updates)
        state["config_version"] = self.config.version
        state["config_fingerprint"] = fingerprint(self.config.to_dict())
        _write_json(self._report("state"), state)
        return state

    def _base_provenance(self, connection: sqlite3.Connection) -> dict[str, Any]:
        source_count = int(connection.execute("SELECT COUNT(*) FROM source_artifacts").fetchone()[0])
        episode_count = int(connection.execute("SELECT COUNT(*) FROM trading_episodes").fetchone()[0])
        input_status = "AVAILABLE" if source_count > 0 and episode_count > 0 else "MISSING_PHASE1_DATA"
        return {
            "dataset_fingerprint": dataset_fingerprint(connection) if input_status == "AVAILABLE" else "NO_PHASE1_DATA",
            "input_dataset_status": input_status,
            "phase1_normalization_version": "normalization/1",
            "phase1_canonical_linkage_version": "canonical-opportunity/1",
            "repository_base_sha": repository_base_sha(self.root),
            "generation_commit": current_git_commit(self.root),
            "feature_set_version": self.config.feature_set_version,
            "split_version": self.config.split.version,
            "regime_version": self.config.regime_version,
            "similarity_version": self.config.similarity.version,
            "model_version": self.config.model.version,
            "random_seed": self.config.random_seed,
            "config_fingerprint": fingerprint(self.config.to_dict()),
        }

    def _load_rows_with_features(self, connection: sqlite3.Connection) -> tuple[list[dict[str, Any]], TrainOnlyPreprocessor, dict[str, tuple[float, ...]]]:
        rows = load_canonical_view(connection)
        manifest = _json_load(self._report("feature_manifest"), {})
        preprocessor = TrainOnlyPreprocessor.from_dict(manifest.get("preprocessor", {}))
        vectors: dict[str, tuple[float, ...]] = {}
        try:
            feature_version = str(manifest.get("feature_set_version", self.config.feature_set_version))
            records = connection.execute(
                "SELECT canonical_opportunity_id, normalized_vector_json FROM canonical_features WHERE feature_set_version = ?",
                (feature_version,),
            ).fetchall()
            for record in records:
                vectors[str(record["canonical_opportunity_id"])] = tuple(float(value) for value in json.loads(record["normalized_vector_json"]))
        except sqlite3.OperationalError:
            pass
        if not vectors and rows:
            vectors = preprocessor.transform(rows)
        for row in rows:
            identifier = str(row["canonical_opportunity_id"])
            if identifier in vectors:
                row["feature_vector"] = vectors[identifier]
                row["features_normalized"] = vectors[identifier]
        return rows, preprocessor, vectors

    def _load_split_map(self, connection: sqlite3.Connection) -> dict[str, str]:
        manifest = _json_load(self._report("split_manifest"), {})
        version = str(manifest.get("split_version", self.config.split.version))
        return {
            str(row["canonical_opportunity_id"]): str(row["split"])
            for row in connection.execute("SELECT canonical_opportunity_id, split FROM phase2_splits WHERE split_version = ?", (version,))
        }

    def _load_regime_map(self, connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        rows = connection.execute(
            "SELECT * FROM regime_assignments WHERE regime_version = ? ORDER BY canonical_opportunity_id",
            (self.config.regime_version,),
        ).fetchall()
        return {
            str(row["canonical_opportunity_id"]): {
                "canonical_opportunity_id": row["canonical_opportunity_id"],
                "trend_state": row["trend_state"],
                "volatility_state": row["volatility_state"],
                "liquidity_state": row["liquidity_state"],
                "composite_regime": row["composite_regime"],
                "confidence": row["confidence"],
                "reason": row["reason"] or "",
                "source_reported_regime": row["source_reported_regime"],
                "regime_version": row["regime_version"],
            }
            for row in rows
        }

    def build_features(self) -> dict[str, Any]:
        connection = self._open()
        try:
            rows = build_canonical_view(connection)
            persist_canonical_view(connection, rows)
            assignments = build_temporal_splits(rows, self.config.split)
            split_manifest = build_split_manifest(
                rows,
                assignments,
                dataset_fingerprint=self._base_provenance(connection)["dataset_fingerprint"],
                feature_set_version=self.config.feature_set_version,
                config=self.config.split,
            )
            split_manifest.update(self._base_provenance(connection))
            train_ids = tuple(
                identifier for identifier, split in assignments.items()
                if split == "TRAIN"
                and str(next(row for row in rows if row["canonical_opportunity_id"] == identifier).get("feature_status", "")).upper() != "CONFLICT"
            )
            preprocessor = TrainOnlyPreprocessor.fit(
                rows,
                train_ids,
                training_cutoff=split_manifest.get("train_end"),
                ood_z_limit=4.0,
            )
            vectors = preprocessor.transform(rows)
            feature_records = []
            for row in rows:
                fields = extract_feature_fields(row)
                missing = [name for name in sorted(FEATURE_ALLOWLIST) if fields.get(name) in (None, "")]
                feature_records.append({
                    "canonical_opportunity_id": row["canonical_opportunity_id"],
                    "normalized_vector": vectors.get(row["canonical_opportunity_id"], ()),
                    "output_names": preprocessor.output_names,
                    "missing": missing,
                    "feature_status": row.get("feature_status"),
                })
            feature_fp = fingerprint_records(feature_records)
            provenance = self._base_provenance(connection)
            feature_manifest = {
                "schema": "trading_agent_phase2_feature_manifest_v1",
                **provenance,
                "feature_set_version": self.config.feature_set_version,
                "canonical_view_version": "canonical-modeling-view/1",
                "registered_feature_count": len(FEATURE_ALLOWLIST),
                "matrix_column_count": len(preprocessor.output_names),
                "canonical_opportunity_count": len(rows),
                "audit_observation_count": sum(int(row.get("observation_count", 0)) for row in rows),
                "feature_fingerprint": feature_fp,
                "feature_count": len(FEATURE_ALLOWLIST),
                "preprocessing_fingerprint": preprocessor.to_dict().get("preprocessing_fingerprint"),
                "allowlist": sorted(FEATURE_ALLOWLIST),
                "definitions": metadata_dict(),
                "preprocessor": preprocessor.to_dict(),
                "float_tolerance": 1e-12,
                "timezone": "UTC",
                "fit_scope": "TRAIN_ONLY" if train_ids else "NONE",
            }
            quality = missingness_report(rows, feature_names=sorted(FEATURE_ALLOWLIST), split_by=assignments)
            quality.update({
                "schema": "trading_agent_phase2_feature_quality_v1",
                "repository_base_sha": provenance["repository_base_sha"],
                "generation_commit": provenance["generation_commit"],
                "dataset_fingerprint": provenance["dataset_fingerprint"],
                "feature_set_version": self.config.feature_set_version,
                "split_version": self.config.split.version,
                "regime_version": self.config.regime_version,
                "similarity_version": self.config.similarity.version,
                "model_version": self.config.model.version,
                "random_seed": self.config.random_seed,
                "config_fingerprint": provenance["config_fingerprint"],
                "feature_count": len(FEATURE_ALLOWLIST),
                "feature_fingerprint": feature_fp,
                "canonical_dedup_pass": len(rows) == len({row["canonical_opportunity_id"] for row in rows}),
                "outcome_fields_used_as_features": False,
                "imputation_fit_scope": "TRAIN_ONLY" if train_ids else "NONE",
                "scaler_fit_scope": "TRAIN_ONLY" if train_ids else "NONE",
            })
            with connection:
                connection.execute("DELETE FROM phase2_splits WHERE split_version = ?", (self.config.split.version,))
                connection.execute("DELETE FROM feature_sets WHERE version = ?", (self.config.feature_set_version,))
                connection.execute(
                    """
                    INSERT INTO feature_sets(version, name, dataset_fingerprint, config_fingerprint, metadata_json, fit_scope, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.config.feature_set_version, "Trading Agent Feature Store V1",
                        provenance["dataset_fingerprint"], provenance["config_fingerprint"],
                        canonical_json(feature_manifest), "TRAIN_ONLY" if train_ids else "NONE", _nowish(split_manifest.get("train_end")),
                    ),
                )
                for identifier, split in sorted(assignments.items()):
                    row = next(item for item in rows if item["canonical_opportunity_id"] == identifier)
                    connection.execute(
                        """
                        INSERT INTO phase2_splits(canonical_opportunity_id, split_version, split, timestamp_utc, dataset_fingerprint, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (identifier, self.config.split.version, split, row["timestamp_utc"], provenance["dataset_fingerprint"], _nowish(row["timestamp_utc"])),
                    )
                connection.execute("DELETE FROM canonical_features WHERE feature_set_version = ?", (self.config.feature_set_version,))
                for record in feature_records:
                    connection.execute(
                        """
                        INSERT INTO canonical_features(canonical_opportunity_id, feature_set_version, normalized_vector_json, output_names_json, missing_json, feature_status, feature_fingerprint, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record["canonical_opportunity_id"], self.config.feature_set_version,
                            canonical_json(list(record["normalized_vector"])), canonical_json(list(record["output_names"])),
                            canonical_json(record["missing"]), record.get("feature_status") or "INSUFFICIENT",
                            fingerprint(record), _nowish(split_manifest.get("train_end")),
                        ),
                    )
            _write_json(self._report("feature_manifest"), feature_manifest)
            _write_json(self._report("feature_quality"), quality)
            _write_json(self._report("split_manifest"), split_manifest)
            state = self._save_state({
                "dataset_fingerprint": provenance["dataset_fingerprint"],
                "repository_base_sha": provenance["repository_base_sha"],
                "generation_commit": provenance["generation_commit"],
                "canonical_opportunity_count": len(rows),
                "audit_observation_count": sum(int(row.get("observation_count", 0)) for row in rows),
                "feature_fingerprint": feature_fp,
                "feature_count": len(FEATURE_ALLOWLIST),
                "split_fingerprint": split_manifest.get("split_fingerprint"),
                "train_count": split_manifest.get("train_count", 0),
                "validation_count": split_manifest.get("validation_count", 0),
                "oos_count": split_manifest.get("oos_count", 0),
                "forward_status": split_manifest.get("forward_status"),
                "feature_store_ready": bool(rows),
                "feature_quality_status": "PASS" if bool(rows) and quality.get("canonical_dedup_pass") else "INSUFFICIENT_DATA",
            })
            return {"status": state["feature_quality_status"], "canonical_count": len(rows), "manifest": feature_manifest, "split_manifest": split_manifest}
        finally:
            connection.close()

    def build_regimes(self) -> dict[str, Any]:
        connection = self._open()
        try:
            rows, _, _ = self._load_rows_with_features(connection)
            splits = self._load_split_map(connection)
            train_ids = tuple(
                identifier for identifier, split in splits.items()
                if split == "TRAIN"
                and str(next(row for row in rows if row["canonical_opportunity_id"] == identifier).get("feature_status", "")).upper() != "CONFLICT"
            )
            split_manifest = _json_load(self._report("split_manifest"), {})
            config = fit_regime_config(
                rows,
                train_ids,
                version=self.config.regime_version,
                training_cutoff=split_manifest.get("train_end"),
            )
            assignments = RegimeEngine(config).assign_many(rows)
            validation = validate_regimes(rows, assignments)
            # Feature coverage is also required by regime so sparse StdDev /
            # Z-score fields remain visible after the regime pass.
            quality = _json_load(self._report("feature_quality"), {})
            quality_by_regime = missingness_report(
                rows,
                feature_names=sorted(FEATURE_ALLOWLIST),
                regime_by={identifier: assignment.composite_regime for identifier, assignment in assignments.items()},
            )
            quality["by_regime"] = quality_by_regime.get("by_regime", {})
            quality["regime_coverage_feature_set_version"] = self.config.feature_set_version
            quality["regime_version"] = config.version
            _write_json(self._report("feature_quality"), quality)
            with connection:
                connection.execute("DELETE FROM regime_assignments WHERE regime_version = ?", (self.config.regime_version,))
                for identifier, assignment in sorted(assignments.items()):
                    connection.execute(
                        """
                        INSERT INTO regime_assignments(canonical_opportunity_id, regime_version, trend_state, volatility_state, liquidity_state, composite_regime, confidence, reason, source_reported_regime, config_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            identifier, assignment.regime_version, assignment.trend_state,
                            assignment.volatility_state, assignment.liquidity_state, assignment.composite_regime,
                            assignment.confidence, assignment.reason, assignment.source_reported_regime,
                            canonical_json(config.to_dict()), _nowish(config.training_cutoff),
                        ),
                    )
            manifest = {
                "schema": "trading_agent_phase2_regime_manifest_v1",
                **self._base_provenance(connection),
                "regime_version": config.version,
                "threshold_source": config.threshold_source,
                "threshold_values": config.thresholds,
                "training_cutoff": config.training_cutoff,
                "training_count": len(config.training_ids),
                "assignment_count": len(assignments),
                "validation": validation,
                "outcome_dependency": False,
            }
            _write_json(self._report("regime_manifest"), manifest)
            _write_text(self._report("regime_report"), render_regime_report(manifest))
            state = self._save_state({
                "regime_ready": bool(rows),
                "regime_fingerprint": validation.get("regime_fingerprint"),
                "regime_validation": validation,
            })
            return {"status": "PASS" if rows else "INSUFFICIENT_DATA", "manifest": manifest, "validation": validation}
        finally:
            connection.close()

    def validate_similarity(self) -> dict[str, Any]:
        connection = self._open()
        try:
            rows, _, vectors = self._load_rows_with_features(connection)
            regimes = self._load_regime_map(connection)
            for row in rows:
                row["regime"] = regimes.get(str(row["canonical_opportunity_id"]), {"composite_regime": "UNKNOWN", "confidence": "LOW"})
            splits = self._load_split_map(connection)
            config = self.config.similarity
            results = evaluate_temporal_similarity(rows, vectors, splits=splits, config=config)
            validation = validate_similarity_results(results)
            run_id = "sim-" + fingerprint({
                "dataset_fingerprint": self._base_provenance(connection)["dataset_fingerprint"],
                "feature_set_version": self.config.feature_set_version,
                "split_version": self.config.split.version,
                "similarity_config": config.to_dict(),
            })
            no_opinion = sum(result.opinion_status == "NO_OPINION" for result in results.values())
            with connection:
                connection.execute("DELETE FROM similarity_runs WHERE run_id = ?", (run_id,))
                connection.execute(
                    """
                    INSERT INTO similarity_runs(run_id, similarity_version, dataset_fingerprint, feature_set_version, config_json, query_count, no_opinion_count, temporal_leakage_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, config.version, self._base_provenance(connection)["dataset_fingerprint"], self.config.feature_set_version, canonical_json(config.to_dict()), len(results), no_opinion, validation["temporal_leakage_count"], _nowish(max((str(row.get("timestamp_utc")) for row in rows), default=None))),
                )
                for query_id, result in sorted(results.items()):
                    for neighbor in result.neighbors:
                        connection.execute(
                            """
                            INSERT INTO similarity_neighbors(run_id, query_opportunity_id, neighbor_opportunity_id, rank, distance, neighbor_timestamp_utc, neighbor_regime, neighbor_side, historical_outcome_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                run_id, query_id, neighbor.canonical_opportunity_id, neighbor.rank, neighbor.distance,
                                neighbor.timestamp_utc, neighbor.regime, neighbor.side,
                                canonical_json(neighbor.historical_outcome or {}),
                            ),
                        )
            payload = {
                "schema": "trading_agent_phase2_similarity_validation_v1",
                **self._base_provenance(connection),
                "run_id": run_id,
                "similarity_version": config.version,
                "config": config.to_dict(),
                "query_count": len(results),
                "no_opinion_count": no_opinion,
                "opinion_status_counts": _count_statuses(results),
                "reason_counts": _count_reasons(results),
                "validation": validation,
                "filter_coverage": _merge_filter_coverage(results),
                "results": {identifier: result.to_dict() for identifier, result in sorted(results.items())},
            }
            _write_json(self._report("similarity_results"), payload)
            _write_text(self._report("similarity_report"), render_similarity_report(payload))
            state = self._save_state({
                "similarity_ready": bool(rows) and validation["passed"],
                "similarity_run_id": run_id,
                "similarity_validation": validation,
                "similarity_no_opinion_count": no_opinion,
            })
            return {"status": "PASS" if rows and validation["passed"] else "INSUFFICIENT_DATA", "payload": payload}
        finally:
            connection.close()

    def train(self) -> dict[str, Any]:
        connection = self._open()
        try:
            rows, preprocessor, vectors = self._load_rows_with_features(connection)
            splits = self._load_split_map(connection)
            regimes = self._load_regime_map(connection)
            bundle = train_models(
                rows,
                splits,
                vectors=vectors,
                preprocessor=preprocessor,
                regimes=regimes,
                dataset_fingerprint=self._base_provenance(connection)["dataset_fingerprint"],
                split_version=self.config.split.version,
                config=self.config.model,
            )
            bundle_payload = bundle.to_dict()
            _write_json(self._report("model_bundle"), bundle_payload)
            similarities_payload = _json_load(self._report("similarity_results"), {})
            similarities = similarities_payload.get("results", {}) if isinstance(similarities_payload, Mapping) else {}
            prediction_records = predict_rows(rows, bundle, regimes=regimes, similarities=similarities)
            with connection:
                connection.execute("DELETE FROM model_predictions WHERE model_version = ?", (bundle.model_version,))
                connection.execute("DELETE FROM model_registry WHERE model_version = ?", (bundle.model_version,))
                connection.execute(
                    """
                    INSERT INTO model_registry(model_version, model_type, feature_set_version, split_version, dataset_fingerprint, fit_ids_json, calibration_fit_ids_json, metadata_json, model_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bundle.model_version, "logistic_regression+ridges+priors", bundle.feature_set_version,
                        bundle.split_version, bundle.dataset_fingerprint, canonical_json(bundle.training_ids),
                        canonical_json(bundle.calibration_ids), canonical_json(bundle.metadata),
                        canonical_json(bundle_payload), _nowish(bundle.training_cutoff),
                    ),
                )
                for identifier, score in sorted(prediction_records.items()):
                    connection.execute(
                        """
                        INSERT INTO model_predictions(model_version, canonical_opportunity_id, split, p_plus_1r_before_minus_1r, expected_r_24bar, regime, similarity_sample_size, model_confidence, data_quality, score_status, reason, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            bundle.model_version, identifier, splits.get(identifier, "UNKNOWN"), score.p_plus_1r_before_minus_1r,
                            score.expected_r_24bar, score.regime, score.similarity_sample_size, score.model_confidence,
                            score.data_quality, score.score_status, score.reason, _nowish(bundle.training_cutoff),
                        ),
                    )
            manifest = {
                "schema": "trading_agent_phase2_model_manifest_v1",
                **self._base_provenance(connection),
                "model_version": bundle.model_version,
                "feature_version": bundle.feature_set_version,
                "split_version": bundle.split_version,
                "model_status": bundle.status,
                "model_types": ["unconditional_prior", "regime_prior", "historical_similarity", "logistic_regression", "ridge_regression"],
                "training_count": len(bundle.training_ids),
                "classification_fit_count": len(bundle.logistic.fit_ids) if bundle.logistic else 0,
                "regression_fit_count": len(bundle.ridge.fit_ids) if bundle.ridge else 0,
                "calibration_fit_count": len(bundle.calibration_ids),
                "fit_scope": "TRAIN_ONLY",
                "calibration_scope": "TRAIN_VALIDATION_ONLY",
                "oos_used_for_fit": False,
                "seed": bundle.seed,
                "preprocessing_fingerprint": bundle.preprocessor.to_dict().get("preprocessing_fingerprint"),
                "prediction_count": len(prediction_records),
            }
            _write_json(self._report("model_manifest"), manifest)
            state = self._save_state({
                "model_ready": bundle.status == "READY",
                "model_status": bundle.status,
                "model_version": bundle.model_version,
                "model_manifest": manifest,
            })
            return {"status": bundle.status, "manifest": manifest, "prediction_count": len(prediction_records)}
        finally:
            connection.close()

    def evaluate(self) -> dict[str, Any]:
        connection = self._open()
        try:
            bundle_payload = _json_load(self._report("model_bundle"), None)
            if not isinstance(bundle_payload, Mapping):
                self.train()
                bundle_payload = _json_load(self._report("model_bundle"), {})
            bundle = ModelBundle.from_dict(bundle_payload)
            rows, _, _ = self._load_rows_with_features(connection)
            splits = self._load_split_map(connection)
            regimes = self._load_regime_map(connection)
            similarities_payload = _json_load(self._report("similarity_results"), {})
            similarities = similarities_payload.get("results", {}) if isinstance(similarities_payload, Mapping) else {}
            validation = evaluate_models(rows, splits, bundle, regimes=regimes, similarities=similarities)
            validation.update({
                "dataset_fingerprint": self._base_provenance(connection)["dataset_fingerprint"],
                "repository_base_sha": self._base_provenance(connection)["repository_base_sha"],
                "generation_commit": self._base_provenance(connection)["generation_commit"],
                "feature_set_version": self.config.feature_set_version,
                "split_version": self.config.split.version,
                "regime_version": self.config.regime_version,
                "similarity_version": self.config.similarity.version,
                "model_version": self.config.model.version,
                "random_seed": self.config.random_seed,
                "config_fingerprint": fingerprint(self.config.to_dict()),
            })
            _write_json(self._report("model_validation"), validation)
            _write_text(self._report("model_validation_md"), render_model_validation(validation))
            state = self._save_state({
                "validation": validation,
                "predictive_edge_status": validation.get("predictive_edge_status", "INSUFFICIENT_DATA"),
            })
            return {"status": "PASS", "predictive_edge_status": state["predictive_edge_status"], "validation": validation}
        finally:
            connection.close()

    def report(self) -> dict[str, Any]:
        connection = self._open()
        try:
            state = self._state()
            quality = _json_load(self._report("feature_quality"), {})
            split_manifest = _json_load(self._report("split_manifest"), {})
            model_validation = _json_load(self._report("model_validation"), {})
            integrity = integrity_status(connection)
            phase1_leakage = run_leakage_checks(connection)
            checks = {
                "phase1_data_available": int(state.get("canonical_opportunity_count", 0)) > 0,
                "canonical_dedup": bool(quality.get("canonical_dedup_pass", False)),
                "temporal_split": bool(split_manifest.get("chronological", False)),
                "canonical_overlap": int(split_manifest.get("canonical_overlap_count", 1)) == 0,
                "feature_leakage": not bool(quality.get("outcome_fields_used_as_features", True)),
                "phase1_lookahead": int(phase1_leakage.get("lookahead_violations", 0)) == 0,
                "sqlite_foreign_keys": bool(integrity.get("foreign_key_ok")),
                "sqlite_integrity": bool(integrity.get("integrity_ok")),
                "similarity_temporal": int(state.get("similarity_validation", {}).get("temporal_leakage_count", 1)) == 0,
                "reproducibility_fingerprints": bool(state.get("feature_fingerprint")) and bool(state.get("split_fingerprint")),
                "regime_pipeline": bool(state.get("regime_ready", False)),
                "scoring_pipeline": bool(state.get("model_ready", False)),
            }
            engineering_status = "PASS" if all(checks.values()) else "FAIL"
            predictive = model_validation.get("predictive_edge_status", state.get("predictive_edge_status", "INSUFFICIENT_DATA"))
            leakage_ready = checks["phase1_data_available"] and checks["feature_leakage"] and checks["phase1_lookahead"] and checks["similarity_temporal"]
            reproducibility_ready = checks["phase1_data_available"] and checks["reproducibility_fingerprints"]
            report = {
                "PHASE2_ENGINEERING_STATUS": engineering_status,
                "FEATURE_STORE_READY": "YES" if state.get("feature_store_ready") else "NO",
                "REGIME_ENGINE_READY": "YES" if state.get("regime_ready") else "NO",
                "SIMILARITY_ENGINE_READY": "YES" if state.get("similarity_ready") else "NO",
                "SIGNAL_SCORING_READY": "YES" if state.get("model_ready") else "NO",
                "LEAKAGE_STATUS": "PASS" if leakage_ready else "INSUFFICIENT_DATA" if not checks["phase1_data_available"] else "FAIL",
                "REPRODUCIBILITY_STATUS": "PASS" if reproducibility_ready else "INSUFFICIENT_DATA" if not checks["phase1_data_available"] else "FAIL",
                "TRAIN_COUNT": int(state.get("train_count", 0)),
                "VALIDATION_COUNT": int(state.get("validation_count", 0)),
                "OOS_COUNT": int(state.get("oos_count", 0)),
                "PREDICTIVE_EDGE_STATUS": predictive,
                "LIVE_EXECUTION_ENABLED": "NO",
                "READY_FOR_PHASE3": "YES" if engineering_status == "PASS" else "NO",
                "dataset_fingerprint": state.get("dataset_fingerprint"),
                "input_dataset_status": "AVAILABLE" if state.get("canonical_opportunity_count", 0) else "MISSING_PHASE1_DATA",
                "repository_base_sha": state.get("repository_base_sha"),
                "head_sha_at_generation": state.get("generation_commit"),
                "canonical_opportunity_count": state.get("canonical_opportunity_count", 0),
                "audit_observation_count": state.get("audit_observation_count", 0),
                "feature_set_version": self.config.feature_set_version,
                "feature_count": int(state.get("feature_count", len(FEATURE_ALLOWLIST))),
                "checks": checks,
                "integrity": integrity,
            }
            _write_text(self._report("phase2_report"), render_phase2_report(report))
            _write_text(self._report("architecture"), render_architecture_report({
                "repository_base_sha": report.get("repository_base_sha"),
                "generation_commit": report.get("head_sha_at_generation"),
                "dataset_fingerprint": report.get("dataset_fingerprint"),
                "feature_set_version": report.get("feature_set_version"),
                "split_version": self.config.split.version,
                "regime_version": self.config.regime_version,
                "similarity_version": self.config.similarity.version,
                "model_version": self.config.model.version,
                "random_seed": self.config.random_seed,
                "config_fingerprint": fingerprint(self.config.to_dict()),
            }))
            self._save_state({"phase2_engineering_status": engineering_status, "engineering_checks": checks, "report": report})
            return report
        finally:
            connection.close()

    def run_all(self) -> dict[str, Any]:
        self.build_features()
        self.build_regimes()
        self.validate_similarity()
        self.train()
        self.evaluate()
        return self.report()


def _count_statuses(results: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results.values():
        status = result.opinion_status
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _count_reasons(results: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results.values():
        counts[result.reason] = counts.get(result.reason, 0) + 1
    return dict(sorted(counts.items()))


def _merge_filter_coverage(results: Mapping[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for result in results.values():
        for key, value in result.filter_coverage.items():
            totals[key] = totals.get(key, 0) + int(value)
    return dict(sorted(totals.items()))


def render_regime_report(payload: Mapping[str, Any]) -> str:
    validation = payload.get("validation", {})
    return "\n".join([
        "# Regime Engine V1",
        "",
        "Rule-based, deterministic and fit without outcome fields.",
        "",
        f"- Regime version: `{payload.get('regime_version')}`",
        f"- Threshold source: `{payload.get('threshold_source')}`",
        f"- Training cutoff: `{payload.get('training_cutoff')}`",
        f"- Training count: `{payload.get('training_count', 0)}`",
        f"- Assignment count: `{payload.get('assignment_count', 0)}`",
        f"- Coverage: `{validation.get('coverage', 0)}`",
        f"- Source-reported coverage: `{validation.get('source_reported_coverage', 0)}`",
        f"- Agreement rate: `{validation.get('agreement_rate')}`",
        f"- Transition frequency: `{validation.get('transition_frequency', 0)}`",
        f"- Dataset fingerprint: `{payload.get('dataset_fingerprint')}`",
        f"- Base SHA: `{payload.get('repository_base_sha')}`",
        f"- Generation SHA: `{payload.get('generation_commit')}`",
        f"- Feature Set: `{payload.get('feature_set_version')}`",
        f"- Split version: `{payload.get('split_version')}`",
        f"- Random seed: `{payload.get('random_seed')}`",
        "",
        "## Distribution",
        "",
        "```json",
        json.dumps(validation.get("distribution", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "Outcome columns are not used to fit thresholds or validate taxonomy.",
    ])


def render_similarity_report(payload: Mapping[str, Any]) -> str:
    validation = payload.get("validation", {})
    return "\n".join([
        "# Historical Similarity V1",
        "",
        "Neighbors are selected from normalized feature vectors only and are evaluated in an expanding temporal index.",
        "",
        f"- Run: `{payload.get('run_id')}`",
        f"- Dataset fingerprint: `{payload.get('dataset_fingerprint')}`",
        f"- Base SHA: `{payload.get('repository_base_sha')}`",
        f"- Generation SHA: `{payload.get('generation_commit')}`",
        f"- Feature Set: `{payload.get('feature_set_version')}`",
        f"- Split version: `{payload.get('split_version')}`",
        f"- Random seed: `{payload.get('random_seed')}`",
        f"- Query count: `{payload.get('query_count', 0)}`",
        f"- NO_OPINION count: `{payload.get('no_opinion_count', 0)}`",
        f"- Opinion statuses: `{json.dumps(payload.get('opinion_status_counts', {}), sort_keys=True)}`",
        f"- Reasons: `{json.dumps(payload.get('reason_counts', {}), sort_keys=True)}`",
        f"- Temporal leakage count: `{validation.get('temporal_leakage_count')}`",
        f"- Self-match count: `{validation.get('self_match_count')}`",
        f"- Validation: `{'PASS' if validation.get('passed') else 'FAIL'}`",
        "",
        "Historical outcomes are attached only after feature-only neighbor selection.",
    ])


def render_model_validation(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Phase 2 Model Validation",
        "",
        f"- Dataset fingerprint: `{payload.get('dataset_fingerprint')}`",
        f"- Base SHA: `{payload.get('repository_base_sha')}`",
        f"- Generation SHA: `{payload.get('generation_commit')}`",
        f"- Feature Set: `{payload.get('feature_set_version')}`",
        f"- Split version: `{payload.get('split_version')}`",
        f"- Regime version: `{payload.get('regime_version')}`",
        f"- Similarity version: `{payload.get('similarity_version')}`",
        f"- Model version: `{payload.get('model_version')}`",
        f"- Random seed: `{payload.get('random_seed')}`",
        "",
        f"- Predictive edge status: `{payload.get('predictive_edge_status')}`",
        f"- Fit scope: `{payload.get('fit_scope')}`",
        f"- Calibration scope: `{payload.get('calibration_scope')}`",
        f"- OOS used for tuning: `{payload.get('oos_used_for_tuning')}`",
        "",
    ]
    for split, values in sorted(payload.get("by_split", {}).items()):
        lines.extend([f"## {split}", "", f"Rows: `{values.get('count', 0)}`", ""])
        for model, metrics in sorted(values.get("classification", {}).items()):
            lines.append(f"- Classification `{model}`: count={metrics.get('count')}, Brier={metrics.get('brier_score')}, ROC-AUC={metrics.get('roc_auc')}, PR-AUC={metrics.get('pr_auc')}")
        for model, metrics in sorted(values.get("regression", {}).items()):
            lines.append(f"- Regression `{model}`: count={metrics.get('count')}, MAE={metrics.get('mae')}, RMSE={metrics.get('rmse')}, Spearman={metrics.get('spearman_rank_correlation')}")
        if values.get("diagnostic_target_coverage"):
            lines.append("- Secondary target coverage: " + json.dumps(values["diagnostic_target_coverage"], sort_keys=True))
        lines.append("")
    lines.extend(["## Walk-forward", "", "```json", json.dumps(payload.get("walk_forward", {}), ensure_ascii=False, indent=2, sort_keys=True), "```"])
    return "\n".join(lines)


def render_phase2_report(report: Mapping[str, Any]) -> str:
    ordered = (
        "PHASE2_ENGINEERING_STATUS", "FEATURE_STORE_READY", "REGIME_ENGINE_READY",
        "SIMILARITY_ENGINE_READY", "SIGNAL_SCORING_READY", "LEAKAGE_STATUS",
        "REPRODUCIBILITY_STATUS", "TRAIN_COUNT", "VALIDATION_COUNT", "OOS_COUNT",
        "PREDICTIVE_EDGE_STATUS", "LIVE_EXECUTION_ENABLED", "READY_FOR_PHASE3",
    )
    lines = ["# Trading Agent Phase 2", "", "Offline / research / shadow intelligence only.", ""]
    lines.extend(f"{key}: {report.get(key)}" for key in ordered)
    lines.extend([
        "",
        "## Provenance",
        "",
        f"- Base SHA: `{report.get('repository_base_sha')}`",
        f"- Generation SHA: `{report.get('head_sha_at_generation')}`",
        f"- Phase 1 dataset fingerprint: `{report.get('dataset_fingerprint')}`",
        f"- Input dataset status: `{report.get('input_dataset_status')}`",
        f"- Canonical opportunities: `{report.get('canonical_opportunity_count', 0)}`",
        f"- Audit observations: `{report.get('audit_observation_count', 0)}`",
        f"- Feature Set: `{report.get('feature_set_version')}`",
        f"- Registered features: `{report.get('feature_count')}`",
        "",
        "## Engineering checks",
        "",
        "```json",
        json.dumps(report.get("checks", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "Signal scoring emits opinion/status metadata only. No execution command, order, position, lot, SL, TP, pyramid or risk-management output is implemented.",
        "If input dataset status is `MISSING_PHASE1_DATA`, this checkout contains no Phase 1 SQLite/raw observations; the pipeline intentionally reports FAIL/INSUFFICIENT_DATA instead of reconstructing them.",
    ])
    return "\n".join(lines)


def render_architecture_report(provenance: Mapping[str, Any] | None = None) -> str:
    provenance = provenance or {}
    return "\n".join([
        "# Phase 2 V1 Architecture Validation",
        "",
        "```text",
        "raw/audit data",
        "      ↓",
        "canonical opportunity (one sample per canonical_opportunity_id)",
        "      ↓",
        "feature store (closed allowlist, train-only preprocessing)",
        "      ↓",
        "rule-based regime engine",
        "      ↓",
        "historical similarity (expanding, past-only index)",
        "      ↓",
        "signal scoring (offline/shadow output)",
        "      ↓",
        "offline/shadow report",
        "```",
        "",
        "Validated negative path:",
        "",
        "```text",
        "signal scoring",
        "      ↓",
        "NO MT5 order path",
        "```",
        "",
        "Phase 2 does not import, call or mutate execution logic; it has no order writer or live bridge.",
        "",
        "## Provenance",
        "",
        f"- Base SHA: `{provenance.get('repository_base_sha')}`",
        f"- Generation SHA: `{provenance.get('generation_commit')}`",
        f"- Phase 1 dataset fingerprint: `{provenance.get('dataset_fingerprint')}`",
        f"- Feature Set: `{provenance.get('feature_set_version')}`",
        f"- Split version: `{provenance.get('split_version')}`",
        f"- Regime version: `{provenance.get('regime_version')}`",
        f"- Similarity version: `{provenance.get('similarity_version')}`",
        f"- Model version: `{provenance.get('model_version')}`",
        f"- Random seed: `{provenance.get('random_seed')}`",
        f"- Config fingerprint: `{provenance.get('config_fingerprint')}`",
    ])


__all__ = ["Phase2Pipeline", "REPORT_FILENAMES", "render_architecture_report", "render_phase2_report"]
