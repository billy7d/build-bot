"""Offline/shadow-only signal scoring components."""

from .labels import DIAGNOSTIC_TARGETS, build_diagnostic_target, build_expected_r_label, build_label, build_label_record
from .predict import ScoreRecord, assert_no_execution_action, score_opportunity
from .train import ModelBundle, ModelConfig, train_models
from .validation import evaluate_models, walk_forward_evaluate

__all__ = [
    "ModelBundle",
    "ModelConfig",
    "ScoreRecord",
    "DIAGNOSTIC_TARGETS",
    "assert_no_execution_action",
    "build_expected_r_label",
    "build_diagnostic_target",
    "build_label",
    "build_label_record",
    "evaluate_models",
    "score_opportunity",
    "train_models",
    "walk_forward_evaluate",
]
