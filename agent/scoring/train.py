"""Train-only model fitting for Signal Scoring V1."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from ..features.normalization import TrainOnlyPreprocessor
from ..features.registry import FEATURE_SET_VERSION
from .baseline import fit_regime_prior, fit_unconditional_prior
from .calibration import PlattCalibrator, fit_platt_calibrator
from .labels import build_expected_r_label, build_label
from .models import (
    LogisticRegressionModel,
    PriorModel,
    RidgeRegressionModel,
    fit_logistic_regression,
    fit_ridge_regression,
)


@dataclass(frozen=True)
class ModelConfig:
    version: str = "scoring/1"
    seed: int = 42
    logistic_l2: float = 1.0
    logistic_iterations: int = 400
    logistic_learning_rate: float = 0.05
    ridge_l2: float = 1.0
    calibration_iterations: int = 250
    calibration_learning_rate: float = 0.03
    min_training_labels: int = 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelConfig":
        values = {key: payload[key] for key in cls.__dataclass_fields__ if key in payload}
        return cls(**values)


@dataclass(frozen=True)
class ModelBundle:
    model_version: str
    feature_set_version: str
    split_version: str
    dataset_fingerprint: str
    preprocessor: TrainOnlyPreprocessor
    logistic: LogisticRegressionModel | None
    ridge: RidgeRegressionModel | None
    unconditional_prior: PriorModel
    regime_prior: PriorModel
    calibrator: PlattCalibrator
    training_ids: tuple[str, ...]
    calibration_ids: tuple[str, ...]
    training_cutoff: str | None
    seed: int
    status: str
    metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "feature_set_version": self.feature_set_version,
            "split_version": self.split_version,
            "dataset_fingerprint": self.dataset_fingerprint,
            "preprocessor": self.preprocessor.to_dict(),
            "logistic": self.logistic.to_dict() if self.logistic else None,
            "ridge": self.ridge.to_dict() if self.ridge else None,
            "unconditional_prior": self.unconditional_prior.to_dict(),
            "regime_prior": self.regime_prior.to_dict(),
            "calibrator": self.calibrator.to_dict(),
            "training_ids": list(self.training_ids),
            "calibration_ids": list(self.calibration_ids),
            "training_cutoff": self.training_cutoff,
            "seed": self.seed,
            "status": self.status,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelBundle":
        return cls(
            model_version=str(payload.get("model_version", "scoring/1")),
            feature_set_version=str(payload.get("feature_set_version", FEATURE_SET_VERSION)),
            split_version=str(payload.get("split_version", "phase2-split/1")),
            dataset_fingerprint=str(payload.get("dataset_fingerprint", "")),
            preprocessor=TrainOnlyPreprocessor.from_dict(payload.get("preprocessor", {})),
            logistic=LogisticRegressionModel.from_dict(payload["logistic"]) if payload.get("logistic") else None,
            ridge=RidgeRegressionModel.from_dict(payload["ridge"]) if payload.get("ridge") else None,
            unconditional_prior=PriorModel.from_dict(payload.get("unconditional_prior", {})),
            regime_prior=PriorModel.from_dict(payload.get("regime_prior", {})),
            calibrator=PlattCalibrator.from_dict(payload.get("calibrator", {})),
            training_ids=tuple(str(value) for value in payload.get("training_ids", ())),
            calibration_ids=tuple(str(value) for value in payload.get("calibration_ids", ())),
            training_cutoff=payload.get("training_cutoff"),
            seed=int(payload.get("seed", 42)),
            status=str(payload.get("status", "INSUFFICIENT_DATA")),
            metadata=dict(payload.get("metadata", {})),
        )


def _training_cutoff(rows: Iterable[Mapping[str, Any]], ids: Iterable[str]) -> str | None:
    wanted = {str(value) for value in ids}
    timestamps = [str(row.get("timestamp_utc")) for row in rows if str(row.get("canonical_opportunity_id")) in wanted and row.get("timestamp_utc")]
    return max(timestamps) if timestamps else None


def train_models(
    rows: Iterable[Mapping[str, Any]],
    splits: Mapping[str, str],
    *,
    vectors: Mapping[str, tuple[float, ...] | list[float]] | None = None,
    preprocessor: TrainOnlyPreprocessor | None = None,
    regimes: Mapping[str, Any] | None = None,
    dataset_fingerprint: str = "",
    split_version: str = "phase2-split/1",
    config: ModelConfig | None = None,
) -> ModelBundle:
    config = config or ModelConfig()
    records = sorted(rows, key=lambda row: (str(row.get("timestamp_utc", "")), str(row.get("canonical_opportunity_id", ""))))
    by_id = {str(row.get("canonical_opportunity_id")): row for row in records}
    if any(not str(row.get("canonical_opportunity_id") or "") for row in records):
        raise ValueError("model training input requires canonical_opportunity_id")
    if len(by_id) != len(records):
        raise ValueError("model training input contains duplicate canonical samples")
    usable = {
        identifier for identifier, row in by_id.items()
        if str(row.get("feature_status", "")).upper() != "CONFLICT"
    }
    # A conflicting audit merge is never selected as a training example.  The
    # row remains in the canonical/reporting layer with its conflict marker.
    training_ids = tuple(sorted(identifier for identifier, split in splits.items() if split == "TRAIN" and identifier in usable))
    validation_ids = tuple(sorted(identifier for identifier, split in splits.items() if split == "VALIDATION" and identifier in usable))
    if preprocessor is None:
        preprocessor = TrainOnlyPreprocessor.fit(records, training_ids, training_cutoff=_training_cutoff(records, training_ids))
    all_vectors = dict(vectors or preprocessor.transform(records))
    if any(identifier not in all_vectors for identifier in by_id):
        raise ValueError("feature vectors do not cover all canonical rows")
    train_label_ids = tuple(identifier for identifier in training_ids if build_label(by_id[identifier]) in (0, 1))
    train_regression_ids = tuple(identifier for identifier in training_ids if build_expected_r_label(by_id[identifier]) is not None)
    logistic = None
    ridge = None
    if len(train_label_ids) >= config.min_training_labels:
        logistic = fit_logistic_regression(
            [all_vectors[identifier] for identifier in train_label_ids],
            [int(build_label(by_id[identifier])) for identifier in train_label_ids],
            feature_names=preprocessor.output_names,
            fit_ids=train_label_ids,
            l2=config.logistic_l2,
            iterations=config.logistic_iterations,
            learning_rate=config.logistic_learning_rate,
        )
    if train_regression_ids:
        ridge = fit_ridge_regression(
            [all_vectors[identifier] for identifier in train_regression_ids],
            [float(build_expected_r_label(by_id[identifier])) for identifier in train_regression_ids],
            feature_names=preprocessor.output_names,
            fit_ids=train_regression_ids,
            l2=config.ridge_l2,
        )
    regimes = regimes or {}
    unconditional = fit_unconditional_prior(records, training_ids)
    regime_prior = fit_regime_prior(records, training_ids, regimes)
    calibration_ids = tuple(
        identifier for identifier in sorted(set(training_ids) | set(validation_ids))
        if build_label(by_id[identifier]) in (0, 1)
    )
    if logistic and calibration_ids:
        calibration_probabilities = [logistic.predict_proba(all_vectors[identifier]) for identifier in calibration_ids]
        calibration_labels = [int(build_label(by_id[identifier])) for identifier in calibration_ids]
        calibrator = fit_platt_calibrator(
            calibration_probabilities,
            calibration_labels,
            fit_ids=calibration_ids,
            iterations=config.calibration_iterations,
            learning_rate=config.calibration_learning_rate,
        )
    else:
        calibrator = PlattCalibrator(fit_ids=calibration_ids)
    status = "READY" if logistic or ridge or unconditional.support or unconditional.expected_support else "INSUFFICIENT_DATA"
    metadata = {
        "fit_scope": "TRAIN_ONLY",
        "calibration_scope": "TRAIN_VALIDATION_ONLY",
        "oos_used_for_fit": False,
        "feature_vector_count": len(all_vectors),
        "classification_train_count": len(train_label_ids),
        "regression_train_count": len(train_regression_ids),
        "classification_calibration_count": len(calibration_ids),
        "seed": config.seed,
        "config": config.to_dict(),
    }
    return ModelBundle(
        model_version=config.version,
        feature_set_version=preprocessor.feature_set_version,
        split_version=split_version,
        dataset_fingerprint=dataset_fingerprint,
        preprocessor=preprocessor,
        logistic=logistic,
        ridge=ridge,
        unconditional_prior=unconditional,
        regime_prior=regime_prior,
        calibrator=calibrator,
        training_ids=training_ids,
        calibration_ids=calibration_ids,
        training_cutoff=_training_cutoff(records, training_ids),
        seed=config.seed,
        status=status,
        metadata=metadata,
    )


__all__ = ["ModelBundle", "ModelConfig", "train_models"]
