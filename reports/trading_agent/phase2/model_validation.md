# Phase 2 Model Validation

- Dataset fingerprint: `NO_PHASE1_DATA`
- Base SHA: `180e0e95e519ed532583c1c69fc7d358ab29f4f1`
- Generation SHA: `180e0e95e519ed532583c1c69fc7d358ab29f4f1`
- Feature Set: `feature-store/1`
- Split version: `phase2-split/1`
- Regime version: `regime/1`
- Similarity version: `similarity/1`
- Model version: `scoring/1`
- Random seed: `42`

- Predictive edge status: `INSUFFICIENT_DATA`
- Fit scope: `TRAIN_ONLY`
- Calibration scope: `TRAIN_VALIDATION_ONLY`
- OOS used for tuning: `False`

## OOS

Rows: `0`

- Secondary target coverage: {"shadow_mae_r": {"count": 0, "mean_realized_r": null}, "shadow_mfe_r": {"count": 0, "mean_realized_r": null}, "shadow_return_12bar_r": {"count": 0, "mean_realized_r": null}, "shadow_return_48bar_r": {"count": 0, "mean_realized_r": null}, "shadow_return_6bar_r": {"count": 0, "mean_realized_r": null}}

## VALIDATION

Rows: `0`

- Secondary target coverage: {"shadow_mae_r": {"count": 0, "mean_realized_r": null}, "shadow_mfe_r": {"count": 0, "mean_realized_r": null}, "shadow_return_12bar_r": {"count": 0, "mean_realized_r": null}, "shadow_return_48bar_r": {"count": 0, "mean_realized_r": null}, "shadow_return_6bar_r": {"count": 0, "mean_realized_r": null}}

## Walk-forward

```json
{
  "aggregate": {
    "brier_improvement": null,
    "folds_with_comparison": 0
  },
  "config": {
    "calibration_iterations": 250,
    "calibration_learning_rate": 0.03,
    "logistic_iterations": 400,
    "logistic_l2": 1.0,
    "logistic_learning_rate": 0.05,
    "min_training_labels": 2,
    "ridge_l2": 1.0,
    "seed": 42,
    "version": "scoring/1"
  },
  "folds": [],
  "schema": "trading_agent_phase2_walk_forward_v1"
}
```
