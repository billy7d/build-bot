# Mentor_RSI_MTF_v1 - Implementation Notes

File da cap nhat: `Mentor_RSI_MTF_v1.mq5`

## Da trien khai

- Risk engine khong ep lot len `SYMBOL_VOLUME_MIN`. Neu lot tinh theo `RiskPerTradePct` nho hon lot toi thieu, bot skip trade va log ly do `raw_lot_below_min_lot`.
- Bias da tach khoi entry: D1/H4/H1 dung de tinh bias, M15/H1 entry chi dung timing theo `EntryTF`.
- Them `UseMTFBias` de chay ablation test core RSI only.
- Entry duoc noi theo co che armed setup: sau khi RSI cham extreme, setup con hieu luc trong `LookbackExtremeBars`.
- Them `EntryMode`:
  - `RSI_CROSS_EMA`: logic chat, can RSI cross EMA9 gan day.
  - `RSI_ABOVE_EMA_AFTER_EXTREME`: logic mo rong, sau extreme chi can RSI nam dung phia EMA9 va dang doc dung huong.
- Them `MaxSetupAgeBars`: setup co the song 48 nen mac dinh, tach khoi `LookbackExtremeBars`.
- Entry mac dinh doi sang `RSI_ABOVE_EMA_AFTER_EXTREME` de tang so luong lenh co kiem soat.
- TP1 partial close tai `TP1_R`, sau do keo SL ve entry.
- TP2 partial close theo RSI curl nguoc tren EntryTF/H1.
- Full exit khi H4 RSI deteriorate.
- Da bo toan bo filter va indicator baseline cu. Bias, entry, exit, chop, trailing chi con dung RSI/EMA/WMA/ATR va gia/SL.
- Them diagnostic log moi nen entry TF: armed state, bias count, reject counters, snapshot RSI/EMA/WMA/ATR cho D1/H4/H1/M15.
- Them `DiagnosticsEveryBars` de giam nhieu log va `ExportDiagnosticsCsv` de xuat file `Mentor_RSI_MTF_diag.csv` trong `MQL5/Files`.
- Them summary log `DIAG_SUMMARY` khi ket thuc backtest/deinit.
- V4:
  - Them `LongArmLevel` va `ShortArmLevel` de arm setup rong hon ma van giu `Oversold/Overbought` cho exit cuc tri.
  - Them `BiasMode`: `STRICT_COUNT` va `HTF_VETO`; mac dinh `HTF_VETO` de tang co hoi vao lenh co kiem soat.
  - Bo long no-chase theo khoang cach baseline cu.
  - Them `TrailMode`: `OFF`, `ATR_CHANDELIER`; mac dinh nen test `ATR_CHANDELIER`.
  - Them `ATRPeriod`, `TrailLookbackBars`, `TrailATRMultiplier`, `StartTrailingAfterR`, `RunnerMinPct` de giu runner cho lenh thang lon.
- V5:
  - Them `EntryMode=RSI_PULLBACK_CONTINUATION` de tang tan suat lenh trong core RSI MTF ma khong them Volume/VWAP/Trap.
  - Them `PullbackLongLevel`, `PullbackShortLevel`, `PullbackLookbackBars`. Mode nay chap nhan setup neu RSI gan day pullback ve vung 50/50, sau do RSI nam dung phia EMA9, EMA9 doc dung huong, va RSI bar hien tai cung doc dung huong.
  - Sua quan ly lenh de giu `initial risk distance` rieng cho position. Truoc day sau khi SL duoc keo ve entry, R-multiple co the bi tinh lai theo SL moi, lam trailing/partial exit kich hoat sai nhip.
  - Diagnostic reject da tinh ca setup pullback, khong chi tinh setup armed tu extreme.

## Preset files

Da tao cac preset tai thu muc `outputs/presets`:

- `01_core_rsi_only.set`
- `02_core_rsi_mtf.set`
- `03_core_rsi_mtf_bias.set`
- `04_full_v1_filter.set`
- `05_expanded_35_65.set`
- `06_v4_core_htf_veto_no_trailing.set`
- `07_v4_htf_veto_atr_trailing_no_long_filter.set`
- `08_v4_htf_veto_atr_trailing_long_filter.set`
- `09_v4_40_60_more_trades_trailing.set`
- `10_v5_pullback_m15_trailing_balanced.set`
- `11_v5_pullback_h1_trailing_balanced.set`
- `12_v5_pullback_m15_rsi_only_filter.set`

## Preset V4/V5 nen chay doc lap

Moi preset la mot cau hinh doc lap. Khong can chay noi tiep. Khi so sanh, giu nguyen symbol, date range, deposit, leverage, commission, spread, modelling quality.

1. `06_v4_core_htf_veto_no_trailing.set`
   - Muc tieu: do rieng tac dong cua core RSI + bias moi.
2. `07_v4_htf_veto_atr_trailing_no_long_filter.set`
   - Muc tieu: do tac dong cua ATR trailing tren core RSI + HTF_VETO.
3. `08_v4_htf_veto_atr_trailing_long_filter.set`
   - Preset legacy tu ban co long filter cu; sau khi bo baseline filter, cau hinh nay co the trung voi `07`.
4. `09_v4_40_60_more_trades_trailing.set`
   - Muc tieu: tang so lenh neu 35/65 van duoi 60 trades.
5. `10_v5_pullback_m15_trailing_balanced.set`
   - Muc tieu: tang so lenh bang RSI pullback/continuation tren M15, van giu HTF_VETO, chop filter, ATR trailing.
6. `11_v5_pullback_h1_trailing_balanced.set`
   - Muc tieu: kiem tra cung logic pullback nhung timing tren H1 de giam nhieu va so sanh Long/Short.
7. `12_v5_pullback_m15_rsi_only_filter.set`
   - Muc tieu: ban pullback M15 toi gian hon, chi giu RSI MTF + chop + ATR trailing.

## Preset backtest uu tien

Chay tren BTCUSD truoc, cung mot giai doan report cu neu co the:

1. Core RSI only
   - `UseMTFBias=false`
   - `UseChopFilter=false`
   - `EntryMode=RSI_ABOVE_EMA_AFTER_EXTREME`

2. Core RSI + MTF
   - `UseMTFBias=true`
   - `MinAlignedTimeframes=2`
   - `UseChopFilter=false`
   - `EntryMode=RSI_ABOVE_EMA_AFTER_EXTREME`

3. Core RSI + MTF legacy
   - `UseMTFBias=true`
   - `MinAlignedTimeframes=2`
   - `UseChopFilter=false`
   - `EntryMode=RSI_ABOVE_EMA_AFTER_EXTREME`
   - Sau khi bo baseline filter, preset nay co the trung voi Core RSI + MTF.

4. Full v1 filter
   - `UseMTFBias=true`
   - `MinAlignedTimeframes=2`
   - `UseChopFilter=true`
   - `EntryMode=RSI_ABOVE_EMA_AFTER_EXTREME`

## Matrix toi uu toi thieu

- `EntryTF`: M15, H1
- `LookbackExtremeBars`: 12, 24, 48
- `MaxSetupAgeBars`: 24, 48, 72
- `MaxBarsAfterCross`: 2, 5, 8
- `PullbackLongLevel/PullbackShortLevel`: 48/52, 50/50, 52/48
- `PullbackLookbackBars`: 12, 24, 48
- `MinAlignedTimeframes`: 2, 3
- `Oversold/Overbought`: 30/70, 35/65, 40/60
- `BiasMode`: HTF_VETO, STRICT_COUNT
- `EntryMode`: RSI_ABOVE_EMA_AFTER_EXTREME, RSI_PULLBACK_CONTINUATION
- `TrailMode`: OFF, ATR_CHANDELIER
- `TrailATRMultiplier`: 2.5, 3.0, 3.5
- `StartTrailingAfterR`: 1.5, 2.0, 2.5

Chi xem cau hinh la ung vien neu co toi thieu 60 lenh, Profit Factor >= 1.20, Expected Payoff duong, Equity DD <= 12%, Long PF >= 1.0 hoac Long winrate khong kem Short qua 10 diem phan tram.

## Luu y quan trong

Voi BTCUSD va tai khoan 1,000 USD, broker co the bat lot toi thieu 0.01. Neu risk 0.5% qua nho, bot se skip nhieu lenh. De test dung risk engine, hay so sanh:

- Tang initial deposit trong tester.
- Hoac tang `RiskPerTradePct` tam thoi de kiem tra logic entry/exit.
- Hoac dung symbol/account co lot step nho hon.
