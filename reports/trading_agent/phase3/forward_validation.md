# Phase 3 Forward Validation

- `PHASE3_ENGINEERING_STATUS`: `PASS`
- `LIVE_BRIDGE_READY`: `YES`
- `OFFLINE_LIVE_PARITY_STATUS`: `PASS`
- `BUNDLE_FREEZE_STATUS`: `PASS`
- `IDEMPOTENCY_STATUS`: `PASS`
- `RESTART_RECOVERY_STATUS`: `PASS`
- `PREDICTION_IMMUTABILITY_STATUS`: `PASS`
- `FORWARD_LEAKAGE_STATUS`: `PASS`
- `FORWARD_COLLECTION_STATUS`: `READY`
- `FORWARD_SAMPLE_COUNT`: `0`
- `FORWARD_PREDICTIVE_EDGE_STATUS`: `INSUFFICIENT_DATA`
- `LIVE_EXECUTION_ENABLED`: `NO`
- `READY_FOR_PHASE4`: `NO`

```json
{
  "auto_retrain": false,
  "auto_update_similarity_reference": false,
  "baselines_predeclared": [
    "unconditional_prior",
    "regime_prior",
    "historical_similarity",
    "logistic_phase2",
    "unconditional_expected_r",
    "ridge_phase2"
  ],
  "classification": {
    "historical_similarity": {
      "brier_score": null,
      "calibration_bins": [
        {
          "bin": 0,
          "count": 0,
          "lower": 0.0,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.1
        },
        {
          "bin": 1,
          "count": 0,
          "lower": 0.1,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.2
        },
        {
          "bin": 2,
          "count": 0,
          "lower": 0.2,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.3
        },
        {
          "bin": 3,
          "count": 0,
          "lower": 0.3,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.4
        },
        {
          "bin": 4,
          "count": 0,
          "lower": 0.4,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.5
        },
        {
          "bin": 5,
          "count": 0,
          "lower": 0.5,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.6
        },
        {
          "bin": 6,
          "count": 0,
          "lower": 0.6,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.7
        },
        {
          "bin": 7,
          "count": 0,
          "lower": 0.7,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.8
        },
        {
          "bin": 8,
          "count": 0,
          "lower": 0.8,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.9
        },
        {
          "bin": 9,
          "count": 0,
          "lower": 0.9,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 1.0
        }
      ],
      "count": 0,
      "expected_calibration_error": null,
      "log_loss": null,
      "pr_auc": null,
      "roc_auc": null
    },
    "logistic_phase2": {
      "brier_score": null,
      "calibration_bins": [
        {
          "bin": 0,
          "count": 0,
          "lower": 0.0,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.1
        },
        {
          "bin": 1,
          "count": 0,
          "lower": 0.1,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.2
        },
        {
          "bin": 2,
          "count": 0,
          "lower": 0.2,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.3
        },
        {
          "bin": 3,
          "count": 0,
          "lower": 0.3,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.4
        },
        {
          "bin": 4,
          "count": 0,
          "lower": 0.4,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.5
        },
        {
          "bin": 5,
          "count": 0,
          "lower": 0.5,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.6
        },
        {
          "bin": 6,
          "count": 0,
          "lower": 0.6,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.7
        },
        {
          "bin": 7,
          "count": 0,
          "lower": 0.7,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.8
        },
        {
          "bin": 8,
          "count": 0,
          "lower": 0.8,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.9
        },
        {
          "bin": 9,
          "count": 0,
          "lower": 0.9,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 1.0
        }
      ],
      "count": 0,
      "expected_calibration_error": null,
      "log_loss": null,
      "pr_auc": null,
      "roc_auc": null
    },
    "regime_prior": {
      "brier_score": null,
      "calibration_bins": [
        {
          "bin": 0,
          "count": 0,
          "lower": 0.0,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.1
        },
        {
          "bin": 1,
          "count": 0,
          "lower": 0.1,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.2
        },
        {
          "bin": 2,
          "count": 0,
          "lower": 0.2,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.3
        },
        {
          "bin": 3,
          "count": 0,
          "lower": 0.3,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.4
        },
        {
          "bin": 4,
          "count": 0,
          "lower": 0.4,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.5
        },
        {
          "bin": 5,
          "count": 0,
          "lower": 0.5,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.6
        },
        {
          "bin": 6,
          "count": 0,
          "lower": 0.6,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.7
        },
        {
          "bin": 7,
          "count": 0,
          "lower": 0.7,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.8
        },
        {
          "bin": 8,
          "count": 0,
          "lower": 0.8,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.9
        },
        {
          "bin": 9,
          "count": 0,
          "lower": 0.9,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 1.0
        }
      ],
      "count": 0,
      "expected_calibration_error": null,
      "log_loss": null,
      "pr_auc": null,
      "roc_auc": null
    },
    "unconditional_prior": {
      "brier_score": null,
      "calibration_bins": [
        {
          "bin": 0,
          "count": 0,
          "lower": 0.0,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.1
        },
        {
          "bin": 1,
          "count": 0,
          "lower": 0.1,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.2
        },
        {
          "bin": 2,
          "count": 0,
          "lower": 0.2,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.3
        },
        {
          "bin": 3,
          "count": 0,
          "lower": 0.3,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.4
        },
        {
          "bin": 4,
          "count": 0,
          "lower": 0.4,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.5
        },
        {
          "bin": 5,
          "count": 0,
          "lower": 0.5,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.6
        },
        {
          "bin": 6,
          "count": 0,
          "lower": 0.6,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.7
        },
        {
          "bin": 7,
          "count": 0,
          "lower": 0.7,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.8
        },
        {
          "bin": 8,
          "count": 0,
          "lower": 0.8,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 0.9
        },
        {
          "bin": 9,
          "count": 0,
          "lower": 0.9,
          "mean_predicted": null,
          "mean_realized": null,
          "upper": 1.0
        }
      ],
      "count": 0,
      "expected_calibration_error": null,
      "log_loss": null,
      "pr_auc": null,
      "roc_auc": null
    }
  },
  "classification_resolved_count": 0,
  "confidence_intervals": {
    "brier_improvement": {
      "count": 0,
      "estimate": null,
      "lower_95": null,
      "upper_95": null
    }
  },
  "coverage": {
    "calendar_end": null,
    "calendar_start": null,
    "markets": {},
    "regimes": {},
    "sides": {}
  },
  "coverage_sufficient": false,
  "forward_collection_status": "READY",
  "forward_predictive_edge_status": "INSUFFICIENT_DATA",
  "improvements": {
    "brier": null,
    "mae": null,
    "rmse": null
  },
  "outcome_used_for_model_fit": false,
  "regression": {
    "ridge_phase2": {
      "count": 0,
      "mae": null,
      "mean_predicted_r": null,
      "mean_realized_r": null,
      "median_absolute_error": null,
      "rmse": null,
      "spearman_rank_correlation": null
    },
    "unconditional_expected_r": {
      "count": 0,
      "mae": null,
      "mean_predicted_r": null,
      "mean_realized_r": null,
      "median_absolute_error": null,
      "rmse": null,
      "spearman_rank_correlation": null
    }
  },
  "regression_24bar_resolved_count": 0,
  "resolved_sample_count": 0,
  "schema": "trading_agent_phase3_forward_validation_v1"
}
```
