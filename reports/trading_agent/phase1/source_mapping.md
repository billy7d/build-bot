# Phase 1 Source Mapping

## Version semantics

- `V26` và `V63` là execution strategy registry; `V81` và `V82` chỉ là audit/observation layer.
- V81: `strategy_version=V26`, `audit_version=V81`, parser `v81-parser/1`.
- V82: `strategy_version=V26`, `audit_version=V82`, parser `v82-parser/1`.
- Aggregate report không được chuyển thành episode-level rows.

## V81 mapping

| Raw field | Trading Memory |
| --- | --- |
| `time` | `trading_episodes.source_time`; normalized `timestamp_utc` |
| `event_id` | `trading_episodes.raw_event_id` |
| `side`, `entry_price`, `initial_sl` | episode side/candidate/stop |
| `conflict_type=FLAT_*` | `FLAT_CANDIDATE` |
| `conflict_type=OPEN_*` | `BLOCKED_OPPORTUNITY` |
| `entry_rsi` | `episode_features.rsi` |
| `entry_return_std_20` | `episode_features.return_std_20` |
| `entry_spread_r` | `episode_features.spread_r` |
| `entry_return_std_rank` | `episode_features.return_std_rank` |
| `entry_price_std_20/100` | `episode_features.price_std_20/100` |
| `entry_price_std_pct_20` | `episode_features.price_std_pct_20` |
| `entry_std_ratio_20_100` | `episode_features.std_ratio_20_100` |
| `entry_price_z20`, `entry_price_abs_z20` | `episode_features.price_z20/price_abs_z20` |
| `entry_rsi_std_20`, `entry_rsi_std_rank` | RSI StdDev feature columns |
| `entry_atr_return_std_ratio/rank` | ATR/return-StdDev feature columns |
| `return_6/12/24/48`, `mfe_r`, `mae_r`, `first_hit` | `episode_outcomes` |

## V82 mapping

| Raw field | Trading Memory |
| --- | --- |
| `event_type=BLOCKED_OPPOSITE` | `BLOCKED_OPPORTUNITY` |
| `event_type=BLOCKED_SAME_SIDE` | `BLOCKED_OPPORTUNITY` |
| `LONG_ONLY` / `SHORT_ONLY` | `CONTROL_OPPORTUNITY` |
| `SIMULTANEOUS_CONFLICT` | `SIMULTANEOUS_CONFLICT` |
| `active_current_r`, `active_bars_open`, `active_pyramid_adds` | `episode_active_context` |
| `active_value_at_event_r` | `episode_active_context.active_value_at_event_r` |
| `shadow_entry_rsi`, `entry_atr_pct`, bias/regime fields | event-time features/context |
| `entry_spread_r` | `episode_features.spread_r` |
| `shadow_*` outcome fields | `episode_opportunity_outcomes` |
| `active_continuation_*` | `episode_opportunity_outcomes` |
| `actual_selected_*` | `episode_opportunity_outcomes` only |
| `opportunity_diff_*` | `episode_opportunity_outcomes` only; label, never feature |
| `completed`, `incomplete_reason` | outcome resolution metadata |

Feature provenance is `SOURCE_REPORTED` for values copied from CSV. Missing values remain SQL `NULL`.
