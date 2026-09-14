import json
import sqlite3
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.data.episodes.builder import build_bundle
from agent.data.models import NormalizedEvent
from agent.features.builder import build_canonical_view, persist_canonical_view
from agent.features.fingerprint import fingerprint_records
from agent.features.normalization import TrainOnlyPreprocessor
from agent.features.registry import FeatureLeakageError, FeatureSchemaError
from agent.features.splits import SplitConfig, SplitError, build_temporal_splits
from agent.memory.database import apply_migrations, connect_database, integrity_status
from agent.memory.repository import TradingMemoryRepository
from agent.phase2.config import Phase2Config
from agent.phase2.pipeline import Phase2Pipeline
from agent.regime.config import fit_regime_config
from agent.regime.engine import RegimeEngine
from agent.scoring.labels import build_diagnostic_target, build_label
from agent.scoring.predict import assert_no_execution_action, score_opportunity
from agent.scoring.train import train_models
from agent.similarity.distance import standardized_euclidean
from agent.similarity.index import HistoricalSimilarityIndex, evaluate_temporal_similarity
from agent.similarity.models import SimilarityConfig
from agent.similarity.validation import validate_similarity_results


def _event(year: int, index: int, audit: str, label: str | None) -> NormalizedEvent:
    base = datetime(year, 1, 1, index, tzinfo=UTC)
    entry = 100.0 + index
    side = "LONG" if index % 2 == 0 else "SHORT"
    stop = entry - 2.0 if side == "LONG" else entry + 2.0
    numeric = {
        "entry_rsi": 50.0 + index,
        "entry_atr_pct": 1.0 + index * 0.01,
        "entry_spread_r": 0.1 + index * 0.001,
        "entry_return_std_20": 0.01 + index * 0.0001,
        "entry_return_std_rank": 50.0 + index,
        "entry_price_std_20": 2.0 + index * 0.01,
        "entry_price_std_100": 3.0 + index * 0.01,
        "entry_price_std_pct_20": 2.0 + index * 0.01,
        "entry_std_ratio_20_100": 0.7,
        "entry_price_z20": 0.5,
        "entry_price_abs_z20": 0.5,
        "entry_rsi_std_20": 4.0,
        "entry_rsi_std_rank": 60.0,
        "entry_atr_return_std_ratio": 2.0,
        "entry_atr_return_std_rank": 65.0,
    }
    first = label or "AMBIGUOUS"
    common = {
        "raw_event_type": "OPEN_OPPOSITE_SIDE" if audit == "V81" else "BLOCKED_OPPOSITE",
        "completed": True,
        "age_bars": 1,
        "initial_sl": stop,
        "risk_distance": 2.0,
        "shadow_initial_sl": stop,
        "shadow_risk_distance": 2.0,
        "shadow_plus_1r_first": label == "PLUS_1R" if label else None,
        "shadow_minus_1r_first": label == "MINUS_1R" if label else None,
        "shadow_first_hit": first,
        "shadow_mfe_r": 1.5,
        "shadow_mae_r": -0.5,
        "shadow_return_6bar_r": 0.2,
        "shadow_return_12bar_r": 0.3,
        "shadow_return_24bar_r": 0.4 if label == "PLUS_1R" else -0.4 if label == "MINUS_1R" else None,
        "shadow_return_48bar_r": 0.5,
        "d1_regime_score": 0.6,
        "h4_regime_score": 0.6,
        "composite_regime_score": 0.6,
    }
    if audit == "V81":
        fields = {**numeric, **common, "first_hit": first, "mfe_r": 1.5, "mae_r": -0.5, "return_6": 0.2, "return_12": 0.3, "return_24": 0.4, "return_48": 0.5}
        return NormalizedEvent(
            "fixture-v81", "BLOCKED_SIGNAL", (base + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            (base + timedelta(hours=1)).isoformat(), "UTC", "BTCUSD", "H1", "V26", "V81", side,
            f"v81-{index}", entry, None, fields, {"event_id": f"v81-{index}"},
        )
    fields = {
        **common,
        "shadow_entry_rsi": numeric["entry_rsi"],
        "entry_atr_pct": numeric["entry_atr_pct"],
        "entry_spread_r": numeric["entry_spread_r"],
        "shadow_entry_rsi_ema": numeric["entry_rsi"],
        "shadow_entry_rsi_wma": numeric["entry_rsi"],
        "d1_bias": "BULLISH",
        "h4_bias": "BULLISH",
        "h1_bias": "BULLISH",
        "shadow_entry_price": entry,
        "event_type": "BLOCKED_OPPOSITE",
    }
    return NormalizedEvent(
        "fixture-v82", "BLOCKED_SIGNAL", base.isoformat().replace("+00:00", "Z"), base.isoformat(), "UTC",
        "BTCUSD", "H1", "V26", "V82", side, f"{int(base.timestamp())}_v82-{index}", entry, None,
        fields, {"event_id": f"{int(base.timestamp())}_v82-{index}"},
    )


def _fixture_database(path: Path, count: int = 12) -> sqlite3.Connection:
    connection = connect_database(path)
    apply_migrations(connection)
    repository = TradingMemoryRepository(connection)
    source_id = repository.insert_source_artifact({
        "path": "fixture.csv", "artifact_type": "BLOCKED_SIGNAL_SHADOW_TELEMETRY", "sha256": "fixture-hash",
        "file_size": 1, "parser_name": "fixture", "parser_version": "fixture/1", "strategy_version": "V26",
        "audit_version": "V82", "source_timezone": "UTC", "status": "IMPORTED",
    })
    with connection:
        for index in range(count):
            year = 2023 if index < 6 else 2024 if index < 9 else 2025
            label = "PLUS_1R" if index % 2 == 0 else "MINUS_1R"
            for audit in ("V81", "V82"):
                bundle = build_bundle(
                    _event(year, index, audit, label), source_artifact_id=source_id,
                    experiment_id=None, preset_id=None, ordinal=1,
                )
                repository.insert_episode(bundle.episode)
                repository.insert_features(bundle.features)
                repository.insert_outcome(bundle.outcome)
                if bundle.opportunity_context:
                    repository.insert_opportunity_context(bundle.opportunity_context)
                    repository.insert_active_context(bundle.active_context)
                    repository.insert_opportunity_outcome(bundle.opportunity_outcome)
    return connection


class Phase2ContractTests(unittest.TestCase):
    def test_canonical_view_deduplicates_v81_v82_and_preserves_provenance(self):
        with TemporaryDirectory() as directory:
            connection = _fixture_database(Path(directory) / "memory.db", count=2)
            rows = build_canonical_view(connection)
            self.assertEqual(len(rows), 2)
            self.assertEqual(sum(row["observation_count"] for row in rows), 4)
            self.assertTrue(all(row["observation_count"] == 2 for row in rows))
            self.assertEqual(rows[0]["labels"]["plus_1r_before_minus_1r"], 1)
            self.assertEqual(len(rows[0]["episode_ids"]), 2)
            persist_canonical_view(connection, rows)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM canonical_opportunities").fetchone()[0], 2)
            connection.close()

    def test_canonical_conflicting_audit_feature_is_quarantined(self):
        with TemporaryDirectory() as directory:
            connection = _fixture_database(Path(directory) / "memory.db", count=1)
            v82_episode = connection.execute("SELECT episode_id FROM trading_episodes WHERE audit_version = 'V82'").fetchone()[0]
            connection.execute("UPDATE episode_features SET rsi = 999.0 WHERE episode_id = ?", (v82_episode,))
            connection.commit()
            row = build_canonical_view(connection)[0]
            self.assertIsNone(row["features"]["rsi"])
            self.assertEqual(row["field_status"]["rsi"], "CONFLICT")
            self.assertIn("rsi", row["feature_conflicts"])
            self.assertIn("field_provenance", row["provenance"])
            connection.close()

    def test_allowlist_rejects_outcome_and_unknown_fields(self):
        preprocessor = TrainOnlyPreprocessor.fit([{"canonical_opportunity_id": "a", "features": {"rsi": 50}}], ["a"])
        with self.assertRaises(FeatureLeakageError):
            preprocessor.transform_one({"canonical_opportunity_id": "b", "features": {"rsi": 50, "shadow_return_24bar_r": 2}})
        with self.assertRaises(FeatureSchemaError):
            preprocessor.transform_one({"canonical_opportunity_id": "b", "features": {"rsi": 50, "new_unregistered_field": 2}})
        with self.assertRaises(FeatureLeakageError):
            preprocessor.transform_one({
                "canonical_opportunity_id": "b",
                "feature_vector": {"rsi": 0.0, "shadow_first_hit": 1.0},
            })

    def test_context_features_are_fit_from_train_only(self):
        rows = [
            {"canonical_opportunity_id": "a", "features": {"rsi": 50}, "context": {"d1_bias": "BULLISH"}},
            {"canonical_opportunity_id": "b", "features": {"rsi": 51}, "context": {"d1_bias": "BEARISH"}},
            {"canonical_opportunity_id": "c", "features": {"rsi": 52}, "context": {"d1_bias": "OUT_OF_SAMPLE"}},
        ]
        preprocessor = TrainOnlyPreprocessor.fit(rows, ["a", "b"])
        self.assertEqual(preprocessor.categorical_levels["d1_bias"], ("BEARISH", "BULLISH"))
        names = set(preprocessor.output_names)
        self.assertIn("d1_bias=BULLISH", names)
        self.assertNotIn("d1_bias=OUT_OF_SAMPLE", names)

    def test_train_only_imputation_and_scaler_statistics(self):
        rows = [
            {"canonical_opportunity_id": "a", "features": {"rsi": 10.0}},
            {"canonical_opportunity_id": "b", "features": {"rsi": 20.0}},
            {"canonical_opportunity_id": "c", "features": {"rsi": 10000.0}},
        ]
        preprocessor = TrainOnlyPreprocessor.fit(rows, ["a", "b"])
        self.assertEqual(preprocessor.numeric_stats["rsi"]["mean"], 15.0)
        self.assertEqual(preprocessor.numeric_stats["rsi"]["fit_scope"], "TRAIN_ONLY")
        self.assertGreater(abs(preprocessor.transform_one(rows[2])[0]), 1000.0)
        missing = preprocessor.transform_one({"canonical_opportunity_id": "d", "features": {}})
        self.assertEqual(missing[1], 1.0)

    def test_scoring_uses_ood_abstention_and_has_no_execution_payload(self):
        rows = [
            {"canonical_opportunity_id": "a", "timestamp_utc": "2023-01-01T00:00:00Z", "features": {"rsi": 40}, "labels": {"shadow_first_hit": "PLUS_1R", "resolved": 1, "shadow_return_24bar_r": 0.5}},
            {"canonical_opportunity_id": "b", "timestamp_utc": "2023-01-02T00:00:00Z", "features": {"rsi": 60}, "labels": {"shadow_first_hit": "MINUS_1R", "resolved": 1, "shadow_return_24bar_r": -0.5}},
            {"canonical_opportunity_id": "c", "timestamp_utc": "2024-01-01T00:00:00Z", "features": {"rsi": 1000}, "labels": {}},
        ]
        bundle = train_models(rows, {"a": "TRAIN", "b": "TRAIN", "c": "OOS"})
        score = score_opportunity(rows[2], bundle)
        self.assertEqual(score.score_status, "NO_OPINION")
        self.assertEqual(score.reason, "OUT_OF_DISTRIBUTION")
        assert_no_execution_action(score.to_dict())

    def test_temporal_split_is_grouped_and_chronological(self):
        rows = [
            {"canonical_opportunity_id": "a", "timestamp_utc": "2023-01-01T00:00:00Z"},
            {"canonical_opportunity_id": "b", "timestamp_utc": "2024-01-01T00:00:00Z"},
            {"canonical_opportunity_id": "c", "timestamp_utc": "2025-01-01T00:00:00Z"},
        ]
        splits = build_temporal_splits(rows, SplitConfig(train_end="2024-01-01T00:00:00Z", validation_end="2025-01-01T00:00:00Z"))
        self.assertEqual(splits, {"a": "TRAIN", "b": "VALIDATION", "c": "OOS"})
        duplicate_assignments = build_temporal_splits(rows + [rows[0]], SplitConfig(train_end="2024-01-01T00:00:00Z", validation_end="2025-01-01T00:00:00Z"))
        self.assertEqual(duplicate_assignments, splits)
        audit_pair = build_temporal_splits(
            [
                {"canonical_opportunity_id": "x", "timestamp_utc": "2023-06-01T00:00:00Z"},
                {"canonical_opportunity_id": "x", "timestamp_utc": "2025-06-01T00:00:00Z"},
            ],
            SplitConfig(train_end="2024-01-01T00:00:00Z", validation_end="2025-01-01T00:00:00Z"),
        )
        self.assertEqual(audit_pair, {"x": "OOS"})

    def test_label_builder_abstains_on_ambiguous_unresolved_and_incomplete(self):
        self.assertEqual(build_label({"shadow_first_hit": "PLUS_1R"}), 1)
        self.assertEqual(build_label({"shadow_first_hit": "MINUS_1R"}), 0)
        self.assertIsNone(build_label({"shadow_first_hit": "AMBIGUOUS"}))
        self.assertIsNone(build_label({"shadow_first_hit": "UNRESOLVED"}))
        self.assertIsNone(build_label({"shadow_first_hit": "PLUS_1R", "resolved": 0}))
        self.assertIsNone(build_label({"shadow_first_hit": "PLUS_1R", "incomplete_reason": "tester_end"}))
        self.assertIsNone(build_label({"shadow_first_hit": "PLUS_1R", "shadow_plus_1r_first": 0}))
        self.assertIsNone(build_label({"shadow_first_hit": "MINUS_1R", "shadow_minus_1r_first": 0}))
        self.assertEqual(build_diagnostic_target({"resolved": 1, "shadow_return_6bar_r": 0.5}, "shadow_return_6bar_r"), 0.5)
        self.assertIsNone(build_diagnostic_target({"resolved": 0, "shadow_return_6bar_r": -1.0}, "shadow_return_6bar_r"))

    def test_similarity_excludes_self_and_future_and_rejects_outcome_distance(self):
        config = SimilarityConfig(top_k=3, min_neighbors=1, min_feature_overlap=1, regime_mode="none", require_outcome_available=False)
        query = {"canonical_opportunity_id": "q", "timestamp_utc": "2025-01-03T00:00:00Z", "symbol": "BTCUSD", "timeframe": "H1", "side": "LONG", "feature_vector": [1.0]}
        past = {"canonical_opportunity_id": "past", "timestamp_utc": "2025-01-01T00:00:00Z", "symbol": "BTCUSD", "timeframe": "H1", "side": "LONG", "feature_vector": [1.1], "label": 1}
        future = {"canonical_opportunity_id": "future", "timestamp_utc": "2025-01-04T00:00:00Z", "symbol": "BTCUSD", "timeframe": "H1", "side": "LONG", "feature_vector": [1.0], "label": 0}
        result = HistoricalSimilarityIndex([past, future], config=config).query(query)
        self.assertEqual([item.canonical_opportunity_id for item in result.neighbors], ["past"])
        self.assertTrue(validate_similarity_results({"q": result})["passed"])
        with self.assertRaises(FeatureLeakageError):
            standardized_euclidean({"rsi": 1.0, "shadow_return_24bar_r": 100.0}, {"rsi": 1.0, "shadow_return_24bar_r": -100.0})

    def test_expanding_similarity_regression_future_observation(self):
        rows = [
            {"canonical_opportunity_id": "t1", "timestamp_utc": "2025-01-01T00:00:00Z", "symbol": "BTCUSD", "timeframe": "H1", "side": "LONG", "labels": {"plus_1r_before_minus_1r": 1}},
            {"canonical_opportunity_id": "t3", "timestamp_utc": "2025-01-03T00:00:00Z", "symbol": "BTCUSD", "timeframe": "H1", "side": "LONG", "labels": {"plus_1r_before_minus_1r": 1}},
            {"canonical_opportunity_id": "t4", "timestamp_utc": "2025-01-04T00:00:00Z", "symbol": "BTCUSD", "timeframe": "H1", "side": "LONG", "labels": {"plus_1r_before_minus_1r": 0}},
        ]
        vectors = {"t1": [1.0], "t3": [1.0], "t4": [1.0]}
        result = evaluate_temporal_similarity(rows, vectors, splits={"t1": "TRAIN", "t3": "OOS", "t4": "OOS"}, config=SimilarityConfig(top_k=1, min_neighbors=1, min_feature_overlap=1, regime_mode="none", require_outcome_available=False))
        self.assertEqual(result["t3"].neighbors[0].canonical_opportunity_id, "t1")
        self.assertNotIn("t4", [item.canonical_opportunity_id for item in result["t3"].neighbors])

    def test_regime_thresholds_are_train_only_and_missing_falls_back_unknown(self):
        rows = [
            {"canonical_opportunity_id": "a", "features": {"atr_percent": 1.0, "spread_r": 0.1, "composite_regime_score": 0.6}},
            {"canonical_opportunity_id": "b", "features": {"atr_percent": 2.0, "spread_r": 0.2, "composite_regime_score": 0.6}},
            {"canonical_opportunity_id": "c", "features": {"atr_percent": 1000.0, "spread_r": 100.0, "composite_regime_score": -100.0}},
        ]
        config = fit_regime_config(rows, ["a", "b"])
        self.assertLess(config.thresholds["volatility_high"], 1000.0)
        assignment = RegimeEngine(config).assign({"canonical_opportunity_id": "c", "features": {}})
        self.assertEqual(assignment.composite_regime, "UNKNOWN")
        self.assertEqual(assignment.confidence, "LOW")

    def test_regime_fingerprint_is_order_independent_and_has_no_outcome_dependency(self):
        rows = [
            {"canonical_opportunity_id": "a", "features": {"atr_percent": 1.0, "spread_r": 0.1, "composite_regime_score": 0.6}, "labels": {"shadow_return_24bar_r": -999.0}},
            {"canonical_opportunity_id": "b", "features": {"atr_percent": 2.0, "spread_r": 0.2, "composite_regime_score": 0.6}, "labels": {"shadow_return_24bar_r": 999.0}},
        ]
        config_a = fit_regime_config(rows, ["a", "b"])
        config_b = fit_regime_config(list(reversed(rows)), ["a", "b"])
        self.assertEqual(config_a.to_dict(), config_b.to_dict())

    def test_pipeline_runs_and_reports_no_execution_on_fixture(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            connection = _fixture_database(root / "memory.db")
            connection.close()
            config = Phase2Config(
                split=SplitConfig(train_end="2024-01-01T00:00:00Z", validation_end="2025-01-01T00:00:00Z"),
                similarity=SimilarityConfig(top_k=5, min_neighbors=2, min_feature_overlap=3, regime_mode="none"),
            )
            pipeline = Phase2Pipeline(root=root, db_path="memory.db", report_dir="reports", config=config)
            report = pipeline.run_all()
            self.assertEqual(report["LIVE_EXECUTION_ENABLED"], "NO")
            self.assertEqual(report["PHASE2_ENGINEERING_STATUS"], "PASS")
            self.assertEqual(report["canonical_opportunity_count"], 12)
            self.assertEqual(report["TRAIN_COUNT"], 6)
            self.assertEqual(report["VALIDATION_COUNT"], 3)
            self.assertEqual(report["OOS_COUNT"], 3)
            self.assertEqual(report["checks"]["canonical_overlap"], True)
            self.assertTrue((root / "reports" / "phase2_report.md").exists())
            self.assertTrue((root / "reports" / "v1_architecture_validation.md").exists())
            check_connection = connect_database(root / "memory.db")
            self.assertTrue(integrity_status(check_connection)["integrity_ok"])
            self.assertTrue(integrity_status(check_connection)["foreign_key_ok"])
            check_connection.close()

    def test_pipeline_artifacts_are_reproducible_on_clean_fixture_state(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            connection = _fixture_database(root / "memory.db", count=12)
            connection.close()
            config = Phase2Config(
                split=SplitConfig(train_end="2024-01-01T00:00:00Z", validation_end="2025-01-01T00:00:00Z"),
                similarity=SimilarityConfig(top_k=5, min_neighbors=2, min_feature_overlap=3, regime_mode="none"),
            )
            pipeline = Phase2Pipeline(root=root, db_path="memory.db", report_dir="reports", config=config)
            pipeline.run_all()
            artifact_names = ("feature_manifest.json", "feature_quality_report.json", "split_manifest.json", "regime_manifest.json", "model_manifest.json", "model_validation.json")
            first = {name: (root / "reports" / name).read_bytes() for name in artifact_names}
            pipeline.run_all()
            second = {name: (root / "reports" / name).read_bytes() for name in artifact_names}
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
