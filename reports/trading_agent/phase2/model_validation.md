# Phase 2 Model Validation

- Dataset fingerprint: `2dc6dcd74928ed00923fd21f032ba0700f1c9c50459c9e0159872aa2045680ff`
- Base SHA: `180e0e95e519ed532583c1c69fc7d358ab29f4f1`
- Generation SHA: `ae33133d09cc04b4acaeba4422791382957cc999`
- Feature Set: `feature-store/1`
- Split version: `phase2-split/1`
- Regime version: `regime/1`
- Similarity version: `similarity/1`
- Model version: `scoring/1`
- Random seed: `42`

- Predictive edge status: `NOT_DEMONSTRATED`
- Fit scope: `TRAIN_ONLY`
- Calibration scope: `TRAIN_VALIDATION_ONLY`
- OOS used for tuning: `False`

## OOS

Rows: `1544`

- Classification `historical_similarity`: count=798, Brier=0.26402063669074805, ROC-AUC=0.5259284420289855, PR-AUC=0.5552350517576098
- Classification `logistic_regression`: count=798, Brier=0.25327358674622236, ROC-AUC=0.4672592089371981, PR-AUC=0.4849721667288824
- Classification `regime_prior`: count=798, Brier=0.25697048800099026, ROC-AUC=0.46347561896135264, PR-AUC=0.49420863416191463
- Classification `unconditional_prior`: count=798, Brier=0.2506327608442904, ROC-AUC=0.5, PR-AUC=0.5281369460267085
- Regression `historical_similarity`: count=856, MAE=1.5739312408095427, RMSE=2.269367258247136, Spearman=0.07616714334063603
- Regression `regime_prior`: count=856, MAE=1.5866023571082237, RMSE=2.240794457269635, Spearman=-0.027764739414619346
- Regression `ridge_regression`: count=856, MAE=2.486108204725833, RMSE=3.0732700355146267, Spearman=0.15537311910841783
- Regression `unconditional_prior`: count=856, MAE=1.544923951523405, RMSE=2.2155897667948055, Spearman=None
- Secondary target coverage: {"shadow_mae_r": {"count": 1534, "mean_realized_r": -1.7330449263363747}, "shadow_mfe_r": {"count": 1534, "mean_realized_r": 2.2139505977835734}, "shadow_return_12bar_r": {"count": 1534, "mean_realized_r": 0.019191487614080825}, "shadow_return_48bar_r": {"count": 1534, "mean_realized_r": 0.2929795254237287}, "shadow_return_6bar_r": {"count": 1534, "mean_realized_r": 0.024605737940026066}}

## VALIDATION

Rows: `1072`

- Classification `historical_similarity`: count=617, Brier=0.282070485379606, ROC-AUC=0.4733607855559075, PR-AUC=0.5309617400306239
- Classification `logistic_regression`: count=617, Brier=0.25027598418317454, ROC-AUC=0.5090592334494773, PR-AUC=0.5613047356465624
- Classification `regime_prior`: count=617, Brier=0.2541394508017904, ROC-AUC=0.4653626860943934, PR-AUC=0.5218692597161196
- Classification `unconditional_prior`: count=617, Brier=0.25103735840796554, ROC-AUC=0.5, PR-AUC=0.5039894763132245
- Regression `historical_similarity`: count=691, MAE=1.6141975443274785, RMSE=2.3799668774582874, Spearman=-0.08246434155583093
- Regression `regime_prior`: count=691, MAE=1.552682789475087, RMSE=2.298293351568453, Spearman=-0.07050431586403728
- Regression `ridge_regression`: count=691, MAE=2.318409173417162, RMSE=2.925098336758625, Spearman=-0.01943590245314675
- Regression `unconditional_prior`: count=691, MAE=1.5178534452266692, RMSE=2.2595254744926305, Spearman=None
- Secondary target coverage: {"shadow_mae_r": {"count": 1068, "mean_realized_r": -1.860215627340828}, "shadow_mfe_r": {"count": 1068, "mean_realized_r": 2.024857611423218}, "shadow_return_12bar_r": {"count": 1068, "mean_realized_r": -0.0650028333333333}, "shadow_return_48bar_r": {"count": 1068, "mean_realized_r": 0.09534362734082406}, "shadow_return_6bar_r": {"count": 1068, "mean_realized_r": -0.050955848314606735}}

## Walk-forward

```json
{
  "aggregate": {
    "brier_improvement": -0.00030541851034097955,
    "folds_with_comparison": 2
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
  "folds": [
    {
      "abstention_count": 377,
      "classification": {
        "logistic_regression": {
          "brier_score": 0.2513087335225276,
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
              "count": 4,
              "lower": 0.3,
              "mean_predicted": 0.38821198595416806,
              "mean_realized": 0.5,
              "upper": 0.4
            },
            {
              "bin": 4,
              "count": 413,
              "lower": 0.4,
              "mean_predicted": 0.4670221254550189,
              "mean_realized": 0.5351089588377724,
              "upper": 0.5
            },
            {
              "bin": 5,
              "count": 200,
              "lower": 0.5,
              "mean_predicted": 0.5231056543286332,
              "mean_realized": 0.535,
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
          "count": 617,
          "expected_calibration_error": 0.050155402556781026,
          "log_loss": 0.6957680598352343,
          "pr_auc": 0.5613047356465624,
          "roc_auc": 0.5090592334494773
        },
        "unconditional_prior": {
          "brier_score": 0.2510373584079472,
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
              "count": 617,
              "lower": 0.4,
              "mean_predicted": 0.4873949579831932,
              "mean_realized": 0.5348460291734197,
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
          "count": 617,
          "expected_calibration_error": 0.04745107119022651,
          "log_loss": 0.6952223707483831,
          "pr_auc": 0.5039894763132245,
          "roc_auc": 0.5
        }
      },
      "evaluated_count": 695,
      "evaluation_count": 1072,
      "evaluation_end": "2024-12-30T05:00:00Z",
      "evaluation_split": "VALIDATION",
      "evaluation_start": "2024-01-01T06:00:00Z",
      "oos_used_for_fit": false,
      "regression": {
        "count": 691,
        "mae": 2.318409173423494,
        "mean_predicted_r": -1.5837469714032395,
        "mean_realized_r": -0.03534440810419689,
        "median_absolute_error": 1.9960957625389795,
        "rmse": 2.925098336764156,
        "spearman_rank_correlation": -0.01943590245314675
      },
      "temporal_guard": true,
      "training_count": 1002,
      "training_end": "2023-12-30T08:00:00Z",
      "training_start": "2023-01-01T01:00:00Z"
    },
    {
      "abstention_count": 76,
      "classification": {
        "logistic_regression": {
          "brier_score": 0.25027125775298886,
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
              "count": 571,
              "lower": 0.4,
              "mean_predicted": 0.4873838690629668,
              "mean_realized": 0.5253940455341506,
              "upper": 0.5
            },
            {
              "bin": 5,
              "count": 702,
              "lower": 0.5,
              "mean_predicted": 0.5216577121857343,
              "mean_realized": 0.5341880341880342,
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
          "count": 1273,
          "expected_calibration_error": 0.02395922765959186,
          "log_loss": 0.6936902901551809,
          "pr_auc": 0.5334720736254889,
          "roc_auc": 0.4959395515917255
        },
        "unconditional_prior": {
          "brier_score": 0.24993179584688727,
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
              "count": 1273,
              "lower": 0.5,
              "mean_predicted": 0.501149425287358,
              "mean_realized": 0.5302435192458759,
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
          "count": 1273,
          "expected_calibration_error": 0.02909409395851792,
          "log_loss": 0.6930107720157695,
          "pr_auc": 0.5389810047185484,
          "roc_auc": 0.5
        }
      },
      "evaluated_count": 1468,
      "evaluation_count": 1544,
      "evaluation_end": "2026-06-30T18:00:00Z",
      "evaluation_split": "OOS",
      "evaluation_start": "2025-01-03T08:00:00Z",
      "oos_used_for_fit": false,
      "regression": {
        "count": 1458,
        "mae": 1.3578285555286644,
        "mean_predicted_r": -0.02535415309130801,
        "mean_realized_r": 0.11645292524005481,
        "median_absolute_error": 0.8632627718672323,
        "rmse": 2.046931009507804,
        "spearman_rank_correlation": 0.05942977135903577
      },
      "temporal_guard": true,
      "training_count": 2074,
      "training_end": "2024-12-30T05:00:00Z",
      "training_start": "2023-01-01T01:00:00Z"
    }
  ],
  "schema": "trading_agent_phase2_walk_forward_v1"
}
```
